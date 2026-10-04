// PreToolUse, matcher AskUserQuestion. During an active run in the orchestrator's own session every
// question is blocked; the reply carries any recorded decision that already answers it, and a true grant
// is appended to .orchestrator/questions.md instead. Unlock: the user's whole message is `ask`.
const { path, os, activeRun, lastHumanText, unlocked, readInput, approve, block } = require('./orch-hook-lib.js');
readInput((input) => {
  const root = activeRun(input);
  if (!root) return approve();
  if (unlocked(lastHumanText(input.transcript_path || ''), 'ask')) return approve();
  const qs = (input.tool_input && input.tool_input.questions) || [];
  const first = ((qs[0] && qs[0].question) || '').split('\n')[0].slice(0, 120);
  const script = path.join(os.homedir(), '.claude', 'skills', 'orchestrator', 'scripts', 'decisions.sh');
  const words = first.replace(/[^A-Za-z0-9 ]/g, ' ').split(/\s+/).filter((w) => w.length > 4).slice(0, 4);
  let found = '';
  if (words.length) {
    const r = require('child_process').spawnSync('bash', [script, 'find', ...words], { cwd: root, encoding: 'utf8' });
    if (r.status === 0) found = (r.stdout || '').trim().slice(0, 600);
  }
  block('No question during a run: "' + first + '". Decide at full scope; append a true grant (a file outside the approved list, an approval-gated action) to .orchestrator/questions.md and continue with the other nodes.'
    + (found ? '\nA recorded decision may already answer it:\n' + found : '') + '\nUnlock: the user sends exactly `ask`.');
});
