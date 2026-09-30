// GET ?id=<task id> -> {status, progress, output}
const { runway, isId, send } = require("../_lib");

module.exports = (req, res) => send(res, async () => {
  const id = (req.query || {}).id;
  if (!isId(id)) throw Object.assign(new Error("bad task id"), { code: 400 });
  const t = await runway("GET", `/tasks/${id}`);
  return { status: t.status, progress: t.progress ?? null, output: t.output || null, failure: t.failure || null };
});
