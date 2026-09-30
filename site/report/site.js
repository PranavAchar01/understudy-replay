// Understudy site: renders one run (window.RUN from data/run.js) and draws the dithered backdrop.
(() => {
  const R = window.RUN;
  const $ = (s) => document.querySelector(s);
  const el = (tag, attrs = {}, html = "") => {
    const e = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs)) e.setAttribute(k, v);
    if (html) e.innerHTML = html;
    return e;
  };
  const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]);

  // Night-to-studio-blue backdrop, 8x8 Bayer ordered dither, 4-step ramp, drawn at low resolution
  function dither() {
    const c = $("#dither");
    const w = 160, h = 90;
    c.width = w; c.height = h;
    const g = c.getContext("2d");
    const img = g.createImageData(w, h);
    const ramp = [[10, 14, 28], [16, 22, 44], [24, 36, 72], [34, 56, 110]];
    const B = [0, 32, 8, 40, 2, 34, 10, 42, 48, 16, 56, 24, 50, 18, 58, 26, 12, 44, 4, 36, 14, 46, 6, 38, 60, 28, 52, 20, 62, 30, 54, 22,
      3, 35, 11, 43, 1, 33, 9, 41, 51, 19, 59, 27, 49, 17, 57, 25, 15, 47, 7, 39, 13, 45, 5, 37, 63, 31, 55, 23, 61, 29, 53, 21];
    for (let y = 0; y < h; y++) for (let x = 0; x < w; x++) {
      const t = Math.max(0, (y / h) * 0.9 + 0.1 * Math.sin(x / 23)) * (ramp.length - 1);
      const i = Math.floor(t), f = t - i;
      const k = f > (B[(y % 8) * 8 + (x % 8)] + 0.5) / 64 ? Math.min(i + 1, ramp.length - 1) : i;
      const o = (y * w + x) * 4;
      [img.data[o], img.data[o + 1], img.data[o + 2]] = ramp[k];
      img.data[o + 3] = 255;
    }
    g.putImageData(img, 0, 0);
  }
  dither();

  if (!R) { $("#task").textContent = "run data missing: run scripts/build_site.py"; return; }
  $("#task").textContent = R.task;
  $("#credits").textContent = `This run: ${R.clips.length} clips, ${R.runway_calls} Runway calls, ${R.credits} credits.`;
  $("#speclink").href = "../docs/DATA-SPEC.md";

  // 2. clips
  const grid = $("#clips");
  R.clips.forEach((c) => {
    const card = el("div", { class: "clip", "data-id": c.id });
    card.innerHTML = `<video src="media/${c.id}_runway.mp4" muted loop playsinline preload="metadata"></video>
      <div class="meta"><span class="id">${c.id}</span><span class="tag ${c.accepted ? "ok" : "no"}">${c.accepted ? "ACCEPTED" : "REJECTED"}</span>
      <span class="why">${esc(c.note ? "first prompt attempt; " : "")}${esc(c.scene)}</span></div>`;
    const v = card.querySelector("video");
    card.addEventListener("mouseenter", () => v.play());
    card.addEventListener("mouseleave", () => v.pause());
    card.addEventListener("click", () => { showSkel(c.id); showGates(c.id); location.hash = "#s3"; });
    grid.append(card);
  });

  // 3. skeletons
  const pick = $("#skelpick");
  function showSkel(id) {
    const c = R.clips.find((x) => x.id === id);
    $("#skel").src = `media/${id}_skeleton.mp4`;
    $("#skelcap").innerHTML = `<b>${id}</b> hand skeleton (green), pinch point (white ring), block (amber box). ` +
      (c.lift_cm != null ? `Measured lift ${c.lift_cm} cm, carry ${c.carry_cm} cm.` : "");
    pick.querySelectorAll("button").forEach((b) => b.classList.toggle("on", b.dataset.id === id));
    document.querySelectorAll(".clip").forEach((b) => b.classList.toggle("sel", b.dataset.id === id));
  }
  R.clips.forEach((c) => {
    const b = el("button", { "data-id": c.id }, c.id);
    b.addEventListener("click", () => { showSkel(c.id); showGates(c.id); });
    pick.append(b);
  });

  // 4. gates
  const ver = $("#verdicts");
  R.clips.forEach((c) => {
    const d = el("div", { class: "verdict" });
    d.innerHTML = `<span class="id">${c.id}</span><span class="tag ${c.accepted ? "ok" : "no"}">${c.accepted ? "PASS" : "FAIL"}</span> ` +
      esc(c.accepted ? "every gate passed" : c.reason);
    d.style.cursor = "pointer";
    d.addEventListener("click", () => { showSkel(c.id); showGates(c.id); });
    ver.append(d);
  });
  function showGates(id) {
    const c = R.clips.find((x) => x.id === id);
    const rows = c.gates.map((g) => {
      const cls = g.passed === true ? "p" : g.passed === false ? "f" : "s";
      const mark = g.passed === true ? "PASS" : g.passed === false ? "FAIL" : "n/a";
      return `<tr><td class="${cls}">${mark}</td><td>${esc(g.name)}</td><td>${esc(g.value)}</td><td>${esc(g.limit)}</td><td>${esc(g.why)}</td></tr>`;
    }).join("");
    $("#gatetable").innerHTML = `<div class="tablewrap"><table><thead><tr><th>${esc(id)}</th><th>gate</th><th>measured</th><th>limit</th><th>why</th></tr></thead><tbody>${rows}</tbody></table></div>`;
  }

  // 5. dataset
  const stat = (v, k) => `<div class="stat"><span class="v">${esc(v)}</span><span class="k">${esc(k)}</span></div>`;
  const acc = R.clips.filter((c) => c.accepted);
  const ds = R.dataset || {};
  const re = R.reanchor || {};
  $("#dsstats").innerHTML = [
    stat(`${acc.length}/${R.clips.length}`, "Runway clips accepted"),
    stat(`${re.accepted ?? 0}/${re.tried ?? 0}`, "re-anchored sim copies that passed the same gates"),
    stat(ds.episodes ?? "-", "episodes in the LeRobot dataset"),
    stat(ds.frames ?? "-", `frames at ${ds.fps ?? 30} fps`),
    stat(ds.codebase_version ?? "-", "LeRobot format"),
  ].join("");
  $("#retarget").innerHTML = acc.filter((c) => c.robot).slice(0, 2).map((c) =>
    `<figure><video src="media/${c.id}_runway.mp4" muted loop playsinline autoplay></video><figcaption><b>${c.id}</b> the lead (Runway)</figcaption></figure>
     <figure><video src="media/${c.id}_robot.mp4" muted loop playsinline autoplay></video><figcaption><b>${c.id}</b> retargeted to the SO-101, MuJoCo physics replay (${R.time_scale}x slower)</figcaption></figure>`
  ).join("");

  // 6. policy
  const E = R.eval || {};
  const T = R.train || {};
  $("#evalstats").innerHTML = [
    stat(E.seeds ? `${E.successes}/${E.seeds}` : "-", "policy successes in MuJoCo (new cube positions)"),
    stat(E.wilson95 ? `${Math.round(E.wilson95[0] * 100)}-${Math.round(E.wilson95[1] * 100)}%` : "-", "Wilson 95% interval"),
    stat(T.train_seconds != null ? `${T.train_seconds}s` : "-", `CPU training, ${T.steps ?? "?"} steps`),
    stat(T.params ?? "-", "parameters"),
  ].join("");
  const films = [];
  if (E.film_success_seed != null) films.push(["success", "a success"]);
  if (E.film_failure_seed != null) films.push(["failure", "a failure (shown on purpose)"]);
  $("#rollouts").innerHTML = films.map(([t, cap]) =>
    `<figure><video src="media/policy_${t}.mp4" muted loop playsinline autoplay></video><figcaption>Trained policy, ${cap}</figcaption></figure>`).join("");
  $("#honest").textContent = "Honest limits: the policy reads joint angles and the cube position from the simulator, not pixels. " +
    "Depth is not measured from one camera, so every demonstration sits in the plane of the block and the bowl. " +
    "Re-anchored copies reuse an accepted human path with the cube moved a few centimetres; they are gated again and labelled in the dataset. " +
    "Nothing here has run on a physical arm yet.";

  const first = acc[0] || R.clips[0];
  showSkel(first.id);
  showGates((R.clips.find((c) => !c.accepted) || first).id);
})();
