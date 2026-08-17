# Task Plan: rush — agentic code-quality CLI + MCP server

## Goal

Build **rush**, a Python 3.12 CLI companion to headcleaner that ships one
agentic surface: a local **stdio MCP server** (the `mcp` Python SDK) that
exposes tools for code review, linting, formatting, testing, and security
to coding agents (Claude Code, Cursor, Windsurf, etc.). The CLI itself
also runs each tool as a one-shot command for humans.

## Next Step

Phase 4 — Tool Implementations. The skeleton is up; each tool's
`__call__` returns a stub ToolResult. Now fill them in:
- `review` → 4 heuristics + `--llm` opt-in (architecture §10)
- `lint` / `format` → engine dispatch via `tools/common.py:run_engine()` + `ENGINES` registry
- `test` / `security` → project-type detection + engine dispatch
Verify each tool end-to-end with a fixture repo before moving on.

## Current Phase

Phase 3 — Skeleton & Tooling (complete) → Phase 4 next

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
- [x] `.python-version` pinned to 3.12
- [x] `pyproject.toml` with locked deps (`mcp==1.28.1`, `click==8.4.2`, `rich==13.9.4`, `pytest==8.3.4`) + `[project.scripts] rush = "rush.cli:cli"`
- [x] Top-level `src/rush/` package: `__init__.py`, `cli.py`, `mcp.py`, `theme.py`, `config.py`, `logging.py`
- [x] `src/rush/tools/` package: `__init__.py` (registry), `base.py`, `common.py`, `review.py`, `lint.py`, `format.py`, `test.py`, `security.py`
- [x] `src/rush/engines/` package: `__init__.py` (registry), `base.py`, `ruff.py`, `eslint.py`, `prettier.py`, `vitest.py`, `pytest.py`, `pip_audit.py`, `npm_audit.py`
- [x] `tests/` skeleton: `conftest.py` (tmp_repo + skip_if_no fixtures) + `test_skeleton.py` (10 smoke tests)
- [x] CLI registers all 5 subcommands + `mcp serve`; `rush --help` renders the full surface
- [x] MCP `build_server()` registers all 5 tools with `rush_` prefix; descriptions all <200 chars; **schema is clean — `config` does NOT leak into the MCP-facing surface**
- [x] `uv sync` produces a clean `.venv/`
- [x] 10/10 pytest pass; CLI runs end-to-end
- **Status:** complete
- **Verified gates:** §5 row 1 (deps), row 7 (theme), row 8 (engine discovery in common.py), row 9 (NDJSON logging). Rows 2, 3, 4, 5, 6, 10, 11, 12, 13 verified for skeleton-level only — full validation lands in Phase 4/5/6.

### Phase 4: Tool Implementations (v0.1 — Python + JS/TS)
- [ ] `rush review <path>` — heuristics (file size, TODO density, docstrings, naming, cyclomatic smell) + `--llm` opt-in that reads `ANTHROPIC_API_KEY` / `OPENAI_API_KEY` from env
- [ ] `rush lint <path>` — `ruff check --output-format=json` for `.py*`, `eslint --format=json` for `.js/.jsx/.mjs/.cjs/.ts/.tsx`; structured `{status: "skipped", reason: ...}` when CLI missing
- [ ] `rush format <path>` — `ruff format` (Python), `prettier --write` (JS/TS + JSON/MD/YAML/CSS/HTML)
- [ ] `rush test <path>` — `pytest` for Python, `vitest run --reporter=json` (with `npm test --reporter=json` fallback) for JS/TS; detect runner from `package.json`
- [ ] `rush security <path>` — `pip-audit --format=json` for Python, `npm audit --json` for JS/TS
- [ ] Per-file language routing so mixed repos work
- [ ] Each tool returns the structured dict from `findings.md` regardless of CLI vs MCP invocation
- **Status:** pending

### Phase 5: MCP Server
- [ ] `rush mcp serve` boots `mcp.server.fastmcp.FastMCP("rush")` over stdio
- [ ] Register the same five tools as MCP tools with JSON-schema inputs and structured outputs
- [ ] Add `RUSH_LOG_LEVEL=debug` env switch that writes NDJSON to stderr (never stdout — stdout is the MCP transport)
- [ ] Smoke test: register with Claude Code / Cursor, invoke each tool from an agent
- **Status:** pending

### Phase 6: Polish & Verification
- [ ] README, AGENTS.md (mirrors headcleaner style), CHANGELOG, install scripts
- [ ] `pytest` green, `ruff check` + `ruff format` clean on rush's own source
- [ ] End-to-end test: from a fresh checkout, `uv sync && rush --help && rush mcp serve` boots and registers tools
- **Status:** pending

## Key Questions

1. **Single source of truth for tools.** Will CLI subcommands and MCP tools share one Python function each (preferred), or two parallel implementations? — Leaning shared.
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
