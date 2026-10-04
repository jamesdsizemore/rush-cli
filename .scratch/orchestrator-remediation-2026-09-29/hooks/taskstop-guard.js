// PreToolUse, matcher TaskStop. During an active run: a finished agent may be stopped (close-out); an agent
// with hang proof may be stopped; everything else is blocked, including a task id that is not an agent
// (a shell task such as a running test suite). Unlock: the user's whole message is `stop`.
const { fs, path, activeRun, lastHumanText, unlocked, agentFinished, readInput, approve, block } = require('./orch-hook-lib.js');
readInput((input) => {
  const root = activeRun(input);
  if (!root) return approve();
  if (unlocked(lastHumanText(input.transcript_path || ''), 'stop')) return approve();
  const id = String((input.tool_input && input.tool_input.task_id) || '');
  if (fs.existsSync(path.join(root, '.orchestrator', `hang-${id}.txt`))) return approve();
  const agentFile = path.join((input.transcript_path || '').replace(/\.jsonl$/, ''), 'subagents', `agent-${id}.jsonl`);
  let st; try { st = fs.statSync(agentFile); } catch {
    return block(`Task ${id} is not an agent, so it is a shell task such as a running test suite. A running suite is never stopped during a run. Unlock: the user sends exactly \`stop\`.`);
  }
  if (agentFinished(agentFile)) return approve();
  const quiet = Math.round((Date.now() - st.mtimeMs) / 1000);
  block(`Agent ${id} is still working (last record ${quiet}s ago). Stop it only with hang proof in .orchestrator/hang-${id}.txt: a transcript quiet 8+ minutes and a process sample. Unlock: the user sends exactly \`stop\`.`);
});
