#!/usr/bin/env bash
# Film v8: 2:00 benchmark cut. 0:00-0:20 the problem, 0:20-1:40 the benchmark (docs/BENCHMARK.md), 1:40-2:00 the
# takeaway. Silent. 0 Runway credits: the plates are the 4 accepted Runway clips already in data/runs/.
#   watch it live:  python3 -m http.server 4650 --bind 127.0.0.1   (repo root), open /film/deck/v8.html
#                   (space pauses, arrows skip a shot, ?t=SECONDS starts there)
#   render it:      scripts/film8.sh            -> media/understudy-demo-v8.mp4 + -720p.mp4
# Linux Chromium has no H.264, so VP9 copies of the clips go to film/deck/media/v8/ (gitignored); the deck picks
# them up by itself. CHROME=<binary> and CHROME_ARGS="--no-sandbox" (as root) are passed through to the renderer.
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p film/deck/media/v8 media
for c in v01 v03 v06 v07; do
  out=film/deck/media/v8/$c.webm
  [ -s "$out" ] || ffmpeg -v error -y -i data/runs/put-the-red-block-in-the-bowl/clips/$c.mp4 -c:v libvpx-vp9 -crf 18 -b:v 0 -row-mt 1 -an "$out"
done
python3 -m http.server 4650 --bind 127.0.0.1 >/dev/null 2>&1 &
SERVER=$!
trap 'kill $SERVER' EXIT
sleep 1
./film/node_modules/.bin/tsx film/tools/render-v4.mts media/understudy-demo-v8.mp4 http://127.0.0.1:4650/film/deck/v8.html "$@"
ffmpeg -v error -y -i media/understudy-demo-v8.mp4 -vf scale=1280:720:flags=lanczos -c:v libx264 -crf 20 -preset slow -pix_fmt yuv420p -an -movflags +faststart media/understudy-demo-v8-720p.mp4
