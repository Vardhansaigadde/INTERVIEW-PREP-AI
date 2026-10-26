import json

from app.seed import CONTENT_PATH, validate_content


def test_shipped_content_is_valid():
    assert validate_content(json.loads(CONTENT_PATH.read_text(encoding="utf-8"))) == []


def test_broken_content_is_reported():
    bad = {"subjects": [{"name": "S", "topics": [{"name": "T", "materials": [{"level": "expert"}],
            "questions": [{"options": ["a", "a"], "answer": 5, "difficulty": 9}]}]}]}
    problems = validate_content(bad)
    assert len(problems) == 4


def test_interview_questions_are_well_formed():
    from app.interview import QUESTIONS
    assert len(QUESTIONS) >= 10
    for q in QUESTIONS.values():
        lo, hi = q["ideal_seconds"]
        assert 0 < lo < hi and q["key_points"] and all(kp["keywords"] for kp in q["key_points"])
