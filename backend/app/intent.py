"""Voice command intent recognition.

The browser turns speech into text (Web Speech API). This module maps that text to an
intent with a TF-IDF + logistic regression classifier trained on data/intents.json.
To add a command, add example phrases to that file and delete models/intent.joblib.
"""
import json
from pathlib import Path

import joblib
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import FeatureUnion, Pipeline

ROOT = Path(__file__).resolve().parents[2]
DATA_PATH = ROOT / "data" / "intents.json"
MODEL_PATH = ROOT / "models" / "intent.joblib"
MIN_CONFIDENCE = 0.25


def load_examples(path: Path = DATA_PATH):
    data = json.loads(path.read_text(encoding="utf-8"))
    texts, labels = [], []
    for intent, phrases in data.items():
        for p in phrases:
            texts.append(p.lower())
            labels.append(intent)
    return texts, labels


def build_pipeline() -> Pipeline:
    features = FeatureUnion([
        ("words", TfidfVectorizer(ngram_range=(1, 2))),
        ("chars", TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 4))),  # copes with speech-to-text mistakes
    ])
    return Pipeline([("features", features), ("clf", LogisticRegression(max_iter=2000, C=10))])


def train(save: bool = True) -> Pipeline:
    texts, labels = load_examples()
    model = build_pipeline().fit(texts, labels)
    if save:
        MODEL_PATH.parent.mkdir(exist_ok=True)
        joblib.dump(model, MODEL_PATH)
    return model


_model: Pipeline | None = None


def get_model() -> Pipeline:
    global _model
    if _model is None:
        fresh = MODEL_PATH.exists() and MODEL_PATH.stat().st_mtime >= DATA_PATH.stat().st_mtime
        _model = joblib.load(MODEL_PATH) if fresh else train()
    return _model


def predict(text: str) -> tuple[str, float]:
    model = get_model()
    probs = model.predict_proba([text.lower().strip()])[0]
    idx = int(probs.argmax())
    intent, conf = str(model.classes_[idx]), float(probs[idx])
    if conf < MIN_CONFIDENCE:
        return "unknown", conf
    return intent, conf
