"""Render the demo video: media/understudy-demo.mp4 (1920x1080, 30 fps, about 80 s).

Plates are real outputs of one run (Runway clips, MediaPipe overlays, MuJoCo renders of the replay and of the
trained policy). Chips, captions and cards are HTML rendered to transparent PNGs by headless Chrome (this ffmpeg
has no drawtext) and composited with ffmpeg overlay + alpha fades: the same pop-up language as the Player Two
video. No zoompan anywhere (it shimmers).

Usage: .venv/bin/python scripts/film.py [data/runs/<slug>]
"""

from __future__ import annotations

import html
import json
import subprocess
import sys
from pathlib import Path

import numpy as np
from PIL import Image

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))
RUN = (
    Path(sys.argv[1])
    if len(sys.argv) > 1
    else REPO / "data" / "runs" / "put-the-red-block-in-the-bowl"
)
WORK = REPO / "media" / "work"
OUT = REPO / "media" / "understudy-demo.mp4"
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
W, H, FPS = 1920, 1080, 30

FONTS = '<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Press+Start+2P&family=VT323&display=swap">'
CSS = """
body{margin:0;width:1920px;height:1080px;background:transparent;color:#ece6d3;font-family:'VT323',monospace;overflow:hidden}
.chip{position:absolute;left:72px;top:60px;font:22px/1 'Press Start 2P';background:#ffbe28;color:#05060b;padding:16px 18px;
 border:4px solid #05060b;box-shadow:6px 6px 0 #05060b;letter-spacing:1px}
.chip small{display:block;font:30px/1 'VT323';margin-top:8px;letter-spacing:0}
.chip.r{left:auto;right:72px}
.cap{position:absolute;left:50%;transform:translateX(-50%);bottom:70px;max-width:1500px;font:46px/1.15 'VT323';
 background:#141c36;border:4px solid #05060b;box-shadow:6px 6px 0 #05060b;padding:14px 26px;text-align:center}
.cap b{color:#ffbe28;font-weight:normal}
.stamp{position:absolute;right:90px;top:180px;font:30px/1.3 'Press Start 2P';color:#05060b;background:#ff5a4e;border:5px solid #05060b;
 box-shadow:8px 8px 0 #05060b;padding:18px 22px;max-width:760px}
.stamp span{display:block;font:40px/1.1 'VT323';margin-top:10px}
.stamp.ok{background:#7cffc4}
.card{position:absolute;left:50%;top:50%;transform:translate(-50%,-50%);width:1400px;background:#141c36;border:5px solid #05060b;
 box-shadow:10px 10px 0 #05060b;padding:48px 56px}
.card h1{font:64px/1 'Press Start 2P';margin:0 0 30px;text-shadow:6px 6px 0 #05060b}
.card p{font:48px/1.2 'VT323';margin:0 0 14px}
.card .amber{color:#ffbe28}
.term{font:34px/1.5 'Press Start 2P';color:#7cffc4;background:#05060b;padding:26px;margin:0 0 26px}
.term i{color:#ffbe28;font-style:normal}
.no{font:40px/1.3 'VT323';color:#a9a693}
.no b{color:#ff5a4e;font:22px 'Press Start 2P';font-weight:normal;margin-right:12px}
.stats{display:grid;grid-template-columns:repeat(3,1fr);gap:22px}
.stat{background:#0a0e1c;border:4px solid #05060b;padding:20px}
.stat .v{font:40px/1.2 'Press Start 2P';color:#7cffc4;display:block;margin-bottom:10px}
.stat .k{font:36px/1.1 'VT323';color:#a9a693}
.pop{position:absolute;right:72px;bottom:200px;font:40px/1.15 'VT323';background:#0a0e1c;border:4px solid #ffbe28;
 box-shadow:6px 6px 0 #05060b;padding:14px 20px;max-width:620px}
.pop b{font:20px 'Press Start 2P';color:#ffbe28;font-weight:normal;display:block;margin-bottom:8px}
"""


def sh(args, **kw):
    subprocess.run(args, check=True, **kw)


