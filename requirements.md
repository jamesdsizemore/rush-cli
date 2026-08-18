# Requirements — rush v0.1

## Status

**Phase 1 deliverable. Phase 1 not complete until this file exists.**

The user asked for Phase 1 to be done right. This document captures the
formal scope, acceptance criteria, and constraints that `findings.md`
researched and the planning trio decided. Anything not in this file is
out of scope for v0.1.

---

## 1. Product summary

**rush** is a Python 3.12 CLI + stdio MCP server for coding agents. It
exposes a small, opinionated set of code-quality tools (review, lint,
format, test, security) that any agent — Claude Code, Cursor, Codex,
Windsurf, Gemini CLI — can call over MCP. The same tools are also
runnable as one-shot CLI subcommands for humans.

rush is a sibling to **headcleaner**, but the two share no code. They
live in separate repos, share a neon palette discipline, and solve
different problems (headcleaner converts documents to Markdown/OKF;
rush reviews code). Both are built with Python 3.12 + uv.

---

## 2. Hard constraints (MUST NOT violate)

These are non-negotiable. If a future decision seems to require
violating one, surface it as a question rather than silently crossing
the line.

| # | Constraint | Source |
|---|---|---|
| C1 | **MCP is the only agentic surface.** No HTTP/SSE daemon, no plugin registry, no separate SDK beyond MCP. | User, original brief |
| C2 | **stdio MCP only.** No HTTP, no SSE, no remote transport in v0.1. | User (`clarify`) |
| C3 | **Single source of truth per tool.** Each tool is one Python function called by both the CLI subcommand and the MCP tool. No parallel implementations. | Findings, "Decisions Made" |
| C4 | **JSON output is canonical.** The same dict shape is returned to CLI (`--json` flag) and to MCP (auto-JSON). Pretty-printing is a CLI-only view layer. | Findings, "Output schema" |
| C5 | **MCP stdout is sacred.** All logs go to stderr (NDJSON, gated by `RUSH_LOG_LEVEL`). Any stdout print corrupts the MCP transport. | Findings, "Logs" |
| C6 | **No code dependency on headcleaner or any other repo.** rush stands alone. Integration is at the agent level (MCP-to-MCP) or config level, never import. | Findings, "Decisions Made" |
| C7 | **Auto-conversion never claims review.** rush's `review` returns `status: heuristic` by default; `status: llm` only when `--llm` is set with a valid API key. A human reviewer must explicitly invoke `rush review --claim-reviewed` (out of scope for v0.1, noted for v0.2) to flip it to `reviewed`. | Headcleaner trust stance, applied |
| C8 | **No red, no warm orange in UI.** Palette: **neon cyan `#22D3EE` (primary)** → **neon green `#22FF88` (secondary, active)** → **neon yellow `#FFE600` (tertiary, review-needed / warnings)**. Status map: ok=cyan, active=green, info=yellow, failed=pink (bright), skipped=grey. | User (`clarify`) |
| C9 | **No LLM call by default.** `rush review` runs deterministic heuristics. The `--llm` flag is an opt-in that reads `ANTHROPIC_API_KEY` or `OPENAI_API_KEY` from env. | User (`clarify`) |
| C10 | **Engine discovery, not engine requirement.** If `ruff` isn't on PATH, `rush lint` returns `{status: "skipped", reason: "..."}` — never a hard failure. Agents can react. | Findings, "Engine discovery" |

---

## 3. v0.1 scope (ship this, nothing else)

### 3.1 Five tools, each a Python function

| Tool name | Python engine | JS/TS engine | Function signature |
|---|---|---|---|
| `review` | heuristics (file size, TODO density, docstrings, naming, cyclomatic smell) + `--llm` opt-in | same heuristics + same `--llm` opt-in | `review(path: str, use_llm: bool = False, llm_provider: str \| None = None) -> ToolResult` |
| `lint` | `ruff check --output-format=json` (49.2k★) | `eslint --format=json` (27.5k★) | `lint(path: str, engine_args: list[str] \| None = None) -> ToolResult` |
| `format` | `ruff format` | `prettier --write` (52.2k★, also handles JSON/MD/YAML/CSS/HTML) | `format(path: str, check: bool = False) -> ToolResult` |
| `test` | `pytest` (parse summary; `--json-report` if plugin present) | `vitest run --reporter=json` preferred, `npm test --reporter=json` fallback | `test(path: str) -> ToolResult` |
| `security` | `pip-audit --format=json` | `npm audit --json` | `security(path: str) -> ToolResult` |

