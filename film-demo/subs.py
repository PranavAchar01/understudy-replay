# Subtitles for the final film from the voice track's word timestamps (mlx-whisper, whisper-small).
# Writes ~/Downloads/understudy-demo-720p.srt and a transparent bottom-strip overlay (work/subs/strip.mov).
# usage: python subs.py <words.json from mlx_whisper> <total seconds>
import json
import re
import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

FD = Path(__file__).resolve().parent
OUT = FD / "work/subs"
OUT.mkdir(parents=True, exist_ok=True)
SRT = Path.home() / "Downloads/understudy-demo-720p.srt"
MAXC = 42
STRIP_H, MARGIN = 64, 26  # strip sits at y = 720 - MARGIN - STRIP_H
TOP_BEFORE = 6.6  # intro shot 1 has its headline at the bottom (y 620-680), so its cues sit at the top

FIX = [  # mis-hearings -> his words (script spellings)
    (r"And right, now", "And right now"),
    (r"and near do most", "and neither do most"),
    (r"I want to see where the Runway", "I wanted to see whether Runway"),
    (r"us\. We type one", "us. You type one"),
    (r"handframes by frame", "hand frame by frame"),
    (r"a one -way model router", "Runway's Model Router"),
    (r"put a red block into a bowl", "put the red block in the bowl"),
    (r"Gen 4 turbo|Jennifer Turbo", "gen4 turbo"),
    (r"C ?-?Dance 2 ?\.5", "Seedance 2.5"),
    (r"that's because the run, the driver run", "that's because the dry run"),
    (r"a clip and at \$10", "a clip, and at $10"),
    (r"25 credits, a clip", "25 credits a clip"),
    (r"rented NVIDIA GPU RunPod", "rented NVIDIA GPU through RunPod"),
    (r"statistical time\.", "statistical tie."),
    (r"This is Understudy|this is Understudy", "This is Understudy"),
    (r"whether it counts This", "whether it counts. This"),
    (r"demonstration physics checks", "demonstrations, physics checks"),
    (r"I want the train on", "I want to train on"),
    (r"press train", "press Train"),
    (r"small VLA", "SmolVLA"),
    (r"everyone keeps", "every run keeps"),
    (r"half rate through", "halfway through"),
    (r"S0101", "SO-101"),
    (r"Mujoko", "MuJoCo"),
    (r"PHY T2V", "PhyT2V"),
    (r"regenerated clip", "regenerate the clip"),
    (r"Nvidia", "NVIDIA"),
    (r"run pod", "RunPod"),
    (r"walks you to exactly", "walks you through exactly"),
    (r"you train before", "you trained before"),
    (r"control test", "controlled test"),
    (r"was whether demonstrations", "was where the demonstrations"),
    (r"statistical time", "statistical tie"),
    (r"people are community", "people at community"),
    (r"like dry took", "like DROID took"),
    (r"a full drill", "a full year"),
    (r"75 ?,000", "76,000"),
    (r"two -day arm teleportation", "two-arm teleoperation"),
    (r"\brunway\b", "Runway"),
    (r"\bunderstudy\b", "Understudy"),
    (r"person\. A Runway imagines", "person. Runway imagines"),
    (r"(\d) ,(\d)", r"\1,\2"),
    (r"(\d) \.(\d)", r"\1.\2"),
    (r" -(\w)", r"-\1"),
    (r"rented NVIDIA GPU RunPod", "rented NVIDIA GPU through RunPod"),
    (r"it counts this is Understudy", "it counts. This is Understudy"),
    (r"\s+", " "),
]


def fix(t):
    for a, b in FIX:
        t = re.sub(a, b, t)
    return t.strip()


def fix_words(words):
    """Apply FIX to the whole transcript, then carry word timings over to the corrected tokens."""
    import difflib

    src = [(w.strip(), s, e) for w, s, e in words if w.strip()]
    a = [w for w, _, _ in src]
    b = fix(" ".join(a)).split(" ")
    res = []
    for op, i1, i2, j1, j2 in difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes():
        if op == "equal":
            res += src[i1:i2]
        elif j2 > j1:
            s0 = src[i1][1] if i2 > i1 else (res[-1][2] if res else 0.0)
            e0 = src[i2 - 1][2] if i2 > i1 else s0 + 0.2
            n = j2 - j1
            for k in range(n):
                res.append((b[j1 + k], s0 + (e0 - s0) * k / n, s0 + (e0 - s0) * (k + 1) / n))
    return res


