// Records a real session on the live Understudy site, frame by frame.
//
// A headless Chrome opens the site with ?film, which hands the page's animation clock to this script. A scripted
// user then types and clicks with real mouse and keyboard events; the site's server runs the real pipeline
// the whole time. Each output frame: advance the page clock by 1/30 s, lay out, seek videos, screenshot to JPEG.
//
// Interaction beats are captured at 1 frame per 1/30 s of page time, however long the screenshot takes. While the
// page waits on real server work, frames are paced on the wall clock instead (one frame per `pace` ms), and every
// frame's wall time goes into timeline.json, so the edit can compress the waits and label the real speed-up.
//
// usage: tsx film/tools/record-live.mts <outdir> [--url http://127.0.0.1:8765/?film] [--task "..."] [--until data]
import { mkdir, writeFile } from "node:fs/promises";
import puppeteer, { type Page } from "puppeteer-core";

const out = process.argv[2];
const arg = (k: string) => { const i = process.argv.indexOf(`--${k}`); return i > 0 ? process.argv[i + 1] : undefined; };
const URL = arg("url") ?? "http://127.0.0.1:8765/?film";
const TASK = arg("task") ?? "put a red block into a bowl";
const UNTIL = arg("until") ?? "end";
const TYPE_FRAMES = Number(arg("type-frames") ?? 3); // frames per typed key (v6: 2)
const HOLD_ACC = Number(arg("hold-accepted") ?? 4.0), HOLD_REJ = Number(arg("hold-rejected") ?? 3.5);
const HOLD_FOOT = Number(arg("hold-footage") ?? 1.5);
const HOLD_DS = Number(arg("hold-dataset") ?? 3.0);
const FPS = 30;
const CHROME = `${process.env.HOME}/Library/Caches/ms-playwright/chromium-1234/chrome-mac-arm64/Google Chrome for Testing.app/Contents/MacOS/Google Chrome for Testing`;

await mkdir(`${out}/frames`, { recursive: true });
const browser = await puppeteer.launch({
  executablePath: CHROME, headless: true,
  args: ["--force-device-scale-factor=1", "--hide-scrollbars", "--autoplay-policy=no-user-gesture-required", "--mute-audio"],
  defaultViewport: { width: 1920, height: 1080, deviceScaleFactor: 1 }, protocolTimeout: 900_000,
});
const page: Page = await browser.newPage();
page.on("pageerror", (e) => console.log("pageerror", String(e).slice(0, 300)));
page.on("console", (m) => { if (m.type() === "error") console.log("console", m.text().slice(0, 300)); });
// the dataset download is real: Chrome saves it next to the frames
await mkdir(`${out}/download`, { recursive: true });
const cdp = await page.createCDPSession();
await cdp.send("Browser.setDownloadBehavior", { behavior: "allow", downloadPath: `${process.cwd()}/${out}/download` });
await page.goto(URL, { waitUntil: "networkidle2", timeout: 120_000 });
await page.evaluate(() => (window as any).__film.ready());

type Row = { i: number; vt: number; wall: number; seg: string };
const timeline: Row[] = [];
const marks: Record<string, number> = {};
let k = 0, seg = "intro";
const t0 = Date.now();
let mouse = { x: 1500, y: 900 };

async function shot() {
  const vt = k / FPS;
  await page.evaluate((t) => (window as any).__film.frame(t), vt);
  await page.screenshot({ path: `${out}/frames/${String(k).padStart(6, "0")}.jpg` as `${string}.jpeg`, type: "jpeg", quality: 92, optimizeForSpeed: true });
  timeline.push({ i: k, vt, wall: Date.now() - t0, seg });
  k++;
  if (k % 150 === 0) {
    console.log(`frame ${k} seg=${seg} wall=${((Date.now() - t0) / 1000).toFixed(0)}s`);
    await save();
  }
}
const save = () => writeFile(`${out}/timeline.json`, JSON.stringify({ fps: FPS, marks, frames: timeline }));
const mark = (name: string) => { marks[name] = k; console.log("mark", name, k); };
async function hold(s: number) { for (let n = Math.round(s * FPS); n > 0; n--) await shot(); }
const st = () => page.evaluate(() => (window as any).__film.state());
const rect = (sel: string) => page.evaluate((s) => (window as any).__film.rect(s), sel);
const ease = (p: number) => (p < 0.5 ? 4 * p * p * p : 1 - Math.pow(-2 * p + 2, 3) / 2);

