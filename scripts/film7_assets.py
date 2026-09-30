"""Film v7 assets: every number and every terminal line the overlay shows, read from the real runs.

- the site take (media/work7/live, the first run's sentence, footage replayed from the Runway cache: asserts 0 credits)
- the terminal sessions recorded verbatim by scripts/termrec.py (data/term/*.jsonl): turned into committed lines and
  in-progress lines (tqdm redraws with carriage returns) with their real wall-clock offsets; ANSI colour codes are
  stripped, nothing else is changed (the macOS objc duplicate-class warnings stay in)
- SmolVLA's eval (data/smolvla/understudy/eval.json), the MLP's (train.json), the PyBullet cross-check
- the rollout and cross-check films, the pop-up sources

Writes media/work7/{facts7.json, term/*.json, *.mp4, sources*/} and links media/work7 as film/deck/media/v7.

usage: .venv/bin/python scripts/film7_assets.py
"""

from __future__ import annotations

import json
import re
import shutil
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
WORK = REPO / "media" / "work7"
RUN = REPO / "data" / "web-runs" / "put-the-red-block-in-the-bowl"
import os  # noqa: E402

RUN_NAME = os.environ.get("SVLA_RUN", "understudy-1h")  # the SmolVLA run the film shows
ALT_NAME = "understudy" if RUN_NAME != "understudy" else None  # the earlier, shorter run (a second data point)
SVLA = REPO / "data" / "smolvla" / RUN_NAME
TEST = os.environ.get("FILM7_TEST") == "1"  # layout test only: stands in the MLP film for a missing SmolVLA hero
sys.path.insert(0, str(REPO / "src"))

from understudy.plan import mismatches, parse_task, prompt_version_for  # noqa: E402

ANSI = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]|\x1b\][^\x07]*\x07|\x1b[()][A-Z0-9]")


def term(src: Path) -> dict:
    """A termrec log -> {cmd, dur, lines: [[t, text]], partial: [[t, text]], loss: [[t, step, loss]]}."""
    rows = [json.loads(x) for x in src.read_text().splitlines() if x.strip()]
    head, tail = rows[0], rows[-1]
    lines, partial, loss = [], [], []
    cur = ""
    for r in rows[1:-1]:
        s = ANSI.sub("", r["d"]).replace("\r\n", "\n")
        for ch in re.split(r"(\n|\r)", s):
            if ch == "\n":
                lines.append([r["t"], cur])
                m = re.search(r"step:([\d.]+)(K?) .*?loss:([\d.]+)", cur)  # lerobot prints 1000 as "1K"
                if m:
                    loss.append([r["t"], round(float(m.group(1)) * (1000 if m.group(2) else 1)), float(m.group(3))])
                cur = ""
            elif ch == "\r":
                cur = ""
            elif ch:
                cur += ch
                partial.append([r["t"], cur])
    if cur:
        lines.append([tail["end"], cur])
    return {
        "cmd": head["cmd"],
        "start": head["start"],
        "dur": tail["end"],
        "exit": tail["exit"],
        "lines": lines,
        "partial": partial,
        "loss": loss,
    }


