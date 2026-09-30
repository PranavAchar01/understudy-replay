// Understudy live app. Every number and file on this page comes from the local server (src/understudy/web.py),
// which runs the real pipeline and streams its progress as Server-Sent Events.
//
// Motion runs off one clock (now()). In a normal browser that is the wall clock and a requestAnimationFrame loop
// drives it. With ?film in the URL the recorder owns the clock: it calls window.__film.frame(t) once per output
// frame, which lays out every tween and seeks every visible video to its exact frame, then screenshots. The
// server work is never faked in either mode; only the drawing is stepped.
"use strict";

const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];
const FILM = new URLSearchParams(location.search).has("film");
let VT = 0;
let INSTANT = false; // true while a reopened run's saved events are drawn: no motion
const now = () => (FILM ? VT : performance.now() / 1000);
const clamp = (x, a = 0, b = 1) => Math.min(b, Math.max(a, x));
const easeOut = (p) => 1 - Math.pow(1 - p, 3);
const esc = (s) => String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
const fmt = (n) => Number(n).toLocaleString("en-US");
const el = (tag, cls, html) => { const e = document.createElement(tag); if (cls) e.className = cls; if (html != null) e.innerHTML = html; return e; };

// ---------- one clock: tweens, spinners, videos ----------
const tweens = [];
function tween(dur, fn, { delay = 0, ease = easeOut, done } = {}) {
  if (INSTANT) { fn(1); if (done) done(); return; }
  fn(0);
  tweens.push({ t0: now() + delay, dur, fn, ease, done });
}
function fadeIn(e, dur = 0.4, dy = 10, delay = 0) {
  tween(dur, (p) => { e.style.opacity = p; e.style.transform = p >= 1 ? "" : `translateY(${(1 - p) * dy}px)`; }, { delay });
}
function fadeOut(e, dur = 0.3, done) {
  tween(dur, (p) => { e.style.opacity = 1 - p; }, { done });
}
function widthTo(e, pct, dur = 0.5) {
  const from = parseFloat(e.style.width) || 0;
  tween(dur, (p) => { e.style.width = `${from + (pct - from) * p}%`; });
}

const vids = new Set();
function attachVideo(v, src, { loop = true } = {}) {
  v.muted = true; v.defaultMuted = true; v.playsInline = true; v.loop = loop; v._loop = loop; v._t0 = now(); v.preload = "auto";
  v.autoplay = !FILM;
  v.src = src;
  vids.add(v);
  if (!FILM) { v.play().catch(() => {}); v.addEventListener("canplay", () => { if (v.paused && v.isConnected) v.play().catch(() => {}); }, { once: true }); }
}
const settle = (v, ev, ms) => new Promise((r) => { const t = setTimeout(r, ms); v.addEventListener(ev, () => { clearTimeout(t); r(); }, { once: true }); });
const visible = (e) => e.isConnected && e.offsetParent !== null;

async function frame(t) {
  VT = t;
  for (let i = tweens.length - 1; i >= 0; i--) {
    const w = tweens[i];
    if (t < w.t0) continue;
    const p = clamp((t - w.t0) / w.dur);
    w.fn(w.ease(p));
    if (p >= 1) { tweens.splice(i, 1); if (w.done) w.done(); }
  }
  for (const s of $$(".spin, .step.is-active .mark i")) s.style.transform = `rotate(${(t * 400) % 360}deg)`;
  if (!FILM) return;
  const jobs = [];
  for (const v of vids) {
    if (!v.isConnected) { vids.delete(v); continue; }
    if (!visible(v)) continue;
    jobs.push((async () => {
      if (!(v.readyState >= 2) || !v.duration) await settle(v, "loadeddata", 8000);
      if (!v.duration) return;
      let x = Math.max(0, t - v._t0);
      x = v._loop ? x % v.duration : Math.min(x, v.duration - 0.02);
      if (Math.abs(v.currentTime - x) > 0.004) { v.currentTime = x; await settle(v, "seeked", 4000); }
    })());
  }
  await Promise.all(jobs);
}
if (!FILM) { const loop = () => { frame(now()); requestAnimationFrame(loop); }; requestAnimationFrame(loop); }
// a browser pauses media in a hidden tab; bring the films back when the page is shown again
document.addEventListener("visibilitychange", () => { if (!FILM && !document.hidden) for (const v of vids) if (v.isConnected && v.paused && v.autoplay) v.play().catch(() => {}); });

// ---------- server ----------
async function api(path, body) {
  const r = await fetch(path, body ? { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) } : {});
  const j = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(j.detail || j.reason || `HTTP ${r.status}`);
  return j;
}
function listen(job, onEvent) {
  const es = new EventSource(`/api/jobs/${job}/events`);
  es.onmessage = (m) => {
    const ev = JSON.parse(m.data);
    if (ev.type === "job_end") es.close();
    onEvent(ev);
  };
}

// ---------- state ----------
const S = {
  phase: "compose", slug: null, task: "", n: 0, budget: null,
  credits: 0, charged: new Set(), cachedVid: new Set(), accepted: [], rejected: [], verdicts: {}, tracked: {},
  jobStart: 0, stageStart: 0,
  gen: [], ready: new Set(), // clips this footage stage is making; clips whose Runway footage is in
  vla: {}, vlaState: null, vlaJob: null, // clip -> its SmolVLA film record (media/vla/<clip>.json)
  router: "demo-cheap", routing: {}, // the Model Router the next footage goes through ("" = direct gen4_turbo); clip -> its pick
};
const media = (file) => `/runs/${S.slug}/${file}?v=${Date.now()}`;

function setStep(step, state) {
  const li = $(`.step[data-step="${step}"]`);
  if (!li) return;
  li.classList.toggle("is-active", state === "active");
  li.classList.toggle("is-done", state === "done");
}
function stat(k, v) { $(`.stat[data-k="${k}"] dd`).textContent = v; }
function clock() { const s = Math.max(0, Date.now() / 1000 - S.stageStart); return `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, "0")}`; }

