"""Film v2 assets: every plate the Player Two style cut needs, rendered from the run (no Runway credits).

Writes
  film/app/media/demo/understudy/ep-NN.mp4 + .jpg   one tile per dataset episode (44), in the Player Two clip layout:
                                                    the Runway lead (MediaPipe + OpenCV overlay) on the left 38%,
                                                    the SO-101 MuJoCo replay on the right, synced by the replay plan
  film/app/media/demo/manifest.json                 the run, in the player-two-site manifest format
  film/deck/media/*.mp4                             B-roll plates (Runway grid, overlay, model, IK path, pass/fail,
                                                    policy rollout)
  media/work2/facts.json                            every number the deck captions use, read from the run and model

The 44 episodes are rebuilt exactly as scripts/pipeline.py made them (same demos, same rng for the re-anchored
copies) and checked against lerobot/understudy_episodes.json before anything is drawn.

Usage: .venv/bin/python scripts/film2_assets.py [--only tiles,deck]
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import mujoco
import numpy as np
from PIL import Image

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from understudy import gates as G
from understudy import media
from understudy.pipeline import JITTER
from understudy.retarget import DT, make_plan, reanchor, replay
from understudy.scene import GRIPPER_CLOSED, HOME, JOINTS, load
from understudy.track import find_events, load_track, to_robot

RUN = REPO / "data" / "runs" / "put-the-red-block-in-the-bowl"
WORK = REPO / "media" / "work2"
APP = REPO / "film" / "app" / "media" / "demo"
TILES = APP / "understudy"
DECK = REPO / "film" / "deck" / "media"
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
REANCHOR_PER_CLIP = 15  # run.json: 60 tried over 4 clips
TW, TH = 1280, 720  # tile size (Player Two clips are 1280x720)
LW = round(TW * 0.38)  # the lead pane, 38% as in player-two Render.tsx
RW = TW - LW


def enc(out: Path, w: int, h: int, fps: float = 30, crf: int = 18):
    out.parent.mkdir(parents=True, exist_ok=True)
    return subprocess.Popen(
        [
            "ffmpeg",
            "-y",
            "-loglevel",
            "error",
            "-f",
            "rawvideo",
            "-pix_fmt",
            "rgb24",
            "-s",
            f"{w}x{h}",
            "-r",
            str(fps),
            "-i",
            "-",
            "-c:v",
            "libx264",
            "-crf",
            str(crf),
            "-preset",
            "medium",
            "-pix_fmt",
            "yuv420p",
            "-movflags",
            "+faststart",
            str(out),
        ],
        stdin=subprocess.PIPE,
    )


def read_frames(path: Path) -> np.ndarray:
    import cv2

    cap, out = cv2.VideoCapture(str(path)), []
    while True:
        ok, bgr = cap.read()
        if not ok:
            break
        out.append(cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB))
    return np.stack(out)


def label_png(name: str, html_body: str, w: int = 1920, h: int = 1080) -> np.ndarray:
    """A transparent overlay drawn by Chrome (this ffmpeg has no drawtext), returned as RGBA."""
    src, out = WORK / f"{name}.html", WORK / f"{name}.png"
    src.write_text(
        "<!doctype html><html><head><meta charset='utf-8'><style>"
        "body{margin:0;width:%dpx;height:%dpx;background:transparent;overflow:hidden;"
        "font-family:ui-monospace,SFMono-Regular,Menlo,monospace}"
        ".l{position:absolute;left:24px;top:24px;border-radius:4px;background:rgba(0,0,0,.5);padding:0 8px;"
        "font-size:18px;line-height:28px;text-transform:uppercase;letter-spacing:.3em;color:#67e8f9}"
        ".r{position:absolute;left:%dpx;top:24px;font-size:18px;line-height:28px;text-transform:uppercase;"
        "letter-spacing:.3em;color:#67e8f9}"
        ".s{position:absolute;right:24px;top:28px;font-size:16px;line-height:24px;color:rgba(255,255,255,.4)}"
        ".b{position:absolute;left:%dpx;right:24px;bottom:24px;font-size:16px;line-height:24px;color:rgba(255,255,255,.7)}"
        ".line{position:absolute;left:%dpx;top:0;bottom:0;width:1px;background:rgba(255,255,255,.1)}"
        "</style></head><body>%s</body></html>"
        % (w, h, 730 + 24, 730 + 24, 730, html_body)
    )
    subprocess.run(
        [
            CHROME,
            "--headless=new",
            "--disable-gpu",
            "--hide-scrollbars",
            "--default-background-color=00000000",
            f"--window-size={w},{h}",
            "--virtual-time-budget=2000",
            f"--screenshot={out}",
            src.as_uri(),
        ],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return np.asarray(Image.open(out).convert("RGBA"))


def over(base: np.ndarray, rgba: np.ndarray) -> np.ndarray:
    a = rgba[..., 3:4].astype(np.float32) / 255
    return (
        base.astype(np.float32) * (1 - a) + rgba[..., :3].astype(np.float32) * a
    ).astype(np.uint8)


def backdrop(w: int, h: int) -> np.ndarray:
    """radial-gradient(circle at 50% 30%, #1b2230, #07080b 75%), the Render.tsx page behind the robot."""
    yy, xx = np.mgrid[0:h, 0:w]
    r = np.hypot(xx - w * 0.5, yy - h * 0.3) / (0.75 * np.hypot(w, h) / 2)
    t = np.clip(r, 0, 1)[..., None]
    return (
        np.array([0x1B, 0x22, 0x30]) * (1 - t) + np.array([0x07, 0x08, 0x0B]) * t
    ).astype(np.uint8)


# ------------------------------------------------------------------ episodes, rebuilt and checked
def episodes(sc):
    run = json.loads((RUN / "run.json").read_text())
    want = json.loads((RUN / "lerobot" / "understudy_episodes.json").read_text())[
        "episodes"
    ]
    acc = [c["clip_id"] for c in run["clips"] if c["accepted"]]
    demos, res = {}, {}
    for cid in acc:
        res[cid] = json.loads((RUN / "results" / f"{cid}.json").read_text())
        tr = load_track(RUN / "pose" / f"{cid}.json")
        demos[cid] = to_robot(tr, find_events(tr), res[cid]["bowl_u"])
    rng = np.random.default_rng(1000)
    eps, failed = [], []
    for cid in acc:
        d = demos[cid]
        eps.append(
            {"clip": cid, "kind": "retargeted clip", "demo": d, "xy": d.cube_start[:2]}
        )
        keep = {
            tuple(e["cube_xy"])
            for e in want
            if e["clip"] == cid and e["kind"] == "re-anchored"
        }
        for _ in range(REANCHOR_PER_CLIP):
            xy = d.cube_start[:2] + rng.uniform(-np.array(JITTER), JITTER)
            if tuple(xy.round(4).tolist()) in keep:
                eps.append(
                    {
                        "clip": cid,
                        "kind": "re-anchored",
                        "demo": reanchor(d, xy),
                        "xy": xy,
                    }
                )
            else:
                failed.append({"clip": cid, "demo": reanchor(d, xy), "xy": xy})
    assert len(eps) == len(want), (len(eps), len(want))
    for e, w in zip(eps, want):
        assert e["clip"] == w["clip"] and e["kind"] == w["kind"], (e["clip"], w)
        assert np.allclose(e["xy"], w["cube_xy"], atol=6e-5), (e["xy"], w["cube_xy"])
    return run, acc, res, demos, eps, failed


class Cam:
    """Renders the scene each recorded frame into a list, with optional in-scene markers."""

    def __init__(self, sc, w, h, camera="front", free=None, marks=None):
        self.sc, self.camera, self.free, self.marks = sc, camera, free, marks
        sc.model.vis.global_.offwidth = max(sc.model.vis.global_.offwidth, w)
        sc.model.vis.global_.offheight = max(sc.model.vis.global_.offheight, h)
        self.r = mujoco.Renderer(sc.model, h, w)
        self.frames = []

    def frame(self, *_):
        cam = self.free if self.free is not None else self.camera
        self.r.update_scene(self.sc.data, camera=cam)
        if self.marks:
            self.marks(self.r.scene, len(self.frames))
        self.frames.append(self.r.render().copy())

    def close(self):
        self.r.close()


def sphere(scn, pos, size, rgba):
    if scn.ngeom >= scn.maxgeom:
        return
    g = scn.geoms[scn.ngeom]
    mujoco.mjv_initGeom(
        g,
        mujoco.mjtGeom.mjGEOM_SPHERE,
        np.array([size, 0, 0]),
        np.asarray(pos, float),
        np.eye(3).flatten(),
        np.asarray(rgba, np.float32),
    )
    scn.ngeom += 1


def human_index(rep, demo, n_clip: int) -> list[int]:
    """Clip frame shown next to each robot frame: held during the added reach and the dwells, advancing at half
    speed (the replay plays 2x slower than the human) while the demonstration plays, then running on to the end."""
    per = demo.fps / 30 / 2
    t, out, started = float(demo.start), [], False
    for ph in rep.phase:
        if ph in ("demo", "dwell"):
            started = True
        if started and ph in ("demo", "return"):
            t = min(t + per, n_clip - 1)
        out.append(int(round(t)))
    return out


def fmt(x, n=1):
    return f"{x:.{n}f}"


def build_tiles(sc, run, acc, res, demos, eps):
    import cv2

    TILES.mkdir(parents=True, exist_ok=True)
    lead = {}
    for cid in acc:
        skel = WORK / f"{cid}_skeleton_full.mp4"
        if not skel.exists():
            media.overlay_clip(
                RUN / "clips" / f"{cid}.mp4",
                RUN / "pose" / f"{cid}.json",
                res[cid]["events"],
                skel,
                scale=1.0,
            )
        fr = read_frames(skel)
        ev = res[cid]["events"]
        # the block with a margin on the left; the hand comes in from the right and the bowl follows
        cx = ev["b0"][0] - 90 + round(fr.shape[1] * LW / TH) / 2
        cw = round(
            fr.shape[2] * 0.38 * 16 / 9 * 9 / 16 * (fr.shape[1] / fr.shape[1])
        )  # 38% of the width
        cw = round(
            fr.shape[1] * LW / TH
        )  # crop width in clip pixels for a LW x TH pane
        x0 = int(np.clip(cx - cw / 2, 0, fr.shape[2] - cw))
        lead[cid] = np.stack(
            [
                cv2.resize(f[:, x0 : x0 + cw], (LW, TH), interpolation=cv2.INTER_AREA)
                for f in fr
            ]
        )
    manifest_clips, stats = [], []
    for n, e in enumerate(eps):
        cid, d = e["clip"], e["demo"]
        cam = Cam(sc, RW, TH)
        rep = replay(sc, d, on_frame=cam.frame)
        cam.close()
        rows = G.robot_gates(rep)
        ok, why = G.verdict(rows)
        assert ok, (n, why)
        idx = human_index(rep, d, len(lead[cid]))
        shift = (np.asarray(e["xy"]) - demos[cid].cube_start[:2]) * 100
        what = (
            "the clip as retargeted"
            if e["kind"] == "retargeted clip"
            else f"re-anchored copy, cube moved {fmt(shift[0])} / {fmt(shift[1])} cm"
        )
        ik = float(rep.ik_err.max()) * 1000
        vel = float(np.abs(np.diff(rep.actions[:, :5], axis=0) * 30).max())
        caption = (
            f"Grasp point to grasp point, 1:1 in metres: lift {fmt(d.lift_height * 100)} cm, carry "
            f"{fmt(d.carry_dist * 100)} cm. IK max error {fmt(ik)} mm, 0 ticks at a joint limit. 2x slower."
        )
        lab = label_png(
            f"tile-{n:02d}",
            "<div class='line'></div><div class='l'>The lead · Runway</div>"
            "<div class='r'>Understudy · SO-101 · MuJoCo</div>"
            f"<div class='s'>{cid}, {what}</div><div class='b'>{caption}</div>",
        )
        lab = np.asarray(Image.fromarray(lab).resize((TW, TH), Image.LANCZOS))
        out = TILES / f"ep-{n + 1:02d}.mp4"
        p = enc(out, TW, TH, crf=20)
        poster_at = (
            next(
                (i for i, ph in enumerate(rep.phase) if ph == "dwell"),
                len(rep.phase) // 2,
            )
            + 8
        )
        for i, rf in enumerate(cam.frames):
            f = np.concatenate([lead[cid][idx[i]], rf], axis=1)
            f = over(f, lab)
            p.stdin.write(f.tobytes())
            if i == poster_at:
                Image.fromarray(f).save(out.with_suffix(".jpg"), quality=86)
        p.stdin.close()
        p.wait()
        gates = {g["id"]: g for g in res[cid]["gates"]}
        manifest_clips.append(
            {
                "file": f"media/demo/understudy/{out.name}",
                "poster": f"media/demo/understudy/{out.with_suffix('.jpg').name}",
                "title": f"{cid}, {'as generated' if e['kind'] == 'retargeted clip' else 're-anchored copy'}",
                "seconds": round(len(cam.frames) / 30),
                "source": f"Runway {res[cid]['prompt']['image_model']} + {res[cid]['prompt']['video_model']}",
                "episode": "the clip as retargeted" if e["kind"] == "retargeted clip" else "re-anchored copy, gated again",
                "clipId": cid,
                "cube": what.replace("the clip as retargeted", "where the lead put it"),
                "quality": None,
                "stats": {
                    "handSeen": round(gates["hand_visible"]["value"] * 100),
                    "liftCm": round(d.lift_height * 100, 1),
                    "carryCm": round(d.carry_dist * 100, 1),
                    "ikMm": round(ik, 1),
                    "velPeak": round(vel, 2),
                    "inBowl": bool(rep.success and rep.lifted),
                },
            }
        )
        stats.append(
            {
                "n": n + 1,
                "clip": cid,
                "kind": e["kind"],
                "frames": len(cam.frames),
                "ik_mm": round(ik, 2),
            }
        )
        print(
            f"tile {n + 1}/44 {cid} {e['kind']} {len(cam.frames)} frames, ik {ik:.1f} mm",
            flush=True,
        )
    return manifest_clips, stats


def manifest(run, res, clips):
    steps = [
        {
            "name": "Plan",
            "detail": "the task fits a 5-DOF arm with two fingers: one hand, pinch a 3 cm red cube, lift, carry, release into a bowl",
            "ms": 40,
        },
        {
            "name": "Generate",
            "by": "Runway",
            "detail": "8 clips: first frame with gen4_image, a new table, bowl and light with gen4_image_turbo, 5 s of motion with gen4_turbo",
            "ms": 0,
        },
        {
            "name": "Track",
            "by": "MediaPipe",
            "detail": "21 hand points and the arm pose on every frame (Hand + Pose landmarkers); the red block followed by colour with OpenCV",
            "ms": 0,
        },
        {
            "name": "Audit",
            "by": "Claude",
            "detail": "headless scene audit of the first and last frames: counts red blocks, bowls and hands, finds the bowl",
            "ms": 0,
        },
        {
            "name": "Retarget",
            "by": "MuJoCo",
            "detail": "grasp point to grasp point, 1:1 in metres, IK on the SO-101, then a physics replay; 21 gates, 4 accepted, 4 rejected",
            "ms": 0,
        },
        {
            "name": "Write dataset",
            "by": "LeRobot",
            "detail": "44 episodes (4 accepted clips + 40 re-anchored copies, each gated again), 14,985 frames, LeRobot v3.0, loaded back",
            "ms": round(run["dataset"]["seconds"] * 1000),
        },
    ]
    rej = []
    for c in run["clips"]:
        if not c["accepted"]:
            rj = c["reason"].split(": ", 1)[-1]
            rej.append({"title": c["clip_id"], "reason": rj})
    return {
        "demos": [
            {
                "id": "understudy-red-block",
                "robot": "SO-101",
                "robotId": "so101",
                "task": run["task"],
                "tier": "runway-video",
                "match": ["red block", "bowl"],
                "agentTask": run["task"],
                "recordedAt": "2026-09-23T22:41:02.000Z",
                "summary": {
                    "found": 8,
                    "judged": 8,
                    "accepted": 4,
                    "rejected": 4,
                    "episodes": run["dataset"]["episodes"],
                    "seconds": 1037,  # data/run2.log: "[run] done in 1037.3 s"
                },
                "steps": steps,
                "rejections": rej,
                "clips": clips,
            }
        ]
    }


# ------------------------------------------------------------------ deck plates
def runway_grid(run):
    """The 8 Runway clips filling the frame, 4x2 cells of 480x540, each cropped around its own block and bowl."""
    ids = [c["clip_id"] for c in run["clips"]]
    ins, g = [], ""
    for k, cid in enumerate(ids):
        ins += ["-i", str(RUN / "clips" / f"{cid}.mp4")]
        r = json.loads((RUN / "results" / f"{cid}.json").read_text())
        ev = r.get("events") or {}
        cx = (ev["b0"][0] + r["bowl_u"]) / 2 if ev.get("b0") and r.get("bowl_u") else 640
        x0 = int(np.clip(cx * 0.75 - 240, 0, 960 - 480))
        g += f"[{k}:v]fps=30,scale=960:540,crop=480:540:{x0}:0,setsar=1[g{k}];"
    lay = "|".join(f"{(k % 4) * 480}_{(k // 4) * 540}" for k in range(8))
    g += "".join(f"[g{k}]" for k in range(8)) + f"xstack=inputs=8:layout={lay}[v]"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", *ins, "-filter_complex", g, "-map", "[v]", "-t", "5",
                    "-c:v", "libx264", "-crf", "18", "-pix_fmt", "yuv420p", str(DECK / "runway-grid.mp4")], check=True)


