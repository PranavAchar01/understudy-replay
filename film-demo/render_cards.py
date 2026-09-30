import re
import sys
from pathlib import Path
from playwright.sync_api import sync_playwright

src = Path("cards.html").resolve()
ids = re.findall(r'<section class="card[^"]*" id="([a-z0-9_]+)"', src.read_text())
only = sys.argv[1:] or ids
out = Path("work/cards")
out.mkdir(parents=True, exist_ok=True)
with sync_playwright() as p:
    b = p.chromium.launch()
    pg = b.new_page(viewport={"width": 1280, "height": 720}, device_scale_factor=1)
    for i in only:
        pg.goto(f"file://{src}?c={i}", wait_until="networkidle")
        pg.evaluate("document.fonts.ready")
        pg.wait_for_timeout(150)
        pg.screenshot(path=str(out / f"{i}.png"), omit_background=i.startswith("c_") or i.endswith("_ov"))
    b.close()
print(len(only), "cards")
