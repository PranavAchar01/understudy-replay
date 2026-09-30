#!/bin/zsh
# Film v3: the Understudy demo, one robot from all the clips. Silent, Player Two look (film/deck/v3.html).
# Needs: .venv, film/node_modules, Chrome for Testing from ms-playwright, and a static server:
#   (cd film && python3 -m http.server 4650 --bind 127.0.0.1)
# The Runway robot clip is made once by scripts/v3_robot_clip.py (27 credits); this script never calls Runway.
# Heavy steps run at the lowest priority (machine sharing).
# usage: scripts/film3.sh [assets]
set -e
cd ${0:A:h}/..
W=media/work3
mkdir -p $W
[[ $1 == assets || ! -f film/deck/media/v3/hero.mp4 ]] && PYTHONPATH=src nice -n 19 taskpolicy -b .venv/bin/python scripts/film3_assets.py
#      title prompt robot drop inside1 inside2 train model hero end
DWELL="4000,11500,7800,5000,10000,9000,8000,7500,13100,6500"
nice -n 19 ./film/node_modules/.bin/tsx film/tools/film-deck.mts $W/film-v3 "http://localhost:4650/deck/v3.html?dwell=$DWELL"
nice -n 19 taskpolicy -b .venv/bin/python scripts/film2_join.py media/understudy-demo-v3.mp4 auto $W/film-v3
