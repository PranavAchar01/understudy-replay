#!/bin/zsh
# Film v2: the Understudy demo in the Player Two (Personal Brains) style, silent.
# Title + pitch (deck) -> the app demo (film/app, a copy of player-two-site) -> the stack B-roll (deck).
# Heavy steps run under ~/helloworld/.render-lock (scripts/film2_lock.sh). Needs: .venv, film/node_modules
# (npm install in film/), Chrome for Testing from ms-playwright, and a static server:
#   (cd film && python3 -m http.server 4650 --bind 127.0.0.1)
# usage: scripts/film2.sh [assets]
set -e
cd ${0:A:h}/..
W=media/work2
mkdir -p $W
[[ $1 == assets || ! -f film/app/media/demo/manifest.json ]] && PYTHONPATH=src scripts/film2_lock.sh assets .venv/bin/python scripts/film2_assets.py
cp $W/facts.json film/deck/media/facts.json
INTRO="4500,5000"
STACK="4800,4800,4500,6500,5500,5500,5000,6500,5500"
scripts/film2_lock.sh film-app ./film/node_modules/.bin/tsx film/tools/film-site.mts $W/film-app http://localhost:4650/app/
NO_FADE_IN=1 NO_FADE_OUT=1 TARGET=30 .venv/bin/python scripts/film2_edit_app.py $W/film-app $W/app.mp4
scripts/film2_lock.sh film-intro ./film/node_modules/.bin/tsx film/tools/film-deck.mts $W/film-intro "http://localhost:4650/deck/broll.html?set=intro&dwell=$INTRO"
scripts/film2_lock.sh film-stack ./film/node_modules/.bin/tsx film/tools/film-deck.mts $W/film-stack "http://localhost:4650/deck/broll.html?set=stack&dwell=$STACK"
scripts/film2_lock.sh join .venv/bin/python scripts/film2_join.py media/understudy-demo-v2.mp4 auto $W/film-intro $W/app.mp4 $W/film-stack
