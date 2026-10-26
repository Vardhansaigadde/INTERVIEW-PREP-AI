import hmac
import logging
import os
import random
from collections import Counter
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path

from fastapi import Depends, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from . import intent as intent_model
from . import interview
from . import recommender
from .auth import DEFAULT_SECRET, SECRET_KEY, create_token, current_user, hash_password, require_teacher, verify_password
from .db import Base, SessionLocal, engine, get_db
from .emotion import NEUTRAL_FACE_MEAN, get_detector
from .models import Attempt, EmotionLog, Material, Question, StudySession, Subject, Topic, User
from .seed import seed_content

FRONTEND_DIST = Path(__file__).resolve().parents[2] / "frontend" / "dist"
# Teachers can see every student's progress, so creating a teacher account needs this code.
TEACHER_SIGNUP_CODE = os.getenv("TEACHER_SIGNUP_CODE", "TEACH-2026")
log = logging.getLogger("uvicorn.error")


@asynccontextmanager
async def lifespan(app: FastAPI):
    if SECRET_KEY == DEFAULT_SECRET:
        log.warning("SECRET_KEY is the built-in development value. Set the SECRET_KEY environment variable before deploying.")
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        seed_content(db)
    get_detector()
    intent_model.get_model()
    yield


app = FastAPI(title="AI Interview Prep Assistant", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(interview.router)


# ---------- schemas ----------
class Credentials(BaseModel):
    username: str = Field(min_length=3, max_length=64)
    password: str = Field(min_length=6, max_length=128)


class RegisterIn(Credentials):
    role: str = Field(default="student", pattern="^(student|teacher)$")
    teacher_code: str | None = Field(default=None, max_length=128)


class AnswerIn(BaseModel):
    question_id: int
    selected: str
    session_id: int | None = None


class VoiceIn(BaseModel):
    text: str = Field(min_length=1, max_length=500)
    topic_id: int | None = None
    question_id: int | None = None
    eliminated: list[str] = Field(default_factory=list, max_length=10)  # options a previous hint already crossed out


# ---------- helpers ----------
def question_out(q: Question) -> dict:
    options = list(q.options)
    random.shuffle(options)
    return {"id": q.id, "topic_id": q.topic_id, "text": q.text, "options": options, "difficulty": q.difficulty}


def material_out(m: Material) -> dict:
    return {"id": m.id, "topic_id": m.topic_id, "title": m.title, "level": m.level, "body": m.body, "url": m.url}


def own_session(db: Session, user: User, session_id: int | None) -> int | None:
    if session_id is None:
        return None
    s = db.get(StudySession, session_id)
    if s is None or s.user_id != user.id:
        raise HTTPException(404, "Session not found")
    return s.id


# ---------- auth ----------
@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.post("/api/auth/register")
def register(body: RegisterIn, db: Session = Depends(get_db)):
    if body.role == "teacher" and not hmac.compare_digest(body.teacher_code or "", TEACHER_SIGNUP_CODE):
        raise HTTPException(403, "A valid teacher code is needed to create a teacher account")
    if db.scalar(select(User).where(User.username == body.username)):
        raise HTTPException(409, "Username already taken")
    user = User(username=body.username, password_hash=hash_password(body.password), role=body.role)
    db.add(user)
    db.commit()
    return {"token": create_token(user), "user": {"id": user.id, "username": user.username, "role": user.role}}


@app.post("/api/auth/login")
def login(body: Credentials, db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.username == body.username))
    if user is None or not verify_password(body.password, user.password_hash):
        raise HTTPException(401, "Wrong username or password")
    return {"token": create_token(user), "user": {"id": user.id, "username": user.username, "role": user.role}}


@app.get("/api/me")
def me(user: User = Depends(current_user)):
    return {"id": user.id, "username": user.username, "role": user.role}


# ---------- content ----------
@app.get("/api/subjects")
def subjects(db: Session = Depends(get_db), user: User = Depends(current_user)):
    out = []
    for s in db.scalars(select(Subject).order_by(Subject.id)):
        out.append({"id": s.id, "name": s.name, "topics": [{"id": t.id, "name": t.name} for t in s.topics]})
    return out