### 3.2 MCP server

- Subcommand: `rush mcp serve`
- Implementation: `mcp.server.fastmcp.FastMCP("rush")` from the `mcp` Python SDK 1.28.x
- Transport: stdio only (C2)
- Five tools registered, one per Python function in §3.1
- Tool descriptions must include: what it does, what it returns, what engines it needs, what `status: skipped` means
- Tool inputs use JSON-schema (auto-generated from type hints via FastMCP)
- Tool outputs are JSON-serialized `ToolResult` dicts (C4)

### 3.3 CLI surface

```
rush --version
rush --help
rush review <path> [--llm] [--json]
rush lint <path> [--engine-args "..."] [--json]
rush format <path> [--check] [--json]
rush test <path> [--json]
rush security <path> [--json]
rush mcp serve
```

Built with **click** (consistent with headcleaner-cli). Output uses **rich**
for pretty tables; `--json` flag bypasses rich and prints the raw `ToolResult`.

### 3.4 Configuration file (`rush.toml`)

Discovered by walking up from cwd to git root; first match wins.
CLI flags override file values.

```toml
[project]
src = ["src"]
test = ["tests"]
exclude = ["**/.venv/**", "**/node_modules/**"]

[tools.lint]
engine_args = ["--select", "E,F,W,I"]

[tools.format]
check = false

[tools.test]
engine_args = ["-q"]

[tools.review]
max_file_lines = 400
fail_on = ["todo-density-high"]

[tools.security]
ignore = []
```

### 3.5 Output schema (C4)

Every tool returns the same shape, regardless of CLI or MCP:

```python
{
    "tool": "lint",               # one of: review, lint, format, test, security
    "engine": "ruff",             # engine name; null if skipped
    "engine_version": "0.6.9",    # captured at runtime; null if skipped
    "status": "ok",               # ok | warn | fail | error | skipped
    "duration_ms": 412,
    "summary": "12 issues, 2 auto-fixable",
    "findings": [
        {
            "path": "src/foo.py",
            "line": 42,
            "column": 8,
            "rule": "E501",
            "severity": "warn",  # info | warn | error
            "message": "line too long",
            "fix": None          # or {"edits": [...]} when engine provides it
        }
    ],
    "raw": "<engine-native payload, optional>"
}
```

Status semantics:
- `ok` — engine ran, no problems at the configured severity
- `warn` — engine ran, findings at warn severity
- `fail` — engine ran, findings at error severity (or test failures)
- `error` — engine crashed / couldn't parse output (not the same as "found a bug")
- `skipped` — engine not on PATH or file type unsupported (C10)

### 3.6 Logs (C5)

- stderr only, NDJSON, gated by `RUSH_LOG_LEVEL` env var (`debug` | `info` | `warn` | `error`)
- Never write to stdout from any rush code path; stdout is reserved for MCP JSON-RPC frames and CLI final output
- Sensitive values (API keys, file contents) redacted by simple key-name heuristics — no logging library, hand-rolled

### 3.7 Theme (C8)

```python
# src/rush/theme.py
CYAN   = "#22D3EE"   # primary, ok
GREEN  = "#22FF88"   # secondary, active
YELLOW = "#FFE600"   # tertiary, review-needed, warn
PINK   = "#EC4899"   # failed status only (bright, not red)
GREY   = "#6B7280"   # skipped, muted
# Red banned. Yellow now allowed.
```

`format` / `lint` / `test` / `security` / `review` each get a glyph from the
theme. Findings table uses rich with theme colors by severity:
- `info` → cyan
- `warn` → yellow
- `error` → pink

### 3.8 Package layout

