# One-time setup + start the app on http://127.0.0.1:8000
# Usage (PowerShell, from the project folder):  .\run.ps1
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

if (-not (Test-Path ".venv")) {
    python -m venv .venv
    .\.venv\Scripts\pip install -r requirements.txt
}
New-Item -ItemType Directory -Force models | Out-Null
if (-not (Test-Path "models\emotion-ferplus-8.onnx")) {
    Invoke-WebRequest "https://github.com/onnx/models/raw/main/validated/vision/body_analysis/emotion_ferplus/model/emotion-ferplus-8.onnx" -OutFile "models\emotion-ferplus-8.onnx"
}
if (-not (Test-Path "models\face_detection_yunet_2023mar.onnx")) {
    Invoke-WebRequest "https://github.com/opencv/opencv_zoo/raw/main/models/face_detection_yunet/face_detection_yunet_2023mar.onnx" -OutFile "models\face_detection_yunet_2023mar.onnx"
}
if (-not (Test-Path "frontend\dist")) {
    Push-Location frontend; npm install; npm run build; Pop-Location
}

Set-Location backend
..\.venv\Scripts\python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
