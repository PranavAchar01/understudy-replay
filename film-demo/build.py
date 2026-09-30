# Builds one section of the Understudy demo film (720p30, silent) from rendered cards, screen recordings and media.
# usage: python3 build.py <intro|demo|bench|routing|close>
import json
import os
import subprocess
import sys
from pathlib import Path

HOME = Path.home()
FD = HOME / "helloworld/understudy-replay/film-demo"
W = FD / "work"
C = W / "cards"
SH = W / "shots"
SH.mkdir(parents=True, exist_ok=True)
RUN = HOME / "helloworld/understudy-replay/data/web-runs/put-the-red-block-in-the-bowl"
REP = HOME / "helloworld/understudy/site/report/media"
OUT = HOME / "Downloads"
FPS = 30
ENC = [
    "-c:v",
    "libx264",
    "-preset",
    "veryfast",
    "-crf",
    "16",
    "-pix_fmt",
    "yuv420p",
    "-r",
    str(FPS),
    "-an",
]
REUSE = bool(os.environ.get("REUSE"))  # skip re-encoding shots that already exist
BASE = f"fps={FPS},scale=1280:720:flags=lanczos,setsar=1,format=yuv420p"


def ff(args):
    subprocess.run(
        [
            "nice",
            "-n",
            "19",
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            *args,
        ],
        check=True,
    )


def caps_graph(base_label, caps, first_idx):
    """caps: [(card, t0, t1)] overlaid with 0.3 s alpha fades. Returns (inputs, filter parts, final label)."""
    ins, parts, cur = [], [], base_label
    for k, (card, t0, t1) in enumerate(caps):
        ins += [
            "-loop",
            "1",
            "-framerate",
            str(FPS),
            "-t",
            f"{t1:.3f}",
            "-i",
            str(C / f"{card}.png"),
        ]
        n = first_idx + k
        parts.append(
            f"[{n}:v]format=rgba,fade=t=in:st={t0:.3f}:d=0.3:alpha=1,fade=t=out:st={t1 - 0.3:.3f}:d=0.3:alpha=1[c{k}]"
        )
        parts.append(f"[{cur}][c{k}]overlay=0:0:eof_action=pass[o{k}]")
        cur = f"o{k}"
    return ins, parts, cur


def still(name, card, dur):
    out = SH / f"{name}.mp4"
    if REUSE and out.exists():
        return out, dur
    ff(
        [
            "-loop",
            "1",
            "-framerate",
            str(FPS),
            "-t",
            f"{dur}",
            "-i",
            str(C / f"{card}.png"),
            "-vf",
            BASE,
            *ENC,
            str(out),
        ]
    )
    return out, dur


def rec(name, src, a, b, caps=(), holds=()):
    """Trim a recording [a, b) and overlay captions given in recording time.
    holds: [(t, secs)] freeze the frame at recording time t (a < t <= b) for secs, to pace the shot to the voiceover."""
    out = SH / f"{name}.mp4"
    holds = sorted(holds)
    dur = b - a + sum(h for _, h in holds)

    def f(t):
        return t - a + sum(h for ht, h in holds if ht < t)

    ins, parts, cur = caps_graph("v0", [(c, f(t0), f(t1)) for c, t0, t1 in caps], 1)
    if holds:
        cuts = [a] + [t for t, _ in holds] + [b]
        hs = [h for _, h in holds] + [0]
        k = len(hs)
        pieces = [f"[0:v]split={k}" + "".join(f"[p{i}]" for i in range(k))]
        for i in range(k):
            pad = f",tpad=stop_mode=clone:stop_duration={hs[i]:.3f}" if hs[i] else ""
            pieces.append(
                f"[p{i}]trim=start={cuts[i]}:end={cuts[i + 1]},setpts=PTS-STARTPTS,{BASE}{pad}[q{i}]"
            )
        pieces.append(
            "".join(f"[q{i}]" for i in range(k)) + f"concat=n={k}:v=1:a=0[v0]"
        )
        head = pieces
    else:
        head = [f"[0:v]trim=start={a}:end={b},setpts=PTS-STARTPTS,{BASE}[v0]"]
    g = [
        *head,
        *parts,
        f"[{cur}]format=yuv420p[out]",
    ]
    ff(
        [
            "-i",
            str(src),
            *ins,
            "-filter_complex",
            ";".join(g),
            "-map",
            "[out]",
            "-t",
            f"{dur:.3f}",
            *ENC,
            str(out),
        ]
    )
    return out, dur


