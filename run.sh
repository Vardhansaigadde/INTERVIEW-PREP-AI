#!/usr/bin/env bash
# One-time setup + start the app on http://127.0.0.1:8000  (macOS / Linux)
# Usage:  ./run.sh
set -euo pipefail
cd "$(dirname "$0")"

if [ ! -d .venv ]; then
  python3 -m venv .venv
  .venv/bin/pip install -r requirements.txt
fi
mkdir -p models
[ -f models/emotion-ferplus-8.onnx ] || curl -L -o models/emotion-ferplus-8.onnx \
  https://github.com/onnx/models/raw/main/validated/vision/body_analysis/emotion_ferplus/model/emotion-ferplus-8.onnx
[ -f models/face_detection_yunet_2023mar.onnx ] || curl -L -o models/face_detection_yunet_2023mar.onnx \
  https://github.com/opencv/opencv_zoo/raw/main/models/face_detection_yunet/face_detection_yunet_2023mar.onnx
if [ ! -d frontend/dist ]; then
  (cd frontend && npm install && npm run build)
fi

.venv/bin/python -m uvicorn --app-dir backend app.main:app --host 127.0.0.1 --port 8000
