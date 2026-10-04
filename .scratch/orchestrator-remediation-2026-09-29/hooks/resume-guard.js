// PreToolUse, matcher SendMessage. A second message to an implementer that has already reported is a
// continuation loop: block it. Other roles, and a message that starts with `SCOPE:` (a correction of scope
// from the user), are not limited. Unlock: the user's whole message is `resume`.
const { fs, path, activeRun, lastHumanText, unlocked, readInput, approve, block } = require('./orch-hook-lib.js');
readInput((input) => {
  const root = activeRun(input);
  if (!root) return approve();
  if (unlocked(lastHumanText(input.transcript_path || ''), 'resume')) return approve();
  const ti = input.tool_input || {};
  const to = ti.to;
  const body = typeof ti.message === 'string' ? ti.message : JSON.stringify(ti.message || '');
  if (!to || /^\s*SCOPE:/.test(body)) return approve();
  let role = '';
  try {
    for (const l of fs.readFileSync(path.join(root, '.orchestrator', 'agents.active'), 'utf8').split('\n')) {
      const p = l.trim().split(/\s+/);
      if (p[0] === to) role = p[2];
    }
  } catch { /* no registry */ }
  if (role !== 'impl') return approve();
  let sent = 0;
  try {
    for (const l of fs.readFileSync(input.transcript_path, 'utf8').split('\n')) {
      if (!l.includes('SendMessage')) continue;
      let e; try { e = JSON.parse(l); } catch { continue; }
      const c = e.message && Array.isArray(e.message.content) ? e.message.content : [];
      for (const b of c) if (b && b.type === 'tool_use' && b.name === 'SendMessage' && b.input && b.input.to === to) sent++;
    }
  } catch { /* no transcript */ }
  if (sent >= 1) return block(`${to} (implementer) already received a message. Take what it reported and finish the rest in a fresh packet built from its checkpoint. A scope correction starts with "SCOPE:". Unlock: the user sends exactly \`resume\`.`);
  approve();
});