def layout(name, card, dur, slots):
    """Card background with videos in slots: [(path, x, y, w, h, start[, vf[, reveal]])]; short clips loop."""
    out = SH / f"{name}.mp4"
    if REUSE and out.exists():
        return out, dur
    ins = [
        "-loop",
        "1",
        "-framerate",
        str(FPS),
        "-t",
        f"{dur}",
        "-i",
        str(C / f"{card}.png"),
    ]
    g, cur = [f"[0:v]{BASE}[b]"], "b"
    for k, slot in enumerate(slots):
        p, x, y, w, h, ss = slot[:6]
        vf = (slot[6] + ",") if len(slot) > 6 and slot[6] else ""
        rv = slot[7] if len(slot) > 7 else 0
        ins += ["-stream_loop", "-1", "-ss", str(ss), "-i", str(p)]
        chain = f"[{k + 1}:v]{vf}fps={FPS},scale={w}:{h}:force_original_aspect_ratio=decrease:flags=lanczos,setsar=1"
        if rv:
            chain += f",setpts=PTS-STARTPTS+{rv}/TB,format=yuva420p,fade=t=in:st={rv}:d=0.45:alpha=1"
        g.append(chain + f"[s{k}]")
        g.append(
            f"[{cur}][s{k}]overlay=x={x}+({w}-overlay_w)/2:y={y}+({h}-overlay_h)/2:shortest=0:eof_action=repeat[l{k}]"
        )
        cur = f"l{k}"
    g.append(f"[{cur}]trim=duration={dur},format=yuv420p[out]")
    ff(
        [
            *ins,
            "-filter_complex",
            ";".join(g),
            "-map",
            "[out]",
            "-t",
            str(dur),
            *ENC,
            str(out),
        ]
    )
    return out, dur


def vidbg(name, src, ss, dur, card, vf="eq=brightness=-0.04"):
    """Full-bleed b-roll video with a transparent card on top."""
    out = SH / f"{name}.mp4"
    g = f"[0:v]fps={FPS},scale=1280:720:flags=lanczos,setsar=1,{vf}[v];[1:v]format=rgba[c];[v][c]overlay=0:0,format=yuv420p[out]"
    ff(
        [
            "-ss",
            str(ss),
            "-i",
            str(src),
            "-loop",
            "1",
            "-framerate",
            str(FPS),
            "-t",
            str(dur),
            "-i",
            str(C / f"{card}.png"),
            "-filter_complex",
            g,
            "-map",
            "[out]",
            "-t",
            str(dur),
            *ENC,
            str(out),
        ]
    )
    return out, dur


def anim(name, dur):
    return SH / f"{name}_anim.mp4", dur


def frames_to_mp4(d):
    out = d / "rec.mp4"
    if out.exists():
        return out
    f = json.loads((d / "frames.json").read_text())["frames"]
    lines = [f"file 'frames/{0:05d}.jpg'", f"duration {f[0]:.4f}"]
    for i, t in enumerate(f):
        dur = (f[i + 1] - t) if i + 1 < len(f) else 0.5
        lines += [f"file 'frames/{i:05d}.jpg'", f"duration {dur:.4f}"]
    lines.append(f"file 'frames/{len(f) - 1:05d}.jpg'")
    (d / "list.txt").write_text("\n".join(lines))
    ff(
        [
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(d / "list.txt"),
            "-vf",
            BASE,
            *ENC,
            str(out),
        ]
    )
    return out


def join(section, shots, xf=0.4):
    """xfade chain, 0.3 s fade from/to black at the ends, final encode."""
    out = OUT / f"understudy-demo-{section}.mp4"
    ins, g = [], []
    for p, _ in shots:
        ins += ["-i", str(p)]
    cur, acc = "0:v", shots[0][1]
    for k in range(1, len(shots)):
        g.append(
            f"[{cur}][{k}:v]xfade=transition=fade:duration={xf}:offset={acc - xf:.3f}[x{k}]"
        )
        cur, acc = f"x{k}", acc + shots[k][1] - xf
    g.append(
        f"[{cur}]fade=t=in:st=0:d=0.3,fade=t=out:st={acc - 0.35:.3f}:d=0.35,format=yuv420p[out]"
    )
    ff(
        [
            *ins,
            "-filter_complex",
            ";".join(g),
            "-map",
            "[out]",
            "-c:v",
            "libx264",
            "-preset",
            "medium",
            "-crf",
            "18",
            "-pix_fmt",
            "yuv420p",
            "-r",
            str(FPS),
            "-an",
            "-movflags",
            "+faststart",
            str(out),
        ]
    )
    return out, acc


