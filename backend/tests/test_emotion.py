from pathlib import Path

import cv2
import numpy as np

from app.emotion import NEUTRAL_FACE_MEAN, classify_state, estimate_yaw, get_detector
from app.recommender import smooth_state

FACE = Path(__file__).parent / "fixtures" / "face.jpg"


def groups(engaged=0.05, confused=0.05, frustrated=0.0):
    return {"engaged": engaged, "confused": confused, "frustrated": frustrated}


def test_mild_confusion_is_not_hidden_by_neutral():
    # neutral 0.70, sad 0.20, fear 0.05: argmax says "neutral", but the confused group is clearly raised
    assert classify_state(groups(confused=0.25)) == "confused"


def test_mild_frustration_detected():
    assert classify_state(groups(confused=0.05, frustrated=0.15)) == "frustrated"


def test_calm_face_is_neutral():
    assert classify_state(groups(engaged=0.08, confused=0.09, frustrated=0.01)) == "neutral"


def test_smile_is_engaged():
    assert classify_state(groups(engaged=0.8)) == "engaged"


def test_baseline_removes_resting_face_bias():
    # someone whose resting face always scores 0.22 "confused" should read as neutral...
    base = {"engaged": 0.05, "confused": 0.22, "frustrated": 0.01}
    assert classify_state(groups(confused=0.22), base) == "neutral"
    # ...but a real jump above their own resting level is still caught
    assert classify_state(groups(confused=0.40), base) == "confused"


def test_baseline_shift_is_capped():
    from app.main import MAX_BASELINE_SHIFT
    assert NEUTRAL_FACE_MEAN["confused"] + MAX_BASELINE_SHIFT < 0.5


def test_yaw_from_landmarks():
    # YuNet row: x, y, w, h, right eye, left eye, nose, mouth right, mouth left, score
    frontal = np.array([0, 0, 100, 100, 30, 40, 70, 40, 50, 60, 35, 80, 65, 80, 0.9], dtype=np.float32)
    turned = frontal.copy()
    turned[8] = 72  # nose shifted well to one side
    assert abs(estimate_yaw(frontal)) < 0.05
    assert abs(estimate_yaw(turned)) > 0.4


def test_empty_frame_is_away():
    r = get_detector().analyze(np.full((240, 320, 3), 90, np.uint8))
    assert r.state == "distracted" and r.reason == "no face in view"


def test_real_face_detected():
    r = get_detector().analyze(cv2.imread(str(FACE)))
    assert r.face_box is not None
    assert r.state in {"engaged", "neutral", "confused", "frustrated"}
    assert set(r.groups) == {"engaged", "confused", "frustrated"}


def test_smoothing_stops_flicker():
    assert smooth_state(["neutral", "confused", "neutral"]) == "neutral"
    assert smooth_state(["neutral", "confused", "confused"]) == "confused"
    assert smooth_state(["engaged", "confused", "distracted"]) == "distracted"  # tie -> newest
