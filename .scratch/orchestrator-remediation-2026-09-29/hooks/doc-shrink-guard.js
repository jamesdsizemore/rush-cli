// PROPOSED (D9), not registered. PreToolUse, matcher Edit|MultiEdit. An edit to a file under docs/reports/ or
// docs/phase-plans/ that removes 10 or more lines net is denied. Unlock: the human's message asks to remove, delete,
// cut, trim or drop something, with no negation before the verb in its clause ("Do not remove anything" does not
// unlock) and a target in the same clause (it, this, that, a section, entry, paragraph, block, part, doc, file, line
// or the file's name).
const { path, authorizes, inReports, lastHumanText, readInput, approve, block } = require('./behavior-lib.js');
const count = (s) => (s ? String(s).split('\n').length : 0);
readInput((input) => {
  const ti = input.tool_input || {};
  if (!['Edit', 'MultiEdit'].includes(input.tool_name) || !inReports(ti.file_path)) return approve();
  const edits = input.tool_name === 'Edit' ? [ti] : ti.edits || [];
  const removed = edits.reduce((n, e) => n + count(e.old_string) - count(e.new_string), 0);
  if (removed < 10) return approve();
  const target = new RegExp('\\b(it|this|that|these|those|section|entry|paragraph|block|part|doc|file|line|lines|' + path.basename(ti.file_path).replace(/[.*+?^${}()|[\]\\]/g, '\\$&') + ')\\b', 'i');
  if (authorizes(lastHumanText(input.transcript_path || ''), /\b(remove|delete|cut|trim|drop)\b/i, target)) return approve();
  block(`Edit removes ${removed} lines from ${ti.file_path}. State the Ask and Action lines first. Unlock: the user asks to remove, delete, cut, trim or drop it, without a negation before that word.`);
});
