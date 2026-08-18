# Task Plan: rush — agentic code-quality CLI + MCP server

## Goal

Build **rush**, a Python 3.12 CLI companion to headcleaner that ships one
agentic surface: a local **stdio MCP server** (the `mcp` Python SDK) that
exposes tools for code review, linting, formatting, testing, and security
to coding agents (Claude Code, Cursor, Windsurf, etc.). The CLI itself
also runs each tool as a one-shot command for humans.

## Next Step

Task 9 is in progress. Complete developer-workflow tool documentation, then
run the full verification and scoped commit before beginning Task 10.

## Current Phase

Phase 11 — Workflow, Language & Context Expansion (Task 9 in progress)

## Phases

### Phase 1: Requirements & Discovery
- [x] Capture user-facing scope in `requirements.md`
- [x] Inventory candidate tools
- [x] Document findings in `findings.md`
- **Status:** complete

### Phase 2: Architecture & Layout
- [x] Project layout (`docs/ARCHITECTURE.md` §2)
- [x] ToolResult TypedDict + ToolFn ABC (§3)
- [x] Engine ABC + dispatch table (§4)
- [x] FastMCP server skeleton + tool-name conventions (§5)
- [x] Logging contract (§7)
- [x] `rush.toml` schema + walk-up discovery (§8)
- [x] Theme + rich style helpers (§9)
- [x] 4 review heuristics + --llm opt-in prompt template (§10)
- [x] Test categories + fixtures (§11)
- [x] All 6 Phase-1 questions resolved (§13)
- **Status:** complete

### Phase 3: Skeleton & Tooling
- [x] `.python-version` (3.12) + `pyproject.toml` (locked deps)
- [x] `src/rush/` package: init, cli, mcp, theme, config, logging
- [x] `src/rush/tools/` package: init, base, common, 5 tool stubs
- [x] `src/rush/engines/` package: init, base, 7 engine stubs
- [x] `tests/` skeleton: conftest + 10 smoke tests
- [x] CLI renders full surface; MCP build_server() registers 5 tools; schema is clean
- [x] `uv sync` clean; 10/10 pytest green
- **Status:** complete

### Phase 4: Tool Implementations (v0.1 — Python + JS/TS)
- [x] `tools/common.py:run_engine()` — C10 enforcement point (engine discovery, never hard-fail; resolves venv-local binaries)
- [x] `engines/ruff.py` — parses `--output-format=json`, maps severity, caches version
- [x] `engines/eslint.py` — parses `--format=json`, detects missing flat-config → skipped, severity mapping
- [x] `engines/prettier.py` — `--check` mode, parses "would reformat" output
- [x] `engines/pytest.py` — parses summary line, supports both pytest ≤7 boxed and pytest 8+ plain format, JSON-report opt-in
- [x] `engines/vitest.py` — `--reporter=json`, counts outcomes
- [x] `engines/pip_audit.py` — `--format=json`, correct exit-code semantics (0=clean, 1=vulns, ≥2=error)
- [x] `engines/npm_audit.py` — `--json`, robust parsing of npm's stdout noise
- [x] `tools/review.py` — 4 heuristics (file-size / todo-density / missing-docstrings / naming) + `--llm` opt-in (env-key check, Anthropic preferred)
- [x] `tools/lint.py` — extension-based dispatch (ruff ↔ eslint), aggregates findings
- [x] `tools/format.py` — extension-based dispatch, always check-only in v0.1
- [x] `tools/test.py` — project-root detection (pyproject.toml vs package.json, stops at .git boundary, 5-level cap)
- [x] `tools/security.py` — same project-root detection
- [x] Per-tool tests with skip-on-missing-engine (`test_tools.py`: 14 tests)
- [x] Per-engine tests (`test_engines.py`: 9 tests)
- [x] Base/helper tests (`test_base.py`: 15 tests)
- **Status:** complete
- **50/50 tests pass on Python 3.12.13**
- **End-to-end verified against real engines** — `rush lint/format/review/test/security` all run real tools and return real ToolResults

### Phase 5: MCP Server
- [x] `rush mcp serve` boots `mcp.server.fastmcp.FastMCP("rush")` over stdio
- [x] Register the same five tools as MCP tools with JSON-schema inputs and structured outputs
- [x] Add `RUSH_LOG_LEVEL=debug` startup logging as NDJSON on stderr (never stdout — stdout is the MCP transport)
- [x] Add `tests/test_mcp.py`: real stdio initialize → tools/list → `rush_review` + `rush_lint` calls, schema assertions, and stderr-log assertion
- [x] Smoke test: official MCP client invokes all five tools in one stdio session; every response is canonical JSON
- [x] Add `docs/MCP.md` with agent configuration snippets and the protocol/result contract
- **Status:** complete
- **Evidence:** 50/50 project-venv tests pass; review/lint/format/test return `ok` over MCP and security correctly returns `fail` for PYSEC-2026-1845.