async function moveTo(x: number, y: number, s = 0.7) {
  const a = { ...mouse }, n = Math.max(1, Math.round(s * FPS));
  for (let j = 1; j <= n; j++) {
    const p = ease(j / n);
    mouse = { x: a.x + (x - a.x) * p, y: a.y + (y - a.y) * p };
    await page.mouse.move(mouse.x, mouse.y);
    await shot();
  }
}
async function moveToSel(sel: string, s = 0.7, dx = 0.5, dy = 0.5) {
  const r = await rect(sel);
  if (!r) throw new Error(`no element ${sel}`);
  await moveTo(r.x + r.w * dx, r.y + r.h * dy, s);
}
async function click(shift = false) {
  if (shift) await page.keyboard.down("Shift");
  await page.mouse.down(); await shot(); await shot();
  await page.mouse.up();
  if (shift) await page.keyboard.up("Shift");
  await shot();
}
// Wait for real server work: one frame per `pace` ms of wall time, until the page reaches `phase`.
async function waitFor(pred: (s: any) => boolean, pace: number, label: string, maxMin = 90) {
  seg = label; mark(`${label}:start`);
  const start = Date.now();
  while (!pred(await st())) {
    const t = Date.now();
    await shot();
    const left = pace - (Date.now() - t);
    if (left > 0) await new Promise((r) => setTimeout(r, left));
    if (Date.now() - start > maxMin * 60_000) throw new Error(`timeout waiting for ${label}`);
  }
  mark(`${label}:end`);
  seg = "ui";
}

try {
  {
    // 1. the entry screen, the user types the task
    await page.mouse.move(mouse.x, mouse.y);
    mark("compose");
    await hold(1.2);
    await moveToSel("#task", 0.9, 0.05, 0.6);
    await click();
    mark("type");
    for (const ch of TASK) { await page.keyboard.type(ch); for (let f = 0; f < TYPE_FRAMES; f++) await shot(); }
    seg = "plan"; await waitFor((s) => s.genEnabled, 34, "plan", 1);
    await hold(1.0);
    await moveToSel("#gen", 0.8);
    await hold(0.2);
    mark("generate");
    await click();
    // 2. Runway generates the footage
    await hold(1.2);
    await waitFor((s) => s.phase === "footage_done", 200, "footage", 30);
    await hold(HOLD_FOOT);
    // 3. training data
    await moveToSel("#data-btn", 0.9);
    await hold(0.2);
    mark("data");
    await click();
    await hold(1.0);
    await waitFor((s) => s.phase === "data_done", 700, "data", 120);
    await save();
    await hold(1.5);
    if (UNTIL === "data") throw new Error("stop after data (requested)");
    // 4. inspect an accepted clip (the tracking) and a rejected one (the gate that fired)
    const s1 = await st();
    const acc: string[] = s1.accepted, rej: string[] = s1.rejected;
    mark("inspect-accepted");
    await moveToSel(`.tile[data-clip="${acc[0]}"] [data-insp]`, 0.8);
    await click();
    await hold(HOLD_ACC);
    await moveToSel("#insp-close", 0.6);
    await click();
    await hold(0.6);
    if (rej.length) {
      mark("inspect-rejected");
      await moveToSel(`.tile[data-clip="${rej[0]}"] [data-insp]`, 0.8);
      await click();
      await hold(HOLD_REJ);
      await moveToSel("#insp-close", 0.6);
      await click();
      await hold(0.6);
    }
    // 5. the dataset: download it (the real zip), then hold on the handoff panel
    await hold(0.6);
    await moveToSel("#dl", 0.9);
    await hold(0.2);
    mark("download");
    await click();
    await waitFor((s) => !!s.downloaded, 100, "download", 5);
    await hold(HOLD_DS);
    mark("end");
  }
} catch (e) {
  console.log("stopped:", String(e).slice(0, 300));
} finally {
  await save();
  await browser.close();
  console.log("frames", k, "wall", ((Date.now() - t0) / 1000).toFixed(0), "s");
}