def cues(words):
    out, cur = [], []
    for w, s, e in words:
        w = w.strip()
        if not w:
            continue
        if cur:
            text = " ".join(x[0] for x in cur)
            gap = s - cur[-1][2]
            punct = cur[-1][0][-1] in ".,?!"
            if (
                len(text) + 1 + len(w) > MAXC
                or gap > 0.6
                or (punct and len(text) > 8)
                or (s - cur[0][1] > 3.6)
            ):
                out.append(cur)
                cur = []
        cur.append((w, s, e))
    if cur:
        out.append(cur)
    res = []
    for c in out:
        res.append([c[0][1], c[-1][2] + 0.2, " ".join(x[0] for x in c)])
    for i in range(len(res) - 1):
        res[i][1] = min(res[i][1], res[i + 1][0] - 0.04)
        if res[i][1] - res[i][0] < 0.7:
            res[i][1] = min(res[i][0] + 0.7, res[i + 1][0] - 0.04)
    return res


def ts(t):
    ms = int(round(t * 1000))
    return f"{ms // 3600000:02d}:{ms // 60000 % 60:02d}:{ms // 1000 % 60:02d},{ms % 1000:03d}"


FONT = ImageFont.truetype("/System/Library/Fonts/HelveticaNeue.ttc", 26, index=10)


def render(text, path, top=False):
    im = Image.new("RGBA", (1280, STRIP_H), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    x0, t, r, b = d.textbbox((0, 0), text, font=FONT)
    w, h = r - x0, b - t
    x, y = (1280 - w) // 2, STRIP_H - 12 - h  # text baseline area near the strip bottom
    d.rounded_rectangle(
        (x - 14, y - 9, x + w + 14, y + h + 10), radius=8, fill=(8, 10, 14, 170)
    )
    d.text((x - x0, y - t), text, font=FONT, fill=(255, 255, 255, 255))
    full = Image.new("RGBA", (1280, 720), (0, 0, 0, 0))
    full.paste(im, (0, MARGIN - 10 if top else 720 - MARGIN - STRIP_H))
    full.save(path)


if __name__ == "__main__":
    words = json.load(open(sys.argv[1]))
    total = float(sys.argv[2])
    cs = [c for c in cues(fix_words(words)) if c[0] < total]
    SRT.write_text(
        "".join(
            f"{i + 1}\n{ts(s)} --> {ts(e)}\n{t}\n\n" for i, (s, e, t) in enumerate(cs)
        )
    )
    blank = OUT / "blank.png"
    Image.new("RGBA", (1280, 720), (0, 0, 0, 0)).save(blank)
    lines, t = [], 0.0
    for i, (s, e, text) in enumerate(cs):
        p = OUT / f"c{i:03d}.png"
        render(text, p, top=s < TOP_BEFORE)
        if s > t:
            lines += [f"file '{blank}'", f"duration {s - t:.3f}"]
        lines += [f"file '{p}'", f"duration {e - s:.3f}"]
        t = e
    lines += [
        f"file '{blank}'",
        f"duration {max(0.1, total - t):.3f}",
        f"file '{blank}'",
    ]
    (OUT / "list.txt").write_text("\n".join(lines) + "\n")
    subprocess.run(
        [
            "nice",
            "-n",
            "19",
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(OUT / "list.txt"),
            "-vf",
            "fps=30,format=rgba",
            "-c:v",
            "qtrle",
            "-t",
            f"{total:.3f}",
            str(OUT / "strip.mov"),
        ],
        check=True,
    )
    print(len(cs), "cues; longest", max(len(c[2]) for c in cs), "chars")
    for s, e, t in cs:
        print(f"{s:7.2f} {e:7.2f} {t}")
