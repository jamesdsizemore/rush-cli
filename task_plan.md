# Task Plan: rush — agentic code-quality CLI + MCP server

## Goal

Build **rush**, a Python 3.12 CLI companion to headcleaner that ships one
agentic surface: a local **stdio MCP server** (the `mcp` Python SDK) that
exposes tools for code review, linting, formatting, testing, and security
to coding agents (Claude Code, Cursor, Windsurf, etc.). The CLI itself
also runs each tool as a one-shot command for humans.

## Next Step

Phase 7 release maintenance is in progress. Local CI-equivalent checks and the
dependency remediation are complete; push the workflow and verify its first
GitHub Actions run before beginning package publication or v0.2 scope.

## Current Phase

Phase 7 — Release Maintenance (in_progress)

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
- [ ] Push the CI workflow and verify the first remote GitHub Actions run
- **Status:** in_progress

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

## Notes

- Update phase status as you progress: pending → in_progress → complete
- Re-read this plan before major decisions
- Log ALL errors
- Never repeat a failed action — mutate approach
- `progress.md` and `findings.md` are co-tenants in this folder; update them every phase
