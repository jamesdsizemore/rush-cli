// Shared by the J-series hooks (proposed, not registered). Same human-message classifier as orch-hook-lib.js.
const base = require('./orch-hook-lib.js');
const fs = base.fs, path = base.path, os = base.os;

const NEG = /\b(?:do not|don't|dont|never|not|no|stop|without|instead of|nothing to)\b(?:\W+\w+){0,4}\W*$/i;

// The human's message authorizes an action when a clause contains the verb and nothing before the verb in that
// clause negates it. "DO NOT FUCKING REWRITE IT" and "Do not remove anything" do not authorize; "rewrite it" does.
// Clauses split on sentence ends, semicolons, line breaks and a spaced dash.
function authorizes(text, verbRe, targetRe) {
  if (!text) return false;
  for (const clause of String(text).split(/[.!?;\n]+|\s[-–—]\s/)) {
    const flags = verbRe.flags.includes('g') ? verbRe.flags : verbRe.flags + 'g';
    const re = new RegExp(verbRe.source, flags);
    let m;
    while ((m = re.exec(clause))) {
      if (NEG.test(clause.slice(0, m.index))) continue;
      if (targetRe && !targetRe.test(clause)) continue;
      return true;
    }
  }
  return false;
}

// The deliverable a session is working on: ~/.claude/active-deliverable holds one absolute path.
const ACTIVE = process.env.ACTIVE_DELIVERABLE || path.join(os.homedir(), '.claude', 'active-deliverable');
function activeDeliverable() {
  try { const p = fs.readFileSync(ACTIVE, 'utf8').trim(); return p && fs.existsSync(p) ? p : null; } catch { return null; }
}

// Ledger rows of the form | R01 | "quote" | entries | check | done|open |
function openLedgerRows(docPath) {
  const ids = [];
  let on = false;
  for (const ln of fs.readFileSync(docPath, 'utf8').split('\n')) {
    if (/^#{2,3} .*Requirement ledger/.test(ln)) { on = true; continue; }
    if (on && /^#{2,3} /.test(ln)) break;
    const m = on && ln.match(/^\|\s*(R\d+)\s*\|.*\|\s*(done|open)\s*\|\s*$/);
    if (m && m[2] === 'open') ids.push(m[1]);
  }
  return ids;
}

const inReports = (p) => /\/docs\/(reports|phase-plans)\//.test(p || '');

// Did an earlier Write or Edit in this session create or change this file?
function writtenThisSession(transcriptPath, file) {
  try {
    for (const l of fs.readFileSync(transcriptPath, 'utf8').split('\n')) {
      if (!l.includes(file)) continue;
      let e; try { e = JSON.parse(l); } catch { continue; }
      const c = e.message && Array.isArray(e.message.content) ? e.message.content : [];
      for (const b of c) if (b && b.type === 'tool_use' && ['Write', 'Edit'].includes(b.name) && b.input && b.input.file_path === file) return true;
    }
  } catch { /* no transcript */ }
  return false;
}

function note(event, text) {
  process.stdout.write(JSON.stringify({ hookSpecificOutput: { hookEventName: event, additionalContext: text } }));
}

module.exports = { ...base, authorizes, activeDeliverable, openLedgerRows, inReports, writtenThisSession, note };