// ---------- compose ----------
const taskEl = $("#task"), genBtn = $("#gen"), fitEl = $("#fit");
let planTimer = 0, planSeq = 0;
function taskText() { return taskEl.textContent.replace(/\s+/g, " ").trim(); }
taskEl.addEventListener("input", () => {
  genBtn.disabled = true;
  fitEl.textContent = ""; fitEl.className = "fit";
  clearTimeout(planTimer);
  planTimer = setTimeout(checkPlan, 300);
});
taskEl.addEventListener("keydown", (e) => { if (e.key === "Enter") { e.preventDefault(); if (!genBtn.disabled) genBtn.click(); } });
async function checkPlan() {
  const t = taskText(), seq = ++planSeq;
  if (t.length < 3) return;
  const r = await api("/api/plan", { task: t }).catch((e) => ({ ok: false, reason: e.message }));
  if (seq !== planSeq) return;
  if (r.ok) {
    const have = (r.existing || []).length;
    fitEl.textContent = have
      ? `The SO-101 can do this. ${have} scenarios already made for this sentence; this adds ${r.clips} new ${r.clips === 1 ? "one" : "ones"}.`
      : "The SO-101 can do this: one hand, a pinch grasp, a place.";
    fitEl.className = "fit is-ok";
    genBtn.disabled = false;
    genBtn.textContent = have ? `Generate ${r.clips} more ${r.clips === 1 ? "scenario" : "scenarios"}` : "Generate Footage";
    dryRun(t);
    const b = S.budget;
    if (b && b.balance != null && r.cost != null && !S.router) {
      $("#budget").textContent = `${r.clips} ${have ? "new " : ""}clips  ·  ${r.cost} credits${r.cached_clips ? ` (${r.cached_clips} made earlier, from the cache)` : ""}  ·  balance ${b.balance}`;
    }
  } else {
    fitEl.textContent = String(r.reason || "").replace(/^'[^']*':\s*/, "");
    fitEl.className = "fit is-no";
  }
  fadeIn(fitEl, 0.3, 4);
}
async function loadBudget() {
  const b = await api("/api/budget").catch(() => null);
  S.budget = b;
  const el2 = $("#budget");
  if (!b || b.balance == null) { el2.textContent = "Runway balance unavailable (no API key in this process)"; return; }
  el2.textContent = `${b.clips} clips  ·  about ${b.cost_run} credits  ·  balance ${b.balance}`;
}
loadBudget();

genBtn.addEventListener("click", async () => {
  if (genBtn.disabled) return;
  genBtn.disabled = true;
  const task = taskText();
  try { await startFootage(task); } catch (e) {
    fitEl.textContent = e.message; fitEl.className = "fit is-no"; genBtn.disabled = false;
  }
});

// one footage stage: a new run, or new scenarios added to a run that already has footage (never a regeneration)
async function startFootage(task, clips) {
  const body = { task, ...(clips ? { clips } : {}), ...(S.router ? { router: S.router } : {}) };
  const r = await api("/api/footage", body);
  meterStart();
  if (r.existing && r.existing.length && S.slug !== r.slug) await reopen(r.slug); // draw the scenarios it has first
  S.slug = r.slug; S.task = task; S.phase = "footage";
  S.gen = r.clip_ids; S.credits = 0; S.charged = new Set();
  S.stageStart = Date.now() / 1000;
  S.startBalance = S.budget && S.budget.balance;
  if ($("#run").hidden) toRun(r.clip_ids);
  else {
    addTiles(r.clip_ids);
    for (const st of ["data", "dataset", "vla"]) setStep(st, "");
    setStep("footage", "active");
    stat("clips", `${S.ready.size}/${$$(".tile").length}`);
    stat("credits", 0);
    sideFootage();
  }
  listen(r.job, onFootage);
}

function toRun(ids) {
  const c = $("#compose"), run = $("#run");
  fadeOut(c, 0.35, () => { c.hidden = true; });
  document.body.classList.add("is-run");
  $("#bar-tag").textContent = "Local run";
  $("#run-sentence").innerHTML = `I want to train an SO-101 to <em>${esc(S.task)}</em>`;
  run.hidden = false;
  fadeIn(run, 0.5, 16, 0.2);
  setStep("footage", "active");
  stat("clips", `0/${ids.length}`);
  addTiles(ids);
  sideFootage();
}
function addTiles(ids) {
  const grid = $("#grid");
  ids.filter((id) => !tile(id)).forEach((id, i) => { const t = makeTile(id); grid.append(t); fadeIn(t, 0.4, 12, 0.3 + i * 0.06); });
  S.n = $$(".tile", grid).length;
}

// ---------- tiles ----------
// A tile is one scenario. Its picture is the fine-tuned SmolVLA running that scenario in MuJoCo (media/vla/<clip>.mp4),
// never the Runway footage: until the film exists the tile shows what the pipeline is doing with the clip.
function makeTile(id) {
  const t = el("div", "tile");
  t.dataset.clip = id;
  t.innerHTML = `<div class="media"><div class="veil"><div class="spin"></div><p class="veil-t">waiting for Runway</p><p class="veil-s"></p></div><span class="tag">queued</span>
    <span class="vla-chip" hidden>VLA · SmolVLA · MuJoCo</span><span class="res-chip" hidden></span><div class="bar2"></div></div>
    <div class="meta"><span class="name">${esc(id)}</span><span class="status">waiting for Runway</span></div>`;
  t.addEventListener("click", (e) => { if (!e.target.closest("[data-insp]") && S.verdicts[id] && S.verdicts[id].accepted) openVla(id); });
  return t;
}
function veil(id, title, sub = "", spinning = true) {
  const t = tile(id); if (!t) return;
  const v = $(".veil", t);
  if ($(".media video", t)) { v.hidden = true; return; }
  v.hidden = false;
  $(".veil-t", v).textContent = title; $(".veil-s", v).textContent = sub;
  $(".spin", v).hidden = !spinning;
}
const tile = (id) => $(`.tile[data-clip="${id}"]`);
function tileStatus(id, text) { const t = tile(id); if (t && !S.verdicts[id]) $(".status", t).textContent = text; }
function tileTag(id, text) { const t = tile(id); if (!t) return; const g = $(".tag", t); g.textContent = text; g.hidden = !text; }
function tileMedia(id, node) {
  const m = $(".media", tile(id));
  const old = $$("img, video", m);
  m.insertBefore(node, $(".veil", m));
  $(".veil", m).hidden = true;
  if (node.tagName === "VIDEO" && !FILM) node.play().catch(() => {});
  fadeIn(node, 0.45, 0);
  tween(0.45, () => {}, { done: () => { old.forEach((o) => { vids.delete(o); o.remove(); }); } });
}

// ---------- side panels ----------
const side = $("#side");
function setSide(html) {
  side.innerHTML = html;
  $$(":scope > *", side).forEach((c, i) => fadeIn(c, 0.4, 10, i * 0.05));
}

