// PROPOSED (D9), not registered. UserPromptSubmit, non-blocking. After the second `rtk-enforce: raw` denial in the
// session transcript, add the raw-to-rtk table to each following turn.
const { fs, note, readInput, approve } = require('./behavior-lib.js');
readInput((input) => {
  let n = 0;
  try { n = (fs.readFileSync(input.transcript_path, 'utf8').match(/rtk-enforce: raw/g) || []).length; } catch { /* none */ }
  if (n < 2) return approve();
  note('UserPromptSubmit', `rtk-enforce has denied ${n} raw commands this session. Type: ls -> rtk ls; wc -> rtk wc; head/tail -> rtk proxy head/tail (or rtk read f --max-lines N / --tail-lines N); git -> rtk git; cat -> rtk read; grep -> rtk grep; find -> rtk find.`);
});
