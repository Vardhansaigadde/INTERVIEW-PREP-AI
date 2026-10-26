"""Facial expression analysis: OpenCV YuNet face detection + CNN emotion classifier (ONNX).

The default model is FER+ (emotion-ferplus-8.onnx from the ONNX model zoo). This is a
CNN trained on the FER2013 images with crowd-sourced relabelling. If you train your
own CNN with scripts/train_emotion_cnn.py, set EMOTION_MODEL to the exported .onnx file.

How a webcam frame becomes a learning state:
  1. YuNet finds the face and 5 landmarks (eyes, nose, mouth corners).
  2. If no face is found, or the head is turned well to the side, the state is "distracted" (away).
  3. The CNN gives a probability for each of the 8 emotions.
  4. The probabilities are added up into groups (confused = sad + fear + contempt, and so on),
     and each group is compared with a threshold. We do NOT just take the top emotion, because
     "neutral" wins almost every time on a mildly confused or annoyed face (see
     scripts/evaluate_models.py --states). The thresholds were tuned on FER2013 test images.
  5. Optionally, a per-person baseline (the student's resting face, measured in the first few
     seconds of a session) is subtracted, so a face that naturally looks a bit "sad" to the model
     is not reported as confused all the time.
"""
import os
from dataclasses import dataclass, field
from pathlib import Path

import cv2
import numpy as np
import onnxruntime as ort

ROOT = Path(__file__).resolve().parents[2]
MODEL_PATH = Path(os.getenv("EMOTION_MODEL", ROOT / "models" / "emotion-ferplus-8.onnx"))
FACE_MODEL_PATH = ROOT / "models" / "face_detection_yunet_2023mar.onnx"

FERPLUS_LABELS = ["neutral", "happy", "surprise", "sad", "angry", "disgust", "fear", "contempt"]
FER2013_LABELS = ["angry", "disgust", "fear", "happy", "sad", "surprise", "neutral"]

# Emotions that add up to each learning state
STATE_GROUPS = {
    "engaged": ("happy", "surprise"),
    "confused": ("sad", "fear", "contempt"),
    "frustrated": ("angry", "disgust"),
}
# A state is reported when its group probability reaches this value. Tuned on FER2013 test images
# while keeping at least 75% of calm faces labelled neutral.
STATE_THRESHOLDS = {"engaged": 0.50, "confused": 0.175, "frustrated": 0.10}
# Average group probability on a calm (neutral) face. Used to judge how far a person's resting face is from typical.
NEUTRAL_FACE_MEAN = {"engaged": 0.08, "confused": 0.09, "frustrated": 0.02}

# Head turned further than this (nose offset from the eye midpoint, as a fraction of the eye distance)
# means the student is looking away from the screen. Roughly 30-35 degrees.
MAX_YAW = 0.4
FACE_MARGIN = 0.10  # widen the face box a little so the crop looks like the FER training images


@dataclass
class EmotionResult:
    emotion: str
    state: str
    confidence: float
    scores: dict
    face_box: list | None
    groups: dict = field(default_factory=dict)
    yaw: float | None = None
    reason: str = ""  # why the state was chosen, e.g. "no face", "looking away"
    pitch: float | None = None  # nose height between eyes and mouth: about 0.55 facing the camera
    face_center: list | None = None  # face centre as a fraction of the frame width/height
    face_size: float | None = None  # face width as a fraction of the frame width


def group_scores(scores: dict) -> dict:
    return {state: sum(scores.get(e, 0.0) for e in emos) for state, emos in STATE_GROUPS.items()}


def classify_state(groups: dict, baseline: dict | None = None) -> str:
    """Turn grouped probabilities into a learning state, optionally relative to the person's resting face."""
    adj = dict(groups)
    if baseline:
        for k in adj:
            adj[k] = max(0.0, adj[k] - max(0.0, baseline.get(k, 0.0) - NEUTRAL_FACE_MEAN[k]))
    if adj["frustrated"] >= STATE_THRESHOLDS["frustrated"] and adj["frustrated"] >= adj["confused"]:
        return "frustrated"
    if adj["confused"] >= STATE_THRESHOLDS["confused"]:
        return "confused"
    if adj["engaged"] >= STATE_THRESHOLDS["engaged"]:
        return "engaged"
    return "neutral"


def estimate_yaw(face_row: np.ndarray) -> float | None:
    """Sideways head turn from YuNet landmarks: 0 when facing the camera, around +/-0.5 at about 35-40 degrees."""
    re = face_row[4:6]
    le = face_row[6:8]
    nose = face_row[8:10]
    eye_dist = float(np.linalg.norm(le - re))
    if eye_dist < 1:
        return None
    return float((nose[0] - (re[0] + le[0]) / 2) / eye_dist)


