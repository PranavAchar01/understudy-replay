#!/bin/zsh
# Film v6: one real session on the live site, on the first run's sentence (Runway footage replayed from the cache,
# 0 credits), v5's frame and pop-ups plus the PhyT2V pop-up and a slow push. Silent.
# 1. the site, unable to spend (floor far above the balance), 7 clips like the first run:
#      UNDERSTUDY_FLOOR_BALANCE=100000 UNDERSTUDY_CLIPS=7 bin/understudy serve
#    record: film/node_modules/.bin/tsx film/tools/record-live.mts media/work6/live --task "put the red block in the bowl" \
#      --type-frames 2 --hold-footage 3.2 --hold-accepted 3.5 --hold-rejected 6.5
# 2. static server for the deck: (cd film && python3 -m http.server 4650 --bind 127.0.0.1)
# 3. this script: facts + edit list + render + 720p
set -e
cd ${0:A:h}/..
.venv/bin/python scripts/film6_assets.py put-the-red-block-in-the-bowl
.venv/bin/python scripts/film5_edit.py --work work6 --data 16 --train 10 --take live:compose:
nice -n 19 taskpolicy -b ./film/node_modules/.bin/tsx film/tools/render-v4.mts media/work6/v6-raw.mp4 http://localhost:4650/deck/v6.html
cp media/work6/v6-raw.mp4 media/understudy-demo-v6.mp4
nice -n 19 ffmpeg -v error -y -i media/understudy-demo-v6.mp4 -vf scale=1280:720:flags=lanczos -c:v libx264 -crf 20 -preset slow -pix_fmt yuv420p -an -movflags +faststart media/understudy-demo-v6-720p.mp4
