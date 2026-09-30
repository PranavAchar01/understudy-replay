"""Film v5 edit list: which recorded frame goes on each output frame, and how fast each part runs.

Input: one or more recordings from film/tools/record-live.mts (each a folder with frames/ and timeline.json:
every captured frame with its page time and wall time, plus named marks), each cut to a mark range. Output:
media/work5/edl.json for film/deck/v5.html:

  frames[k] = path of the recorded frame shown on output frame k (relative to media/work5)
  speed[k]  = real seconds per output second at frame k (1 = as recorded)
  take[k]   = which recording frame k comes from
  marks     = each mark's time in the output, in seconds
  cuts      = output times where one recording ends and the next begins

UI beats (typing, clicks, the drag, the rollout) play as recorded: one frame per 1/30 s of page time. The waits on
real server work (Runway, the data stage, training) were captured on the wall clock; each is resampled to a target
length at a constant speed-up measured from the wall times, which the film prints on screen. A wait is never
slowed down.

usage: .venv/bin/python scripts/film5_edit.py --take live:compose:inspect-accepted --take take3:reopened:
       (folder under media/work5 : first mark : mark to stop before, empty = to the end)
"""

from __future__ import annotations

import argparse
import bisect
import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
WORK = REPO / "media" / "work5"
FPS = 30
WAITS = ("footage", "data", "train")


def main() -> None:
    ap = argparse.ArgumentParser()
    for w, d in (("footage", 9.0), ("data", 12.0), ("train", 9.0)):
        ap.add_argument(f"--{w}", type=float, default=d)
    ap.add_argument("--take", action="append", required=True)
    ap.add_argument("--work", default="work5", help="folder under media/ (v6: work6)")
    a = ap.parse_args()
    global WORK
    WORK = REPO / "media" / a.work
    out_frames: list[str] = []
    speed: list[float] = []
    takes: list[int] = []
    out_marks: dict[str, float] = {}
    waits: dict[str, dict] = {}
    cuts: list[float] = []
    for ti, spec in enumerate(a.take):
        folder, m0, m1 = (spec.split(":") + ["", ""])[:3]
        tl = json.loads((WORK / folder / "timeline.json").read_text())
        frames, marks = tl["frames"], tl["marks"]
        i = marks[m0] if m0 else 0
        stop = marks[m1] if m1 else len(frames)
        if ti:
            cuts.append(len(out_frames) / FPS)
        order = sorted(marks.items(), key=lambda kv: kv[1])
        path = lambda f: f"{folder}/frames/{f['i']:06d}.jpg"  # noqa: E731
        while i < stop:
            for name, at in order:
                if at == i and name not in out_marks:
                    out_marks[name] = len(out_frames) / FPS
            w = next(
                (
                    w
                    for w in WAITS
                    if marks.get(f"{w}:start") == i
                    and marks.get(f"{w}:end", i) > i  # a wait that ended before its first frame (cache) is none
                ),
                None,
            )
            if w:
                j = marks[f"{w}:end"]
                seg = frames[i:j]
                wall0 = seg[0]["wall"] if seg else frames[i]["wall"]
                wall1 = frames[j]["wall"] if j < len(frames) else seg[-1]["wall"]
                real = (wall1 - wall0) / 1000
                k = max(1, round(min(getattr(a, w), real) * FPS)) if seg else 0
                walls = [f["wall"] for f in seg]
                for m in range(k):
                    t = wall0 + (wall1 - wall0) * m / k
                    idx = min(len(seg) - 1, max(0, bisect.bisect_right(walls, t) - 1))
                    out_frames.append(path(seg[idx]))
                    speed.append(real / (k / FPS))
                    takes.append(ti)
                if k:
                    waits[w] = {
                        "real_s": round(real, 1),
                        "out_s": round(k / FPS, 2),
                        "speed": round(real / (k / FPS), 1),
                    }
                out_marks[f"{w}:end"] = len(out_frames) / FPS
                i = j
                continue
            out_frames.append(path(frames[i]))
            speed.append(1.0)
            takes.append(ti)
            i += 1
        out_marks[f"take{ti}:end"] = len(out_frames) / FPS
    edl = {
        "fps": FPS,
        "frames": out_frames,
        "speed": speed,
        "take": takes,
        "marks": out_marks,
        "waits": waits,
        "cuts": cuts,
        "seconds": round(len(out_frames) / FPS, 2),
    }
    (WORK / "edl.json").write_text(json.dumps(edl))
    print(
        json.dumps(
            {
                "seconds": edl["seconds"],
                "waits": waits,
                "cuts": cuts,
                "marks": out_marks,
            },
            indent=1,
        )
    )


if __name__ == "__main__":
    main()
