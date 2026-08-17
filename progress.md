# Progress Log — rush

## Session: 2026-08-16

### Phase 1: Requirements & Discovery
- **Status:** complete
- **Started:** 2026-08-16 (session open)
- **Completed:** 2026-08-16 (current turn — `requirements.md` written, scope formalized, 10 hard constraints locked, 33 explicit non-goals enumerated, 6 open questions deferred to Phase 2)

- Actions taken (this phase, in order):
  - Created `C:\Users\james\developer\rush-cli\`
  - `git init -b main`, set local user.name/user.email
  - Confirmed MCP Python SDK `mcp` 1.28.1 available on PyPI; `FastMCP` is the stdio server we want
  - Asked the user about MCP transport; confirmed **stdio-only**
  - Asked the user about language coverage; confirmed **Python + JS/TS in v0.1**
  - Asked the user about `review` quality; confirmed **heuristics default + `--llm` opt-in via env keys**
  - Asked the user to clarify palette; confirmed **cyan → green → yellow** (in-use order, main→least)
  - Asked the user to clarify that "neon yellow" meant actual yellow, not pink/purple
  - Wrote `task_plan.md` (6 phases: Requirements → Architecture → Skeleton → Tool Implementations → MCP Server → Polish)
  - Wrote `findings.md` (requirements, engine matrix, output schema, config schema, decisions)
  - Wrote this `progress.md`
  - Updated `findings.md` and `task_plan.md` to reflect the user's v0.1 = Python + JS/TS and `--llm` opt-in
  - Updated palette to user-confirmed **cyan → green → yellow** (in-use order, main→least). Yellow now in (review-needed / warnings); pink reserved for failed status only; red still banned.
  - **Deep GitHub research (per user request): 14 parallel `gh search repos` queries → 1,055 raw repos → 740 categorized → 109 curated picks across 19 categories.** Saved raw/blended/curated JSON in `research/`. Identified 16 additional v0.2 tool candidates beyond the original 5. Found 6 existing MCP-server precedents that validate rush's architecture.
  - **Follow-up research: SemanticDriftDetector + more languages + more testing categories** — added `semantic-drift` tool, per-language matrix covering 20 languages, and 7 new testing-category tools (pbt/visual/snapshot/flaky/fuzz/load/contract) to v0.2 backlog.
  - **E2E + CI/CD research** — added `e2e`, `ci`, and `release` tools; total v0.2 tools now 27.
  - **Graft research** — `NanoNets/Graft` (3,096★) confirmed as rush's direct conceptual neighbor; 4 integration points defined; no code dependency.
  - **User asked "have you completed phase 1?" — honest answer was NO** (requirements.md missing).
  - **User asked for Phase 1 to be done right.** Wrote `requirements.md` (15.6 KB, 8 sections): product summary, 10 hard constraints (C1–C10), v0.1 scope (5 tools + MCP + CLI + config + output schema + logs + theme + package layout + verification + docs), 33 explicit non-goals, 13-item acceptance gate checklist, 6 open questions for Phase 2, full traceability table linking every requirement to its source.

### Phase 2: Architecture & Layout
- **Status:** complete
- **Started:** 2026-08-16 (current turn — kicked off with "go phase 2")
- **Completed:** 2026-08-16 (same turn — all 10 architecture decisions locked in `docs/ARCHITECTURE.md`)

- Actions taken (this phase, in order):
  - Reloaded `requirements.md` (15.6 KB) into context before making architecture decisions
  - **Probed the real FastMCP 1.28.1 API** in an isolated venv (`$HOME/rush-probe2`) — confirmed: `FastMCP(name, *, tools=None, ...)` constructor, `@mcp.tool(name=..., description=...)` decorator, auto-generated JSON-schema from type hints, `run_stdio_async()` for stdio transport, public methods `add_tool`, `run`, `run_stdio_async` (no `mount` in this version). No invented API surface.
  - **Verified click 8.4.2 and rich 13.9.4** in the same isolated venv — versions match the locked ranges in requirements.md §5.
  - Locked all 10 architecture decisions into `docs/ARCHITECTURE.md` (28 KB, 14 sections).
  - Resolved all 6 Phase-1 open questions in §13.

### Phase 3: Skeleton & Tooling
- **Status:** complete
- **Started:** 2026-08-16 (current turn — kicked off with "go phase 3")
- **Completed:** 2026-08-16 (same turn)

- Actions taken (this phase, in order):
  - Probed click 8.4.2 / rich 13.9.4 / pytest 8.3.4 / mcp 1.28.1 versions in `$HOME/rush-probe3` (real installs)
  - Created `.python-version` (3.12) and `pyproject.toml` (hatchling backend, locked exact deps, `[project.scripts] rush = "rush.cli:cli"`, `[tool.pytest.ini_options]` with needs_<engine> markers)
  - Built the 19-file `src/rush/` package per architecture §2:
    - `__init__.py` (version), `cli.py` (click group + 5 subcommands + mcp serve), `mcp.py` (`build_server()` + `run_stdio()`), `theme.py` (5 palette constants + rich theme + `render_result()`), `config.py` (`RushConfig` dataclass + walk-up `discover_config()` + `load_config()`), `logging.py` (`NdjsonHandler` to stderr + `setup_logging()` + redaction)
    - `tools/`: `base.py` (`ToolStatus`/`ToolName`/`Severity`/`LlmStatus` literals, `Finding`/`ToolResult` TypedDicts, `ToolFn` ABC), `common.py` (`engine_on_path`, `run_subprocess`, `skipped_result`, `error_result`, `normalize_findings`, `exit_code_for`, `now_ms`, `elapsed_ms`), 5 tool stubs (review/lint/format/test/security), `__init__.py` (registry: `ALL_TOOLS`)
    - `engines/`: `base.py` (`Engine` ABC + `EngineResult` TypedDict + `version()` + default `normalize()`), 7 engine stubs (ruff/eslint/prettier/vitest/pytest/pip_audit/npm_audit), `__init__.py` (registry: `ENGINES`)
  - Built `tests/`: `conftest.py` (`tmp_repo` + `skip_if_no` fixtures), `test_skeleton.py` (10 smoke tests covering version, imports, ALL_TOOLS count, MCP description lengths, CLI help/version, subcommand JSON output, NDJSON-to-stderr, secret redaction)
  - `uv sync` produced a clean `.venv/` with all locked deps installed
  - **Bugs found and fixed during verification:**
    1. `click.Path(exists=True, path_type=click.Path)` returned `click.Path` objects instead of `pathlib.Path` — fixed to `path_type=Path`
    2. `Path` was used in decorators before `from pathlib import Path` at module top — moved the import up
    3. `now_ms()` was returning wall-clock time (1.7 trillion ms), not elapsed time — renamed to clarify and added `elapsed_ms(start)` companion
    4. `config` was leaking into the MCP-exposed `__call__` schema — refactored each tool so `__call__(self, path, **tool_flags)` is the MCP-facing surface and `run(self, path, *, config=None, **tool_flags)` is the internal entry; CLI calls `.run()` so it can still pass config
  - **MCP schema verified clean** — all 5 tools' input schemas show only `path` + tool-specific flags, no `config` leak. Descriptions all under 200 chars (max: 181 for `rush_review`).

- Files created/modified:
  - `.python-version` (created — 3.12)
  - `pyproject.toml` (created — locked deps + scripts + pytest config)
  - `README.md` (created — minimal stub so hatchling build doesn't fail on Readme missing)
  - `src/rush/__init__.py` (created)
  - `src/rush/cli.py` (created)
  - `src/rush/mcp.py` (created)
  - `src/rush/theme.py` (created)
  - `src/rush/config.py` (created)
  - `src/rush/logging.py` (created)
  - `src/rush/tools/{__init__,base,common,review,lint,format,test,security}.py` (created, 8 files)
  - `src/rush/engines/{__init__,base,ruff,eslint,prettier,vitest,pytest,pip_audit,npm_audit}.py` (created, 9 files)
  - `tests/conftest.py` (created)
  - `tests/test_skeleton.py` (created, 10 tests, all green)
  - `task_plan.md` (updated — Phase 3 checkboxes ticked, Next Step → Phase 4)
  - `progress.md` (this entry)

- Test results:

| Test | Input | Expected | Actual | Status |
|------|-------|----------|--------|--------|
| `pytest tests/` | full suite | 10 passed | 10 passed | ✓ |
| `uv sync` | pyproject.toml | clean .venv/ | clean .venv/, 31 packages | ✓ |
| `rush --version` | (no args) | `0.1.0` | `0.1.0` | ✓ |
| `rush --help` | (no args) | renders 5 subcommands + mcp | renders all 6 (review/lint/format/test/security/mcp) | ✓ |
| `rush review src/rush/cli.py --json` | real file | parseable JSON ToolResult | parseable JSON, status=ok, duration_ms=0 | ✓ |
| `rush lint x.py --json` (no ruff) | stub | status=skipped, exit 0 | status=skipped, exit 0 | ✓ |
| MCP `build_server()` introspection | (Python) | 5 tools, descriptions <200 chars | 5 tools registered, max desc = 181 chars | ✓ |
| MCP schema inspection | (Python) | no `config` arg visible | zero `config` fields across all 5 schemas | ✓ |
| stderr NDJSON logging | `log.warning("hi")` | one JSON line on stderr, none on stdout | one line on stderr, zero on stdout | ✓ |
| Secret redaction | `log.error("api_key=sk-12345")` | REDACTED marker, no key value | REDACTED, no `sk-12345` in output | ✓ |

## Test Results

| Test | Input | Expected | Actual | Status |
|------|-------|----------|--------|--------|
|      |       |          |        |        |

## Error Log

| Timestamp | Error | Attempt | Resolution |
|-----------|-------|---------|------------|
| 2026-08-16 | pydantic_core import broken in Hermes system venv | 1 | Irrelevant — rush uses its own `.venv` |

## 5-Question Reboot Check

| Question | Answer |
|----------|--------|
| Where am I? | Phase 1 (Requirements & Discovery), in_progress |
| Where am I going? | Phases 2–6: architecture, skeleton, tool impls, MCP server, polish |
| What's the goal? | Ship rush: Python CLI + stdio MCP server exposing review/lint/format/test/security tools |
| What have I learned? | See `findings.md` (transport=stdio, SDK=mcp 1.28.1, Python-only v0.1, output schema) |
| What have I done? | Repo created, git initialized, planning trio written, transport confirmed |
