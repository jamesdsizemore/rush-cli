# Phase 70 implementation evidence (T29)

Recorded 2026-09-27 on macOS 26 (Darwin 25.6.0, arm64). Every row below is an observation made in this run against the frozen release binary described under Runtime identity; nothing is restated from the plan or inferred from test fixtures. Temporary project and HOME paths are redacted to `<tmp>`.

## Runtime identity

- Subject: branch `phase/70-t29evidence` at commit `449cd62` (phase branch plus T28 fixes plus T29 tests).
- Build route: the release workflow's own path (`.github/workflows/release.yml` "Compile standalone binary"): `pyinstaller --onefile --name rush --paths src --collect-data license_expression --collect-data rush.integrations rush_entry.py`, PyInstaller 6.22.3, CPython 3.12.12, exit 0.
- Executable under test: frozen `rush`, `rush --version` = `0.3.0`, sha256 `11cc193a6cf607ed82c80b9088c1293e1639ba4448920d3f1810c8e1fff42027`. Called "frozen 11cc193a" below. It was built in a session scratch directory and deleted after this run.
- Source origin check: the PyInstaller analysis TOC lists 453 modules from this worktree's `src/rush`; the 10 `agent_assets` data files were collected from the shared venv's editable install, and `diff -r` of the two `agent_assets` trees reported them byte-identical.
- G5 artifact probe: packaged as `rush-darwin-arm64.tar.gz` (sha256 `773db66840d928f74db373359331d788a934bb5cef7936f6dd63de68a00813f0`, rush plus VERSION, as the release job does), then `python scripts/probe_installed_artifacts.py --dist-dir <dist> --checkout-root <worktree> --json`, exit 0: `artifact_type native, status passed, origin_verified true, import_clean true, mcp_initialized true`.
- Not the subject: the real-HOME installed `~/Library/Application Support/Rush/bin/rush` (also reports `0.3.0`). It is a different, older build and was not used for any row.
- Every journey ran from an arbitrary cwd (a TemporaryDirectory project, or its parent) with `HOME` set to a TemporaryDirectory, both deleted after the run, except the host probes in the host acceptance section.

## Journey matrix

| Req | Starting state | Outcome | Route | Visible result | Failure/recovery | Owner | Runtime identity |
|---|---|---|---|---|---|---|---|
| R01 | Fresh HOME; project `proj ü space` with Python sources; no agent registered | An agent discovers a small core tool set with usable schemas | `rush mcp serve --profile core` over stdio: `initialize`, `tools/list`; Claude Code `claude -p` with that server | serverInfo `rush` 1.28.1; exactly 7 tools: rush_status, rush_check, rush_lint, rush_review, rush_security, rush_test, rush_memory; `rush_status` requires nothing, the other six require `path`; Claude Code reported the server `connected` and the model called `rush_lint` and `rush_check` | `rush agent list` on the fresh HOME lists claude-code and codex as `not_detected` (exit 0) instead of implying a connection | T1-T5 | frozen 11cc193a |
| R02 | Same MCP session | Invalid input is rejected with a typed error and no effect | `tools/call rush_memory {path, operation: ask}` without subject/query/session_allowlist | status `error`, code `E_INPUT`, message `invalid request: subject: Field required; query: Field required; session_allowlist: Field required` | Project file list after the session is unchanged (pyproject.toml, src/bad.py, tests/test_ok.py, uv.lock); no `.rush` directory created | T3, T6, T7 | frozen 11cc193a |
| R03 | Project with `src/bad.py` (two unused imports) | Relative targets resolve once, from the caller's cwd | `rush lint src/bad.py` from the project; `rush lint "proj ü space/src/bad.py" --json` from its parent; MCP `rush_lint {path: "src/bad.py"}` with server cwd = project | All three report F401 at `<tmp>/proj ü space/src/bad.py` lines 1 and 2; no `src/src` path; CLI exit 1 (fail) | Scope block shows `files: matched 1, consumed 1`, `coverage: complete` | T8-T10 | frozen 11cc193a |
| R04 | Fresh HOME, engines on PATH (ruff, mypy); pyproject plus uv.lock pinning requests 2.19.0 | Engine readiness and diagnostics are truthful | `rush doctor . --json`; `rush security . --json`; `rush check . --allow-build --allow-cache-write` | doctor exit 0: `6/6 required engine(s) installed, 1 finding(s)`, finding `bandit: no Rush-managed package; install manually if needed.`; security status `skipped` with reasons `osv-scanner: no offline vulnerability database available` and `requires permissions: network, download, cache_write, build` | DEFECT observed: in the frozen binary the check's test step reports `error, pytest exit 2` for a passing test; the same `rush test . --allow-build --json` from source reports `ok, 1 passed`. Cause: `src/rush/engines/pytest.py:62` builds `[sys.executable, "-m", "pytest", ...]`, and in a PyInstaller binary `sys.executable` is the rush binary itself (the result's executable path is the frozen rush). Open, not fixed by this report | T11-T15 | frozen 11cc193a |
| R05 | Same project, no grants, then build and cache_write grants | Every check step has an outcome; denial is visible | `rush check . --json`; `rush check . --allow-build --allow-cache-write` | Six steps listed `6/6 steps`: format ok, lint fail (2), typecheck fail (mypy+pyrefly, 1), dead warn (vulture, 2), slop skipped `requires permission: --allow-download (aislop's npm package is not in the local npm cache) (permission_denied)`, test error (the R04 defect); overall exit 1 without grants, 2 with grants | Denied step named with its missing grant; no project files written by either run | T16, T17 | frozen 11cc193a |
| R06 | Fresh project with no memory store | Memory is visible without creating state | `rush memory` | `memory: 0 useful record(s) in <tmp>/proj ü space (showing none)` and `no memory store at <tmp>/proj ü space/.rush/memory.db`, exit 0 | No `.rush/memory.db` created by the read | T18-T22 | frozen 11cc193a |
| R07 | Unregistered project, fresh HOME | Bare `rush` tells the user where they stand | `rush` (no arguments); `rush status . --json`; `rush --help`; `rush help quality` | `rush status: warn -- unregistered project ...; no analysis has run; project is not registered.` with Project, Config (`rush.toml: missing`), Engines (ruff, mypy, pytest, pip-audit, aislop, tach installed; bandit unsupported), Activity idle, Latest attempt none, Agents; exit 1. `--help` shows 11 everyday commands plus 7 categories with counts | Same status fields over JSON and MCP `rush_status` (R12) | T23-T25 | frozen 11cc193a |
| R08 | Commit 449cd62 | Installed artifact carries native assets and runs outside the checkout | Release PyInstaller build plus `scripts/probe_installed_artifacts.py --json` | native probe `passed`, `origin_verified true`, `mcp_initialized true`, exit 0 | The R04 frozen-binary pytest defect is a source-versus-installed difference that only the installed artifact exposes | All | frozen 11cc193a |
| R09 | Fresh HOME, project `new proj ü` with no rush.toml, no Claude Code config in that HOME | One installed command reaches a configured project and host | `rush setup "<tmp>/new proj ü" --agent claude` in a real PTY, answering y to each native prompt | 6 native prompts (resolution network grant, apply, register with Claude Code, instruction block, host probe, representative check); `Setup ok`, `engines applied: aislop, mypy, pip-audit, pytest, ruff, tach`, `host claude: configured (registration applied)`, `guidance: applied`, `probe: failed`, `check: ran`; `rush status` afterwards: `registered`, `configured: yes`, `rush.toml: valid`, ruff 0.16.9, mypy 2.3.1, pytest 9.1.1, pip-audit 2.10.1, aislop 0.16.1, tach 0.35.1 | Host probe failed because the temporary HOME has no Claude login; setup printed `next (login): claude /login` and `resume: rush setup '<tmp>/new proj ü' --agent claude`. The capability_verified state was not reached on this route | T2, T3, T15, T24, T26 | frozen 11cc193a |
| R10 | Fresh HOME | Every route prints real data or a stated empty or denied state | `rush project list`; `rush agent list`; `rush setup . --apply --yes`; `rush install --agent claude --agents none`; `rush setup . --save-plan <tmp>/plan.json --allow-artifact-write --json` | `0 records: no projects are registered; register one with rush project add PATH --allow-cache-write --allow-artifact-write`; agent list prints 6 records; apply without plan exits 2 with `non-interactive apply needs --apply --yes --plan-file PATH --plan-id ID plus the --allow-* grants the saved review lists`; conflicting install exits 2 before effects with `--agent conflicts with --agents none` | save-plan without network exits 1, `reason resolution_required`, with the exact `resume_command` adding `--allow-network`; no plan file written | T9, T16, T23, T25, T27 | frozen 11cc193a |
| R11 | Two unregistered git projects (`proj ü one`, `proj two`), fresh HOME | Every TUI section and action is reachable in a real terminal | `rush ui p1 p2` in a macOS PTY at 80x24, 120x40 and 60x20; keys 1-8, ?, Esc, C, s, y, c, r, M, m, G, d, i, a, F2, j, Enter, bracketed paste, resize, q | All 8 section labels rendered at 80x24 and 120x40; 60x20 shows the compact single-section layout; `q` exits 0 at every size; no traceback; C shows `analysis started`; c shows `no running work to cancel`; r shows `no completed run to rescan yet`; M shows the memory table with `no memory recorded for this project yet`; F2 opens the project chooser; pasted `ü漢字 paste` appears in the filter | Scan on an unregistered project stays at the setup stage (`p stage to retry`); Ctrl-C at idle did not exit within 11 s (harness sent SIGTERM, exit -15); details in the terminal walkthrough section | T17, T20, T23, T24, T26, T28-A to F | frozen 11cc193a |
| R12 | Same unregistered project | CLI, MCP and TUI agree on identity and state | `rush status . --json`, MCP `rush_status {path}`, TUI Overview | All three report `warn`, `unregistered project <tmp>/proj ü space; no analysis has run; project is not registered.`; MCP `rush_check` without grants and CLI `rush check .` both report status fail with the same F401 findings and the same engine list `ruff+mypy+pyrefly+vulture+aislop+pytest` | Dashboard acceptance is owned by Phase 71 (next sections) | T29, all tasks | frozen 11cc193a |

## T26 route counts

Route: already-installed setup, `rush setup "<tmp>/new proj ü" --agent claude`, frozen 11cc193a, macOS PTY, fresh HOME.

- Manual edits: 0.
- Hidden prerequisite commands: 0 (no init, project add, doctor or agent connect was run before setup).
- User shell commands: 1.
- Native prompts: 6 (listed in R09), each answered y.
- Login: 1 pending, not completed (`next (login): claude /login`); the temporary HOME has no Claude account.
- Reload: 0 requested by setup.
- Measured duration: 37.5 s wall clock from exec to exit 0, including engine resolution and installation into the temporary HOME. This is a measurement, not a speed claim.
- Readiness reached: project registered and configured, engines installed, host configured; `capability_verified` not reached because the host probe failed without a login.

Fresh guided bootstrap route (`scripts/install.sh --setup --agent HOST --project PATH`): not run. It downloads and installs a published release into the real HOME, which would replace the owner's installed `rush`, and no published build of 449cd62 exists to download.

## Phase 71 consumes

Phase 71 builds on these Phase 70 shared contracts, and its dashboard gate must satisfy them:

- Dashboard provision frozen identity (T24). The reviewed setup path freezes engine identities (version, URL, digest) into the reviewed plan and applies exactly those, labelled `identity_source="frozen_review"` (`src/rush/setup/provision.py:1186` default, `apply_provision_plan` at `src/rush/setup/provision.py:1518-1525`). The dashboard `provision_apply` action (`src/rush/dashboard/server.py:978-1050`) still calls `run_setup_wizard(root, install=True, permissions=...)`, which resolves identities under the caller's network grant and applies them in the same invocation through `resolve_and_apply_provision_plan` (`src/rush/setup/provision.py:1606-1633`, labelled `identity_source="resolved_at_apply"`; `src/rush/tools/setup_wizard.py:279-298` and `:330-346`). Its `plan_id` comparison runs before resolution, so the approved plan does not bind a concrete package version or digest. Phase 71 must move the dashboard provision flow to review, then resolve, then apply frozen identities: show the resolution-only request, freeze identities into the reviewed plan, and apply only those.
- The core MCP profile of seven tools and its schemas (R01, R02), the shared StatusTool fields (R07, R12), the six-step check outcome contract (R05), the setup review envelope and readiness states installed, configured, restart_required, authenticated, connected and capability_verified (R09), and the TUI section and state vocabulary (Overview, Map, Scans/Findings, Memory, Tokens, Git, Artifacts, Setup/Agents; loading, populated, empty, unavailable, denied, failed, stale, disconnected).

## Real-home files touched

- `~/.claude.json`, `~/.codex/config.toml`, `~/.claude/settings.json`, `~/.codex/hooks.json`, `~/.claude/plugins/*.json`: read only (digests in the host acceptance section). No write by this run.
- `~/Library/Application Support/Rush`: read by the digest script; the two `rush setup --agent claude|codex --json` previews ran with the real HOME and are preview-only. Before and after digests of `projects.json`, `session_projects.json` and `cursor.key` are equal; `agents/` stayed empty.
- The shared venv `/Users/jamesdsizemore/Developer/rush-cli-worktrees/phase-70/.venv` gained `pyinstaller 6.22.3`, `pyinstaller-hooks-contrib 2026.7` and `setuptools 84.0.0` (`uv pip install pyinstaller`, for the release build).

## G6 native host acceptance

Host versions: Claude Code `2.1.283 (Claude Code)` at `/Users/jamesdsizemore/.local/bin/claude`; Codex CLI `codex-cli 0.155.1` at `/Users/jamesdsizemore/.local/bin/codex`.

Digests (sha256, first 16 hex), before and after, all equal except the volatile whole `~/.claude.json`, which Claude Code itself rewrites during any session (`c61098d9ff76366c` then `d8a1ea8711dd8a0e`): user `mcpServers.rush` entry `c995a5a1649cb0d8`, no project-scoped rush entries; `~/.codex/config.toml` `mcp_servers.rush` entry `20447601ac87608b`, whole file `8ddbd4e9ca6ca030`; `~/.claude/settings.json` `ab49119e1ce6bcd6`; `~/.codex/hooks.json` `e97605b597198cd0`; `~/.claude/plugins/installed_plugins.json` `324bf00698740a49`; `~/.claude/plugins/known_marketplaces.json` `97c2e5a7a4acee99`; `~/.claude/skills/rush`, `~/.codex/skills/rush`, `~/.agents/skills/rush` absent.

