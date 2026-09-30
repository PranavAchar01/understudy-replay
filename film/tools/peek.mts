// Screenshot the live site (normal mode) after optional typing: tsx film/tools/peek.mts out.png [task]
import puppeteer from "puppeteer-core";
const CHROME = `${process.env.HOME}/Library/Caches/ms-playwright/chromium-1234/chrome-mac-arm64/Google Chrome for Testing.app/Contents/MacOS/Google Chrome for Testing`;
const b = await puppeteer.launch({ executablePath: CHROME, headless: true, defaultViewport: { width: 1920, height: 1080 } });
const p = await b.newPage();
p.on("pageerror", (e) => console.log("pageerror", String(e)));
await p.goto(process.argv[4] ?? "http://127.0.0.1:8765/", { waitUntil: "networkidle2" });
if (process.argv[3]) { await p.click("#task"); await p.keyboard.type(process.argv[3]); await new Promise((r) => setTimeout(r, 1200)); }
await p.screenshot({ path: process.argv[2] as `${string}.png` });
await b.close();