def estimate_pitch(face_row: np.ndarray) -> float | None:
    """Up/down head tilt from YuNet landmarks: about 0.55 when facing the camera (0.49-0.62 on frontal
    FER2013 faces), higher when looking down, lower when looking up."""
    eye_y = (face_row[5] + face_row[7]) / 2
    mouth_y = (face_row[11] + face_row[13]) / 2
    span = float(mouth_y - eye_y)
    if span < 1:
        return None
    return float((face_row[9] - eye_y) / span)


class EmotionDetector:
    def __init__(self, model_path: Path = MODEL_PATH):
        self.session = ort.InferenceSession(str(model_path), providers=["CPUExecutionProvider"])
        inp = self.session.get_inputs()[0]
        self.input_name = inp.name
        self.size = int(inp.shape[-1])
        n_out = self.session.get_outputs()[0].shape[-1]
        # FER+ was trained on raw 0-255 pixels; our own trained model uses 0-1 values
        self.labels = FERPLUS_LABELS if n_out == 8 else FER2013_LABELS
        self.scale = 1.0 if n_out == 8 else 1 / 255.0
        # YuNet: a small CNN face detector that comes with OpenCV (opencv_zoo)
        self.face_detector = cv2.FaceDetectorYN.create(str(FACE_MODEL_PATH), "", (320, 320), 0.7)

    def detect_face(self, image_bgr: np.ndarray) -> np.ndarray | None:
        """Return the YuNet row (box, 5 landmarks, score) of the largest face, or None."""
        h, w = image_bgr.shape[:2]
        self.face_detector.setInputSize((w, h))
        _, faces = self.face_detector.detect(image_bgr)
        if faces is None or len(faces) == 0:
            return None
        face = max(faces, key=lambda f: f[2] * f[3])
        return face if face[2] > 20 and face[3] > 20 else None

    @staticmethod
    def square_crop(gray: np.ndarray, box) -> tuple[np.ndarray, list]:
        """Square crop around the face box with a small margin (FER images are square, so don't stretch)."""
        x, y, w, h = box
        cx, cy = x + w / 2, y + h / 2
        side = max(w, h) * (1 + FACE_MARGIN)
        H, W = gray.shape[:2]
        x0, y0 = int(max(cx - side / 2, 0)), int(max(cy - side / 2, 0))
        x1, y1 = int(min(cx + side / 2, W)), int(min(cy + side / 2, H))
        return gray[y0:y1, x0:x1], [x0, y0, x1 - x0, y1 - y0]

    def predict_face(self, face_gray: np.ndarray) -> np.ndarray:
        face = cv2.resize(face_gray, (self.size, self.size)).astype(np.float32) * self.scale
        logits = self.session.run(None, {self.input_name: face[None, None, :, :]})[0][0]
        exp = np.exp(logits - logits.max())
        return exp / exp.sum()

    def analyze(self, image_bgr: np.ndarray, baseline: dict | None = None) -> EmotionResult:
        if image_bgr.ndim == 2:
            image_bgr = cv2.cvtColor(image_bgr, cv2.COLOR_GRAY2BGR)
        elif image_bgr.shape[2] == 4:
            image_bgr = cv2.cvtColor(image_bgr, cv2.COLOR_BGRA2BGR)
        face = self.detect_face(image_bgr)
        if face is None:
            return EmotionResult("no_face", "distracted", 1.0, {}, None, reason="no face in view")
        gray = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY)
        crop, box = self.square_crop(gray, face[:4])
        probs = self.predict_face(crop)
        idx = int(np.argmax(probs))
        scores = {label: round(float(p), 4) for label, p in zip(self.labels, probs)}
        groups = group_scores(scores)
        yaw = estimate_yaw(face)
        H, W = gray.shape[:2]
        pose = {
            "pitch": estimate_pitch(face),
            "face_center": [float((face[0] + face[2] / 2) / W), float((face[1] + face[3] / 2) / H)],
            "face_size": float(face[2] / W),
        }
        if yaw is not None and abs(yaw) > MAX_YAW:
            return EmotionResult(self.labels[idx], "distracted", float(probs[idx]), scores, box, groups, yaw, "looking away", **pose)
        state = classify_state(groups, baseline)
        return EmotionResult(self.labels[idx], state, float(probs[idx]), scores, box, groups, yaw, **pose)

    def analyze_bytes(self, data: bytes, baseline: dict | None = None) -> EmotionResult:
        if not data:
            raise ValueError("Empty image")
        image = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
        if image is None:
            raise ValueError("Could not decode image")
        return self.analyze(image, baseline)


_detector: EmotionDetector | None = None


def get_detector() -> EmotionDetector:
    global _detector
    if _detector is None:
        _detector = EmotionDetector()
    return _detector
