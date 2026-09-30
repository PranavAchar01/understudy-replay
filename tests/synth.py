"""A synthetic pose JSON (same schema as src/pose/extract.py) for a clean pick-and-place, plus ways to break it."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

FPS, N = 24.0, 120
B0 = np.array([500.0, 440.0])
B1 = np.array([860.0, 420.0])
BPX = 126.0
OFF = np.array([0.0, -45.0])  # pinch point sits above the block centre when holding it


def keyframes():
    # (frame, pinch x, pinch y)
    return [
        (0, 500, 300),
        (24, 500, 395),
        (30, 500, 395),
        (40, 500, 200),
        (58, 860, 200),
        (66, 860, 375),
        (74, 860, 375),
        (90, 900, 200),
        (119, 950, 120),
    ]


def clean(n=N):
    kf = keyframes()
    f = np.array([k[0] for k in kf])
    px = np.interp(np.arange(n), f, [k[1] for k in kf])
    py = np.interp(np.arange(n), f, [k[2] for k in kf])
    pinch = np.stack([px, py], 1)
    frames = []
    for i in range(n):
        if i < 31:
            b = B0
        elif i < 70:
            b = pinch[i] - OFF
            if i >= 66:
                b = B1
        else:
            b = B1
        frames.append(
            {
                "hand": {
                    "pts": [pinch[i].tolist()] * 21,
                    "score": 0.98,
                    "label": "Left",
                    "aperture": 0.2,
                    "pinch": pinch[i].tolist(),
                    "aperture_2d": 0.2,
                    "hand_px": 80.0,
                },
                "arm": {"wrist": [pinch[i][0] - 60, pinch[i][1] - 40, 0.9]},
                "block": {
                    "c": b.tolist(),
                    "area": int(BPX * BPX),
                    "bbox": [0, 0, 1, 1],
                    "second_ratio": 0.0,
                },
            }
        )
    return {
        "clip": "synth.mp4",
        "extractor": "synthetic",
        "fps": FPS,
        "width": 1280,
        "height": 720,
        "n_frames": n,
        "frames": frames,
    }


def write(d: dict, path: Path) -> Path:
    path.write_text(json.dumps(d))
    return path


AUDIT_OK = {
    "available": True,
    "red_blocks_first": 1,
    "bowls_first": 1,
    "hands_first": 1,
    "bowl_bbox_first": [760, 330, 960, 470],
    "block_in_bowl_last": True,
    "red_blocks_last": 1,
}
