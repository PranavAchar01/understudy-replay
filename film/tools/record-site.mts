// Records the site demo for film v8 (the middle 1:20): a scripted user on the real page, frame by frame at 30 fps.
//
// The page runs with ?film (this script owns its clock: window.__film.frame(t) per frame, then a screenshot) and
// ?replay=<slug>: the sentence is typed and checked by the live planner, the buttons are clicked with real mouse
// events, and the two stages play the run's saved events at a compressed pace (site/app.js, "replay a saved run").
// Then the gates of an accepted clip are opened and scrolled, and the dataset / SmolVLA panel is shown.
//
// usage: tsx film/tools/record-site.mts <out.mp4> [--url http://127.0.0.1:8765/?film&replay=<slug>] [--secs 80]
//        [--task "put the red block in the bowl"] [--stills s,s,...]
// env:   CHROME (browser binary), CHROME_ARGS (e.g. "--no-sandbox" as root), WEBM_DIR (a Chromium without H.264
//        gets <name>.webm from this folder for every <name>.mp4 the page asks for)
import { spawn } from "node:child_process";
import { existsSync, readFileSync, writeFileSync } from "node:fs";
import puppeteer, { type Page } from "puppeteer-core";

const out = process.argv[2];
const arg = (k: string) => { const i = process.argv.indexOf(`--${k}`); return i > 0 ? process.argv[i + 1] : undefined; };
const SLUG = arg("slug") ?? "put-the-red-block-in-the-bowl";
const URL = arg("url") ?? `http://127.0.0.1:8765/?film&replay=${SLUG}`;
const TASK = arg("task") ?? "put the red block in the bowl";
const SECS = Number(arg("secs") ?? 80);
const FPS = 30;
const stills = arg("stills")?.split(",").map(Number);
const CHROME = process.env.CHROME ?? `${process.env.HOME}/Library/Caches/ms-playwright/chromium-1234/chrome-mac-arm64/Google Chrome for Testing.app/Contents/MacOS/Google Chrome for Testing`;

const browser = await puppeteer.launch({
  executablePath: CHROME, headless: true,
  args: ["--force-device-scale-factor=1", "--hide-scrollbars", "--autoplay-policy=no-user-gesture-required", "--mute-audio", ...(process.env.CHROME_ARGS?.split(" ").filter(Boolean) ?? [])],
  defaultViewport: { width: 1920, height: 1080, deviceScaleFactor: 1 }, protocolTimeout: 900_000,
});
const page: Page = await browser.newPage();
page.on("pageerror", (e) => console.log("pageerror", String(e).slice(0, 300)));
page.on("console", (m) => { if (m.type() === "error" && !/404|ERR_CERT/.test(m.text())) console.log("console", m.text().slice(0, 300)); });
if (process.env.WEBM_DIR) {
  await page.setRequestInterception(true);
  page.on("request", (r) => {
    const m = r.url().match(/\/([^/?]+)\.mp4(\?|$)/);
    const f = m && `${process.env.WEBM_DIR}/${m[1]}.webm`;
    if (f && existsSync(f)) r.respond({ status: 200, contentType: "video/webm", body: readFileSync(f) });
    else r.continue();
  });
}
await page.goto(URL, { waitUntil: "networkidle2", timeout: 120_000 });
await page.evaluate(() => (window as any).__film.ready());

const ff = stills ? null : spawn("ffmpeg", ["-hide_banner", "-loglevel", "error", "-y", "-f", "image2pipe", "-framerate", String(FPS), "-c:v", "png", "-i", "-",
  "-c:v", "libx264", "-preset", "slow", "-crf", "14", "-pix_fmt", "yuv420p", "-r", String(FPS), "-an", "-movflags", "+faststart", out], { stdio: ["pipe", "inherit", "inherit"] });

