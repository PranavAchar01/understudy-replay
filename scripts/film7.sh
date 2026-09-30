#!/bin/zsh
# Film v7: the live site (ends at the LeRobot dataset download), the two-engine check, training in the terminal
# (verbatim time-lapse), SmolVLA vs the MLP in MuJoCo, the stack. Silent. 0 Runway credits.
# 1. the site, unable to spend, 7 clips like the first run:
#      UNDERSTUDY_FLOOR_BALANCE=100000 UNDERSTUDY_CLIPS=7 bin/understudy serve
#    record: film/node_modules/.bin/tsx film/tools/record-live.mts media/work7/live --task "put the red block in the bowl" \
#      --type-frames 2 --hold-footage 3.2 --hold-accepted 3.5 --hold-rejected 6.0 --hold-dataset 4.5
# 2. the terminal runs, each recorded by scripts/termrec.py into data/term/:
#      scripts/train_smolvla.sh; scripts/eval_smolvla.sh; scripts/train_mlp.sh; scripts/crosscheck.sh
# 3. static server for the deck: (cd film && python3 -m http.server 4650 --bind 127.0.0.1)
# 4. this script: facts + edit list + render + 720p
set -e
cd ${0:A:h}/..
[ "$FILM7_TEST" = 1 ] && { echo "FILM7_TEST is set: layout test only"; exit 1; }
.venv/bin/python scripts/film7_assets.py
.venv/bin/python scripts/film5_edit.py --work work7 --data 14 --take live:compose:
nice -n 19 taskpolicy -b ./film/node_modules/.bin/tsx film/tools/render-v4.mts media/work7/v7-raw.mp4 http://localhost:4650/deck/v7.html
cp media/work7/v7-raw.mp4 media/understudy-demo-v7.mp4
nice -n 19 ffmpeg -v error -y -i media/understudy-demo-v7.mp4 -vf scale=1280:720:flags=lanczos -c:v libx264 -crf 20 -preset slow -pix_fmt yuv420p -an -movflags +faststart media/understudy-demo-v7-720p.mp4