### Phase 6: Polish & Verification
- [x] Eliminate Ruff lint and format debt from `src/` and `tests/`
- [x] README, AGENTS.md, CHANGELOG, LICENSE, and cross-platform install scripts
- [x] `pytest` green, `ruff check` + `ruff format` clean on Rush's own source
- [x] End-to-end fresh checkout: `uv sync --frozen`, `rush --help`, and the real stdio MCP integration suite
- **Status:** complete
- **Evidence:** project venv: Ruff clean, format clean, **50/50** tests passed. Python-managed temporary clone: `uv sync --frozen` completed, `rush --help` succeeded, and **46 passed / 4 skipped** (expected missing external engines).

### Phase 7: Release Maintenance
- [x] Push the Phase 6 verification record to `origin/main`
- [x] Upgrade `pytest` from 8.3.4 to 9.0.3 and refresh `uv.lock`
- [x] Declare pinned `ruff` and `pip-audit` development dependencies
- [x] Add GitHub Actions CI for locked install, lint, format, tests, audit, whitespace, and package build
- [x] Run the full local CI-equivalent pipeline: **50/50** tests, no known vulnerabilities, wheel and sdist built
- [x] Push the CI workflow and verify the remote GitHub Actions run
- **Status:** complete
- **Evidence:** GitHub Actions run `32081298431` passed all quality, audit, and build steps in 22 seconds with the Node-24 action releases.

### Phase 8: v0.2 Catalog & Routing Foundation
- [x] Read the approved v0.2 plan at `.hermes/plans/2026-08-17_164317-rush-v0-2-expansion.md`
- [x] Build and query a local Graft wiring graph under `.hermes/graft/`
- [x] Record `rtk`, context, codegraph, and Graft availability/results
- [x] Create `docs/V0_2_SCOPE.md` and update v0.2 architecture/dependency policy
- [x] Add failing catalog/result-schema tests
- [x] Create `src/rush/catalog.py` and extensible ToolResult fields
- [x] Extract deterministic routing/aggregation into `src/rush/tools/routing.py`
- [x] Convert CLI/MCP help and registration to catalog-driven behavior
- **Deliverables:** `docs/V0_2_SCOPE.md`, `src/rush/catalog.py`, `src/rush/tools/routing.py`, `tests/test_catalog.py`, `tests/test_cli_registry.py`
- **Status:** complete — v0.2 foundation verified locally; capability batches follow

### Phase 9: Static, Content & Infrastructure Tools
- [x] Add `typecheck`, `dead`, `complexity`, and `slop` tools/adapters
  - [x] `typecheck` — mypy/tsc routing and unavailable-engine coverage
  - [x] `dead` — vulture/knip routing and unavailable-engine coverage
  - [x] `complexity` — radon/jscpd routing and unavailable-engine coverage
  - [x] `slop` — sloppylint adapter plus deterministic Rush JS/TS heuristic fallback
- [x] Add `markdown`, `actions`, `yaml`, `sql`, `templates`, `containerfile`, and `iac` tools/adapters
- [x] Add Task 5 parser fixtures, normalization, and opt-in real-engine contract tests
- **Deliverables:** static/content tool and engine modules, `tests/test_static_tools.py`, `tests/test_content_infra_tools.py`
- **Status:** in_progress — Task 5 static analysis and Task 6 content/infrastructure tools complete; Task 7 supply-chain tools remain

### Phase 10: Supply Chain & Test Quality Tools
- [x] Add `secrets` and `sbom` with secret-redaction and artifact safety contracts
- [x] Add coverage and advanced test-quality tools with explicit slow/browser/network guards
- [ ] Add JSON/JUnit/LCOV/Cobertura parser fixture coverage
- **Deliverables:** supply-chain/test-quality modules, `tests/test_supply_chain_tools.py`, `tests/test_test_quality_tools.py`
- **Status:** pending

### Phase 11: Workflow, Language & Context Expansion
- [ ] Add `commit-msg`, dry-run `ci`, and dry-run `release` tools
- [ ] Add language/project routing for Go, Rust, Ruby, JVM, Swift, PHP, C#, Elixir, Dart, Scala, and Nix
- [ ] Add optional, local Graft-backed review context
- [ ] Add experimental semantic-drift adapter with opt-in execution guards
- **Deliverables:** workflow/language/context modules, `tests/test_workflow_tools.py`, `tests/test_language_routing.py`, `tests/test_graft_integration.py`, `tests/test_semantic_drift.py`
- **Status:** pending