function sideFootage() {
  setSide(`<p class="kicker">Step 1 · Runway API</p><h3>Generating the footage</h3>
    <p>A person doing the task, filmed by Runway. <b>gen4_image</b> draws clip 1's first frame, <b>gen4_image_turbo</b> restyles it for every other clip (table, bowl, light), ${S.router ? `the <b>${esc(S.router)}</b> Model Router picks the video model for each 5 s clip (free dry run first, then live).` : "<b>gen4_turbo</b> animates each one for 5 s."}</p>
    <div class="progline"><span id="fp-text">0 of ${(S.gen.length || S.n)} clips ready</span><span id="fp-clock">0:00</span></div>
    <div class="prog"><i id="fp-bar"></i></div>
    <ol class="calls" id="calls"></ol>`);
}
const callRows = {};
function onFootage(ev) {
  if (ev.type === "runway") {
    const key = `${ev.clip}-${ev.stage}`;
    if (ev.routing) { ev.model = ev.routing.model || ev.model; routeChip(ev.clip, ev.routing, ev.status); }
    let li = callRows[key];
    if (!li) {
      li = el("li", "", `<span>${ev.clip}</span><span>${ev.model} · ${ev.stage === "frame" ? "first frame" : "5 s video"}</span><span class="st"></span><span class="cr"></span>`);
      callRows[key] = li;
      $("#calls").append(li);
      fadeIn(li, 0.3, 6);
    }
    const pct = ev.progress ? ` ${Math.round(ev.progress * 100)}%` : "";
    veil(ev.clip, ev.stage === "frame" ? "Runway · first frame" : "Runway · 5 s video", ev.status === "CACHED" ? "from cache" : `${ev.status.toLowerCase()}${ev.status === "RUNNING" ? pct : ""}`);
    $(".st", li).textContent = ev.status === "CACHED" ? "cached" : ev.status === "SUCCEEDED" ? "done" : `${ev.status.toLowerCase()}${ev.status === "RUNNING" ? pct : ""}`;
    li.classList.toggle("is-done", ev.status === "SUCCEEDED");
    li.classList.toggle("is-cached", ev.status === "CACHED");
    if (ev.status === "SUCCEEDED" && !S.charged.has(key)) { S.charged.add(key); const c = ev.routing && ev.routing.realized_credits != null ? ev.routing.realized_credits : ev.cost; ev.cost = c; S.credits += c; meterCredits(c); stat("credits", S.credits); $(".cr", li).textContent = `${ev.cost} cr`; }
    if (ev.status === "CACHED") { $(".cr", li).textContent = "0 cr"; if (ev.stage === "video") S.cachedVid.add(ev.clip); }
    const stageLabel = ev.stage === "frame" ? "first frame" : "5 s video";
    tileStatus(ev.clip, ev.status === "CACHED" ? `${stageLabel} · from cache` : `${ev.model} · ${stageLabel} · ${ev.status.toLowerCase()}${ev.status === "RUNNING" ? pct : ""}`);
    const t = tile(ev.clip);
    if (t) widthTo($(".bar2", t), ev.stage === "frame" ? 5 + 20 * (ev.progress || 0) : 30 + 70 * (ev.progress || 0), 0.6);
    tileTag(ev.clip, ev.stage === "frame" ? "drawing first frame" : "animating");
  } else if (ev.type === "routed") {
    S.routing[ev.clip] = { ...(S.routing[ev.clip] || {}), ...ev };
    routeChip(ev.clip, ev, "SUCCEEDED");
  } else if (ev.type === "clip_ready") {
    if (S.routing[ev.clip]) showFootage(ev.clip);
    S.ready.add(ev.clip);
    tileTag(ev.clip, "");
    tileStatus(ev.clip, S.cachedVid.has(ev.clip) ? "Runway · 5 s · from cache" : "Runway · 5 s · ready");
    veil(ev.clip, "Footage in", "the gates decide next", false);
    const t = tile(ev.clip); if (t) fadeOut($(".bar2", t), 0.4);
    const gen = S.gen.length ? S.gen : $$(".tile").map((x) => x.dataset.clip);
    const ready = gen.filter((c) => S.ready.has(c)).length;
    stat("clips", `${S.ready.size}/${S.n}`);
    const ft = $("#fp-text"); if (ft) ft.textContent = `${ready} of ${gen.length} clips ready`;
    const fb = $("#fp-bar"); if (fb) widthTo(fb, (100 * ready) / gen.length);
  } else if (ev.type === "job_end") { meterStop();
  } else if (ev.type === "footage_done") {
    setStep("footage", "done");
    if (S.startBalance != null && ev.balance != null) { S.credits = S.startBalance - ev.balance; stat("credits", S.credits); }
    S.phase = "footage_done";
    stat("clips", S.n);
    sideData(ev.balance, S.cachedVid.size);
  } else if (ev.type === "budget_stop" || ev.type === "error") {
    const p = el("p", "", `<span style="color:var(--no)">${esc(ev.message)}</span>`);
    side.append(p);
  }
}
setInterval(() => { const c = $("#fp-clock") || $("#dp-clock"); if (c && !["footage_done", "data_done"].includes(S.phase)) c.textContent = clock(); }, 250);

