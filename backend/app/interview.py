"""Mock interview API: answer a question on camera and get a confidence & body-language report."""
import json
import random
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from . import confidence
from .auth import current_user
from .db import get_db
from .emotion import get_detector
from .models import InterviewAttempt, InterviewFrame, User

QUESTIONS_PATH = Path(__file__).resolve().parents[2] / "data" / "interview_questions.json"
QUESTIONS = {q["id"]: q for q in json.loads(QUESTIONS_PATH.read_text(encoding="utf-8"))["questions"]}

router = APIRouter(prefix="/api/interview", tags=["interview"])


class StartIn(BaseModel):
    question_id: str | None = None
    category: str | None = None


class AudioIn(BaseModel):
    speaking_sec: float | None = Field(default=None, ge=0)
    long_pauses: int | None = Field(default=None, ge=0)
    longest_pause_sec: float | None = Field(default=None, ge=0)


class FinishIn(BaseModel):
    transcript: str = Field(default="", max_length=20000)
    duration_sec: float = Field(gt=0, le=1800)
    audio: AudioIn | None = None


def question_out(q: dict) -> dict:
    return {"id": q["id"], "category": q["category"], "text": q["text"], "tip": q["tip"],
            "ideal_seconds": q["ideal_seconds"], "key_points": [k["label"] for k in q["key_points"]]}


def frame_dict(f: InterviewFrame) -> dict:
    return {"has_face": f.has_face, "yaw": f.yaw, "pitch": f.pitch, "cx": f.cx, "cy": f.cy,
            "size": f.size, "happy": f.happy, "state": f.state}


def own_attempt(db: Session, user: User, attempt_id: int) -> InterviewAttempt:
    a = db.get(InterviewAttempt, attempt_id)
    if a is None or a.user_id != user.id:
        raise HTTPException(404, "Interview attempt not found")
    return a


@router.get("/questions")
def questions(user: User = Depends(current_user)):
    return [question_out(q) for q in QUESTIONS.values()]


@router.post("/attempts")
def start_attempt(body: StartIn, db: Session = Depends(get_db), user: User = Depends(current_user)):
    if body.question_id:
        q = QUESTIONS.get(body.question_id)
        if q is None:
            raise HTTPException(404, "Question not found")
    else:
        pool = [q for q in QUESTIONS.values() if not body.category or q["category"] == body.category]
        if not pool:
            raise HTTPException(404, "No questions in that category")
        q = random.choice(pool)
    a = InterviewAttempt(user_id=user.id, question_id=q["id"], question=q["text"], category=q["category"])
    db.add(a)
    db.commit()
    return {"attempt_id": a.id, "question": question_out(q)}


@router.post("/attempts/{attempt_id}/frame")
async def attempt_frame(attempt_id: int, file: UploadFile = File(...), db: Session = Depends(get_db),
                        user: User = Depends(current_user)):
    a = own_attempt(db, user, attempt_id)
    if a.finished:
        raise HTTPException(409, "This answer is already finished")
    data = await file.read()
    if len(data) > 2_000_000:
        raise HTTPException(413, "Frame too large")
    try:
        r = get_detector().analyze_bytes(data)
    except ValueError as e:
        raise HTTPException(400, str(e))
    has_face = r.face_box is not None
    f = InterviewFrame(attempt_id=a.id, has_face=has_face, yaw=r.yaw, pitch=r.pitch,
                       cx=r.face_center[0] if r.face_center else None, cy=r.face_center[1] if r.face_center else None,
                       size=r.face_size, happy=r.scores.get("happy") if r.scores else None, state=r.state)
    db.add(f)
    db.commit()
    frames = [frame_dict(x) for x in db.scalars(select(InterviewFrame).where(InterviewFrame.attempt_id == a.id)
                                                .order_by(InterviewFrame.id)).all()]
    base = confidence.pitch_baseline(frames)
    ec = confidence.eye_contact(frames)
    return {"has_face": has_face, "facing": confidence.is_facing(frame_dict(f), base), "state": r.state,
            "reason": r.reason, "eye_contact_so_far": None if ec is None else round(ec, 3), "frames": len(frames)}


@router.post("/attempts/{attempt_id}/finish")
def finish_attempt(attempt_id: int, body: FinishIn, db: Session = Depends(get_db), user: User = Depends(current_user)):
    a = own_attempt(db, user, attempt_id)
    if a.finished:
        return attempt_out(a)
    q = QUESTIONS.get(a.question_id, {})
    frames = [frame_dict(x) for x in db.scalars(select(InterviewFrame).where(InterviewFrame.attempt_id == a.id)
                                                .order_by(InterviewFrame.id)).all()]
    report = confidence.build_report(frames, body.transcript, body.duration_sec,
                                     body.audio.model_dump() if body.audio else None,
                                     q.get("key_points"), tuple(q.get("ideal_seconds", (45, 120))))
    a.finished = True
    a.duration_sec = body.duration_sec
    a.transcript = body.transcript
    a.overall = report["overall"]
    a.report = report
    db.commit()
    return attempt_out(a)


def attempt_out(a: InterviewAttempt, full: bool = True) -> dict:
    out = {"id": a.id, "question_id": a.question_id, "question": a.question, "category": a.category,
           "started_at": a.started_at.isoformat(), "duration_sec": a.duration_sec, "overall": a.overall}
    if full:
        out["transcript"] = a.transcript
        out["report"] = a.report
    elif a.report:
        out["metrics"] = {m["key"]: m["score"] for m in a.report["metrics"]}
    return out


@router.get("/attempts")
def history(db: Session = Depends(get_db), user: User = Depends(current_user)):
    rows = db.scalars(select(InterviewAttempt).where(InterviewAttempt.user_id == user.id, InterviewAttempt.finished)
                      .order_by(InterviewAttempt.id.desc()).limit(30)).all()
    return [attempt_out(a, full=False) for a in rows]


@router.get("/attempts/{attempt_id}")
def get_attempt(attempt_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    return attempt_out(own_attempt(db, user, attempt_id))
