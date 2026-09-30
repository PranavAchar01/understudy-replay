// Auto-routing: the sentence picks the Runway Model Router, the user never does.
// A transparent rubric:
//   hard cues (deformable, liquid, two hands, several steps, precision) -> Best: the video must get the physics right
//   live on stage (the Live toggle)                                      -> Fast: lowest latency
//   everything else (one rigid object, one hand)                         -> Cheap: an easy scene, cheapest usable clip
//   Route.decide(text, {live}) -> {router: "demo-best" | "demo-fast" | "demo-cheap", reasons: [...]}
(() => {
  const BEST = [
    [/\b(cloth|laundry|towel|shirt|sock|sheet|napkin|fabric|fold|folding|crumple|rope|cable|string|wire|bag|dough|paper)\b/, (m) => `${deform(m[1])} is deformable`],
    [/\b(pour|pouring|liquid|water|juice|coffee|milk|spill|wipe|splash)\b/, () => "liquids move on their own"],
    [/\b(two hands|both hands|bimanual|two arms|both arms|handover)\b/, () => "needs two hands"],
    [/\b(then|after that|stack|tower|sort|arrange|every|all the|each|assemble|build)\b/, () => "several steps"],
    [/\b(insert|thread|peg|plug|screw|needle|precise|precisely|carefully|tiny|align)\b/, () => "needs precision"],
  ];
  const deform = (w) => (w === "fold" || w === "folding" ? "cloth" : w);
  const norm = (s) => String(s || "").toLowerCase().replace(/[^a-z0-9 ]+/g, " ").replace(/\s+/g, " ").trim();

  function decide(text, opts = {}) {
    const t = norm(text);
    const hard = [];
    for (const [re, why] of BEST) { const m = t.match(re); if (m && !hard.includes(why(m))) hard.push(why(m)); }
    if (opts.live) return { router: "demo-fast", reasons: ["live: lowest latency"] };
    if (hard.length) return { router: "demo-best", reasons: hard };
    return { router: "demo-cheap", reasons: [t ? "one rigid object, one hand" : "an easy scene"] };
  }

  const NAME = { "demo-cheap": "Cheap", "demo-fast": "Fast", "demo-best": "Best" };
  window.Route = { decide, NAME };
})();
