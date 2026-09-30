// A virtual clock for film/tools/record-v2.mts, injected before the page's own scripts: timers, requestAnimationFrame,
// Date.now / performance.now, CSS animations, video frames and smooth scrolling all run off window.__clock.advance(ms).
(() => {
  const W = window;
  const realTimeout = window.setTimeout.bind(window);
  const T0 = Date.now();
  let VT = 0, seq = 1;
  const timers = new Map();
  const rafs = new Map();
  Date.now = () => T0 + VT;
  performance.now = () => VT;
  W.setTimeout = (fn, ms = 0, ...args) => { const i = seq++; timers.set(i, { at: VT + Math.max(0, Number(ms) || 0), fn, args }); return i; };
  W.setInterval = (fn, ms = 0, ...args) => { const i = seq++; const e = Math.max(1, Number(ms) || 1); timers.set(i, { at: VT + e, fn, args, every: e }); return i; };
  W.clearTimeout = W.clearInterval = (i) => { timers.delete(i); };
  W.requestAnimationFrame = (fn) => { const i = seq++; rafs.set(i, fn); return i; };
  W.cancelAnimationFrame = (i) => { rafs.delete(i); };
  // videos never play on their own: they are seeked to the clock every frame
  const vt0 = new WeakMap();
  const blobs = new Map();
  HTMLMediaElement.prototype.play = function () { if (!vt0.has(this)) vt0.set(this, VT); return Promise.resolve(); };
  const origLoad = HTMLMediaElement.prototype.load;
  HTMLMediaElement.prototype.load = function () { vt0.delete(this); return origLoad.call(this); };
  new MutationObserver((ms) => ms.forEach((m) => {
    if (m.type === "attributes" && m.target instanceof HTMLMediaElement && !String(m.target.getAttribute("src")).startsWith("blob:")) vt0.delete(m.target);
  })).observe(document, { subtree: true, attributes: true, attributeFilter: ["src"] });
  // smooth scrolling runs on the clock too
  let scrollAnim = null;
  const realScrollTo = window.scrollTo.bind(window);
  W.scrollTo = (a, b) => {
    const top = typeof a === "object" ? a.top : b;
    if (typeof a === "object" && a.behavior === "smooth" && top != null) { scrollAnim = { from: scrollY, to: top, t0: VT, dur: 900 }; return; }
    scrollAnim = null; realScrollTo(a, b);
  };
  const tick = () => new Promise((r) => realTimeout(r, 0));
  W.__clock = {
    now: () => VT,
    scrollTween(to, dur) { scrollAnim = { from: scrollY, to, t0: VT, dur }; },
    async advance(to) {
      // due timers in time order, letting the promise chains they start run between them
      for (let guard = 0; guard < 500; guard++) {
        let best = null;
        for (const e of timers) if (e[1].at <= to && (!best || e[1].at < best[1].at)) best = e;
        if (!best) break;
        const [i, t] = best;
        VT = Math.max(VT, t.at);
        if (t.every) t.at += t.every; else timers.delete(i);
        try { typeof t.fn === "function" ? t.fn(...t.args) : 0; } catch (e) { console.error(e); }
        await tick();
      }
      VT = to;
      const fs = [...rafs.values()]; rafs.clear();
      for (const f of fs) { try { f(VT); } catch (e) { console.error(e); } }
      await tick();
      if (scrollAnim) {
        const p = Math.min(1, (VT - scrollAnim.t0) / scrollAnim.dur), e = p < 0.5 ? 4 * p * p * p : 1 - Math.pow(-2 * p + 2, 3) / 2;
        realScrollTo(0, scrollAnim.from + (scrollAnim.to - scrollAnim.from) * e);
        if (p >= 1) scrollAnim = null;
      }
      // CSS animations and transitions: paused, then set to their age on the clock
      for (const a of document.getAnimations()) {
        if (a.__vt0 == null) { a.__vt0 = VT; a.pause(); }
        a.currentTime = VT - a.__vt0;
      }
      // videos: the frame for their age on the clock (looped)
      const jobs = [];
      for (const v of document.querySelectorAll("video")) {
        if (!v.currentSrc && !v.getAttribute("src")) continue;
        if (!vt0.has(v)) { if (!v.autoplay) continue; vt0.set(v, VT); }
        if (!v.paused) v.pause();
        // only a video on screen is seeked: Chromium does not decode hidden or off-screen ones
        const r = v.getBoundingClientRect();
        if (!r.width || !r.height || r.bottom < 0 || r.top > innerHeight || getComputedStyle(v).visibility === "hidden" || !v.offsetParent) continue;
        jobs.push((async () => {
          // every film is swapped for an in-memory copy of itself: exact, instant seeks on any server
          const src = v.getAttribute("src") || "";
          if (!src.startsWith("blob:")) {
            if (!blobs.has(src)) blobs.set(src, fetch(src).then((r) => r.blob()).then((b) => URL.createObjectURL(b)).catch(() => null));
            const u = await blobs.get(src);
            if (!u || v.getAttribute("src") !== src) return;
            v.preload = "auto"; v.src = u;
          }
          if (v.error || v.networkState === 3) return;
          // a video still loading gets a short real wait, never a block: it shows its first frame when it lands
          if (!(v.readyState >= 2) || !v.duration) await new Promise((r) => { const k = realTimeout(r, 400); v.addEventListener("loadeddata", () => { clearTimeout(k); r(); }, { once: true }); });
          if (!(v.readyState >= 1) || !v.duration || !isFinite(v.duration)) return;
          const x = ((VT - vt0.get(v)) / 1000) % v.duration;
          if (Math.abs(v.currentTime - x) > 0.004) await new Promise((r) => { const k = realTimeout(() => { console.warn("vclock: seek timeout", v.currentSrc, v.readyState, x); r(); }, 1500); v.addEventListener("seeked", () => { clearTimeout(k); r(); }, { once: true }); v.currentTime = x; });
        })());
      }
      await Promise.all(jobs);
    },
  };
  // a drawn cursor (a headless screenshot has none)
  addEventListener("DOMContentLoaded", () => {
    const c = document.createElement("div");
    c.id = "__cursor";
    c.innerHTML = `<svg viewBox="0 0 24 24" width="30" height="30"><path d="M4 2.5v17.2l4.6-4.3 3 6.6 3-1.3-3-6.5h6.3z" fill="#fff" stroke="#05070d" stroke-width="1.4" stroke-linejoin="round"/></svg>`;
    c.style.cssText = "position:fixed;left:0;top:0;z-index:2147483647;pointer-events:none;transform:translate(-100px,-100px);filter:drop-shadow(0 2px 4px rgba(0,0,0,.5))";
    document.body.append(c);
    addEventListener("pointermove", (e) => { c.style.transform = `translate(${e.clientX - 4}px, ${e.clientY - 2}px)`; }, true);
  });
})();
