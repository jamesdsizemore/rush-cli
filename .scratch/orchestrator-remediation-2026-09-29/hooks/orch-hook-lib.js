// Shared by ask-guard.js, prose-question-stop.js, resume-guard.js, taskstop-guard.js and the J-series hooks.
const fs = require('fs');
const os = require('os');
const path = require('path');

const MARKER = process.env.ORCH_ACTIVE_RUN || path.join(os.homedir(), '.claude', 'orchestrator', 'active-session.json');

// active-session.json is JSON {"root": "<worktree>", "session_id": "<orchestrator session>"}, written by
// run-state.sh start from $CLAUDE_CODE_SESSION_ID. It is a separate file from active-run, which stays the
// plain root path that orchestrator-model-guard.js reads. A hook enforces only in that session, and only
// while root's run.json exists.
function activeRun(input) {
  try {
    const m = JSON.parse(fs.readFileSync(MARKER, 'utf8'));
    if (!m.root || !m.session_id) return null;
    if (input && input.session_id !== m.session_id) return null;
    if (!fs.existsSync(path.join(m.root, '.orchestrator', 'run.json'))) return null;
    return m.root;
  } catch { return null; }
}

// One classifier for "what the human last said": hook feedback, hook errors, interrupts and system
// notices are not human messages.
const NOT_HUMAN = /^\s*(<|Stop hook feedback|Stop hook blocking error|PreToolUse:|PostToolUse:|UserPromptSubmit|Another Claude session|\[Request interrupted|Caveat:)/;
function lastHumanText(transcriptPath) {
  try {
    const lines = fs.readFileSync(transcriptPath, 'utf8').split('\n').filter(Boolean);
    for (let i = lines.length - 1; i >= 0; i--) {
      let e; try { e = JSON.parse(lines[i]); } catch { continue; }
      if (e.type !== 'user' || !e.message || e.isMeta) continue;
      const c = e.message.content;
      const t = typeof c === 'string' ? c : Array.isArray(c) ? c.filter((b) => b && b.type === 'text').map((b) => b.text).join('\n') : '';
      if (t.trim() && !NOT_HUMAN.test(t)) return t.trim();
    }
  } catch { /* fall through */ }
  return '';
}

// An unlock is the human's whole message being the unlock word: nothing to negate, nothing to misread.
function unlocked(text, word) {
  return new RegExp('^\\s*' + word + '\\s*[.!]?\\s*$', 'i').test(text || '');
}

// The one definition of a finished agent, the same as monitor.py finished(): last line is a SubagentStop
// record, or the last assistant message is an end_turn.
function agentFinished(agentFile) {
  try {
    const lines = fs.readFileSync(agentFile, 'utf8').trimEnd().split('\n');
    if (lines.length && lines[lines.length - 1].includes('SubagentStop')) return true;
    for (let i = lines.length - 1; i >= 0; i--) {
      let e; try { e = JSON.parse(lines[i]); } catch { continue; }
      if (e.type === 'assistant') return !!(e.message && e.message.stop_reason === 'end_turn');
      if (e.type === 'user') return false;
    }
  } catch { /* fall through */ }
  return false;
}

function readInput(cb) {
  let d = ''; process.stdin.on('data', (c) => { d += c; });
  process.stdin.on('end', () => { let i = {}; try { i = JSON.parse(d); } catch { /* empty */ } cb(i); });
}
const approve = () => process.stdout.write('{"decision":"approve"}');
const block = (reason) => process.stdout.write(JSON.stringify({ decision: 'block', reason }));

module.exports = { fs, os, path, activeRun, lastHumanText, unlocked, agentFinished, readInput, approve, block };
