"""Film v2: joins the parts of the cut in order with half-second cross-fades, silent.

Copied from player-two/scripts/join-film.py (the Personal Brains join): same 0.5 s fades between parts, same
0.8 s fade to black at the end, same trimming of a filmed deck from its first slide to its "done" cue. Understudy's
cut has no audio at all, so the page sounds and the audio stream are gone; the result has a video stream only.

usage: .venv/bin/python scripts/film2_join.py <out.mp4> <total-seconds|auto> <part> [<part> ...]
A part is an .mp4 (used as it is) or a film directory from film/tools/film-deck.mts (raw.webm + cues.json).
Also writes <out>-720p.mp4.
"""

import json
import subprocess
import sys
from pathlib import Path

FADE = 0.5
out = Path(sys.argv[1])
parts = [Path(p) for p in sys.argv[3:]]


def seconds(f: Path) -> float:
    got = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "csv=p=0",
            str(f),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    return float(got.stdout.strip())


inputs: list[str] = []
chains: list[str] = []
durations: list[float] = []
for k, part in enumerate(parts):
    inputs += ["-i", str(part if part.suffix == ".mp4" else part / "raw.webm")]
    if part.suffix == ".mp4":
        dur = seconds(part)
        chains.append(
            f"[{k}:v]fps=30,scale=1920:1080:flags=lanczos,format=yuv420p,setpts=PTS-STARTPTS[v{k}]"
        )
    else:
        cues = json.loads((part / "cues.json").read_text())
        start = next(c["t"] for c in cues if c["type"] == "slide-0")
        dur = next(c["t"] for c in cues if c["type"] == "done") - start
        chains.append(
            f"[{k}:v]trim=start={start:.3f}:duration={dur:.3f},setpts=PTS-STARTPTS,fps=30,"
            f"scale=1920:1080:flags=lanczos,format=yuv420p[v{k}]"
        )
    durations.append(dur)

natural = sum(durations) - FADE * (len(parts) - 1)
total = natural if sys.argv[2] == "auto" else float(sys.argv[2])
graph = ";".join(chains)
vlast, offset = "v0", 0.0
for k in range(1, len(parts)):
    offset += durations[k - 1] - FADE
    graph += f";[{vlast}][v{k}]xfade=transition=fade:duration={FADE}:offset={offset:.3f}[vx{k}]"
    vlast = f"vx{k}"
graph += f";[{vlast}]fade=t=out:st={total - 0.8:.3f}:d=0.8[v]"
subprocess.run(
    [
        "ffmpeg",
        "-y",
        "-loglevel",
        "error",
        *inputs,
        "-filter_complex",
        graph,
        "-map",
        "[v]",
        "-an",
        "-c:v",
        "libx264",
        "-crf",
        "18",
        "-preset",
        "slow",
        "-pix_fmt",
        "yuv420p",
        "-t",
        f"{total:.3f}",
        "-movflags",
        "+faststart",
        str(out),
    ],
    check=True,
)
subprocess.run(
    [
        "ffmpeg",
        "-y",
        "-loglevel",
        "error",
        "-i",
        str(out),
        "-vf",
        "scale=1280:720:flags=lanczos",
        "-an",
        "-c:v",
        "libx264",
        "-crf",
        "22",
        "-preset",
        "slow",
        "-pix_fmt",
        "yuv420p",
        "-movflags",
        "+faststart",
        str(out.with_name(out.stem + "-720p.mp4")),
    ],
    check=True,
)
starts, t = [], 0.0
for d in durations:
    starts.append(round(t, 2))
    t += d - FADE
print(
    "parts",
    [round(d, 2) for d in durations],
    "start at",
    starts,
    f"natural {natural:.2f} s, cut to {seconds(out):.2f} s",
)
