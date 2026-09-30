# Records the pick tile's overview on the live site: training timeline, then a smooth scroll to the Runway video gallery.
# usage: work/.venv/bin/python record_gallery.py work/gallery
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


SCROLL = """([sel, dur]) => new Promise(res => {
  const p = document.querySelector('.sheet-panel'), g = document.querySelector(sel);
  const a = p.scrollTop, b = Math.min(p.scrollHeight - p.clientHeight, a + g.getBoundingClientRect().top - p.getBoundingClientRect().top - 24);
  const t0 = performance.now();
  const step = t => { const u = Math.min(1, (t - t0) / dur), e = u < .5 ? 4*u*u*u : 1 - Math.pow(-2*u + 2, 3) / 2;
    p.scrollTop = a + (b - a) * e; u < 1 ? requestAnimationFrame(step) : res(b); };
  requestAnimationFrame(step); })"""

with sync_playwright() as p:
    b = p.chromium.launch(
        args=[
            "--hide-scrollbars",
            "--autoplay-policy=no-user-gesture-required",
            "--mute-audio",
        ]
    )
    ctx = b.new_context(
        viewport={"width": 1280, "height": 720}, device_scale_factor=1.5
    )
    page = ctx.new_page()
    page.goto(URL, wait_until="networkidle")
    tile = (
        page.locator("#grid .tile")
        .filter(has_text="put the red block in the bowl")
        .first
    )
    tile.scroll_into_view_if_needed()
    page.evaluate("window.scrollBy(0,-120)")
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
    ev("tiles")
    W(1200)
    ev("open_tile")
    (tile.locator("video").first if tile.locator("video").count() else tile).click()
    W(5500)
    # let every gallery video load before it scrolls into view
    page.evaluate(
        "Promise.all([...document.querySelectorAll('#ov-gallery video')].map(v => v.readyState >= 2 ? 1 : new Promise(r => { v.addEventListener('loadeddata', r, {once: true}); setTimeout(r, 6000); })))"
    )
    ev("scroll_gallery")
    page.evaluate(SCROLL, ["#ov-gallery", 2600])
    ev("gallery")
    W(5500)
    ev("end")
    cdp.send("Page.stopScreencast")
    W(300)
    b.close()

(out / "frames.json").write_text(json.dumps({"frames": frames, "events": events}))
print("frames", len(frames), "dur", frames[-1] if frames else 0)
