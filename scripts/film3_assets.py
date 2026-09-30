"""Film v3 assets: the plates and the facts the v3 deck (film/deck/v3.html) plays. No Runway credits.

Writes into film/deck/media/v3/ (gitignored with the rest of film/*/media):
  thumbs/vNN.jpg    first frame of each Runway clip, for the file cards
  robot-clip.mp4    the one Runway clip of the SO-101 itself (data/runs/robot-clip/r00.mp4), 1920x1080 30 fps
  hero.mp4          the trained policy in MuJoCo, full frame: rollout 1 at 1x, rollouts 2 and 3 at 2x
  facts3.json       every number and log line the deck shows, read from the run, the log and the policy code

Log lines are copied verbatim from data/run2.log (the final run). The model facts come from the MLPChunk module
itself (layer shapes, parameter count) and policy/train.json (steps, samples, seconds).

usage: .venv/bin/python scripts/film3_assets.py [--only facts,thumbs,robot,hero]
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(REPO / "scripts"))

RUN = REPO / "data" / "runs" / "put-the-red-block-in-the-bowl"
OUT = REPO / "film" / "deck" / "media" / "v3"
LOG = REPO / "data" / "run2.log"
HERO_SEEDS = (
    10001,
    10003,
    10009,
)  # three successful eval seeds, spread across the region
TRIM_HEAD = 45  # frames of the reach from home that are cut from each rollout


def ff(*args: str) -> None:
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", *args], check=True)


def facts() -> dict:
    import torch

    from understudy.pipeline import JITTER
    from understudy.policy import CHUNK, MLPChunk
    from understudy.scene import BOWL_R, TARGET_XY

    log = LOG.read_text().splitlines()
    pick = lambda tag: [ln for ln in log if ln.startswith(tag)]  # noqa: E731
    gates = pick("[gates]")
    rejected = []
    for ln in gates:
        m = re.match(r"\[gates\] (v\d\d): REJECTED \((.*)\)$", ln)
        if m:
            rejected.append({"clip": m.group(1), "line": ln, "why": m.group(2)})
    run = json.loads((RUN / "run.json").read_text())
    train = json.loads((RUN / "policy" / "train.json").read_text())
    eps = json.loads((RUN / "lerobot" / "understudy_episodes.json").read_text())[
        "episodes"
    ]

    model = MLPChunk()
    layers = [
        [m.in_features, m.out_features]
        for m in model.net
        if isinstance(m, torch.nn.Linear)
    ]
    params = sum(p.numel() for p in model.parameters())
    assert params == train["params"], (params, train["params"])

    # the joint angles of the first accepted clip, as written to the dataset (LeRobot units, degrees; gripper 0-100)
    df = pd.read_parquet(RUN / "lerobot" / "data" / "chunk-000" / "file-000.parquet")
    e0 = df[df.episode_index == 0]
    act = np.stack(e0["action"].to_numpy())
    step = max(1, len(act) // 150)
    cpu = subprocess.run(
        ["sysctl", "-n", "machdep.cpu.brand_string"], capture_output=True, text=True
    ).stdout.strip()
    return {
        "log": {
            "run": pick("[run] 8 clips"),
            "gates": gates,
            "episodes": pick("[episodes]"),
            "train": pick("[train]"),
            "eval": pick("[eval]"),
        },
        "rejected": rejected,
        "accepted": [c["clip_id"] for c in run["clips"] if c["accepted"]],
        "clips": [c["clip_id"] for c in run["clips"]],
        "reanchor": run["reanchor"],
        "dataset": {
            k: run["dataset"][k]
            for k in ("episodes", "frames", "fps", "codebase_version")
        },
        "episodes": [
            {"clip": e["clip"], "kind": e["kind"], "xy": e["cube_xy"]} for e in eps
        ],
        "joints": {
            "names": [
                "shoulder_pan",
                "shoulder_lift",
                "elbow_flex",
                "wrist_flex",
                "wrist_roll",
                "gripper",
            ],
            "clip": eps[0]["clip"],
            "frames": int(len(act)),
            "values": np.round(act[::step], 2).tolist(),
        },
        "loss": [
            {"step": int(m.group(1)), "l1": float(m.group(2))}
            for m in (
                re.match(r"\[train\] step (\d+) l1 ([\d.]+)", ln)
                for ln in pick("[train]")
            )
        ],
        "model": {
            "kind": "MLP with action chunking (MLPChunk, src/understudy/policy.py)",
            "layers": layers,
            "activation": "GELU",
            "params": params,
            "obs": "6 joint positions + cube xyz (9 numbers, no camera)",
            "chunk": CHUNK,
            "act_dim": 6,
            "loss": "L1",
            "optimizer": "AdamW, lr 1e-3, cosine",
            "batch": 256,
            **train,
            "cpu": cpu,
        },
        "eval": {k: run["eval"][k] for k in ("seeds", "successes", "wilson95")},
        "hero_seeds": list(HERO_SEEDS),
        "bowl": {"xy": list(TARGET_XY), "r": BOWL_R},
        "jitter": list(JITTER),
    }


def thumbs() -> None:
    (OUT / "thumbs").mkdir(parents=True, exist_ok=True)
    for png in sorted((RUN / "clips").glob("v*.png")):
        ff(
            "-i",
            str(png),
            "-vf",
            "scale=480:270:flags=lanczos",
            "-q:v",
            "3",
            str(OUT / "thumbs" / f"{png.stem}.jpg"),
        )


def grid() -> None:
    """Each Runway clip at cell size, so the page decodes eight small videos instead of eight 720p ones."""
    (OUT / "grid").mkdir(parents=True, exist_ok=True)
    for mp4 in sorted((RUN / "clips").glob("v*.mp4")):
        ff("-i", str(mp4), "-vf", "fps=30,scale=640:360:flags=lanczos", "-an", "-c:v", "libx264", "-crf", "18",
           "-pix_fmt", "yuv420p", str(OUT / "grid" / mp4.name))


def robot() -> None:
    src = REPO / "data" / "runs" / "robot-clip" / "r00.mp4"
    ff(
        "-i",
        str(src),
        "-vf",
        "fps=30,scale=1920:1080:flags=lanczos",
        "-an",
        "-c:v",
        "libx264",
        "-crf",
        "16",
        "-pix_fmt",
        "yuv420p",
        str(OUT / "robot-clip.mp4"),
    )


def hero_cam():
    """A closer free camera than the dataset's "front" camera, on the same side, so the arm fills the frame."""
    import mujoco

    c = mujoco.MjvCamera()
    c.type = mujoco.mjtCamera.mjCAMERA_FREE
    c.lookat[:] = (0.19, -0.035, 0.09)
    c.distance, c.azimuth, c.elevation = 0.58, -155.0, -24.0
    return c