```
src/rush/
  __init__.py
  cli.py          # click entrypoint (rush command)
  mcp.py          # FastMCP server registration
  theme.py        # palette constants + rich style helpers
  config.py       # rush.toml discovery + parsing
  tools/
    __init__.py
    base.py       # ToolResult TypedDict + ToolFn ABC
    review.py     # review() function + heuristics
    lint.py       # lint() function + engine dispatch
    format.py     # format() function + engine dispatch
    test.py       # test() function + engine dispatch
    security.py   # security() function + engine dispatch
    common.py     # subprocess runner, engine discovery, output parsing
  engines/
    __init__.py
    ruff.py
    eslint.py
    prettier.py
    vitest.py
    pytest.py
    pip_audit.py
    npm_audit.py
tests/
  conftest.py
  test_*.py        # one per tool + smoke test for `rush mcp serve`
docs/
  README.md, AGENTS.md, CHANGELOG.md, CONTRIBUTING.md, INSTALL.md
pyproject.toml     # Python 3.12, deps: mcp, click, rich
```

### 3.9 Verification (acceptance)

The following must all pass before v0.1 is shipped:

1. `uv sync` produces a clean `.venv/`
2. `rush --help` renders the CLI
3. `rush review ./src` returns a structured dict
4. `rush lint ./src --json` returns parseable JSON
5. `rush mcp serve` boots and registers 5 tools without crashing
6. Registering rush in Claude Code / Cursor lets an agent invoke all 5 tools
7. `pytest` green (≥ 1 test per tool + smoke test for MCP server)
8. `rush --version` reports the correct version

### 3.10 Documentation (deliverables)

- `README.md` — install + 30-second quickstart + MCP wiring snippet
- `AGENTS.md` — mirrors headcleaner structure (palette, layout, trust stance, layout diagram)
- `CHANGELOG.md` — `0.1.0` entry
- `INSTALL.md` — `uv tool install rush-cli` and `uvx rush` paths
- `CONTRIBUTING.md` — "Adding a new tool" walkthrough (the `Adapter` pattern)

---

## 4. Out of scope for v0.1 (explicit non-goals)

| Not in v0.1 | Why |
|---|---|
| HTTP/SSE MCP transport | C2 — user chose stdio only |
| `--llm` reviews requiring API key by default | C9 — heuristics are the default |
| AI-slop detection as a separate tool | v0.2 backlog; heuristic `review` covers most of it |
| Secret scanning (gitleaks, trufflehog) | v0.2 backlog |
| IaC scanning (tflint, checkov) | v0.2 backlog |
| Dockerfile lint (hadolint) | v0.2 backlog |
| Markdown lint (markdownlint-cli2) | v0.2 backlog |
| GitHub Actions lint (actionlint) | v0.2 backlog |
| YAML/JSON lint (spectral) | v0.2 backlog |
| SQL lint (sqlfluff) | v0.2 backlog |
| Dead-code detection (vulture, knip) | v0.2 backlog |
| Coverage (coveragepy, istanbul) | v0.2 backlog |
| Mutation testing (mutpy, gremlins) | v0.2 backlog |
| E2E testing (playwright, puppeteer, cypress) | v0.2 backlog |
| Type checking (mypy, pyright, tsc) | v0.2 backlog |
| Complexity (radon, jscpd) | v0.2 backlog |
| AI-slop (`sloppylint`) | v0.2 backlog |
| Cloud AI review (sourcery, kodus-ai, codeball) | v0.3 backlog |
| SBOM generation (cdxgen) | v0.2 backlog |
| OSV-scanner (replaces pip-audit/npm-audit) | v0.3 backlog |
| License compliance | v0.3 backlog |
| Commit-msg lint (commitlint) | v0.2 backlog |
| Pre-commit framework integration | v0.2 backlog |
| Property-based testing (hypothesis, fast-check) | v0.2 backlog |
| Visual regression (jest-image-snapshot, loki) | v0.2 backlog |
| Snapshot testing (insta, Verify, swift-snapshot-testing) | v0.2 backlog |
| Flaky-test detection | v0.2 backlog |
| Fuzzing (AFLplusplus, oss-fuzz, ffuf) | v0.2 backlog |
| Load testing (k6, locust, vegeta, gatling) | v0.2 backlog |
| Contract testing (pact-*) | v0.2 backlog |
| Semantic-drift detection (`svitaliy/SemanticDriftDetector`) | v0.3 backlog — niche, requires .NET |
| CI/CD config linting (`ci` tool) | v0.2 backlog |
| Release automation (`release` tool) | v0.2 backlog |
| Graft integration (`--use-graft`) | v0.2 backlog — Graft is rush's conceptual neighbor; integrate via MCP-to-MCP |
| Languages beyond Python + JS/TS | v0.2 adds 12 more; v0.3 adds Haskell/C/C++/Lua |
| `--claim-reviewed` flag for `review` | v0.2 — human-review trust flip |
| Auto-update / version check | v0.2 |
| TUI / Textual dashboard | Not in v0.1 scope; rush is CLI+MCP only |

