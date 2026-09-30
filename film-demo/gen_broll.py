# Generates "Built for students" b-roll with the Runway Model Router (demo-best images, demo-best video).
# Key is read from Keychain and never printed. Outputs land in work/gen/<name>.{png,mp4} plus <name>.json.
import json
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import requests

OUT = Path(__file__).resolve().parent / "work/gen"
OUT.mkdir(parents=True, exist_ok=True)
KEY = subprocess.run(
    ["security", "find-generic-password", "-s", "RUNWAY_API_KEY", "-w"],
    capture_output=True,
    text=True,
    check=True,
).stdout.strip()
API = "https://api.dev.runwayml.com/v1"
H = {
    "Authorization": f"Bearer {KEY}",
    "X-Runway-Version": "2024-11-06",
    "Content-Type": "application/json",
}
STYLE = "Photorealistic cinematic photograph, warm tungsten light, shallow depth of field, 35mm film look, unbranded plain objects, text-free surfaces."
ARM = "a small low-cost hobby robot arm built from white 3D-printed parts and small black servo motors"

IMAGES = {
    "desk": f"A college student seen from behind, face turned away from camera, sitting at a small desk at night, laptop open showing a dark minimal web app, {ARM} clamped to the desk beside the laptop. {STYLE}",
    "dorm": f"Wide shot of a cozy small dorm room at night with warm string lights, a lofted bed, a desk under the window holding a laptop and {ARM}. The room is empty of people. {STYLE}",
    "bench": f"A community college lab bench in late afternoon sunlight through tall windows, {ARM} clamped to a worn wooden workbench, a laptop, jumper wires and a small red cube next to a ceramic bowl. The room is empty of people. {STYLE}",
    "hack": f"A hackathon table late at night seen from above at an angle, several open laptops, sticky notes, paper cups, {ARM} in the middle of the table, hands typing on keyboards with faces out of frame. {STYLE}",
    "arm": f"Close-up of {ARM}, its two-finger gripper holding a small red cube above a white ceramic bowl on a wooden desk, a laptop glowing softly in the blurred background. {STYLE}",
}
VIDEOS = {
    "v_desk": f"Slow cinematic dolly-in across a small desk at night: {ARM} slowly lowers a small red cube into a white ceramic bowl, a laptop glows beside it, warm lamp light, shallow depth of field, photorealistic, unbranded objects, no people in frame.",
}


def run(name, kind, body):
    if (OUT / f"{name}.json").exists():
        return name, "cached"
    r = requests.post(f"{API}/generate/{kind}", headers=H, json=body, timeout=60)
    if r.status_code >= 300:
        return name, f"submit {r.status_code} {r.text[:300]}"
    tid = r.json()["id"]
    t0 = time.time()
    while time.time() - t0 < 900:
        time.sleep(6)
        t = requests.get(f"{API}/tasks/{tid}", headers=H, timeout=60).json()
        st = t.get("status")
        if st == "SUCCEEDED":
            url = t["output"][0]
            ext = "mp4" if kind == "video" else "png"
            (OUT / f"{name}.{ext}").write_bytes(requests.get(url, timeout=300).content)
            meta = {k: v for k, v in t.items() if k != "output"}
            meta["seconds"] = round(time.time() - t0, 1)
            (OUT / f"{name}.json").write_text(json.dumps(meta, indent=1))
            return name, f"ok {meta['seconds']}s"
        if st in ("FAILED", "CANCELLED"):
            return name, f"{st} {json.dumps(t)[:300]}"
    return name, "timeout"


jobs = [
    (
        n,
        "image",
        {"configId": "demo-best", "input": {"promptText": p, "aspectRatio": "16:9"}},
    )
    for n, p in IMAGES.items()
]
if "--no-video" not in sys.argv:
    jobs += [
        (
            n,
            "video",
            {
                "configId": "demo-best",
                "input": {"promptText": p, "aspectRatio": "16:9", "duration": 5},
            },
        )
        for n, p in VIDEOS.items()
    ]
with ThreadPoolExecutor(8) as ex:
    for name, res in ex.map(lambda j: run(*j), jobs):
        print(name, res, flush=True)
