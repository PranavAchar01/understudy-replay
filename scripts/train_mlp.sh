#!/bin/zsh
# The small MLP baseline on the site's dataset, in a terminal (recorded verbatim to data/term/mlp.jsonl).
set -e
cd ${0:A:h}/..
exec .venv/bin/python scripts/termrec.py data/term/mlp.jsonl -- nice -n 19 taskpolicy -b bin/understudy train put-the-red-block-in-the-bowl