def deck(sc, run, acc, res, demos, eps, failed):

    DECK.mkdir(parents=True, exist_ok=True)
    facts = {}

    runway_grid(run)

    # the lead with what was measured: MediaPipe hand points, the OpenCV block box, full frame
    hero = acc[0]
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-loglevel",
            "error",
            "-i",
            str(WORK / f"{hero}_skeleton_full.mp4"),
            "-vf",
            "fps=30,scale=1920:1080:flags=lanczos",
            "-c:v",
            "libx264",
            "-crf",
            "18",
            "-pix_fmt",
            "yuv420p",
            str(DECK / "lead-overlay.mp4"),
        ],
        check=True,
    )
    # two raw leads for the pitch shot and the rejection
    for cid, name in ((acc[1], "lead-raw"), ("v00", "reject-v00")):
        subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-loglevel",
                "error",
                "-i",
                str(RUN / "clips" / f"{cid}.mp4"),
                "-vf",
                "fps=30,scale=1920:1080:flags=lanczos",
                "-c:v",
                "libx264",
                "-crf",
                "18",
                "-pix_fmt",
                "yuv420p",
                str(DECK / f"{name}.mp4"),
            ],
            check=True,
        )

    # the model: a slow orbit while each joint moves in turn (kinematic, no physics)
    m, d = sc.model, sc.data
    sc.reset(HOME, GRIPPER_CLOSED, np.array([0.25, -0.085]), 0.0)
    free = mujoco.MjvCamera()
    free.type = mujoco.mjtCamera.mjCAMERA_FREE
    free.lookat[:] = [0.07, 0.0, 0.13]
    free.distance, free.elevation = 0.62, -18.0
    cam = Cam(sc, 1920, 1080, free=free)
    qadr = [m.joint(j).qposadr[0] for j in JOINTS]
    q0 = np.array([*HOME, GRIPPER_CLOSED])
    n = int(7.0 * 30)
    for k in range(n):
        t = k / n
        free.azimuth = 150 + 60 * t
        q = q0.copy()
        j = min(int(t * 6), 5)
        u = t * 6 - j
        lo, hi = m.jnt_range[m.joint(JOINTS[j]).id]
        amp = 0.35 * (hi - lo) / 2 if j < 5 else 0.9
        q[j] = (
            q0[j] + amp * np.sin(2 * np.pi * u)
            if j < 5
            else GRIPPER_CLOSED + amp * np.sin(np.pi * u)
        )
        for a, v in zip(qadr, q):
            d.qpos[a] = v
        mujoco.mj_forward(m, d)
        cam.frame()
    cam.close()
    write(DECK / "model-orbit.mp4", cam.frames)
    arm = [
        b
        for b in (
            "base",
            "shoulder",
            "upper_arm",
            "lower_arm",
            "wrist",
            "gripper",
            "moving_jaw_so101_v1",
        )
    ]
    facts["model"] = {
        "arm_mass_kg": round(sum(float(m.body_mass[m.body(b).id]) for b in arm), 3),
        "masses_g": {b: round(float(m.body_mass[m.body(b).id]) * 1000) for b in arm},
        "limits_deg": {
            j: [round(float(np.degrees(v))) for v in m.jnt_range[m.joint(j).id]]
            for j in JOINTS
        },
        "meshes": int(m.nmesh),
        "kp": float(m.actuator_gainprm[0][0]),
        "forcerange": m.actuator_forcerange[0].tolist(),
        "timestep_hz": round(1 / m.opt.timestep),
        "gravcomp": [b for b in arm if float(m.body_gravcomp[m.body(b).id]) == 1.0],
    }

    # IK: the human's grasp path drawn in the scene while the SO-101 follows it
    dm = demos[hero]
    plan = make_plan(dm)
    path = [
        plan.grasp_pt[k]
        for k in range(len(plan.phase))
        if plan.phase[k] in ("demo", "dwell")
    ][::2]
    pre_ticks = int(0.3 / DT) + int(1.5 / DT)

    def marks(scn, fr):
        for pnt in path:
            sphere(scn, pnt, 0.0028, (0.40, 0.91, 0.98, 0.55))
        k = fr * 10 // 6 - pre_ticks
        if 0 <= k < len(plan.grasp_pt):
            sphere(scn, plan.grasp_pt[k], 0.0065, (0.40, 0.91, 0.98, 1.0))

    cam = Cam(sc, 1920, 1080, marks=marks)
    rep = replay(sc, dm, on_frame=cam.frame)
    cam.close()
    write(
        DECK / "ik-path.mp4", cam.frames[::2]
    )  # the human's own speed (the replay is 2x slower)
    facts["ik"] = {
        "clip": hero,
        "ik_max_mm": round(float(rep.ik_err.max()) * 1000, 2),
        "limit_ticks": int(rep.at_limit.sum()),
        "lift_cm": round(dm.lift_height * 100, 1),
        "carry_cm": round(dm.carry_dist * 100, 1),
    }

    # physics decides: an accepted episode next to a re-anchored copy that failed a robot gate
    bad = None
    for f in failed:
        r2 = replay(sc, f["demo"])
        ok, why = G.verdict(G.robot_gates(r2))
        if not ok and ("opens over the bowl" in why or "closes before lift" in why):
            bad, bad_why = f, why
            break
    assert bad is not None
    panes = []
    for dd in (dm, bad["demo"]):
        cam = Cam(sc, 960, 1080)
        replay(sc, dd, on_frame=cam.frame)
        cam.close()
        panes.append(cam.frames)
    n = max(len(p) for p in panes)
    frames = [
        np.concatenate(
            [panes[0][min(i, len(panes[0]) - 1)], panes[1][min(i, len(panes[1]) - 1)]],
            axis=1,
        )
        for i in range(0, n, 2)
    ]
    write(DECK / "pass-fail.mp4", frames)
    facts["fail"] = {
        "clip": bad["clip"],
        "why": bad_why,
        "xy": np.round(bad["xy"], 4).tolist(),
    }

    # the trained policy on an unseen cube position (only in its own section of the film)
    from understudy.policy import Runner, rollout

    runner = Runner(RUN / "policy")
    ok_eps = [e for e in run["eval"]["episodes"] if e["success"]]
    cam = Cam(sc, 1920, 1080)
    rollout(sc, runner, ok_eps[0]["cube_xy"], on_frame=cam.frame)
    cam.close()
    # the reach from home is trimmed (2 s) so the shot holds on the grasp, the carry and the release
    write(DECK / "policy.mp4", cam.frames[60:])
    facts["policy"] = {
        "seed": ok_eps[0]["seed"],
        "cube_xy": ok_eps[0]["cube_xy"],
        **{k: run["eval"][k] for k in ("seeds", "successes", "wilson95")},
    }

    # the title and end backgrounds: the first tile (lead + replay), never the policy
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-loglevel",
            "error",
            "-i",
            str(TILES / "ep-01.mp4"),
            "-vf",
            "scale=1920:1080:flags=lanczos",
            "-c:v",
            "libx264",
            "-crf",
            "18",
            "-pix_fmt",
            "yuv420p",
            str(DECK / "tile-bg.mp4"),
        ],
        check=True,
    )
    facts["run"] = {k: run[k] for k in ("reanchor", "dataset", "train")}
    (WORK / "facts.json").write_text(json.dumps(facts, indent=1))
    print(json.dumps(facts, indent=1))


def write(out: Path, frames):
    h, w = frames[0].shape[:2]
    p = enc(out, w, h)
    for f in frames:
        p.stdin.write(np.ascontiguousarray(f).tobytes())
    p.stdin.close()
    p.wait()


def main():
    only = (
        sys.argv[sys.argv.index("--only") + 1].split(",")
        if "--only" in sys.argv
        else ["tiles", "deck"]
    )
    WORK.mkdir(parents=True, exist_ok=True)
    sc = load(task="pick")
    run, acc, res, demos, eps, failed = episodes(sc)
    print(
        f"rebuilt {len(eps)} episodes, matches understudy_episodes.json; {len(failed)} failed copies",
        flush=True,
    )
    if "tiles" in only:
        clips, stats = build_tiles(sc, run, acc, res, demos, eps)
        (APP / "manifest.json").write_text(
            json.dumps(manifest(run, res, clips), indent=1)
        )
        (WORK / "tiles.json").write_text(json.dumps(stats, indent=1))
    if "deck" in only:
        deck(sc, run, acc, res, demos, eps, failed)


if __name__ == "__main__":
    main()
