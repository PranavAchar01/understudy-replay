// POST {prompt} with X-Runway-Key -> route the sentence, then Runway draws the first frame (gen4_image).
const { keyOf, runway, decide, clean, imagePrompt, limit, send } = require("../_lib");

module.exports = (req, res) => send(res, async () => {
  if (req.method !== "POST") throw Object.assign(new Error("POST only"), { code: 405 });
  const key = keyOf(req);
  const task = clean((req.body || {}).prompt);
  limit(req);
  const t = await runway(key, "POST", "/text_to_image", { model: "gen4_image", promptText: imagePrompt(task), ratio: "1280:720" });
  return { task, ...decide(task, (req.body || {}).budget), image_task: t.id };
});
