"""Film v4 assets: every moving plate at a true 30 frames per second. No Runway credits.

v3 looked choppy for two reasons, measured with scripts/fps_probe.py: the deck was filmed with a real-time
screencast (about 7 unique frames a second), and the Runway clips are 24 fps, so 30 fps copies repeat every
fourth frame. v4 fixes both at the source: the deck is rendered frame by frame on a virtual clock
(film/tools/render-v4.mts), and this script turns every 24 fps Runway clip into real 30 fps frames with
motion-compensated interpolation (ffmpeg minterpolate), so every output frame is a different picture.

The tracking overlay is drawn again on the 30 fps frames: hand points and the block box are linearly
interpolated between the two measured 24 fps frames on either side (the measurements themselves are
data/runs/.../pose/v01.json, unchanged). The MuJoCo hero is v3's (one render per 30 Hz control step; the 2x
rollouts show every other step, still 30 different frames a second).

Writes film/deck/media/v4/ (gitignored with the rest of film/*/media):
  grid/vNN.mp4   640x360, 30 fps, the eight Runway clips
  full/vNN.mp4   1920x1080, 30 fps, the clips that fill the frame (v03 for the hook, v01)
  track-v01.mp4  1920x1080, 30 fps, v01 with the MediaPipe hand and the OpenCV block drawn on it
  robot-clip.mp4 1920x1080, 30 fps, the Runway clip of the SO-101 (data/runs/robot-clip/r00.mp4)
  hero.mp4       the v3 hero rollouts, re-encoded with short keyframe spacing for exact seeking

usage: .venv/bin/python scripts/film4_assets.py [--only grid,full,track,robot,hero]
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import cv2
import numpy as np

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))
from understudy.media import AMBER, HAND_EDGES, INK, LIME  # noqa: E402

RUN = REPO / "data" / "runs" / "put-the-red-block-in-the-bowl"
OUT = REPO / "film" / "deck" / "media" / "v4"
V3 = REPO / "film" / "deck" / "media" / "v3"
CLIPS = [f"v{k:02d}" for k in range(8)]
MI = "minterpolate=fps=30:mi_mode=mci:mc_mode=aobmc:me_mode=bidir:vsbmc=1"
# short keyframe spacing, no B-frames: the renderer seeks to every frame
ENC = [
    "-c:v",
    "libx264",
    "-preset",
    "slow",
    "-crf",
    "14",
    "-g",
    "10",
    "-bf",
    "0",
    "-pix_fmt",
    "yuv420p",
    "-an",
    "-movflags",
    "+faststart",
]


def ff(*args: str) -> None:
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", *args], check=True)


def src_fps(p: Path) -> float:
    r = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=r_frame_rate",
            "-of",
            "csv=p=0",
            str(p),
        ],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    a, b = r.split("/")
    return float(a) / float(b)


def to30(src: Path, out: Path, w: int, h: int) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    chain = (
        MI + "," if abs(src_fps(src) - 30) > 0.01 else "fps=30,"
    ) + f"scale={w}:{h}:flags=lanczos"
    ff("-i", str(src), "-vf", chain, *ENC, str(out))


def track() -> None:
    """v01 at 30 fps with what the pipeline measured, drawn per output frame."""
    raw = OUT / "full" / "v01.mp4"
    d = json.loads((RUN / "pose" / "v01.json").read_text())
    ev = json.loads((RUN / "results" / "v01.json").read_text())["events"]
    fr = d["frames"]
    s = 1920 / d["width"]
    cap = cv2.VideoCapture(str(raw))
    p = subprocess.Popen(
        [
            "ffmpeg",
            "-y",
            "-loglevel",
            "error",
            "-f",
            "rawvideo",
            "-pix_fmt",
            "bgr24",
            "-s",
            "1920x1080",
            "-r",
            "30",
            "-i",
            "-",
            *ENC,
            str(OUT / "track-v01.mp4"),
        ],
        stdin=subprocess.PIPE,
    )
    k = 0
    while True:
        ok, img = cap.read()
        if not ok:
            break
        u = k / 30 * d["fps"]  # position on the measured 24 fps timeline
        i0 = min(int(u), len(fr) - 1)
        i1 = min(i0 + 1, len(fr) - 1)
        a = u - i0 if i1 != i0 else 0.0

        def lerp(get):
            x0, x1 = get(fr[i0]), get(fr[i1])
            if x0 is None or x1 is None:
                return x0 if a < 0.5 else x1
            return np.asarray(x0, float) * (1 - a) + np.asarray(x1, float) * a

        b = lerp(lambda f: f["block"]["bbox"] if f.get("block") else None)
        if b is not None:
            x, y, bw, bh = (np.asarray(b) * s).round().astype(int)
            cv2.rectangle(img, (x, y), (x + bw, y + bh), AMBER, 3, cv2.LINE_AA)
        pts = lerp(lambda f: f["hand"]["pts"] if f.get("hand") else None)
        if pts is not None:
            q = (np.asarray(pts) * s).round().astype(int)
            for e0, e1 in HAND_EDGES:
                cv2.line(img, tuple(q[e0]), tuple(q[e1]), INK, 6, cv2.LINE_AA)
                cv2.line(img, tuple(q[e0]), tuple(q[e1]), LIME, 3, cv2.LINE_AA)
            for c in q:
                cv2.circle(img, tuple(c), 5, LIME, -1, cv2.LINE_AA)
            pc = lerp(lambda f: f["hand"]["pinch"] if f.get("hand") else None)
            cv2.circle(
                img,
                tuple((np.asarray(pc) * s).round().astype(int)),
                11,
                (255, 255, 255),
                3,
                cv2.LINE_AA,
            )
        i = round(u)
        label = ""
        if ev.get("ok"):
            if ev["t_grasp"] <= i < ev["t_release"]:
                label = "HELD"
            if abs(i - ev["t_grasp"]) <= 3:
                label = "GRASP"
            if abs(i - ev["t_release"]) <= 3:
                label = "RELEASE"
        if label:
            for col, th in ((INK, 7), ((255, 255, 255), 3)):
                cv2.putText(
                    img,
                    label,
                    (22, 1080 - 26),
                    cv2.FONT_HERSHEY_PLAIN,
                    3.0,
                    col,
                    th,
                    cv2.LINE_AA,
                )
        p.stdin.write(img.tobytes())
        k += 1
    p.stdin.close()
    assert p.wait() == 0
    cap.release()


def main() -> None:
    only = (
        sys.argv[sys.argv.index("--only") + 1].split(",")
        if "--only" in sys.argv
        else ["grid", "full", "track", "robot", "hero"]
    )
    OUT.mkdir(parents=True, exist_ok=True)
    if "grid" in only:
        for c in CLIPS:
            to30(RUN / "clips" / f"{c}.mp4", OUT / "grid" / f"{c}.mp4", 640, 360)
    if "full" in only:
        for c in ("v01", "v03"):
            to30(RUN / "clips" / f"{c}.mp4", OUT / "full" / f"{c}.mp4", 1920, 1080)
    if "track" in only:
        track()
    if "robot" in only:
        to30(
            REPO / "data" / "runs" / "robot-clip" / "r00.mp4",
            OUT / "robot-clip.mp4",
            1920,
            1080,
        )
    if "hero" in only:
        ff("-i", str(V3 / "hero.mp4"), *ENC, str(OUT / "hero.mp4"))
    print("wrote", sorted(str(p.relative_to(OUT)) for p in OUT.rglob("*.mp4")))


if __name__ == "__main__":
    main()
