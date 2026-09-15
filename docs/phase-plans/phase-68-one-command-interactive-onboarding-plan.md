# Phase 68 — One-and-Done Install

## 1. Why this phase exists

Real end-to-end testing this session (2026-09-13/14) found the actual path from "download rush" to "rush is checking my code" requires four separate typed commands, each with flags never documented anywhere a new user would find them:

```
curl -fsSL .../install.sh | sh
rush init .
rush governance sync
rush setup . --install --allow-download --allow-network --allow-build --allow-cache-write
```

Explicit requirement from the maintainer, verbatim, final: a user should only ever have to run one command (the install line itself, or `rush install` — never longer than two words) or click one button. That single action installs into the current project, activates and serves the MCP server, activates and serves all available CLIs, and activates and serves the memory system. No picker, no prompt, no second command, no wizard.

## 2. Verified current state (do not re-derive, build on this)

- `scripts/install.sh` / `scripts/install.ps1` already download the binary and hand off to `rush install --agents all --memory on` as their last line. Passing no `--project` leaves project selection "pending" today (`src/rush/tools/install.py`; confirmed by this session's own README Install section) — this is exactly the gap this phase closes, by making the current working directory the project automatically instead of leaving it pending.
- `rush setup <path> --install --allow-download --allow-network --allow-build --allow-cache-write` is the only existing path to installing missing engines. Verified working end-to-end this session (commit `e74995d`) after fixing a real bug where it failed for every PyPI-sourced engine unconditionally (`src/rush/setup/provision.py`). This phase makes that call happen automatically, with permission implied by having run the installer at all — no flag the user has to type.
- `rush ui` (persistent Rich TUI), `rush dashboard` (local authenticated web UI), and `rush mcp serve` (stdio MCP server) already exist and are already built (README's Dashboards and MCP feature groups; `src/rush/dashboard/server.py`). Nothing here needs to be built new — only wired to launch automatically.
- `rush project add <path> --allow-cache-write` (verified via `--help`) is the existing project-registration primitive `rush install` needs to call against the current working directory, with no path argument required from the user.
- `detect_project_stacks` (`src/rush/discovery/stack.py:40-153`) only checks the exact path given — no recursion into subdirectories. Confirmed this session against a real nested-app repo layout (marker files one directory below the given root produced "no detected stacks"). Because this phase has no picker, the one thing a user must still get right themselves is running the install/`rush install` command from inside the actual project root, not a parent directory — this needs to be stated plainly wherever the one-liner is documented, since there is no prompt to catch it.
- Two interactive-prompt mechanisms were researched this session and are **not used** by this design because they are unnecessary once there is no picker to drive: piping a script into `sh` cannot read `read -p` from stdin (verified twice), and piping a script into a real downloaded `pwsh` binary cannot read `Read-Host` from stdin either (verified once, portable macOS build, no Windows machine available). Recorded here only so this finding is not re-derived or re-asked about later — it does not drive any task below, since this design has no prompt.

## 3. Scope

**In scope:** `rush install` (both as the installer scripts' handoff and as the command an existing install re-runs) does everything in one shot when run from inside a project directory with no arguments: registers the current directory as the project, detects its stack, writes `rush.toml`, syncs governance rules, installs missing engines, starts serving the MCP server, connects every detected agent's CLI, and activates memory — all in the one command, no follow-up command, no prompt.

**Out of scope, explicitly not touched here:** the `--allow-*` permission-flag architecture shared by the other ~29 CLI commands (`permission_options` in `src/rush/cli_support/options.py`) — unrelated commands keep their existing flags. `rush setup`, `rush init`, and `rush governance sync` remain available as standalone commands for anyone who wants to run a piece manually or script it (e.g. in CI) — this phase makes `rush install` do all of it automatically, it does not remove the individual commands.

## 4. Tasks

### P68-01 — `rush install` defaults to the current directory as the project

1. **RED:** Add a test asserting that `InstallTool.run(project=None, ...)` — no `--project` flag passed — registers `Path.cwd()` as the project (via the same call `rush project add` already makes) instead of leaving selection "pending" as it does today.
2. **GREEN:** In `src/rush/tools/install.py`'s project-selection path, when `project` is not explicitly given, use the current working directory instead of leaving it unset.
3. **VERIFY:** Run the new test; manually run `rush install` from inside a real project directory and confirm it reports that project as active, not pending.

### P68-02 — Automatic stack detection, config, governance, and engine setup on install

1. **RED:** Extend the test suite asserting that a successful project registration inside `InstallTool.run` also (in order): writes `rush.toml` via the same logic `rush init` already uses, runs the governance-sync compiler against that project, and calls `build_provision_plan`/`apply_provision_plan` for the detected stack with permissions equivalent to today's four `--allow-*` grants on `rush setup --install` — all without any additional flag on the `install` invocation.
2. **GREEN:** Wire those three calls into `InstallTool.run`'s post-registration path, granting `ExecutionPermissions(network=True, download=True, cache_write=True, build=True, ...)` implicitly — justified because running the installer is already the explicit trust act. An undetected stack (P67's known gap) skips engine setup silently, matching today's `rush setup` behavior for an empty stack list.
3. **VERIFY:** Run the extended suite; manually run `rush install` against a real project with a real detectable stack (e.g. this repo) and confirm `rush.toml`, governance files, and installed engines all appear from that one command alone.

### P68-03 — Serve MCP and connect every detected agent automatically

1. **RED:** Add a test asserting `InstallTool.run` starts (or confirms already running) the MCP server and calls the existing agent-connection logic for every detected agent (`ADAPTERS` in `src/rush/integrations/agents.py`) as part of the same single call, with no separate `--agents` value required beyond the existing default.
2. **GREEN:** Confirm/wire this path — most of it already exists (`--agents all` is already the documented default per the current README); this task closes any gap between "agents connected" and "MCP server actually serving," verified end to end rather than assumed.
3. **VERIFY:** Manual run: after `rush install` alone, a connected agent (e.g. Claude Desktop) can immediately call a Rush MCP tool with no further setup step.

## 5. Dependencies and completion

Depends on: Phase 65 (`rush install`, `rush ui`, `rush setup`, MCP server all already implemented and shipped), this session's `e74995d` (`rush setup --install` PyPI fix) and `e03791f`/`d898178` (PATH-persistence fixes in both install scripts) — all already on `main`.

Completion requires all three tasks' VERIFY steps passing, plus one full manual run on a real machine confirming the entire experience is exactly one command: run `rush install` (or the one-line `curl`/`irm` installer) inside a project, and MCP, CLI tools, and memory are all active with nothing else typed.

This plan does not authorize implementation. Building P68-01 through P68-03 requires explicit approval to proceed, same as any other plan in this directory.
