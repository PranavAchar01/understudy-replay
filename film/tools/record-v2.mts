// Records the site demo for film v8 (the middle 1:20): the deployed Understudy site (site-v2, as on
// understudy-replay.vercel.app) driven by a scripted user, at a true 30 fps.
//
// The site runs on the wall clock (setTimeout, requestAnimationFrame, performance.now, CSS animations, autoplaying
// video, smooth scroll). A virtual clock is injected before its scripts run and every one of those is driven from
// it, so each output frame is the page exactly 1/30 s after the last, however long a screenshot takes. The page's
// own logic is untouched: it replays its recorded runs (data/recorded.json, data/three-prompts.json) as on Vercel.
//
// usage: tsx film/tools/record-v2.mts <out.mp4> [--url https://understudy-replay.vercel.app/] [--secs 80]
//        [--stills s,s,...]
// env:   CHROME, CHROME_ARGS (e.g. "--no-sandbox" as root), WEBM_ROOT (a Chromium without H.264: every <path>.mp4
//        the page asks for is answered with WEBM_ROOT/<path>.webm when that file exists)
// Writes <out>.json next to the film: the beat marks and where each beat's subject sits, for film/deck/v8.html.
import { spawn } from "node:child_process";
import { existsSync, readFileSync, writeFileSync } from "node:fs";
import puppeteer, { type Page } from "puppeteer-core";

const out = process.argv[2];
const arg = (k: string) => { const i = process.argv.indexOf(`--${k}`); return i > 0 ? process.argv[i + 1] : undefined; };
const URL = arg("url") ?? "https://understudy-replay.vercel.app/";
const SECS = Number(arg("secs") ?? 80);
const FPS = 30;
const stills = arg("stills")?.split(",").map(Number);
const CHROME = process.env.CHROME ?? `${process.env.HOME}/Library/Caches/ms-playwright/chromium-1234/chrome-mac-arm64/Google Chrome for Testing.app/Contents/MacOS/Google Chrome for Testing`;

// ---------------------------------------------------------------- the virtual clock, injected before the site
const CLOCK = readFileSync(new globalThis.URL("./vclock.js", import.meta.url), "utf8");

// ---------------------------------------------------------------- browser
const browser = await puppeteer.launch({
  executablePath: CHROME, headless: true,
  args: ["--force-device-scale-factor=1", "--hide-scrollbars", "--autoplay-policy=no-user-gesture-required", "--mute-audio", ...(process.env.CHROME_ARGS?.split(" ").filter(Boolean) ?? [])],
  defaultViewport: { width: 1920, height: 1080, deviceScaleFactor: 1 }, protocolTimeout: 900_000,
});
const page: Page = await browser.newPage();
page.on("pageerror", (e) => console.log("pageerror", String(e).slice(0, 300)));
page.on("console", (m) => { if (m.type() === "error" || m.text().startsWith("vclock")) console.log("console", m.text().slice(0, 300)); });
if (process.env.WEBM_ROOT) {
  await page.setRequestInterception(true);
  page.on("request", (r) => {
    const p = new globalThis.URL(r.url()).pathname;
    const f = p.endsWith(".mp4") && `${process.env.WEBM_ROOT}${decodeURIComponent(p).replace(/\.mp4$/, ".webm")}`;
    if (f && existsSync(f)) r.respond({ status: 200, contentType: "video/webm", body: readFileSync(f) });
    else r.continue();
  });
}
await page.evaluateOnNewDocument(CLOCK);
await page.goto(URL, { waitUntil: "networkidle0", timeout: 120_000 });
await page.evaluate(() => document.fonts.ready);

const ff = stills ? null : spawn("ffmpeg", ["-hide_banner", "-loglevel", "error", "-y", "-f", "image2pipe", "-framerate", String(FPS), "-c:v", "png", "-i", "-",
  "-c:v", "libx264", "-preset", "slow", "-crf", "14", "-pix_fmt", "yuv420p", "-r", String(FPS), "-an", "-movflags", "+faststart", out], { stdio: ["pipe", "inherit", "inherit"] });

let k = 0;
const N = Math.round(SECS * FPS);
const t0 = Date.now();
const marks: Record<string, number> = {};
const rects: Record<string, unknown> = {};
async function shot() {
  const t = k / FPS;
  await page.evaluate((x) => (window as any).__clock.advance(x * 1000), t);
  if (stills) {
    if (stills.some((s) => Math.round(s * FPS) === k)) await page.screenshot({ path: out.replace(/\.(mp4|png)$/, "") + `-${t.toFixed(2)}.png`, type: "png" });
  } else {
    const png = await page.screenshot({ type: "png", optimizeForSpeed: true });
    if (!ff!.stdin.write(png)) await new Promise((r) => ff!.stdin.once("drain", r));
  }
  k++;
  if (k % (process.env.EVERY ? +process.env.EVERY : 300) === 0) console.log(`frame ${k}/${N} t=${(k / FPS).toFixed(1)}s ${((Date.now() - t0) / 1000).toFixed(0)}s elapsed`);
}
const hold = async (s: number) => { for (let i = 0, n = Math.round(s * FPS); i < n && k < N; i++) await shot(); };
const rect = (sel: string) => page.evaluate((s) => { const n = document.querySelector(s); if (!n) return null; const r = n.getBoundingClientRect(); return { x: r.left, y: r.top, w: r.width, h: r.height }; }, sel) as Promise<{ x: number; y: number; w: number; h: number } | null>;
const mark = async (name: string, sel?: string) => { marks[name] = +(k / FPS).toFixed(2); if (sel) rects[name] = await rect(sel); };
const until = async (js: string, maxS: number) => { for (let i = 0; i < maxS * FPS && k < N; i++) { if (await page.evaluate(js)) return; await shot(); } };

