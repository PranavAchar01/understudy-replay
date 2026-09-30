#!/bin/zsh
# Film v5: the recording of a real session on the live site, with the v4 frame and B-roll pop-ups on top. Silent.
# 1. the site must be running (bin/understudy serve) and the session recorded:
#      film/node_modules/.bin/tsx film/tools/record-live.mts media/work5/live --task "put a red block into a bowl"   (take 2)
#      film/node_modules/.bin/tsx film/tools/record-live.mts media/work5/take3 --reopen put-a-red-block-into-a-bowl   (take 3)
# 2. then this script: facts + edit list + render + 720p + fps probe. Needs a static server for the deck:
#      (cd film && python3 -m http.server 4650 --bind 127.0.0.1)
# usage: scripts/film5.sh [slug]
set -e
cd ${0:A:h}/..
SLUG=${1:-put-a-red-block-into-a-bowl}
.venv/bin/python scripts/film5_assets.py $SLUG
.venv/bin/python scripts/film5_edit.py --train 10 --take live:compose:inspect-accepted --take take3:reopened:
nice -n 19 taskpolicy -b ./film/node_modules/.bin/tsx film/tools/render-v4.mts media/work5/v5-raw.mp4 http://localhost:4650/deck/v5.html
cp media/work5/v5-raw.mp4 media/understudy-demo-v5.mp4
nice -n 19 ffmpeg -v error -y -i media/understudy-demo-v5.mp4 -vf scale=1280:720:flags=lanczos -c:v libx264 -crf 20 -preset slow -pix_fmt yuv420p -an -movflags +faststart media/understudy-demo-v5-720p.mp4
