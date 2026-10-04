// PROPOSED (D9), not registered. Stop hook. The trigger is ledger state, not words: when ~/.claude/active-deliverable
// names a document whose "Requirement ledger" has a row with status `open`, a reply that ends the turn must have a
// line starting `Blocked:` in its last 6 lines, or it is blocked. With no open row the hook approves whatever the
// reply says ("remaining: 0" passes). Unlock: the human's whole message is exactly `stop`.
const { activeDeliverable, openLedgerRows, lastHumanText, unlocked, readInput, approve, block } = require('./behavior-lib.js');
readInput((input) => {
  if (input.stop_hook_active) return approve();
  const doc = activeDeliverable();
  if (!doc) return approve();
  const open = openLedgerRows(doc);
  if (!open.length) return approve();
  if (unlocked(lastHumanText(input.transcript_path || ''), 'stop')) return approve();
  const tail = String(input.last_assistant_message || '').trim().split('\n').slice(-6);
  if (tail.some((l) => /^\s*Blocked:/.test(l))) return approve();
  block(`The ledger in ${doc} has open rows: ${open.join(', ')}. Finish them, or state the blocker on a line starting "Blocked:". Unlock: the user sends exactly \`stop\`.`);
});
