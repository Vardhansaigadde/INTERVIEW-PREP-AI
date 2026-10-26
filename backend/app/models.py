from datetime import datetime, timezone

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


def now():
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(256))
    role: Mapped[str] = mapped_column(String(16), default="student")  # student | teacher
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Subject(Base):
    __tablename__ = "subjects"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(128), unique=True)
    topics: Mapped[list["Topic"]] = relationship(back_populates="subject", order_by="Topic.id")


class Topic(Base):
    __tablename__ = "topics"
    id: Mapped[int] = mapped_column(primary_key=True)
    subject_id: Mapped[int] = mapped_column(ForeignKey("subjects.id"))
    name: Mapped[str] = mapped_column(String(128))
    subject: Mapped[Subject] = relationship(back_populates="topics")
    materials: Mapped[list["Material"]] = relationship(order_by="Material.id")
    questions: Mapped[list["Question"]] = relationship(order_by="Question.id")


class Material(Base):
    __tablename__ = "materials"
    id: Mapped[int] = mapped_column(primary_key=True)
    topic_id: Mapped[int] = mapped_column(ForeignKey("topics.id"))
    title: Mapped[str] = mapped_column(String(256))
    level: Mapped[str] = mapped_column(String(16))  # basic | advanced
    body: Mapped[str] = mapped_column(Text)
    url: Mapped[str | None] = mapped_column(String(512), nullable=True)


class Question(Base):
    __tablename__ = "questions"
    id: Mapped[int] = mapped_column(primary_key=True)
    topic_id: Mapped[int] = mapped_column(ForeignKey("topics.id"))
    text: Mapped[str] = mapped_column(Text)
    options: Mapped[list] = mapped_column(JSON)
    answer: Mapped[int] = mapped_column(Integer)
    difficulty: Mapped[int] = mapped_column(Integer, default=1)  # 1 easy .. 3 hard
    explanation: Mapped[str] = mapped_column(Text, default="")


class StudySession(Base):
    __tablename__ = "study_sessions"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Attempt(Base):
    __tablename__ = "attempts"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    question_id: Mapped[int] = mapped_column(ForeignKey("questions.id"))
    topic_id: Mapped[int] = mapped_column(ForeignKey("topics.id"), index=True)
    session_id: Mapped[int | None] = mapped_column(ForeignKey("study_sessions.id"), nullable=True)
    correct: Mapped[bool] = mapped_column(Boolean)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class EmotionLog(Base):
    __tablename__ = "emotion_logs"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    session_id: Mapped[int | None] = mapped_column(ForeignKey("study_sessions.id"), nullable=True)
    topic_id: Mapped[int | None] = mapped_column(ForeignKey("topics.id"), nullable=True)
    emotion: Mapped[str] = mapped_column(String(16))  # raw model label, or "no_face"
    state: Mapped[str] = mapped_column(String(16))  # engaged | confused | frustrated | distracted | neutral
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class InterviewAttempt(Base):
    """One spoken answer to a mock-interview question, with its confidence report."""
    __tablename__ = "interview_attempts"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    question_id: Mapped[str] = mapped_column(String(64))
    question: Mapped[str] = mapped_column(Text)
    category: Mapped[str] = mapped_column(String(32))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    finished: Mapped[bool] = mapped_column(Boolean, default=False)
    duration_sec: Mapped[float | None] = mapped_column(Float, nullable=True)
    transcript: Mapped[str] = mapped_column(Text, default="")
    overall: Mapped[float | None] = mapped_column(Float, nullable=True)
    report: Mapped[dict | None] = mapped_column(JSON, nullable=True)


class InterviewFrame(Base):
    """Body-language measurements from one webcam frame during an answer (no image is stored)."""
    __tablename__ = "interview_frames"
    id: Mapped[int] = mapped_column(primary_key=True)
    attempt_id: Mapped[int] = mapped_column(ForeignKey("interview_attempts.id"), index=True)
    has_face: Mapped[bool] = mapped_column(Boolean)
    yaw: Mapped[float | None] = mapped_column(Float, nullable=True)
    pitch: Mapped[float | None] = mapped_column(Float, nullable=True)
    cx: Mapped[float | None] = mapped_column(Float, nullable=True)
    cy: Mapped[float | None] = mapped_column(Float, nullable=True)
    size: Mapped[float | None] = mapped_column(Float, nullable=True)
    happy: Mapped[float | None] = mapped_column(Float, nullable=True)
    state: Mapped[str] = mapped_column(String(16))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
