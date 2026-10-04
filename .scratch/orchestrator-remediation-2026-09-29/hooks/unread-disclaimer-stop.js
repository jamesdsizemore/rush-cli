// PROPOSED (D9), not registered. Stop hook. A reply that says "I have not opened/read <X>" is blocked when <X> names a
// file that exists in the orchestrator skill, the agent definitions, the active deliverable's directory or the
// working directory: that is work I could do in the same turn. A disclaimer whose object is not a file
// ("I have not opened unrelated Codex sessions") is scope observance and passes. Unlock: the human's whole message is
// exactly `skip`.
const { fs, os, path, activeDeliverable, lastHumanText, unlocked, readInput, approve, block } = require('./behavior-lib.js');
const DISCLAIM = /\b(?:I|we)\s+(?:have not|haven't|did not|didn't)\s+(?:opened|open|read|inspected)\s+([^\n;]{1,160}?)(?=[.!?](?:\s|$)|$)/gi;
function exists(tok, roots) {
  if (path.isAbsolute(tok)) return fs.existsSync(tok);
  for (const r of roots) { try { if (fs.existsSync(path.join(r, tok))) return true; if (fs.readdirSync(r).includes(path.basename(tok))) return true; } catch { /* skip */ } }
  return false;
}
readInput((input) => {
  if (input.stop_hook_active) return approve();
  if (unlocked(lastHumanText(input.transcript_path || ''), 'skip')) return approve();
  const home = os.homedir();
  const doc = activeDeliverable();
  const roots = [path.join(home, '.claude', 'skills', 'orchestrator'), path.join(home, '.claude', 'skills', 'orchestrator', 'scripts'),
    path.join(home, '.claude', 'agents'), input.cwd || process.cwd(), ...(doc ? [path.dirname(doc)] : [])];
  const text = String(input.last_assistant_message || '');
  let m;
  DISCLAIM.lastIndex = 0;
  while ((m = DISCLAIM.exec(text))) {
    const toks = (m[1].match(/[\w./~-]+\.(?:sh|py|js|md|tsv|json|yaml|toml)\b/g) || []);
    const hit = toks.find((t) => exists(t, roots));
    if (hit) return block(`"${m[0].trim().slice(0, 100)}": ${hit} exists. Open it now, then report; a disclaimer of a file you can open is not allowed. Unlock: the user sends exactly \`skip\`.`);
  }
  approve();
});
