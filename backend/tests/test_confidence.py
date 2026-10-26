from app import confidence as c


def frame(has_face=True, yaw=0.0, pitch=0.55, cx=0.5, cy=0.5, size=0.3, happy=0.0, state="neutral"):
    return {"has_face": has_face, "yaw": yaw, "pitch": pitch, "cx": cx, "cy": cy, "size": size, "happy": happy, "state": state}


GOOD_ANSWER = ("I am a final year computer science student. Last summer I did an internship where I built "
               "a dashboard in React and Python. I am good at problem solving and I learn quickly. "
               "I am looking for a role where I can grow as a backend developer, and this company's work "
               "on data products really excites me. ") * 2


def test_facing_camera_counts_as_eye_contact():
    frames = [frame() for _ in range(8)] + [frame(yaw=0.45), frame(has_face=False)]
    assert c.eye_contact(frames) == 0.8


def test_looking_down_breaks_eye_contact():
    frames = [frame(pitch=0.55)] * 3 + [frame(pitch=0.75)] * 7  # baseline from first frames, then head down
    assert c.eye_contact(frames) == 0.3


def test_head_movement():
    still = [frame(cx=0.5 + 0.002 * (i % 2)) for i in range(10)]
    restless = [frame(cx=0.3 if i % 2 else 0.6) for i in range(10)]
    assert c.head_movement(still) < 0.05
    assert c.head_movement(restless) > 0.5


def test_fillers_found():
    t = "Um so basically I think, uh, you know, the answer is like a hash map. I mean it's actually fast"
    f = c.find_fillers(t)
    assert sorted(f) == sorted(["um", "uh", "basically", "you know", "i mean", "actually"])


def test_no_filler_false_positives():
    assert c.find_fillers("I mean to say the umbrella was actually useful") == ["i mean", "actually"]
    assert c.find_fillers("The human error rate") == []


def test_key_points():
    q_kp = [{"label": "Stack", "keywords": ["react", "python"]}, {"label": "Result", "keywords": ["reduced", "improved"]}]
    cov = c.key_point_coverage(GOOD_ANSWER, q_kp)
    assert cov == [{"label": "Stack", "covered": True}, {"label": "Result", "covered": False}]


def test_strong_answer_scores_high():
    frames = [frame(cx=0.5 + 0.003 * (i % 2), happy=0.4 if i < 3 else 0.05) for i in range(30)]
    kp = [{"label": "Role", "keywords": ["student"]}, {"label": "Goal", "keywords": ["looking for"]}]
    words = c.word_count(GOOD_ANSWER)
    r = c.build_report(frames, GOOD_ANSWER, duration_sec=words / 140 * 60, audio={"long_pauses": 0, "speaking_sec": 40},
                       key_points=kp, ideal_seconds=(30, 120))
    assert words / 140 * 60 >= 30  # the sample answer is long enough for this question
    assert r["overall"] >= 85
    by = {m["key"]: m for m in r["metrics"]}
    assert by["eye_contact"]["status"] == "good" and by["pace"]["status"] == "good"
    assert by["fillers"]["value"] == 0 and by["content"]["display"] == "2 of 2"


def test_nervous_answer_gets_tips():
    frames = [frame(yaw=0.5 if i % 2 else 0.0, cx=0.3 if i % 2 else 0.6, state="confused") for i in range(20)]
    t = "um so uh basically I uh think um it is you know like um a thing that uh works " * 3
    r = c.build_report(frames, t, duration_sec=20, audio={"long_pauses": 5}, key_points=None, ideal_seconds=(60, 120))
    assert r["overall"] < 50
    by = {m["key"]: m for m in r["metrics"]}
    assert by["eye_contact"]["status"] == "work" and by["fillers"]["status"] == "work"
    assert by["length"]["status"] == "work" and "Too short" in by["length"]["tip"]
    assert len(r["improvements"]) == 4 and r["improvements"][0].startswith("Replace 'um'")  # worst + most important first


def test_no_speech_or_camera_is_handled():
    r = c.build_report([], "", duration_sec=5, audio=None)
    assert r["overall"] is None
    assert all(m["score"] is None for m in r["metrics"])
