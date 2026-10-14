# Token and context tools: what each does, what is enforced, what is not

Researched 2026-09-27 from each tool's own help, `rtk gain`, the installed hook scripts in `~/.claude/hooks/`, the hook registrations in `~/.claude/settings.json`, and the session transcripts (my session `90c5b55d` plus 115 subagent transcripts). Every number below comes from one of those sources, named beside it.

## 1. The tools

| Tool | What it does (its own help text) | Measured saving | Available here |
|---|---|---|---|
| `rtk grep` / `rtk rg` | "Compact grep - strips whitespace, truncates, groups by file" | 30.6% / 29.1% average (`rtk gain --project`) | yes |
| `rtk read` | "Read file with intelligent filtering"; options `--level none\|minimal\|aggressive`, `--max-lines`, `--tail-lines`, `-n`. No line-range option. | 8.2% average (`rtk gain --project`); `--level minimal` on typecheck.py printed 597 of 623 lines | yes |
| `rtk log` | "Filter and deduplicate log output" | not in the top-10 gain table | yes |
| `rtk proxy <cmd>` | "Execute command without filtering but track usage" | none by design | yes |
| `rtk git`, `rtk find`, `rtk ls`, `ps` rewrite | compact output of those commands | `ps aux` 97.5%, `find` 7.7% | yes |
| graft | prebuilt code graph: `ask`, `grep`, `skeleton`, `callers`, `map`, `build` | 76–91% per call (its own "tokens saved" line on each call this session) | CLI yes; MCP tools yes in the main session; 0 MCP calls from any subagent |
| context-mode | `ctx_execute`, `ctx_execute_file`, `ctx_batch_execute`, `ctx_search`, `ctx_index`, `ctx_fetch_and_index`: run code over data in a sandbox, only printed results enter context | 58.9 KB of research output stayed out of context this session (indexed, queried) | main session yes; `ctx_execute_file` refuses paths outside the rush-cli checkout (the worktrees); 0 calls from any subagent |
| repowise | `distill` (run a command, compact reversible output, exit code kept), `expand`, `ask`, `context`, `why` | not measured by a stats command | CLI yes; its MCP server is disabled in rush-cli `settings.local.json` |
| codegraph | `explore`, `query`, `context` over a `.codegraph/` index | n/a | no: rush-cli has no `.codegraph/` index |
| headroom | proxy, memory, agent-savings CLI | n/a | CLI installed; its MCP compress tools are not loaded in this session |

## 2. What the installed hooks already enforce (read from the scripts)

- `rtk-enforce-bash.sh` (PreToolUse Bash): denies a raw command that rtk wraps (`sed`, `cat`, `grep`, `git`, `ls`, ...) as its own segment unless the segment starts with `rtk`.
- `rtk-enforce-native-tools.sh` (PreToolUse Read|Grep|Glob): Grep and Glob always denied; Read denied unless that exact file went through `rtk read` this session or a ctx_*/graft tool ran.
- `rtk-context-read-guard.sh` (PreToolUse Read): a native Read is allowed only for the exact path most recently cleared by `rtk read` or `ctx_execute_file`.
- `rtk hook claude` and `repowise-rewrite` (PreToolUse Bash): rewrite some commands automatically.
- `repowise-augment` (PostToolUse Read|Grep|Glob|Edit|Write): adds codebase context to those results.
- `rtk-adoption-stop.sh` (Stop): records adoption for `rtk gain`; prints and blocks nothing.
- These hooks run for subagents too: agent reports this session quote their denials (for example the T28-A continuation agent: the Read hook denied native reads of tui.py).

## 3. The gap: `rtk proxy` read passthrough

`rtk-enforce-bash.sh` allows any segment that starts with `rtk`, and `rtk proxy` runs the command raw. So `rtk proxy sed -n`, `rtk proxy cat`, `rtk proxy tail`, `rtk proxy grep` pass every gate and save nothing.

Measured since 2026-09-27 18:12Z (the last compaction), from the transcripts:

| | raw-read calls (`rtk proxy sed/cat/head/tail/grep/awk/wc`, `sed -n`) | `rtk read` | native Read | graft or repowise CLI | graft MCP | context-mode |
|---|---|---|---|---|---|---|
| Me (orchestrator) | 506 | 21 | 30 | 22 | 3 | 12 |
| All subagents | 988 + 496 `sed -n` | 299 | 114 | 92 | 0 | 0 |

What those raw reads targeted (same window): agents `sed -n` on source/config files 554, agents `grep` 338 and `head`/`tail` 230 on stdin or unclassified paths, me `grep`/`head`/`tail` 294 on stdin, logs/outputs 115 across both, markdown 74. Source-file and log reads have a direct saver (graft for code, `rtk log`/`rtk read --tail-lines`/ctx for logs); the pipe forms (`... | grep`, `| head`) are output trimming of other commands, which `repowise distill` or `ctx_batch_execute` replace.

Native Read in the same window: me 30 (28 with a `limit`, the largest 120 lines; 2 whole-file reads); all subagents 114 (70 with a `limit`, 44 whole-file reads). The existing read gates allow a whole-file native Read once `rtk read` has cleared that path, so they do not stop whole-file reads.

Subagents made 0 graft MCP and 0 context-mode calls even after the `orch-*` agent definitions listed those tools; whether definition edits apply mid-session is unconfirmed (all post-edit dispatches still show 0 such calls).

## 4. Enforcement design

1. **Rule, now (no tooling needed):** no `rtk proxy` for reading files or trimming output. Code questions go to graft; logs to `rtk log`, `rtk read --tail-lines`, or `ctx_execute`; command output to `repowise distill` or `ctx_batch_execute`. Native Read is never used to research or understand code. Its one use is the Edit tool's own precondition (the Edit tool refuses a file that was not Read: "File has not been read yet. Read it first before writing to it."), and then only with `offset`/`limit` covering exactly the lines being replaced. Written into `SKILL.md` and `dispatch-prompt.sh`'s tool rules.
2. **Monitor alert, now (`monitor.py`, non-blocking):** a TOOLSTACK alert per agent and for the orchestrator session when raw-read calls (the column set in §3) exceed 10 and outnumber graft + repowise + context-mode calls 3 to 1 in the last 30 tool calls. The replay numbers above would have fired for me and for every implementer this session.
3. **Proposed blocking hook (needs James's go):** `rtk-proxy-read-guard` on PreToolUse Bash. Trigger: a segment `rtk proxy` followed by `sed`, `cat`, `head`, `tail`, `grep`, `rg`, `awk` or `wc` whose argument is a file path (not stdin). Clear: rerun with the saver named in the message (`graft` for source files, `rtk read`/`rtk log` for other files). It does not match `rtk proxy` for `df`, `ps`, `git`, `lsof`, `sample`, or pipes reading stdin. It is a new hook file; no existing hook changes.
   Same hook, second trigger: a native Read with no `limit`, or a `limit` over 40 lines, on a file over 200 lines. Clear: use graft/`rtk read`/ctx to find the span, then Read only that span. Replay: would have fired on my 2 whole-file reads and 120-line read, and on 44 whole-file subagent reads.
4. **Subagent MCP tools:** confirm at the next session start whether `orch-*` agents can call `mcp__graft__*` and `ctx_*`; until then prompts name the CLI forms (`graft ask/grep/skeleton/callers`, `repowise distill`), which work in any subagent.
