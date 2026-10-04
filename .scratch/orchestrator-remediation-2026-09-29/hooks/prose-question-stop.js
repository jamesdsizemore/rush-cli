// Stop hook. During an active run, in the orchestrator's own session, a reply that ends in a question to the
// user is blocked. Unlock: the user's whole message is `ask`.
const { activeRun, lastHumanText, unlocked, readInput, approve, block } = require('./orch-hook-lib.js');
const Q = /^\s*(?:\d+[.)]\s*|[-*]\s*)?(?:\*\*)?(?:Should|Shall|Do you want|Would you (?:like|prefer)|Which|Want me to|Can I|May I)\b[^\n]*\?\s*$/im;
readInput((input) => {
  if (!activeRun(input)) return approve();
  if (unlocked(lastHumanText(input.transcript_path || ''), 'ask')) return approve();
  const m = Q.exec(input.last_assistant_message || '');
  if (!m) return approve();
  block('A question to the user during a run: "' + m[0].trim().slice(0, 120) + '". Decide at full scope and log a true grant to .orchestrator/questions.md. Unlock: the user sends exactly `ask`.');
});
