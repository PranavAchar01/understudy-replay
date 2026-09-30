#!/usr/bin/env bash
# Film v8, 2:00, silent, 0 Runway credits:
#   0:00-0:20  the problem          (Runway plates, source pop-ups)
#   0:20-1:40  the site demo        (the deployed site, recorded by film/tools/record-v2.mts)   ?cut=bench: the benchmark slides
#   1:40-2:00  the takeaway
#
#   scripts/film8.sh                      record the site from understudy-replay.vercel.app, then render
#   SITE_URL=http://127.0.0.1:4651/ scripts/film8.sh     record a local copy of the site instead
#   SKIP_RECORD=1 scripts/film8.sh        re-render with the recording already in film/deck/media/v8/
#   CUT=bench scripts/film8.sh            the benchmark cut (no recording needed)
# -> media/understudy-demo-v8.mp4 + -720p.mp4
#
# Watch the deck live: python3 -m http.server 4650 --bind 127.0.0.1 (repo root), open /film/deck/v8.html
# (space pauses, arrows skip a shot, ?t=SECONDS starts there, ?cut=bench).
# Optional: put the Runpod screenshot at film/v8/sources/runpod.png and the deck shows it instead of its fact card.
# A Chromium without H.264 (Linux builds): VP9 copies go to film/deck/media/v8/ (gitignored) and the deck picks
# them up; for the recording set WEBM_ROOT to a local copy of the site holding <path>.webm next to each <path>.mp4.
# CHROME=<binary> and CHROME_ARGS="--no-sandbox" (as root) pass through to both tools.
set -euo pipefail
cd "$(dirname "$0")/.."
CUT="${CUT:-site}"
mkdir -p film/deck/media/v8 media
for c in v01 v03 v06 v07; do
  out=film/deck/media/v8/$c.webm
  [ -s "$out" ] || ffmpeg -v error -y -i data/runs/put-the-red-block-in-the-bowl/clips/$c.mp4 -c:v libvpx-vp9 -crf 18 -b:v 0 -row-mt 1 -an "$out"
done
if [ "$CUT" = site ] && [ -z "${SKIP_RECORD:-}" ]; then
  ./film/node_modules/.bin/tsx film/tools/record-v2.mts film/deck/media/v8/site.mp4 --url "${SITE_URL:-https://understudy-replay.vercel.app/}"
  ffmpeg -v error -y -i film/deck/media/v8/site.mp4 -c:v libvpx-vp9 -crf 20 -b:v 0 -row-mt 1 -an film/deck/media/v8/site.webm
fi
python3 -m http.server 4650 --bind 127.0.0.1 >/dev/null 2>&1 &
SERVER=$!
trap 'kill $SERVER' EXIT
sleep 1
./film/node_modules/.bin/tsx film/tools/render-v4.mts media/understudy-demo-v8.mp4 "http://127.0.0.1:4650/film/deck/v8.html?cut=$CUT" "$@"
ffmpeg -v error -y -i media/understudy-demo-v8.mp4 -vf scale=1280:720:flags=lanczos -c:v libx264 -crf 20 -preset slow -pix_fmt yuv420p -an -movflags +faststart media/understudy-demo-v8-720p.mp4