// ---------- step 2: training data ----------
function sideData(balance, cached = 0) {
  setSide(`<p class="kicker">Step 2 · Training data</p><h3>Footage in hand. Now make it robot data.</h3>
    <p>MediaPipe tracks 21 hand points on every frame and OpenCV follows the red block. 21 gates throw out any clip a robot should not learn from. The hand's grasp point is retargeted onto the SO-101 in MuJoCo with real contact physics, and every survivor is written as a LeRobot dataset.</p>
    <button type="button" class="cta" id="data-btn">Generate Training Data</button>
    <p class="budget">${cached ? `${cached} of ${S.n} clips from the cache (made earlier for this sentence) · 0 credits · ` : ""}${balance != null ? `Runway balance now ${balance}` : ""}</p>`);
  $("#data-btn").addEventListener("click", startData);
}
async function startData() {
  const b = $("#data-btn"); b.disabled = true; meterStart();
  let r;
  try { r = await api("/api/data", { slug: S.slug }); } catch (e) { b.disabled = false; side.append(el("p", "", esc(e.message))); return; }
  dataPanel();
  listen(r.job, onData);
}
function dataPanel() {
  S.phase = "data"; S.stageStart = Date.now() / 1000;
  setStep("data", "active");
  setSide(`<p class="kicker">Step 2 · running</p><h3>Generating training data</h3>
    <div class="progline"><span id="dp-text">tracking</span><span id="dp-clock">0:00</span></div>
    <div class="prog"><i id="dp-bar"></i></div>
    <ul class="feed" id="feed"></ul>`);
}
const STAGE = { track: "MediaPipe · tracking the hand", audit: "Claude · scene audit", gates: "checking 21 gates", retarget: "MuJoCo · SO-101 replay" };
function feed(html) {
  const f = $("#feed"); if (!f) return;
  const li = el("li", "", html); f.append(li); fadeIn(li, 0.3, 6);
  while (f.children.length > 26) f.firstChild.remove();
}
let dataClips = [];
function onData(ev) {
  if (ev.type === "data_start") {
    // every clip of the run is checked again: clear the last verdicts (the films stay, they are the VLA's)
    dataClips = ev.clips; S.accepted = []; S.rejected = []; S.verdicts = {};
    for (const t of $$(".tile")) { t.classList.remove("is-ok", "is-no"); $$(".stamp", t).forEach((x) => x.remove()); }
    stat("accepted", 0); stat("rejected", 0);
  }
  else if (ev.type === "clip_stage") {
    tileStatus(ev.clip, STAGE[ev.stage]);
    if (ev.stage !== "retarget") veil(ev.clip, STAGE[ev.stage], "", true);
    const i = dataClips.indexOf(ev.clip);
    if (ev.stage !== "retarget") {
      $("#dp-text").textContent = `clip ${i + 1} of ${dataClips.length} · ${STAGE[ev.stage]}`;
      widthTo($("#dp-bar"), (100 * (i + ({ track: 0, audit: 0.5, gates: 0.8 }[ev.stage] || 0))) / dataClips.length * 0.5);
    } else $("#dp-text").textContent = `${ev.clip} · ${STAGE.retarget}`;
    feed(`<b>${ev.clip}</b> ${STAGE[ev.stage]}`);
  } else if (ev.type === "tracked") {
    S.tracked[ev.clip] = ev;
    tileTag(ev.clip, "hand + block tracked");
    feed(`<b>${ev.clip}</b> hand tracked on ${ev.frames} frames at ${Math.round(ev.fps)} fps`);
  } else if (ev.type === "verdict") {
    S.verdicts[ev.clip] = ev;
    const t = tile(ev.clip);
    (ev.accepted ? S.accepted : S.rejected).push(ev.clip);
    stat("accepted", S.accepted.length); stat("rejected", S.rejected.length);
    if (S.routing[ev.clip]) { S.routing[ev.clip].verdict = { accepted: ev.accepted, reason: ev.reason }; routeChip(ev.clip, S.routing[ev.clip], "SUCCEEDED"); }
    meterPaint();
    if (!t) return;
    t.classList.add(ev.accepted ? "is-ok" : "is-no");
    tileTag(ev.clip, "");
    if (ev.accepted) veil(ev.clip, "Accepted", "the SmolVLA film comes after the dataset", false);
    else {
      veil(ev.clip, "Rejected", "no robot data from this clip", false);
      const stamp = el("div", "stamp", `<b>Rejected</b>${esc(why(ev.reason))}<span class="gate">gate: ${esc(ev.reason.split(": ")[0])}</span>`);
      $(".media", t).append(stamp); fadeIn(stamp, 0.35, 8);
    }
    const st = $(".status", t);
    st.innerHTML = `<button type="button" class="linkish" data-insp="${ev.clip}">${ev.gates_total} gates ›</button>`;
    feed(ev.accepted ? `<b>${ev.clip}</b> <span class="ok">ACCEPTED</span> ${ev.gates_passed}/${ev.gates_total} gates` : `<b>${ev.clip}</b> <span class="no">REJECTED</span> ${esc(why(ev.reason))}`);
  } else if (ev.type === "reanchor") {
    feed(`<b>${ev.clip}</b> re-anchored to new cube spots: ${ev.accepted} of ${ev.tried} copies passed the robot gates`);
  } else if (ev.type === "episodes") {
    stat("episodes", ev.total);
    $("#dp-text").textContent = `writing ${ev.total} episodes`;
  } else if (ev.type === "dataset_progress") {
    $("#dp-text").textContent = `LeRobot v3.0 · episode ${ev.episode} of ${ev.total}`;
    widthTo($("#dp-bar"), 50 + (50 * ev.episode) / ev.total, 0.4);
  } else if (ev.type === "data_done") {
    setStep("data", "done");
    S.phase = "data_done";
    S.dataset = ev;
    stat("episodes", ev.episodes);
    sideDataset().then(() => refreshVla(true));
  } else if (ev.type === "error") feed(`<span class="no">${esc(ev.message)}</span>`);
  else if (ev.type === "job_end") meterStop();
}

// "gate name: why it failed" -> the why, capitalised
function why(reason) { const i = reason.indexOf(": "); const w = i >= 0 ? reason.slice(i + 2) : reason; return w.charAt(0).toUpperCase() + w.slice(1); }

// ---------- inspector ----------
document.addEventListener("click", (e) => {
  const b = e.target.closest("[data-insp]");
  if (b) { e.stopPropagation(); openInspector(b.dataset.insp); }
});
function num(v) { return typeof v === "number" ? (Math.abs(v) >= 100 ? v.toFixed(0) : Math.abs(v) >= 1 ? v.toFixed(2) : v.toFixed(3)) : v == null ? "" : String(v); }
function openInspector(id) {
  const ev = S.verdicts[id], tr = S.tracked[id];
  if (!ev) return;
  $("#insp-title").textContent = `${id} · gates`;
  const vd = $("#insp-verdict");
  vd.className = `insp-verdict ${ev.accepted ? "ok" : "no"}`;
  vd.innerHTML = ev.accepted ? `<b>Accepted.</b> Passed ${ev.gates_passed} of ${ev.gates_total} gates.` : `<b>Rejected.</b> ${esc(why(ev.reason))}`;
  $("#insp-gates").innerHTML = ev.gates.map((g) => `<li class="${g.passed === false ? "no" : g.passed == null ? "na" : ""}"><span>${esc(g.name)}</span><span>${esc(num(g.value))}${g.limit != null && g.limit !== "" ? ` <i style="color:var(--text-3);font-style:normal">(${esc(num(g.limit))})</i>` : ""}</span>${g.why ? `<span class="why">${esc(g.why)}</span>` : ""}</li>`).join("");
  const fix = !ev.accepted && S.refine && S.refine.clips[id] ? S.refine.clips[id].own : [];
  $("#insp-fix").hidden = !fix.length;
  if (fix.length) {
    $("#fix-t").textContent = fix.map((m) => m.fix).join(" ");
    $("#fix-n").textContent = `The gate's reason, read as a mismatch, becomes the first rule of the ${fix[0].target === "video" ? "motion" : fix[0].target === "frame" ? "first-frame" : "first-frame and motion"} prompt. Text only: not generated yet, so its effect is not measured.`;
  }
  if (tr) $("#insp-verdict").insertAdjacentHTML("beforeend", `<br><span class="insp-cap">MediaPipe tracked the hand on ${tr.frames} frames. Grasp at frame ${tr.grasp_frame}, release at frame ${tr.release_frame}.</span>`);
  const box = $("#inspector"); box.hidden = false;
  fadeIn($(".insp-card", box), 0.35, 14);
  tween(0.3, (p) => { box.style.opacity = p; });
}
function closeInspector() { const box = $("#inspector"); fadeOut(box, 0.25, () => { box.hidden = true; box.style.opacity = 1; }); }
$("#insp-close").addEventListener("click", closeInspector);
$("#inspector").addEventListener("click", (e) => { if (e.target.id === "inspector") closeInspector(); });

