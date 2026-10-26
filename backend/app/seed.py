"""Load study content from data/content.json into the database (only the first time)."""
import json
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import Material, Question, Subject, Topic

CONTENT_PATH = Path(__file__).resolve().parents[2] / "data" / "content.json"


def validate_content(data: dict) -> list[str]:
    """Return a list of problems in content.json (empty when it's fine)."""
    problems = []
    for s in data.get("subjects", []):
        for t in s.get("topics", []):
            where = f"{s.get('name')} / {t.get('name')}"
            if {m.get("level") for m in t.get("materials", [])} - {"basic", "advanced"}:
                problems.append(f"{where}: material level must be 'basic' or 'advanced'")
            for i, q in enumerate(t.get("questions", []), 1):
                opts = q.get("options", [])
                if len(opts) < 2:
                    problems.append(f"{where} Q{i}: needs at least 2 options")
                if len(set(opts)) != len(opts):
                    problems.append(f"{where} Q{i}: options must be different from each other")
                if not isinstance(q.get("answer"), int) or not 0 <= q["answer"] < len(opts):
                    problems.append(f"{where} Q{i}: 'answer' must be the index of one of the options")
                if q.get("difficulty", 1) not in (1, 2, 3):
                    problems.append(f"{where} Q{i}: difficulty must be 1, 2 or 3")
    return problems


def seed_content(db: Session, path: Path = CONTENT_PATH) -> int:
    data = json.loads(path.read_text(encoding="utf-8"))
    problems = validate_content(data)
    if problems:
        raise ValueError("data/content.json has problems:\n  " + "\n  ".join(problems))
    added = 0
    for s in data["subjects"]:
        subject = db.scalar(select(Subject).where(Subject.name == s["name"]))
        if subject is None:
            subject = Subject(name=s["name"])
            db.add(subject)
            db.flush()
        for t in s["topics"]:
            if db.scalar(select(Topic).where(Topic.subject_id == subject.id, Topic.name == t["name"])):
                continue
            topic = Topic(subject_id=subject.id, name=t["name"])
            db.add(topic)
            db.flush()
            for m in t.get("materials", []):
                db.add(Material(topic_id=topic.id, title=m["title"], level=m["level"], body=m["body"], url=m.get("url")))
            for q in t.get("questions", []):
                db.add(Question(topic_id=topic.id, text=q["text"], options=q["options"], answer=q["answer"],
                                difficulty=q.get("difficulty", 1), explanation=q.get("explanation", "")))
            added += 1
    db.commit()
    return added
