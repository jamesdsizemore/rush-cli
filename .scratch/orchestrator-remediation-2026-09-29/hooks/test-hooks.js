// Fixture test for the D4 hooks. Run: node test-hooks.js  (temp HOME-free: ORCH_ACTIVE_RUN points at a temp marker)
const fs = require('fs'), os = require('os'), path = require('path'), cp = require('child_process');
const here = __dirname;
const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'hooktest-'));
const root = path.join(tmp, 'run'); fs.mkdirSync(path.join(root, '.orchestrator'), { recursive: true });
fs.writeFileSync(path.join(root, '.orchestrator', 'run.json'), '{}');
const SID = 'sess-orch', marker = path.join(tmp, 'active-run');
fs.writeFileSync(marker, JSON.stringify({ root, session_id: SID }));
const tdir = path.join(tmp, 'session'); fs.mkdirSync(path.join(tdir, 'subagents'), { recursive: true });
const tpath = tdir + '.jsonl';
const user = (t) => JSON.stringify({ type: 'user', message: { role: 'user', content: t } });
const asst = (b, stop) => JSON.stringify({ type: 'assistant', message: { role: 'assistant', stop_reason: stop || null, content: b } });
const write = (lines) => fs.writeFileSync(tpath, lines.join('\n') + '\n');
function run(hook, input) {
  const r = cp.spawnSync('node', [path.join(here, hook)], { input: JSON.stringify(input), encoding: 'utf8', env: { ...process.env, ORCH_ACTIVE_RUN: marker } });
  try { return JSON.parse(r.stdout).decision; } catch { return 'ERR:' + (r.stderr || r.stdout).slice(0, 80); }
}
let fail = 0;
const expect = (name, got, want) => { if (got !== want) { fail++; console.log(`FAIL ${name}: got ${got}, want ${want}`); } else console.log(`ok   ${name}`); };
const ask = (extra) => ({ session_id: SID, transcript_path: tpath, tool_input: { questions: [{ question: 'Should the aislop fix keep all findings?', options: [{ label: 'All' }] }] }, ...extra });

write([user('go on')]);
expect('ask-guard blocks any question in the run session', run('ask-guard.js', ask()), 'block');
expect('ask-guard: a question that starts "decision-search: zzznomatch" is still blocked', run('ask-guard.js', { ...ask(), tool_input: { questions: [{ question: 'decision-search: zzznomatch\nShould we?' }] } }), 'block');
write([user('ask')]);
expect('ask-guard: the unlock word `ask` approves', run('ask-guard.js', ask()), 'approve');
write([user('ask'), user('Stop hook feedback:\nPROCESS FAILURE in the response just sent')]);
expect('ask-guard: hook feedback after `ask` does not hide the unlock', run('ask-guard.js', ask()), 'approve');
write([user('ask'), user('PreToolUse:Bash hook error: rtk-enforce: raw ls')]);
expect('ask-guard: a hook error after `ask` does not hide the unlock', run('ask-guard.js', ask()), 'approve');
write([user('please ask me later, do not ask now')]);
expect('ask-guard: a sentence containing "ask" is not the unlock', run('ask-guard.js', ask()), 'block');
write([user('go on')]);
expect('ask-guard: another session is not enforced', run('ask-guard.js', ask({ session_id: 'someone-else' })), 'approve');
fs.rmSync(path.join(root, '.orchestrator', 'run.json'));
expect('ask-guard: a stale marker (no run.json) is not enforced', run('ask-guard.js', ask()), 'approve');
fs.writeFileSync(path.join(root, '.orchestrator', 'run.json'), '{}');
expect('prose-question-stop blocks a closing question', run('prose-question-stop.js', { session_id: SID, transcript_path: tpath, last_assistant_message: 'Done.\nShould I merge T9 now?' }), 'block');
expect('prose-question-stop approves a statement', run('prose-question-stop.js', { session_id: SID, transcript_path: tpath, last_assistant_message: 'T9 merged.' }), 'approve');

fs.writeFileSync(path.join(root, '.orchestrator', 'agents.active'), 'impl1 100 impl\nrev1 80 reviewer\n');
const send = (to, message) => JSON.stringify({ type: 'assistant', message: { content: [{ type: 'tool_use', name: 'SendMessage', input: { to, message } }] } });
write([user('go on'), send('impl1', 'first'), send('rev1', 'first')]);
const sm = (to, message) => ({ session_id: SID, transcript_path: tpath, tool_input: { to, message } });
expect('resume-guard blocks a second message to an implementer', run('resume-guard.js', sm('impl1', 'again')), 'block');
expect('resume-guard allows a second message to a reviewer', run('resume-guard.js', sm('rev1', 'again')), 'approve');
expect('resume-guard allows a SCOPE: correction to an implementer', run('resume-guard.js', sm('impl1', 'SCOPE: also cover T14')), 'approve');
write([user('go on'), send('rev1', 'first')]);
expect('resume-guard allows the first message to an implementer', run('resume-guard.js', sm('impl1', 'first')), 'approve');

const rec = (o) => JSON.stringify(o);
const aid = (id) => path.join(tdir, 'subagents', `agent-${id}.jsonl`);
fs.writeFileSync(aid('fin1'), [asst([{ type: 'text', text: 'done' }], 'end_turn'), rec({ type: 'system', hookEvent: 'SubagentStop' })].join('\n') + '\n');
fs.writeFileSync(aid('fin2'), asst([{ type: 'text', text: 'done' }], 'end_turn') + '\n');
fs.writeFileSync(aid('work1'), asst([{ type: 'tool_use', id: 't1', name: 'Bash', input: {} }]) + '\n');
write([user('go on')]);
const ts = (id) => ({ session_id: SID, transcript_path: tpath, tool_input: { task_id: id } });
expect('taskstop-guard approves a finished agent (SubagentStop as last line)', run('taskstop-guard.js', ts('fin1')), 'approve');
expect('taskstop-guard approves a finished agent (end_turn as last assistant record)', run('taskstop-guard.js', ts('fin2')), 'approve');
expect('taskstop-guard blocks a working agent', run('taskstop-guard.js', ts('work1')), 'block');
expect('taskstop-guard blocks a shell task id (a running suite)', run('taskstop-guard.js', ts('bshell01')), 'block');
fs.writeFileSync(path.join(root, '.orchestrator', 'hang-work1.txt'), 'proof');
expect('taskstop-guard approves a working agent with hang proof', run('taskstop-guard.js', ts('work1')), 'approve');
write([user('stop')]);
expect('taskstop-guard: the unlock word `stop` approves', run('taskstop-guard.js', ts('bshell01')), 'approve');
write([user('Do not stop the tests')]);
expect('taskstop-guard: "Do not stop the tests" is not the unlock', run('taskstop-guard.js', ts('bshell01')), 'block');

fs.rmSync(tmp, { recursive: true, force: true });
console.log(fail ? `${fail} FAILED` : 'ALL PASS');
process.exit(fail ? 1 : 0);
