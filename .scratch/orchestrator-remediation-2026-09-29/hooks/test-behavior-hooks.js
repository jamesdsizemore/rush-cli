// Fixture test for the J-series hooks (proposed, not registered). Run: node test-behavior-hooks.js
// Includes the counterexamples from the Codex review (finding 34): a prohibition must not unlock, a zero-open
// ledger must not block, and a disclaimer about something that is not a file must pass.
const fs = require('fs'), os = require('os'), path = require('path'), cp = require('child_process');
const here = __dirname;
const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'jhooktest-'));
process.on('exit', () => fs.rmSync(tmp, { recursive: true, force: true }));
const tpath = path.join(tmp, 'session.jsonl');
const user = (t) => JSON.stringify({ type: 'user', message: { role: 'user', content: t } });
const said = (t) => fs.writeFileSync(tpath, user(t) + '\n');
const activeFile = path.join(tmp, 'active-deliverable');
function run(hook, input) {
  const r = cp.spawnSync('node', [path.join(here, hook)], { input: JSON.stringify({ transcript_path: tpath, ...input }), encoding: 'utf8', env: { ...process.env, ACTIVE_DELIVERABLE: activeFile } });
  try { const j = JSON.parse(r.stdout); return j.decision || (j.hookSpecificOutput ? 'note:' + j.hookSpecificOutput.additionalContext : '?'); } catch { return 'ERR:' + (r.stderr || r.stdout).slice(0, 100); }
}
let fail = 0;
const expect = (name, got, want) => { const okk = typeof want === 'function' ? want(got) : got === want; if (!okk) { fail++; console.log(`FAIL ${name}: got ${got}`); } else console.log(`ok   ${name}`); };

// deliverable-edit-guard
const docs = path.join(tmp, 'docs', 'reports'); fs.mkdirSync(docs, { recursive: true });
const doc = path.join(docs, 'plan.md');
const lines = Array.from({ length: 20 }, (_, i) => `line ${i}`);
fs.writeFileSync(doc, lines.join('\n'));
const W = (content) => ({ tool_name: 'Write', tool_input: { file_path: doc, content } });
said('go on');
expect('rewrite: small change is approved', run('deliverable-edit-guard.js', W(lines.concat('new').join('\n'))), 'approve');
expect('rewrite: replacing the doc is blocked', run('deliverable-edit-guard.js', W('brand new text')), 'block');
said('DO NOT FUCKING REWRITE IT ASSHOLE - EDIT IT - JESUS FUCKING CHRIST');
expect('rewrite: the J8 message does not unlock', run('deliverable-edit-guard.js', W('brand new text')), 'block');
said('please rewrite it from scratch');
expect('rewrite: "rewrite it" unlocks', run('deliverable-edit-guard.js', W('brand new text')), 'approve');
said('go on');
expect('rewrite: a new file is approved', run('deliverable-edit-guard.js', { tool_name: 'Write', tool_input: { file_path: path.join(docs, 'new.md'), content: 'x' } }), 'approve');

// doc-shrink-guard
const E = (old, neu) => ({ tool_name: 'Edit', tool_input: { file_path: doc, old_string: old, new_string: neu } });
const big = lines.slice(0, 12).join('\n');
said('go on');
expect('shrink: removing 12 lines is blocked', run('doc-shrink-guard.js', E(big, 'x')), 'block');
expect('shrink: a small edit is approved', run('doc-shrink-guard.js', E('line 1', 'line one')), 'approve');
said('Do not remove anything');
expect('shrink: "Do not remove anything" does not unlock', run('doc-shrink-guard.js', E(big, 'x')), 'block');
said('remove the C6 section');
expect('shrink: "remove the C6 section" unlocks', run('doc-shrink-guard.js', E(big, 'x')), 'approve');
said('remove');
expect('shrink: a bare verb with no target does not unlock', run('doc-shrink-guard.js', E(big, 'x')), 'block');