// ---------- step 3: the dataset, handed off (training happens in a terminal on this dataset) ----------
const DL_ICON = '<svg width="18" height="18" viewBox="0 0 18 18"><path d="M9 2v10M4.5 7.5 9 12l4.5-4.5M3 15.5h12" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"/></svg>';
const ZIP_ICON = '<svg width="20" height="22" viewBox="0 0 20 22"><path d="M2 1h10l6 6v14H2z" fill="none" stroke="currentColor" stroke-width="1.5"/><path d="M8 1v2h2v2H8v2h2v2H8v2h2" fill="none" stroke="currentColor" stroke-width="1.3"/></svg>';
async function sideDataset() {
  S.refine = await api(`/api/runs/${S.slug}/refine`).catch(() => null);
  const d = S.dataset;
  if (!d.accepted.length) {
    setSide(`<p class="kicker">Step 3</p><h3>No clip passed the gates</h3><p>Understudy will not write a dataset from footage that fails a gate. The inspector shows why; the next take's prompts carry the fix.</p>`);
    return;
  }
  const ds = await api(`/api/runs/${S.slug}/dataset`).catch(() => null);
  S.ds = ds;
  setStep("dataset", "done");
  if (!ds) { // the dataset files are not on disk (a trimmed copy of the run): its numbers, from the data stage itself
    setSide(`<p class="kicker">Step 3 · LeRobot dataset</p><h3>The training data this run made</h3>
      <dl class="facts"><div><dd>${d.episodes}</dd><dt>episodes</dt></div><div><dd>${d.frames != null ? fmt(d.frames) : "-"}</dd><dt>frames</dt></div><div><dd>${esc(d.codebase_version || "v3.0")}</dd><dt>LeRobot format</dt></div></dl>
      <p>From the ${d.accepted.length} clips that passed the gates, each re-anchored to new cube spots and gated again. The dataset files are not in this copy; Generate Training Data writes them again.</p>
      <div class="train-block" id="train-block"></div>
      <div class="vla-block" id="vla-block"></div>`);
    renderVlaBlock(); renderTrain();
    return;
  }
  setSide(`<p class="kicker">Step 3 · LeRobot dataset</p><h3>Your training data is ready</h3>
    <dl class="facts"><div><dd>${ds.episodes}</dd><dt>episodes</dt></div><div><dd>${fmt(ds.frames)}</dd><dt>frames at ${ds.fps} fps</dt></div><div><dd>${esc(ds.codebase_version)}</dd><dt>LeRobot format</dt></div></dl>
    <div class="dsfile"><span class="ic">${ZIP_ICON}</span><span><span class="nm">${esc(ds.name).replace(/_/g, "_<wbr>")}.zip</span><br><span class="sub">${esc(ds.robot_type || "")} · from ${d.accepted.length} of ${S.n} clips that passed</span></span><span class="sz">${ds.mb} MB</span></div>
    <div class="feats">${ds.features.map((f) => `<span>${esc(f)}</span>`).join("")}</div>
    <a class="cta" id="dl" href="/api/runs/${encodeURIComponent(S.slug)}/dataset.zip" download="${esc(ds.name)}.zip">${DL_ICON}Download dataset</a>
    <p class="dlstate" id="dlstate"></p>
    <p class="next-h">Next: train on it in a terminal</p>
    <pre class="term"><span class="cm"># fine-tune the SmolVLA robot foundation model (Hugging Face LeRobot)</span>
<span class="pr">$</span> lerobot-train --policy.path=lerobot/smolvla_base --dataset.repo_id=${esc(ds.repo_id)} --dataset.root=${esc(ds.name)}
<span class="cm"># or the small MLP baseline</span>
<span class="pr">$</span> bin/understudy train ${esc(S.slug)}</pre>
    <div class="train-block" id="train-block"></div>
    <div class="vla-block" id="vla-block"></div>`);
  $("#dl").addEventListener("click", download);
  renderVlaBlock(); renderTrain();
}

// ---------- step 4: the VLA itself, one MuJoCo film per scenario ----------
let vlaTimer = 0;
async function refreshVla(auto = false) {
  clearTimeout(vlaTimer);
  if (!S.slug) return;
  const st = await api(`/api/runs/${encodeURIComponent(S.slug)}/vla`).catch(() => null);
  if (!st) return;
  S.vlaState = st;
  for (const c of st.accepted) {
    if (st.films[c]) showFilm(c, st.films[c]);
    else if (!S.vla[c]) veilVla(c);
  }
  setStep("vla", st.accepted.length && !st.missing.length ? "done" : st.running ? "active" : "");
  if (st.running && !S.vlaJob) { S.vlaJob = st.running; listen(st.running, onVla); }
  else if (auto && st.ckpt && st.missing.length && !st.running) startVla();
  renderVlaBlock();
  if (st.missing.length && !S.vlaJob) vlaTimer = setTimeout(() => refreshVla(false), 5000); // films dropped in later appear on their own
}
function veilVla(c, sub) {
  const st = S.vlaState || {};
  const running = S.vlaJob && (!S.vlaClips || S.vlaClips.includes(c));
  if (running) veil(c, "VLA film rendering", sub || "SmolVLA in MuJoCo · queued", true);
  else if (st.ckpt) veil(c, "VLA pending", "SmolVLA runs this scenario after the dataset", false);
  else veil(c, "VLA film rendering", "SmolVLA in MuJoCo · appears here when ready", true);
}
function showFilm(c, rec) {
  const t = tile(c); if (!t) return;
  const key = JSON.stringify(rec);
  if (S.vla[c] && S.vla[c]._key === key && $(".media video", t)) return;
  S.vla[c] = { ...rec, _key: key };
  const v = el("video"); attachVideo(v, media(`media/vla/${c}.mp4`));
  tileMedia(c, v);
  $(".vla-chip", t).hidden = false;
  const r = $(".res-chip", t);
  r.hidden = false; r.className = `res-chip ${rec.success ? "ok" : "no"}`;
  r.textContent = rec.success ? "in the bowl" : "missed";
  t.classList.add("has-film");
}
async function startVla(clips) {
  let r;
  try { r = await api("/api/vla", clips ? { slug: S.slug, clips } : { slug: S.slug }); } catch (e) { vlaNote(e.message); return; }
  S.vlaJob = r.job; S.vlaClips = r.clips;
  setStep("vla", "active");
  r.clips.forEach((c) => veilVla(c));
  renderVlaBlock();
  listen(r.job, onVla);
}
function onVla(ev) {
  if (ev.type === "vla_start") { S.vlaClips = ev.clips; ev.clips.forEach((c) => veilVla(c)); }
  else if (ev.type === "vla_wait") (S.vlaClips || []).forEach((c) => veilVla(c, "waiting for the machine's heavy-job lock"));
  else if (ev.type === "vla_clip" && ev.clip) veilVla(ev.clip, ev.stage === "load" ? `loading SmolVLA · ${ev.device}` : ev.stage === "rollout" ? "SmolVLA in MuJoCo · rollout" : "filming the episode");
  else if (ev.type === "vla_progress") veilVla(ev.clip, ev.stage === "rollout" ? `SmolVLA in MuJoCo · frame ${ev.frame}` : `filming · frame ${ev.frame} of ${ev.frames}`);
  else if (ev.type === "vla_film") { showFilm(ev.clip, ev); renderVlaBlock(); }
  else if (ev.type === "error") vlaNote(ev.message);
  else if (ev.type === "job_end") { S.vlaJob = null; S.vlaClips = null; refreshVla(false); }
}
function vlaNote(msg) { const n = $("#vla-note"); if (n) { n.textContent = msg; n.hidden = false; } }
function renderVlaBlock() {
  const b = $("#vla-block"), st = S.vlaState;
  if (!b) return;
  const acc = st ? st.accepted : S.accepted;
  const have = acc.filter((c) => S.vla[c]);
  const inBowl = have.filter((c) => S.vla[c].success).length;
  const missing = acc.filter((c) => !S.vla[c]);
  const sig = JSON.stringify([acc, have, inBowl, !!S.vlaJob, st && st.ckpt, S.task]);
  if (b.dataset.sig === sig) return; // the 5 s poll found nothing new: keep the controls as they are
  b.dataset.sig = sig;
  let html = `<p class="kicker">Step 4 · SmolVLA in MuJoCo</p>
    <p>Each tile is the fine-tuned SmolVLA itself running that scenario in the simulator: the camera, the joints and the sentence in, joint targets out. Click a tile to watch it.</p>
    <p class="vla-line">${have.length} of ${acc.length} films ready${have.length ? ` · ${inBowl} in the bowl` : ""}${S.vlaJob ? " · rendering" : ""}</p>`;
  if (st && missing.length && !S.vlaJob) {
    html += st.ckpt
      ? `<button type="button" class="ghost-btn" id="vla-run">Run SmolVLA on ${missing.length} ${missing.length === 1 ? "scenario" : "scenarios"}</button>`
      : `<pre class="term"><span class="cm"># film the missing scenarios (${missing.join(", ")}) with the fine-tuned SmolVLA</span>
<span class="pr">$</span> ${esc(st.command)}</pre>`;
  }
  html += `<p class="vla-note no" id="vla-note" hidden></p>
    <div class="more"><span>More scenarios</span><select id="more-n" aria-label="How many">${[1, 2, 3].map((k) => `<option>${k}</option>`).join("")}</select>
      <button type="button" class="ghost-btn" id="more-btn" ${S.vlaJob ? "disabled" : ""}>Generate with Runway</button><span class="more-cost" id="more-cost"></span></div>`;
  b.innerHTML = html;
  const run = $("#vla-run"); if (run) run.addEventListener("click", () => startVla());
  $("#more-n").addEventListener("change", moreCost);
  $("#more-btn").addEventListener("click", async () => {
    $("#more-btn").disabled = true;
    try { await startFootage(S.task, Number($("#more-n").value)); } catch (e) { vlaNote(e.message); $("#more-btn").disabled = false; }
  });
  moreCost();
}
async function moreCost() {
  const n = Number(($("#more-n") || {}).value || 1);
  const r = await api("/api/plan", { task: S.task, clips: n }).catch(() => null);
  const c = $("#more-cost"); if (!c || !r || !r.ok) return;
  const bal = S.budget && S.budget.balance != null ? ` · balance ${S.budget.balance}` : "";
  c.textContent = `${r.cost} credits${bal}`;
}

