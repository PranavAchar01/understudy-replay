#!/bin/zsh
# Takes ~/helloworld/.heavy-lock (waits while a live PID holds it), builds the given sections in parallel, releases.
cd ${0:A:h}
L=~/helloworld/.heavy-lock
until mkdir $L 2>/dev/null; do
  o=$(cat $L/owner 2>/dev/null)
  if [[ -n $o ]] && ! kill -0 $o 2>/dev/null; then rm -r $L; continue; fi
  sleep 5
done
echo $$ > $L/owner
echo "LOCK $(date +%T)"
pids=()
for s in "$@"; do nice -n 19 taskpolicy -b work/.venv/bin/python build.py $s > work/log-$s.txt 2>&1 & pids+=$!; done
for p in $pids; do wait $p; done
rm -r $L
echo "ALLDONE $(date +%T)"