def hero() -> dict:
    from film2_assets import Cam, write

    from understudy.policy import Runner, rollout
    from understudy.scene import load

    run = json.loads((RUN / "run.json").read_text())
    by_seed = {e["seed"]: e for e in run["eval"]["episodes"]}
    sc = load(task="pick")
    runner = Runner(RUN / "policy")
    # the evaluation's exact start positions (run.json stores them rounded to 0.1 mm): same anchors, same rng
    from understudy.pipeline import JITTER
    from understudy.track import find_events, load_track, to_robot

    anchors = []
    for c in run["clips"]:
        if c["accepted"]:
            res_c = json.loads((RUN / "results" / f"{c['clip_id']}.json").read_text())
            tr = load_track(RUN / "pose" / f"{c['clip_id']}.json")
            anchors.append(to_robot(tr, find_events(tr), res_c["bowl_u"]).cube_start[:2])
    frames, segs = [], []
    for k, seed in enumerate(HERO_SEEDS):
        ep = by_seed[seed]
        assert ep["success"], seed
        s = seed - 10_000
        xy = anchors[s % len(anchors)] + np.random.default_rng(seed).uniform(-np.array(JITTER), JITTER)
        assert np.allclose(xy.round(4), ep["cube_xy"]), (xy, ep["cube_xy"])
        cam = Cam(sc, 1920, 1080, free=hero_cam())
        res = rollout(sc, runner, xy, on_frame=cam.frame)
        cam.close()
        # the film shows exactly what the evaluation scored: same seed, same start, same outcome
        assert res["success"] and res["frames"] == ep["frames"], (seed, res, ep)
        fr = cam.frames[TRIM_HEAD:]
        speed = 1 if k == 0 else 2
        fr = fr[::speed]
        segs.append(
            {
                "seed": seed,
                "cube_xy": ep["cube_xy"],
                "speed": speed,
                "start_s": len(frames) / 30,
                "seconds": len(fr) / 30,
            }
        )
        frames += fr
    write(OUT / "hero.mp4", frames)
    return {"segments": segs, "seconds": len(frames) / 30}


def main() -> None:
    only = (
        sys.argv[sys.argv.index("--only") + 1].split(",")
        if "--only" in sys.argv
        else ["facts", "thumbs", "robot", "hero"]
    )
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / "facts3.json"
    out = json.loads(path.read_text()) if path.exists() else {}
    if "facts" in only:
        out.update(facts())
    if "thumbs" in only:
        thumbs()
        grid()
    if "robot" in only:
        robot()
    if "hero" in only:
        out["hero"] = hero()
    path.write_text(json.dumps(out, indent=1))
    print(
        json.dumps(
            {
                k: v
                for k, v in out.items()
                if k in ("model", "hero", "loss", "rejected")
            },
            indent=1,
        )
    )


if __name__ == "__main__":
    main()
