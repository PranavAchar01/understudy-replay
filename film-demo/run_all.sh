#!/bin/zsh
# Runs the given sections in parallel under the shared heavy-lock (this script's PID owns it).
cd ${0:A:h}
echo $$ > ~/helloworld/.heavy-lock/owner
pids=()
for s in "$@"; do nice -n 19 taskpolicy -b python3 build.py $s > work/log-$s.txt 2>&1 & pids+=$!; done
for p in $pids; do wait $p; done
rm -r ~/helloworld/.heavy-lock
echo ALLDONE
