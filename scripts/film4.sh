#!/bin/zsh
# Film v4: v3's story in the Player Two frame at a true 30 fps. Silent. Never calls Runway.
# Needs .venv, film/node_modules, Chrome for Testing (ms-playwright), and a static server:
#   (cd film && python3 -m http.server 4650 --bind 127.0.0.1)
# usage: scripts/film4.sh [assets]
set -e
cd ${0:A:h}/..
[[ $1 == assets || ! -f film/deck/media/v4/hero.mp4 ]] && PYTHONPATH=src nice -n 19 taskpolicy -b .venv/bin/python scripts/film4_assets.py
nice -n 19 taskpolicy -b ./film/node_modules/.bin/tsx film/tools/render-v4.mts media/work4/v4-raw.mp4 http://localhost:4650/deck/v4.html
cp media/work4/v4-raw.mp4 media/understudy-demo-v4.mp4
nice -n 19 ffmpeg -v error -y -i media/understudy-demo-v4.mp4 -vf scale=1280:720:flags=lanczos -c:v libx264 -crf 20 -preset slow -pix_fmt yuv420p -an -movflags +faststart media/understudy-demo-v4-720p.mp4
.venv/bin/python scripts/fps_probe.py media/understudy-demo-v4.mp4 "0,4.5,9.4,13,19.2,23.8,28.75,36.75,42.15,48.05,55.05,61.85,67.65,80.45"