Preview: `rush setup <tmp>/g6proj --agent claude --json` and `--agent codex --json` with the real HOME, both exit 0, `status skipped, reason preview_only`, review host `claude` and `codex` respectively; no host config bytes changed.

Result: Claude Code model-requested Rush call, granted. `claude -p <prompt> --mcp-config <tmp>/mcp.json --strict-mcp-config --output-format stream-json --verbose --max-turns 6 --allowedTools mcp__rush_t29__rush_lint,mcp__rush_t29__rush_check`, exit 0, 27.8 s. The per-invocation config launches frozen 11cc193a with `mcp serve --profile core`; no real config is written. Host trace: init `mcp_servers: [{name: rush_t29, status: connected}]`; `tool_use mcp__rush_t29__rush_lint {path: <tmp>/g6proj/src/bad.py}` returned `status fail, summary "lint [ruff]: 2 issue(s)"`; `tool_use mcp__rush_t29__rush_check {path: <tmp>/g6proj}` returned `status fail, summary "check: executed 5 tool(s) with status 'fail'"`, engine `ruff+mypy+pyrefly+vulture+aislop+pytest`; the model's answer named `F401` at line 1 (`os`) and line 2 (`sys`); `permission_denials: []`.

Result: Claude Code denied. The same command with `--disallowedTools mcp__rush_t29__rush_lint,mcp__rush_t29__rush_check`, exit 0, 18.9 s. The server was `connected`; the host withheld both tools (tool search returned only rush_review, rush_memory, rush_security and the rest), and the model answered `Neither tool ran ... I have no status or rule ids to report`.

Result: Codex CLI model-requested Rush call. `codex exec --skip-git-repo-check --json -C <tmp>/g6proj -c mcp_servers.rush_t29.command=<frozen rush> -c mcp_servers.rush_t29.args=["mcp","serve","--profile","core"] -c mcp_servers.rush_t29.tool_timeout_sec=120 <prompt>`, exit 0, 46.0 s. The model requested `rush_t29.rush_lint {path: <tmp>/g6proj/src/bad.py}` and `rush_t29.rush_check {path: <tmp>/g6proj}`; both items ended `status failed` with host error `MCP tool call requires approval, but approval policy is never`. The host denied the calls before they reached Rush, so there is no Codex domain output.

Result: Codex CLI timeout probe (`tool_timeout_sec=0.001`, `rush_status`), exit 0, 28.7 s: the call was stopped by the same approval-policy denial before the timeout could apply, so no timeout behavior was observed.

Side effect seen in the Claude Code runs: the temporary project gained `.ruff_cache/` (ruff 0.16.7) and `graft/.cache/session/*.json`. The CLI journeys with the same binary created no `.ruff_cache`, and graft is a user-level host hook, so these are not attributed to Rush from this evidence.

Blocker: lane real-config install, trust, reload, skill invocation, faulty edit with received model context, timeout and disconnect, for both Claude Code and Codex CLI. Reason: both real configs already hold a user-owned `rush` MCP entry (Claude Code user `mcpServers.rush`, Codex `mcp_servers.rush`) with no Rush ownership record (`~/Library/Application Support/Rush/agents/` is empty). `rush agent connect` keeps an existing Rush entry and repairs only its command path (its own help text), so connecting the unreleased 449cd62 binary would repoint the owner's working entry at a scratch executable, and `rush agent disconnect` would then either remove an entry Rush did not create or leave it pointing at a deleted binary. Either way the after-digest could not equal the before-digest. This lane needs an owner decision on the pre-existing entries (for example, installing 449cd62 as the owner's installed rush first, or temporarily removing the existing entries). No real host config was written, so no disconnect was needed. The Codex model-call lane additionally needs an approval policy that lets `codex exec` run MCP tools (for example `-c approval_policy=...` chosen by the owner).

## G8 native terminal walkthroughs

Result: macOS lane, frozen 11cc193a, terminal = Python `pty.fork` with `TERM=xterm-256color`, `LANG=en_US.UTF-8`, projects `proj ü one` and `proj two` (git repositories with a dirty file), fresh HOME.

- 80x24, 120x40 and 60x20: 43 keyed steps each. At launch the state words `loading`, `unavailable` and `failed` render; all eight section labels are present at 80x24 and 120x40; 60x20 shows the one-section compact layout. `q` exited 0 at each size (89.2 s, 89.3 s and 88.8 s per full walkthrough). No traceback in any frame.
- Actions observed: C `analysis started`; s then y, and Esc to deny a grant, return to the Overview with `p stage to retry` (the project is unregistered, so the scan stays at the setup stage); c `no running work to cancel`; r `no completed run to rescan yet`; M opens the memory table (`id trust source stale`, `page 1/1`, `no memory recorded for this project yet`); m opens Tokens; d `dirty-file diffs are in the Git section`; in Git the footer offers `]:Older commits`, `[:Newer commits` and `d:Dirty diff`; i `no captured artifact selected`; F2 opens the project chooser (`Choose later`, `[enter] choose`, `[escape] cancel`), then j and Enter switch projects (`[1/2]` header); the bracketed paste `ü漢字 paste` appears in the filter; resize to 60x20 and back to 120x40 re-renders without error.
- NO_COLOR=1 with RUSH_REDUCED_MOTION=1 at 80x24: all eight sections render, `q` exits 0 (22.9 s).
- Ctrl-C at idle at 80x24: the process did not exit within 11 s; the harness sent SIGTERM (exit -15). `q` is the working quit key.
- Not traversed on this lane: a complete setup, scan, agent and rescan cycle inside the TUI with a registered project and real findings; memory write, archive and delete actions; artifact detail with a captured artifact; slow-work progress. The walkthrough projects were unregistered, so these screens showed their empty and setup-stage states only.
- T26 command counts and native CLI probes: in the T26 route counts section above.

Blocker: lane Linux native walkthrough. Reason: this run has only a macOS machine; per the owner's rule a phase is not gated on cross-platform testing, and CI runs the Linux contract jobs.

Blocker: lane Windows native walkthrough. Reason: this run has only a macOS machine; CI runs the Windows contract job.

## CI runs

Recorded by the orchestrator after the phase push.

## Restart execution — 2026-10-03

This section records a separate source-checkout run. Historical binary journeys
above retain their original identity and limitations. They do not accept these
new changes. Phase acceptance and final handoff remain incomplete.

Checkout: `/Users/jamesdsizemore/Developer/rush-cli-worktrees/phase-70`, branch
`phase/70-agent-adoption-and-usability`, starting HEAD
`66c6c799eaa5b6017776d659e9e0de2b4a8878a5`. Locked project interpreter reports
Python 3.12.12. Primary checkout and its existing user-owned changes preserved.
Execution checklist: [Phase 70 restart](../phase-plans/phase-70-restart-checklist.md).

Owner corrections during this run: prioritize existing CI blockers and full
gates; use existing CI for Linux/Windows testing. Separate production Aislop
attribution writer stopped before edits; that requirement remains unresolved.
Claude Code and Codex host scope follows the existing §3.3 owner amendment.

T29 change: dependency-free `t29_world` gets the restart plan's exact local
`.aislop/config.yml` with `security.audit: false`. Real anti-pattern subprocess,
six-step results and CLI/MCP/TUI permission assertions remain exercised.

Executed command:

```sh
rtk proxy env -u PYTHONPATH uv run --frozen --python 3.12 --extra dev python -m pytest tests/test_phase70_onboarding.py::test_t29_allowed_and_denied_scans_parity_cli_mcp_tui tests/test_phase70_onboarding.py::test_t29_user_outcome_parity -q
```

Result: **2 passed in 18.24s**. This closes the reproduced fixture failure only;
it does not repair production dependency attribution or prove native journeys.

CI diagnosis corrections from saved `ci-36465316792-failed.log` and current
producer/reader source:

1. Offline review fixture supplied an executable but omitted Ollama transport
   readiness. Production correctly skipped an unavailable daemon. Fixture now
   controls that external readiness boundary; unavailable-runner assertion stays.
2. Recorded target metadata was displayed correctly. Saved failing assertion
   concerned the unscoped label wrapping on a longer Linux temporary path.
3. Git backend correctly set truncation; TUI appended its notice beyond the
   clipped body. Notice now precedes diff lines.
4. Both warnings came from the same threaded `multiprocessing` fork fixture.
   Concurrent connect now uses existing real `spawn_child` processes.
5. Windows collection imported POSIX `pty` unnecessarily. Import now belongs
   inside `spawn_pty_child`; ordinary children use `subprocess.Popen`.

