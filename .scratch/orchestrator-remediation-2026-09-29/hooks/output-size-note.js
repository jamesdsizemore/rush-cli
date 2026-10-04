// PROPOSED (D9), not registered. PostToolUse, non-blocking. A tool result over 4,000 characters adds a note with its
// size and the rule: print at most 40 lines, derive the answer in ctx_execute.
const { note, readInput, approve } = require('./behavior-lib.js');
readInput((input) => {
  const r = input.tool_response;
  const s = typeof r === 'string' ? r : JSON.stringify(r || '');
  if (s.length <= 4000) return approve();
  note('PostToolUse', `That output was ${s.split('\n').length} lines, ${s.length} characters. Print at most 40 lines; derive the answer with ctx_execute or ctx_execute_file.`);
});
