// Understudy v2: one sentence -> auto-routed Runway Model Router -> physics gates -> SmolVLA films.
//   live:   the local server (GET /api/trainer answers): POST /api/footage, /api/data, /api/train, /api/vla, SSE per job
//   static: no server (Vercel): Train replays the recorded run (data/recorded.json), nothing is spent
//   ?static=1 forces the static replay.
(() => {
  const $ = (s, r = document) => r.querySelector(s);
  const el = (tag, cls, html) => { const e = document.createElement(tag); if (cls) e.className = cls; if (html != null) e.innerHTML = html; return e; };
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const wait = (ms) => new Promise((r) => setTimeout(r, ms));
  const fmt = (n) => Math.round(n).toLocaleString("en-US");
  const clock = (s) => { s = Math.max(0, Math.round(s)); const m = Math.floor(s / 60); return m >= 60 ? `${Math.floor(m / 60)}h ${m % 60}m` : `${m}:${String(s % 60).padStart(2, "0")}`; };
  const qs = new URLSearchParams(location.search);
  const DRY_FALLBACK = {
    "demo-cheap": { model: "gen4_turbo", provider: "runway", credits: 25 },
    "demo-fast": { model: "seedance2_fast", provider: "bytedance", credits: 145 },
    "demo-best": { model: "seedance2_5", provider: "bytedance", credits: 150 },
  };

  const input = $("#prompt");
  const liveBtn = $("#live");
  const state = { live: false, backend: false, route: null, dry: { ...DRY_FALLBACK }, recorded: null, running: false };

  // ---------- backend or static ----------
  const getJSON = async (url, opt = {}, ms = 0) => {
    const ctl = new AbortController(); const t = ms ? setTimeout(() => ctl.abort(), ms) : 0;
    try {
      const r = await fetch(url, { ...opt, signal: ctl.signal });
      const ct = r.headers.get("content-type") || "";
      const body = ct.includes("json") ? await r.json() : null;
      return { ok: r.ok && body != null, status: r.status, body };
    } catch { return { ok: false, status: 0, body: null }; } finally { if (t) clearTimeout(t); }
  };
  const post = (url, data) => getJSON(url, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(data) });
  const ready = (async () => {
    const [dry, rec, probe] = await Promise.all([
      getJSON("data/router-dryruns.json"), getJSON("data/recorded.json"),
      qs.has("static") ? Promise.resolve({ ok: false }) : getJSON("/api/trainer", {}, 1500),
    ]);
    if (dry.ok) for (const k of Object.keys(DRY_FALLBACK)) {
      const d = dry.body[k]; if (d && d.model) state.dry[k] = { model: d.model, provider: d.provider, credits: (d.estimatedCost || {}).credits ?? DRY_FALLBACK[k].credits };
    }
    state.recorded = rec.ok ? rec.body : null;
    state.backend = !!probe.ok;
  })();

  // ---------- auto-route (debounced) ----------
  const pill = $("#route-pill"), line = $("#route-line");
  let routeSeq = 0, routeTimer = 0;
  const textNow = () => input.value.trim() || input.placeholder;
  function paintRoute(r, dry, note) {
    const name = Route.NAME[r.router] || r.router;
    if (!state.route || state.route.router !== r.router) { pill.classList.remove("flash"); void pill.offsetWidth; pill.classList.add("flash"); }
    state.route = { ...r, dry };
    $("#route-label").textContent = name;
    line.classList.toggle("is-no", !!note);
    line.innerHTML = note ? esc(note)
      : `Routed to <b>${esc(name)}</b>: ${esc((r.reasons || []).join(", "))} · ${esc(dry.model)} · ${esc(dry.credits)} credits a clip`;
  }
  async function route() {
    const seq = ++routeSeq;
    if (!input.value.trim()) { pill.classList.add("is-empty"); line.textContent = ""; state.route = null; return; }
    pill.classList.remove("is-empty");
    const text = textNow();
    const local = Route.decide(text, { live: state.live });
    paintRoute(local, state.dry[local.router] || DRY_FALLBACK[local.router]);
    await ready;
    if (!state.backend) return;
    const r = await post("/api/route", { task: text, live: state.live });
    if (seq !== routeSeq || !r.ok || !r.body.router) return;
    const d = r.body.dryRun || r.body.dry_run || {};
    const base = state.dry[r.body.router] || DRY_FALLBACK[r.body.router] || {};
    paintRoute({ router: r.body.router, reasons: r.body.reasons && r.body.reasons.length ? r.body.reasons : local.reasons },
      { model: d.model || base.model, provider: d.provider || base.provider, credits: d.credits ?? d.estimated_credits ?? base.credits });
  }
  const routeSoon = () => { clearTimeout(routeTimer); routeTimer = setTimeout(route, 250); };
  input.addEventListener("input", routeSoon);
  liveBtn.addEventListener("click", () => { state.live = !state.live; liveBtn.setAttribute("aria-pressed", String(state.live)); route(); });
  document.querySelectorAll(".chip").forEach((c) => c.addEventListener("click", () => { input.value = c.dataset.text; input.focus(); route(); }));
  route();

  // ---------- GPU for SmolVLA training (RunPod on-demand, prices seen 2026-09-30) ----------
  const GPUS = [
    { key: "4090", label: "4090", id: "NVIDIA GeForce RTX 4090", price: "$0.34/h" },
    { key: "5090", label: "5090", id: "NVIDIA GeForce RTX 5090", price: "$0.69/h", speed: "3,000 steps in 9 min" },
    { key: "l40s", label: "L40S", id: "NVIDIA L40S", price: "$0.79/h" },
    { key: "a100", label: "A100 80GB", id: "NVIDIA A100 80GB PCIe", price: "$1.19/h" },
    { key: "h100", label: "H100", id: "NVIDIA H100 80GB HBM3", price: "price varies" },
  ];
  state.gpu = GPUS[1];
  state.runTimes = {};

  // ---------- run time (the Time card) ----------
  const M = { t0: 0, seconds: null, timer: 0 };
  const paintTime = () => { $('.stats [data-m="time"] b').textContent = clock(M.seconds != null ? M.seconds : M.t0 ? Date.now() / 1000 - M.t0 : 0); };
  function timeStart() { Object.assign(M, { t0: Date.now() / 1000, seconds: null }); clearInterval(M.timer); M.timer = setInterval(paintTime, 500); paintTime(); }
  function timeStop() { if (M.seconds == null && M.t0) M.seconds = Date.now() / 1000 - M.t0; clearInterval(M.timer); paintTime(); if (CUR.slug) state.runTimes[CUR.slug] = M.seconds; }
  const gpuSeg = $("#gpu-seg"), gpuHint = $("#gpu-hint");
  function paintGpu() {
    gpuSeg.querySelectorAll("button").forEach((b) => b.setAttribute("aria-checked", String(b.dataset.gpu === state.gpu.key)));
    gpuHint.textContent = state.gpu.speed ? `${state.gpu.price} · ${state.gpu.speed}` : state.gpu.price;
  }
  for (const g of GPUS) {
    const b = el("button", null, esc(g.label)); b.type = "button"; b.dataset.gpu = g.key; b.setAttribute("role", "radio"); b.title = `${g.id} · ${g.price}`;
    b.addEventListener("click", () => { state.gpu = g; paintGpu(); });
    gpuSeg.append(b);
  }
  paintGpu();

  // ---------- run head + tiles ----------
  // running-job text lives as a tiny label on this run's unfinished tiles; cleared when the run ends
  const status = (t, done = false) => document.querySelectorAll(`#grid .tile[data-run="${RUN}"]`).forEach((n) => {
    const s = $(".tile-run", n); s.textContent = done ? "" : t; s.hidden = done || !t;
  });
  const tiles = new Map();
  let RUN = 0, CUR = { title: "", router: "", slug: "" };
  const STATE = {
    queued: ["wait", "Queued"], gen: ["", "Runway generating"], physics: ["", "Physics check"],
    ok: ["ok", "Accepted"], no: ["no", "Rejected"], train: ["", "SmolVLA training"], film: ["", "SmolVLA filming"],
  };
  function tile(id, grid = $("#grid"), key = `${RUN}:${id}`, meta = null) {
    if (tiles.has(key)) return tiles.get(key);
    const root = el("article", "tile");
    const m = meta || CUR;
    root.dataset.run = meta ? "lib" : String(RUN);
    if (m.slug) root.dataset.slug = m.slug;
    root.innerHTML = `<span class="tile-id"><span class="route-pill xs">${pillHTML(m.router)}</span><span class="tile-title">${esc(m.title || id)}</span></span><video muted loop playsinline preload="metadata"></video>
      <div class="tile-state"><span class="status wait"><i></i><span>Queued</span></span><small></small></div>
      <span class="tile-cap"></span><span class="tile-run" hidden></span>`;
    const older = meta ? null : [...grid.children].find((c) => c.dataset.run !== String(RUN));
    if (older) grid.insertBefore(root, older); else grid.append(root);
    const t = {
      root, src: null,
      set(k, note = "") {
        const [cls, label] = STATE[k];
        const s = $(".status", root); s.className = `status ${cls}`; $("span", s).textContent = label;
        $("small", root).textContent = note; root.classList.toggle("is-no", k === "no"); return t;
      },
      film(src, success = true, cap = null) {
        const v = $("video", root); t.src = src;
        v.onerror = () => { root.classList.remove("is-film"); t.set("film", "film not found"); };
        v.muted = true; v.loop = true; v.autoplay = true; v.playsInline = true;
        v.src = src; v.play().catch(() => {}); v.oncanplay = () => { if (v.paused) v.play().catch(() => {}); };
        const c = $(".tile-cap", root); c.textContent = cap || `SmolVLA · ${success ? "in the bowl" : "missed"}`; c.classList.toggle("miss", !success);
        root.classList.add("is-film"); return t;
      },
    };
    root.addEventListener("click", () => { if (root.classList.contains("is-film")) openOverview(root.dataset.slug, t.src, m); });
    tiles.set(key, t);
    return t;
  }
  const pillHTML = (router) => `<span class="robot-dot"></span><span>${esc(Route.NAME[router] || router || "")}</span>`;
  function startRun(task, head, router) {
    RUN++; CUR = { title: task, router, slug: "" };
    $("#fleet").hidden = false; $("#run-task").textContent = task; $("#run-pill").innerHTML = pillHTML(router); status(head); timeStart();
    requestAnimationFrame(() => window.scrollTo({ top: $("#fleet").getBoundingClientRect().top + scrollY - 12, behavior: "smooth" }));
  }

  // ---------- overview: the film plus how its VLA was trained (data/overview.json, keyed by slug) ----------
  //   the film's own JSON (<clip>.json) overrides eval {successes, seeds} and download when present
  const sheet = $("#sheet"), sv = $("#sheet-video"), steps = $("#ov-steps"), dl = $("#ov-dl");
  let overview = null, ovSeq = 0;
  const loadOverview = () => (overview ||= getJSON(`data/overview.json?t=${Date.now()}`).then((r) => (r.ok ? r.body : {})));
  const num = (n) => (n == null || n === "" ? "" : typeof n === "number" ? fmt(n) : esc(n));
  const join = (...xs) => xs.filter((x) => x != null && x !== "").join(" · ");
  function renderOverview(o, meta, film) {
    const r = o.route || {}, d = o.demonstrations || {}, ds = o.dataset || {}, t = o.training || {};
    const ev = (film && film.eval && film.eval.seeds ? film.eval : null) || (o.result && o.result.seeds ? o.result : null);
    const secs = state.runTimes[meta.slug] ?? o.run_seconds ?? null;
    const url = (film && film.download) || (o.download && o.download.url) || "";
    const row = (k, main, sub = "") => `<li><span class="ov-k">${k}</span><p class="ov-v">${main}</p>${sub ? `<p class="ov-s">${sub}</p>` : ""}</li>`;
    steps.innerHTML = [
      row("Prompt", `<q>${esc(o.prompt || meta.title || "")}</q>`),
      row("Route", join(`<b>${esc(r.router || Route.NAME[meta.router] || "")}</b> router`, esc(r.model), r.credits_per_clip != null ? `${num(r.credits_per_clip)} credits a clip` : ""), esc(r.note || "")),
      row("Demonstrations", d.generated != null ? `${num(d.generated)} clips generated, <b>${num(d.accepted)}</b> physics-accepted` : `<b>${num(d.episodes)}</b> episodes`,
        join(esc(d.rejected || ""), esc(d.source || ""))),
      row("Dataset", join(ds.episodes != null ? `<b>${num(ds.episodes)}</b> episodes` : "", ds.frames != null ? `${num(ds.frames)} frames` : ""), ds.cameras ? `cameras ${esc(ds.cameras)}` : ""),
      row("Training", join(`${esc(t.base || "SmolVLA")} base`, t.steps != null ? `<b>${num(t.steps)}</b> steps` : ""), join(esc(t.gpu || ""), esc(t.time || ""), esc(t.cost || ""))),
      row("Time", join(secs != null ? `<b>${clock(secs)}</b> demo pipeline` : "", t.time ? `${esc(t.time)} training` : "") || `<span class="ov-pending">not recorded yet</span>`,
        secs != null ? "sentence to physics-accepted dataset, then SmolVLA training" : ""),
      row("Result", ev ? `<b class="ov-score">${num(ev.successes)}/${num(ev.seeds)}</b>` : `<span class="ov-pending">Evaluating</span>`,
        ev ? esc((o.result && o.result.note) || "in simulation") : "score in simulation"),
    ].join("");
    if (url) { dl.href = url; dl.removeAttribute("aria-disabled"); dl.innerHTML = `Download VLA${o.download && o.download.size && !(film && film.download) ? ` <small>${esc(o.download.size)}</small>` : ""}`; }
    else { dl.removeAttribute("href"); dl.setAttribute("aria-disabled", "true"); dl.innerHTML = "Download VLA <small>uploading</small>"; }
  }
  async function openOverview(slug, src, meta) {
    const seq = ++ovSeq;
    sv.src = src; sheet.hidden = false; document.body.classList.add("is-locked"); sv.play().catch(() => {});
    const all = await loadOverview();
    if (seq !== ovSeq) return;
    const o = all[slug] || {};
    renderOverview(o, meta, null);
    const j = await getJSON(String(src).replace(/\.mp4(\?.*)?$/, ".json"));
    if (seq === ovSeq && j.ok && (j.body.eval || j.body.download)) renderOverview(o, meta, j.body);
  }
  function closeFilm() { ovSeq++; sheet.hidden = true; sv.pause(); sv.removeAttribute("src"); sv.load(); document.body.classList.remove("is-locked"); }
  $("#sheet-close").addEventListener("click", closeFilm);
  $("#sheet-backdrop").addEventListener("click", closeFilm);
  dl.addEventListener("click", (e) => { if (dl.getAttribute("aria-disabled") === "true") e.preventDefault(); });
  document.addEventListener("keydown", (e) => { if (e.key === "Escape" && !sheet.hidden) closeFilm(); });

  // ---------- one row per prompt: data/three-prompts.json
  //   [{prompt, slug, router, model, credits, clips, accepted, episodes, frames, seconds?, eval: {successes, seeds}, tiles_dir}]
  async function manifest() {
    for (const u of state.backend ? ["/api/three-prompts", "data/three-prompts.json"] : ["data/three-prompts.json"]) {
      const r = await getJSON(`${u}?t=${Date.now()}`);
      if (r.ok) return Array.isArray(r.body) ? r.body : Array.isArray(r.body.prompts) ? r.body.prompts : [];
    }
    return [];
  }
  const score = (e) => (e && e.seeds ? `SmolVLA <b>${e.successes}/${e.seeds}</b>` : "");
  const count = (x) => (Array.isArray(x) ? x.length : x);
  async function prompts(mainSlug, base) {
    const rows = await manifest();
    for (const e of rows) {
      if (!e || !e.slug || document.querySelector(`#grid .tile[data-slug="${e.slug}"]`)) continue;
      const dir = String(e.tiles_dir || "media/vla").replace(/^.*\/web-runs\/[^/]+\//, "").replace(/^\/+|\/+$/g, "");
      let ids = Array.isArray(e.accepted) ? e.accepted : Array.isArray(e.films) ? e.films : [];
      if (!ids.length && state.backend) { const v = await getJSON(`/api/runs/${e.slug}/vla`); if (v.ok) ids = Object.keys(v.body.films || {}); }
      if (!ids.length) continue;
      const id = String(ids[0]).replace(/\.mp4$/, ""), url = `${base}/${e.slug}/${dir}/${id}.mp4`;
      const t = tile(id, $("#grid"), `lib:${e.slug}`, { title: e.prompt || e.slug, router: e.router, slug: e.slug }).film(url, true, "SmolVLA");
      getJSON(url.replace(/\.mp4$/, ".json")).then((j) => {
        if (!j.ok || j.body.success == null) return;
        const c = $(".tile-cap", t.root); c.textContent = `SmolVLA · ${j.body.success ? "success" : "missed"}`; c.classList.toggle("miss", !j.body.success);
      });
    }
  }


  // ---------- static: replay the recorded run ----------
  async function replay(_text, fast = false) {
    const R = state.recorded;
    const wait_ = (ms) => (fast ? Promise.resolve() : wait(ms));
    if (!R) { line.classList.add("is-no"); line.textContent = "No recorded run on this page."; return; }
    const tag = `Recorded run · ${R.model} · no credits spent`;
    // static site: a typed push / stack prompt replays that recorded example; anything else replays the pick run
    const typed = String(_text || "").toLowerCase();
    const want = /\bpush|shove|slide\b/.test(typed) ? "push" : /\bstack|tower|on top\b/.test(typed) ? "stack" : null;
    const lib = want && !fast ? (await manifest()).find((e) => e && e.slug && e.slug.startsWith(want)) : null;
    startRun(lib ? lib.prompt : R.task, tag, lib ? lib.router : R.router);
    const filmDir = lib ? `runs/${lib.slug}/${lib.tiles_dir || "media/vla"}` : `runs/${R.slug}/media/vla`;
    const hero = lib ? { id: lib.accepted[0], film: `${lib.accepted[0]}.mp4`, success: true }
      : R.clips.find((c) => c.accepted && c.film && c.success !== false) || R.clips.find((c) => c.film);
    CUR.slug = lib ? lib.slug : R.slug;
    document.querySelectorAll(`#grid .tile[data-slug="${CUR.slug}"]`).forEach((n) => n.remove());
    const t = tile(hero ? hero.id : "demo");
    const T = fast ? 0 : 9000, t0 = performance.now();
    M.t0 = 0; M.seconds = 0; clearInterval(M.timer);
    const tick = () => { const f = T ? Math.min(1, (performance.now() - t0) / T) : 1; M.seconds = R.seconds * f; paintTime(); if (f < 1 && state.running) requestAnimationFrame(tick); };
    requestAnimationFrame(tick);
    status("Runway generating · recorded run"); t.set("gen"); await wait_(1600);
    status("Physics check · 21 gates in MuJoCo"); t.set("physics"); await wait_(1800);
    t.set("ok"); await wait_(700);
    status(`SmolVLA training on ${R.episodes} episodes`); t.set("train");
    await wait_(Math.max(0, T - (performance.now() - t0) - 600));
    if (hero) t.film(`${filmDir}/${hero.film}`, hero.success !== false);
    M.seconds = R.seconds; paintTime(); state.runTimes[R.slug] = R.seconds;
    status("", true);
    prompts(R.slug, "runs");
  }

  // ---------- live: the real pipeline ----------
  const job = (id, on) => new Promise((resolve) => {
    const es = new EventSource(`/api/jobs/${encodeURIComponent(id)}/events`);
    let ok = false;
    es.onmessage = (m) => { let ev; try { ev = JSON.parse(m.data); } catch { return; } if (ev.type === "job_end") { ok = !!ev.ok; es.close(); resolve(ok); return; } on(ev); };
    es.onerror = () => { if (es.readyState === EventSource.CLOSED) resolve(ok); };
  });
  const why = (r, fallback) => (r.body && (r.body.reason || r.body.detail)) || fallback;
  const short = (s, n = 42) => (String(s).length > n ? String(s).slice(0, n - 1) + "…" : String(s));

  async function live(text) {
    const rt = state.route || Route.decide(text, { live: state.live });
    const f = await post("/api/footage", { task: text, router: rt.router });
    if (!f.ok) { paintRoute(rt, rt.dry || DRY_FALLBACK[rt.router], why(f, f.status === 409 ? "A stage is still running." : "The server refused this task.")); return; }
    const { slug, clip_ids: ids = [], existing = [] } = f.body;
    const name = Route.NAME[rt.router] || rt.router;
    startRun(text, `Live · ${(rt.dry || {}).model || name}`, rt.router); CUR.slug = slug;
    const base = "/runs";
    // scenarios this sentence already had keep their films
    if (existing.length) {
      const v = await getJSON(`/api/runs/${slug}/vla`);
      for (const c of existing) {
        const film = v.ok && v.body.films[c];
        if (film) tile(c).film(`${base}/${slug}/media/vla/${c}.mp4`, film.success !== false);
      }
    }
    ids.forEach((c) => tile(c));
    status(`Runway generating · ${name}`);
    const okFoot = await job(f.body.job, (ev) => {
      if (ev.type === "runway" && ev.clip) {
        tile(ev.clip).set("gen", ev.stage === "frame" ? "first frame" : (ev.model || ""));
      } else if (ev.type === "clip_ready") tile(ev.clip).set("physics", "queued");
      else if (ev.type === "error") status(short(ev.message, 80));
    });
    if (!okFoot) { timeStop(); status("", true); paintRoute(rt, rt.dry || DRY_FALLBACK[rt.router], "Runway stage failed"); return; }

    const d = await post("/api/data", { slug });
    if (!d.ok) { timeStop(); status("", true); paintRoute(rt, rt.dry || DRY_FALLBACK[rt.router], why(d, "Physics stage refused")); return; }
    status("Physics check · 21 gates in MuJoCo");
    const accepted = [];
    await job(d.body.job, (ev) => {
      if (ev.type === "clip_stage" && tiles.has(ev.clip)) tile(ev.clip).set("physics", ev.stage || "");
      else if (ev.type === "verdict" && ev.clip) {
        if (ev.accepted) accepted.push(ev.clip);
        tile(ev.clip).set(ev.accepted ? "ok" : "no", ev.accepted ? `${ev.gates_passed || 21} of ${ev.gates_total || 21} gates` : short(ev.reason || "rejected"));
      } else if (ev.type === "episodes") status(`${ev.total} episodes for SmolVLA`);
    });
    if (!accepted.length) { timeStop(); status("", true); paintRoute(rt, rt.dry || DRY_FALLBACK[rt.router], "No clip passed the physics gates"); return; }

    // SmolVLA on a rented GPU, when the trainer is connected
    const tr = await getJSON("/api/trainer");
    accepted.forEach((c) => tile(c).set("train"));
    if (tr.ok && tr.body.connected) {
      const t = await post("/api/train", { slug, gpu: state.gpu.id });
      if (t.ok) {
        status(`SmolVLA training on ${state.gpu.label}`);
        await job(t.body.job, (ev) => {
          if (ev.type === "train_line") status(`${state.gpu.label} · ${clock(ev.seconds || 0)}${ev.usd != null ? ` · $${Number(ev.usd).toFixed(2)}` : ""}${ev.step && ev.steps ? ` · step ${ev.step}/${ev.steps}` : ""}`);
        });
      }
    }
    timeStop();
    const v = await post("/api/vla", { slug, clips: accepted });
    status(v.ok ? "SmolVLA filming in MuJoCo" : "Waiting for SmolVLA films");
    accepted.forEach((c) => tile(c).set("film"));
    const shown = new Set();
    for (let i = 0; i < 360 && shown.size < accepted.length; i++) {
      const s = await getJSON(`/api/runs/${slug}/vla`);
      if (s.ok) for (const c of accepted) {
        const film = s.body.films[c];
        if (film && !shown.has(c)) { shown.add(c); tile(c).film(`${base}/${slug}/media/vla/${c}.mp4?t=${Date.now()}`, film.success !== false); }
      }
      if (shown.size < accepted.length) await wait(5000);
    }
    const mine = [...document.querySelectorAll(`#grid .tile[data-run="${RUN}"]`)];
    const first = mine.find((n) => n.classList.contains("is-film"));
    if (first) mine.forEach((n) => { if (n !== first) n.remove(); });
    status(shown.size ? "" : "Films still rendering", !!shown.size);
    prompts(slug, base);
  }

  // ---------- Train ----------
  $("#composer").addEventListener("submit", async (ev) => {
    ev.preventDefault();
    if (state.running) return;
    const text = textNow();
    state.running = true; $("#go").disabled = true;
    try { await ready; await (state.backend ? live(text) : replay(text)); }
    finally { state.running = false; $("#go").disabled = false; }
  });

  // keep every tile film playing while it is on screen (browsers pause muted autoplay offscreen or during load)
  const playIO = new IntersectionObserver((es) => es.forEach((e) => { const v = e.target; if (e.isIntersecting && v.src && v.paused) v.play().catch(() => {}); }), { threshold: 0.2 });
  new MutationObserver(() => document.querySelectorAll("video").forEach((v) => { if (!v.__io) { v.__io = 1; playIO.observe(v); } })).observe(document.body, { childList: true, subtree: true });
  document.addEventListener("visibilitychange", () => { if (!document.hidden) document.querySelectorAll("video").forEach((v) => { if (v.src && v.paused && v.getBoundingClientRect().top < innerHeight) v.play().catch(() => {}); }); });

  // ---------- library: finished runs are already on the page when you scroll down ----------
  ready.then(async () => {
    if (qs.get("preload") === "0" || !state.recorded || state.running) return;
    state.running = true;
    try { await replay(null, true); } finally { state.running = false; }
  });
})();
