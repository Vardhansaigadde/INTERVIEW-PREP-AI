import os
import tempfile
from pathlib import Path

os.environ["DATABASE_URL"] = f"sqlite:///{Path(tempfile.mkdtemp()) / 'test.db'}"

import cv2  # noqa: E402
import numpy as np  # noqa: E402
import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app import recommender  # noqa: E402
from app.intent import predict  # noqa: E402
from app.main import app  # noqa: E402

FACE = Path(__file__).parent / "fixtures" / "face.jpg"


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def auth(client, username="alice", role="student"):
    body = {"username": username, "password": "secret123", "role": role}
    if role == "teacher":
        body["teacher_code"] = "TEACH-2026"
    r = client.post("/api/auth/register", json=body)
    if r.status_code == 409:
        r = client.post("/api/auth/login", json={"username": username, "password": "secret123"})
    return {"Authorization": f"Bearer {r.json()['token']}"}


def test_requires_login(client):
    assert client.get("/api/subjects").status_code == 401


def test_wrong_password(client):
    auth(client)
    assert client.post("/api/auth/login", json={"username": "alice", "password": "wrongpass"}).status_code == 401


def test_content_seeded(client):
    subjects = client.get("/api/subjects", headers=auth(client)).json()
    assert {s["name"] for s in subjects} == {"Data Structures & Algorithms", "CS Fundamentals", "Aptitude", "HR & Behavioural"}
    assert sum(len(s["topics"]) for s in subjects) == 12


def test_quiz_flow_updates_mastery(client):
    h = auth(client, "bob")
    sid = client.post("/api/sessions", headers=h).json()["session_id"]
    for _ in range(3):
        q = client.get("/api/topics/1/question", headers=h).json()
        assert "answer" not in q
        r = client.post("/api/answer", headers=h, json={"question_id": q["id"], "selected": "definitely wrong", "session_id": sid}).json()
        assert r["correct"] is False
        r = client.post("/api/answer", headers=h, json={"question_id": q["id"], "selected": r["correct_option"], "session_id": sid}).json()
        assert r["correct"] is True
    topics = client.get("/api/progress", headers=h).json()["topics"]
    t1 = next(t for t in topics if t["topic_id"] == 1)
    assert t1["attempts"] == 6
    summary = client.post(f"/api/sessions/{sid}/end", headers=h).json()
    assert summary["questions"] == 6 and summary["correct"] == 3


def test_emotion_frame(client):
    h = auth(client)
    sid = client.post("/api/sessions", headers=h).json()["session_id"]
    for _ in range(4):
        r = client.post("/api/emotion/frame", headers=h, data={"session_id": sid, "topic_id": 2},
                        files={"file": ("f.jpg", FACE.read_bytes(), "image/jpeg")})
        assert r.status_code == 200
    body = r.json()
    assert body["emotion"] != "no_face" and body["face_box"]
    assert client.post("/api/emotion/frame", headers=h, files={"file": ("x.jpg", b"notanimage", "image/jpeg")}).status_code == 400


def test_away_from_camera_suggests_break(client):
    h = auth(client, "away_user")
    sid = client.post("/api/sessions", headers=h).json()["session_id"]
    blank = cv2.imencode(".jpg", np.full((240, 320, 3), 90, np.uint8))[1].tobytes()
    for _ in range(4):
        r = client.post("/api/emotion/frame", headers=h, data={"session_id": sid},
                        files={"file": ("f.jpg", blank, "image/jpeg")}).json()
    assert r["state"] == "distracted" and r["reason"] == "no face in view"
    assert r["feedback"]["type"] == "break"


def test_cannot_use_other_users_session(client):
    sid = client.post("/api/sessions", headers=auth(client, "carol")).json()["session_id"]
    r = client.post("/api/emotion/frame", headers=auth(client, "dave"), data={"session_id": sid},
                    files={"file": ("f.jpg", FACE.read_bytes(), "image/jpeg")})
    assert r.status_code == 404


def test_voice_commands(client):
    h = auth(client)
    r = client.post("/api/voice/command", headers=h, json={"text": "quiz me", "topic_id": 3}).json()
    assert r["intent"] == "quiz" and r["question"]["topic_id"] == 3
    r = client.post("/api/voice/command", headers=h, json={"text": "I don't understand this", "topic_id": 3}).json()
    assert r["intent"] == "explain" and r["material"]["level"] == "basic"
    r = client.post("/api/voice/command", headers=h, json={"text": "what should I study next"}).json()
    assert r["intent"] == "recommend" and "topic_id" in r


def test_recommendations_prioritise_weak_topic(client):
    h = auth(client, "erin")
    q = client.get("/api/topics/5/question", headers=h).json()
    for _ in range(4):
        client.post("/api/answer", headers=h, json={"question_id": q["id"], "selected": "nope"})
    plan = client.get("/api/recommendations", headers=h).json()
    assert plan[0]["topic_id"] == 5 and plan[0]["level"] == "basic"