// incomplete-handoff-stop
const led = (rows) => `# t\n\n## 0. The ask, verbatim\n\n> a\n\n### 0.1 Requirement ledger\n\n| ID | Quote | Entries | Check | Status |\n|---|---|---|---|---|\n${rows}\n\n## 1. x\n`;
const ledDoc = path.join(tmp, 'ledger.md');
fs.writeFileSync(activeFile, ledDoc);
said('go on');
fs.writeFileSync(ledDoc, led('| R01 | a | A1 | c | done |\n| R02 | b | A2 | c | open |'));
expect('handoff: an open row and no Blocked line is blocked', run('incomplete-handoff-stop.js', { last_assistant_message: 'Done with the first part.\nI have not finished R02.' }), 'block');
expect('handoff: a Blocked line in the last 6 lines passes', run('incomplete-handoff-stop.js', { last_assistant_message: 'Partial.\nBlocked: R02 needs the token' }), 'approve');
expect('handoff: stop_hook_active passes (no loop)', run('incomplete-handoff-stop.js', { stop_hook_active: true, last_assistant_message: 'x' }), 'approve');
fs.writeFileSync(ledDoc, led('| R01 | a | A1 | c | done |\n| R02 | b | A2 | c | done |'));
expect('handoff: remaining: 0 with no open row passes', run('incomplete-handoff-stop.js', { last_assistant_message: 'remaining: 0. I have not skipped anything; done.' }), 'approve');
fs.rmSync(activeFile);
expect('handoff: no active deliverable passes', run('incomplete-handoff-stop.js', { last_assistant_message: 'not yet' }), 'approve');

// unread-disclaimer-stop
const skillDir = path.join(os.homedir(), '.claude', 'skills', 'orchestrator');
const existing = fs.existsSync(skillDir) ? fs.readdirSync(path.join(skillDir, 'scripts')).find((f) => f.endsWith('.py') || f.endsWith('.sh')) : null;
said('go on');
expect('disclaimer: the installed skill has a script to name', existing, (g) => !!g);
expect('disclaimer: "have not opened <existing file>" is blocked', run('unread-disclaimer-stop.js', { cwd: tmp, last_assistant_message: `I have not opened ${existing} in full.` }), 'block');
expect('disclaimer: "have not opened unrelated Codex sessions" passes', run('unread-disclaimer-stop.js', { cwd: tmp, last_assistant_message: 'I have not opened unrelated Codex sessions.' }), 'approve');
expect('disclaimer: a file that does not exist passes', run('unread-disclaimer-stop.js', { cwd: tmp, last_assistant_message: 'I have not read nonexistent-zz.py.' }), 'approve');
said('skip');
expect('disclaimer: exactly `skip` unlocks', run('unread-disclaimer-stop.js', { cwd: tmp, last_assistant_message: `I have not opened ${existing}.` }), 'approve');

// script-bypass-guard
const scr = path.join(tmp, 'fixture.sh');
fs.writeFileSync(scr, '#!/bin/bash\ngit status\necho ok\n');
const entry = JSON.stringify({ type: 'assistant', message: { content: [{ type: 'tool_use', name: 'Write', input: { file_path: scr, content: 'x' } }] } });
fs.writeFileSync(tpath, entry + '\n' + user('go on') + '\n');
const B = (command) => ({ tool_name: 'Bash', cwd: tmp, tool_input: { command } });
expect('bypass: running a script Write created with a raw git line is blocked', run('script-bypass-guard.js', B(`bash ${scr}`)), 'block');
expect('bypass: cp into docs/ is blocked', run('script-bypass-guard.js', B('cp /tmp/x docs/reports/plan.md')), 'block');
fs.writeFileSync(path.join(tmp, 'old.sh'), 'git status\n');
expect('bypass: a script not written this session passes', run('script-bypass-guard.js', B(`bash ${path.join(tmp, 'old.sh')}`)), 'approve');
fs.writeFileSync(tpath, entry + '\n' + user('allow') + '\n');
expect('bypass: exactly `allow` unlocks', run('script-bypass-guard.js', B(`bash ${scr}`)), 'approve');