def png(name: str, body: str) -> Path:
    """Render one transparent 1920x1080 overlay."""
    src = WORK / f"{name}.html"
    out = WORK / f"{name}.png"
    src.write_text(
        f"<!doctype html><html><head><meta charset='utf-8'>{FONTS}<style>{CSS}</style></head><body>{body}</body></html>"
    )
    sh(
        [
            CHROME,
            "--headless=new",
            "--disable-gpu",
            "--hide-scrollbars",
            "--default-background-color=00000000",
            f"--window-size={W},{H}",
            "--virtual-time-budget=4000",
            f"--screenshot={out}",
            src.as_uri(),
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return out


def dither_bg() -> Path:
    """Night-to-studio-blue backdrop with an 8x8 Bayer dither, rendered small and scaled up with nearest neighbour."""
    out = WORK / "bg.png"
    B = np.array(
        [
            [0, 32, 8, 40, 2, 34, 10, 42],
            [48, 16, 56, 24, 50, 18, 58, 26],
            [12, 44, 4, 36, 14, 46, 6, 38],
            [60, 28, 52, 20, 62, 30, 54, 22],
            [3, 35, 11, 43, 1, 33, 9, 41],
            [51, 19, 59, 27, 49, 17, 57, 25],
            [15, 47, 7, 39, 13, 45, 5, 37],
            [63, 31, 55, 23, 61, 29, 53, 21],
        ]
    )
    ramp = np.array([[10, 14, 28], [16, 22, 44], [24, 36, 72], [34, 56, 110]], np.uint8)
    w, h = 240, 135
    y, x = np.mgrid[0:h, 0:w]
    t = np.clip((y / h) * 0.9 + 0.1 * np.sin(x / 23), 0, 1) * 3
    i = np.floor(t).astype(int)
    k = np.where(t - i > (B[y % 8, x % 8] + 0.5) / 64, np.minimum(i + 1, 3), i)
    Image.fromarray(ramp[k]).resize((W, H), Image.NEAREST).save(out)
    return out


def seg_plate(name: str, dur: float, inputs: list, graph: str) -> Path:
    """One segment: arbitrary ffmpeg inputs + a graph that ends in [v]; always 1920x1080 30 fps, dur seconds."""
    out = WORK / f"seg_{name}.mp4"
    args = ["ffmpeg", "-v", "error", "-y"]
    for inp in inputs:
        args += inp
    args += [
        "-filter_complex",
        graph,
        "-map",
        "[v]",
        "-t",
        f"{dur}",
        "-r",
        str(FPS),
        "-c:v",
        "libx264",
        "-crf",
        "18",
        "-preset",
        "medium",
        "-pix_fmt",
        "yuv420p",
        str(out),
    ]
    sh(args)
    return out


def overlays(
    base: str, pngs: list[tuple[Path, float, float]], first_input: int
) -> tuple[list, str, str]:
    """Pop-in (0.25 s alpha fade) PNG overlays. Returns (inputs, graph fragment, final label)."""
    inputs, g, cur = [], "", base
    for n, (p, t0, t1) in enumerate(pngs):
        idx = first_input + n
        inputs.append(["-loop", "1", "-t", f"{t1 + 0.5}", "-i", str(p)])
        g += (
            f"[{idx}:v]format=rgba,fade=t=in:st={t0}:d=0.25:alpha=1,fade=t=out:st={t1 - 0.25}:d=0.25:alpha=1[o{n}];"
            f"[{cur}][o{n}]overlay=0:0:enable='between(t,{t0},{t1})'[c{n}];"
        )
        cur = f"c{n}"
    return inputs, g, cur


def fit(label_in: str, w: int, h: int, label_out: str) -> str:
    return f"[{label_in}]scale={w}:{h}:force_original_aspect_ratio=decrease:flags=lanczos,pad={w}:{h}:(ow-iw)/2:(oh-ih)/2:color=0x0a0e1c,setsar=1,tpad=stop_mode=clone:stop_duration=20[{label_out}];"


def main() -> None:
    WORK.mkdir(parents=True, exist_ok=True)
    run = json.loads((REPO / "site" / "data" / "run.json").read_text())
    clips = {c["id"]: c for c in run["clips"]}
    acc = [c for c in run["clips"] if c["accepted"]]
    rej = [c for c in run["clips"] if not c["accepted"]]
    bg = dither_bg()
    E, T, D = run["eval"], run["train"], run["dataset"]
    segs = []

    # --- renders at film resolution: skeleton overlay of the hero clip, robot replay and policy rollouts at 1280x720
    from understudy import media, retarget
    from understudy.policy import Runner, rollout
    from understudy.scene import load
    from understudy.track import find_events, load_track, to_robot

    hero = acc[0]["id"]
    res = json.loads((RUN / "results" / f"{hero}.json").read_text())
    media.overlay_clip(
        RUN / "clips" / f"{hero}.mp4",
        RUN / "pose" / f"{hero}.json",
        res["events"],
        WORK / "hero_skeleton.mp4",
        scale=1.0,
    )
    sc = load(task="pick")
    sc.model.vis.global_.offwidth, sc.model.vis.global_.offheight = 1280, 720
    tr = load_track(RUN / "pose" / f"{hero}.json")
    demo = to_robot(tr, find_events(tr), res["bowl_u"])
    film = media.SimFilm(sc, WORK / "hero_robot.mp4", 1280, 720)
    retarget.replay(sc, demo, on_frame=film.frame)
    film.close()
    runner = Runner(RUN / "policy")
    full = json.loads((RUN / "run.json").read_text())["eval"]["episodes"]
    ok = [e for e in full if e["success"]]
    film = media.SimFilm(sc, WORK / "policy.mp4", 1280, 720)
    rollout(sc, runner, (ok[0] if ok else full[0])["cube_xy"], on_frame=film.frame)
    film.close()

    # 1. title
    t = png(
        "title",
        "<div class='card'><h1>UNDERSTUDY</h1><p>AI video now models gravity, contact and grasping well enough "
        "to look real at a glance.</p><p class='amber'>The natural next step: use it as data. Robotics first.</p></div>",
    )
    segs.append(
        seg_plate(
            "title",
            6,
            [["-loop", "1", "-i", str(bg)], ["-loop", "1", "-i", str(t)]],
            "[0:v][1:v]overlay=0:0,fade=t=in:st=0:d=0.5[v]",
        )
    )

    # 1b. the problem
    t2 = png(
        "problem",
        "<div class='card'><p>Robots learn a skill by watching demonstrations, and they need a lot of them.</p>"
        "<p>Today people record them one take at a time, teleoperating a robot or filming themselves. "
        "Slow and expensive.</p><p class='amber'>Understudy makes them from one sentence. "
        "An understudy learns the role by watching the lead.</p></div>",
    )
    segs.append(
        seg_plate(
            "problem",
            6,
            [["-loop", "1", "-i", str(bg)], ["-loop", "1", "-i", str(t2)]],
            "[1:v]format=rgba,fade=t=in:st=0.1:d=0.3:alpha=1[c];[0:v][c]overlay=0:0[v]",
        )
    )

    # 2. prompt
    p = png(
        "prompt",
        f"<div class='card'><div class='term'><i>&gt;</i> {html.escape(run['task'])}</div>"
        "<p class='no'><b>NO</b>fold the towel: deformable, two fingers cannot manage cloth</p>"
        "<p class='no'><b>NO</b>pour water into the cup: liquids need wrist twist</p>"
        "<p class='no'><b>NO</b>use both hands: the SO-101 is one arm</p></div>",
    )
    c = png(
        "prompt_chip",
        "<div class='chip'>STEP 1 / PROMPT<small>checked against a 5-DOF arm with two fingers</small></div>",
    )
    ins, g, last = overlays("0:v", [(p, 0.2, 6), (c, 0.6, 6)], 1)
    segs.append(
        seg_plate(
            "prompt", 6, [["-loop", "1", "-i", str(bg)], *ins], g + f"[{last}]null[v]"
        )
    )

    # 3. Runway grid (8 clips, 4x2)
    ids = [c["id"] for c in run["clips"]][:8]
    ins = [["-stream_loop", "-1", "-i", str(RUN / "clips" / f"{i}.mp4")] for i in ids]
    g = "".join(
        f"[{n}:v]scale=472:266,setsar=1,pad=480:270:4:2:color=0x05060b[g{n}];"
        for n in range(len(ids))
    )
    layout = "|".join(f"{(n % 4) * 480}_{(n // 4) * 270}" for n in range(len(ids)))
    g += (
        "".join(f"[g{n}]" for n in range(len(ids)))
        + f"xstack=inputs={len(ids)}:layout={layout}:fill=0x0a0e1c[grid];"
    )
    g += f"[{len(ids)}:v][grid]overlay=0:250[base];"
    chip = png(
        "runway_chip",
        "<div class='chip'>RUNWAY API<small>gen4_image, gen4_image_turbo, gen4_turbo</small></div>",
    )
    cap = png(
        "runway_cap",
        f"<div class='cap'>One prompt, <b>{len(ids)} generated demonstrations</b>: new table, bowl and light each time. "
        f"{run['credits']} credits.</div>",
    )
    o, g2, last = overlays("base", [(chip, 0.3, 10), (cap, 1.2, 10)], len(ids) + 1)
    segs.append(
        seg_plate(
            "runway",
            10,
            [*ins, ["-loop", "1", "-i", str(bg)], *o],
            g + g2 + f"[{last}]null[v]",
        )
    )

    # 4. skeleton on the hero clip
    chip = png(
        "skel_chip",
        "<div class='chip'>MEDIAPIPE<small>Hand Landmarker (21 points) + Pose heavy</small></div>",
    )
    gates = {g_["id"]: g_ for g_ in clips[hero]["gates"]}
    pop = png(
        "skel_pop",
        f"<div class='pop'><b>MEASURED</b>hand seen on {gates['hand_visible']['value'] * 100:.0f}% of frames<br>"
        f"lift {clips[hero]['lift_cm']} cm, carry {clips[hero]['carry_cm']} cm<br>grasp and release read from the block</div>",
    )
    o, g2, last = overlays("base", [(chip, 0.3, 8), (pop, 2.0, 8)], 1)
    segs.append(
        seg_plate(
            "skeleton",
            8,
            [["-stream_loop", "-1", "-i", str(WORK / "hero_skeleton.mp4")], *o],
            fit("0:v", W, H, "base") + g2 + f"[{last}]null[v]",
        )
    )

    # 5. two rejections
    for n, cr in enumerate(rej[:2]):
        chip = png(
            f"rej{n}_chip",
            "<div class='chip'>21 STRICT GATES<small>MediaPipe, OpenCV, Claude scene audit, MuJoCo</small></div>",
        )
        cap = png(
            f"rej{n}_cap",
            "<div class='cap'>Runway imagines the demonstration. <b>Physics decides if it counts.</b></div>",
        )
        why = cr["reason"].split(": ", 1)
        stamp = png(
            f"rej{n}_stamp",
            f"<div class='stamp'>REJECTED {cr['id']}<span>{html.escape(why[-1])}</span></div>",
        )
        o, g2, last = overlays("base", [(chip, 0.2, 6), (stamp, 1.2, 6), (cap, 2.2, 6)], 1)
        segs.append(
            seg_plate(
                f"reject{n}",
                6,
                [["-i", str(RUN / "clips" / f"{cr['id']}.mp4")], *o],
                fit("0:v", W, H, "base") + g2 + f"[{last}]null[v]",
            )
        )

    # 6. retarget: lead and understudy side by side
    chip = png(
        "rt_chip",
        "<div class='chip'>MUJOCO<small>SO-101, real contact physics, 2x slower than the human</small></div>",
    )
    cap = png(
        "rt_cap",
        "<div class='cap'>The hand's grasp point becomes the gripper's grasp point, <b>1:1 in metres</b>. "
        "The 3 cm block is the ruler.</div>",
    )
    stamp = png(
        "rt_stamp",
        f"<div class='stamp ok'>ACCEPTED {hero}<span>all 21 gates pass</span></div>",
    )
    g = (
        "[0:v]scale=944:531,setsar=1[l];[1:v]scale=944:531,setsar=1,tpad=stop_mode=clone:stop_duration=20[r];"
        "[2:v][l]overlay=24:250[a];[a][r]overlay=952:250[base];"
    )
    o, g2, last = overlays(
        "base", [(chip, 0.2, 12), (cap, 1.0, 12), (stamp, 7.5, 12)], 3
    )
    segs.append(
        seg_plate(
            "retarget",
            12,
            [
                ["-stream_loop", "-1", "-i", str(RUN / "clips" / f"{hero}.mp4")],
                ["-i", str(WORK / "hero_robot.mp4")],
                ["-loop", "1", "-i", str(bg)],
                *o,
            ],
            g + g2 + f"[{last}]null[v]",
        )
    )

    # 7. dataset card
    re_ = run["reanchor"]
    card = png(
        "ds",
        "<div class='card'><h1>LEROBOT v3.0</h1><div class='stats'>"
        f"<div class='stat'><span class='v'>{len(acc)}/{len(run['clips'])}</span><span class='k'>Runway clips accepted</span></div>"
        f"<div class='stat'><span class='v'>{D['episodes']}</span><span class='k'>episodes ({re_['accepted']} re-anchored copies, each gated again)</span></div>"
        f"<div class='stat'><span class='v'>{D['frames']}</span><span class='k'>frames at 30 fps, so101_follower keys and units</span></div>"
        "</div><p style='margin-top:30px'>Written with <span class='amber'>LeRobotDataset.create</span>, loaded back before training.</p></div>",
    )
    segs.append(
        seg_plate(
            "dataset",
            7,
            [["-loop", "1", "-i", str(bg)], ["-loop", "1", "-i", str(card)]],
            "[1:v]format=rgba,fade=t=in:st=0.1:d=0.3:alpha=1[c];[0:v][c]overlay=0:0[v]",
        )
    )

    # 8. policy
    chip = png(
        "pol_chip",
        f"<div class='chip'>THE UNDERSTUDY<small>MLP policy, trained on a laptop CPU in {T['train_seconds']:.0f} s</small></div>",
    )
    pop = png(
        "pol_pop",
        f"<div class='pop'><b>MUJOCO, UNSEEN CUBE POSITIONS</b>{E['successes']}/{E['seeds']} successes<br>"
        f"95% interval {E['wilson95'][0] * 100:.0f} to {E['wilson95'][1] * 100:.0f}%<br>state-based, sim only</div>",
    )
    o, g2, last = overlays("base", [(chip, 0.3, 14), (pop, 2.5, 14)], 1)
    segs.append(
        seg_plate(
            "policy",
            14,
            [["-i", str(WORK / "policy.mp4")], *o],
            fit("0:v", W, H, "base0")
            + "[base0]tpad=stop_mode=clone:stop_duration=14[base];"
            + g2
            + f"[{last}]null[v]",
        )
    )

    # 9. outro
    t = png(
        "outro",
        "<div class='card'><h1>UNDERSTUDY</h1><p>Runway imagines the demonstration. Physics decides if it counts.</p>"
        "<p class='amber'>Runway API, MediaPipe, OpenCV, Claude, MuJoCo, LeRobot</p></div>",
    )
    segs.append(
        seg_plate(
            "outro",
            5,
            [["-loop", "1", "-i", str(bg)], ["-loop", "1", "-i", str(t)]],
            "[0:v][1:v]overlay=0:0,fade=t=out:st=4.4:d=0.6[v]",
        )
    )

    lst = WORK / "concat.txt"
    lst.write_text("".join(f"file '{s}'\n" for s in segs))
    sh(
        [
            "ffmpeg",
            "-v",
            "error",
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(lst),
            "-c:v",
            "libx264",
            "-crf",
            "20",
            "-preset",
            "medium",
            "-pix_fmt",
            "yuv420p",
            "-movflags",
            "+faststart",
            str(OUT),
        ]
    )
    dur = float(
        subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "csv=p=0",
                str(OUT),
            ],
            capture_output=True,
            text=True,
        ).stdout
    )
    print(f"{OUT} {dur:.1f} s")


if __name__ == "__main__":
    main()
