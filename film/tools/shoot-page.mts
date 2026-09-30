// Screenshot a real web page for a B-roll pop-up: tsx film/tools/shoot-page.mts <url> <out.png> [width] [height]
import puppeteer from "puppeteer-core";
const [url, out, w = "1400", h = "1000"] = process.argv.slice(2);
const CHROME = `${process.env.HOME}/Library/Caches/ms-playwright/chromium-1234/chrome-mac-arm64/Google Chrome for Testing.app/Contents/MacOS/Google Chrome for Testing`;
const b = await puppeteer.launch({ executablePath: CHROME, headless: true, defaultViewport: { width: +w, height: +h, deviceScaleFactor: 1.5 } });
const p = await b.newPage();
await p.goto(url, { waitUntil: "networkidle2", timeout: 60_000 });
await p.screenshot({ path: out as `${string}.png` });
console.log(await p.title());
await b.close();