def test_teacher_view(client):
    assert client.get("/api/teacher/students", headers=auth(client)).status_code == 403
    students = client.get("/api/teacher/students", headers=auth(client, "teach", "teacher")).json()
    assert any(s["username"] == "erin" and "Object-Oriented Programming" in s["weak_topics"] for s in students)


def test_live_feedback_rules():
    assert recommender.live_feedback(["engaged"]) is None
    assert recommender.live_feedback(["distracted"] * 4)["type"] == "break"
    assert recommender.live_feedback(["frustrated"] * 4)["type"] == "easier"
    assert recommender.live_feedback(["confused", "confused", "neutral", "engaged"])["type"] == "explain"
    assert recommender.live_feedback(["engaged"] * 5)["type"] == "harder"


@pytest.mark.parametrize("text,expected", [
    ("explain this topic again", "explain"), ("give me a hint please", "hint"),
    ("skip this one", "next"), ("I need a break", "break"), ("show my progress", "progress"),
])
def test_intents(text, expected):
    assert predict(text)[0] == expected


def test_mock_interview_flow(client):
    h = auth(client, "interviewee")
    qs = client.get("/api/interview/questions", headers=h).json()
    assert len(qs) >= 10 and {"HR", "Behavioural", "Technical"} <= {q["category"] for q in qs}
    start = client.post("/api/interview/attempts", headers=h, json={"question_id": "hr-about-yourself"}).json()
    aid = start["attempt_id"]
    assert start["question"]["text"] == "Tell me about yourself."
    for _ in range(3):
        r = client.post(f"/api/interview/attempts/{aid}/frame", headers=h,
                        files={"file": ("f.jpg", FACE.read_bytes(), "image/jpeg")}).json()
        assert r["has_face"] is True
    blank = cv2.imencode(".jpg", np.full((240, 320, 3), 90, np.uint8))[1].tobytes()
    r = client.post(f"/api/interview/attempts/{aid}/frame", headers=h, files={"file": ("f.jpg", blank, "image/jpeg")}).json()
    assert r["has_face"] is False and r["eye_contact_so_far"] <= 0.75
    transcript = ("I am a final year student. I built a project in Python during my internship and I am looking "
                  "for a role where I can grow. Um, my key skill is problem solving.")
    rep = client.post(f"/api/interview/attempts/{aid}/finish", headers=h,
                      json={"transcript": transcript, "duration_sec": 15, "audio": {"long_pauses": 1, "speaking_sec": 12}}).json()
    assert rep["overall"] is not None and rep["report"]["fillers"] == ["um"]
    assert rep["report"]["frames_analyzed"] == 4
    assert any(cv["covered"] for cv in rep["report"]["coverage"])
    hist = client.get("/api/interview/attempts", headers=h).json()
    assert hist[0]["id"] == aid and "eye_contact" in hist[0]["metrics"]
    # another user can't read or add to this attempt
    other = auth(client, "snooper")
    assert client.get(f"/api/interview/attempts/{aid}", headers=other).status_code == 404
    assert client.post(f"/api/interview/attempts/{aid}/frame", headers=other,
                       files={"file": ("f.jpg", blank, "image/jpeg")}).status_code == 404


def test_teacher_signup_needs_code(client):
    r = client.post("/api/auth/register", json={"username": "fake_teacher", "password": "secret123", "role": "teacher"})
    assert r.status_code == 403
    r = client.post("/api/auth/register", json={"username": "fake_teacher", "password": "secret123", "role": "teacher",
                                                "teacher_code": "wrong"})
    assert r.status_code == 403


def test_empty_or_broken_frames_are_rejected_cleanly(client):
    h = auth(client)
    for data in (b"", b"not an image"):
        assert client.post("/api/emotion/frame", headers=h, files={"file": ("f.jpg", data, "image/jpeg")}).status_code == 400
    aid = client.post("/api/interview/attempts", headers=h, json={}).json()["attempt_id"]
    assert client.post(f"/api/interview/attempts/{aid}/frame", headers=h,
                       files={"file": ("f.jpg", b"", "image/jpeg")}).status_code == 400


def test_unknown_topic_id_in_frame_is_ignored(client):
    h = auth(client)
    r = client.post("/api/emotion/frame", headers=h, data={"topic_id": 99999},
                    files={"file": ("f.jpg", FACE.read_bytes(), "image/jpeg")})
    assert r.status_code == 200


def test_unknown_api_path_is_404_not_html(client):
    r = client.get("/api/does-not-exist")
    assert r.status_code == 404 and r.headers["content-type"].startswith("application/json")


def test_hint_never_repeats_or_reveals_answer(client):
    h = auth(client)
    q = client.get("/api/topics/1/question", headers=h).json()
    crossed = []
    for _ in range(4):
        r = client.post("/api/voice/command", headers=h,
                        json={"text": "give me a hint", "question_id": q["id"], "eliminated": crossed}).json()
        if "eliminate" in r:
            assert r["eliminate"] not in crossed
            crossed.append(r["eliminate"])
    assert len(crossed) == len(q["options"]) - 2  # one wrong option always stays
    ans = client.post("/api/answer", headers=h, json={"question_id": q["id"], "selected": "x"}).json()["correct_option"]
    assert ans not in crossed
