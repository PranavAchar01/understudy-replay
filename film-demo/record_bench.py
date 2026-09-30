import base64
import json
import sys
import time
from pathlib import Path
from playwright.sync_api import sync_playwright

out = Path(sys.argv[1])
fr = out / "frames"
fr.mkdir(parents=True, exist_ok=True)
frames = []
with sync_playwright() as p:
    b = p.chromium.launch(args=["--hide-scrollbars", "--autoplay-policy=no-user-gesture-required", "--mute-audio"])
    ctx = b.new_context(viewport={"width": 1280, "height": 720}, device_scale_factor=1.5)
    page = ctx.new_page()
    cdp = ctx.new_cdp_session(page)
    t0 = [time.time()]

    def on_frame(params):
        (fr / f"{len(frames):05d}.jpg").write_bytes(base64.b64decode(params["data"]))
        frames.append(round(time.time() - t0[0], 4))
        cdp.send("Page.screencastFrameAck", {"sessionId": params["sessionId"]})

    cdp.on("Page.screencastFrame", on_frame)
    page.goto("https://understudy-benchmark.vercel.app", wait_until="commit")
    cdp.send("Page.startScreencast", {"format": "jpeg", "quality": 92, "maxWidth": 1920, "maxHeight": 1080})
    page.wait_for_timeout(18000)
    cdp.send("Page.stopScreencast")
    b.close()
(out / "frames.json").write_text(json.dumps({"frames": frames}))
print(len(frames), frames[-1])
