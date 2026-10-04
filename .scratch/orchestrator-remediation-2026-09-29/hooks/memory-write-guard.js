// PROPOSED (D9), not registered. PreToolUse, matcher Write. Creating a NEW file under a `memory/` directory of
// ~/.claude/projects/ needs the human's authorization in the last message: a non-negated remember, memorize or
// "save/add/write/update ... memory", or a named process failure (your CLAUDE.md requires a memory entry then).
// Editing an existing memory file is not gated. Unlock also: the whole message is exactly `memory`.
const { fs, authorizes, lastHumanText, unlocked, readInput, approve, block } = require('./behavior-lib.js');
const ASK = /\b(remember|memorize|(?:save|add|write|update|record)\b[^.\n]{0,30}\bmemory|process failure)\b/i;
readInput((input) => {
  const file = (input.tool_input && input.tool_input.file_path) || '';
  if (input.tool_name !== 'Write' || !/\/\.claude\/projects\/[^/]+\/memory\//.test(file) || fs.existsSync(file)) return approve();
  const said = lastHumanText(input.transcript_path || '');
  if (unlocked(said, 'memory') || authorizes(said, ASK)) return approve();
  block(`Creating ${file} was not asked for. Update an existing memory file if one covers it, or wait for the user to ask. Unlock: the user asks to remember or save it, or names a process failure, or sends exactly \`memory\`.`);
});