let mouse = { x: 1560, y: 880 };
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
  if (!r) throw new Error(`no element ${sel} at t=${(k / FPS).toFixed(2)}`);
  await glide(r.x + r.w * fx, r.y + r.h * fy, s);
}
async function click() { await page.mouse.down(); await shot(); await page.mouse.up(); await shot(); }
async function scrollTo(y: number, s: number) { await page.evaluate((to, d) => (window as any).__clock.scrollTween(to, d), y, s * 1000); await hold(s); }
const fleetTop = () => page.evaluate(() => { const f = document.querySelector("#fleet") as HTMLElement; return f && !f.hidden ? f.getBoundingClientRect().top + scrollY - 12 : 0; });
async function typeTask(text: string) {
  await to("#prompt", 0.9, 0.35, 0.5);
  await click();
  await page.evaluate(() => { const i = document.querySelector("#prompt") as HTMLInputElement; i.select(); });
  await page.keyboard.press("Backspace"); await hold(0.2);
  for (const ch of text) { await page.keyboard.type(ch); await hold(2 / FPS); }
  await hold(0.6);   // the route pill settles (the router runs 250 ms after the last key)
}
// one prompt: type it, Train, the run replays, its film lands on the tile
async function run(name: string, text: string, filmS: number, live = false) {
  await scrollTo(0, 1.1);
  await mark(`${name}:type`, ".composer");
  await typeTask(text);
  await mark(`${name}:routed`, ".composer");
  await hold(1.0);
  if (live) {   // the Model Router, on stage: Live routes for latency (Fast), off again for the recorded route
    await to("#live", 0.8); await click(); await mark(`${name}:live`, ".composer"); await hold(1.8);
    await click(); await hold(1.0);
  }
  await to("#go", 0.7);
  await click();
  await mark(`${name}:run`);
  await until("!!document.querySelector('#fleet:not([hidden])')", 2);
  await hold(1.2);
  await mark(`${name}:tile`, "#grid .tile");
  await until("document.querySelector('#run-status')?.classList.contains('done')", 14);
  await mark(`${name}:film`, "#grid .tile");
  await hold(filmS);
}

// ---------------------------------------------------------------- the take
// the page preloads its library of finished runs and scrolls to it; the take starts at the top, as a visitor does
await page.evaluate(() => (window as any).__clock.advance(0));
await page.evaluate(() => { (window as any).__clock.scrollTween(0, 1); });
await page.evaluate(() => (window as any).__clock.advance(1));
await page.mouse.move(mouse.x, mouse.y);
await mark("hero", ".hero-copy");
await hold(2.2);

// 1. pick: the sentence on the placeholder, routed Cheap
await run("pick", "put the red block in the bowl", 1.4, true);
const pick = await rect("#grid .tile");
if (pick) await glide(pick.x + pick.w * 0.55, pick.y + pick.h * 0.5, 0.9);
await hold(0.4);
await click();                       // the film, full size
await mark("sheet", ".sheet-panel");
await hold(4.8);
await to("#sheet-close", 0.7);
await click();
await hold(0.5);

// 2. push: a new task, same box
await run("push", "push the red block onto the blue square", 2.0);

// 3. stack: a third task from the same box
await run("stack", "stack the red block on the blue block", 1.0);
const st = await rect("#grid .tile");
if (st) { await glide(st.x + st.w * 0.5, st.y + st.h * 0.55, 0.8); await hold(0.3); await click(); await mark("sheet2", ".sheet-panel"); await hold(4.2); await to("#sheet-close", 0.6); await click(); await hold(0.4); }

// 4. the library: every run's tile, side by side
await mark("library", "#grid");
await glide(960, 980, 1.0);
await scrollTo(await fleetTop(), 1.2);
const grid = await rect("#grid");
if (grid) {
  const tiles = await page.evaluate(() => [...document.querySelectorAll("#grid .tile")].map((t) => { const r = t.getBoundingClientRect(); return [r.left + r.width / 2, r.top + r.height / 2]; }));
  for (const [x, y] of tiles.slice(0, 4)) { if (k >= N - 60) break; await glide(x, y, 0.9); await hold(0.8); }
}
await mark("end");
while (k < N) await shot();

if (!stills) writeFileSync(out.replace(/\.mp4$/, ".json"), JSON.stringify({ fps: FPS, secs: SECS, url: URL, marks, rects }, null, 1));
console.log("marks", JSON.stringify(marks));
if (ff) { ff.stdin.end(); await new Promise((r) => ff.on("close", r)); }
await browser.close();
console.log(stills ? "stills done" : `wrote ${out}, ${k} frames, ${((Date.now() - t0) / 1000).toFixed(0)} s`);