let k = 0;
const N = Math.round(SECS * FPS);
const marks: Record<string, number> = {};
const t0 = Date.now();
async function shot() {
  const t = k / FPS;
  await page.evaluate((x) => (window as any).__film.frame(x), t);
  if (stills) {
    if (stills.some((s) => Math.round(s * FPS) === k)) await page.screenshot({ path: out.replace(/\.(mp4|png)$/, "") + `-${t.toFixed(2)}.png`, type: "png" });
  } else {
    const png = await page.screenshot({ type: "png", optimizeForSpeed: true });
    if (!ff!.stdin.write(png)) await new Promise((r) => ff!.stdin.once("drain", r));
  }
  k++;
  if (k % 300 === 0) console.log(`frame ${k}/${N} t=${(k / FPS).toFixed(1)}s ${((Date.now() - t0) / 1000).toFixed(0)}s elapsed`);
}
const hold = async (s: number) => { for (let i = 0, n = Math.round(s * FPS); i < n && k < N; i++) await shot(); };
const rects: Record<string, unknown> = {};
const mark = (name: string) => { marks[name] = +(k / FPS).toFixed(2); };
// where a beat's subject sits on screen, for the deck's camera (film/deck/v8.html)
const where = async (name: string, sel: string) => { rects[name] = await rect(sel); };
const state = () => page.evaluate(() => (window as any).__film.state());
const rect = (sel: string) => page.evaluate((s) => (window as any).__film.rect(s), sel) as Promise<{ x: number; y: number; w: number; h: number } | null>;
// frames until the page reaches a state (the replay runs on the page clock, so this is deterministic)
async function until(pred: () => Promise<boolean>, maxS: number) { for (let i = 0; i < maxS * FPS && k < N; i++) { if (await pred()) return; await shot(); } }

// the cursor glides with an ease-in-out, one real pointermove per frame (the page draws its own cursor)
let mouse = { x: 1500, y: 900 };
async function glide(x: number, y: number, s = 0.8) {
  const a = { ...mouse }, n = Math.max(1, Math.round(s * FPS));
  for (let i = 1; i <= n; i++) {
    const p = i / n, e = p < 0.5 ? 4 * p * p * p : 1 - Math.pow(-2 * p + 2, 3) / 2;
    mouse = { x: a.x + (x - a.x) * e, y: a.y + (y - a.y) * e };
    await page.mouse.move(mouse.x, mouse.y);
    await shot();
  }
}
async function to(sel: string, s = 0.8, fx = 0.5, fy = 0.5) {
  const r = await rect(sel);
  if (!r) throw new Error(`no element ${sel} at t=${(k / FPS).toFixed(2)}: ${JSON.stringify(await state()).slice(0, 300)} side=${await page.evaluate(() => document.querySelector("#side")?.textContent?.slice(0, 200))}`);
  await glide(r.x + r.w * fx, r.y + r.h * fy, s);
}
async function click() { await page.mouse.down(); await shot(); await page.mouse.up(); await shot(); }

// ---------------------------------------------------------------- the take
await page.mouse.move(mouse.x, mouse.y);
mark("compose");
await hold(0.8);
await to("#task", 1.0, 0.75, 0.25);
await click();
await page.focus("#task");
await where("type", "#sentence");
mark("type");
for (const ch of TASK) { await page.keyboard.type(ch); await hold(2 / FPS); }
// the live planner's verdict comes from the server on the wall clock: one frame per 34 ms until it lands
for (let i = 0; i < 150 && !(await state()).genEnabled; i++) { await shot(); await new Promise((r) => setTimeout(r, 34)); }
mark("planned");
await hold(1.4);
await to("#gen", 0.9);
await hold(0.3);
await click();
mark("footage");
await until(async () => !!(await rect("#data-btn")), 8);
await hold(1.2);
mark("footage_done");
await to("#data-btn", 0.9);
await hold(0.3);
await click();
mark("data");
await where("data", "#side");
await until(async () => (await state()).phase === "data_done", 60);
mark("data_done");
await hold(1.5);
await glide(1380, 700, 1.2);   // across the dataset panel
await hold(1.2);
await to('.tile[data-clip="v01"] [data-insp]', 1.1);
await hold(0.3);
await click();
mark("gates");
await hold(0.4);
await where("gates", ".insp-card");
await hold(1.6);
await to("#insp-gates", 1.4, 0.3, 0.08);   // down the 21 gates
await to("#insp-gates", 4.0, 0.3, 0.92);
await hold(1.0);
await to("#insp-close", 0.8);
await click();
await hold(0.8);
mark("vla");
await where("vla", "#side");
await to("#vla-block", 1.2, 0.5, 0.3);
await hold(2.0);
await to('.tile[data-clip="v07"] [data-insp]', 1.1);
await click();
mark("gates2");
await hold(3.0);
await to("#insp-close", 0.7);
await click();
mark("end");
await glide(1500, 950, 1.2);
while (k < N) await shot();

if (!stills) writeFileSync(out.replace(/\.mp4$/, ".json"), JSON.stringify({ fps: FPS, secs: SECS, marks, rects }, null, 1));
console.log("marks", JSON.stringify(marks), "state", JSON.stringify(await state()).slice(0, 200));
if (ff) { ff.stdin.end(); await new Promise((r) => ff.on("close", r)); }
await browser.close();
console.log(stills ? "stills done" : `wrote ${out}, ${k} frames, ${((Date.now() - t0) / 1000).toFixed(0)} s`);