// the VLA view: only the film
function openVla(id) {
  const rec = S.vla[id];
  const v = $("#vla-video"), empty = $("#vla-empty");
  if (rec) { attachVideo(v, media(`media/vla/${id}.mp4`)); v.hidden = false; empty.hidden = true; }
  else { v.removeAttribute("src"); v.hidden = true; empty.hidden = false; $("#vla-empty-t").textContent = "VLA film rendering"; }
  $("#vla-cap").innerHTML = `<b>${esc(id)}</b> · VLA · SmolVLA · MuJoCo${rec ? ` · <span class="${rec.success ? "ok" : "no"}">${rec.success ? "in the bowl" : "missed"}</span> · ${rec.frames} frames at 30 fps` : ""}`;
  const box = $("#vla-view"); box.hidden = false;
  fadeIn($(".vla-card", box), 0.3, 12);
  tween(0.25, (p) => { box.style.opacity = p; });
}
function closeVla() {
  const box = $("#vla-view");
  fadeOut(box, 0.2, () => {
    box.hidden = true; box.style.opacity = 1; const v = $("#vla-video"); v.pause(); vids.delete(v);
    if (!FILM) $$(".tile video").forEach((x) => { if (x.paused) x.play().catch(() => {}); });
  });
}
$("#vla-close").addEventListener("click", closeVla);
$("#vla-view").addEventListener("click", (e) => { if (e.target.id === "vla-view") closeVla(); });
document.addEventListener("keydown", (e) => { if (e.key === "Escape") { if (!$("#vla-view").hidden) closeVla(); if (!$("#inspector").hidden) closeInspector(); } });
async function download(e) {
  // fetch the real file (so the page can say when it has arrived), then save it under its name
  e.preventDefault();
  const a = $("#dl"), st = $("#dlstate");
  if (a.classList.contains("is-busy")) return;
  a.classList.add("is-busy");
  st.textContent = "downloading...";
  const t0 = Date.now();
  const blob = await (await fetch(a.href)).blob();
  const u = URL.createObjectURL(blob);
  const x = el("a"); x.href = u; x.download = a.getAttribute("download"); document.body.append(x); x.click(); x.remove();
  st.innerHTML = `<b>Saved</b> ${esc(a.getAttribute("download"))} · ${(blob.size / 1e6).toFixed(1)} MB · ${((Date.now() - t0) / 1000).toFixed(1)} s`;
  fadeIn(st, 0.3, 4);
  S.downloaded = { bytes: blob.size, seconds: (Date.now() - t0) / 1000 };
}
document.addEventListener("pointermove", (e) => moveCursor(e.clientX, e.clientY));

// ---------- reopen a saved run (/?run=<slug>): its saved stage events, drawn by the same handlers ----------
async function reopen(slug) {
  const evs = await api(`/api/runs/${encodeURIComponent(slug)}/events`);
  const run = evs.shift();
  if (!evs.length) return;
  INSTANT = true;
  S.slug = run.slug; S.task = run.task;
  const ids = [...new Set(evs.flatMap((e) => (e.type === "runway" || e.type === "clip_ready") && e.clip ? [e.clip] : e.type === "data_start" ? e.clips : []))].sort();
  const saved = new Date(evs[evs.length - 1].ts * 1000);
  toRun(ids);
  $("#compose").hidden = true;
  $("#bar-tag").textContent = `Saved run, reopened · last stage finished ${saved.toLocaleString("en-US", { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" })}`;
  let stage = "";
  for (const ev of evs) {
    if (ev.stage !== stage) {
      stage = ev.stage;
      if (stage === "data") dataPanel();
    }
    if (stage === "footage") onFootage(ev);
    else if (stage === "data") { if (ev.type === "data_done") { S.dataset = ev; S.phase = "data_done"; setStep("data", "done"); stat("episodes", ev.episodes); } else onData(ev); }
  }
  INSTANT = false;
  await loadRouting();
  if (S.phase === "data_done") await sideDataset();
  await refreshVla(false);
  S.reopened = true;
}
{
  const want = new URLSearchParams(location.search).get("run");
  if (want) reopen(want);
}

