"""Measure model accuracy so you can put real numbers in your report.

    python scripts/evaluate_models.py                        # voice intent model (always works)
    python scripts/evaluate_models.py --fer data/fer2013     # also the emotion model + learning states on FER2013 test
"""
import argparse
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

import cv2  # noqa: E402
import numpy as np  # noqa: E402
from sklearn.metrics import classification_report  # noqa: E402
from sklearn.model_selection import StratifiedKFold, cross_val_predict  # noqa: E402

from app import intent  # noqa: E402
from app.emotion import EmotionDetector, classify_state, group_scores  # noqa: E402

# FER+ has 8 classes and FER2013 has 7; "contempt" has no FER2013 folder
TRUE_STATE = {"happy": "engaged", "surprise": "engaged", "neutral": "neutral", "sad": "confused",
              "fear": "confused", "angry": "frustrated", "disgust": "frustrated"}
FER_FOLDER_TO_LABEL = {"angry": "angry", "disgust": "disgust", "fear": "fear", "happy": "happy",
                       "sad": "sad", "surprise": "surprise", "neutral": "neutral"}


def eval_intents():
    texts, labels = intent.load_examples()
    cv = StratifiedKFold(n_splits=5, shuffle=True, random_state=0)
    pred = cross_val_predict(intent.build_pipeline(), texts, labels, cv=cv)
    print("=== Voice intent classifier (5-fold cross-validation) ===")
    print(classification_report(labels, pred, zero_division=0))


def eval_emotion(root: Path, limit: int):
    det = EmotionDetector()
    y_true, y_pred, s_true, s_pred = [], [], [], []
    for folder in sorted((root / "test").iterdir()):
        files = sorted(folder.glob("*.jpg"))[:limit]
        for f in files:
            gray = cv2.imread(str(f), cv2.IMREAD_GRAYSCALE)
            # FER2013 images are already cropped 48x48 faces, so classify them directly
            probs = det.predict_face(gray)
            y_true.append(FER_FOLDER_TO_LABEL[folder.name])
            y_pred.append(det.labels[int(np.argmax(probs))])
            s_true.append(TRUE_STATE[folder.name])
            s_pred.append(classify_state(group_scores(dict(zip(det.labels, map(float, probs))))))
    print("=== Emotion CNN on FER2013 test set ===")
    print(classification_report(y_true, y_pred, zero_division=0))
    acc = np.mean(np.array(y_true) == np.array(y_pred))
    print(f"accuracy: {acc:.3f} on {len(y_true)} images; predicted label counts: {Counter(y_pred)}")
    print("=== Learning state detection (what the app actually uses) ===")
    print(classification_report(s_true, s_pred, zero_division=0))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--fer", type=Path, help="path to the FER2013 folder (with test/<emotion>/ subfolders)")
    ap.add_argument("--limit", type=int, default=500, help="max images per class")
    args = ap.parse_args()
    eval_intents()
    if args.fer:
        eval_emotion(args.fer, args.limit)