// memory-write-guard
const mem = path.join(tmp, '.claude', 'projects', 'p', 'memory', 'feedback_x.md');
fs.mkdirSync(path.dirname(mem), { recursive: true });
const M = (p) => ({ tool_name: 'Write', tool_input: { file_path: p, content: 'x' } });
said('go on');
expect('memory: a new memory file nobody asked for is blocked', run('memory-write-guard.js', M(mem)), 'block');
said("Don't remember this");
expect('memory: "Don\'t remember this" does not unlock', run('memory-write-guard.js', M(mem)), 'block');
said('please remember this for next time');
expect('memory: "remember this" unlocks', run('memory-write-guard.js', M(mem)), 'approve');
said('that is a process failure');
expect('memory: a named process failure unlocks', run('memory-write-guard.js', M(mem)), 'approve');
fs.writeFileSync(mem, 'x'); said('go on');
expect('memory: editing an existing memory file is not gated', run('memory-write-guard.js', M(mem)), 'approve');
expect('memory: a Write outside memory/ is not gated', run('memory-write-guard.js', M(path.join(tmp, 'a.md'))), 'approve');

// time-estimate-stop
said('how long');
expect('estimate: "about 2 hours left" with no tag is blocked', run('time-estimate-stop.js', { last_assistant_message: 'About 2 hours left at this rate.' }), 'block');
expect('estimate: "should take 40 minutes" is blocked', run('time-estimate-stop.js', { last_assistant_message: 'The gate should take 40 minutes.' }), 'block');
expect('estimate: the measured line with its tag passes', run('time-estimate-stop.js', { last_assistant_message: 'elapsed=61.3h merged=17/29 rate=3.6h per merged task [run-state.sh report 14:02:11: progress.log line 1, tasks.tsv]\nAbout 43 hours left at this rate.' }), 'approve');
expect('estimate: a past duration passes', run('time-estimate-stop.js', { last_assistant_message: 'The suite took 12 minutes on this Mac.' }), 'approve');
said('estimate');
expect('estimate: exactly `estimate` unlocks', run('time-estimate-stop.js', { last_assistant_message: 'About 2 hours left.' }), 'approve');

// notes
fs.writeFileSync(ledDoc, 'x'); fs.writeFileSync(activeFile, ledDoc);
const old = Date.now() / 1000 - 600; fs.utimesSync(ledDoc, old, old);
expect('age note: names the minutes since the last edit', run('deliverable-age-note.js', { prompt: 'x' }), (g) => /^note:.*last edited 10 minutes ago/.test(g));
expect('size note: 5,000 characters adds a note', run('output-size-note.js', { tool_response: 'x'.repeat(5000) }), (g) => g.startsWith('note:That output was'));
expect('size note: 100 characters adds nothing', run('output-size-note.js', { tool_response: 'x'.repeat(100) }), 'approve');
fs.writeFileSync(tpath, 'tool_result: rtk-enforce: raw ls\ntool_result: rtk-enforce: raw wc\n');
expect('denial card: the second denial adds the table', run('denial-card.js', { prompt: 'x' }), (g) => g.startsWith('note:rtk-enforce has denied 2'));
fs.writeFileSync(tpath, 'tool_result: rtk-enforce: raw ls\n');
expect('denial card: one denial adds nothing', run('denial-card.js', { prompt: 'x' }), 'approve');

// silence-note
const call = () => JSON.stringify({ type: 'assistant', message: { content: [{ type: 'tool_use', name: 'Bash', input: {} }] } });
const talk = JSON.stringify({ type: 'assistant', message: { content: [{ type: 'text', text: 'Working on the ledger.' }] } });
fs.writeFileSync(tpath, Array.from({ length: 7 }, call).join('\n') + '\n');
expect('silence: 7 calls add nothing', run('silence-note.js', {}), 'approve');
fs.writeFileSync(tpath, Array.from({ length: 8 }, call).join('\n') + '\n');
expect('silence: 8 calls in a row add the note', run('silence-note.js', {}), (g) => g.startsWith('note:8 tool calls in a row'));
fs.writeFileSync(tpath, Array.from({ length: 9 }, call).join('\n') + '\n');
expect('silence: 9 calls add nothing (checked at 8, 12, 16)', run('silence-note.js', {}), 'approve');
fs.writeFileSync(tpath, Array.from({ length: 10 }, call).join('\n') + '\n' + talk + '\n' + Array.from({ length: 3 }, call).join('\n') + '\n');
expect('silence: text resets the count', run('silence-note.js', {}), 'approve');

console.log(fail ? `test-behavior-hooks.js: ${fail} FAIL` : 'test-behavior-hooks.js: ALL PASS');
process.exit(fail ? 1 : 0);
