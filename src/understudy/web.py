"""The Understudy web app: a small local server around the real pipeline.

  bin/understudy serve            -> http://127.0.0.1:8765

The page (site/) calls two stages, each run as a child process (webjob.py) that does the real work and
streams its progress back as Server-Sent Events:

  POST /api/footage {task, clips}  Runway generates the footage
  POST /api/data    {slug}         track, gate, retarget, write the LeRobot dataset
  POST /api/vla     {slug, clips?} the fine-tuned SmolVLA runs each accepted scenario in MuJoCo, filmed for the
                                   tiles (media/vla/<clip>.mp4 + .json); needs UNDERSTUDY_VLA_CKPT

A sentence whose run already has footage gets NEW clips on POST /api/footage (the next ids after the highest one),
never a regeneration of the clips it has (or of the ones cut from it).

and hands the dataset over: GET /api/runs/<slug>/dataset.zip. Training happens in a terminal on that dataset
(lerobot-train for SmolVLA, `bin/understudy train` for the small MLP baseline), not on the site.

One stage runs at a time (the machine also renders research). Heavy stages run at the lowest CPU priority.
Run outputs are served from data/web-runs/<slug>/.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import subprocess
import sys
import threading
import time
import uuid
from dataclasses import asdict
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import runway
from .generate import cost_per_clip, estimate_more, existing_clips, next_index
from .plan import Infeasible, parse_task

REPO = runway.REPO
SITE = REPO / "site"
RUNS = REPO / "data" / "web-runs"
RUNS.mkdir(parents=True, exist_ok=True)
CLIPS = int(os.environ.get("UNDERSTUDY_CLIPS", "5"))
LOW_PRIORITY = os.environ.get("UNDERSTUDY_LOW_PRIORITY", "1") == "1"
MAX_SCENARIOS = int(os.environ.get("UNDERSTUDY_MAX_SCENARIOS", "7"))  # default size of a run when adding clips
VLA_CKPT = os.environ.get("UNDERSTUDY_VLA_CKPT", "")  # SmolVLA checkpoint dir for the "vla" stage
VLA_DEVICE = os.environ.get("UNDERSTUDY_VLA_DEVICE", "auto")
VLA_CAMERAS = os.environ.get("UNDERSTUDY_VLA_CAMERAS", "front")
_HOME_LOCK = Path.home() / "helloworld" / ".heavy-lock"
HEAVY_LOCK = os.environ.get("UNDERSTUDY_HEAVY_LOCK", str(_HOME_LOCK) if _HOME_LOCK.parent.is_dir() else "")
if HEAVY_LOCK == "0":
    HEAVY_LOCK = ""

app = FastAPI(title="Understudy")


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:48]


class Job:
    def __init__(self, stage: str, run_slug: str, args: dict):
        self.id = uuid.uuid4().hex[:12]
        self.stage, self.slug = stage, run_slug
        self.events: list[dict] = []
        self.done = False
        self.log_path = (
            RUNS
            / run_slug
            / "jobs"
            / f"{time.strftime('%Y%m%d-%H%M%S')}-{stage}-{self.id}.jsonl"
        )
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        cmd = [sys.executable, "-u", "-m", "understudy.webjob", stage, json.dumps(args)]
        if LOW_PRIORITY and stage != "footage":
            cmd = ["nice", "-n", "19", "taskpolicy", "-b", *cmd]
        elif LOW_PRIORITY:
            cmd = ["nice", "-n", "19", *cmd]
        env = {**os.environ, "PYTHONPATH": str(REPO / "src"), "PYTHONUNBUFFERED": "1"}
        self.proc = subprocess.Popen(
            cmd,
            cwd=REPO,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        threading.Thread(target=self._pump, daemon=True).start()

    def _add(self, ev: dict) -> None:
        ev.setdefault("ts", round(time.time(), 3))
        self.events.append(ev)
        with self.log_path.open("a") as f:
            f.write(json.dumps(ev) + "\n")
        if ev.get("type") == "job_end":
            self.done = True  # the next stage may start while this process exits

    def _pump(self) -> None:
        assert self.proc.stdout is not None
        for line in self.proc.stdout:
            line = line.rstrip("\n")
            i = line.find("@@EV ")
            if i >= 0:
                try:
                    self._add(json.loads(line[i + 5 :]))
                    continue
                except json.JSONDecodeError:
                    pass
            if line.strip():
                self._add({"type": "log", "line": line[:400]})
        code = self.proc.wait()
        if not any(e.get("type") == "job_end" for e in self.events):
            self._add({"type": "job_end", "stage": self.stage, "ok": code == 0})
        self.done = True


JOBS: dict[str, Job] = {}


def _busy() -> Job | None:
    return next((j for j in JOBS.values() if not j.done), None)


def _start(stage: str, run_slug: str, args: dict) -> dict:
    b = _busy()
    if b:
        raise HTTPException(409, f"the {b.stage} stage is still running")
    j = Job(stage, run_slug, args)
    JOBS[j.id] = j
    return {"job": j.id, "slug": run_slug, "stage": stage}


class TaskIn(BaseModel):
    task: str
    clips: int | None = None
    refine: bool = False  # rewrite the prompts from this run's last rejections (PhyT2V Step 3)


class SlugIn(BaseModel):
    slug: str


class VlaIn(BaseModel):
    slug: str
    clips: list[str] | None = None


def _add_count(s: str, asked: int | None) -> int:
    """How many NEW clips a footage request for an existing run makes: as asked, else up to MAX_SCENARIOS."""
    have = len(existing_clips(RUNS / s))
    return max(1, min(int(asked or (MAX_SCENARIOS - have)), 8))


def _task_text(task: str) -> str:
    return re.sub(r"\s+", " ", task).strip()


@app.get("/api/budget")
def budget() -> dict:
    try:
        bal = runway.balance()
    except Exception as e:  # no key or no network: the page says so
        return {"balance": None, "error": str(e)[:200], "floor": runway.FLOOR_BALANCE}
    first, rest = cost_per_clip(True), cost_per_clip(False)
    n = CLIPS
    return {
        "balance": bal,
        "floor": runway.FLOOR_BALANCE,
        "clips": n,
        "cost_first": first,
        "cost_rest": rest,
        "cost_run": first + rest * (n - 1),
    }


@app.post("/api/plan")
def plan(body: TaskIn) -> dict:
    text = _task_text(body.task)
    try:
        t = parse_task(text)
    except Infeasible as e:
        return {"ok": False, "reason": str(e)}
    from .generate import estimate

    s = slug(t.text)
    have = existing_clips(RUNS / s) if (RUNS / s / "clips" / "v01.png").exists() else []
    if have:  # this sentence already has footage: the button adds new scenarios to it
        n = _add_count(s, body.clips)
        return {"ok": True, "task": t.text, "slug": s, "clips": n, "existing": have, **estimate_more(t, RUNS / s, n)}
    return {"ok": True, "task": t.text, "slug": s, "clips": CLIPS, "existing": [], **estimate(t, CLIPS)}


@app.post("/api/footage")
def footage(body: TaskIn) -> dict:
    text = _task_text(body.task)
    try:
        t = parse_task(text)
    except Infeasible as e:
        return JSONResponse({"ok": False, "reason": str(e)}, status_code=422)
    s = slug(t.text)
    start = next_index(RUNS / s) if (RUNS / s / "clips" / "v01.png").exists() else 0
    n = _add_count(s, body.clips) if start else max(1, min(int(body.clips or CLIPS), 8))
    if body.refine and not (RUNS / s / "data.json").exists():
        return JSONResponse({"ok": False, "reason": "no gate verdicts to refine from yet"}, status_code=422)
    _save_task(s, t.text)
    args = {"task": t.text, "run_dir": str(RUNS / s), "clips": n, "refine": body.refine, "start": start}
    ids = [f"v{i + 1:02d}" for i in range(start, start + n)]
    return _start("footage", s, args) | {"clips": n, "clip_ids": ids, "existing": existing_clips(RUNS / s) if start else []}


def _run_task(s: str) -> str:
    d = RUNS / s
    js = sorted((d / "clips").glob("v*.json"))
    if not js:
        raise HTTPException(404, "no footage for this run yet")
    task = (d / "task.txt").read_text().strip() if (d / "task.txt").exists() else None
    return task or s.replace("-", " ")


@app.post("/api/data")
def data(body: SlugIn) -> dict:
    task = _run_task(body.slug)
    return _start("data", body.slug, {"task": task, "run_dir": str(RUNS / body.slug)})


def _vla_state(run_slug: str) -> dict:
    from .vla_tiles import accepted_clips, films

    d = RUNS / run_slug
    acc = accepted_clips(d) if (d / "data.json").exists() or (d / "train.json").exists() else []
    have = films(d / "media" / "vla")
    job = next((j for j in JOBS.values() if j.stage == "vla" and j.slug == run_slug and not j.done), None)
    return {
        "accepted": acc,
        "films": {c: have[c] for c in acc if c in have},
        "missing": [c for c in acc if c not in have],
        "ckpt": bool(VLA_CKPT),
        "running": job.id if job else None,
        "command": f"PYTHONPATH=src python scripts/vla_tiles.py data/web-runs/{run_slug} --ckpt <smolvla checkpoint> --missing",
    }


@app.get("/api/runs/{run_slug}/vla")
def vla_state(run_slug: str) -> dict:
    """Which accepted scenarios have their SmolVLA film yet (media/vla/<clip>.json), and whether this server can
    make the missing ones (UNDERSTUDY_VLA_CKPT)."""
    if not re.fullmatch(r"[a-z0-9-]+", run_slug) or not (RUNS / run_slug).is_dir():
        raise HTTPException(404, "no such run")
    return _vla_state(run_slug)


@app.post("/api/vla")
def vla(body: VlaIn) -> dict:
    if not re.fullmatch(r"[a-z0-9-]+", body.slug) or not (RUNS / body.slug / "task.txt").exists():
        raise HTTPException(404, "no such run")
    if not VLA_CKPT:
        return JSONResponse({"ok": False, "reason": "no SmolVLA checkpoint on this server (set UNDERSTUDY_VLA_CKPT)"}, status_code=422)
    st = _vla_state(body.slug)
    clips = [c for c in (body.clips or st["missing"]) if c in st["accepted"]]
    if not clips:
        return JSONResponse({"ok": False, "reason": "every accepted scenario already has its film"}, status_code=422)
    args = {"run_dir": str(RUNS / body.slug), "ckpt": VLA_CKPT, "clips": clips, "device": VLA_DEVICE,
            "cameras": VLA_CAMERAS, "heavy_lock": HEAVY_LOCK}
    return _start("vla", body.slug, args) | {"clips": clips}


@app.get("/api/runs/{run_slug}/dataset.zip")
def dataset_zip(run_slug: str) -> FileResponse:
    """The run's LeRobot v3.0 dataset as one zip (data/, meta/, videos/ and the per-episode origins), built once."""
    import zipfile

    if not re.fullmatch(r"[a-z0-9-]+", run_slug):
        raise HTTPException(404, "no such run")
    root = RUNS / run_slug / "lerobot"
    if not (root / "understudy_episodes.json").exists():
        raise HTTPException(404, "no dataset for this run yet")
    name = "understudy_" + run_slug.replace("-", "_")
    out = RUNS / run_slug / f"{name}.zip"
    if not out.exists() or out.stat().st_mtime < (root / "understudy_episodes.json").stat().st_mtime:
        tmp = out.with_suffix(".part")
        with zipfile.ZipFile(tmp, "w", zipfile.ZIP_STORED) as z:
            for f in sorted(root.rglob("*")):
                if f.is_file() and "images" not in f.relative_to(root).parts:
                    z.write(f, Path(name) / f.relative_to(root))
        tmp.rename(out)
    return FileResponse(out, media_type="application/zip", filename=out.name)


