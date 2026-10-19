#!/usr/bin/env bash
# One-time setup from a fresh clone: Python 3.12 env (.venv), a Python 3.11 env for hand tracking (.venv-pose),
# the MediaPipe models, and a .env to fill in. Needs uv (https://docs.astral.sh/uv/) and ffmpeg on PATH.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
command -v uv >/dev/null || { echo "uv is missing: https://docs.astral.sh/uv/getting-started/installation/"; exit 1; }
command -v ffmpeg >/dev/null || { echo "ffmpeg is missing: brew install ffmpeg (macOS) or apt install ffmpeg (Linux)"; exit 1; }

echo "== main environment (.venv, Python 3.12) =="
uv sync --frozen

echo "== hand-tracking environment (.venv-pose, Python 3.11) =="
# mediapipe 0.10.14 is the last release that runs here (newer ones abort with "graph_service.h Service is unavailable")
[ -x .venv-pose/bin/python ] || uv venv --python 3.11 .venv-pose
uv pip install --python .venv-pose/bin/python "mediapipe==0.10.14" opencv-python-headless numpy

echo "== MediaPipe models =="
scripts/fetch_models.sh

[ -f .env ] || { cp .env.example .env; echo "created .env from .env.example"; }
echo
echo "Setup done. Next: open .env and fill in your keys (all optional for the cached demo), then run: make demo"
