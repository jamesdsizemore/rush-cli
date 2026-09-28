# Phase 70 handoff: agent adoption and usability

Status on 2026-09-28: **not complete.** The code for T1–T29 is on the phase branch, but CI is red. Three plan items remain: the evidence re-run, the phase-end adversarial review and the final handoff. The owner paused the run after the last push, so nothing listed under "Next steps" has started.

## Where everything is

| Item | Value |
|---|---|
| Plan | `docs/phase-plans/phase-70-agent-adoption-and-usability-plan.md` |
| Branch | `phase/70-agent-adoption-and-usability` (base `codex/phases70-and-beyond-codex` at `dab48af`) |
| Only worktree | `/Users/jamesdsizemore/Developer/rush-cli-worktrees/phase-70` |
| Pushed head | `e7c29b1` (origin, draft PR #2 "DO NOT MERGE … (CI only)") |
| Local, not pushed | `30cd77c` retro docs; this handoff doc |
| Last local gate | `f2db51d` (same tree as `e7c29b1`): 6348 passed, 0 failed, 0 skipped; slow tests 1 passed; ruff, format, mypy `src/rush`, `sync_docs --check`, `git diff --check`, pip-audit all exit 0 |
| Orchestrator run | active: `phase-70/.orchestrator/run.json`, `~/.claude/orchestrator/active-run` points at the phase-70 worktree |
| Logs | `phase-70/.orchestrator/` (gate logs, progress log); every removed worktree's `.orchestrator/` is under `phase-70/.orchestrator/worktree-archive/` |

Merging into `main` is a separate step and needs the owner's approval.

## Red CI to fix first

Run 36465316792 on `e7c29b1`: https://github.com/jamesdsizemore/rush-cli/actions/runs/36465316792. The failed-job log is saved at `phase-70/.orchestrator/ci-36465316792-failed.log`.

Five jobs pass: Executed workload contracts, Representative Python engine smoke, Static tool acceptance, and Isolated artifact probes on Ubuntu and on Windows.

Quality and tests (Linux): 3 failed, 6334 passed, 2 warnings. All three pass on macOS.

1. `tests/test_phase70_t27.py::test_t27_catalog_semantics_and_human_output[offline-review]`: status `skipped`, expected `ok`. Commit `dd5fa78` made five CI-only Linux failures hermetic by adding placeholder engines on PATH. On the runner this case still resolves an engine it does not have.
2. `tests/test_phase70_t28c_review2.py::test_outcome_detail_shows_recorded_targets`: the outcome detail shows `target: /tmp/pytest-of-runner/... (project root; no targets recorded)` instead of the recorded targets. The recorded-target lookup does not match the result's metadata on the Linux tmp path.
3. `tests/test_phase70_tui_usability_ef.py::test_t28e_tokens_git_artifacts`: "a truncated diff must say more remains".
4. Warnings (zero allowed): one is `multiprocessing/popen_fork.py:66 DeprecationWarning: This process ... is multi-threaded, use of fork() may lead to deadlocks`. The second has not been identified yet; read it from the log's "warnings summary".

Windows runtime and installed contracts: fails at the step "Verify Windows dashboard data-directory ACL contract". The chain is:
- `tests/test_dashboard_http_contract.py:27` imports `tests/_process_children.py`;
- `tests/_process_children.py:16` has a module-level `import pty`;
- `pty` imports `tty`, which imports `termios`, and `termios` does not exist on Windows (`ModuleNotFoundError`).

The job stops there, so the later Windows steps never ran. Those steps include the first real-host run of the Windows guard change `c276013` (Toolhelp snapshot and Restart Manager in `tests/conftest.py`) and of the frozen Windows gate (`rush.entry.main` with `__rush_windows_gate__`).

## Remaining plan work (in order)

1. **Fix the red CI above.** Run the full gate locally, including `-m slow`. Then push and watch CI until every job passes with zero warnings and zero skips. Also push `30cd77c` and this handoff.
2. **Re-run T29 evidence on the final commit** (plan T29, lines 438–443; gates G5–G8, lines 445–466). The first-pass report on `449cd62` is `docs/reports/phase-70-implementation-evidence.md`. The re-run must:
   - Rebuild the frozen binary with the release.yml PyInstaller command. PyInstaller is already installed in `phase-70/.venv`. Record the runtime identity: version, sha256 and commit.
   - Run G6 for Claude Code and Codex CLI in the owner's real configs. The plan's owner decision after the §7 gate table authorizes it.
     - Both `~/.claude.json` (user `mcpServers.rush`) and `~/.codex/config.toml` (`[mcp_servers.rush]`) already contain a user-owned `rush` entry pointing at `~/Library/Application Support/Rush/bin/rush`. Rush has no ownership record for it.
     - Procedure: copy both files aside and record their sha256, show the preview, `rush agent connect`, run the model tool calls (granted, denied, faulty edit, timeout), `rush agent disconnect`, restore both files byte-for-byte, and show the before and after sha256 match.
     - Codex blocks tool calls under approval policy `never`, so pass a per-invocation approval policy that lets the calls reach Rush.
   - Finish the TUI walkthrough with a registered project: setup, scan, agent, rescan; memory write, archive and delete; artifact detail; slow-work progress. Also re-check idle Ctrl-C with the fix `e0e363a`.
   - Run the install route (`scripts/install.sh --setup`) against an isolated prefix and HOME, so the owner's installed rush is left alone.
   - Fill the "CI runs" section with each run's URL and conclusion.
   - Update the report's coverage receipt (historical, `immutable_body_sha256` from `scripts/sync_docs.py`).
3. **Phase-end adversarial review**: orch-adversarial-reviewer, Codex and agy in parallel. Scope the prompt to architecture fit, breakage risk and sequencing, not citation counts. Fix every real finding through the task loop.
4. **Final handoff report** replacing this document, then `run-state.sh stop`.

## What landed this session (on the branch)

- T28 review fixes:
  - T28-C: rescan, Scans filters and per-tool evidence, Map evidence and provenance.
  - T28-E: safe export and Git backend, tokens, evidence index, and no I/O on render.
  - T28-F: paste and Windows VT input, `+`/`-` detail in every section, loop pacing and motion, Ctrl-C and detach, starts off the key path, and cancel while a start is in progress.
  - T28-D round 2.
- Test isolation:
  - The owned-process data root is bound at owner start (`658adbf`).
  - The TUI owner lock is taken under the TUI's data root (`8864802`).
  - The real-HOME guard closes two holes and lists processes natively on Windows (`c276013`).
- Dashboard supervised operations are joined at shutdown (`d4c8387`).
- aislop runs its npm package directly (`85eedb2`, `a75dbfd`).
- The frozen binary resolves the project's Python instead of running itself (`71d24f6`, `e53ea86`). `rush.entry` is the standalone entry point. Five import cycles are broken, and every module imports first in a fresh interpreter (`tests/test_import_order.py`).
- Ctrl-C at idle exits even when the PTY is not the controlling terminal (`e0e363a`).
- Six Linux CI-only test failures made hermetic (`dd5fa78`).
- T29 cross-interface parity tests (`6a2a167`), T29 docs (`ad2ca1a`) and the first-pass evidence report (`c2c8e68`).
- Retro docs: `docs/reports/i-fucked-up-and-james-is-fucking-pissed.md` and `docs/reports/token-tool-enforcement-research.md` (`30cd77c`, local).

## Open items outside the task list

- `mypy .` (whole repo, not the gate's `mypy src/rush`) reported about 1290 errors in 159 files under `tests/` and `scripts/`, per the agents' runs. This is untracked.
- Plan §8.1 names a root `rush.toml` that was never in the repo.
- The merge commits for `fixf` and `e2` lack the session line.
- The export default destination is `<root>/.rush/exports`.
- CLAUDE.md consolidation waits for the owner's go.

## Real HOME and data root

- `~/Library/Application Support/Rush/owners` was emptied on 2026-09-28. The 252 files deleted there came from test runs on 2026-09-27 before the lock-leak fix, and none were held open. Every gate run since then left it unchanged.
- The first evidence pass wrote no host config. Before and after digests matched for:
  - the `rush` entries in `~/.claude.json` and `~/.codex/config.toml`;
  - all of `~/.codex/config.toml`, `~/.claude/settings.json` and `~/.codex/hooks.json`.

  The whole `~/.claude.json` digest changed, because Claude Code rewrites that file during any session.

## Tooling changed this session (orchestrator skill and hooks)

- `~/.claude/skills/orchestrator/scripts/dispatch-prompt.sh` pastes every cited `path:line` span into the prompt. It refuses a map that tells the agent to go read files ("in full", "read the checkpoint/plan/spec").
- `~/.claude/hooks/orchestrator-model-guard.js`:
  - rule 7: an `orch-*` agent runs only with a prompt file generated by `dispatch-prompt.sh`, checked by its sha256 marker;
  - it finds the run through `~/.claude/orchestrator/active-run`;
  - it switches off with `run-state.sh stop` or the single word `unguard`.
- `run-state.sh start` and `stop` write and remove the active-run marker.
- Backups of the three files before these changes are in the session scratchpad (`dispatch-prompt.sh.bak`, `orchestrator-model-guard.js.bak`, `run-state.sh.bak`).

## Rules for the next session

- Every dispatch goes through `dispatch-prompt.sh`, and each map carries the code spans, failure text and decisions. Agents given full packets finished in 12 to 60 tool calls. Agents told to go read burned 150–260k tokens, one of them without making a single edit.
- One worktree per task under `rush-cli-worktrees/`. Remove each worktree as soon as it is merged, after archiving its `.orchestrator/` folder.
- Before every push: the full gate plus `-m slow`, never a failing state. After every push: every CI job, including annotations and warnings.
- Keep 8 GiB or more free on disk. Tests never touch the real HOME or data root; the guard enforces this.