// ---------- Model Router: pick, free dry run, per-tile routing ----------
const ROUTER_NAME = { "demo-cheap": "Cheap", "demo-fast": "Fast", "demo-best": "Best", "": "Direct" };
$$("#seg button").forEach((b) => b.addEventListener("click", () => {
  S.router = b.dataset.r;
  $$("#seg button").forEach((x) => x.setAttribute("aria-checked", String(x === b)));
  paintPick();
}));
let drySeq = 0;
async function dryRun(task) {
  const seq = ++drySeq;
  $("#pick").textContent = "Asking each router for its pick (dry run, free)...";
  const r = await api("/api/router/dryrun", { task }).catch((e) => ({ ok: false, reason: e.message }));
  if (seq !== drySeq) return;
  S.dry = r.ok ? r : null;
  if (!r.ok) { $("#pick").textContent = `Dry run unavailable: ${r.reason || ""}`; return; }
  paintPick();
}
function paintPick() {
  const el2 = $("#pick"), d = S.dry;
  $$("#seg button").forEach((b) => {
    const p = d && d.picks.find((x) => x.router === b.dataset.r);
    const sm = $("small", b);
    sm.textContent = b.dataset.r === "" ? "gen4_turbo · 25 cr" : p && p.model ? `${p.model} · ${p.estimated_credits} cr` : sm.textContent;
  });
  if (!d) return;
  if (!S.router) { el2.innerHTML = `Direct: <b>gen4_turbo</b> for every clip, 25 credits a video plus 2 for its first frame. No routing.`; return; }
  const p = d.picks.find((x) => x.router === S.router);
  if (!p || p.error) { el2.textContent = p ? p.error : ""; return; }
  el2.innerHTML = `Dry run for ${esc(d.clip)}: <b>${esc(ROUTER_NAME[S.router] || S.router)}</b> routes to <b>${esc(p.model)}</b> (${esc(p.provider)}) · about <b>${p.estimated_credits} credits</b> ($${(p.estimated_credits * 0.01).toFixed(2)}) a clip + 2 for its first frame · free, nothing spent yet`;
  fadeIn(el2, 0.25, 3);
}
function routeChip(id, r, status) {
  const t = tile(id); if (!t || !r) return;
  let c = $(".route", t);
  if (!c) { c = el("div", "route"); t.append(c); }
  const cr = r.realized_credits != null ? `${r.realized_credits} cr` : r.estimated_credits != null ? `~${r.estimated_credits} cr` : "";
  const sec = r.seconds != null ? `${Math.round(r.seconds)} s` : status && status !== "SUCCEEDED" && status !== "CACHED" ? String(status).toLowerCase() : "";
  const v = r.verdict ? (r.verdict.accepted ? '<span class="ok">physics: accepted</span>' : `<span class="no" title="${esc(r.verdict.reason)}">physics: rejected</span>`) : '<span class="pend">physics: not judged yet</span>';
  c.innerHTML = `<span class="rt">${esc(ROUTER_NAME[r.router] || r.router || "")}</span><span>${esc(r.model || "")}</span><span>${esc(cr)}</span><span>${esc(sec)}</span>${v}`;
}
function showFootage(id) {
  const t = tile(id); if (!t || S.vla[id] || $(".media video", t)) return;
  const v = el("video"); attachVideo(v, media(`clips/${id}.mp4`));
  tileMedia(id, v);
  const ch = $(".vla-chip", t); ch.hidden = false; ch.textContent = "Runway footage";
}
async function loadRouting() {
  if (!S.slug) return;
  const r = await api(`/api/runs/${encodeURIComponent(S.slug)}/routing`).catch(() => null);
  if (!r) return;
  let cr = 0;
  for (const [id, rec] of Object.entries(r.clips)) {
    if (!tile(id)) continue;
    S.routing[id] = rec; routeChip(id, rec, "SUCCEEDED"); showFootage(id);
    cr += rec.cached ? 0 : Number(rec.realized_credits || 0);
  }
  if (cr && !M.credits) { M.credits = cr; }
  meterPaint();
}

// ---------- meter: credits, dollars, wall time, accepted demos, training ----------
const M = { credits: 0, wall: 0, t0: 0, trainSec: 0, trainT0: 0, gpuUsd: null };
function meterStart() { if (!M.t0) M.t0 = Date.now() / 1000; }
function meterStop() { if (M.t0) { M.wall += Date.now() / 1000 - M.t0; M.t0 = 0; } meterPaint(); }
function meterCredits(c) { M.credits += Number(c) || 0; meterPaint(); }
const mm = (s) => `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, "0")}`;
function meterPaint() {
  const set = (k, v) => { const d = $(`.meter [data-m="${k}"] dd`); if (d) d.textContent = v; };
  const acc = S.accepted.length;
  const wall = M.wall + (M.t0 ? Date.now() / 1000 - M.t0 : 0);
  set("credits", fmt(Math.round(M.credits)));
  set("usd", `$${(M.credits * 0.01).toFixed(2)}`);
  set("wall", mm(wall));
  set("accepted", acc);
  set("cpa", acc && M.credits ? fmt(Math.round(M.credits / acc)) : "-");
  const tr = M.trainSec + (M.trainT0 ? Date.now() / 1000 - M.trainT0 : 0);
  if (tr || M.gpuUsd != null) {
    $('.meter [data-m="train"]').hidden = false; $('.meter [data-m="gpu"]').hidden = false;
    set("train", mm(tr)); set("gpu", M.gpuUsd != null ? `$${M.gpuUsd.toFixed(2)}` : "-");
  }
}
setInterval(meterPaint, 1000);

