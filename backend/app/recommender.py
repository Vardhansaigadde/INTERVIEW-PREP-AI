"""Recommendation engine.

For each topic it combines:
  * mastery    - smoothed quiz accuracy, with recent answers counting more
  * struggle   - share of negative emotions (confused/frustrated) seen while studying the topic
  * staleness  - how long since the topic was last practised
and turns these into a priority score. In a live session it also reacts to the
student's emotions over the last few seconds.
"""
from collections import Counter
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import Attempt, EmotionLog, Material, Question, Topic

NEGATIVE = {"confused", "frustrated"}
W_MASTERY, W_STRUGGLE, W_STALE = 0.6, 0.3, 0.1


def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def topic_stats(db: Session, user_id: int) -> list[dict]:
    topics = db.scalars(select(Topic).order_by(Topic.id)).all()
    attempts = db.scalars(select(Attempt).where(Attempt.user_id == user_id).order_by(Attempt.id)).all()
    emotions = db.scalars(
        select(EmotionLog).where(EmotionLog.user_id == user_id, EmotionLog.topic_id.is_not(None))
    ).all()
    now = datetime.now(timezone.utc)

    stats = []
    for t in topics:
        ta = [a for a in attempts if a.topic_id == t.id]
        # Recent answers weigh more: weight 1.0 for the latest, then decaying
        weighted_correct = weighted_total = 0.0
        for i, a in enumerate(reversed(ta)):
            w = 0.85 ** i
            weighted_total += w
            weighted_correct += w * a.correct
        mastery = (weighted_correct + 1) / (weighted_total + 2)  # Laplace smoothing, 0.5 when no data

        te = [e for e in emotions if e.topic_id == t.id][-50:]
        struggle = sum(e.state in NEGATIVE for e in te) / len(te) if te else 0.0

        last = max((_aware(a.created_at) for a in ta), default=None)
        days = (now - last).total_seconds() / 86400 if last else 7.0
        staleness = min(days / 7.0, 1.0)

        priority = W_MASTERY * (1 - mastery) + W_STRUGGLE * struggle + W_STALE * staleness
        stats.append({
            "topic_id": t.id,
            "topic": t.name,
            "subject": t.subject.name,
            "attempts": len(ta),
            "correct": sum(a.correct for a in ta),
            "mastery": round(mastery, 3),
            "struggle": round(struggle, 3),
            "staleness": round(staleness, 3),
            "priority": round(priority, 3),
        })
    return stats


def level_for(mastery: float, struggle: float) -> str:
    if struggle > 0.4 or mastery < 0.45:
        return "basic"
    return "advanced" if mastery >= 0.75 else "basic"


def difficulty_for(mastery: float, struggle: float) -> int:
    if struggle > 0.4 or mastery < 0.4:
        return 1
    return 3 if mastery >= 0.75 else 2


def study_plan(db: Session, user_id: int, limit: int = 4) -> list[dict]:
    stats = sorted(topic_stats(db, user_id), key=lambda s: s["priority"], reverse=True)[:limit]
    plan = []
    for s in stats:
        level = level_for(s["mastery"], s["struggle"])
        material = db.scalar(select(Material).where(Material.topic_id == s["topic_id"], Material.level == level))
        if s["attempts"] == 0:
            reason = "Not practised yet. Start with the basics."
        elif s["struggle"] > 0.4:
            reason = "You looked confused or frustrated on this topic. Go over the simpler notes again."
        elif s["mastery"] < 0.5:
            reason = "Low quiz accuracy. This is a weak area."
        elif s["mastery"] >= 0.75:
            reason = "Strong here. Try the advanced material to lock it in."
        else:
            reason = "Getting there. More practice will help."
        plan.append({**s, "level": level, "material_id": material.id if material else None,
                     "material_title": material.title if material else None, "reason": reason})
    return plan


def pick_question(db: Session, user_id: int, topic_id: int, difficulty: int | None = None) -> Question | None:
    """Pick an unseen (or least-recently-correct) question near the target difficulty."""
    if difficulty is None:
        s = next((x for x in topic_stats(db, user_id) if x["topic_id"] == topic_id), None)
        difficulty = difficulty_for(s["mastery"], s["struggle"]) if s and s["attempts"] else 1
    questions = db.scalars(select(Question).where(Question.topic_id == topic_id)).all()
    if not questions:
        return None
    attempts = db.scalars(select(Attempt).where(Attempt.user_id == user_id, Attempt.topic_id == topic_id)).all()
    seen_correct = {a.question_id for a in attempts if a.correct}
    seen = Counter(a.question_id for a in attempts)

    def score(q: Question):
        return (q.id in seen_correct, abs(q.difficulty - difficulty), seen[q.id], q.id)

    return min(questions, key=score)


def smooth_state(recent_states: list[str], window: int = 3) -> str:
    """State to show the student: the most common of the last few frames (ties go to the newest), so the label doesn't flicker."""
    last = recent_states[-window:]
    counts = Counter(last)
    best = max(counts.values())
    return next(s for s in reversed(last) if counts[s] == best)


def live_feedback(recent_states: list[str]) -> dict | None:
    """React to the student's emotions over the last few readings (newest last)."""
    if len(recent_states) < 3:
        return None
    window = recent_states[-6:]
    counts = Counter(window)
    n = len(window)
    if counts["distracted"] / n >= 0.6:
        return {"type": "break", "message": "You seem to be away from the screen. Take a short 5-minute break, then come back."}
    if counts["frustrated"] / n >= 0.5:
        return {"type": "easier", "message": "You seem frustrated. Here is a simpler explanation and an easier question."}
    if (counts["confused"] + counts["frustrated"]) / n >= 0.5:
        return {"type": "explain", "message": "You look a bit confused. Want to go over the notes for this topic again?"}
    if counts["engaged"] / n >= 0.6:
        return {"type": "harder", "message": "You're doing well! Ready for a harder question?"}
    return None
