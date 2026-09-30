// Film v3 check: screenshots of one deck shot at chosen moments, at the film's true 1920x1080.
// usage: tsx film/tools/stills.mts <out-dir> <deck-url> <shot> <ms,ms,...>
import { mkdir } from "node:fs/promises";
import puppeteer from "puppeteer-core";

const [out, deck, shot, times] = process.argv.slice(2);
const CHROME = `${process.env.HOME}/Library/Caches/ms-playwright/chromium-1234/chrome-mac-arm64/Google Chrome for Testing.app/Contents/MacOS/Google Chrome for Testing`;
await mkdir(out, { recursive: true });
const browser = await puppeteer.launch({
  executablePath: CHROME,
  headless: true,
  args: ["--force-device-scale-factor=1", "--hide-scrollbars", "--autoplay-policy=no-user-gesture-required"],
  defaultViewport: { width: 1920, height: 1080, deviceScaleFactor: 1 },
});
const page = await browser.newPage();
page.on("pageerror", (e) => console.log("pageerror", String(e).slice(0, 200)));
page.on("console", (m) => m.type() === "error" && console.log("console", m.text().slice(0, 200)));
await page.goto(`${deck}${deck.includes("?") ? "&" : "?"}shot=${shot}`, { waitUntil: "load", timeout: 120_000 });
await page.waitForFunction("window.deckReady === true", { timeout: 60_000 });
await page.evaluate(() => document.fonts.ready);
// the page shows the shot as soon as it is ready; re-show it so every timer starts now
await page.keyboard.press("ArrowLeft");
await page.keyboard.press("ArrowRight");
const t0 = Date.now();
for (const ms of times.split(",").map(Number)) {
  const wait = ms - (Date.now() - t0);
  if (wait > 0) await new Promise((r) => setTimeout(r, wait));
  await page.screenshot({ path: `${out}/s${shot}-${String(ms).padStart(5, "0")}.png` });
}
await browser.close();
