"""Film v5 assets: the numbers the overlay prints, read from the recorded web run, plus the pop-up media.

Writes media/work5/facts5.json (every number from data/web-runs/<slug>/data.json, train.json and the Runway
ledger), media/work5/robot-clip.mp4 (the v3 Runway SO-101 experiment at 30 fps), copies the verified source
screenshots, and links media/work5 into the deck as film/deck/media/v5.

usage: .venv/bin/python scripts/film5_assets.py [slug]
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
WORK = REPO / "media" / "work5"


def main() -> None:
    slug = sys.argv[1] if len(sys.argv) > 1 else "put-a-red-block-into-a-bowl"
    run = REPO / "data" / "web-runs" / slug
    data = json.loads((run / "data.json").read_text())
    tr = json.loads((run / "train.json").read_text())
    def charged(job: Path) -> dict:
        evs = [json.loads(line) for line in job.read_text().splitlines() if line.strip()]
        return {(e["clip"], e["stage"]): e["cost"] for e in evs if e.get("type") == "runway" and e.get("status") == "SUCCEEDED"}

    jobs = sorted((run / "jobs").glob("*-footage-*.jsonl"))
    last = charged(jobs[-1])
    total = sum(sum(charged(j).values()) for j in jobs)
    card = tr["card"]
    facts = {
        "slug": slug,
        "task": data["task"],
        "clips": len(data["clips"]),
        "accepted": [c["clip_id"] for c in data["clips"] if c["accepted"]],
        "rejected": [
            {"clip": c["clip_id"], "reason": c["reason"]}
            for c in data["clips"]
            if not c["accepted"]
        ],
        "episodes": card["episodes"],
        "frames": card["frames"],
        "credits_total": total,
        "credits_last_take": sum(last.values()),
        "live_clips": sum(1 for (_, stage) in last if stage == "video"),
        "inspected": [r for i, r in enumerate(c["clip_id"] for c in data["clips"] if not c["accepted"]) if i in (0, 2)],
        "train_clips": card["clips"],
        "layers": [card["layers"][0][0], *[l2[1] for l2 in card["layers"]]],
        "chunk": card["chunk"],
        "params": card["params"],
        "steps": card["steps"],
        "train_seconds": card["train_seconds"],
        "device": card["device"],
        "final_l1": card["final_l1"],
        "eval_k": tr["eval"]["successes"],
        "eval_n": tr["eval"]["seeds"],
        "wilson95": tr["eval"]["wilson95"],
        "hero_seed": tr["films"]["success"]["seed"],
    }
    WORK.mkdir(parents=True, exist_ok=True)
    (WORK / "facts5.json").write_text(json.dumps(facts, indent=1))
    print(json.dumps(facts, indent=1))
    rc = WORK / "robot-clip.mp4"
    if not rc.exists():
        subprocess.run(
            [
                "ffmpeg",
                "-v",
                "error",
                "-y",
                "-i",
                str(REPO / "data/runs/robot-clip/r00.mp4"),
                "-vf",
                "fps=30,scale=1280:720",
                "-an",
                "-c:v",
                "libx264",
                "-crf",
                "16",
                "-g",
                "15",
                "-pix_fmt",
                "yuv420p",
                str(rc),
            ],
            check=True,
        )
    shutil.copytree(
        REPO / "film" / "v5" / "sources", WORK / "sources", dirs_exist_ok=True
    )
    link = REPO / "film" / "deck" / "media" / "v5"
    link.parent.mkdir(parents=True, exist_ok=True)
    if not link.exists():
        link.symlink_to(WORK)


if __name__ == "__main__":
    main()
