# Records the live Understudy site with CDP screencast (JPEG q92), writing frames + timestamps and an event log.
# usage: uv run --no-project --with playwright python record_site.py <outdir>
import base64
import json
import sys
import time
from pathlib import Path
from playwright.sync_api import sync_playwright

URL = "https://understudy-replay.vercel.app"
out = Path(sys.argv[1])
fr = out / "frames"
fr.mkdir(parents=True, exist_ok=True)
frames, events = [], []
T0 = [None]


def now():
    return time.time() - T0[0]


def ev(name):
    events.append({"t": round(now(), 3), "e": name})
    print(f"{now():6.2f}s {name}", flush=True)


with sync_playwright() as p:
    b = p.chromium.launch(
        args=[
            "--hide-scrollbars",
            "--autoplay-policy=no-user-gesture-required",
            "--mute-audio",
        ]
    )
    ctx = b.new_context(viewport={"width": 1280, "height": 720}, device_scale_factor=1.5)
    page = ctx.new_page()
    page.goto(URL, wait_until="networkidle")
    page.evaluate("window.scrollTo(0,0)")
    page.wait_for_timeout(2500)
    cdp = ctx.new_cdp_session(page)

    def on_frame(params):
        i = len(frames)
        (fr / f"{i:05d}.jpg").write_bytes(base64.b64decode(params["data"]))
        frames.append(round(now(), 4))
        cdp.send("Page.screencastFrameAck", {"sessionId": params["sessionId"]})

    cdp.on("Page.screencastFrame", on_frame)
    T0[0] = time.time()
    cdp.send(
        "Page.startScreencast",
        {
            "format": "jpeg",
            "quality": 92,
            "maxWidth": 1920,
            "maxHeight": 1080,
            "everyNthFrame": 1,
        },
    )
    W = page.wait_for_timeout
    ev("hero")
    W(3500)
    page.click("#prompt")
    page.fill("#prompt", "")
    ev("type_fold")
    page.keyboard.type("fold the laundry", delay=85)
    W(600)
    ev("pill_best")
    W(3800)
    page.click("#prompt", click_count=3)
    page.keyboard.press("Meta+A")
    page.keyboard.press("Backspace")
    W(300)
    ev("type_pick")
    page.keyboard.type("put the red block in the bowl", delay=60)
    W(600)
    ev("pill_cheap")
    W(3200)
    ev("train")
    page.click("#go")
    W(700)
    ev("run_start")
    W(10500)
    ev("run_done")
    W(3000)
    page.mouse.wheel(0, 300)
    W(1500)
    ev("library")
    W(3500)
    tile = page.locator("#grid .tile video").first
    ev("open_tile")
    tile.click()
    W(7000)
    ev("close_tile")
    page.keyboard.press("Escape")
    W(400)
    if page.locator("#sheet").is_visible():
        page.click("#sheet-close")
    W(900)
    page.evaluate("window.scrollTo({top:0,behavior:'smooth'})")
    W(1600)
    page.click("#prompt", click_count=3)
    page.keyboard.press("Meta+A")
    page.keyboard.press("Backspace")
    W(200)
    ev("type_push")
    page.keyboard.type("push the red block onto the blue square", delay=50)
    W(700)
    ev("pill_push")
    W(2200)
    ev("train_push")
    page.click("#go")
    W(700)
    W(10500)
    ev("push_done")
    W(2500)
    page.mouse.wheel(0, 300)
    W(1200)
    ev("push_library")
    W(4000)
    ev("end")
    cdp.send("Page.stopScreencast")
    W(300)
    b.close()

(out / "frames.json").write_text(json.dumps({"frames": frames, "events": events}))
print("frames", len(frames), "dur", frames[-1] if frames else 0)
