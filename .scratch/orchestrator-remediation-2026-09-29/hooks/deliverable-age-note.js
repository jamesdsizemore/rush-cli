// PROPOSED (D9), not registered. UserPromptSubmit, non-blocking. When ~/.claude/active-deliverable names a file, add
// the minutes since it was last edited to the top of the turn.
const { fs, activeDeliverable, note, readInput, approve } = require('./behavior-lib.js');
readInput(() => {
  const doc = activeDeliverable();
  if (!doc) return approve();
  const mins = Math.round((Date.now() - fs.statSync(doc).mtimeMs) / 60000);
  note('UserPromptSubmit', `The active deliverable ${doc} was last edited ${mins} minutes ago.`);
});
