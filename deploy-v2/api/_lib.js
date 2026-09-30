// Shared helpers for the live Runway path (Vercel functions). Bring your own key: every call uses the visitor's
// Runway API key from the X-Runway-Key header. It is forwarded to Runway only, never stored or logged.
const BASE = "https://api.dev.runwayml.com/v1";
const VERSION = "2024-11-06";
const PER_IP = 12; // calls per visitor per 10 minutes (per warm instance)
const hits = new Map();

const fail = (msg, code) => Object.assign(new Error(msg), { code });

function keyOf(req) {
  const k = String(req.headers["x-runway-key"] || "").trim();
  if (!k) throw fail("Add your Runway API key to generate new prompts.", 401);
  if (!/^key_[A-Za-z0-9_-]{16,300}$/.test(k)) throw fail("That doesn't look like a Runway API key (it starts with key_).", 401);
  return k;
}

async function runway(key, method, path, body) {
  const r = await fetch(BASE + path, {
    method,
    headers: { Authorization: `Bearer ${key}`, "X-Runway-Version": VERSION, "Content-Type": "application/json" },
    body: body ? JSON.stringify(body) : undefined,
  });
  const j = await r.json().catch(() => ({}));
  if (r.status === 401 || r.status === 403) throw fail("Runway rejected this API key.", 401);
  if (!r.ok) throw fail(j.error || j.message || `Runway HTTP ${r.status}`, r.status === 400 || r.status === 404 ? r.status : 502);
  return j;
}

// the same rubric as route.js: hard cues go to Best, everything else to Cheap (Fast is live-stage only)
const BEST = [
  [/\b(cloth|laundry|towel|shirt|sock|sheet|napkin|fabric|fold|folding|crumple|rope|cable|string|wire|bag|dough|paper)\b/, "deformable object"],
  [/\b(pour|pouring|liquid|water|juice|coffee|milk|spill|wipe|splash)\b/, "liquids move on their own"],
  [/\b(two hands|both hands|bimanual|two arms|both arms|handover)\b/, "needs two hands"],
  [/\b(then|after that|stack|tower|sort|arrange|every|all the|each|assemble|build)\b/, "several steps"],
  [/\b(insert|thread|peg|plug|screw|needle|precise|precisely|carefully|tiny|align)\b/, "needs precision"],
];
function decide(text) {
  const t = text.toLowerCase().replace(/[^a-z0-9 ]+/g, " ").replace(/\s+/g, " ").trim();
  const reasons = BEST.filter(([re]) => re.test(t)).map(([, why]) => why);
  return reasons.length ? { router: "demo-best", reasons } : { router: "demo-cheap", reasons: ["one rigid object, one hand"] };
}

// the visitor's account gets the same two Model Routers the first time it is used (Cheap = cost, Best = quality)
const ROUTERS = {
  "demo-cheap": { slug: "understudy-cheap", optimizeFor: "cost" },
  "demo-best": { slug: "understudy-best", optimizeFor: "quality" },
};
async function ensureRouter(key, router) {
  const want = ROUTERS[router];
  const have = await runway(key, "GET", "/routers");
  if ((have.data || []).some((r) => r.slug === want.slug || r.name === want.slug)) return want.slug;
  const made = await runway(key, "POST", "/routers", {
    slug: want.slug,
    name: want.slug,
    description: `Understudy robot demonstrations, optimize for ${want.optimizeFor}`,
    settings: { schemaVersion: 1, models: { mode: "allow_new_except", ids: [] }, optimizeFor: want.optimizeFor, fallback: { onCapacity: true } },
  });
  return made.slug || made.name || want.slug;
}

function clean(prompt) {
  const p = String(prompt || "").replace(/\s+/g, " ").trim().replace(/[.!]+$/, "");
  if (p.length < 6 || p.length > 140 || !/^[a-zA-Z0-9 ,'-]+$/.test(p)) {
    throw fail("Use a short plain sentence (6 to 140 letters), like \"put the green cup on the plate\".", 400);
  }
  return p;
}

// PhyT2V-style positive phrasing, generalized from plan.py's v1 prompts
const imagePrompt = (task) =>
  `Photorealistic photo, three-quarter view from slightly above, of a plain light wooden tabletop holding only the few ` +
  `simple objects needed to ${task}. Nothing else is on the table. A person's right hand hovers just above the first ` +
  `object, fingers open, ready to grasp it; the forearm enters from the right edge of the frame. The whole hand and ` +
  `every object are fully in frame and unobstructed. Soft even daylight. Sharp focus, no text.`;
const videoPrompt = (task) =>
  `The right hand does this: ${task}. One continuous smooth motion at natural speed, then the open hand moves back up ` +
  `and away. Static camera, locked off. Every object keeps its shape, size and count the whole time.`;

function limit(req) {
  const ip = String(req.headers["x-forwarded-for"] || "").split(",")[0].trim() || "?";
  const now = Date.now(), recent = (hits.get(ip) || []).filter((t) => now - t < 600000);
  if (recent.length >= PER_IP) throw fail("That's a lot of runs in a row. Try again in a few minutes.", 429);
  recent.push(now); hits.set(ip, recent);
}

const isId = (s) => /^[0-9a-f-]{36}$/i.test(String(s || ""));

function send(res, fn) {
  res.setHeader("Cache-Control", "no-store");
  return fn().then((b) => res.status(200).json(b)).catch((e) => res.status(e.code || 500).json({ error: e.message }));
}

module.exports = { keyOf, runway, decide, ensureRouter, clean, imagePrompt, videoPrompt, limit, isId, send };
