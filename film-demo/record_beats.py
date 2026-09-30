# Records the demo beats on the live site in real time, with every action scheduled at the voiceover's word time.
# usage: work/.venv/bin/python record_beats.py <A|B1|B2> <outdir>
#   A : section 0-37.5 s  (type prompt, $2, $10, GPU, Train, replayed run)
#   B1: library then the pick tile's overview (section 72.3 s onwards)
#   B2: new push prompt, Train, new tile on top (section 86.5 s onwards)
import base64
import json
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

URL = "https://understudy-replay.vercel.app"
beat, out = sys.argv[1], Path(sys.argv[2])
fr = out / "frames"
fr.mkdir(parents=True, exist_ok=True)
frames, events = [], []
T0 = [None]
ROUTE = "() => { const e=[...document.querySelectorAll('body *')].find(n=>n.children.length<6 && /a run:/.test(n.innerText||'') && (n.innerText||'').length<200); return e ? e.innerText.replace(/\\n/g,' ') : ''; }"


def now():
    return time.time() - T0[0]


def at(page, t, name):
    d = t - now()
    if d > 0:
        page.wait_for_timeout(d * 1000)
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
    ctx = b.new_context(
        viewport={"width": 1280, "height": 720}, device_scale_factor=1.5
    )
    page = ctx.new_page()
    page.goto(URL, wait_until="networkidle")
    page.evaluate("window.scrollTo(0,0)")
    if beat == "A":
        page.click(
            "button:text-is('$6')"
        )  # so the $2 click visibly changes the route line
    if beat == "B1":
        page.evaluate(
            "window.scrollTo(0, document.querySelector('#grid').getBoundingClientRect().top+scrollY-110)"
        )
        page.evaluate(
            "Promise.all([...document.querySelectorAll('#grid video')].map(v => v.readyState >= 2 ? 1 : new Promise(r => { v.addEventListener('loadeddata', r, {once: true}); setTimeout(r, 6000); })))"
        )
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
    if beat == "A":
        at(page, 0.0, "hero")
        at(page, 1.9, "type_pick")
        page.click("#prompt")
        page.keyboard.type("put the red block in the bowl", delay=60)
        at(page, 6.8, "budget_2")
        page.click("button:text-is('$2')")
        page.wait_for_timeout(300)
        print("   route:", page.evaluate(ROUTE))
        at(page, 14.0, "budget_10")
        page.click("button:text-is('$10')")
        page.wait_for_timeout(300)
        print("   route:", page.evaluate(ROUTE))
        at(page, 24.0, "gpu")
        page.click("[data-gpu='l40s']")
        at(page, 26.0, "train")
        page.click("#go")
        at(page, 38.0, "end")
    elif beat == "B1":
        at(page, 0.0, "library")
        at(page, 8.9, "open_tile")
        tile = (
            page.locator("#grid .tile")
            .filter(has_text="put the red block in the bowl")
            .first
        )
        (tile.locator("video").first if tile.locator("video").count() else tile).click()
        at(page, 15.0, "end")
    else:
        at(page, 0.0, "hero")
        at(page, 0.2, "type_push")
        page.click("#prompt")
        page.keyboard.type("push the red block onto the blue square", delay=8)
        at(page, 1.5, "train_push")
        page.click("#go")
        at(page, 7.5, "end")
    cdp.send("Page.stopScreencast")
    page.wait_for_timeout(300)
    b.close()

(out / "frames.json").write_text(json.dumps({"frames": frames, "events": events}))
print("frames", len(frames), "dur", frames[-1] if frames else 0)
