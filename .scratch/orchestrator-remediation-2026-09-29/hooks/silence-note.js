// PROPOSED (D9), not registered. PostToolUse, non-blocking. When 8 or more tool calls in a row have run with no
// text from me in between (checked at 8, 12, 16 ...), add a note: say in one line what you are doing and what is next.
const { fs, note, readInput, approve } = require('./behavior-lib.js');
readInput((input) => {
  let n = 0;
  try {
    const lines = fs.readFileSync(input.transcript_path, 'utf8').split('\n').filter(Boolean);
    for (let i = lines.length - 1; i >= 0; i--) {
      let e; try { e = JSON.parse(lines[i]); } catch { continue; }
      if (e.type !== 'assistant' || !e.message || !Array.isArray(e.message.content)) continue;
      const text = e.message.content.some((b) => b && b.type === 'text' && String(b.text || '').trim());
      if (text) break;
      n += e.message.content.filter((b) => b && b.type === 'tool_use').length;
    }
  } catch { return approve(); }
  if (n >= 8 && n % 4 === 0) note('PostToolUse', `${n} tool calls in a row with no text from me. Say in one line what you are doing and what comes next.`);
  else approve();
});
