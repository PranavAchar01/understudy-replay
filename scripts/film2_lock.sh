#!/bin/zsh
# Runs a heavy render step under ~/helloworld/.render-lock (machine sharing rule), then releases the lock.
# usage: scripts/film2_lock.sh <label> <command...>
LOCK=~/helloworld/.render-lock
if [[ -f $LOCK ]]; then
  pid=$(sed -n 's/^pid=//p' $LOCK)
  if [[ -n $pid ]] && kill -0 $pid 2>/dev/null; then echo "render lock is live: $(cat $LOCK)"; exit 75; fi
fi
label=$1; shift
printf 'pid=%s\nowner=understudy film v2 (%s)\nstarted=%s\n' $$ "$label" "$(date '+%Y-%m-%d %H:%M')" > $LOCK
"$@"; rc=$?
rm -f $LOCK
exit $rc
