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
# the Replay-style site (deploy-v2, built by site-v2/build-deploy.sh); UNDERSTUDY_SITE=site serves the older page
SITE = REPO / os.environ.get("UNDERSTUDY_SITE", "deploy-v2" if (REPO / "deploy-v2" / "index.html").is_file() else "site")
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
        if LOW_PRIORITY and stage not in ("footage", "train"):  # train is remote GPU work: no background QoS
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


def _busy(stage: str = "") -> Job | None:
    """The running job that blocks a new one of this stage. Training runs on a rented GPU, so it only blocks
    another training job, and local stages never wait for it."""
    if stage == "train":
        return next((j for j in JOBS.values() if not j.done and j.stage == "train"), None)
    return next((j for j in JOBS.values() if not j.done and j.stage != "train"), None)


def _start(stage: str, run_slug: str, args: dict) -> dict:
    b = _busy(stage)
    if b:
        raise HTTPException(409, f"the {b.stage} stage is still running")
    j = Job(stage, run_slug, args)
    JOBS[j.id] = j
    return {"job": j.id, "slug": run_slug, "stage": stage}


class TaskIn(BaseModel):
    task: str
    clips: int | None = None
    refine: bool = False  # rewrite the prompts from this run's last rejections (PhyT2V Step 3)
    router: str | None = None  # a Model Router slug; omitted = chosen from the task text (route.py); "direct" = gen4_turbo
    live: bool = False  # a live/urgent request: an easy task routes to demo-fast instead of demo-cheap
    max_credits: float | None = None  # refuse before spending if the dry-run estimate for all clips is above this


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
    if body.router and not re.fullmatch(r"[a-z][a-z0-9_-]{0,63}", body.router):
        return JSONResponse({"ok": False, "reason": "not a router slug"}, status_code=422)
    decision = None
    if body.router is None:
        from .route import choose

        decision = choose(t.text, live=body.live)
        router = decision["router"]
    else:
        router = None if body.router == "direct" else body.router
    estimate = None
    if router:
        from .generate import base_frame
        from .plan import variants

        frame = base_frame(RUNS / s) if start else base_frame(RUNS / "put-the-red-block-in-the-bowl")
        try:
            d = runway.router_dry_run(runway.router_body(router, variants(t, start + 1)[start].video_prompt, frame))
            per = float((d.get("estimatedCost") or {}).get("credits") or 0)
            estimate = {"model": d.get("model"), "per_clip_video": per,
                        "total": per * n + (2 * n if start else 5 + 2 * (n - 1))}
        except Exception as e:
            estimate = {"error": str(e)[:200]}
    if body.max_credits is not None and (estimate is None or "total" not in estimate or estimate["total"] > body.max_credits):
        return JSONResponse({"ok": False, "reason": f"estimate {estimate} is over max_credits {body.max_credits}",
                             "estimate": estimate}, status_code=422)
    args = {"task": t.text, "run_dir": str(RUNS / s), "clips": n, "refine": body.refine, "start": start,
            "router": router}
    ids = [f"v{i + 1:02d}" for i in range(start, start + n)]
    return _start("footage", s, args) | {"clips": n, "clip_ids": ids, "existing": existing_clips(RUNS / s) if start else [],
                                         "router": router, "route": decision, "estimate": estimate}


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
    stages that finished)."""
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
        out += [{**e, "stage": "footage"} for e in evs]
    data = [evs for evs in (finished(p) for p in sorted(jobs.glob("*-data-*.jsonl"))) if evs]
    if data:
        out += [{**e, "stage": "data"} for e in data[-1] if e.get("type") != "log"]
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


# ---------- Model Router ----------
ROUTER_DRYRUNS = REPO / "data" / "router-dryruns.json"
DEMO_ROUTERS = ("demo-cheap", "demo-fast", "demo-best")
USD_PER_CREDIT = 0.01
TRAINER = Path(os.environ.get("UNDERSTUDY_TRAINER", str(Path.home() / "helloworld" / "so101" / "train_vla.sh")))


class DryIn(BaseModel):
    task: str
    routers: list[str] | None = None


@app.get("/api/routers")
def list_routers() -> dict:
    """The account's Model Router configs (slug, optimizeFor, price ceiling)."""
    try:
        rs = runway.routers()
    except Exception as e:
        return {"routers": [{"slug": r} for r in DEMO_ROUTERS], "error": str(e)[:200]}
    out = [
        {
            "slug": r["slug"],
            "description": r.get("description"),
            "optimize_for": (r.get("settings") or {}).get("optimizeFor"),
            "max_credits": ((r.get("settings") or {}).get("maxCreditsPerGeneration") or {}).get("video"),
            "fallback": ((r.get("settings") or {}).get("fallback") or {}).get("onCapacity"),
        }
        for r in rs
    ]
    order = {s: i for i, s in enumerate(DEMO_ROUTERS)}
    out.sort(key=lambda r: order.get(r["slug"], 99))
    return {"routers": out}


