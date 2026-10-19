#!/usr/bin/env bash
# Download the two MediaPipe landmark models the pose stage needs into data/models/ (about 38 MB, Apache-2.0).
# Add --policy to also download the trained pick SmolVLA (907 MB) from the GitHub release vla-pick-20k (needs unzip).
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
M="$ROOT/data/models"
mkdir -p "$M"
BASE=https://storage.googleapis.com/mediapipe-models
get() { [ -s "$M/$2" ] && { echo "have $2"; return; }; echo "fetching $2"; curl -fL -sS -o "$M/$2.part" "$BASE/$1" && mv "$M/$2.part" "$M/$2"; }
get hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task hand_landmarker.task
get pose_landmarker/pose_landmarker_heavy/float16/1/pose_landmarker_heavy.task pose_landmarker_heavy.task
if [ "${1:-}" = "--policy" ]; then
  mkdir -p "$M/policy"
  Z="$M/policy/understudy-smolvla-pick-20k.zip"
  [ -s "$Z" ] || curl -fL -sS -o "$Z" https://github.com/PranavAchar01/understudy-replay/releases/download/vla-pick-20k/understudy-smolvla-pick-20k.zip
  unzip -qn "$Z" -d "$M/policy"
  echo "unzipped into $M/policy; set UNDERSTUDY_VLA_CKPT in .env to the folder that holds config.json"
fi
