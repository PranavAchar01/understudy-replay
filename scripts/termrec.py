"""Record a terminal session verbatim: run a command in a pseudo-terminal, pass its output through, and log every
output chunk with its wall-clock offset to a JSONL file. The film's terminal time-lapse replays exactly these bytes.

    .venv/bin/python scripts/termrec.py data/term/mlp.jsonl -- bin/understudy train ...

First line: {"cmd": "...", "cwd": "...", "start": <unix time>}; then {"t": seconds, "d": text} per chunk; last line
{"end": seconds, "exit": code}.
"""

from __future__ import annotations

import json
import os
import pty
import shlex
import subprocess
import sys
import time


def main() -> None:
    out, argv = sys.argv[1], sys.argv[sys.argv.index("--") + 1 :]
    shown = shlex.join(argv)  # exactly what ran, nice and taskpolicy included
    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
    master, slave = pty.openpty()
    env = dict(os.environ, COLUMNS="120", LINES="40", TERM="xterm-256color")
    t0 = time.time()
    p = subprocess.Popen(
        argv, stdin=slave, stdout=slave, stderr=slave, env=env, close_fds=True
    )
    os.close(slave)
    with open(out, "w") as f:
        f.write(json.dumps({"cmd": shown, "cwd": os.getcwd(), "start": t0}) + "\n")
        while True:
            try:
                b = os.read(master, 65536)
            except OSError:
                break
            if not b:
                break
            s = b.decode("utf-8", "replace")
            sys.stdout.write(s)
            sys.stdout.flush()
            f.write(json.dumps({"t": round(time.time() - t0, 3), "d": s}) + "\n")
            f.flush()
        code = p.wait()
        f.write(json.dumps({"end": round(time.time() - t0, 3), "exit": code}) + "\n")
    sys.exit(code)


if __name__ == "__main__":
    main()
