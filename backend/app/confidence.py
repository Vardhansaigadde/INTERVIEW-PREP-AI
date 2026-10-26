"""Confidence & body-language report for a spoken mock-interview answer.

Inputs collected while the student answers:
  * webcam frames -> face found?, head yaw/pitch, face position, smile probability, learning state
  * browser speech-to-text -> transcript (for pace, filler words and key-point coverage)
  * browser microphone level -> speaking time, long pauses

Everything here is rule-based and explainable, so each score in the report can be traced
back to a measurement. "Eye contact" means *facing the camera* (head pose), not true gaze.
"""
import re
import statistics

# ---- tunable limits -------------------------------------------------------
FACING_MAX_YAW = 0.25  # sideways turn still counted as facing the camera (about 20 degrees)
FACING_MAX_PITCH_DELTA = 0.10  # up/down change from the student's own baseline
DEFAULT_PITCH = 0.55  # typical frontal value (measured on FER2013 faces: 0.49-0.62)
SMILE_PROB = 0.30
IDEAL_WPM = (120, 160)
LONG_PAUSE_SEC = 2.5

FILLER_WORDS = {"um", "umm", "uh", "uhh", "uhm", "er", "erm", "ah", "hmm", "mm"}
FILLER_PHRASES = ["you know", "i mean", "kind of", "sort of", "basically", "actually", "literally", "like i said"]

WEIGHTS = {"eye_contact": 0.20, "pace": 0.12, "fillers": 0.15, "content": 0.15, "length": 0.12,
           "pauses": 0.10, "stability": 0.08, "composure": 0.08}


def _lerp_score(value, bad, good):
    """Linear 0-100 score: `bad` maps to 0, `good` to 100 (works in either direction), clamped."""
    if good == bad:
        return 100.0
    t = (value - bad) / (good - bad)
    return round(max(0.0, min(1.0, t)) * 100, 1)


def _status(score):
    if score is None:
        return "na"
    return "good" if score >= 75 else "ok" if score >= 50 else "work"


# ---- individual measurements ----------------------------------------------
def pitch_baseline(frames: list[dict]) -> float:
    first = [f["pitch"] for f in frames if f.get("has_face") and f.get("pitch") is not None][:3]
    if not first:
        return DEFAULT_PITCH
    return min(max(statistics.median(first), 0.48), 0.64)


def is_facing(frame: dict, base_pitch: float) -> bool:
    if not frame.get("has_face") or frame.get("yaw") is None:
        return False
    if abs(frame["yaw"]) > FACING_MAX_YAW:
        return False
    p = frame.get("pitch")
    return p is None or abs(p - base_pitch) <= FACING_MAX_PITCH_DELTA


def eye_contact(frames: list[dict]) -> float | None:
    if not frames:
        return None
    base = pitch_baseline(frames)
    return sum(is_facing(f, base) for f in frames) / len(frames)


def head_movement(frames: list[dict]) -> float | None:
    """Average jump of the face centre between frames, measured in face widths."""
    pts = [f for f in frames if f.get("has_face") and f.get("cx") is not None and f.get("size")]
    if len(pts) < 3:
        return None
    moves = []
    for a, b in zip(pts, pts[1:]):
        d = ((a["cx"] - b["cx"]) ** 2 + (a["cy"] - b["cy"]) ** 2) ** 0.5
        moves.append(d / max((a["size"] + b["size"]) / 2, 1e-6))
    return statistics.mean(moves)


def find_fillers(transcript: str) -> list[str]:
    text = " " + re.sub(r"[^a-z' ]+", " ", transcript.lower()) + " "
    found = [w for w in text.split() if w in FILLER_WORDS]
    for ph in FILLER_PHRASES:
        found += [ph] * len(re.findall(rf"(?<= ){re.escape(ph)}(?= )", text))
    return found


def word_count(transcript: str) -> int:
    return len(re.findall(r"[A-Za-z0-9']+", transcript))


def key_point_coverage(transcript: str, key_points: list[dict]) -> list[dict]:
    text = transcript.lower()
    return [{"label": kp["label"], "covered": any(k.lower() in text for k in kp["keywords"])} for kp in key_points]