@app.get("/api/runs/{run_slug}/dataset")
def dataset_info(run_slug: str) -> dict:
    """What the download holds, for the page: counts from the dataset's own meta/info.json."""
    if not re.fullmatch(r"[a-z0-9-]+", run_slug):
        raise HTTPException(404, "no such run")
    root = RUNS / run_slug / "lerobot"
    if not (root / "meta" / "info.json").exists():
        raise HTTPException(404, "no dataset for this run yet")
    info = json.loads((root / "meta" / "info.json").read_text())
    size = sum(f.stat().st_size for f in root.rglob("*") if f.is_file() and "images" not in f.relative_to(root).parts)
    return {
        "name": "understudy_" + run_slug.replace("-", "_"),
        "repo_id": json.loads((root / "understudy_episodes.json").read_text())["info"]["repo_id"],
        "episodes": info["total_episodes"],
        "frames": info["total_frames"],
        "fps": info["fps"],
        "codebase_version": info["codebase_version"],
        "robot_type": info.get("robot_type"),
        "features": [k for k in info["features"] if k not in ("timestamp", "frame_index", "episode_index", "index", "task_index")],
        "mb": round(size / 1e6, 1),
    }


@app.get("/api/runs/{run_slug}/refine")
def refine(run_slug: str) -> dict:
    """The prompt fixes the next take of this run would use: each rejection reason read as a mismatch and turned
    into a corrective rule (plan.refine_fixes, after PhyT2V). Text only: nothing is generated, no credits."""
    if not re.fullmatch(r"[a-z0-9-]+", run_slug) or not (RUNS / run_slug / "data.json").exists():
        raise HTTPException(404, "no gate verdicts for this run")
    from .generate import estimate
    from .plan import mismatches, refine_fixes

    t = parse_task(_run_task(run_slug))
    verdicts = json.loads((RUNS / run_slug / "data.json").read_text())["clips"]
    fixes = refine_fixes(verdicts, t)
    return {
        "method": "PhyT2V (Xue et al., CVPR 2025): rules + mismatches -> refined prompt",
        "clips": {
            v["clip_id"]: {
                "accepted": v["accepted"],
                "reason": v["reason"],
                "own": [asdict(m) for m in mismatches([v["reason"]], t)]
                if not v["accepted"]
                else [],
            }
            for v in verdicts
        },
        "fixes": [asdict(m) for m in fixes.get("*", [])],
        "next_take": estimate(t, len(verdicts), fixes),
    }