def main() -> None:
    WORK.mkdir(parents=True, exist_ok=True)
    (WORK / "term").mkdir(exist_ok=True)
    data = json.loads((RUN / "data.json").read_text())
    task = parse_task(data["task"])
    job = sorted((RUN / "jobs").glob("*-footage-*.jsonl"))[-1]
    evs = [json.loads(x) for x in job.read_text().splitlines() if x.strip()]
    rw = [e for e in evs if e.get("type") == "runway"]
    spent = sum(e.get("cost", 0) for e in rw if e.get("status") == "SUCCEEDED")
    assert spent == 0, f"the take spent {spent} Runway credits; v7 must spend none"
    rej = [c for c in data["clips"] if not c["accepted"]]
    ds_info = json.loads((RUN / "lerobot" / "meta" / "info.json").read_text())

    terms = {}
    for name, fn in (("smolvla", f"smolvla-{RUN_NAME}"), ("mlp", "mlp"), ("crosscheck", "crosscheck"), ("smolvla_eval", f"smolvla-{RUN_NAME}-eval")):
        f = REPO / "data" / "term" / f"{fn}.jsonl"
        if f.exists():
            terms[name] = term(f)
            (WORK / "term" / f"{name}.json").write_text(json.dumps(terms[name]))
    tr = json.loads((RUN / "train.json").read_text())
    ev = json.loads((SVLA / "checkpoints" / "last" / "eval.json").read_text())
    xc = json.loads((RUN / "crosscheck" / "crosscheck.json").read_text())
    xf = json.loads((RUN / "crosscheck" / "film.json").read_text())
    hp = SVLA / "checkpoints" / "last" / "hero.json"
    if TEST and not hp.exists():
        hero = {"seed": 0, "success": True, "frames": 319, "test_stand_in": True}
    else:
        hero = json.loads(hp.read_text())
    alt = None
    if ALT_NAME:
        ae = json.loads((REPO / "data" / "smolvla" / ALT_NAME / "checkpoints" / "last" / "eval.json").read_text())
        at_ = json.loads(REPO.joinpath("data", "term", f"smolvla-{ALT_NAME}.jsonl").read_text().splitlines()[-1])
        acfg = json.loads((REPO / "data" / "smolvla" / ALT_NAME / "checkpoints" / "last" / "pretrained_model" / "train_config.json").read_text())
        alt = {"steps": acfg["steps"], "wall_s": at_["end"], "eval_k": ae["successes"], "eval_n": ae["seeds"], "wilson95": ae["wilson95"]}
    tcfg = json.loads(
        (
            SVLA / "checkpoints" / "last" / "pretrained_model" / "train_config.json"
        ).read_text()
    )
    sl = terms["smolvla"]
    facts = {
        "task": data["task"],
        "prompt_version": prompt_version_for(task),
        "clips": len(data["clips"]),
        "accepted": [c["clip_id"] for c in data["clips"] if c["accepted"]],
        "rejected": [{"clip": c["clip_id"], "reason": c["reason"]} for c in rej],
        "fixes": {
            c["clip_id"]: [m.fix for m in mismatches([c["reason"]], task)] for c in rej
        },
        "credits_this_take": spent,
        "clips_from_cache": len(
            {
                e["clip"]
                for e in rw
                if e.get("status") == "CACHED" and e.get("stage") == "video"
            }
        ),
        "episodes": ds_info["total_episodes"],
        "frames": ds_info["total_frames"],
        "dataset_mb": round(
            sum(
                f.stat().st_size
                for f in (RUN / "lerobot").rglob("*")
                if f.is_file() and "images" not in f.parts
            )
            / 1e6,
            1,
        ),
        "smolvla": {
            "model": tcfg["policy"].get("pretrained_path") or "lerobot/smolvla_base",
            "steps": tcfg["steps"],
            "batch": tcfg["batch_size"],
            "wall_s": sl["dur"],
            "loss_first": sl["loss"][0][2],
            "loss_last": sl["loss"][-1][2],
            "device": "Apple M4 GPU (MPS)",
            "eval_k": ev["successes"],
            "eval_n": ev["seeds"],
            "wilson95": ev["wilson95"],
            "eval_s": ev["seconds"],
            "hero": hero,
            "earlier_run": alt,
        },
        "mlp": {
            "params": tr["card"]["params"],
            "steps": tr["card"]["steps"],
            "train_s": tr["card"]["train_seconds"],
            "device": tr["card"]["device"],
            "eval_k": tr["eval"]["successes"],
            "eval_n": tr["eval"]["seeds"],
            "wilson95": tr["eval"]["wilson95"],
            "hero_seed": tr["films"]["success"]["seed"],
            "cmd_s": terms["mlp"]["dur"] if "mlp" in terms else None,
        },
        "xcheck": {
            k: xc[k]
            for k in (
                "episodes",
                "mujoco_in_bowl",
                "bullet_in_bowl",
                "both",
                "agree",
                "seconds",
            )
        }
        | {
            "film_episode": xf["episode"],
            "film_clip": xf["clip"],
            "film_mujoco": xf["mujoco"]["success"],
            "film_bullet": xf["bullet"]["success"],
        },
        "per_seed": [
            [e["seed"], e["success"], m["success"]]
            for e, m in zip(ev["episodes"], tr["eval"]["episodes"])
        ],
    }
    (WORK / "facts7.json").write_text(json.dumps(facts, indent=1))
    print(json.dumps({k: v for k, v in facts.items() if k != "per_seed"}, indent=1))
    for src, dst in (
        (RUN / "media" / "policy_success_hero.mp4", "mlp_hero.mp4"),
        (RUN / "media" / "policy_success_hero.mp4" if TEST and not (SVLA / "checkpoints" / "last" / "hero.mp4").exists()
         else SVLA / "checkpoints" / "last" / "hero.mp4", "smolvla_hero.mp4"),
        (RUN / "crosscheck" / "film_mujoco.mp4", "xc_mujoco.mp4"),
        (RUN / "crosscheck" / "film_bullet.mp4", "xc_bullet.mp4"),
    ):
        shutil.copy(src, WORK / dst)
    shutil.copytree(
        REPO / "film" / "v5" / "sources", WORK / "sources", dirs_exist_ok=True
    )
    shutil.copytree(
        REPO / "film" / "v6" / "sources", WORK / "sources6", dirs_exist_ok=True
    )
    shutil.copytree(
        REPO / "film" / "v7" / "sources", WORK / "sources7", dirs_exist_ok=True
    )
    rc = REPO / "media" / "work5" / "robot-clip.mp4"
    if rc.exists():
        shutil.copy(rc, WORK / "robot-clip.mp4")
    link = REPO / "film" / "deck" / "media" / "v7"
    if not link.exists():
        link.symlink_to(WORK)


if __name__ == "__main__":
    main()