def intro():
    HERO = HOME / "helloworld/understudy-replay/site-v2/media/hero.mp4"
    s = [
        vidbg("i1", HERO, 0.5, 7.0, "i_prob_ov"),
        anim("heads", 8.5),
        still("i3", "i_title", 7.4),
        layout(
            "i4",
            "i_pipev",
            15.6,  # tiles reveal on their voiceover lines
            [
                (REP / "v01_runway.mp4", 40, 170, 392, 220, 0, "", 1.8),
                (REP / "v01_skeleton.mp4", 444, 170, 392, 220, 0, "", 4.7),
                (REP / "v04_runway.mp4", 848, 170, 392, 220, 1.5, "", 7.1),
                (REP / "v01_robot.mp4", 242, 452, 392, 220, 0, "", 10.2),
                (RUN / "media/vla/v01.mp4", 646, 452, 392, 220, 0, "", 12.9),
            ],
        ),
        layout(
            "i5",
            "i_routerv",
            9.1,
            [
                (RUN / f"clips/v{v}.mp4", x, 200, 373, 210, 0)
                for v, x in (("08", 64), ("14", 453), ("20", 842))
            ],
        ),
    ]
    return join("01-intro", s, xf=0.5)


def cut(section, shots):
    """Hard cuts (exact beat timing to the voiceover), 0.3 s fade from/to black at the ends, final encode."""
    out = OUT / f"understudy-demo-{section}.mp4"
    ins = []
    for p_, _ in shots:
        ins += ["-i", str(p_)]
    acc = sum(d for _, d in shots)
    g = "".join(f"[{k}:v]" for k in range(len(shots))) + f"concat=n={len(shots)}:v=1:a=0[c];[c]fade=t=in:st=0:d=0.3,fade=t=out:st={acc - 0.35:.3f}:d=0.35,format=yuv420p[out]"
    ff([*ins, "-filter_complex", g, "-map", "[out]", "-t", f"{acc:.3f}", "-c:v", "libx264", "-preset", "medium", "-crf", "18",
        "-pix_fmt", "yuv420p", "-r", str(FPS), "-an", "-movflags", "+faststart", str(out)])
    return out, acc


def demo():
    """Re-filmed 2026-09-30: every site action is recorded in real time at the word time of the voiceover
    (record_beats.py), so section time == recording time within each beat. Section starts at 45.6 s in the film."""
    A = frames_to_mp4(W / "beatA")
    B1 = frames_to_mp4(W / "beatB1")
    B2 = frames_to_mp4(W / "beatB2n")
    s = [
        rec(  # recording lags its schedule by 0.6 s at the start (typing began at 2.55 s), so trim 0.6 s: actions land on or just before his words
            "e1",
            A,
            0.6,
            37.2,
            [
                ("c_budget", 4.9, 9.0),
                ("c_cheap", 9.0, 14.5),
                ("c_best", 14.7, 18.4),
                ("c_dry", 18.5, 23.2),
                ("c_train", 24.4, 34.2),
                ("c_stats", 34.4, 37.2),
            ],
        ),
        layout(
            "e4",
            "d_step2",
            4.7,
            [
                (REP / "v01_runway.mp4", 30, 190, 600, 338, 0),
                (REP / "v01_skeleton.mp4", 650, 190, 600, 338, 0),
            ],
        ),
        layout(
            "e5",
            "d_step3",
            4.3,
            [
                (REP / "v04_runway.mp4", 30, 190, 600, 338, 2.0),
                (REP / "v01_runway.mp4", 650, 190, 600, 338, 0),
            ],
        ),
        layout(
            "e6",
            "d_step4",
            5.4,
            [
                (REP / "v01_runway.mp4", 30, 190, 600, 338, 0),
                (REP / "v01_robot.mp4", 650, 190, 600, 338, 0),
            ],
        ),
        still("e7", "b_prompt", 12.3),  # PhyT2V line
        still("e8", "d_step5", 9.0),  # RunPod line
        rec("e9", B1, 0.0, 14.2, [("c_lib", 0.2, 8.7), ("c_film", 9.1, 14.2)]),
        rec("e10", B2, 1.2, 7.5, [("c_pushlib", 3.6, 7.5)]),
    ]
    return cut("02-demo", s)