@app.get("/api/runs/{run_slug}/events")
def run_events(run_slug: str) -> list[dict]:
    """A saved run, to reopen it on the page: the events of its latest footage and data stages, in order (only the
    stages that finished). Each event is tagged with its job ("job": "footage" | "data"); its own "stage" field
    (a Runway call's "frame" / "video", a clip's "track" / "audit" / ...) is kept."""
    if not re.fullmatch(r"[a-z0-9-]+", run_slug):
        raise HTTPException(404, "no such run")
    jobs = RUNS / run_slug / "jobs"
    out: list[dict] = []

    def finished(p: Path) -> list[dict]:
        evs = [json.loads(line) for line in p.read_text().splitlines() if line.strip()]
        return evs if any(e.get("type") == "job_end" and e.get("ok") for e in evs) else []

    # every finished footage stage (clips can be added to a run), then the latest finished data stage
    foot = [finished(p) for p in sorted(jobs.glob("*-footage-*.jsonl"))]
    foot = [evs for evs in foot if evs]
    if not foot:
        return [{"type": "run", "slug": run_slug, "task": ""}]
    for evs in foot:
        out += [{**e, "job": "footage"} for e in evs]
    data = [evs for evs in (finished(p) for p in sorted(jobs.glob("*-data-*.jsonl"))) if evs]
    if data:
        out += [{**e, "job": "data"} for e in data[-1] if e.get("type") != "log"]
    task = (RUNS / run_slug / "task.txt").read_text().strip() if (RUNS / run_slug / "task.txt").exists() else ""
    return [{"type": "run", "slug": run_slug, "task": task}] + out


@app.get("/api/jobs/{job_id}/events")
async def events(job_id: str) -> StreamingResponse:
    j = JOBS.get(job_id)
    if not j:
        raise HTTPException(404, "no such job")

    async def stream():
        i = 0
        yield "retry: 1000\n\n"
        while True:
            while i < len(j.events):
                yield f"data: {json.dumps(j.events[i])}\n\n"
                i += 1
            if j.done and i >= len(j.events):
                return
            await asyncio.sleep(0.1)

    return StreamingResponse(
        stream(), media_type="text/event-stream", headers={"Cache-Control": "no-store"}
    )


def _save_task(s: str, text: str) -> None:
    """The data stage needs the exact sentence, not the slug, so it is kept next to the run."""
    d = RUNS / s
    d.mkdir(parents=True, exist_ok=True)
    (d / "task.txt").write_text(text + "\n")


@app.get("/")
def index() -> FileResponse:
    return FileResponse(SITE / "index.html", headers={"Cache-Control": "no-store"})


app.mount("/runs", StaticFiles(directory=RUNS), name="runs")
app.mount("/", StaticFiles(directory=SITE, html=True), name="site")
