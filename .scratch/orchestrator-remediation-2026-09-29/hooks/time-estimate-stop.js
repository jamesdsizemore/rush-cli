// PROPOSED (D9), not registered. Stop hook. A reply that estimates time ahead ("about 2 hours left", "should take 40
// minutes", "another 3 hours") is blocked unless it carries a `[run-state.sh report` tag, which is the measured
// elapsed/merged/rate line. Past durations ("the suite took 12 minutes") and durations with no forward word pass.
// Unlock: the human's whole message is exactly `estimate`.
const { lastHumanText, unlocked, readInput, approve, block } = require('./behavior-lib.js');
const FWD = /\b(?:about|around|roughly|approximately|should take|will take|would take|another|left|remaining|to go|from now|more)\b[^.\n]{0,40}?\b\d+(?:\.\d+)?\s*(?:hours?|hrs?|minutes?|mins?)\b|\b\d+(?:\.\d+)?\s*(?:hours?|hrs?|minutes?|mins?)\b[^.\n]{0,20}\b(?:left|remaining|to go|from now|more)\b/i;
readInput((input) => {
  if (input.stop_hook_active) return approve();
  const text = String(input.last_assistant_message || '');
  const m = FWD.exec(text);
  if (!m || text.includes('[run-state.sh report')) return approve();
  if (unlocked(lastHumanText(input.transcript_path || ''), 'estimate')) return approve();
  block(`A forward time estimate ("${m[0].trim().slice(0, 80)}") without the measured line. Run run-state.sh report and quote its elapsed/merged/rate line with its tag. Unlock: the user sends exactly \`estimate\`.`);
});
