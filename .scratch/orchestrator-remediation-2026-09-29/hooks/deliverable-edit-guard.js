// PROPOSED (D9), not registered. PreToolUse, matcher Write. A Write to an existing file under docs/reports/ or
// docs/phase-plans/ that keeps fewer than 70% of the existing non-empty lines is a rewrite: deny it with "Edit it".
// Unlock: the human's message asks to rewrite, redo, overwrite or start over, and no negation sits before that verb
// in its clause ("DO NOT FUCKING REWRITE IT" does not unlock).
const { fs, authorizes, inReports, lastHumanText, readInput, approve, block } = require('./behavior-lib.js');
readInput((input) => {
  const ti = input.tool_input || {};
  const file = ti.file_path;
  if (input.tool_name !== 'Write' || !inReports(file) || !fs.existsSync(file)) return approve();
  const oldLines = fs.readFileSync(file, 'utf8').split('\n').map((s) => s.trim()).filter(Boolean);
  if (!oldLines.length) return approve();
  const keep = new Set(String(ti.content || '').split('\n').map((s) => s.trim()));
  const kept = oldLines.filter((l) => keep.has(l)).length;
  const ratio = kept / oldLines.length;
  if (ratio >= 0.7) return approve();
  if (authorizes(lastHumanText(input.transcript_path || ''), /\b(rewrite|redo|overwrite|start over)\b/i)) return approve();
  block(`Write would replace ${file} and keep ${Math.round(ratio * 100)}% of its ${oldLines.length} lines. Edit it with the Edit tool. Unlock: the user asks to rewrite, redo, overwrite or start over, without a negation before that word.`);
});