If a user request lands in this list, the answer is "v0.2 backlog" unless
they want to expand v0.1 scope (in which case, surface the trade-off
explicitly rather than silently expanding).

---

## 5. Acceptance gates

A change is "v0.1 done" when **all** of these are true:

- [ ] `pyproject.toml` lists `mcp>=1.28,<2`, `click>=8,<9`, `rich>=13,<14`
- [ ] `uv sync` produces a clean `.venv/`
- [ ] All 5 tool functions exist in `src/rush/tools/*.py` and return the canonical `ToolResult`
- [ ] `src/rush/mcp.py` registers all 5 tools via `FastMCP`
- [ ] `src/rush/cli.py` exposes all 5 subcommands + `mcp serve` via click
- [ ] `src/rush/theme.py` exports the palette constants per C8
- [ ] `src/rush/config.py` discovers and parses `rush.toml` per §3.4
- [ ] Engine discovery per C10 is implemented in `src/rush/tools/common.py`
- [ ] stderr NDJSON logging per §3.6 is wired
- [ ] ≥ 1 pytest test per tool + 1 smoke test for `rush mcp serve`
- [ ] README, AGENTS.md, CHANGELOG, INSTALL, CONTRIBUTING all exist
- [ ] Manual test: `rush mcp serve` boots in Claude Code and all 5 tools are callable
- [ ] Manual test: each `rush <tool>` subcommand runs and returns the canonical JSON

---

## 6. Open questions for Phase 2

These don't block Phase 1 sign-off but should be resolved before Phase 3
(Implementation) starts:

1. **Engine version capture.** Do we shell out to `<engine> --version` on
   first use and cache, or assume the latest stable? Recommendation: cache.
2. **Concurrent engine execution.** When `rush review` invokes multiple
   heuristics, do they run in parallel via `asyncio.gather` or sequentially?
   Recommendation: parallel for `review`; sequential for `lint`/`test`/`security`
   to preserve deterministic output ordering.
3. **MCP tool description length.** FastMCP truncates long descriptions;
   we should target <200 chars per tool.
4. **Where does `--llm` prompt content come from?** Heuristic findings
   become the prompt context. Need a stable, deterministic prompt template
   to avoid flapping LLM output.
5. **Path handling on Windows.** `pathlib.Path` cross-platform — verify
   no `os.path.join` leaks.
6. **`rush.toml` schema validation.** Use `pydantic` or hand-rolled? Recommendation:
   hand-rolled for v0.1 (smaller dep surface); switch to pydantic in v0.2 if
   config complexity grows.

---

## 7. Traceability

| Requirement | Source |
|---|---|
| stdio MCP only | User `clarify`, session 1 |
| Python + JS/TS in v0.1 | User `clarify`, session 1 |
| `--llm` opt-in (heuristics default) | User `clarify`, session 1 |
| Palette: cyan → green → yellow (main → least) | User, session 2 |
| No red in palette | Headcleaner rule, applied + extended |
| Single source of truth per tool | Findings, "Decisions Made" |
| JSON canonical, --json CLI flag | Findings, "Output schema" |
| stderr logs only (MCP stdout sacred) | Findings, "Logs" |
| Engine discovery, not hard fail | Findings, "Engine discovery" |
| 5 tools in v0.1: review/lint/format/test/security | User, original brief; locked in Phase 1 `clarify` |
| ruff + pytest + pip-audit (Python) | Findings, "Engine matrix" |
| eslint + vitest + npm-audit (JS/TS) | Findings, "Engine matrix" |
| No headcleaner import | Findings, "Decisions Made" |
| Package layout mirrors headcleaner | Findings, "headcleaner parallels" |
| Click + rich for CLI | Findings, "Decisions Made" |
| v0.2 backlog of 27 additional tools + Graft integration | Findings, "Deep research" |

