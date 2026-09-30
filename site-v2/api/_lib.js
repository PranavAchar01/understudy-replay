// Shared helpers for the live Runway path (Vercel functions). The key lives in the RUNWAY_API_KEY env var only.
const BASE = "https://api.dev.runwayml.com/v1";
const VERSION = "2024-11-06";
const FLOOR = Number(process.env.UNDERSTUDY_CREDIT_FLOOR || 35000); // public visitors never take the balance below this
const PER_IP = 8; // start + video calls per visitor per 10 minutes (per warm instance; the floor is the hard cap)
const hits = new Map();

async function runway(method, path, body) {
  const key = process.env.RUNWAY_API_KEY;
  if (!key) throw Object.assign(new Error("live generation is not configured"), { code: 503 });
  const r = await fetch(BASE + path, {
    method,
    headers: { Authorization: `Bearer ${key}`, "X-Runway-Version": VERSION, "Content-Type": "application/json" },
    body: body ? JSON.stringify(body) : undefined,
  });
  const j = await r.json().catch(() => ({}));
  if (!r.ok) throw Object.assign(new Error(j.error || j.message || `Runway HTTP ${r.status}`), { code: r.status === 400 ? 400 : 502 });
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

function clean(prompt) {
  const p = String(prompt || "").replace(/\s+/g, " ").trim().replace(/[.!]+$/, "");
  if (p.length < 6 || p.length > 140 || !/^[a-zA-Z0-9 ,'-]+$/.test(p)) {
    throw Object.assign(new Error("Use a short plain sentence (6 to 140 letters), like \"put the green cup on the plate\"."), { code: 400 });
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
  if (recent.length >= PER_IP) throw Object.assign(new Error("That's a few runs in a row. Try again in a few minutes."), { code: 429 });
  recent.push(now); hits.set(ip, recent);
}

async function guard(cost) {
  const org = await runway("GET", "/organization");
  if ((org.creditBalance ?? 0) - cost < FLOOR) throw Object.assign(new Error("Today's live-generation budget is used up. The library below still plays."), { code: 402 });
}

const isId = (s) => /^[0-9a-f-]{36}$/i.test(String(s || ""));

function send(res, fn) {
  return fn().then((b) => res.status(200).json(b)).catch((e) => res.status(e.code || 500).json({ error: e.message }));
}

module.exports = { runway, decide, clean, imagePrompt, videoPrompt, limit, guard, isId, send };