// ---------- step 3b: train the VLA on a rented GPU (the trainer script streams its progress) ----------
async function renderTrain() {
  const b = $("#train-block"); if (!b) return;
  const st = await api("/api/trainer").catch(() => ({ connected: false }));
  if (!st.connected) {
    b.innerHTML = `<p class="kicker">Train VLA</p><p class="train-off">GPU trainer not connected</p>
      <p class="train-sub">Expects <code>${esc(st.script || "~/helloworld/so101/train_vla.sh")}</code> (SmolVLA on a RunPod GPU).</p>`;
    return;
  }
  b.innerHTML = `<p class="kicker">Train VLA · SmolVLA on a GPU</p>
    <div class="more"><span>Steps</span><select id="train-steps" aria-label="Steps">${[1000, 3000, 6000, 20000].map((k) => `<option ${k === 3000 ? "selected" : ""}>${k}</option>`).join("")}</select>
    <button type="button" class="ghost-btn" id="train-btn" ${st.running ? "disabled" : ""}>Train VLA</button><span class="more-cost" id="train-state"></span></div>
    <div class="prog"><i id="train-bar"></i></div>
    <pre class="term train-term" id="train-term" hidden></pre>`;
  $("#train-btn").addEventListener("click", startTrain);
  if (st.running) listen(st.running, onTrain);
}
async function startTrain() {
  const btn = $("#train-btn"); btn.disabled = true;
  let r;
  try { r = await api("/api/train", { slug: S.slug, steps: Number($("#train-steps").value) }); }
  catch (e) { $("#train-state").textContent = e.message; btn.disabled = false; return; }
  M.trainT0 = Date.now() / 1000; M.gpuUsd = 0; meterPaint();
  listen(r.job, onTrain);
}
function onTrain(ev) {
  const term = $("#train-term");
  if (ev.type === "train_line" || ev.type === "log") {
    if (term) { term.hidden = false; term.textContent += (ev.line || "") + "\n"; term.scrollTop = term.scrollHeight; }
    if (ev.step && ev.steps) { const bar = $("#train-bar"); if (bar) widthTo(bar, (100 * ev.step) / ev.steps, 0.4); $("#train-state").textContent = `step ${ev.step} of ${ev.steps}`; }
    if (ev.usd != null) M.gpuUsd = ev.usd;
    if (ev.done) $("#train-state").textContent = "trained";
    if (ev.eval_ok != null) $("#train-state").textContent = `eval ${ev.eval_ok}/${ev.eval_n} in the bowl`;
    if (!M.trainT0) M.trainT0 = Date.now() / 1000;
  } else if (ev.type === "error") { $("#train-state").textContent = ev.message; }
  else if (ev.type === "job_end") {
    if (M.trainT0) { M.trainSec += Date.now() / 1000 - M.trainT0; M.trainT0 = 0; }
    const btn = $("#train-btn"); if (btn) btn.disabled = false;
  }
  meterPaint();
}

// ---------- the router bench (data/web-runs/<slug>/router_bench.json) ----------
async function openBench() {
  const slug = S.slug || "put-the-red-block-in-the-bowl";
  const b = await api(`/api/runs/${encodeURIComponent(slug)}/router_bench`).catch(() => null);
  const box = $("#bench-view");
  if (!b) { $("#bench-sub").textContent = "No router bench for this run yet. Run scripts/router_bench.py."; $("#bench-table").innerHTML = ""; $("#bench-clips").innerHTML = ""; }
  else paintBench(b);
  box.hidden = false; fadeIn($(".bench-card", box), 0.3, 12); tween(0.25, (p) => { box.style.opacity = p; });
  if (b && !b.judged) S.benchTimer = setTimeout(() => { if (!box.hidden) openBench(); }, 8000);
}
function paintBench(b) {
  const rows = b.table || [];
  const judged = !!b.judged;
  $("#bench-sub").innerHTML = `${esc(b.task)} · ${b.clips_per_router} clips per router, the same scenes for each (shared first frames and prompts); only the router differs. Every clip then goes through MediaPipe, the Claude audit, 21 gates and a MuJoCo replay.${judged ? "" : ' <b class="pend">Still running: numbers fill in as clips finish.</b>'}`;
  const max = Math.max(1, ...rows.map((r) => r.accepted_per_1000_credits || 0));
  const cell = (v, d = "-") => (v == null ? d : v);
  $("#bench-table").innerHTML = `<table><thead><tr><th>Router</th><th>Model chosen</th><th>Clips</th><th>Physics-accepted</th><th>Rate</th><th>Credits</th><th>$</th><th>Credits / accepted</th><th>Accepted / 1,000 cr</th><th>Mean gen</th></tr></thead><tbody>${rows.map((r) => `<tr class="${r.winner ? "win" : ""}">
    <td><b>${esc(ROUTER_NAME[r.router] || r.router)}</b><small>${esc(r.router)}${r.optimize_for ? ` · ${esc(r.optimize_for)}` : ""}</small></td>
    <td>${esc((r.models || []).join(", ") || "-")}</td><td>${r.clips}</td><td>${r.judged ? r.accepted : "-"}</td>
    <td>${r.acceptance_rate != null ? Math.round(r.acceptance_rate * 100) + "%" : "-"}</td>
    <td>${fmt(r.credits)}</td><td>$${r.usd.toFixed(2)}</td><td>${cell(r.credits_per_accepted)}</td>
    <td class="k"><span class="kbar"><i style="width:${(100 * (r.accepted_per_1000_credits || 0)) / max}%"></i></span>${cell(r.accepted_per_1000_credits)}${r.winner ? ' <span class="crown">best value</span>' : ""}</td>
    <td>${r.mean_generation_s != null ? Math.round(r.mean_generation_s) + " s" : "-"}</td></tr>`).join("")}</tbody></table>`;
  $("#bench-clips").innerHTML = (b.routers || []).map((r) => `<div class="bc-row"><span class="bc-r">${esc(ROUTER_NAME[r] || r)}</span>${b.clips.filter((c) => c.router === r).map((c) => {
    const cls = c.accepted === true ? "ok" : c.accepted === false ? "no" : c.status === "SUCCEEDED" ? "pend" : c.status === "FAILED" || c.status === "SKIPPED_BUDGET" ? "no" : "run";
    const tip = `${c.clip_id} · ${c.model || ""} · ${c.realized_credits != null ? c.realized_credits + " cr" : c.status}${c.seconds ? ` · ${Math.round(c.seconds)} s` : ""}${c.reason ? ` · ${c.reason}` : ""}`;
    return `<span class="bc ${cls}" title="${esc(tip)}">${esc(c.clip_id)}</span>`;
  }).join("")}</div>`).join("");
  $("#bench-foot").textContent = `Budget ${fmt(b.budget)} credits, hard stop from dry-run estimates${b.credits_spent_balance != null ? ` · spent ${fmt(b.credits_spent_balance)} by the live balance` : ""} · updated ${b.updated || ""}`;
}
$("#bench-btn").addEventListener("click", openBench);
function closeBench() { clearTimeout(S.benchTimer); const box = $("#bench-view"); fadeOut(box, 0.2, () => { box.hidden = true; box.style.opacity = 1; }); }
$("#bench-close").addEventListener("click", closeBench);
$("#bench-view").addEventListener("click", (e) => { if (e.target.id === "bench-view") closeBench(); });

// ---------- film hooks (only used with ?film) ----------
function moveCursor(x, y) {
  if (!FILM) return;
  const c = $("#cursor"); c.hidden = false; c.style.transform = `translate(${x}px, ${y}px)`;
}
window.__film = {
  frame,
  state: () => ({ reopened: !!S.reopened, phase: S.phase, accepted: S.accepted, rejected: S.rejected, slug: S.slug, dataset: S.ds || null, downloaded: S.downloaded || null, genEnabled: !genBtn.disabled, fit: fitEl.textContent }),
  rect: (sel) => { const n = $(sel); if (!n) return null; const r = n.getBoundingClientRect(); return { x: r.left, y: r.top, w: r.width, h: r.height }; },
  ready: async () => { await document.fonts.ready; return true; },
};
if (FILM) document.documentElement.classList.add("film");
