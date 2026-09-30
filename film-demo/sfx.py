# Synthesizes the quiet SFX track for the whole film (48 kHz stereo), muxes each section's slice into its mp4,
# then builds the final cut: video streams concatenated losslessly + one continuous AAC track.
# usage: python sfx.py [sections...]   (default: all)  |  python sfx.py --final
import subprocess
import sys
import wave
from pathlib import Path

import numpy as np

SR = 48000
FD = Path(__file__).resolve().parent
W = FD / "work"
DL = Path.home() / "Downloads"
rng = np.random.default_rng(7)

# (file suffix, shot durations, xfade) mirroring build.py
SECTIONS = [
    ("01-intro", [7.0, 8.5, 7.4, 15.6, 9.1], 0.5),
    ("02-demo", [36.6, 4.7, 4.3, 5.4, 12.3, 9.0, 14.2, 6.3], 0.0),
    ("03-benchmark", [5.9, 11.3, 9.6, 11.9], 0.5),
    ("04-routing", [4.7, 11.3], 0.4),
    ("04b-students", [3.85, 2.95, 3.15, 12.85, 5.7], 0.45),
    ("05-close", [5.61], 0.4),
]
# card / pill events: (section, shot index, time in shot, kind)
CUES = {
    "01-intro": [(3, t, "tick_s") for t in (1.8, 4.7, 7.1, 10.2, 12.9)],
    "02-demo": [
        (0, 6.8, "pill"),
        (0, 14.0, "pill"),
        (0, 24.0, "tick_s"),
        (0, 26.0, "tick"),
        (6, 0.2, "tick"),
        (6, 8.9, "tick"),
        (7, 1.7, "tick"),
    ],
    "03-benchmark": [],
    "04-routing": [(0, 0.6, "tick"), (1, 0.5, "pill"), (1, 1.2, "tick_s")],
    "04b-students": [
        (k, t, "tick_s")
        for k, t in ((0, 0.3), (1, 0.35), (2, 0.25), (3, 0.3), (4, 0.3))
    ],
    "05-close": [],
}
VOICE = W / "voice.wav"  # cut voiceover, mono 48 kHz, ~-16 LUFS


def db(x):
    return 10 ** (x / 20)


def probe(p):
    out = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-count_packets",
            "-show_entries",
            "stream=nb_read_packets",
            "-of",
            "csv=p=0",
            str(p),
        ],
        capture_output=True,
        text=True,
    ).stdout.strip()
    return int(out) / 30


def band(n, lo, hi):
    x = rng.standard_normal(n)
    X = np.fft.rfft(x)
    f = np.fft.rfftfreq(n, 1 / SR)
    X *= np.exp(
        -0.5
        * (
            (np.log(np.maximum(f, 1)) - np.log(np.sqrt(lo * hi)))
            / (np.log(hi / lo) / 2)
        )
        ** 2
    )
    y = np.fft.irfft(X, n)
    return y / np.abs(y).max()


def whoosh(peak_db=-24, dur=1.1, peak_at=0.45):
    n = int(dur * SR)
    t = np.arange(n) / SR
    env = np.where(
        t < peak_at,
        (t / peak_at) ** 2.2,
        np.exp(-(t - peak_at) / (dur - peak_at) * 4.5),
    )
    lo, hi = band(n, 180, 900), band(n, 900, 4500)
    mix = np.clip(t / peak_at, 0, 1)  # brightens toward the cut
    y = (lo * (1 - 0.6 * mix) + hi * 0.55 * mix) * env
    pan = np.clip(t / dur, 0, 1)
    L, R = (
        y * np.cos(pan * np.pi / 2 * 0.6 + 0.3),
        y * np.sin(pan * np.pi / 2 * 0.6 + 0.3),
    )
    s = np.stack([L, R], 1)
    return s / np.abs(s).max() * db(peak_db)


def tick(peak_db=-31, f=2300, dur=0.06):
    n = int(dur * SR)
    t = np.arange(n) / SR
    y = np.sin(2 * np.pi * f * t) * np.exp(-t / 0.012) + 0.25 * band(
        n, 3000, 8000
    ) * np.exp(-t / 0.004)
    y = y / np.abs(y).max() * db(peak_db)
    return np.stack([y, y], 1)


def pill():  # two soft notes, the route pill flipping
    a, b = tick(-28, 1760, 0.09), tick(-29, 2640, 0.12)
    out = np.zeros((a.shape[0] + int(0.07 * SR) + b.shape[0], 2))
    out[: a.shape[0]] += a
    out[int(0.07 * SR) : int(0.07 * SR) + b.shape[0]] += b
    return out


def tone(freqs, dur, att, rel, peak_db):
    n = int(dur * SR)
    t = np.arange(n) / SR
    y = sum(np.sin(2 * np.pi * f * t + k) / (1 + k * 0.6) for k, f in enumerate(freqs))
    y *= 1 + 0.08 * np.sin(2 * np.pi * 0.35 * t)  # slow breathing
    env = np.minimum(
        np.clip(t / att, 0, 1) ** 1.5, np.clip((dur - t) / rel, 0, 1) ** 1.5
    )
    y = y * env
    L = y
    R = np.roll(y, int(0.004 * SR))
    s = np.stack([L, R], 1)
    return s / np.abs(s).max() * db(peak_db)