---

## 8. Sign-off

Phase 1 is complete when:
- This file exists ✓ (you are here)
- `findings.md` is committed ✓
- `task_plan.md` reflects the current scope ✓
- `progress.md` logs Phase 1 as complete
- Phase 1 checkboxes in `task_plan.md` are all ticked

---

## 9. v0.2 expansion contract

v0.2 retains every hard constraint in §2 and extends the catalog-driven tool
surface. Engine executables remain externally discovered; Python-native
installations may be documented as optional extras but no Rush command silently
installs an engine. See [`docs/V0_2_SCOPE.md`](docs/V0_2_SCOPE.md) for output,
safety, and status contracts.

| Capability | Primary engine(s) | Fallback / routing marker | Support |
|---|---|---|---|
| `typecheck` | mypy, tsc | `pyproject.toml`, `package.json` | stable |
| `dead` | vulture, knip | Python/JS source markers | best-effort |
| `complexity` | radon, jscpd | Python/JS source markers | best-effort |
| `slop` | sloppylint, deterministic heuristics | Python/JS source markers | experimental |
| `markdown` | markdownlint-cli2 | `.md`, `.mdx` | stable |
| `actions` | actionlint | `.github/workflows/*.yml` | stable |
| `yaml` | spectral | `.yaml`, `.yml`, OpenAPI markers | best-effort |
| `sql` | sqlfluff | `.sql`, dbt markers | stable |
| `templates` | djlint | `.html`, `.jinja`, Django markers | best-effort |
| `containerfile` | hadolint | `Dockerfile*`, `Containerfile*` | stable |
| `iac` | tflint, checkov | `.tf`, Terraform markers | stable |
| `secrets` | gitleaks | repository root; values always redacted | stable |
| `sbom` | cdxgen | explicit safe output path | best-effort |
| `coverage` | coverage.py, c8/nyc | project test configuration | stable |
| `mutation` | mutmut, Stryker | explicit `allow_slow` | experimental |
| `e2e` | Playwright | explicit `allow_browser` | best-effort |
| `pbt` | Hypothesis, fast-check | existing tests only | best-effort |
| `visual` / `snapshot` | project snapshot runner | explicit baseline acceptance | best-effort |
| `flaky` | JUnit/history parser | existing reports only | experimental |
| `fuzz` | configured fuzz target | explicit `allow_fuzz` | experimental |
| `load` | k6, Locust | explicit `allow_network` | experimental |
| `contract` | Pact configuration | existing suites only | best-effort |
| `commit-msg` | commitlint | commit message or Git metadata | stable |
| `ci` | actionlint plus workflow checks | CI configuration | best-effort |
| `release` | Git metadata checks | dry-run by default | experimental |
| language routing | native ecosystem CLIs | Go/Rust/Java/.NET/Ruby/PHP/C/C++/Dart/Swift/Kotlin/Lua/Elixir markers | best-effort |
| `context` | Graft graph queries | local Graft graph only | experimental |
| `semantic-drift` | documented external detector | explicit opt-in | experimental |

Cloud AI review, hosted OSV enrichment, license policy enforcement, and all
non-stdio MCP transports remain deferred. Slow, browser, fuzzing, networked,
or publishing operations must return `skipped` until explicitly enabled.

### v0.2 traceability

| Requirement | Test evidence |
|---|---|
| catalog identity and optional result fields | `tests/test_catalog.py`, `tests/test_base.py` |
| deterministic routing and aggregation | `tests/test_routing.py`, `tests/test_tools.py` |
| CLI/MCP parity | `tests/test_cli_registry.py`, `tests/test_mcp.py` |
| engine parser and missing-binary behavior | per-family adapter tests and fixtures |
| opt-in safety controls | test-quality and workflow tool tests |
| stdio-only transport / stderr logging | `tests/test_mcp.py`, `tests/test_logging.py` |
