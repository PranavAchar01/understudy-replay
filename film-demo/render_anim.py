# Renders an anim.html scene on a virtual clock (window.seek) to work/shots/<scene>_anim.mp4, 720p30.
import subprocess
import sys
from pathlib import Path
from playwright.sync_api import sync_playwright

scene = sys.argv[1]
src = Path("anim.html").resolve()
out = Path("work/shots") / f"{scene}_anim.mp4"
out.parent.mkdir(parents=True, exist_ok=True)
ff = subprocess.Popen(["nice", "-n", "19", "ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "image2pipe", "-framerate", "30",
                       "-c:v", "png", "-i", "-", "-c:v", "libx264", "-preset", "veryfast", "-crf", "16", "-pix_fmt", "yuv420p", "-r", "30", str(out)],
                      stdin=subprocess.PIPE)
with sync_playwright() as p:
    b = p.chromium.launch()
    pg = b.new_page(viewport={"width": 1280, "height": 720}, device_scale_factor=1)
    pg.goto(f"file://{src}?s={scene}", wait_until="networkidle")
    pg.evaluate("document.fonts.ready")
    pg.wait_for_timeout(300)
    dur = pg.evaluate("window.DURATION")
    for k in range(round(dur * 30)):
        pg.evaluate(f"window.seek({k / 30})")
        ff.stdin.write(pg.screenshot(type="png"))
    b.close()
ff.stdin.close()
ff.wait()
print("wrote", out, dur)