def resolve():
    n = int(6.5 * SR)
    t = np.arange(n) / SR
    y = np.zeros(n)
    for k, f in enumerate(
        (110.0, 164.8, 220.0, 277.2, 329.6)
    ):  # A major, notes rolled in gently
        st = 0.09 * k
        tt = np.clip(t - st, 0, None)
        e = (tt > 0) * np.minimum(tt / 0.25, 1) * np.exp(-tt / 2.4)
        y += (
            (np.sin(2 * np.pi * f * tt) + 0.15 * np.sin(4 * np.pi * f * tt))
            * e
            / (1 + 0.3 * k)
        )
    s = np.stack([y, np.roll(y, int(0.006 * SR))], 1)
    return s / np.abs(s).max() * db(-19)


def place(buf, clip, t):
    i = int(round(t * SR))
    if i < 0:
        clip, i = clip[-i:], 0
    j = min(buf.shape[0], i + clip.shape[0])
    buf[i:j] += clip[: j - i]


def build():
    durs = [probe(DL / f"understudy-demo-{s}.mp4") for s, _, _ in SECTIONS]
    total = sum(durs)
    buf = np.zeros((int(round(total * SR)) + SR, 2))
    off = 0.0
    for (sec, shots, xf), d in zip(SECTIONS, durs):
        starts = [sum(shots[:k]) - k * xf for k in range(len(shots))]
        if sec == "01-intro":
            place(buf, whoosh(-30, 1.4, 0.6), 0.0)
        else:  # section cut: whoosh straddles the boundary, peaking just after it
            place(buf, whoosh(-23, 1.1, 0.45), off - 0.3)
        for k in range(1, len(shots)):  # shot crossfades: faint air
            place(buf, whoosh(-34, 0.7, 0.3), off + starts[k] - 0.05)
        for k, t, kind in CUES[sec]:
            place(
                buf,
                {"tick": tick(), "tick_s": tick(-35, 2000, 0.05), "pill": pill()}[kind],
                off + starts[k] + t,
            )
        if sec == "01-intro":  # low soft tone under the title card (shot 2)
            place(
                buf,
                tone([55.0, 110.0, 164.8], 6.0, 1.2, 2.0, -22),
                off + starts[2] - 0.4,
            )
        if sec == "05-close":
            place(buf, tone([55.0, 110.0], d, 1.5, 2.0, -30), off)
            place(buf, resolve(), off + 0.25)
        off += d
    buf = buf[: int(round(total * SR))]
    pk = np.abs(buf).max()
    if pk > db(-18):
        buf *= db(-18) / pk
    if VOICE.exists():
        buf = mix_voice(buf)
    return buf, durs


def mix_voice(sfx):
    """Voice on top; SFX ducked 12 dB under speech (smoothed envelope), so the voice always dominates."""
    with wave.open(str(VOICE)) as w:
        v = np.frombuffer(w.readframes(w.getnframes()), "<i2").astype(np.float64) / 32768
    v *= db(-3.0)  # mono voice is played on both channels: -3 dB keeps the stereo mix at ~-16 LUFS
    n = sfx.shape[0]
    v = np.pad(v, (0, max(0, n - v.size)))[:n]
    h = int(0.02 * SR)
    m = n // h
    e = np.sqrt((v[: m * h].reshape(m, h) ** 2).mean(1))
    talk = (e > db(-42)).astype(np.float64)
    k = 15  # 300 ms hold either side, then smoothed ramps
    talk = np.convolve(talk, np.ones(2 * k + 1), "same") > 0
    g = np.where(talk, db(-12), 1.0)
    g = np.convolve(g, np.ones(8) / 8, "same")
    g = np.repeat(g, h)
    g = np.pad(g, (0, n - g.size), mode="edge")
    out = sfx * g[:, None] + v[:, None]
    pk = np.abs(out).max()
    if pk > db(-1.0):
        out *= db(-1.0) / pk
    return out


def write_wav(p, a):
    x = (np.clip(a, -1, 1) * 32767).astype("<i2")
    with wave.open(str(p), "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(x.tobytes())


def ff(*a):
    subprocess.run(
        ["nice", "-n", "19", "ffmpeg", "-hide_banner", "-loglevel", "error", "-y", *a],
        check=True,
    )


if __name__ == "__main__":
    buf, durs = build()
    A = W / "audio"
    A.mkdir(exist_ok=True)
    write_wav(A / "full.wav", buf)
    only = [a for a in sys.argv[1:] if not a.startswith("--")]
    off = 0
    for (sec, _, _), d in zip(SECTIONS, durs):
        n = int(round(d * SR))
        seg = buf[off : off + n]
        off += n
        if only and sec not in only:
            continue
        write_wav(A / f"{sec}.wav", seg)
        src = DL / f"understudy-demo-{sec}.mp4"
        tmp = A / f"{sec}.mp4"
        ff(
            "-i",
            str(src),
            "-i",
            str(A / f"{sec}.wav"),
            "-map",
            "0:v:0",
            "-map",
            "1:a:0",
            "-c:v",
            "copy",
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            "-ar",
            "48000",
            "-t",
            f"{d:.3f}",
            "-movflags",
            "+faststart",
            str(tmp),
        )
        tmp.replace(src)
        print("muxed", sec, f"{d:.2f}s", flush=True)
    if "--final" in sys.argv:
        lst = W / "concat.txt"
        lst.write_text(
            "".join(
                f"file '{DL / f'understudy-demo-{s}.mp4'}'\n" for s, _, _ in SECTIONS
            )
        )
        ff(
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(lst),
            "-i",
            str(A / "full.wav"),
            "-map",
            "0:v:0",
            "-map",
            "1:a:0",
            "-c:v",
            "copy",
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            "-ar",
            "48000",
            "-movflags",
            "+faststart",
            str(DL / "understudy-demo-720p.mp4"),
        )
        print("final", DL / "understudy-demo-720p.mp4", f"{sum(durs):.2f}s", flush=True)
