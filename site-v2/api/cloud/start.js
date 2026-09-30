// POST {prompt} -> route the sentence, then Runway draws the first frame (gen4_image). Returns the image task id.
const { runway, decide, clean, imagePrompt, limit, guard, send } = require("../_lib");

module.exports = (req, res) => send(res, async () => {
  if (req.method !== "POST") throw Object.assign(new Error("POST only"), { code: 405 });
  const task = clean((req.body || {}).prompt);
  const route = decide(task);
  limit(req);
  await guard(route.router === "demo-best" ? 155 : 30);
  const t = await runway("POST", "/text_to_image", { model: "gen4_image", promptText: imagePrompt(task), ratio: "1280:720" });
  return { task, ...route, image_task: t.id };
});