@app.post("/api/router/dryrun")
def router_dryrun(body: DryIn) -> dict:
    """Free: what each router would pick for the next clip of this sentence (model, provider, estimated credits).
    No task is created and nothing is billed. The reference image is the run's base frame (clips/v01.png), or the
    first run's when this sentence has no footage yet (the pick depends on the input's shape, not its pixels)."""
    from .generate import base_frame
    from .plan import variants

    text = _task_text(body.task)
    try:
        t = parse_task(text)
    except Infeasible as e:
        return JSONResponse({"ok": False, "reason": str(e)}, status_code=422)
    s = slug(t.text)
    frame = base_frame(RUNS / s)
    if not frame.exists():
        frame = base_frame(RUNS / "put-the-red-block-in-the-bowl")
    i = next_index(RUNS / s) if (RUNS / s / "clips" / "v01.png").exists() else 0
    v = variants(t, i + 1)[i]
    from concurrent.futures import ThreadPoolExecutor

    t0 = time.time()
    body_img = runway.image_data_uri(frame)

    def pick(r: str) -> dict:
        try:
            b = runway.router_body(r, v.video_prompt, frame)
            b["input"]["referenceImages"][0]["uri"] = body_img
            d = runway.router_dry_run(b)
            cr = (d.get("estimatedCost") or {}).get("credits")
            return {
                "router": r, "model": d.get("model"), "provider": d.get("provider"),
                "optimize_for": (d.get("resolvedSettings") or {}).get("optimizeFor"),
                "price_ceiling": (d.get("resolvedSettings") or {}).get("priceCeiling"),
                "resolved": d.get("resolvedInput"), "estimated_credits": cr,
                "usd": round(cr * USD_PER_CREDIT, 2) if cr is not None else None,
            }
        except Exception as e:
            return {"router": r, "error": str(e)[:240]}

    names = [r for r in (body.routers or list(DEMO_ROUTERS)) if re.fullmatch(r"[a-z][a-z0-9_-]{0,63}", r)]
    with ThreadPoolExecutor(max_workers=max(1, len(names))) as pool:
        picks = list(pool.map(pick, names))
    return {"ok": True, "task": t.text, "slug": s, "clip": v.clip_id, "picks": picks,
            "seconds": round(time.time() - t0, 2), "free": True}


class RouteIn(BaseModel):
    task: str
    claude: bool = False  # refine the rubric with the headless Claude CLI (falls back after 10 s)
    live: bool = False  # live/urgent: an easy task routes to demo-fast


