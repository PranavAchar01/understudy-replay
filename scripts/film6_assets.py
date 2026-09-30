"""Film v6 assets: the numbers the overlay prints, read from the recorded web run (the first run's sentence,
replayed from the Runway cache), plus the pop-up media (v5's verified news sources + the PhyT2V paper).

Writes media/work6/facts6.json, the prompt fix the refine step makes for each rejected clip (the same call the
site's inspector makes), copies the source screenshots, and links media/work6 into the deck as film/deck/media/v6.

usage: .venv/bin/python scripts/film6_assets.py [slug]
"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
WORK = REPO / "media" / "work6"
sys.path.insert(0, str(REPO / "src"))

from understudy.plan import mismatches, parse_task, prompt_version_for  # noqa: E402


def main() -> None:
    slug = sys.argv[1] if len(sys.argv) > 1 else "put-the-red-block-in-the-bowl"
    run = REPO / "data" / "web-runs" / slug
    data = json.loads((run / "data.json").read_text())
    tr = json.loads((run / "train.json").read_text())
    task = parse_task(data["task"])
    job = sorted((run / "jobs").glob("*-footage-*.jsonl"))[-1]
    evs = [json.loads(line) for line in job.read_text().splitlines() if line.strip()]
    runway = [e for e in evs if e.get("type") == "runway"]
    spent = sum(e.get("cost", 0) for e in runway if e.get("status") == "SUCCEEDED")
    cached = sorted({e["clip"] for e in runway if e.get("status") == "CACHED" and e.get("stage") == "video"})
    card = tr["card"]
    rej = [c for c in data["clips"] if not c["accepted"]]
    facts = {
        "slug": slug,
        "task": data["task"],
        "prompt_version": prompt_version_for(task),
        "clips": len(data["clips"]),
        "accepted": [c["clip_id"] for c in data["clips"] if c["accepted"]],
        "rejected": [{"clip": c["clip_id"], "reason": c["reason"]} for c in rej],
        "fixes": {
            c["clip_id"]: [m.fix for m in mismatches([c["reason"]], task)] for c in rej
        },
        "credits_this_take": spent,
        "clips_from_cache": len(cached),
        "footage_job": job.name,
        "episodes": card["episodes"],
        "frames": card["frames"],
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
    assert spent == 0, f"this take spent {spent} Runway credits; v6 must spend none"
    WORK.mkdir(parents=True, exist_ok=True)
    (WORK / "facts6.json").write_text(json.dumps(facts, indent=1))
    print(json.dumps(facts, indent=1))
    shutil.copytree(REPO / "film" / "v5" / "sources", WORK / "sources", dirs_exist_ok=True)
    shutil.copytree(REPO / "film" / "v6" / "sources", WORK / "sources6", dirs_exist_ok=True)
    rc = REPO / "media" / "work5" / "robot-clip.mp4"
    if rc.exists():
        shutil.copy(rc, WORK / "robot-clip.mp4")
    link = REPO / "film" / "deck" / "media" / "v6"
    if not link.exists():
        link.symlink_to(WORK)


if __name__ == "__main__":
    main()