Live remote read during this run: latest branch CI remains
[36465316792](https://github.com/jamesdsizemore/rush-cli/actions/runs/36465316792),
conclusion **failure**, head `e7c29b1c573ad3b6e7872fb20a617e92d5d51244`.
No new CI conclusion claimed. Full local gate, final frozen artifacts, native
host journeys, independent final review and new CI evidence remain required.

Additional executed source checks:

- Complete T29 selection (`tests/test_phase70_onboarding.py -k t29 -q`):
  **8 passed, 38 deselected in 18.06s**.
- Three saved CI selectors, T03 concurrency and unavailable-runner case:
  **5 passed in 1.79s**, fresh long owned `/tmp` test root. Explicit no-daemon
  readiness probe plus unavailable-runner test after final T27 fixture edit:
  **2 passed in 0.17s**.
- Terminal/dashboard/fork-free-helper regressions: **128 passed, 1 Windows-only
  deselected in 33.93s**. Windows check belongs to existing CI. Invocation:

```sh
rtk proxy env -u PYTHONPATH TERM=xterm-256color uv run --frozen --python 3.12 --extra dev env -u NO_COLOR python -m pytest tests/test_tui_terminal.py tests/test_dashboard_http_contract.py tests/test_fork_free_children.py --basetemp /tmp/rush-phase70-portability-regressions-color-01a10230 -q --tb=line
```

Initial PTY failures were characterized as `TERM=dumb` and inherited
`NO_COLOR=1`. No terminal test/regex change applied; real ESC sample matched
the existing regex. Changed-file lint/format/whitespace checks passed.

Frozen patch identities before independent review:

| File | SHA-256 |
|---|---|
| `src/rush/tui.py` | `2731a7f157f0cf2ec49a5187efdf9878770c74b841f7128c7db4a3232879cc7d` |
| `tests/_process_children.py` | `d850e9e4c35a892f201b05e3dfe88ec63a0865e22df58c2e703cd4b77dc10f5a` |
| `tests/test_phase70_adoption.py` | `0e894f0d818b255f8e5d44fef1ad0b8b0d4d192decbe2e1d640f24f5acfbc2ed` |
| `tests/test_phase70_onboarding.py` | `23a007fa80129e1034356465fb447123e131bc8268fa7399f8a4a7f0d265d2e1` |
| `tests/test_phase70_t27.py` | `f3187b730293e8f409b74a8e9c3164889001220387b3438fb0ad119410e4ce72` |
| `tests/test_phase70_t28c_review2.py` | `d3b0c915073637440d09b6997f5f61ee03badd4045cce299ae2841724d5851f4` |
| `tests/test_phase70_tui_usability_ef.py` | `683375a43fd21210383edf06568ea53e311f0e36bce8f9bc34faf01678026676` |
| `uv.lock` | `fb0804a33d4e599ccf16008f75b73a8c38ec737c60fe2dcce158f6814a45a806` |

Hashes establish review subject identity only. They do not close full regression,
installed/native behavior, production attribution, host acceptance or final CI.

### Independent frozen review findings

Initial seven-file review found Git detail still clipped at actual 80×24 and
60×20. `_render_git_panel` placed selected detail after up to twenty history
rows and dirty rows; `render_app` gives Git a fixed-height body. Initial
220×400 rendered check did not exercise this boundary. Additional correction
and actual required-size rendered checks are in progress; earlier patch hashes
and passing checks do not accept the changed subject.

Separate scope correction: historical "Phase 71 consumes" section above assigned
dashboard frozen provisioning to Phase 71. Amended Phase 70 §8.1 explicitly
retains shared dashboard setup/readiness contracts. Current server compares an
unresolved plan ID, then setup resolves and applies package identities in one
invocation (`identity_source="resolved_at_apply"`). Reviewed concrete version
and digest are not yet bound. This remains an unresolved **Phase 70 T24 shared
contract**, not an approved transfer to Phase 71. Required behavior: a changed
upstream identity after preview must not replace the reviewed identity during
apply; use reviewed bytes or reject before effects.

Inherited Phase 69 T054 51/51 receipt excludes nine Windows ownership scenarios
and records a non-green full run. Current per-finding source, equivalent test
and empirical evidence reconciliation remains required. Existing named/renamed
regressions must be read before adding tests; historical counts do not close
current acceptance.

### Restart gate observations and inherited-finding reconciliation

Current status: **in progress; Phase 70 not accepted**. This subsection extends
the 2026-10-03 restart record without replacing historical evidence above.
Source review used committed `66c6c799eaa5b6017776d659e9e0de2b4a8878a5`, then
separately reviewed frozen correction packets. Rows below distinguish source
and test-body coverage from executed behavior. Historical T054's 51/51 claim
excluded nine native Windows ownership cases and recorded a non-green full
suite; it cannot close these rows. Existing equivalent/renamed regressions
were read before adding tests. Finding inventory is not acceptance evidence.

#### Observed execution through this checkpoint

| Check / subject | Observed result | Exact limit |
|---|---|---|
| Coordinator G7 baseline, full `tests/` with `-m ""` | 6,345 passed, 4 failed, 2 deselected in 1,503.64s; 1,482 frozen subject hashes unchanged | Non-green baseline, not G7 PASS. Subsequent source/lock/docs edits require final frozen gates. |
| Four failed baseline selectors after Git loading-visibility and lock corrections | 4 passed in 9.89s | Targeted repair verification only; does not rerun full suite. |
| Dependency audit after PyJWT 2.15 / urllib3 2.8 lock update | PASS; reuse-expiry/options regression PASS | Upgraded lock changes final artifact provenance. Audit success is not installed-artifact acceptance. |
| M10 token-reader correction | 93 local tests passed | Independent review still found canonical project filtering missing from handoff rows; correction remains in progress. |
| S03 Windows wait-result correction | 104 local tests passed; 1 Windows ACL case deselected | Local failure-path tests do not execute nine required native Windows ownership scenarios. |
| U05 original downloader plus extended production-JS tests | 12 failed, 4 passed, 32 deselected in 4.26s | Actual RED: early/missing terminal marker, zero progress, oversize and invalid size. |
| U05 frozen guarded downloader, exact focused selection | 16 passed, 32 deselected in 3.94s | Real production JS under existing Node DOM harness; not native browser acceptance. |
| U05 complete `test_dashboard_projects.py` module | 48 passed in 9.75s; Python 3.12.12; Ruff check/format PASS | Binary three-page assembly, empty artifact, grant forwarding and cancel before Blob/URL/anchor verified. |
| G5 older-lock macOS artifact probe | PASS; artifacts `/tmp/rush-phase70-g5.AVQbMy` | Older lock. Final wheel/sdist/frozen executable must be rebuilt and probed after lock upgrade. |

U05 commands actually executed by the regression lane:

```sh
rtk proxy env -u PYTHONPATH uv run --frozen --no-sync --python 3.12 --extra dev python -m pytest tests/test_dashboard_projects.py -q -k artifact_export_control --tb=short
rtk proxy env -u PYTHONPATH uv run --frozen --no-sync --python 3.12 --extra dev python -m pytest tests/test_dashboard_projects.py -q --tb=short
```

U05 post-run subject hashes remained unchanged:

| File | SHA-256 |
|---|---|
| `src/rush/dashboard/application.js` | `c04c5dc75538071c9af0de46e5dcc3ffb663bb77f19aaf13b40838258a27da1b` |
| `tests/test_dashboard_projects.py` | `96b6b1c975721477bcd498e01ddf1f6a90d82c8b681f20cbd9a1f5ddb93ef0ef` |

#### All inherited Phase 69 findings

Paths in this table are repository-relative. `Present` means frozen source and
substantive existing test bodies were inspected, not that the row passed final
acceptance. Every row still depends on applicable final frozen G7/G8 checks;
additional empirical gaps are explicit. Coordinator-reported local correction
results above remain separate from this lane's source review and U05 execution.

| ID | Required outcome | Exact current code path / symbol | Existing behavior selector and implementation finding | Unresolved empirical acceptance / risk |
|---|---|---|---|---|
| S01 | Ownership reaches real engine execution, version/work/resume/rescan subprocesses. | `src/rush/invocation/executor.py::InvocationExecutor.execute`; `src/rush/runtime/subprocesses.py::owned_execution_scope`, `run_subprocess`, `run_engine`. | `tests/test_subprocess_contract.py::test_typecheck_tool_run_engine_call_carries_owner_instance_id_and_run_id` observes ambient ownership at real engine call site; `tests/test_project_run_lifecycle.py::test_resume_scan_run_call_path_reaches_owned_execution_scope_at_invocation_executor_boundary` observes forwarded identity. Shared boundary present. | Spies prove propagation, not installed/native descendant lifecycle. |
| S02 | Reap confirmed-dead owner's children before releasing admission; retain uncertain records; exclude live owners; recover receipts once. | `src/rush/dashboard/state.py::reconcile_admissions`, `claim_dead_owner`; `src/rush/runtime/subprocesses.py::reap_owner_processes`. | `tests/test_dashboard_http_contract.py::test_dead_owner_reap_terminates_recorded_children_before_release`, `test_failed_reap_retains_admission_and_does_not_release`, `test_concurrent_recovery_claims_on_the_same_pending_row_only_one_succeeds` exercise real children, failure retention and exclusive claim. Present on POSIX. | Current crash/restart and native Windows recovery evidence required. |
| S03 | Native Windows mutex, closed launch gate, restricted inheritance, Job Object fencing, PID-reuse-safe recovery and restart. | `src/rush/dashboard/state.py::OwnerLock._acquire_windows_mutex`, `claim_dead_owner`, `_observe_owner_windows`; `src/rush/runtime/subprocesses.py::_launch_gated_process_windows`, `_windows_confirm_terminated`. | Existing mutex/job-name tests check names. Frozen review found `WAIT_FAILED` treated as ownership/death; correction now has coordinator-observed 104 local passes. | Nine report §12 native Windows scenarios remain unmet; name checks and local mocks cannot close them. Execute in existing Windows CI. |
| S04 | Reservation atomically stores sanitized validated arguments, preallocated per-effect IDs and recovery schema; never reconstruct from body hash. | `src/rush/dashboard/state.py::MutationLedger.reserve`, `get_reservation`; `src/rush/dashboard/server.py::_s04_effect_ids`, `_handle_action`. | `tests/test_dashboard_missing_routes.py::test_reservation_persists_validated_argument_payload`, `test_reservation_persists_preallocated_effect_ids_map`, `test_recovery_uses_persisted_reservation_data_only_never_replays_body_hash` inspect persisted payload/IDs. Persistence present. | Reservation-data inspection is not execution of every mapped effect's crash/recovery path. Preserve full per-kind crash matrix. |
| S05 | Monotonic handoff recovery, stable operation identity, no plaintext capability, no effects leaked before descriptor. | `src/rush/workflows/project_run.py::build_handoff`, `recover_prepared_handoff`; `src/rush/dashboard/state.py::reconcile_admissions`. | `tests/test_dashboard_map.py::test_crash_after_session_receipt_before_prepared_descriptor_is_recoverable` checks orphan/revocation receipts; `tests/test_scan_handoff.py::test_session_capability_never_appears_in_persisted_descriptor_or_status_serialization` rejects plaintext. Present. | Current crash/restart runs required. Recovery receipt is not receiver acknowledgment. |
| S06 | Preview hash binds packet, evidence versions, allowlist, source/run/attempt, grants and budget. | `src/rush/dashboard/server.py::_handoff_preview_hash`, `_dispatch_handoff_send`. | `tests/test_dashboard_scan_actions.py::test_handoff_preview_hash_changes_when_packet_content_changes`, `test_handoff_preview_hash_changes_when_evidence_artifact_version_changes`, `test_handoff_preview_hash_changes_when_session_allowlist_changes`. Full envelope present. | Current HTTP and visible preview/send proof required; renamed selectors already cover original themes. |
| S07 | Handoff/provisioning revalidate accepted expected identity immediately before effects. | `src/rush/dashboard/server.py::_revalidate_expected_at_execution`, `_dispatch_handoff_send`, `_dispatch_provision_apply`. | `tests/test_dashboard_scan_actions.py::test_handoff_send_returns_terminal_conflict_on_envelope_mismatch_with_zero_effects`, `test_provisioning_worker_returns_terminal_conflict_on_plan_mismatch_with_zero_effects` assert terminal conflict. Rechecks present. | Reviewed concrete package identity still required under Phase 70 T24 shared dashboard contract; unresolved-plan comparison alone is insufficient. |
| S08 | Expected comparison and synchronous mutation share lock/CAS; independent artifacts remain independent; genesis/configuration revisions work before scan. | `src/rush/dashboard/state.py::ProjectRegistry.mutation_lock`; `src/rush/dashboard/server.py::_handle_action`; memory store CAS. | `tests/test_dashboard_missing_routes.py::test_two_requests_with_the_same_expected_revision_cannot_both_commit_against_an_invalidated_state` checks lock sequencing; `test_never_scanned_configure_and_memory_mutation_still_work_against_genesis` exercises genesis. Protection present. | Lock-order test alone does not prove two concurrent HTTP mutations cannot both commit; retain domain CAS/concurrency evidence. |
| S09 | Allocate winner's attempt before header; attachments/replays return exact attempt; resume gets new attempt. | `src/rush/dashboard/state.py::MutationLedger.admit`; dashboard admission/launch boundary. | `tests/test_dashboard_scan_actions.py::test_attach_before_header_publication_returns_the_exact_attempt_later_persisted` compares attached/winner/persisted identities. Present. | Current admission race/restart execution required. |
| S10 | Cancel resolves logical operation including attached caller and another server; old intent cannot cancel later attempt. | `src/rush/dashboard/server.py::_dispatch_scan_cancel`, `_resolved_operation_id`; `src/rush/workflows/project_run.py::cancel_scan_run`. | `tests/test_dashboard_scan_actions.py::test_cancel_from_a_second_server_process_still_resolves_the_same_durable_intent`; `tests/test_scan_rescan.py::test_old_cancellation_intent_cannot_cancel_a_later_resume_attempt` checks new attempt lacks old marker. Present. | Current full/slow CHECK_SUITE cancellation and partial-result evidence required. |
| S11 | Public bootstrap exchange itself atomic and one-use, including direct callers and expiry races. | `src/rush/dashboard/auth.py::exchange_bootstrap`. | `tests/test_dashboard_http_contract.py::test_concurrent_direct_method_calls_to_exchange_bootstrap_mint_exactly_one_session` asserts one result/session; concurrent HTTP coverage exists. Present. | Current concurrent auth execution required. |
| S12 | Redact control/bootstrap/cookie/CSRF secrets in nested output, preserving ordinary text and concurrent safety. | `src/rush/dashboard/server.py::_redact_secrets`, `live_secrets`; locked auth secret matching. | `tests/test_dashboard_http_contract.py::test_bootstrap_token_value_is_redacted_from_finding_content_via_digest_match`, cookie/CSRF counterparts, `test_ordinary_text_resembling_a_token_format_is_not_falsely_redacted`. Present. | Current real HTTP failure/churn checks required. |
| S13 | Security headers cover JSON, assets, failures and pre-thread overload. | `src/rush/dashboard/server.py::_send_json`, response helpers, `process_request`. | `tests/test_dashboard_http_contract.py::test_pre_thread_503_response_carries_the_same_security_headers_as_normal_responses` asserts exact headers; JS/CSS coverage present. | Current response-family checks required. |
| S14 | Only explicit integer schema version 1 accepted; missing/null/string/bool rejected before action/control effects. | `src/rush/dashboard/server.py::_schema_version_error`, `_handle_action`, `_handle_control_check_suite`. | `tests/test_dashboard_http_contract.py::test_handle_action_rejects_missing_schema_version`, null/string/bool and control counterparts. Present. | Valid control-version test reaches unrelated missing-input rejection; schema acceptance is not successful CHECK_SUITE execution. |
| S15 | TUI lifetime owner lock precedes reservation/worker; lock failure creates no work; attachments do not relaunch; sibling completion retains shared owner. | `src/rush/tui.py::_admit_local_run`, `_start_scan_thread`; `src/rush/dashboard/state.py::OwnerLock`. | `tests/test_tui.py::test_admit_local_run_refuses_to_reserve_work_when_owner_lock_acquisition_failed`, attachment-identity and sibling-owner selectors. Present. | Native Windows lifetime-lock evidence remains S03. |
| S16 | Handoff source tuple and provisioning job tuple remain distinct/stable through 202/status/replay/recovery. | `src/rush/dashboard/server.py::_dispatch_handoff_send`, `_dispatch_provision_apply`. | `tests/test_dashboard_scan_actions.py::test_handoff_202_response_includes_attempt_id_matching_preview_source_tuple`, `test_provisioning_202_response_includes_its_own_allocated_attempt_id`, `test_crash_immediately_after_202_recovers_without_reminting_or_substituting_an_attempt`. Present. | Current accepted/status/restart execution required. |
| M01 | Readers receive detached immutable records; scan publication and memory refresh preserve both concurrent updates. | `src/rush/dashboard/state.py::ProjectRegistry.get`, `publish_scan_result`, memory refresh publication. | `tests/test_dashboard_map.py::test_get_returns_a_detached_record_not_the_live_stored_object`, `test_paused_scan_publication_and_concurrent_memory_refresh_both_survive`. Present. | Current concurrency execution required. |
| M02 | Scan keeps consumed source A after live tree becomes B; CHECK_SUITE retains inventory/content/Git provenance. | `src/rush/dashboard/server.py::_publish_scan_snapshot`, `_hydrate_published_scan`, `publish_check_suite_scan`; `src/rush/workflows/project_run.py::_build_manifest`. | `tests/test_dashboard_map.py::test_scan_bytes_a_changed_to_b_then_hydrate_still_reports_a`, `test_check_suite_manifest_carries_content_identity_inventory_generation_and_git_link`. Present. | Current fresh-server/restart checks required. |
| M03 | Persist inventory; old attempts lacking it report missing provenance, never live rewalk. | `src/rush/workflows/project_run.py::_scan_inventory`, `_build_manifest`; `src/rush/dashboard/server.py::_manifest_file_inventory`. | `tests/test_dashboard_map.py::test_persisted_inventory_survives_restart_and_file_changes`, `test_legacy_attempt_without_inventory_reports_missing_provenance_not_current_files`. Present. | Old missing-test issue stale; no duplicate test needed. Current run required. |
| M04 | Ingest real candidate events; retain 2,000 per run; paginate 100; stale cursor gives explicit gap. | `src/rush/dashboard/server.py::_handle_events`; `src/rush/dashboard/state.py::MutationLedger` event ingestion/listing. | `tests/test_dashboard_missing_routes.py::test_events_route_surfaces_real_candidate_progress_events`, retention and expired-cursor selectors. Present. | Producer delivery/timing needs current execution; retention counts alone do not prove it. |
| M05 | Every relationship survives grouping and remains reachable through same-group/overflow expansion. | `src/rush/dashboard/project_map.py::_grouped_overview`, `_relation_overflow_members`, `expand_group_edge`. | `tests/test_dashboard_map.py::test_101_file_101_finding_fixture_preserves_all_report_relationships_through_expansion` reconstructs relationship reachability. Present. | Current expansion/paging boundary execution required. |
| M06 | Historical run requires pinned attempt; expansion uses snapshot; cursor binds full view identity. | `src/rush/dashboard/server.py::_build_historical_map_snapshot`; map expansion/cursor validation. | `tests/test_dashboard_map.py::test_historical_map_request_without_attempt_id_is_rejected`, `test_historical_expansion_uses_the_pinned_attempts_snapshot_not_live_record`, cross-view cursor coverage. Present. | Current history/resume/cursor tests required. |
| M07 | Every committed memory mutation refreshes publication/generation; no-write/preview creates no sequence bump. | `src/rush/dashboard/server.py::_dispatch_memory_edit`, archive/delete/promote, `_refresh_project_memories_if_store_exists`. | `tests/test_memory_public_contract.py::test_memory_edit_immediately_updates_map_content_and_generation`, `test_promotion_denial_after_candidate_write_still_refreshes_the_real_candidate_commit`, `test_preview_and_zero_write_failure_publish_no_fabricated_sequence_bump`. Present. | Current execution required, including partial commit before promotion denial. |
| M08 | Explicit owner before reservation; project UUID bound to URL; session bound to authenticated non-secret ID; opaque user/agent accepted. | `src/rush/dashboard/server.py::_validate_memory_owner_scope`, `_handle_action`. | `tests/test_memory_public_contract.py::test_foreign_project_uuid_owner_rejected_before_reservation`, `test_wrong_session_id_owner_rejected`, `test_arbitrary_nonempty_user_agent_labels_accepted_structurally_and_persist_unchanged`. Present. | Current no-effect rejection HTTP tests required. |
| M09 | Registered UUID flows through TUI/all maintenance; scoped expiry leaves other owners untouched; path fallback only explicit unregistered root. | `src/rush/tui.py::_default_owner_scope_id`; `src/rush/cli.py::memory_maintain_cmd`; `src/rush/tools/memory.py::MemoryTool._run_maintain`. | `tests/test_memory_core_regressions.py::test_tui_and_cli_maintenance_reach_the_registered_projects_uuid_owned_row_not_path_owner` checks UUID/path distinction. Present. | Focused maintenance/expiry modules and all four owner kinds require current run. |
| M10 | Canonical project/run/agent/session selection filters displayed token/by-kind/handoff totals; exclude unscoped legacy rows from narrower selection. | `src/rush/dashboard/server.py::_build_tokens_section`; `src/rush/token_economy/telemetry.py::read_summary_readonly`, `read_memory_event_totals_readonly`. | `tests/test_dashboard_memory_tokens.py::test_tokens_section_totals_respect_run_agent_session_filters_not_just_handoff_rows` covers unequal totals. Frozen review found missing canonical filter and migrating GET; correction has 93 local passes. | Independent handoff-row project-filter finding remains under correction. Combined/canonical/legacy read-only acceptance not closed by prior passes. |
| M11 | Invocation minted once; distinct identical calls counted twice; retry deduped; actual retrieval/fallback attribution preserved. | `src/rush/tools/memory.py::MemoryTool.run`; `src/rush/memory/retrieval.py::_record_memory_event`, recall/hybrid/expand; telemetry recording. | `tests/test_memory_retrieval.py::test_two_identical_distinct_calls_are_counted_twice_and_one_retry_is_counted_once`, `test_persisted_attribution_columns_match_the_public_invocation_id_on_every_success_and_fallback_branch`. Present. | Current actual-route execution required. |
| M12 | Capture immutable per-candidate/attempt artifacts before overwrite; preserve resume/CHECK_SUITE producers; lossless attempt-bound byte pages. | `src/rush/workflows/project_run.py` capture/finalization; `src/rush/workflows/projects.py::read_project_artifact_page` and exports. | `tests/test_dashboard_git_artifacts.py::test_two_candidates_in_one_attempt_writing_the_same_logical_filename_retain_different_original_bytes`, resumed-attempt and split UTF-8/NUL/0xff paging selectors. Backend present. | Installed/native browser two-attempt full size/hash remains required. U05 correction separately verified locally. |
| M13 | Repository-state evidence separate; Git checks receive only real consumed paths. | `src/rush/workflows/project_run.py::_run_candidates`, `_build_manifest`; `src/rush/workflows/projects.py::git_link_matches_commit`. | `tests/test_dashboard_git_artifacts.py::test_no_synthetic_evidence_key_reaches_git_show_commit_path`, clean matching GitGuard/DiffCover/UnderCover selector. Present. | Old missing-test issue stale. Current repository-engine execution required. |
| M14 | Traverse beyond 10,240 with exact totals; page freshness revalidated; generation mutation rejects cursor. | `src/rush/dashboard/server.py::_build_memory_section`; memory paging/query. | `tests/test_dashboard_memory_tokens.py::test_browse_and_query_traverse_more_than_10240_rows_with_exact_totals_and_unique_ids`, freshness and generation-mutation selectors. Present. | Current large-fixture traversal required. |
| M15 | In-process tools read staged, not divergent live bytes; logical provenance preserved through scan/CHECK_SUITE. | `src/rush/workflows/project_run.py::_execute_candidate`; staging/result remapping. | `tests/test_project_run_lifecycle.py::test_slop_tool_reads_staged_bytes_not_live_source_when_live_content_diverges`; `tests/test_full_project_scan.py::test_offline_review_dead_asset_license_matrix_all_read_staged_bytes`. Present. | Current real scan/check execution required. |
| M16 | Record actual explicit targets/configs only; root scan records intended scope, not unrelated inventory. | `src/rush/runtime/subprocesses.py::_staged_invocation`; `src/rush/engines/staging.py::record_consumption`. | `tests/test_project_run_lifecycle.py::test_explicit_target_a_py_does_not_claim_unrelated_b_js_as_consumed`; explicit configuration consumption selector. Present. | Exact-set bodies already cover renamed requirement; current run required. |
| M17 | Registered repository-state engines execute actual route; unknown/missing/denied dispositions honest. | `src/rush/workflows/project_run.py::_execute_candidate` registered `ENGINES` branch. | `tests/test_full_project_scan.py::test_gitguard_candidate_executes_through_execute_scan_with_a_real_or_fixture_engine_binary_and_persists_evidence`, unknown/missing/denied selectors. Present. | Fixture proves routing, not every installed engine's native integration; representative CI workloads remain required. |
| M18 | Escaping symlink rejected before argv; no live fallback; allowed internal links/external config preserved. | `src/rush/engines/staging.py::substitute_arg`; staged argv path. | `tests/test_project_run_lifecycle.py::test_escaping_symlink_argument_never_reaches_the_real_engine_argv`, `test_internal_symlink_and_explicitly_supported_external_configuration_are_not_overblocked`. Present. | Current rejected/allowed-path execution required. |
| M19 | Fresh owned DiffCover report/tempdir; reject overrides; cleanup every exit; fold coverage and diff identity. | `src/rush/engines/diff_cover.py::run`. | `tests/test_diff_cover_reference.py::test_stale_live_report_with_no_fresh_output_fails_honestly_rather_than_reusing_old_bytes`, conflicting-args, cleanup and changed-coverage identity selectors. Present. | Current timeout/cancel/error cases required. |
| M20 | Remap decoded Stylelint source/Trivy Target fields; preserve literal message/fix text. | `src/rush/engines/staging.py::remap_paths`; decoder integration. | `tests/test_project_run_lifecycle.py::test_stylelint_decoded_raw_source_field_uses_logical_path_not_staged_temp_path`, `test_literal_message_or_fix_text_containing_a_path_like_substring_is_never_rewritten`; Trivy reference fixture. Present. | Current decoder checks required. |
| M21 | Vanished/read/copy/hash/config staging failures produce explicit incomplete evidence; no clean zero-candidate/live fallback. | `src/rush/engines/staging.py::stage_inventory`, failure recording; `src/rush/workflows/project_run.py` aggregation. | `tests/test_project_run_lifecycle.py::test_copy_or_hash_error_during_staging_prevents_the_affected_candidate_from_executing`, vanished-input/no-live-fallback selectors. Present. | Current injected-failure execution required. |
| U01 | F2/F3/project/section/pane/hierarchy/help; fragmented UTF-8/escapes; selectors/SIGWINCH cleanup; identical native Windows actions. | `src/rush/dashboard/keymaps.py`; `src/rush/tui.py::_dispatch_key`; `src/rush/dashboard/terminal_input.py::PosixKeyReader`, `WindowsKeyReader`. | F2/F3/pane/hierarchy/decoder tests; `tests/test_tui_terminal.py::test_tab_never_switches_project_over_a_real_pty`. POSIX path present. | Mocked Windows scan codes do not close native console acceptance; existing Windows CI must exercise it. |
| U02 | Remain pending until durable terminal state; retain/poll logical op; cache/renew authenticated session; durable cancel/detach. | `src/rush/tui.py::_start_dashboard_owned`, `_poll_dashboard_owned_scan`, `DashboardOwner`; `src/rush/dashboard/server.py::_control_session`. | `tests/test_tui.py::test_dashboard_owned_check_suite_does_not_report_complete_before_terminal_status`, retained-operation, polling/session-renewal selectors. Present. | Current real slow CHECK_SUITE partial-result/cancel/control-channel journey required; acceptance response is not completion. |
| U03 | Detach local run A only; sibling B keeps running; failed records retained; dead-owner cleanup still all-runs. | `src/rush/tui.py::_handle_detach`; `src/rush/runtime/subprocesses.py::reap_owner_processes` exact run filter. | Real two-tree tests in `tests/test_subprocess_contract.py`; `tests/test_tui.py::test_detach_reaps_only_the_selected_local_runs_process_tree_not_a_sibling_projects`, failed-record selector. Present. | Current real process-tree evidence required. |
| U04 | Shared theme/motion; 79/80/99/100 layouts/footer; resize preserves state; NO_COLOR independent of reduced motion. | `src/rush/tui.py::render_app` and theme/selection-motion paths. | `tests/test_tui.py::test_layout_80_columns_uses_compact_branch`, adjacent boundaries, selection/reduced-motion selectors. Git required-viewport correction separately reviewed and exercised. | Headless renders do not prove complete terminal motion/walkthrough. Final subject tests required. |
| U05 | Visible granted export validates immutable page reference/size/digest; rejects truncation/failure; cancels; downloads complete bytes. | `src/rush/dashboard/application.js::downloadArtifactContentPages`, `buildArtifactExportControl`. | `tests/test_dashboard_projects.py::test_artifact_export_control_rejects_a_truncated_or_inconsistent_page_sequence` now exercises 13 cases; positive selector covers binary three pages/empty; cancellation asserts no Blob/URL/anchor. RED and GREEN observed above. | Local defect corrected and full module passed. Native browser two same-name attempts, complete size/hash and failure/cancel flow remain unmet. |
| U06 | Visible preview/inspect/send uses pinned inputs/hash/identity; stale 409 retains preview, disables send and forbids silent retry. | `src/rush/dashboard/application.js::buildHandoffControl`; server handoff contracts. | `tests/test_dashboard_projects.py::test_visible_handoff_preview_then_send_completes_using_stored_preview_inputs`, source-change/stale-disable scenarios drive production JS. Present. | Actual browser delivery and receiver acknowledgment/consumption not proved by mocked POST or stored descriptor. |
| U07 | Warm-local shell interactive within bound while map delayed; navigation-origin metric distinct from bootstrap. | `src/rush/dashboard/application.js` shell-interactive milestone independent of map. | `tests/test_dashboard_projects.py::test_shell_interactive_signal_independent_of_map_fetch_completion` delays map and uses controls. Regression present. | Node DOM is not native navigation timing. Current browser/version/control/map timestamps required. |
| U08 | Real terminal event via normal polling triggers one actual 480ms pulse; no idle/reduced-motion repetition; reference comparison/date preserved. | `src/rush/dashboard/application.js::startEventPolling`; `src/rush/dashboard/project_map.js::pulseEvidence`. | `tests/test_dashboard_projects.py::test_terminal_event_pulse_plays_once_480ms_on_real_scan_completion_via_normal_ledger_polling` reaches spy; motion-contract tests structural. Present. | Actual browser duration/easing/start-mid-end and prescribed reference comparison unproved; spy call is not observed animation. |
| U09 | Drain/join PTY reader before close; surface errors; explicit TERM/NO_COLOR control; nonempty text/color assertions. | `tests/test_tui_terminal.py::_collect`, reader/error/harness environment. | `test_no_color_env_suppresses_ansi_color_codes`, `test_pty_harness_capture_never_returns_empty_bytes_on_a_successful_run`. Harness present. | Final focused/full execution must clear inherited NO_COLOR after uv environment construction. |
| U10 | Five forms expose four ownership kinds; canonical/non-secret derived IDs; opaque user/agent; renewal preserves ownership. | `src/rush/dashboard/application.js::buildOwnerScopeControl`, `buildActionForm`, session state; M08 validation. | `tests/test_dashboard_projects.py::test_all_five_memory_actions_expose_owner_kind_and_id_control`, UUID/opaque/session/renewal selectors. Full module now passed. | Pair JS forms with real server rejections and native visible mutation flow; no browser completion claim. |
| U11 | JSON-object guidance/validation, zero POST for invalid input, exact write/promote source kinds, valid edit/archive flow. | `src/rush/dashboard/application.js::buildActionForm`, `ACTION_FORMS`. | `tests/test_dashboard_projects.py::test_malformed_or_non_object_content_sends_no_post_request`, exact source-kind and revision-sequence selectors. Full module now passed. | Stubbed response revisions do not prove persisted DB revisions; pair real memory-public tests and native browser flow. |
| D01 | User guide/cookbook accurately describe persistent TUI and read-only non-TTY status, security, gain and recovery. | `docs/USER_GUIDE.md`, `docs/CLI_REFERENCE.md`, `docs/CLI_COOKBOOK.md`; `src/rush/cli.py::ui_cmd`. | Root corrected stale check-suite claims. Existing `tests/test_phase70_t28f.py::test_ui_json_non_tty_never_runs_check_suite`, plain non-TTY counterpart cover runtime. Current changed paragraphs reread. | Final docs parity and changed-subject verification required; prose is not journey evidence. |
| D02 | Public references accurately cover ownership, aliases, operation identity and implemented boundaries. | `docs/MCP_REFERENCE.md`, `docs/CLI_REFERENCE.md`, `docs/ARCHITECTURE.md`; `scripts/sync_docs.py::check_docs`. | Ownership/aliases present; root reconciled historical M12 with current U05 limitation in architecture. `tests/test_sync_docs.py` contract/default/history checks exist. | Checker does not prove semantic accuracy. Current targeted document receipts and final docs gate required. |
| D03 | Current index/status/evidence agree; historical facts preserved; no partial/excluded/non-green completion. | `docs/phase-plans/README.md`; Phase 69 report/receipts; this current restart evidence. | Root replaced false nonexistent-T29-evidence claim; `tests/test_sync_docs.py::test_historical_claim_retains_text_and_current_link` verifies preservation rule. | T054 exclusion/non-green status retained. Phase 70/G7 remain unaccepted until actual final gates and journeys complete. |

#### Required remaining work; original scope retained

1. Finish current M10 project-filter correction and T24 shared dashboard reviewed
   concrete package identity binding; freeze and independently review affected
   bytes. Production Aislop dependency attribution remains unresolved and
   stopped under current CI/full-gate priority; fixture success does not remove it.
2. Execute final G7 on final frozen source/tests/lock/docs: full pytest including
   slow, lint, format, `mypy src/rush`, documentation parity, whitespace and
   dependency audit. Four repaired selectors do not convert baseline to PASS.
3. Rebuild and probe wheel, sdist and frozen executable against upgraded lock;
   record final provenance, digest/assets, arbitrary-cwd and installed behavior.
   Older G5 artifacts are historical diagnostics, not final artifact acceptance.
4. Run existing Linux/Windows CI on final revision and record URLs, conclusions
   and exact revision coverage, including nine native Windows ownership cases
   and console/action/recovery requirements. No separate native machines are
   requested by current owner direction.
5. Complete remaining R01–R12/G6/G8 user outcomes: isolated install/setup,
   registered-project setup→scan→agent→rescan, macOS terminal/recovery,
   Claude Code/Codex consent/readback/restoration and feedback/continuation,
   plus native browser export/handoff/ownership/pulse/readiness evidence.
   Cursor remains superseded by owner amendment §3.3. Final independent review
   must reconcile T1–T29, T28-A–F, all 51 rows, permissions, recovery and assets
   before any Phase 70 acceptance or final handoff claim.

#### Native documentation write and verification receipt

This lane changed only this report (append-only),
`docs/phase-plans/phase-70-restart-checklist.md`, and targeted entries in
`docs/reports/phase-64-66-documentation-coverage.md`. The report's prior
27,355 bytes retain SHA-256
`f8b03e5d07490198bfbb03b959503406aa3dd23c139f506d4e3ffb33774027e0`.
All 51 row identifiers appear once; 53 explicitly file-qualified existing
test selectors resolve to actual test definitions. These checks establish
preservation/inventory/reference validity, not behavioral acceptance.

Existing `scripts/sync_docs.py` receipt/digest helpers refreshed 13 changed
document entries, including root's USER_GUIDE, CLI_REFERENCE, CLI_COOKBOOK,
ARCHITECTURE, phase index, CI/testing/release guidance and Git truncation guide.
All 437 unrelated entries and the runtime-contract payload remained unchanged.
Prior lane receipts remain; new targeted receipts state affected-hunk review
honestly rather than claiming a new full read of every referenced document.

Executed documentation check returned
`Documentation coverage and runtime contracts match.`; owned-path
`git diff --check` passed. Exact check:

```sh
rtk proxy env -u PYTHONPATH uv run --frozen --no-sync --python 3.12 --extra dev python scripts/sync_docs.py --check
```

This establishes current documentation parity only. Later edits invalidate its
subject; final G7, rebuilt G5 provenance, native CI/browser/host journeys and
independent final acceptance remain required.

#### Latest coordinator checkpoint before final documentation receipt

These observations supersede only the earlier M10 correction-in-progress
status; they do not turn baseline G7 or Phase 70 into PASS.

- M10 canonical handoff selection now explicitly requires each handoff's
  `project_id` to equal canonical registered UUID. Actual RED was 3 failures
  in 0.73s; GREEN was 93 passed, 1 deselected in 27.11s, covering by-kind totals,
  ratio/dollar values and selected IDs. Portability lane independently reviewed
  final frozen M10 packet read-only and returned PASS. Final all-source gates
  and native journeys remain required.
- T24 existing positive HTTP selector now asserts actual setup identity is
  `frozen_review`. Actual RED was 1 failure in 0.55s with
  `resolved_at_apply`; bounded four-file production correction is in progress.
  Shared dashboard concrete identity remains Phase 70 scope, not Phase 71.
- Native Windows fixture preparation found `_observe_owner_windows` opened
  mutex with `SYNCHRONIZE` alone, insufficient for `ReleaseMutex`. Root changed
  access mask to `0x00100001`; existing five local cases passed in 0.34s.
  This edit supersedes prior S03 frozen review subject and requires final
  independent review. Nine native Windows ownership cases remain unmet and
  belong in existing Windows CI.
- Coordinator verified current Claude Code 2.1.285 and Codex CLI 0.159.0
  version metadata only. No host configuration write or native adoption,
  consent, model feedback or continuation acceptance follows from versions.

Subsequent S03 observer-rights packet independently passed read-only review at
`src/rush/dashboard/state.py` SHA-256
`e87c314dfdd95fab6bd8588e3f301ae918deecfb7035206112fd2d9926eae1c0`.
Prepared native module locally passed two import checks and deselected ten
Windows-only cases; the nine original native ownership requirements remain
unmet until actual Windows CI execution. Existing CI selection coverage is
being reconciled; no workflow write or CI conclusion is recorded here.
Root's ARCHITECTURE clause now distinguishes passing production-JS U05 sequence
validation from unmet native browser acceptance. Final documentation receipt
remains provisional pending that CI-selection decision and final subject.

CI-selection decision now recorded: coordinator extended the existing Windows
contracts command by one line to include `tests/test_windows_import_safety.py`
and exact selector
`tests/test_dashboard_http_contract.py::test_windows_owner_mutex_wait_results_fail_closed`.
Same job, runner, triggers and build steps; no separate native runner added.
This selects prepared native ownership cases under current owner direction;
actual Linux/Windows execution still requires the new CI head, URLs and
conclusions. Targeted documentation receipt can now be frozen for this
checkpoint while T24 source correction continues. This is not phase acceptance.

## Restart integration checkpoint — 2026-10-03, T24 review and open native packets

This append supersedes earlier in-progress T24 observations without replacing
historical evidence. All pre-append 64,200 bytes remain unchanged; the original
27,355-byte historical prefix remains unchanged. This checkpoint does not
claim final G7/G5/CI/G6/G8 or whole-phase acceptance.

### T24 shared frozen provisioning — implemented, independently reviewed

T24 remains Phase 70's shared dashboard contract. Actual HTTP regression
reproduced `resolved_at_apply`; corrected scan-actions lane passed 42 tests in
25.22s. Independent read-only review passed with these four hashes unchanged
before/after review:

- `src/rush/dashboard/server.py`: `97ba069d4488cd0147b200570826a7309c1e3771a6bacbaf4a409d7173c96ecf`.
- `src/rush/dashboard/application.js`: `afed3ae80ea17939ef43e9742e6dbb44e9c1ea65efefd7a5561d7bc66e4957bb`.
- `tests/test_dashboard_scan_actions.py`: `87a6c714969aeda8cd7eb52640560f5b9296c717e0809635699e84ca3a19f6cf`.
- `tests/test_dashboard_projects.py`: `14ffc3f87d106ca6ad71e2a3fcbd117aa21cb86cf785decb9ffa512399498fb8`.

Reviewed producer/consumer uses `build_setup_review` and `apply_setup_review`;
explicit network resolution yields a second frozen review. Root/data/platform,
canonical project identity, grants, plan/hash and stale state bind acceptance
and worker execution. Shared apply validates again under setup lock. Actual
HTTP case reviews Ruff 0.6.9, changes upstream latest to 0.7.0, then verifies
exact command `uv tool install --force ruff==0.6.9` and frozen manifest identity.
Manager failure remains failed, without an applied manifest. Durable 202,
S04 effect reservation/replay, M10 scoped read-only telemetry and U05 binary
download invariants remain in reviewed source. Phase 65 `scan_plan` metadata
staging is distinct from setup effects and remains allowed by its contract.

Evidence limit: stale-worker fixture exercises conflict return but does not
explicitly assert disk-byte stability; source review verifies rejection before
apply. This limited packet PASS is not final integrated/native acceptance.

### S03 Windows ownership — local correction evidence, native acceptance open

Identity-query correction distinguishes confirmed absence (Windows error 87)
from failed/ambiguous observations (including errors 5, 0 and 6). Failed
queries retain durable records; actual handle declarations and error capture
before close reviewed independently. RED: 4 failed/3 passed in 0.50s. GREEN:
40 subprocess/owned-data tests passed in 8.45s; Ruff/format/whitespace passed.
Independent frozen runtime review passed on:

- `src/rush/runtime/subprocesses.py`: `475d1b2588af4ea777fc4eb33853601b111895d96e504846d843a3fbb0fcd362`.
- `tests/test_subprocess_contract.py`: `48eb5e301043290954f95f57577ab89862f634cd5ee7015bb72c0a78b663ad04`.

Prepared native module `tests/test_windows_import_safety.py` hash
`a166d636a5d040751a37d285fa2049140ad5b3a7a540b806c9489f4c6a6a6946`
locally passed 2 import cases with 11 Windows-only cases deselected; local
static checks passed. Added case uses real DACL access denial, retains record
and observes actual zero-process query. Its independent review and actual
Windows CI remain pending at this checkpoint. Mocked wait/query regressions
do not prove native kernel behavior. All nine ownership scenarios plus U01
native console/recovery remain required through existing Windows CI.

### Public native-plugin hook disable — implemented packet, callback defect open

Public JSON CLI fixture reproduced duplicate manual registration beside an
installed plugin: 2 failed in 3.37s. Guard correction passed 2 focused cases
in 2.82s and 87 affected regressions in 31.92s; static checks passed. Prior
frozen hashes:

- `src/rush/tools/agent_connection.py`: `781dfddaced79ca4fbe9d7c5aba7a9a8650b3e1eafdb6f47938d51902e55de6e`.
- `tests/test_phase70_t7.py`: `9e27f72c15174595cc0ca8877f12bebe77a998718c5cd512a93c9262893aac6d`.

Independent review then found P1: guard silently drops explicit
`confirm_guidance` callable; JSON-only fixture misses interactive behavior.
Callback correction, affected regressions and new frozen review remain pending.
No final hook-review PASS claimed. Actual Claude Code/Codex plugin/model hook,
timeout, disabled-feedback and disconnect/restoration acceptance still require
final artifact plus documented preview/consent. Cursor requirement superseded
by owner amendment; no Cursor gap claimed.

### Remaining gates and documentation scope

Checklist retains bounded next packets: callback correction; native S03 review
and existing CI; final integrated freeze/full G7/docs and G5 rebuild; actual
Claude Code/Codex G6/G8 journeys. Production Aislop attribution remains stopped
under CI-priority correction and unresolved. Full pytest includes slow tests,
`TERM=xterm-256color` and inherited `NO_COLOR` cleared after `uv run`.

This documentation integration refreshes only 13 existing targeted receipts;
437 unrelated document entries, prior lane receipts and runtime contracts are
preserved. Digest/parity checks verify this documentation snapshot only. Later
source, tests, lock or documentation changes invalidate final integrated gates.

### Same-day callback/native cleanup follow-up — superseding pending review status

Coordinator independently reviewed final hook correction with hashes unchanged:

- `src/rush/tools/agent_connection.py`: `73305502c1597c886b1d1d177f255e2c8f5d8180bbf0960c3f3376d71ffe459a`.
- `src/rush/cli.py`: `14221f2f90dc72d958bf882edcdb6937f6406c2149a281e824550a02317c685b`.
- `tests/test_phase70_t7.py`: `dd37723da7410aa95248aa2710221ccae7e1ab4ae7c3e6bde527df3331a79a18`.

Shared fast path now requires `confirm_guidance is None`. CLI omits implicit
callback only for installed-native-plugin disable-only requests without explicit
intent. Explicit shared callback and nonnative interactive prompt remain intact.
Writer reproduced missing explicit preview, then missing interactive prompt;
final focused selection passed 6 cases. Affected lane passed 99 before final
added nonnative test; final focused 6 covers that addition. Ruff/format/whitespace
passed. Coordinator's final frozen source/test review passed; actual native G6
acceptance remains unmet.

Native DACL fixture cleanup corrected with exact `try/finally` restoration.
`tests/test_windows_import_safety.py` final hash
`de8e8cb68f5be962c9f2417c810f803ea145b13afecfb0c00d0e510bd6ab9797`;
2 local passes/11 native deselections in 3.21s and static checks passed.
Coordinator independently reviewed cleanup source. Actual Windows kernel,
ownership and console acceptance remains pending existing CI.

## Required static gates and installed-terminal acceptance scope — 2026-10-03

Required G7 static subset executed once with Python 3.12.12, all exit 0:

- `rtk proxy env -u PYTHONPATH uv run --frozen --no-sync --python 3.12 --extra dev ruff check src tests scripts`: all checks passed.
- `rtk proxy env -u PYTHONPATH uv run --frozen --no-sync --python 3.12 --extra dev ruff format --check src tests scripts`: 938 files already formatted.
- `rtk proxy env -u PYTHONPATH uv run --frozen --no-sync --python 3.12 --extra dev mypy src/rush`: no issues in 474 source files.
- `rtk proxy env -u PYTHONPATH uv run --frozen --no-sync --python 3.12 --extra dev python scripts/sync_docs.py --check`: documentation coverage/runtime contracts match.
- `rtk git diff --check`: passed.

Frozen manifest covered `src/`, `tests/`, `scripts/`, `docs/`, `pyproject.toml`,
`uv.lock`, `.github/workflows/ci.yml`: 1,485 files, exact path/hash equality
before/after checks. `/tmp/phase70-g7-static-frozen.json` SHA-256
`bfb6964df69f271c66216f37fee57eae46f497ae7c58db0088046cb8bc0227b7`.
No environment sync, subject write, pytest or dependency audit occurred in that
verification packet. Full G7 remains unmet. This subsequent docs update and
planned installed-terminal test/workflow corrections invalidate affected static
verdicts; final integrated freeze must precede required reruns.

### Installed-terminal G8 gap and bounded acceptance inputs

Existing POSIX harness uses checkout `PYTHONPATH` and `runpy` Rush CLI;
existing real Windows console case exercises input reader/mode restoration.
These are useful source/native-input checks, not installed UI proof.
Coordinator's required correction stays inside existing
`tests/test_tui_terminal.py`, `tests/test_windows_import_safety.py` and existing
`.github/workflows/ci.yml` build-job selections. Existing quality/Windows jobs
build `dist/rush`/`dist/rush.exe`; no new runner/framework/script/release needed.

Acceptance requires exact final binary from arbitrary cwd, without checkout
import injection; executable/version/digest and native platform/terminal
identity; real keys and screen/state observations across eight sections and
complete T28-A–F action/state matrix at 80×24, 120×40 and 60×20; resize,
grant/cancel, failure/recovery and restored terminal plus durable outcomes.
Menu/section labels alone cannot establish full matrix. G8's T26 command-count
and native CLI probes, T27 exact public routes and T29 cross-interface journey
matrix remain required. macOS acceptance is local; Linux/Windows use existing
CI with actual revision/URLs/conclusions. No installed-terminal result claimed
by this scoping checkpoint.

### Native G6 preparation — read-only status, consent still required

Preparation observed Claude Code 2.1.285 and Codex 0.159.0 authenticated.
Pre-existing user-owned manual Rush MCP entries exist in `~/.claude.json` and
`~/.codex/config.toml`, without a Rush ownership ledger. No host config mutation
or model call performed. Final-artifact conversion/instruction/hook previews,
packet consent, backups, reviewed-hash CAS restoration, readback/reload and
disconnect remain required before/after actual native acceptance. Sensitive
identities excluded from this evidence. G6/G8, final G5/G7/CI and production
Aislop attribution remain open.

## Integrated checkpoint — 2026-10-03, compact header and native-test packets

This append supersedes pending implementation statuses above only where exact
evidence follows. Historical entries remain intact. No final phase acceptance,
native G8/full matrix, full G7, current CI, final G5/G6 or production Aislop
closure is claimed.

### Compact header and POSIX terminal contract

Actual 60×20 production-header RED: 16 failed in 1.25s across eight sections
and normal/80-character project names. GREEN: 16 passed in 0.90s; full EF/TUI
lane 72 passed in 25.27s. Independent frozen review passed, hashes unchanged:

- `src/rush/tui.py`: `e1d7c91ff0e82f00121261809b4ff48a7c68282005fad56c22763c0752486f55`.
- `tests/test_phase70_tui_usability_ef.py`: `6022e667f5367266d2a04e01d60904808459a4308eece85a80ed49d7f258b556`.

Narrow header puts canonical section/size before index/name. Long names cannot
hide section/index in its three rows. Wider product/version/index/name/section
text remains identical; `_safe` literal/control sanitization and all body
loaders/actions are retained. This proves source rendering, not installed UI.

POSIX source terminal lane: 28 passed in 17.97s with cleared `PYTHONPATH`,
`TERM=xterm-256color`, frozen/no-sync Python 3.12 and `NO_COLOR` cleared after
`uv run`. Earlier inherited `TERM=dumb`/`NO_COLOR=1` failures were environmental;
no speculative capture waits remain. Final native test after exact Tab correction:
`tests/test_tui_terminal.py` SHA-256
`e503a528a406fe00ed2735a3245a2eb3e97021748235d47cf6766c1cb167454b`.

Native mode reuses existing real PTY driver, extracts/checksums installed
archive, uses isolated projects/arbitrary cwd and omits checkout `PYTHONPATH`
and `PYTHONHOME`. Actual section/domain/key/resize output, archive/binary
digests, version, exit and mode restoration form `posix-installed-tui.json`.
Tab/Shift+Tab retain beta; the traced four-pane cycle selects Map through
navigation and asserts its actual selected beta root. Failure cleanup kills
the whole owned native process group. Old G5 macOS archive debugging reached
80×24/120×40 journeys but failed missing `Scans/Findings` at 60×20. That archive
predates lock/header corrections; final rebuilt-artifact rerun is still required.

### Windows console packet and CI binding

Independent read-only review of `tests/test_windows_import_safety.py` at
`a9f552ab7a69c8903a92cfb54e9b71bb51730aeb65bd173fe3bf479496dd1a09`
found four blockers: invalid 1×1 `SetConsoleWindowInfo` rectangle; eight-section
visits only at 80×24; missing stored Memory/Tokens and other body-domain
assertions; cleanup killed only parent processes rather than the PyInstaller
onefile tree. Writer is correcting those exact defects. Real inherited
console handles, active `CONOUT$` screen reads, typed structures, bounded
retry/failure behavior and explicit key records were verified structurally.
Local two import passes with twelve native deselections are not Windows PASS.
Existing S03 ownership/denial/zero-process cases remain required in native CI.

Corrected workflow independent frozen review passed at `.github/workflows/ci.yml`
`8c84c722fbdd8358799c8ebe7a34bde11b74310340308e3f5a8dd7950fc53fb9`.
Existing quality/Windows contracts jobs bind `RUSH_G8_NATIVE_ARCHIVE`,
`RUSH_G8_NATIVE_SUMS` and `RUSH_G8_NATIVE_RECEIPT_DIR`; Linux creates the receipt
directory, PowerShell preserves pytest's `$LASTEXITCODE`, and each job requires
valid native observation JSON. Same jobs/builds/triggers/runners. Receipt
presence checks detect omitted collection; only tests' actual domain and
terminal/console assertions can verify behavior. Current CI execution pending.

### U05 latest local evidence and unresolved final review

Shared captured-artifact metadata correction was followed by five real defects
and corrections: immutable preview capture; encoded reference decoded once;
WebCrypto digest verification; preserved `grant_denied`; concurrent submit and
cancel guard. Latest affected lane: 228 passed, 1 deselected in 78.95s. Subsequent
captured-page local-name check: 3 passed in 0.90s. Mypy passed on 474 source
files; Ruff check/format, JS syntax and whitespace passed. Final frozen packet:

- `src/rush/dashboard/server.py`: `082e96ec46b3961aebd681b98c1b992337bc31b1475de0e7bb4f672df46a127b`.
- `src/rush/dashboard/application.js`: `51dcba0e03d546639c1ebe69648f967a38f94504052641cf956ee24b3bf00229`.
- `tests/test_dashboard_projects.py`: `17eb74bf0669e2b09ace79172b598ca8756914dac908b822066600f22571bd44`.

Independent final U05 frozen review and native browser two-attempt
size/hash/failure/cancel acceptance remain pending. T24/M10 and prior frozen
runtime proof remain retained; local affected checks do not replace integrated
full gates. Phase 70 estimate remains 2–4 hours if gates pass, not a deadline,
execution budget or downscope. Final G5/G6/G7/G8, full T28-A–F action/state
matrix, CI revision/URLs and production Aislop attribution remain open.

## Integrated checkpoint — 2026-10-03, native actions and captured EOF race

This append supersedes older pending/under-correction statuses only for exact
local checkpoints below. All prior 79,144 bytes remain unchanged (SHA-256
`3872a24913ca8f837eff7c24cf1539ec094ee623afe2dcd062c1beb205c70f62`),
including original 27,355-byte prefix and all historical receipts. No native,
current CI, final full G7/G5/G6/G8 or production Aislop closure claimed.

### POSIX native action assertions prepared; installed run pending

Frozen `tests/test_tui_terminal.py` SHA-256
`5f7b8e1769cc9e603852c41adbacfc53b18b8f1e3758e1230946e72be5a21052`.
Source terminal lane: 28 passed in 17.10s under explicit Python 3.12,
`TERM=xterm-256color`, cleared PYTHONPATH and NO_COLOR cleared after uv.
Native selector collection: 1 of 29 tests, 28 deselected, 0.09s. Collection used
an explicit pending-artifact path and did not execute a native artifact.
Ruff check/format and whitespace passed; frozen test hash stayed unchanged.
Independent review of these native additions remains pending.

Existing PTY harness retains checksum verification/extraction, arbitrary cwd,
Python-path isolation, isolated registered projects, three dimensions/eight
sections, focus/project selection, actual Git patch, resize and normal quit.
Overview now checks registration body distinct from header. Receipts capture
actual launch HOME/TERM/cwd/PYTHONPATH/PYTHONHOME/color/motion flags, platform,
keys as hex with timestamps, screen observations and timing/durable identity.
Added native assertions use public `ui --allow-build`, visible exact build/
cache/artifact grant review, decline with no run, approve with a real discovered
pytest engine and bounded project-test gate/PID, scoped cancel-request marker,
then exact cancelled manifest/events/visible Scans row and dead worker PID.
Malformed configuration plus F5 shows invalid status; repaired configuration
plus F5 shows valid status. Literal Unicode/control-byte bracketed paste must
not quit or start analysis. Native NO_COLOR and reduced-motion cases observe
actual color/idle writes separately. Normal quit and fresh-binary idle Ctrl-C
assert termios/cursor/alternate-screen restoration and process cleanup; wrapper
ignores only its own foreground SIGINT after spawning native Rush.

These new native assertions are UNEXECUTED until final rebuilt archive. They do
not close complete T28-A–F action/state or setup→agent→rescan/full-memory matrix;
G6-dependent real-host work and final platform evidence remain required.

### U05 EOF race corrected through shared immutable reader

Real HTTP mutation exposed one failing EOF-race case in 0.40s. Minimum shared
reader correction retains bounded requested page while hashing the same open
stream, preventing a later read from observing changed immutable bytes under
an earlier digest. Actual short reads, EOF, 1 MiB boundary crossing, size and
digest guards, both attempts across three logical paths and original preview
bytes were verified. Latest affected lane: 195 passed in 61.67s; mypy passed
474 source files; Ruff check/format passed. Independent read-only review passed
on unchanged frozen subjects:

- `src/rush/workflows/projects.py`: `41feec73bef3d4aff7570ebf9c4aebeae1a647261e66373fd6c16e62a899f511`.
- `tests/test_dashboard_projects.py`: `11cd010e141c38d6a820d811802e98af0b0504d4e3a9e28f7c1ca4099fd6e088`.
- `src/rush/dashboard/application.js`: `24a0638f9bb046dc78e16bf894247929a90a5f3dfc6da5f894c63fcf68c11804`.
- `src/rush/dashboard/server.py` unchanged: `082e96ec46b3961aebd681b98c1b992337bc31b1475de0e7bb4f672df46a127b`.

Prior canonical captured paths, immutable preview, one URL decode, WebCrypto
actual-byte SHA verification, exact grant denial and single-submit/cancel
contracts remain retained. Local HTTP/production Node DOM checks are not native
browser acceptance; final binary/browser two-attempt download proof remains open.

### Windows and CI status; no native acceptance

Latest Windows frozen packet review (`408…` checkpoint) remained blocked by
narrow header, intermediate focus and selected beta-root assertions. Writer is
correcting those defects and adding native action cases. Earlier local import
passes/deselected native cases do not accept Windows; all nine S03 ownership
scenarios and U01 console/recovery remain required through existing native CI.

Workflow SHA-256
`66097aae80bf25f051c954c094711478dc443f3caada47f669d554d449547761`
passed independent static review. Existing jobs retain archive/checksum/receipt
binding, Linux receipt-directory creation and post-uv PYTHONPATH/NO_COLOR scrub
with TERM=xterm-256color, PowerShell pytest exit guard and parsed receipt JSON
logging. No YAML parser or actual CI execution occurred in that review; no
receipt artifact upload is configured. Run URLs/revision/conclusions remain due.

Earlier M10 under-correction status is superseded by canonical-project handoff
filtering: actual 3-case RED, 93 passed/1 deselected GREEN in 27.11s and independent
final local frozen review, with modern/legacy filters, by-kind counts, ratios,
dollars and canonical handoff IDs retained. This does not imply native or full
G7 acceptance. Final integrated freeze and required gates must follow current
source/test/docs changes; G5/G6/G7/G8/CI and production Aislop remain unmet.

## Superseding native harness and public-hook checkpoint — 2026-10-03

This checkpoint supersedes the earlier POSIX `5f7b…` harness observations without
rewriting historical evidence. Current reviewed subject
`tests/test_tui_terminal.py` SHA-256
`e2da1b0dfb23ad9bbccadd700afcdc8391ccdc9b67bd5c314300d14725b6ddd7`
passed 29 source/helper cases in 17.59s; the real orphaned-descendant helper
regression passed in 0.35s. Independent read-only review verified absolute
project-root gate paths across staging, a caught launcher SIGINT handler
installed BEFORE native spawn (exec resets the caught handler in native Rush),
and owned process-group cleanup even after launcher exit. Gate release follows
exact cancelled events/manifest and worker absence. Normal quit and idle
interrupt require naturally absent process groups BEFORE forced safety cleanup.
Help Escape observes Map without retained Help text. The orphan regression uses
an actual surviving descendant with SIGHUP ignore/readiness before parent exit,
proves it alive before cleanup and requires bounded group disappearance afterward;
EPERM never counts as disappearance. These are source/helper observations, not
executed installed-binary acceptance. Independent review still rejected paired
header-only Tab/Shift assertions; coordinator is adding actual actions-focus
evidence before another frozen review.

Windows subject `tests/test_windows_import_safety.py` SHA-256
`a15d9e22815cc75682c8c18fbd44f9381d8a514666187bba43aa105b8d96fb18`
was reviewed read-only with unchanged before/after hash and valid AST. Corrected
width-aware headers, unique selected root/file, three sizes/eight actual domain
bodies, real scan gates/cancelled identity/preopened worker HANDLE and Job
assignment before native start were retained. Natural Job zero is asserted
before forced cleanup, and final zero afterward. Review remains blocked by
paired header-only focus observations, missing explicit CTRL_C_EVENT proof,
child CloseHandle pointer declaration and cursor/alternate-buffer restoration
evidence. Corrective writer owns that packet; local import passes and native
deselections do not close Windows behavior or nine S03 ownership scenarios.

Public native hook ENABLE-only route reproduced four duplicate-registration
failures; existing DISABLE cases passed four checks. Minimum shared correction
is awaiting final affected regressions and independent frozen review. New guide
sections describe actual public hook flags/cache constraints and the already
corrected native DISABLE-only route, including unchanged host registration and
CAS conflict behavior. Read-only guide subjects were
`docs/CLI_REFERENCE.md` SHA-256
`e3d09aa6794cce0d100b8ee75818ea4330974f67f3ff030e47b3bd1450430c68`
and `docs/user-guide/working-with-ai-agents.md` SHA-256
`99d766989860946349e6a47105ae818122df853aa846a66cca6a190aff1ba0d1`.
These local routes do not establish native ENABLE acceptance or authorize
real-HOME/network/model changes. Final artifact, conversion/instructions/hooks
preview, consent, backup/readback and CAS restoration remain required.

Existing CI workflow checkpoint remains
`66097aae80bf25f051c954c094711478dc443f3caada47f669d554d449547761`:
static review only, no actual CI/YAML-parser or receipt-upload evidence. All
G5/G6/G7/G8, full-memory/agent-rescan/known-and-unknown-artifact actions, native
U05 browser acceptance and production Aislop attribution remain required open
lanes. Current source/test/docs edits invalidate earlier integrated gates.

### Hook-only local result supersedes pending regression checkpoint

Native hook-only ENABLE/DISABLE shared/public correction passed 139 affected
cases in 47.96s after the actual four-failure ENABLE RED; independent read-only
review passed on unchanged `e72…` shared-tool, `45ab…` CLI and `ef98…` T7 test
subjects. Existing DISABLE behavior remains preserved. This closes that local
source/test correction only: broader native connect profile/guidance/memory
still duplicates manual registration and remains a required shared correction.
No native host/model/configuration call, final artifact or G6 acceptance follows
from these local passes. The guide subjects above remain unchanged.

POSIX paired-focus correction is pending coordinator's final frozen subject and
peer review; planned real actions cursor at widths at least 80 and Scan/decline
action at all three sizes must replace header-only evidence. Those assertions
will still require execution against the final native artifact. Windows packet
corrections and existing native CI execution remain open. This four-document
checkpoint refreshes exactly 14 pertinent coverage receipts, retaining the
other 436 entries and runtime contracts; final integrated source gates remain due.

Exact hook-only local frozen subjects:

- `src/rush/tools/agent_connection.py`: `e72ba395ca86c7296cd3b17e6344ea7cb520573286dc7744528d75d055d7b391`.
- `src/rush/cli.py`: `45ab217780bbbd5d608c375c5231f4eb940dc68d1ba17c33bf23d6f56e8509b8`.
- `tests/test_phase70_t7.py`: `ef98fa38aac1b5ccbd115c6330c5045026ce8550efd10408e6c0cc524ec36c09`.

## Native shared-connect and local Memory checkpoint — 2026-10-03

This additive checkpoint supersedes earlier statements that broader native
connect still duplicates manual registration. Shared correction selects owned
native plugin roots before registration across ordinary/guidance/resources/
memory/ack/profile requests; host configuration remains unchanged. Missing,
mutated or ambiguous evidence conflicts instead of falling back to manual
registration. Owned plugin profile migration reuses preview/consent/CAS,
journal/root-ledger digests and verified host refresh commands outside ledger
lock, with compensation. Omitted profile preserves full/extras; restricted
memory-session arguments fail before profile normalization. Journaled memory
uses exact own serialized write digest and retains concurrent edits.

Required guidance-CAS/unowned-resource transaction regression produced four
failures in 0.39s, then four passes in 0.24s after native-only conflict guards.
Both hosts retain user edits, restore owned profile/ledger/memory and avoid
host refresh on conflict. Eight affected modules passed 256 tests in 42.55s:
T2, T4, T7, T7 fixes, adoption, agent connection, install memory activation and
bootstrap install. Exact environment cleared `PYTHONPATH` before `uv`, set
`TERM=xterm-256color`, cleared `NO_COLOR` after `uv`, and selected frozen,
no-sync Python 3.12. Ruff, format, whitespace and agents-module mypy passed.

Frozen four-file SHA-256 subjects were unchanged after verification:

- `src/rush/integrations/agents.py`: `a569492882d490a79fe49393bed3baf6db9def8b9404792163e8828f181800a6`.
- `tests/test_agent_connection.py`: `909cba3b2280edecb899198ec32480e65b78cbab049e29f669b72366aaea88a7`.
- `tests/test_phase70_adoption.py`: `62404b7f35c0119bc61e17c07aadbd4a6c96419089099fb3f88cc26cd0b58ea9`.
- `tests/test_phase70_t4.py`: `9da981f1a5150e02b5289e311042f7bc87eb7c69c4cdcaf20e03a610526658ed`.

`src/rush/tools/install.py` was unchanged; existing refresh helpers reused.
Independent frozen review passed on all four unchanged subjects. Fixture command success proves
transaction/control flow, not actual same-version host cache adoption or
host-loaded profile. Native host/model continuation and full G6 acceptance
remain unexecuted.

Historical POSIX `b198…` / Windows `c0f24…` independent read-only review passed
five focus/signal/WinAPI/restoration corrections as source evidence only.
New local Memory/artifact native cases now being added invalidate final
candidate verdicts. New frozen review and final binary execution remain due.
T28-D mini-checklist in existing restart checklist covers real decoded/paged
content, related traversal, read-only per-record write/use receipts,
grant/CAS/recovery and genuinely corroborated promotion. Single-source
hardcoding currently prevents positive promotion; required source correction
and positive/negative behavioral evidence are local, without G6 dependency.

Earlier 2–4-hour estimate is explicitly superseded: no defensible ETA while
source and native acceptance remain unresolved. Approximately 25-minute full
suite is observed runtime only. All 51 requirements, full action/state matrix,
later phases and final G5/G6/G7/G8/CI/production Aislop acceptance remain intact
and open. No native/full-suite/final-artifact closure claimed.

### Local Memory source correction supersedes pending T28-D statements

The preceding single-source promotion blocker is resolved in local source:
promotion now checks real, current, matching evidence from distinct sources at
preview and apply; lone, stale and changed-source cases refuse. Expansion reads
exact stored content by version in 256-byte pages. `]` / `[` make every decoded
character and every returned related/receipt row reachable at 60×20; `x`
continues content and cached prior pages remain available. Per-record write/use
receipt reads remain read-only and bounded to latest eight per ledger, disclosed
in detail. Same-ID cross-project, owner/source/version and missing-store guards
prevent stale or unauthorized detail.

Affected local gate: 180 passed in 11.65s; Ruff check/format and diff check
passed. Independent read-only review of frozen corrected spans passed. Source
SHA-256: `tui.py` `e0103a81d05a568c50deec7a743b149bc45de1b217c8fcba64fcde70755cec6e`;
`memory/store.py` `0caea9fc34dbc6bfe88c47f1bb0d1b3e98ad073443e8ed9ca459f4e1d6eb4e23`;
`token_economy/telemetry.py` `21c0335f0c7978d3eac696992f4301e6b711d34d6e6548312a902025fcd9c913`;
`tools/memory.py` `c19f502a9cbdba2f73f3468a84d915b6de91db994e51b2a477501a3bc423bb22`.
Frozen tests: `test_phase70_t28d.py` `3d88e703b535c7eeb93e8967b0807a0e716a93a8872b79c2efc17c76e9642551`;
`test_phase70_tui_usability.py` `720979a3fb9c6eec2a5efdc86dc7ca704468cbd852359d400afc68b64c115587`.
Installed POSIX/Windows binary execution, native Memory actions and full Phase 70
matrix remain open.

### G7 fixture corrections after incomplete runs — 2026-10-03

First full G7 used `-q -m ""`; root sent SIGINT after the observed failure
(exit 2; 739 passed, one failed, 14 deselected; 120.72s): CI contract test
still expected an older command. Corrected fixture passed four
focused cases and independent frozen review (`test_ci_contract.py` SHA-256
`67dc2e626101a14ffaad1df8499f7aad989abad994f9c0d56750337e2a1abef6`).
Second full G7 used `-x` and stopped naturally on the first failure
(exit 1; 952 passed, one failed, 14 deselected; 183.29s): dashboard user
journey wrote real 100→40 token telemetry with no
`project_id`, which stores it as unscoped, then asked HTTP for the registered
project's scoped totals. The shared reader correctly excluded that event.
Journey fixture now supplies the registered canonical project ID and asserts
exact HTTP totals: 100 raw, 40 sent, 60 saved, one event; foreign and unscoped
rows remain excluded. Fifteen focused journey cases passed. No production
telemetry or dashboard source changed for this fixture correction. Frozen
subjects: `scripts/benchmarks/run.py`
`0411d5d6cd2e352e19d2723da644e70be6e17ec9b1446fe7a11e83c6a068240e`;
`tests/test_dashboard_user_journey.py`
`7b8f89c92080b60b62713967e75488af65bf1e41249848c5689992fa670b297a`.
Neither run is full G7 PASS. Final integrated G7,
installed/native/CI and remaining Phase 70 acceptance remain open.

### Installed acceptance corrections — 2026-10-04

Later full G7 stopped on real failures after 2,946, 4,976 and 5,201 passes;
the last natural failure took 647.14 seconds. Subsequent runs were interrupted
after 1,751 and 1,929 passes when native acceptance exposed new defects.
None is a full G7 pass. Final G7 is held until the required installed journeys
pass; fixture repairs and focused checks do not close this gate.

Actual native acceptance exposed clipped action focus, an F5 refresh lost
while a section load was pending, and failure to cancel an active pytest
child. Focus visibility and refresh use existing TUI paths; shared project
execution now enters the existing subprocess cancellation scope. The real
blocked pytest/descendant regression verifies both processes terminate and the
durable attempt becomes cancelled before releasing its blocking fixture.
The strict native journey subsequently passed that cancellation step.

Native dashboard packaging omitted `application.js` and `project_map.js`.
The existing CI, release and test PyInstaller commands now collect
`rush.dashboard` data. Clean artifact probes and public HTTP checks returned
200 with exact source bytes for both assets in rebuilt packages. Existing
installed CLI journeys also exercised real failing pytest, repair, rescan and
resolved-finding comparison; missing engines retain truthful incomplete
outcomes. These checks do not establish real Claude Code/Codex adoption.

Latest completed build: `/tmp/rush-phase70-memory-markers-fixed-8z4k2n1w`,
archive SHA-256
`8cd53347f6a26ca817e2f4f42dafe86d658f9b808779da5ac32aec61215e5d91`.
Its clean artifact and exact dashboard asset probes passed with unchanged
1,487-file build manifest
`864b81e62fbf01d9d13d6462976d86740ac468c258dcc68103ca829d1c6cce28`.
The strict native run in `/tmp/rush-phase70-native-markers-fixed.X7bh3g`
failed after 35.29 seconds at the owner-scope acknowledgment. Pagination,
literal checked cells and owner form cycling had passed; the owner change
applied, but a previous section's `declined` message hid its acknowledgment.
Explicit Memory entry now clears that prior status, preserving priority for
later global errors/cancellation. The real-state regression and adjacent TUI
tests passed (94 cases), followed by independent frozen review; installed
acceptance against this correction remains open. Frozen source/test hashes:
`tui.py` `a3c7fdd845da03e73562b3e9de7a7d840ad11c7236abc8158025710ef42299e0`;
`test_phase70_t28d.py`
`47fa34d681245328ad85f59540d071970f903e45441cfb85d19ff24f7dae035e`.

Actual browser acceptance on the same native archive reached the artifact
form after reauthorization. At 741×680, inspector content was 1,901 pixels
high inside a fixed 624-pixel panel without scrolling; the submit control
remained below the viewport, and wheel input did not move it. No downloaded
artifact bytes were verified. The required mobile scrolling correction and
subsequent browser acceptance remain open. Both drawers also remained open;
that observation alone does not establish a separate keyboard defect.

Final native three-size journeys, browser export/failure/cancel cases,
responsiveness/motion, full G7, current Linux/Windows CI, real host adoption
and continuation, production dependency attribution and final documentation
review remain open. Later restart-plan phases remain required and unstarted.

The next combined archive, SHA-256
`126543de1a152bd61eb675f43267ec848028de7ca0317fbaef530024563c88ef`,
passed clean artifact and exact dashboard asset probes with unchanged
1,487-file manifest
`0d093132d4e964fc694838c2185ea3af852a363fbca855eb4d02659c81e8b962`.
Actual mobile scrolling now moves the inspector to scrollTop 1,291 and
places the submit button at y=644 inside the 680-pixel viewport. A granted
export reports `downloaded 2097160 of 2097160 bytes`; the browser download
event timed out, so no filesystem digest or completed U05 acceptance is
claimed. The strict native journey advanced past owner acknowledgment, then
failed after 39.06 seconds during genuine Memory expansion:
`Unknown encoding cl100k_base. Plugins found: [] tiktoken version:0.14.0`.
Retained evidence: `/tmp/rush-phase70-native-ownerack-fixed.X0sMOR`.
The required frozen-package plugin correction remains open. Do not replace
real expansion/token computations with a fallback to close this gate.

Tokenizer plugin collection now uses `--collect-submodules tiktoken_ext` in
the existing CI, release and native-test PyInstaller commands. Ten focused
CI/artifact cases passed, followed by independent frozen review. Native
archive SHA-256
`819f68732e51d668d1fb881947b0d9cccbf1c588a727e3387921ba5eb9cce5f4`
contains the real encoding plugin; its clean artifact and exact dashboard
asset probes passed with unchanged build manifest
`eb524b2d47b98b591c1badfd9b06da2bed65458989e5614c3a9e18ccbda05b30`.
Python 3.12.12 uses locked `tiktoken` 0.14.0. The existing public BPE cache
matched the installed package's expected SHA-256
`223921b76ee99bde995b7ff738513eef100fb51d18c93597a113bcffe865b2a7`;
no download or fallback was used. This is an explicit cache condition,
not a cold-empty-cache offline guarantee.

Actual installed-native Memory expansion passed on this archive. The strict
journey then failed after 39.81 seconds at conflict refresh: a deliberate
external edit produced real v2 content `NATIVEEXTERNAL`; the approved write
correctly rejected its stale version. Refresh still searched using active
query `NATIVELONE`, so it could not find the held record whose new content no
longer matched. External bytes were preserved. Evidence:
`/tmp/rush-phase70-native-tokenizer-fixed.LNzoEs`. Correcting held-ID refresh
while retaining canonical owner boundaries, typed draft and CAS re-review
remains required; full native/G7/CI/host/browser acceptance is still open.

### 2026-10-04 held-record refresh and exact terminal content

Held-ID refresh now reads the canonical record independently of the active
search query, preserving owner boundaries, the typed draft and CAS re-review.
Real external-query regression passed with 92 focused cases; independent
frozen review passed. Subsequent installed-native runs exercised conflict
refresh, explicit re-review, edit, archive and create successfully.

Strict native collection exposed two distinct page issues. The collector
incorrectly treated the 256-byte response budget as 256 raw content bytes;
it now derives actual displayed ranges from independent original fixture
bytes, retains contiguous coverage and exact UTF-8/marker assertions, and
rejects shifted/tampered ranges. Production then displayed the terminal
continuation sentinel as the page end (`bytes 447..None`). Production now
stores the end as returned offset plus the actual decoded chunk byte length,
while retaining `next_offset=None` for completed continuation. The existing
real multi-page Unicode regression failed before the fix, then 62 cases
passed in 3.90 seconds. Ruff, format, whitespace, mypy over 474 source files
and independent frozen review passed.

Frozen subjects: `src/rush/tui.py`
`249d775dce4ca4e3a2e63e7a93cd18a7701bee2e31b16f8d00efd9f3325ab9a3`;
`tests/test_phase70_t28d.py`
`666ccb1aaf7fd948695f8bce49d786d61e80e3e88fa80d319812ba0d36757e7a`;
POSIX driver `bea824142cd9083e8c50c58131d73e6dc196d14ae1e278d35209622bfd52ef46`;
shared collector `b730ff90e4f92cc4184784a0382555d12e33ae5370ab061898a3af1e49d418ea`.
Rebuilt archive `/tmp/rush-phase70-final-page-fixed-u73x9k2m/dist/rush-darwin-arm64.tar.gz`
has SHA-256 `993a5a1a137f2373d8f5bb427666da66a7ce401d50f50df92f30914e0ae114e8`,
35,854,988 bytes and version 0.3.0. Existing wheel/sdist/native G5 probes and
actual public HTTP 200/exact-byte checks for both dashboard JS assets passed.
The 1,487-subject build manifest
`a6038f7572d2540b9caade8523c84657b6b05c5688fbbbf0499c3bfafcbeff21`
had zero before/after drift.

Actual strict native run passed exact final-page content, multibyte markers
and cached forward/back navigation, then failed after 21.08 seconds while
checking maintenance persisted state. Its frame still showed pending apply;
the driver had matched the prior `promotion_sweep:` preview before async
completion. Evidence: `/tmp/rush-phase70-native-finalpage-fixed.wjQMiZ`.
Correct completion waiting and the unchanged exact stale/expired assertions
remain required. This is not a full three-size native pass.

Actual Chrome export of captured attempt 1 text reported
`downloaded 2097160 of 2097160 bytes` and rendered an `out file.txt` Blob link.
Automation's download event/path did not complete; browser policy rejected
its downloads page. Saved-file SHA-256 remains unverified. Browser, full G7,
current Linux/Windows CI and real host gates remain open. Later restart-plan
phases remain required and unstarted.

### Current native candidate and G6 consent packet — 2026-10-04

Current candidate archive SHA-256:
`10947f5b5d11d4adf4dd2f7e734d590d72aea38721c3e96e4e45a5043812c36b`;
executable SHA-256:
`ad6e44b20345d75bb1267bd9d7da8d11745828d450acc48a56dccc61bb79928a`.
Existing G5 wheel/sdist/native import, native MCP and exact dashboard asset
probes passed. Production TUI SHA-256:
`f2e3b745571648ef44c941276b24245f2e9dfc26cde8d3cc5fb473c9e4659d49`.

Maintenance now checks actual apply completion and a genuinely changed source.
Artifacts details remain visible at compact sizes; 44 focused cases passed.
Narrow footer preserves selected disabled-action reasons; 33 focused cases passed.
Independent frozen reviews passed. Strict native 80×24 and 120×40 journeys
passed. Latest 60×20 journey passed resize, then failed because the skill ID
`native-skill` is clipped in its table cell. Its next check must use selected
record details for exact identity without weakening skill filtering.
Native transcript: `/tmp/rush-phase70-native-resize-fixed.GvN7yD`.
No all-three-size PASS, current full G7 or current CI result is claimed.

G6 real-home writes require the explicit preview/consent rule in the Phase 70
plan's acceptance decisions. The following packet covers Claude Code 2.1.285
and Codex 0.159.0. The §3.3 owner amendment supersedes Cursor and every
three-host requirement; G6 requires Claude Code and Codex CLI only.

1. Back up these two original files privately, preserving bytes and modes.
   Remove only their unowned manual Rush MCP entry through the existing
   conversion helper; preserve every non-Rush setting:
   - `/Users/jamesdsizemore/.claude.json`, mode 0644,
     before SHA-256 `f9aec9c5d45d938503b81e6d4fec31c7a4a7dea14552ce20540c91fae5ec83f8`;
     preview removes `mcpServers.rush`, 200 bytes.
   - `/Users/jamesdsizemore/.codex/config.toml`, mode 0600,
     before SHA-256 `e0c0c2efdd25da79273c585ac907316fd5c16e51723db45752c1ff9c94729c31`;
     preview removes `mcp_servers.rush`, 120 bytes.
   Both entries currently invoke
   `/Users/jamesdsizemore/Library/Application Support/Rush/bin/rush mcp serve`.
   Re-preview and stop on byte drift.
2. Materialize the existing native plugin templates under
   `/Users/jamesdsizemore/Library/Application Support/Rush/agent-plugins/0.3.0/{claude,codex}`,
   binding their MCP and hook commands to the reviewed candidate executable
   `/private/tmp/rush-phase70-narrow-footer-fixed-k7d2s0m4/dist/rush`.
   Use existing `materialize_agent_plugins` and
   `install_native_agent_plugin(..., consent=True)`; the latter applies
   conversion through its SHA-CAS/journal boundary.
   Actual host commands are `claude plugin marketplace add <claude-root> --scope user`,
   `claude plugin install rush@rush-local --scope user`,
   `codex plugin marketplace add <codex-root>` and
   `codex plugin add rush@rush-local`.
3. Register the empty acceptance fixture
   `/private/tmp/rush-phase70-g6-native-u73x9k2m/project` with the candidate's
   public `project add --allow-cache-write --json` route.
   Connect sessions `phase70-g6-claude-native` and
   `phase70-g6-codex-native` using public `agent connect` with this project,
   exact candidate `--rush-binary`, `--consent --install-guidance
   --allow-cache-write --allow-artifact-write --json`.
   Native plugin ownership avoids duplicate manual MCP registration.
4. Guidance adds only the following managed block to initially absent
   `CLAUDE.md` and `AGENTS.md` in that temporary fixture. The Codex block
   differs only in its opening `hosts=codex` marker:

   ```markdown
   <!-- rush:begin v=1 hosts=claude-code sha256=97f9268d2abe0477a8cf219d96928ede487390bdd81d6c9e84b1e85837fbf5e5 -->
   ## Rush

   This project is connected to Rush, a local code-quality toolbelt, through the `rush` MCP server.

   - Check code you change with Rush tools such as `rush_lint`, `rush_test`, `rush_security` and `rush_review`.
   - Each tool returns `{status, findings, summary}`. `status: skipped` means no work was performed (the engine is missing, there were no supported targets, or a permission was denied), not that the code passed.
   - Rush manages this block. Remove it with `rush agent disconnect <agent> --project <path>` instead of editing it.
   <!-- rush:end -->
   ```
   Expected complete-file SHA-256: Claude
   `24b649860d44e2d09d492fb787a2f354d2b97f5ee658da24f40f3c6e551c772b`;
   Codex `1c72c9578cc8cd81f8401948edf93473f842ba9d54577870097828b207d232bd`.
5. D3 hook activation is a separate opt-in: the same connections additionally
   receive `--enable-agent-hooks`. This writes fixture/host activation records
   in `/Users/jamesdsizemore/Library/Application Support/Rush/agent-hooks/activations.json`;
   `recovery_cache_write:false`, with no hook-result-cache grant.
   Run actual host trust/reload, granted/denied calls, faulty edit/model uptake,
   timeout and hook feedback. Then disable activations, disconnect owned fixture
   guidance/resources/memory and uninstall newly installed plugins.
   Disconnect does not restore the original manual entries: restore those
   exact backed-up entries with existing JSON/TOML upsert and SHA-CAS helpers,
   preserving concurrent non-Rush settings. Verify modes, entry digests,
   absence of owned activation and actual host readback. Stop on conflict.

Read-only conversion previews ran no host commands and changed no file bytes.
No real-home apply is authorized by this evidence entry alone. Browser saved
export hashes, complete browser/host acceptance, production Aislop correction,
current G7/CI and later restart-plan phases remain required.

### Superseding owner scope correction — 2026-10-04

Owner assigns all UI work and acceptance to Phase 71. Earlier entries' pending
terminal/browser UI gates are preserved Phase 71 inputs, not Phase 70 work or
accepted results. All task-owned UI runs stopped; latest native PID 25529 and
prior PIDs 11951/1656 were absent. Logs and edits remain intact. Exact Phase 71
plan was checked; its earlier TUI exclusion and all-gates start condition are
superseded by the additive owner amendment, retaining every requirement.
Phase 70 now closes only retained backend/CLI/MCP, engines, permission/identity,
memory, setup and real Claude Code/Codex acceptance. Existing full pytest can
run with native UI archive opt-in variables unset; source compatibility tests
and genuine installed-artifact build remain enabled. Current CI still runs UI
lanes; record those under Phase 71 without calling them accepted or deleting
their checks. Real-host G6 packet consent remains pending.

### Resource stop and resumed CI verification — 2026-10-04

Latest full G7 was stopped after the owner reported the laptop crashing:
exit 137, 44% pytest progress, five failure markers, 829.1 seconds.
Log: `/tmp/rush-phase70-g7-final-nonui-v6r8k2p1/pytest.log` (3,348 bytes).
The interrupted output contains no named traceback; neither PASS nor five
diagnosed defects is claimed. All seven owned process IDs were absent after
termination. Edits and logs were preserved.

Ruff check/format and mypy passed on unchanged 1,025-file source subjects;
mypy covered 474 source files. Earlier documentation/whitespace checks passed
before this additive checkpoint. The owner explicitly resumed execution.
Heavy suites, artifact builds and real-engine verification now run in current
CI, with no local full suite or build. Only one small mocked attribution
regression may execute serially locally; no real engine/network/child workload.
Current CI must bind an exact candidate commit, run URL, job conclusions and
logs. Transferred UI results remain Phase 71 evidence. Real-host consent and
actual host adoption remain separate, unresolved G6 acceptance.

Production attribution correction is now frozen in `engines/aislop.py` and
`tests/test_aislop_reference.py`. Known Aislop 0.16.1 unbound Python dependency
diagnostics retain their vulnerabilities, error severity and raw report,
while explicitly disclosing external-environment scope instead of claiming
the target's `requirements.txt` was audited. Genuine source paths and
FindingV1 conversion remain intact. The exact mocked selector
`test_aislop_unbound_pip_audit_preserves_external_findings` was RED in 0.20s,
then GREEN in 0.13s; independent unchanged-hash review passed. These checks
verify normalization, not actual upstream project-inventory coverage.
Source SHA-256: `a4f843086da92daf6bad8a6274d2e9edff53c0e3599d81207aaf624ac8046963`;
test SHA-256: `41fc1b3937178521031f0d45b0a288970fdd7fad2454502b1111e2c9cb6d1f97`.
Full current CI and rebuilt-artifact verification remain required.

### Current CI checkpoint and Windows diagnostic — 2026-10-04

Candidate `8341cd8e470751a39a86c6bdc3dfeb66fb30181b` completed
[CI run 37218787048](https://github.com/jamesdsizemore/rush-cli/actions/runs/37218787048)
with overall FAILURE. Five jobs passed: static real-binary acceptance,
representative Python engines, real-workload engine contracts, and installed
artifact probes on Ubuntu and Windows. Linux Quality reported 6,470 passed,
three failed and 26 deselected in 1,196.70 seconds. Its three failures are
transferred Phase 71 UI requirements: detail expansion in
`test_phase70_t28f_review1.py`, hostile artifact-path rendering in
`test_phase70_tui_usability_ef.py`, and wrapped owner-scope text in
`test_tui_terminal.py`. Later Quality steps were skipped; their acceptance
remains open. These results do not establish overall Phase 70 acceptance.

Windows runtime reported four failed and 56 passed in 106.89 seconds.
Three failures are Phase 71 inputs: dashboard asset newline parity,
F2/F3/Shift-Tab console setup, and the installed TUI journey's existing attempt
directory. Retained Phase 70 failure is
`test_windows_query_denial_keeps_owner_record`: its prerequisite query returned
handle 1124 after applying `D:P`, before owner-record retention could execute.
Neither a production defect nor the effective privilege/DACL cause is proven.

The same test now has a frozen, independently reviewed diagnostic amendment,
SHA-256 `d06587dc2a3fe6be88466407ba765a51d93a81ccef3b50514615748ad2849d65`.
On unexpected query success it reports installed DACL presence, null state,
ACE count and effective-token `SeDebugPrivilege` state. Handles close;
no privilege writes, mocks or skips were added. Genuine access-denial,
owner-retention and live-child assertions remain. Native execution of this
amendment is pending; it is diagnostic evidence collection, not a claimed fix.
Real Claude Code/Codex acceptance and a current macOS artifact remain open.
The earlier `/tmp` G7 log is historical; it is unavailable after host restart.
