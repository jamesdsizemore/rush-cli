# Phase 67 — Cross-Agent Capability Validation & Benchmark Suite

Status: Planned. This plan validates capability the codebase already implements; it does not build
new product features. It extends the existing offline benchmark harness (`scripts/benchmarks/`) and
existing real-protocol test patterns — it does not create a second harness or a second detection
mechanism, per the constraint Phase 65 already states for this repo (§2.1 below).

## 1. Why this phase exists

`docs/reference/compatibility.md`'s "Provider continuation" section states, verbatim:

> Compatibility includes preinstalled, authenticated Claude Code, Codex, and Antigravity CLI
> profiles, `9router_cli`'s Codex-through-fixed-local-9Router route, and OmniRoute's fixed local
> OpenAI-compatible API.

Every other row in that same document's "Rush Core Runtime Matrix" table carries a `Verification
Method` column (e.g. `Python | >=3.12 | Declared in pyproject.toml, verified via uv sync`). The
Provider continuation paragraph carries none. This phase closes that gap: for each claim the repo
makes about working across multiple coding-CLI agents (Claude Code, Codex CLI, Antigravity/`agy`),
either produce real evidence it holds, or document the exact blocker preventing that evidence today.

## 2. Verified current state (drift ledger)

Every claim below was checked against the real source in this repo during planning, not inferred.

### 2.1 Phases 63-66 are complete, not planned — and their own evidence already names this phase's gap

**Correction:** an earlier draft of this plan stated Phases 63-66 were "planned, not implemented,"
copied from stale prose in `docs/phase-plans/README.md`'s preamble instead of checked against git
history. That was wrong. Verified via `git log --oneline`: commit `55e994b` "feat: complete Phase 65
and Phase 66 (project provisioning, scan/agent workflows, TUI, and web dashboard)". Verified via
`docs/goals/phases-64-63-65-66/state.yaml`'s final PM summary: "Stage 1 (MC01 + Phase 64
remediation...) and Stage 2 (MC02-MC15 + Phase 65 + Phase 66) are both fully complete, independently
re-verified by both the T999 Judge and the PM... full_outcome_complete: true." All of Phase 63's
MC01-MC15 (80 tasks) and Phases 64/65/66 are implemented and merged.

This does not weaken this phase's case — it strengthens it. Phase 65's own implementation evidence
(`docs/phase-plans/phase-65-implementation-evidence.md`, "Coverage gaps" section) already names,
verbatim, the exact gap this phase closes: "Real provider tokens / a live connected-agent session
require live network/credential access unavailable in this sandbox. The connected-agent profile in
this journey exercises Rush's own real consent/acknowledgment/isolation mechanics
(`rush.integrations.agents`) — real code, real state transitions, real isolation — but never a live
agent process or live model call. Named as an open external blocker." Phase 65's own P65-09 acceptance
test (`tests/test_project_journey.py`, 8 passing tests, real `InstallTool`/`register_project`/
`plan_scan`/`execute_scan`/handoff/rescan/memory pipeline) deliberately stops short of spawning a
real `claude`/`codex`/`agy` process — that is this phase's job, not a duplicate of it.

Separately, `docs/phase-plans/phase-65-project-provisioning-scan-and-agent-workflow-plan.md:25`: "No
second agent framework, generic scheduler, benchmark framework or automatic Git hook installation."
`:45`: "Do not install coding agents themselves." This phase follows the same constraint: every new
probe here is a new function added into the existing `scripts/benchmarks/run.py` harness the same
way P65-09's real `run_project_journey`/`run_project_journey_suite` (`:514`, `:1190`) already are —
a standalone function wired into `build_parser()`/`main()`, not the separate per-scenario
`register_probe`/`get_probe_runner` registry (see P67-06's correction, §4, for why these are two
different mechanisms) — using the existing `ProbeResult`/`Scenario`/`Outcome` contracts
(`scripts/benchmarks/contracts.py:12-118`) either way. Nothing here installs `claude`, `codex`, or
`agy` as a side effect of running tests or CI — every live-binary check is skip-with-reason when the
binary isn't already present and authenticated on the machine running it, exactly like the existing
pattern in `tests/test_phase61_transport.py`.

### 2.2 The three real cross-agent surfaces that exist today

1. **Session-resume CLI dispatch** — `src/rush/continuity/providers.py`. `provider_command(provider,
   handoff)` (`:32-76`) maps `"claude_code"` → `claude -p --output-format json --max-turns 1
   --permission-mode plan <prompt>`, `"codex_cli"` → `codex exec --ephemeral --json --sandbox
   read-only <prompt>`, `"antigravity_cli"` → `agy -p <prompt> --output-format json --sandbox
   --print-timeout 2m`. `resume_provider()` (`:392-483`) gates this behind
   `ExecutionPermissions(network=True)` and spawns it via `subprocess.run(..., shell=False,
   timeout=120)`. **Every test that exercises this path mocks the subprocess call**: `git grep -n
   "monkeypatch\|mock" tests/test_continuity.py` returns only `monkeypatch.setattr` calls
   (`tests/test_continuity.py:161,185`); `tests/test_providers.py`'s frozen contracts
   (`test_continuity_provider_resume_uses_verified_cli_contracts`,
   `test_direct_cli_resume_has_permission_gated_bounded_process_behavior`, cited in
   `docs/phase-plans/phase-61-cross-llm-memory-typed-artifact-schema-plan.md:36`) assert argv shape
   and subprocess kwargs, never a real process's real output. **This is the one surface with zero
   real-binary exercise anywhere in the test suite.**

2. **Cross-tool memory transport (3-tier dispatch)** — `src/rush/memory/transport.py`, built by P61.10
   (`docs/phase-plans/phase-61-implementation-evidence.md:361-367`, verified complete: `select_tier`
   picks native SDK → ACP → dedicated-file per tool). `pyproject.toml:43-44` pins
   `claude-agent-sdk==0.2.152` and `agent-client-protocol==0.12.1` as real, non-optional
   dependencies. `tests/test_phase61_transport.py::test_real_sdk_local_peer` (`:272-`) is **already
   better than initially assumed**: it uses `pytest.importorskip` against the *real* installed
   `claude_agent_sdk`/`acp` packages (not a mock of importability), and drives the real SDK's real
   wire protocol against a synthetic local peer process. What it does **not** do: point that peer at
   the actual `claude`, `codex`, or `agy` CLI binary (all three are ACP-tier or native-tier
   candidates per `_NATIVE_SDK_MODULES`/`_ACP_TOOLS`, `src/rush/memory/transport.py:39-42`), or run
   against a live authenticated session — the peer is a test double that speaks the same protocol,
   not the real product.

3. **MCP-client registration** — `src/rush/integrations/agents.py`. `discover_agents()` (`:509-525`)
   detects config state for Claude Desktop, Claude Code, Cursor, Windsurf, Zed, and Codex adapters;
   `apply_agent_registration()`/`probe_agent_connection()` (`:668-753`) write and verify MCP server
   registration. `tests/test_agent_connection.py` (19 test functions) and Phase 65's
   `tests/test_install_memory_activation.py`/`tests/test_project_journey.py` cover config-file
   read/write correctness and structural connection/isolation state for all six adapters (per
   `docs/phase-plans/phase-65-implementation-evidence.md`'s own "Each supported agent/platform
   combination" evidence). This validates that rush's MCP server gets *registered* correctly and that
   its own consent/isolation state machine is real — it does not validate that each tool's actual MCP
   client, once connected, gets correct tool results back over a live session, which Phase 65's
   evidence explicitly leaves as an open external blocker (§2.1).

### 2.3 What already validates real MCP-protocol behavior (build on this, don't replace it)

`tests/test_mcp.py::test_stdio_mcp_lists_clean_tool_schemas_and_calls_review` (`:206-`) already
imports the **real, official** `mcp` Python SDK (`from mcp import ClientSession,
StdioServerParameters`; `from mcp.client.stdio import stdio_client`) and drives rush's actual `rush
mcp serve` subprocess over real stdio JSON-RPC — the same transport any real MCP-speaking coding
agent (Claude Code, Codex's MCP mode, Cursor, etc.) uses. **Correction (Codex review round 1):** this
test's coverage is broader than an earlier draft of this plan stated — verified it calls `rush_review`
(`:69-75`), `rush_lint` (`:77-82`), and continuity save/restore operations (`:84-`), not just one
tool. It does not yet cover the `memory` catalog tool or a scan tool. This is the correct foundation
for agent-agnostic protocol validation; §4's P67-04/P67-05 extend it to those two tools rather than
building a parallel client harness.

### 2.4 Scanning functions

`src/rush/discovery/stack.py::detect_project_stacks` (`:40-153`) and the engine dispatch chain
(`src/rush/engines/*`, `src/rush/tools/scan.py`, `src/rush/tools/routing.py::detect_project_languages`
`:35-44`) run as plain, agent-agnostic subprocess/filesystem logic — they have no code path that
branches on which coding agent invoked them. The actual cross-agent risk is not in this logic; it is
at the invocation boundary (does a scan requested via CLI subprocess and a scan requested via an MCP
`tool_call` from a live agent session return the same `ToolResult`). No existing test compares these
two invocation paths against each other on the same fixture.

## 3. Scope

**In scope:** validating and closing evidence gaps for the three surfaces in §2.2–2.4, using only
the existing benchmark harness and the existing real-`mcp`-SDK test pattern.

**Non-goals (explicit, not deferred to an unwritten phase):**
- Rebuilding Phase 65's agent-inventory/connection/install workflow — it is already built and merged
  (§2.1); this phase consumes its real functions (`InstallTool`, `discover_agents`,
  `probe_agent_connection`, `register_project`, `plan_scan`/`execute_scan`) as-is.
- A second benchmark framework, generic scheduler, or new agent-detection mechanism (§2.1).
- CI installation of paid/authenticated `claude`/`codex`/`agy` CLI binaries — §5's P67-06 documents
  this as a local, opt-in, maintainer-run path instead, with the rationale in §6. If the user later
  wants a funded CI job for this, that is a distinct decision to make explicitly, not something this
  plan assumes.
- Rebuilding or re-verifying Phase 63/64/66's own scope (memory capabilities, runtime correctness,
  TUI/web dashboard) — this phase touches only the three cross-agent surfaces in §2.2-2.4.

## 4. Tasks

### P67-01 — Drift ledger and evidence ledger

1. **RED/discovery:** No file currently states, in one place, which cross-agent claims have real
   evidence versus mocked-only evidence. Confirmed by grep: no file under `docs/` cross-references
   `docs/reference/compatibility.md`'s Provider continuation paragraph with a test file.
2. **GREEN:** Create `docs/developer/phase-67-implementation-evidence.md`, seeded with §2.2's three
   surfaces as an evidence table (surface | file:line | current test | real-binary status |
   blocker-if-any), mirroring the format used in `docs/phase-plans/phase-61-implementation-evidence.md`.
   This file is updated by every subsequent task in this phase, not written once and frozen.
3. **VERIFY:** The evidence table has exactly 3 rows before P67-02 starts (one per §2.2 surface) and
   is never marked "PASS" for a row without a citation to a real, currently-passing test.

### P67-02 — Real-binary contract tests for session-resume dispatch

**Corrected after Codex adversarial review round 1 (2026-09-13, plan SHA-256
`9420e0174be4441f455ac3df11637d7b6ea0d94c98c4da2951175ae2db18554c`):** the original draft assumed
`resume_provider()` returns inspectable real stdout and accepts a handoff prompt directly. Verified
against real source this is false on both counts: `_run_provider_cli`
(`src/rush/continuity/providers.py:221-253`) sends the real subprocess's stdout/stderr to
`subprocess.DEVNULL` by design — a deliberate production redaction boundary this plan does not touch
— so `resume_provider()` itself can never surface real JSON content to a caller. `resume_provider()`
(`:392-483`) also does not accept a handoff dict directly; it loads one via `provider_handoff(root,
name)` from an existing named checkpoint (`:456`), returning `"skipped"`/`handoff_not_found` if none
exists. Fixed design below uses two separate assertions instead of one impossible one.

1. **RED:** Create `tests/test_continuity_live_agents.py` with
   `test_provider_command_argv_produces_real_json_claude_code`,
   `test_provider_command_argv_produces_real_json_codex_cli`,
   `test_provider_command_argv_produces_real_json_antigravity_cli`, and
   `test_resume_provider_completes_against_a_real_checkpoint` (one shared test, parametrized over the
   three providers). Each binary-specific test uses `shutil.which("claude")` /
   `shutil.which("codex")` / `shutil.which("agy")` and `pytest.skip(f"{binary} not installed")` when
   absent — matching the existing skip convention in this repo's real-binary tests.
2. **GREEN:**
   - The three `..._produces_real_json_*` tests call `provider_command(provider, handoff)`
     (`:32-76`) to get the exact real argv, then run it directly with the test's own
     `subprocess.run(capture_output=True, text=True, timeout=120)` — bypassing
     `_run_provider_cli`'s DEVNULL redirect entirely, since that redirect is production code this
     plan does not modify. Assert real exit code and that real stdout parses as the documented JSON
     shape (`--output-format json` for claude/agy, `--json` for codex). This proves the argv
     contract itself produces valid output from the real binary.
   - `test_resume_provider_completes_against_a_real_checkpoint` first creates a real checkpoint via
     `src/rush/memory/checkpoint_journal.py::save_checkpoint` with a minimal, read-only-shaped
     payload, then calls the real `resume_provider()` against that checkpoint's `name` and
     `ExecutionPermissions(network=True)`. Assert it does not raise, and that
     `ContinuityOutput.status`/`provider_route.state` reflect real completion (not `"skipped"` or
     `"handoff_not_found"`) — this proves the full production path runs end to end without needing
     to inspect its (deliberately discarded) stdout.
3. **VERIFY:** Run `uv run pytest tests/test_continuity_live_agents.py -v` twice: once with
   `PATH` scrubbed of all three binaries (all skip, with reasons printed), once on a real developer
   machine with `claude`/`codex`/`agy` installed and authenticated — confirmed available on at least
   one such machine already (§6) — where all tests actually run and pass. Record both runs' output
   in `docs/developer/phase-67-implementation-evidence.md`'s P67-02 row.

   **Opt-in enforcement, corrected twice:** round 1 found that markers alone don't stop a plain local
   `uv run pytest tests/` from executing these tests (and spending real API credit) on any machine
   with the binaries installed. Round 1's own fix (an `addopts`-level `-m` exclusion) was then found
   broken by round 2: verified directly (`pytest --help` plus pytest's documented single-value option
   behavior) that a command-line `-m` does not combine with an `addopts`-level `-m` — the last one
   wins, it does not AND them together. `.github/workflows/ci.yml:61` already passes its own explicit
   `-m "not needs_vulture and not needs_knip and not needs_radon and not needs_jscpd and not
   needs_sloppylint"`, which would silently **replace** a new `addopts`-level exclusion in CI,
   defeating it there specifically (the opposite failure from round 1: now excluded in CI even when
   binaries somehow existed there, and not excluded locally is not the risk — the risk is CI's own
   `-m` masking the addopts default, which happens to be harmless here since CI lacks the binaries
   anyway, but the mechanism itself was still misdescribed as "working everywhere"). Fix: add
   `needs_claude`, `needs_codex`, `needs_agy` to `pyproject.toml:90-98`'s `markers` list (required
   under `--strict-markers` regardless); add the same `-m "not needs_claude and not needs_codex and
   not needs_agy"` to `pyproject.toml:86`'s `addopts` for local-run default safety; **and** extend
   `.github/workflows/ci.yml:61`'s own existing `-m` expression to also include `and not needs_claude
   and not needs_codex and not needs_agy`, since CI's explicit flag is what actually governs there.
   Every live-run verify command in this plan (P67-02.3, P67-03.3, P67-04.3, P67-06.3) must pass an
   explicit `-m "needs_claude"` (or the relevant marker) override to actually execute the marked
   tests on a real machine — without it, the default exclusion silently deselects them even when the
   binary is present, which reads as "0 tests ran," not a real pass.

### P67-03 — Real-CLI peer variant of the P61.10 transport test

**Corrected after Codex review, both rounds:** round 1 found the original draft's
`status in {"ok", "error"}` assertion nearly worthless — verified: `dispatch()`
(`src/rush/memory/transport.py:126-149`) catches `Exception` broadly and converts ANY failure to the
same generic `status="error"` string by design (the exception text may carry secrets). Accepting
`"error"` as passing would let a fully broken protocol integration pass silently; fixed to require
`status == "ok"`. Round 1 also correctly separated the native (Claude) and ACP (Codex) tiers, since
`_send_native` uses `ClaudeAgentOptions(cli_path=...)` and `_send_acp` uses a separate
`acp_command` argv tuple (`dispatch:141`) — two different mechanisms.

Round 2 found the Claude half of that split (`cli_path=`) verified clean, but the ACP half does not
yet have a known real answer, **and it's two providers' worth of unresolved research, not one:**
verified `_ACP_TOOLS = {"claude_code", "codex_cli", "antigravity_cli"}`
(`src/rush/memory/transport.py:42`) — Codex and Antigravity are both ACP-tier candidates, not just
Codex; round 2 only flagged Codex. Verified `_send_acp` (`:504-537`) just forwards whatever
`acp_command` argv it's given to the generic `acp` package's `spawn_agent_process`, then performs the
ACP protocol handshake (`initialize`/`new_session`/`prompt`) — it has no Codex- or
Antigravity-specific knowledge either way. Verified `codex --help`'s real subcommand list (`exec`,
`mcp`, `mcp-server`, `app-server`, ...) contains no subcommand named `acp` or described as
ACP-compatible; `agy --help`'s real subcommand list (`agent`, `mcp`, `plugin`, `remote-control`, ...)
likewise has none. Whether either CLI's `mcp-server`/`app-server`-style mode actually speaks the ACP
wire protocol (as opposed to standard MCP, a different protocol) is an open question this planning
session did not resolve for either provider.

1. **RED:** In `tests/test_phase61_transport.py`, add
   `test_real_sdk_real_cli_peer_claude` (native_sdk tier) alongside the existing
   `test_real_sdk_local_peer` (`:272`), using the same `pytest.importorskip("claude_agent_sdk")`
   guard plus a `shutil.which("claude")` skip guard for the actual binary.
2. **GREEN:** `test_real_sdk_real_cli_peer_claude` reuses the exact fixture pattern at `:277-296`
   (`sdk.ClaudeAgentOptions` with `cli_path=`), pointing `cli_path` at the real resolved `claude`
   binary instead of the synthetic `_peer(tmp_path, ...)` fixture. Assert `transport.dispatch(...)`
   returns `tier == "native_sdk"` **and `status == "ok"`** — `"error"` is a test failure here, not an
   accepted outcome, since the whole point is proving real wire-compatibility.
3. **The ACP variants (Codex and Antigravity) are a separate, explicitly unresolved research task,
   not implemented here:** before any `test_real_acp_real_cli_peer_codex` or
   `test_real_acp_real_cli_peer_antigravity` can be written, someone must determine, per provider,
   (a) which real CLI command, if any, speaks the ACP protocol `_send_acp` expects, and (b) the exact
   argv that starts it in that mode. This plan does not guess either answer. If P67-03 is executed
   and this research resolves for a given provider, add that provider's variant using the same
   pattern as the Claude test above; for any provider it does not resolve for (no ACP-speaking mode
   found), record that as a real, verified external blocker in the evidence ledger — not a silently
   skipped test.
4. **VERIFY:** `uv run pytest tests/test_phase61_transport.py -m needs_claude -k
   real_sdk_real_cli_peer_claude -v` (explicit `-m needs_claude` override, same reason as P67-02.3),
   scrubbed-PATH run (skips) and real-machine run (passes). Record in the evidence ledger. Each ACP
   variant's status (implemented-and-passing, or documented-blocker) is recorded once its own
   research in step 3 concludes — this task's completion does not require an answer to either
   research question today, only that both be tracked honestly rather than assumed away.

### P67-04 — Broaden the real-MCP-client test to memory and scan tools, and to a real invoking agent

**Corrected after Codex review round 1, then corrected again after round 1's own fix was found wrong
in round 2 — resolved here by direct verification, not by trusting either review:** round 1 found
the original draft cited `rush_memory` and concluded it was wrong because
`register_memory_bridge_tool` only registers under a restricted `memory_session`. Round 2 disputed
that fix, citing `list_tools()` returning `rush_memory` on the default server too. Both were
half-right. Verified directly: `src/rush/mcp.py:24` generates every catalog tool's MCP name as
`f"rush_{name}"` — so the catalog's `"memory"` ToolSpec (`src/rush/catalog.py:127`) is genuinely
exposed as MCP tool name **`rush_memory`** on the default (full-catalog) server. Separately,
`src/rush/mcp.py:41-71`'s restricted-receiver path (`memory_session` set) registers a *different*
object under the *same* literal name `rush_memory` via `register_memory_bridge_tool`, exposing only
receive/expand/related/resume. **Same MCP tool name, two different handlers, depending on which
server variant is running** — round 1 was wrong to say the default server lacks `rush_memory`; round
2 was right about the name but did not flag that a second, narrower object shares it. This task uses
only the default server's `rush_memory` (backed by the full catalog's memory tool); the restricted
receiver's same-named bridge is out of this task's scope (§ below).

Also, per Codex round-1 finding 5, nothing in this plan drove an actual coding-agent CLI to
autonomously decide to call one of rush's tools through its own real, registered MCP connection.
Round 2 found the fix for this (a real `claude-code` registration) was itself dangerous: verified
`src/rush/integrations/agents.py:615-624` — when `shutil.which("claude")` succeeds, registration
takes the **native** branch, running real `claude mcp remove rush --scope user` then `claude mcp add
rush --scope user ...` against the machine's actual global Claude Code config, with no backup for
this branch (`backup_path` only exists on the config-edit branch for non-native adapters). Running
this in an automated test would destroy or alter a real maintainer's existing global `rush` MCP
registration. Fixed below to never call `apply_agent_registration()`'s native path in a test; use
`claude`'s own `--mcp-config <file> --strict-mcp-config` flags instead (verified via `claude --help`
these exist and, per their description, confine the session to only the servers in the given file,
never touching the global user-scope config).

1. **RED:** `tests/test_mcp.py::test_stdio_mcp_lists_clean_tool_schemas_and_calls_review` (`:206`)
   currently calls `review`, `lint`, and continuity save/restore (`:69-`, confirmed — see §2.3) but
   not `memory` or `scan`. Add `test_stdio_mcp_memory_write_then_read_round_trip` and
   `test_stdio_mcp_scan_tool_call_matches_cli` (both reusing the exact `stdio_client`/`ClientSession`
   setup at `:258-266`), and `test_real_claude_code_agent_invokes_rush_memory_via_mcp_config` in
   `tests/test_continuity_live_agents.py` (from P67-02, needs the real `claude` binary, marked
   `needs_claude`, same skip convention).
2. **GREEN:**
   - First new test: over the real stdio session, call `rush_memory` (the default server's real
     catalog-backed tool, confirmed above — not the restricted bridge) with a write-shaped operation,
     then a read-shaped operation, and assert the read returns what was written.
   - Second new test: call the scan tool via the real `ClientSession` and separately invoke `rush
     scan --full` as a CLI subprocess (not the default plan-only invocation — verified via
     `src/rush/cli.py:3210` that bare `rush scan` only plans, never executes engines) on the same
     fixture directory, with matching write permissions on both paths (verified via
     `src/rush/tools/scan.py:59,306` that a real `run` requires both `cache_write` and
     `artifact_write` grants). Verified via `src/rush/tools/scan.py:387-399` that the outer
     `ToolResult.findings` is always empty by design — compare `raw.data.aggregate.findings` instead,
     never the outer field, or the test proves nothing. Seed the fixture with at least one real,
     known-detectable defect first (do not compare two empty finding lists and call it a pass — an
     empty-vs-empty match proves nothing was actually scanned). Normalize run_id/attempt_id (distinct
     by design per `src/rush/workflows/project_run.py:672`) plus timestamps/duration_ms before
     asserting the remaining finding fields (path, rule, message, severity) match exactly.
   - Third new test: write a temporary MCP config JSON declaring rush's own `mcp serve` command,
     invoke the real `claude` binary with `-p "<prompt instructing it to call the rush_memory tool
     and report the result>" --mcp-config <temp-file> --strict-mcp-config`, and assert rush's own
     side (a real memory write under a known key) reflects that the tool was actually invoked — not
     just that the CLI process exited 0. This never touches the real global Claude Code
     configuration. This is the one check in this plan that proves a real agent, through a real MCP
     connection it controls, actually reaches rush's tools — every other test proves the pieces work
     in isolation, not this end-to-end path. A Codex-equivalent of this test is not included here —
     Codex's project-scoped MCP configuration mechanism has not been verified in this session and
     would need its own research before a matching test could be written; P67-06's benchmark matrix
     must show this cell as unimplemented for Codex, not silently reuse the Claude result for it.
   - This task's scope is the default catalog's tools only. The restricted `rush_memory` bridge
     (receive/expand/related/resume, `memory_session`-only) is a distinct, narrower surface with its
     own setup requirements this task does not build; naming it here as real, unaddressed scope, not
     a phantom deferral to an unwritten phase.
3. **VERIFY:** `uv run pytest tests/test_mcp.py -k "memory_write_then_read or scan_tool_call" -v` and
   `uv run pytest tests/test_continuity_live_agents.py -m needs_claude -k
   real_claude_code_agent_invokes -v` (the explicit `-m needs_claude` override is required — see
   P67-02.3's corrected opt-in mechanism; without it the default addopts exclusion silently
   deselects this test even when `claude` is installed). Record in the evidence ledger.

### P67-05 — Scanning invocation-path parity (standalone, cites P67-04's harness)

This is the direct answer to "does scanning work the same across CLI agents": since agents talk to
rush exclusively through the CLI subprocess route or the MCP route (§2.4), P67-04's second new test
*is* this check for one fixture. This task extends it to the fixture matrix already used elsewhere
in this repo, not a new one:

1. **RED:** Parametrize `test_stdio_mcp_scan_tool_call_matches_cli` (from P67-04) over the same
   polyglot fixture set `docs/reference/compatibility.md`'s "Language Ecosystem Detection" table
   documents (Python, TypeScript, Rust, Go — confirm exact fixture paths via `tests/fixtures/` before
   citing them, do not assume a path exists because the language is listed in the compatibility doc).
2. **GREEN:** No production code change expected; if any language's two invocation paths disagree,
   fix the actual divergence in the shared engine-dispatch code (not in the test) and cite the exact
   file changed in the evidence ledger.
3. **VERIFY:** Full parametrized run green; record pass/fail per language in the evidence ledger, not
   just an aggregate pass/fail.

### P67-06 — Agent-parity benchmark probe (opt-in, local)

**Corrected after Codex review round 1:** two real defects in the original draft. First, verified
`scripts/benchmarks/run.py:36-42`: `register_probe`/`get_probe_runner` is a per-scenario probe
registry (`_PROBE_MAP`, keyed `provider`/`protocol`/`privacy`/`context`/`coordination`/`local`/
`memory`), each entry a `Callable[..., ProbeResult]` invoked by `run_scenario()` with a `Scenario`
object — a completely different mechanism from `run_memory_suite`/`run_project_journey_suite`
(`argparse.Namespace -> int` functions wired directly into `build_parser()`/`main()`'s own
subcommand dispatch). `run_agent_parity_suite` must follow the second pattern, not be "registered
through register_probe" — that registry does not accept this function's signature.

Second, verified `src/rush/integrations/agents.py:114-152`: `ADAPTERS` has exactly six entries
(`claude-desktop`, `claude-code`, `cursor`, `windsurf`, `zed`, `codex`) — no Antigravity/`agy` entry
exists at all, and the IDs are hyphenated MCP-config-registration identities, not the same strings as
`provider_command()`'s underscored CLI-continuity provider IDs (`claude_code`, `codex_cli`,
`antigravity_cli`). These are two separate ID namespaces for two separate subsystems in this
codebase: `discover_agents()` reports MCP-config-registration state; `provider_command()` targets a
CLI binary directly. Antigravity/`agy` is only reachable through the second, never the first —
`discover_agents()` cannot and structurally does not report on it.

1. **RED:** Add `run_agent_parity_suite(args: argparse.Namespace) -> int` to `scripts/benchmarks/run.py`
   as a standalone function wired into `build_parser()`/`main()` (`:77-173`, `:1297-1363`) with a new
   `--agent-parity` subcommand, matching how `run_memory_suite`/`run_project_journey_suite` (`:289`,
   `:1190`) are already wired — not through `register_probe`. Create
   `tests/test_benchmark_agent_parity.py` asserting the probe's own dispatch logic (not the live
   agents) with fake `shutil.which`/`discover_agents` return values.
**Agy-specific note (independent review via `agy`, Google Antigravity CLI, this session):** confirmed
sound: `provider_command()`'s real `antigravity_cli` argv (`agy -p <prompt> --output-format json
--sandbox --print-timeout 2m`) matches real, current `agy --help` flags, and `_run_provider_cli`
already passes real `cwd=root` (verified directly against source; a competing claim that it
doesn't was checked and is false). One real, verified constraint for any *future* agy-equivalent to
P67-04's real-agent-invocation test (not attempted in this phase, same reason as Codex's ACP gap):
`agy mcp add` has no `--scope`/isolated-config flag (confirmed via real `agy mcp add --help`) and
writes to a genuinely persistent, existing directory on this machine
(`~/.gemini/antigravity-cli/mcp/`, confirmed present with real per-server subdirectories) — an
automated test using it would mutate real user state with no built-in isolation, the same class of
risk P67-04's Claude Code fix (§ above) had to work around. This is named as a real, verified
blocker for that future work, not solved here.

2. **GREEN:** Implement `run_agent_parity_suite` with an explicit provider-to-adapter mapping table
   declared in code (not inferred at runtime): `claude_code -> claude-code`, `codex_cli -> codex`,
   `antigravity_cli -> None` (no MCP-registration adapter exists — confirmed genuine architectural
   inconsistency, not a bug to fix in this phase: this benchmark's agy eligibility check will use a
   different mechanism than its claude_code/codex_cli rows, since no adapter exists to check
   consistently against). For `claude_code`/`codex_cli`,
   eligibility is CLI-binary presence (`shutil.which`, reusing P67-02's exact check) for the
   real-binary checks, and separately `discover_agents()`'s registration state for MCP-registration
   evidence — these are two different rows in the matrix, not one. For `antigravity_cli`, eligibility
   is `shutil.which("agy")` plus auth-file presence only; it never appears in an MCP-registration row
   since no such adapter exists. For each eligible provider, run three checks as one probe pass, not
   two — an earlier draft of this task omitted the second capability below, leaving the matrix
   missing one of §2.2's three surfaces entirely:
   (a) the P67-02 real-binary argv/checkpoint check (all three providers);
   (b) the P67-03 memory-transport tier check. Verified `src/rush/memory/transport.py:39-42`:
   `_NATIVE_SDK_MODULES` maps only `claude_code`; `_ACP_TOOLS = {"claude_code", "codex_cli",
   "antigravity_cli"}` — both `codex_cli` and `antigravity_cli` are ACP-tier candidates, not just
   Codex. So: `claude_code` → native_sdk via `test_real_sdk_real_cli_peer_claude`; `codex_cli` and
   `antigravity_cli` both → `not_implemented` until each one's real ACP-speaking argv is researched
   (P67-03 step 3's open question applies to agy too, not only Codex — extend that research task to
   cover both, not just Codex, before either matrix cell can show real pass/fail);
   (c) for `claude_code`/`codex_cli` only, the P67-04 scan-parity check. The P67-04
   real-agent-invocation check (a real agent actually calling `rush_memory` through its own MCP
   connection) is defined for `claude_code` only — **corrected after Codex round 2**: an earlier draft
   of this matrix implied Codex coverage for this specific capability without P67-04 ever defining a
   Codex-equivalent test (Codex's own project-scoped MCP configuration mechanism is unresearched, per
   P67-03's Codex-ACP note). The matrix's `codex_cli` row for this one capability must show
   `not_implemented`, a distinct status from `skipped` (binary present but no test exists yet) — never
   silently reuse Claude's result for it. Emit a `ProbeResult` (`scripts/benchmarks/contracts.py:43-60`)
   per provider using the existing `to_dict()` shape, mapping `ok/error` to `Outcome.PASS`/`Outcome.FAIL`
   (`scripts/benchmarks/contracts.py:12-17`), and a summary matrix (provider × capability →
   pass/fail/skipped/not_implemented) through the existing `scripts/benchmarks/reporting.py` output
   path — do not invent a new report schema beyond this one extra status value.
3. **VERIFY:** `uv run python -m scripts.benchmarks.run --agent-parity` runs to completion with
   `PATH` scrubbed (matrix is all-skipped, exit 0, not an error) and, separately, on a real developer
   machine with all three agents installed and authenticated, using the explicit
   `-m "needs_claude or needs_codex or needs_agy"` override on any pytest-based checks this probe
   shells out to (same reason as P67-02.3) — every row shows real pass/fail, not skipped, except
   `codex_cli`'s real-agent-invocation cell (`not_implemented`, per above) and Antigravity's
   MCP-registration cell (no such row exists at all, per above). Record both runs' matrix output in
   the evidence ledger.

### P67-07 — Documentation

1. Create `docs/reports/cross-agent-parity-benchmark-strategy.md`, matching the role and structure of
   `docs/reports/memory-capabilities-benchmark-strategy.md` (Decision, comparison set, existing Rush
   substrate, scenario contract, experimental protocol, metrics, acceptance targets, execution tiers).
2. Edit `docs/reference/compatibility.md`'s "Provider continuation" section to add the missing
   `Verification Method` treatment the rest of that document's table already has, citing
   `tests/test_continuity_live_agents.py`, `tests/test_phase61_transport.py::test_real_sdk_real_cli_peer_claude`,
   and `scripts/benchmarks/run.py::run_agent_parity_suite` once P67-02/03/06 land — not before. Cite
   `test_real_acp_real_cli_peer_codex` only if P67-03's Codex-ACP research (§ P67-03 step 3) actually
   resolves and that test gets written; if it doesn't, this edit states the Codex ACP tier as an
   open, documented blocker instead of citing a nonexistent test.
3. After the first real `--agent-parity` run on a machine with at least one real agent available,
   write `docs/developer/cross-agent-parity-benchmarking-report.md`, matching
   `docs/developer/benchmarking-report.md`'s structure (Executive Summary, Metrics, Subsystem plans,
   Harness architecture, Continuous baseline tracking).
4. **Already done as part of writing this plan** (both corrections landed directly in
   `docs/phase-plans/README.md` during this planning session, not deferred): Phase 67 is registered
   as a new row in the master sequencing table with prerequisite Phase 66, and the preamble's stale
   "All three are planned, not implemented" sentence for Phases 64-66 is corrected to state they are
   implemented, citing commit `55e994b` and `docs/goals/phases-64-63-65-66/state.yaml`'s
   `full_outcome_complete: true`.

## 5. Dependencies and completion

Prerequisite: Phase 66 (completed; Phases 61-66, including all of Phase 63's MC01-MC15, are merged
per `git log` commit `55e994b` and `docs/goals/phases-64-63-65-66/state.yaml`'s
`full_outcome_complete: true`). This phase validates cross-agent surfaces that already exist in the
completed codebase; it has no unmet prerequisite.

Execution order: P67-01 → **P67-02 first** (it creates `tests/test_continuity_live_agents.py` and the
`needs_claude`/`needs_codex`/`needs_agy` marker registration that P67-03's and P67-04's own tests
depend on and reuse — corrected after Codex round 2 found the original "P67-02/03/04 in any order"
claim contradicted this real file/marker dependency) → {P67-03, P67-04 in any order, each
independently committed} → P67-05 (depends on P67-04's harness) → P67-06 (depends on P67-02/03/04 all
landing) → P67-07.

**Completion requires three separate gates, not one (corrected after Codex review round 1 flagged
these as contradictory — P67-02.3 required all three real tests to pass while the original single
completion paragraph below let a zero-agent run with documented skips satisfy it):**

1. **Implementation complete:** every new test/probe file in §4 exists, passes when its required
   binary/config is present, and skips-with-reason (never silently passes, never errors) when
   absent. Verified by a scrubbed-`PATH` run per P67-02.3/P67-03.3/P67-06.3.
2. **Live validation evidence:** at least one real run on a machine with `claude`/`codex`/`agy`
   installed and authenticated (confirmed to exist, §6) has produced real `ok`/pass results — not
   skips — for P67-02, P67-03, and P67-06, recorded in the evidence ledger with real output. A
   zero-agent CI/sandbox run proves gate 1 only; it does not satisfy this gate.
3. **Documentation:** `docs/reference/compatibility.md` cites the real verification methods from
   gate 2's evidence for its Provider continuation claim — this edit happens only after gate 2 has
   real evidence to cite (per P67-07.2), not before.

Gate 1 alone is not phase completion. A documented, genuinely unavailable binary in a given
environment is valid evidence *for that environment* (matching Phase 65's own precedent for this
exact class of blocker, §2.1's citation to `phase-65-implementation-evidence.md`'s "Coverage gaps"
section) — but gate 2 still requires that real evidence exist from *some* environment, which §6
confirms is achievable, before this phase can be marked done.

## 6. Why live-agent checks are opt-in/local, not a new required CI job

**Verified, not assumed:** on the maintainer machine this plan was written on, `claude`, `codex`, and
`agy` are all already installed and authenticated — confirmed via `which claude codex agy` (all
three resolve) and the presence of `~/.claude.json` and `~/.codex/auth.json`. Exact version numbers
are deliberately not recorded here: these CLIs update frequently, and a pinned version string in a
durable plan document goes stale immediately and misleads a future reader into thinking a specific
version is expected. The point that matters and stays true regardless of version drift: this is not
a hypothetical or exotic setup — P67-02, P67-03, and P67-06's real-binary tests are runnable today, on
this machine, with zero additional setup. Their skip-with-reason path exists for any *other* machine
(a fresh contributor checkout, a CI runner) that lacks these installs, not because the tooling itself
is generally scarce.

The actual, narrower constraint this section addresses is **shared CI**, not general availability:
GitHub Actions runners are ephemeral and do not carry a maintainer's personal `claude`/`codex`/`agy`
authentication. Running these tests as a *required* CI job would mean either committing this
repository's CI budget to per-run API spend across three vendors, or storing three sets of
long-lived credentials in CI secrets for a benchmark suite — both are cost/security decisions outside
this plan's authority to make unilaterally. This repo's own `.scratch/phases-64-63-65-66/issues/06`
is a direct, on-record warning against this exact class of mistake in the other direction (naming a
blocker as "no network access" when the real, verified cause was "no published release exists yet")
— the corresponding discipline here is: name the real constraint (no CI-provisioned credentials) and
verify it, don't assume unavailability where none exists. §4's tasks are written so every real-binary
check is skip-with-reason by default in CI, and produces real evidence immediately when run locally —
including on this machine, right now, once P67-02/03/06 are actually implemented (this document plans
that work; running it is a separate, explicit decision, since it spends real API credit against
live accounts).
