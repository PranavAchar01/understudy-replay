"""Film v2: cuts the raw app recording (film/tools/film-site.mts) into the demo piece of the cut.

Copied from player-two/scripts/edit-film.py, the script that cut app-50s.mp4 for the Personal Brains video. Same
segments and speeds: typing and the run timeline sped up, the robot footage close to real time. Understudy has one
recorded run where Player Two had two, so the one run ends the way Player Two's second did: two seconds after moving
to the next clip in the viewer. No sound: the Understudy cut is silent, so the sound design is dropped.

usage: .venv/bin/python scripts/film2_edit_app.py <film-dir> <out.mp4>   (TARGET=seconds, default 30)
"""

import json
import os
import subprocess
import sys
from pathlib import Path

film, out = Path(sys.argv[1]), Path(sys.argv[2])
cues = json.loads((film / "cues.json").read_text())


def first(kind: str, after: float = 0.0) -> float:
    return next(c["t"] for c in cues if c["type"] == kind and c["t"] >= after)


def last_before(kind: str, before: float) -> float:
    return [c["t"] for c in cues if c["type"] == kind and c["t"] < before][-1]


# ---- segments of the raw recording: (start, end, speed)
segments: list[tuple[float, float, float]] = []
loaded = first("loaded")
order = [
    int(c["type"].rsplit("-", 1)[1])
    for c in cues
    if c["type"].startswith("demo-start-")
]
for n, which in enumerate(order):
    start, end = first(f"demo-start-{which}"), first(f"demo-end-{which}")
    first_tick = first("tick", start)
    compose = last_before("click", first_tick)
    success = first("success", start)
    clicks_after = [
        c["t"] for c in cues if c["type"] == "click" and success < c["t"] < end
    ]
    # the headline resolving out of its blur, typing, the run timeline, then the library and the viewer; the last
    # piece stops two seconds after moving to the next clip (Player Two's second-demo ending)
    segments.append((loaded + 0.15, start + 1.0, 1.0))
    segments.append((start + 1.0, compose, 1.8))
    segments.append((compose, success + 0.6, 1.6))
    stop = clicks_after[1] + 1.8 if len(clicks_after) > 1 else end - 0.2
    segments.append((success + 0.6, stop, 1.18))


# Hold the cut to TARGET seconds: a longer sentence takes longer to type, so the typing and run-timeline segments
# (the ones already sped up past 1.5x) absorb the difference. The robot footage keeps its near-real-time speed.
TARGET = float(os.environ.get("TARGET", "30"))
fixed = sum((b - a) / sp for a, b, sp in segments if sp < 1.5)
flexible = sum((b - a) / sp for a, b, sp in segments if sp >= 1.5)
if fixed + flexible > TARGET:
    squeeze = flexible / (TARGET - fixed)
    segments = [(a, b, sp * squeeze if sp >= 1.5 else sp) for a, b, sp in segments]


def remap(t: float) -> float | None:
    acc = 0.0
    for a, b, sp in segments:
        if a <= t < b:
            return acc + (t - a) / sp
        acc += (b - a) / sp
    return None


total = sum((b - a) / sp for a, b, sp in segments)
print("final length", round(total, 2), "s from", len(segments), "segments")

# ---- picture
# A recording that is already 1920 wide is left alone; an older 1280 one is scaled up and sharpened a little.
raw_w = int(subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width", "-of", "csv=p=0", str(film / "raw.webm")], capture_output=True, text=True).stdout.strip() or 0)
SCALE = "" if raw_w >= 1920 else "scale=1920:1080:flags=lanczos,unsharp=5:5:0.5:5:5:0.0,"
# NO_FADE_OUT=1 when another clip follows this one (scripts/join-film.py fades between them)
FADE_OUT = "" if os.environ.get("NO_FADE_OUT") else f",fade=t=out:st={total - 0.6:.3f}:d=0.6"
# NO_FADE_IN=1 when another clip comes before this one
FADE_IN = "" if os.environ.get("NO_FADE_IN") else "fade=t=in:st=0:d=0.5"
parts, labels = [], []
for i, (a, b, sp) in enumerate(segments):
    parts.append(
        f"[0:v]trim=start={a:.3f}:end={b:.3f},setpts=(PTS-STARTPTS)/{sp},fps=30[s{i}]"
    )
    labels.append(f"[s{i}]")
graph = (
    ";".join(parts)
    + f";{''.join(labels)}concat=n={len(segments)}:v=1:a=0,{SCALE}{FADE_IN or 'null'}{FADE_OUT}[v]"
)
subprocess.run(
    [
        "ffmpeg",
        "-y",
        "-loglevel",
        "error",
        "-i",
        str(film / "raw.webm"),
        "-filter_complex",
        graph,
        "-map",
        "[v]",
        "-c:v",
        "libx264",
        "-crf",
        "19",
        "-preset",
        "slow",
        "-pix_fmt",
        "yuv420p",
        "-an",
        "-t",
        f"{total:.3f}",
        "-movflags",
        "+faststart",
        str(out),
    ],
    check=True,
)
print("wrote", out)