# ---- the report -------------------------------------------------------------
def build_report(frames: list[dict], transcript: str, duration_sec: float, audio: dict | None,
                 key_points: list[dict] | None = None, ideal_seconds: tuple[int, int] = (45, 120)) -> dict:
    audio = audio or {}
    metrics = []

    def add(key, label, value, display, score, ideal, tip_good, tip_work):
        metrics.append({"key": key, "label": label, "value": value, "display": display, "score": score,
                        "status": _status(score), "ideal": ideal,
                        "tip": None if score is None else (tip_good if score >= 75 else tip_work)})

    # Eye contact (facing the camera)
    ec = eye_contact(frames)
    add("eye_contact", "Eye contact", ec, "—" if ec is None else f"{round(ec * 100)}%",
        None if ec is None else _lerp_score(ec, 0.3, 0.8), "80% or more",
        "Great eye contact. You kept facing the interviewer.",
        "Look at the camera lens more often. It reads as eye contact to the interviewer.")

    # Head stability
    mv = head_movement(frames)
    add("stability", "Head stability", mv, "—" if mv is None else ("Steady" if mv < 0.08 else "Some movement" if mv < 0.2 else "Restless"),
        None if mv is None else _lerp_score(mv, 0.35, 0.05), "Calm, steady posture",
        "Steady posture. You looked composed.",
        "Try to keep your head and shoulders still. Frequent movement can look nervous.")

    # Composure (no confused/frustrated expressions)
    faced = [f for f in frames if f.get("has_face")]
    calm = (sum(f.get("state") not in ("confused", "frustrated") for f in faced) / len(faced)) if faced else None
    add("composure", "Composure", calm, "—" if calm is None else f"{round(calm * 100)}% calm",
        None if calm is None else _lerp_score(calm, 0.4, 0.9), "Calm for most of the answer",
        "You looked relaxed and in control.",
        "You looked tense at times. Pause, breathe, and slow down when a question feels hard.")

    # Smile / warmth (informational, not scored)
    smile = (sum((f.get("happy") or 0) >= SMILE_PROB for f in faced) / len(faced)) if faced else None

    # Pace
    words = word_count(transcript)
    speaking_sec = audio.get("speaking_sec") or duration_sec
    wpm = words / (duration_sec / 60) if duration_sec > 0 and words >= 10 else None
    if wpm is None:
        pace_score = None
    elif IDEAL_WPM[0] <= wpm <= IDEAL_WPM[1]:
        pace_score = 100.0
    elif wpm < IDEAL_WPM[0]:
        pace_score = _lerp_score(wpm, 70, IDEAL_WPM[0])
    else:
        pace_score = _lerp_score(wpm, 220, IDEAL_WPM[1])
    add("pace", "Speaking pace", wpm, "—" if wpm is None else f"{round(wpm)} wpm", pace_score, "120-160 words/min",
        "Good, clear pace.",
        "You spoke a bit slowly. Try to keep your answer flowing." if wpm is not None and wpm < IDEAL_WPM[0]
        else "You spoke fast. Slow down and pause between your main points.")

    # Filler words
    fillers = find_fillers(transcript)
    filler_rate = len(fillers) / words * 100 if words >= 10 else None
    add("fillers", "Filler words", len(fillers) if words >= 10 else None,
        "—" if filler_rate is None else f"{len(fillers)} ({filler_rate:.1f} per 100 words)",
        None if filler_rate is None else _lerp_score(filler_rate, 8, 1), "Under 1 per 100 words",
        "Very few filler words. Sounds confident.",
        "Replace 'um', 'basically' and 'you know' with a short silent pause.")

    # Long pauses (from the microphone level)
    long_pauses = audio.get("long_pauses")
    per_min = long_pauses / (duration_sec / 60) if long_pauses is not None and duration_sec >= 10 else None
    add("pauses", "Long pauses", long_pauses, "—" if per_min is None else f"{long_pauses} (over {LONG_PAUSE_SEC:g}s)",
        None if per_min is None else _lerp_score(per_min, 5, 1), "At most 1 per minute",
        "Smooth delivery with few long silences.",
        "Several long silences. Plan your answer as 2-3 points before you start speaking.")

    # Content: key points covered
    coverage = key_point_coverage(transcript, key_points or []) if key_points else []
    covered = sum(c["covered"] for c in coverage)
    content_score = round(covered / len(coverage) * 100, 1) if coverage and words >= 10 else None
    add("content", "Key points covered", covered if coverage else None,
        "—" if content_score is None else f"{covered} of {len(coverage)}", content_score, "All key points",
        "You covered the important points.",
        "Some key points were missing. See the checklist below.")

    # Answer length compared with what the question needs
    lo, hi = ideal_seconds
    if words < 10:
        length_score = None
    elif lo <= duration_sec <= hi:
        length_score = 100.0
    elif duration_sec < lo:
        length_score = _lerp_score(duration_sec, lo * 0.25, lo)
    else:
        length_score = _lerp_score(duration_sec, hi * 2, hi)
    add("length", "Answer length", duration_sec, f"{round(duration_sec)}s", length_score, f"{lo}-{hi} seconds",
        "Good length: complete but to the point.",
        f"Too short. Aim for {lo}-{hi} seconds and add a concrete example." if duration_sec < lo
        else f"Too long. Aim for {lo}-{hi} seconds and get to the point sooner.")

    # Overall score: weighted average of whatever could be measured
    scored = [(WEIGHTS[m["key"]], m["score"]) for m in metrics if m["score"] is not None]
    overall = round(sum(w * s for w, s in scored) / sum(w for w, _ in scored)) if scored else None

    # weakest first; on a tie, the metric that matters more to the overall score comes first
    ranked = sorted([m for m in metrics if m["score"] is not None], key=lambda m: (m["score"], -WEIGHTS[m["key"]]))
    strengths = [m["tip"] for m in reversed(ranked) if m["status"] == "good"][:3]
    improvements = [m["tip"] for m in ranked if m["status"] != "good"][:4]
    if smile is not None and smile < 0.05 and len(faced) >= 5:
        improvements.append("Smile now and then, especially when you introduce yourself. It makes you seem warmer.")

    return {
        "overall": overall,
        "metrics": metrics,
        "strengths": strengths,
        "improvements": improvements[:4],
        "smile_pct": None if smile is None else round(smile, 3),
        "duration_sec": round(duration_sec, 1),
        "speaking_sec": round(speaking_sec, 1) if speaking_sec else None,
        "word_count": words,
        "fillers": fillers,
        "coverage": coverage,
        "frames_analyzed": len(frames),
    }
