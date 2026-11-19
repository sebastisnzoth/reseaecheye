#!/usr/bin/env bash
# rapidocr-onnxruntime declares opencv-python (GUI build) as a dependency.
# On headless servers that build fails with "libGL.so.1: cannot open shared object".
# Keep the headless wheel instead; cv2 APIs used here are identical.
set -euo pipefail
cd "$(dirname "$0")/.."
.venv/bin/pip uninstall -y opencv-python >/dev/null 2>&1 || true
.venv/bin/pip install --force-reinstall opencv-python-headless -q
.venv/bin/python -c "import cv2; print('OpenCV headless OK:', cv2.__version__)"