def bench():
    b = frames_to_mp4(W / "bench")
    s = [
        rec("b1", b, 0.8, 6.7),
        still("b2", "b_same", 11.3),
        still("b3", "b_num", 9.6),
        still("b4", "b_honest", 11.9),
    ]
    return join("03-benchmark", s, xf=0.5)


def routing():
    return join(
        "04-routing",
        [
            push("r1", C / "r_routers@2x.png", 4.7, None, z0=1.0, z1=1.03),
            still("r2", "r_budget", 11.3),
        ],
        xf=0.4,
    )


def push(name, img, dur, card=None, z0=1.0, z1=1.06, dx=0.0, dy=0.0, cap_in=0.35):
    """Sub-pixel push-in on a still (PIL affine, bicubic) with an optional transparent card faded in."""
    import numpy as np
    from PIL import Image

    out = SH / f"{name}.mp4"
    src = Image.open(img).convert("RGB")
    s0 = max(1280 / src.width, 720 / src.height)
    pre = 1.15  # pre-downscale with lanczos so the per-frame bicubic resample never aliases
    k = min(1.0, s0 * z1 * pre)
    src = src.resize((round(src.width * k), round(src.height * k)), Image.LANCZOS)
    s0 = max(1280 / src.width, 720 / src.height)
    ov = (
        np.asarray(Image.open(C / f"{card}.png").convert("RGBA"), dtype=np.float32)
        / 255
        if card
        else None
    )
    n = round(dur * FPS)
    p = subprocess.Popen(
        [
            "nice",
            "-n",
            "19",
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-f",
            "rawvideo",
            "-pix_fmt",
            "rgb24",
            "-s",
            "1280x720",
            "-r",
            str(FPS),
            "-i",
            "-",
            *ENC,
            str(out),
        ],
        stdin=subprocess.PIPE,
    )
    for i in range(n):
        u = i / max(1, n - 1)
        e = u * u * (3 - 2 * u) * 0.5 + u * 0.5  # gentle ease, never stops moving
        s = s0 * (z0 + (z1 - z0) * e)
        cx = src.width / 2 + dx * e * src.width
        cy = src.height / 2 + dy * e * src.height
        f = src.transform(
            (1280, 720),
            Image.AFFINE,
            (1 / s, 0, cx - 640 / s, 0, 1 / s, cy - 360 / s),
            resample=Image.BICUBIC,
        )
        if ov is not None:
            t = i / FPS
            a = min(1.0, max(0.0, (t - cap_in) / 0.4)) * min(
                1.0, max(0.0, (dur - t) / 0.3)
            )
            fr = np.asarray(f, dtype=np.float32) / 255
            al = ov[..., 3:4] * a
            f = Image.fromarray(
                np.clip((fr * (1 - al) + ov[..., :3] * al) * 255 + 0.5, 0, 255).astype(
                    np.uint8
                )
            )
        p.stdin.write(f.tobytes())
    p.stdin.close()
    p.wait()
    return out, dur


def students():
    G = W / "gen"
    site = frames_to_mp4(W / "site")
    last = G / "v_desk.mp4"
    s = [
        push("s1", G / "desk.png", 3.85, "s1_ov", dx=0.02, cap_in=0.3),
        push("s6", G / "hack.png", 2.95, "s6_ov", z0=1.05, z1=1.0, dy=0.01),
        rec("s4", site, 0.3, 3.45, [("s4_ov", 0.55, 3.45)]),
        push("s5c", C / "s_cost@2x.png", 12.85, None, z0=1.0, z1=1.03),  # DROID / rig / cost lines
        rec("s7", last, 0.0, 5.0, [("s7_ov", 0.3, 5.0)], holds=[(4.95, 0.7)])
        if last.exists()
        else push("s7", G / "arm.png", 5.7, "s7_ov", dy=-0.01),
    ]
    return join("04b-students", s, xf=0.45)


def close():
    return join("05-close", [still("z1", "z_close", 5.61)])


if __name__ == "__main__":
    fn = {
        "intro": intro,
        "demo": demo,
        "bench": bench,
        "routing": routing,
        "students": students,
        "close": close,
    }[sys.argv[1]]
    out, dur = fn()
    real = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "csv=p=0",
            str(out),
        ],
        capture_output=True,
        text=True,
    ).stdout.strip()
    print(f"DONE {sys.argv[1]} {out} {real}s", flush=True)