@app.post("/api/route")
def route_task(body: RouteIn) -> dict:
    """The router this task's footage goes through, from the task text (src/understudy/route.py rubric), with
    Runway's free dry run on that router: the model it would pick and the estimated credits."""
    from .generate import base_frame
    from .plan import variants
    from .route import choose

    text = _task_text(body.task)
    feasible, reason, t = True, None, None
    try:
        t = parse_task(text)
    except Infeasible as e:
        feasible, reason = False, str(e)
    s = slug(t.text if t else text)
    have = (RUNS / s / "clips" / "v01.png").exists()
    dec = choose(t.text if t else text, live=body.live, use_claude=body.claude)
    frame = base_frame(RUNS / s) if have else base_frame(RUNS / "put-the-red-block-in-the-bowl")
    prompt = text
    if t:
        i = next_index(RUNS / s) if have else 0
        prompt = variants(t, i + 1)[i].video_prompt
    dry = None
    try:
        d = runway.router_dry_run(runway.router_body(dec["router"], prompt, frame))
        dry = {"model": d.get("model"), "provider": d.get("provider"),
               "credits": (d.get("estimatedCost") or {}).get("credits"),
               "optimize_for": (d.get("resolvedSettings") or {}).get("optimizeFor"),
               "resolved": d.get("resolvedInput")}
    except Exception as e:
        dry = {"error": str(e)[:240]}
    return {"task": text, "slug": s, "router": dec["router"], "reasons": dec["reasons"], "source": dec["source"],
            "feasible": feasible, "infeasible_reason": reason, "dryRun": dry,
            "first_frame": f"/runs/{s if have else 'put-the-red-block-in-the-bowl'}/clips/v01.png"}


@app.get("/api/runs/{run_slug}/routing")
def run_routing(run_slug: str) -> dict:
    """Per clip: the router's pick and cost (clips/<id>.routing.json) and the physics verdict (results/<id>.json),
    plus the totals the meter shows."""
    if not re.fullmatch(r"[a-z0-9-]+", run_slug) or not (RUNS / run_slug).is_dir():
        raise HTTPException(404, "no such run")
    d = RUNS / run_slug
    clips = {}
    for p in sorted((d / "clips").glob("v*.routing.json")):
        cid = p.name.split(".")[0]
        r = json.loads(p.read_text())
        res = d / "results" / f"{cid}.json"
        verdict = None
        if res.exists():
            rj = json.loads(res.read_text())
            verdict = {"accepted": rj["accepted"], "reason": rj["reason"]}
        clips[cid] = {k: r.get(k) for k in ("router", "model", "provider", "optimize_for", "estimated_credits",
                                            "realized_credits", "seconds", "cached")} | {"verdict": verdict}
    return {"clips": clips}


@app.get("/api/runs/{run_slug}/router_bench")
def router_bench(run_slug: str) -> dict:
    if not re.fullmatch(r"[a-z0-9-]+", run_slug) or not (RUNS / run_slug / "router_bench.json").exists():
        raise HTTPException(404, "no router bench for this run")
    b = json.loads((RUNS / run_slug / "router_bench.json").read_text())
    return {k: b.get(k) for k in ("slug", "task", "routers", "clips_per_router", "budget", "started", "generated",
                                  "judged", "updated", "credits_spent_balance", "method", "table", "clips", "frames")}