@app.get("/api/topics/{topic_id}")
def topic_detail(topic_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    t = db.get(Topic, topic_id)
    if t is None:
        raise HTTPException(404, "Topic not found")
    return {"id": t.id, "name": t.name, "subject": t.subject.name, "materials": [material_out(m) for m in t.materials]}


@app.get("/api/topics/{topic_id}/question")
def next_question(topic_id: int, difficulty: int | None = None, db: Session = Depends(get_db),
                  user: User = Depends(current_user)):
    q = recommender.pick_question(db, user.id, topic_id, difficulty)
    if q is None:
        raise HTTPException(404, "No questions for this topic")
    return question_out(q)


@app.post("/api/answer")
def answer(body: AnswerIn, db: Session = Depends(get_db), user: User = Depends(current_user)):
    q = db.get(Question, body.question_id)
    if q is None:
        raise HTTPException(404, "Question not found")
    correct_option = q.options[q.answer]
    correct = body.selected.strip() == correct_option
    db.add(Attempt(user_id=user.id, question_id=q.id, topic_id=q.topic_id,
                   session_id=own_session(db, user, body.session_id), correct=correct))
    db.commit()
    return {"correct": correct, "correct_option": correct_option, "explanation": q.explanation}


# ---------- study sessions & emotion ----------
@app.post("/api/sessions")
def start_session(db: Session = Depends(get_db), user: User = Depends(current_user)):
    s = StudySession(user_id=user.id)
    db.add(s)
    db.commit()
    return {"session_id": s.id}


@app.post("/api/sessions/{session_id}/end")
def end_session(session_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    s = db.get(StudySession, own_session(db, user, session_id))
    s.ended_at = datetime.now(timezone.utc)
    db.commit()
    _baselines.pop(s.id, None)
    logs = db.scalars(select(EmotionLog).where(EmotionLog.session_id == s.id)).all()
    attempts = db.scalars(select(Attempt).where(Attempt.session_id == s.id)).all()
    return {
        "session_id": s.id,
        "states": dict(Counter(l.state for l in logs)),
        "questions": len(attempts),
        "correct": sum(a.correct for a in attempts),
    }


# Per-session resting-face baseline, measured on the first few frames with a face.
# Kept in memory: after a server restart the session simply calibrates again.
CALIBRATION_FRAMES = 4
MAX_BASELINE_SHIFT = 0.15  # never let calibration hide a strong expression
_baselines: dict[int, dict] = {}


def _baseline_for(sid: int | None) -> tuple[dict | None, bool]:
    """Return (baseline to use, still calibrating?)."""
    if sid is None:
        return None, False
    b = _baselines.get(sid)
    if b is None or b["n"] < CALIBRATION_FRAMES:
        return None, True
    return b["mean"], False


def _update_baseline(sid: int, groups: dict):
    b = _baselines.setdefault(sid, {"n": 0, "sum": {k: 0.0 for k in groups}})
    if b["n"] >= CALIBRATION_FRAMES:
        return
    b["n"] += 1
    for k, v in groups.items():
        b["sum"][k] += v
    b["mean"] = {k: min(v / b["n"], NEUTRAL_FACE_MEAN[k] + MAX_BASELINE_SHIFT) for k, v in b["sum"].items()}


@app.post("/api/emotion/frame")
async def emotion_frame(
    file: UploadFile = File(...),
    session_id: int | None = Form(None),
    topic_id: int | None = Form(None),
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    data = await file.read()
    if len(data) > 2_000_000:
        raise HTTPException(413, "Frame too large")
    sid = own_session(db, user, session_id)
    if topic_id is not None and db.get(Topic, topic_id) is None:
        topic_id = None
    baseline, calibrating = _baseline_for(sid)
    try:
        result = get_detector().analyze_bytes(data, baseline)
    except ValueError as e:
        raise HTTPException(400, str(e))
    if calibrating and result.groups and result.state != "distracted":
        _update_baseline(sid, result.groups)
    db.add(EmotionLog(user_id=user.id, session_id=sid, topic_id=topic_id, emotion=result.emotion,
                      state=result.state, confidence=result.confidence))
    db.commit()
    feedback = None
    shown_state = result.state
    if sid is not None:
        recent = list(reversed(db.scalars(select(EmotionLog.state).where(EmotionLog.session_id == sid)
                                          .order_by(EmotionLog.id.desc()).limit(6)).all()))
        feedback = recommender.live_feedback(recent)
        if calibrating and feedback and feedback["type"] != "break":
            feedback = None  # expression-based tips wait until we know the student's resting face
        shown_state = recommender.smooth_state(recent)
    return {"emotion": result.emotion, "state": shown_state, "raw_state": result.state,
            "confidence": round(result.confidence, 3), "scores": result.scores,
            "groups": {k: round(v, 3) for k, v in result.groups.items()}, "reason": result.reason,
            "face_box": result.face_box, "calibrating": calibrating, "feedback": feedback}


# ---------- voice commands ----------
@app.post("/api/voice/command")
def voice_command(body: VoiceIn, db: Session = Depends(get_db), user: User = Depends(current_user)):
    intent, conf = intent_model.predict(body.text)
    resp: dict = {"text": body.text, "intent": intent, "confidence": round(conf, 3)}
    topic_id = body.topic_id

    if intent == "recommend" or (topic_id is None and intent in {"explain", "easier", "harder", "quiz", "next"}):
        plan = recommender.study_plan(db, user.id, limit=1)
        if plan:
            topic_id = plan[0]["topic_id"]
            resp["topic_id"] = topic_id
            resp["message"] = f"Let's study {plan[0]['topic']}. {plan[0]['reason']}"

    if intent in {"explain", "easier", "harder"} and topic_id:
        level = "advanced" if intent == "harder" else "basic"
        m = db.scalar(select(Material).where(Material.topic_id == topic_id, Material.level == level))
        if m:
            resp["material"] = material_out(m)
    if intent in {"quiz", "next", "easier", "harder", "recommend"} and topic_id:
        difficulty = {"easier": 1, "harder": 3}.get(intent)
        q = recommender.pick_question(db, user.id, topic_id, difficulty)
        if q:
            resp["question"] = question_out(q)
    if intent == "hint" and body.question_id:
        q = db.get(Question, body.question_id)
        if q:
            m = db.scalar(select(Material).where(Material.topic_id == q.topic_id, Material.level == "basic"))
            resp["message"] = "Hint: " + (m.body.splitlines()[0] if m else "Read the question again slowly.")
            wrong = [o for i, o in enumerate(q.options) if i != q.answer and o not in body.eliminated]
            if len(wrong) > 1:  # always leave at least one wrong option so the hint doesn't give the answer away
                resp["eliminate"] = random.choice(wrong)
            else:
                resp["message"] += " (That's all the help I can give on this one. You've got this!)"
    if intent == "repeat" and body.question_id:
        q = db.get(Question, body.question_id)
        if q:
            resp["message"] = q.text
    if intent in {"hint", "repeat"} and not body.question_id:
        resp["message"] = "There's no question open yet. Say 'quiz me' to get one."
    if intent == "progress":
        weak = sorted(recommender.topic_stats(db, user.id), key=lambda s: s["mastery"])[:2]
        resp["message"] = "Your weakest topics right now: " + ", ".join(
            f"{s['topic']} ({round(s['mastery'] * 100)}%)" for s in weak)
    if intent == "break":
        resp["message"] = "Good idea. Take 5 minutes, have some water, and come back fresh."
    if intent == "unknown":
        resp["message"] = "Sorry, I didn't catch that. Try 'explain this', 'quiz me', 'next question' or 'give me a hint'."
    return resp


# ---------- progress & recommendations ----------
@app.get("/api/progress")
def progress(db: Session = Depends(get_db), user: User = Depends(current_user)):
    stats = recommender.topic_stats(db, user.id)
    logs = db.scalars(select(EmotionLog).where(EmotionLog.user_id == user.id).order_by(EmotionLog.id.desc()).limit(500)).all()
    attempts = db.scalars(select(Attempt).where(Attempt.user_id == user.id).order_by(Attempt.id)).all()
    sessions = db.scalars(select(StudySession).where(StudySession.user_id == user.id)).all()
    total = len(attempts)
    return {
        "topics": stats,
        "emotion_summary": dict(Counter(l.state for l in logs)),
        "total_attempts": total,
        "accuracy": round(sum(a.correct for a in attempts) / total, 3) if total else None,
        "sessions": len(sessions),
        "history": [{"t": a.created_at.isoformat(), "correct": a.correct, "topic_id": a.topic_id} for a in attempts[-100:]],
    }


@app.get("/api/recommendations")
def recommendations(db: Session = Depends(get_db), user: User = Depends(current_user)):
    return recommender.study_plan(db, user.id)


@app.get("/api/materials/{material_id}")
def material(material_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    m = db.get(Material, material_id)
    if m is None:
        raise HTTPException(404, "Material not found")
    return material_out(m)


# ---------- teacher ----------
@app.get("/api/teacher/students")
def teacher_students(db: Session = Depends(get_db), teacher: User = Depends(require_teacher)):
    out = []
    for u in db.scalars(select(User).where(User.role == "student").order_by(User.username)):
        stats = recommender.topic_stats(db, u.id)
        practised = [s for s in stats if s["attempts"]]
        attempts = sum(s["attempts"] for s in stats)
        out.append({
            "id": u.id,
            "username": u.username,
            "attempts": attempts,
            "accuracy": round(sum(s["correct"] for s in stats) / attempts, 3) if attempts else None,
            "weak_topics": [s["topic"] for s in sorted(practised, key=lambda s: s["mastery"])[:3] if s["mastery"] < 0.6],
            "struggling_topics": [s["topic"] for s in stats if s["struggle"] > 0.4],
        })
    return out


# ---------- serve built frontend ----------
if FRONTEND_DIST.exists():
    app.mount("/assets", StaticFiles(directory=FRONTEND_DIST / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str):
        if path == "api" or path.startswith("api/"):
            raise HTTPException(404, "Not found")
        target = FRONTEND_DIST / path
        if path and target.is_file() and FRONTEND_DIST in target.resolve().parents:
            return FileResponse(target)
        return FileResponse(FRONTEND_DIST / "index.html")
