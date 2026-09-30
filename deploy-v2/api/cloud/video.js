// POST {prompt, image_task} -> the Model Router picks the video model for this sentence and animates the first frame.
const { runway, decide, clean, videoPrompt, isId, limit, guard, send } = require("../_lib");

module.exports = (req, res) => send(res, async () => {
  if (req.method !== "POST") throw Object.assign(new Error("POST only"), { code: 405 });
  const { prompt, image_task } = req.body || {};
  const task = clean(prompt);
  if (!isId(image_task)) throw Object.assign(new Error("bad image task"), { code: 400 });
  const img = await runway("GET", `/tasks/${image_task}`);
  if (img.status !== "SUCCEEDED" || !img.output || !img.output[0]) throw Object.assign(new Error("first frame is not ready"), { code: 409 });
  const { router } = decide(task);
  limit(req);
  await guard(router === "demo-best" ? 150 : 25);
  const t = await runway("POST", "/generate/video", {
    configId: router,
    input: { promptText: videoPrompt(task), aspectRatio: "16:9", duration: 5, referenceImages: [{ uri: img.output[0], role: "first" }] },
  });
  const r = t.routing || {};
  return { video_task: t.id, router, model: r.model || null, credits: (r.estimatedCost || {}).credits ?? null };
});