@app.get("/api/runs/{run_slug}/tiles")
def run_tiles(run_slug: str) -> dict:
    """Every clip of the run as one tile: footage, first frame, routing (router, model, credits, seconds), the
    physics verdict, and the SmolVLA film if one exists (media/vla/<clip>.mp4 + .json)."""
    if not re.fullmatch(r"[a-z0-9-]+", run_slug) or not (RUNS / run_slug).is_dir():
        raise HTTPException(404, "no such run")
    d = RUNS / run_slug
    base = f"/runs/{run_slug}/"
    tiles = []
    for p in sorted((d / "clips").glob("v[0-9][0-9].json")):
        cid = p.stem
        meta = json.loads(p.read_text())
        rt = d / "clips" / f"{cid}.routing.json"
        routing = None
        if rt.exists():
            r = json.loads(rt.read_text())
            routing = {k: r.get(k) for k in ("router", "model", "provider", "optimize_for", "estimated_credits",
                                             "realized_credits", "seconds", "cached")}
        res = d / "results" / f"{cid}.json"
        verdict = None
        if res.exists():
            rj = json.loads(res.read_text())
            verdict = {"accepted": rj["accepted"], "reason": rj["reason"],
                       "gates_total": len(rj["gates"]),
                       "gates_passed": sum(1 for g in rj["gates"] if g["passed"] is True)}
        vj = d / "media" / "vla" / f"{cid}.json"
        vla_film = None
        if vj.exists() and (d / "media" / "vla" / f"{cid}.mp4").exists():
            vla_film = json.loads(vj.read_text()) | {"video": base + f"media/vla/{cid}.mp4"}
        tiles.append({
            "clip": cid,
            "footage": base + f"clips/{cid}.mp4" if (d / "clips" / f"{cid}.mp4").exists() else None,
            "first_frame": base + f"clips/{cid}.png" if (d / "clips" / f"{cid}.png").exists() else None,
            "video_model": meta.get("video_model"),
            "variant": meta.get("variant", cid),
            "routing": routing,
            "verdict": verdict,
            "vla": vla_film,
            "skeleton": base + f"media/{cid}_skeleton.mp4" if (d / "media" / f"{cid}_skeleton.mp4").exists() else None,
        })
    routed = [t["routing"] for t in tiles if t["routing"] and not t["routing"].get("cached")]
    credits = sum(float(r.get("realized_credits") or 0) for r in routed)
    acc = sum(1 for t in tiles if t["verdict"] and t["verdict"]["accepted"])
    return {
        "slug": run_slug,
        "task": (d / "task.txt").read_text().strip() if (d / "task.txt").exists() else "",
        "tiles": tiles,
        "totals": {
            "clips": len(tiles), "accepted": acc,
            "routed_credits": credits, "routed_usd": round(credits * USD_PER_CREDIT, 2),
            "routed_seconds": round(sum(float(r.get("seconds") or 0) for r in routed), 1),
            "credits_per_accepted": round(credits / acc, 1) if acc and credits else None,
        },
    }


class TrainIn(BaseModel):
    slug: str
    steps: int = 3000
    dataset: str | None = None  # a LeRobot dataset root under data/ (default: the run's lerobot/)


@app.get("/api/trainer")
def trainer() -> dict:
    job = next((j for j in JOBS.values() if j.stage == "train" and not j.done), None)
    return {"connected": TRAINER.is_file(), "script": str(TRAINER), "running": job.id if job else None}


@app.post("/api/train")
def train(body: TrainIn) -> dict:
    """Train SmolVLA on this run's LeRobot dataset on a rented GPU: the trainer script streams its progress."""
    if not re.fullmatch(r"[a-z0-9-]+", body.slug) or not (RUNS / body.slug).is_dir():
        raise HTTPException(404, "no such run")
    if not TRAINER.is_file():
        return JSONResponse({"ok": False, "reason": "GPU trainer not connected"}, status_code=422)
    root = RUNS / body.slug / "lerobot"
    if body.dataset:
        root = (REPO / body.dataset).resolve()
        if not root.is_relative_to((REPO / "data").resolve()):
            raise HTTPException(422, "dataset must be under data/")
    if not (root / "meta" / "info.json").exists():
        return JSONResponse({"ok": False, "reason": "no LeRobot dataset for this run yet"}, status_code=422)
    steps = max(100, min(int(body.steps), 100_000))
    return _start("train", body.slug, {"script": str(TRAINER), "root": str(root), "steps": steps,
                                       "run_dir": str(RUNS / body.slug)})


def _save_task(s: str, text: str) -> None:
    """The data stage needs the exact sentence, not the slug, so it is kept next to the run."""
    d = RUNS / s
    d.mkdir(parents=True, exist_ok=True)
    (d / "task.txt").write_text(text + "\n")


@app.get("/")
def index() -> FileResponse:
    return FileResponse(SITE / "index.html", headers={"Cache-Control": "no-store"})


@app.get("/runs/{path:path}")
def run_file(path: str) -> FileResponse:
    """Run outputs: this machine's runs first, then the ones the built site ships (library tiles trained elsewhere)."""
    for root in (RUNS, SITE / "runs"):
        f = (root / path).resolve()
        if f.is_relative_to(root.resolve()) and f.is_file():
            return FileResponse(f)
    raise HTTPException(404, "not found")


app.mount("/", StaticFiles(directory=SITE, html=True), name="site")