### Phase 12: Configuration, Documentation & Release Validation
- [ ] Add generic per-tool `rush.toml` configuration and optional Python-engine extras
- [ ] Document all tool, engine, installation, and safety semantics
- [ ] Update CI with fixture-based core and representative real-engine coverage
- [ ] Run fresh-clone, package, CLI/MCP parity, local, and remote CI gates
- **Deliverables:** `docs/ENGINES.md`, `docs/CONFIGURATION.md`, `docs/TOOL_CATALOG.md`, `examples/rush.toml`, green CI evidence
- **Status:** pending

## Key Questions

1. **Single source of truth for tools.** CLI subcommands and MCP tools share the same canonical Python tool implementations.
2. **Engine coverage for v0.1.** Python-only vs Python + JS/TS? — **Confirmed: both, v0.1.**
3. **Review quality v0.1.** Rule-based heuristics only, or wire an LLM call behind a feature flag? — **Confirmed: heuristics default + `--llm` opt-in that reads `ANTHROPIC_API_KEY` / `OPENAI_API_KEY` from env.**
4. **Config discovery.** Single `rush.toml` in cwd? Or also walk up to git root? — Walk up to git root + cwd.
5. **Telemetry / logs.** Stderr NDJSON only, with redaction of obvious secrets. No remote telemetry.
6. **Companion relationship to headcleaner.** Both ship from `~/developer/`, share neon palette, but are independent repos. Should rush import anything from headcleaner? — **No.** Shared code goes to a third crate later if needed.

## Decisions Made

| Decision | Rationale |
|----------|-----------|
| Python 3.12 + uv + pyproject.toml | Same toolchain as headcleaner-cli; user is fluent |
| stdio MCP only (no HTTP/SSE in v0.1) | User confirmed stdio; zero infra, works in Claude Code / Cursor / Windsurf via command+args |
| MCP is the only agentic surface | Explicit user requirement — no SDK for ad-hoc tool registration, no daemon mode |
| `mcp` Python SDK (`FastMCP`) | Official, stdio-first, JSON-schema I/O — exact match for v0.1 |
| `click` for CLI + `rich` for output | Same as headcleaner-cli; consistent UX, no reinvention |
| Neon cyan + pink + purple palette, no red/yellow | Hardcoded brand rule from headcleaner; reuse for visual cohesion |
| One Python function per tool, called by both CLI and MCP | Single source of truth, half the maintenance |
| v0.1 ships Python-only toolchain | Ruff + pytest + pip-audit already on the user's PATH; JS/TS adds engines without proof of need |

## Errors Encountered

| Error | Attempt | Resolution |
|-------|---------|------------|
| pydantic_core import broken in Hermes system venv | 1 | Irrelevant — rush uses its own uv-managed `.venv`; will pin `mcp` resolution fresh |
| `context` command unavailable; codegraph has no project index | 1 | Used the installed `rtk` CLI and Graft's local key-free wiring graph; do not invent a context tool or index without user approval |
| `graft callers ALL_TOOLS` cannot trace module-level constants | 1 | Used `graft grep` and `graft ask` to locate registry consumers and refactor seams |
| New absent `ToolResult` fields failed FastMCP output validation | 1 | Keep v0.1 `ToolName` literal until tool expansion and annotate optional v0.2 fields as nullable (`T | None`) so FastMCP accepts omitted values |
| Combined lint/format migration patch matched duplicate status lines ambiguously | 1 | Re-read current files, added the shared collector first, then applied context-specific tool migrations |
| Ruff found an unused import in new routing code | 1 | Ran the project-prescribed Ruff auto-fix and formatter; all quality gates are green |
| Static-analysis delegation failed before edits (API connection error after retries) | 1 | No delegated changes accepted; resumed Task 5 locally from the first complete capability |
| Task 9 multi-document patch had stale CHANGELOG heading context | 1 | Read current headings and split documentation updates into exact targeted patches |
| Task 9 full quality gate reported five import-order violations | 1 | Applied project-prescribed Ruff safe auto-fix before re-running all gates |

## Notes

- Update phase status as you progress: pending → in_progress → complete
- Re-read this plan before major decisions
- Log ALL errors
- Never repeat a failed action — mutate approach
- `progress.md` and `findings.md` are co-tenants in this folder; update them every phase
