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

### Phase 4: Tool Implementations
- **Status:** complete
- **Completed:** 2026-08-16
- Implemented real Ruff, ESLint, Prettier, pytest, Vitest, pip-audit, and npm-audit adapters; wired all five CLI/MCP-shared tools; added review heuristics and LLM-key guards.
- Fixed venv binary precedence, project-root discovery, pip-audit exit semantics, pytest summary parsing, ESLint missing-config handling, and nested engine finding coordinates.
- Evidence: `.venv/Scripts/python.exe -m pytest tests/ -q` passed **48/48** on Python 3.12.13. End-to-end CLI smoke tests exercised review, lint, format, test, and security against real engines.
- Commit: `c5a8487 feat(v0.1.0-alpha): tool implementations — real engines, real results`.

### Phase 5: MCP Server
- **Status:** complete
- **Started:** 2026-08-16
- Initial evidence: `build_server()` exists and registers `rush_review`, `rush_lint`, `rush_format`, `rush_test`, and `rush_security`; Phase 5 will verify the full stdio JSON-RPC handshake and tool-call result shape.
- Error (attempt 1): Windows MCP subprocess creation rejects `io.StringIO` as `errlog` because it has no `fileno()`. Resolution: capture server stderr through a real temporary file handle.
- Error (attempt 2): multi-tool MCP smoke parsed `rush_review` successfully, then assumed every following response was JSON and raised `JSONDecodeError` on `rush_lint`. Next action: inspect the raw MCP response and distinguish a server-side tool error from an invalid test assumption.
- Root cause (attempt 2): FastMCP validated non-review results against `ToolResult.review_kind: Literal["heuristic", "llm"]`; those tools correctly omit the review-only field, which FastMCP materialized as `None` and rejected. Resolution: make the review-only field nullable in the canonical schema and cover a real MCP lint call in the integration test.
- Error (attempt 3): all-five MCP smoke with `rush_test` aimed at Rush's own root exceeded 240 seconds. The likely self-recursive path is the server launching pytest, which runs the MCP integration test and starts another server. Resolution: validate `rush_test` over MCP against an isolated temporary Python project; keep the full-repo CLI test as the non-recursive end-to-end evidence.
- Error (attempt 4): isolated-project MCP smoke confirms the timeout is not recursion: review/lint/format return, then `rush_test` blocks. Next action: inspect pytest adapter argv and the child process environment inherited from `StdioServerParameters`.
- Root cause (attempt 4): `StdioServerParameters.env` replaces (rather than merges) the process environment. The smoke set only `RUSH_LOG_LEVEL`, removing Windows runtime variables required by pytest/plugin imports. Resolution: preserve `os.environ` and override only `RUSH_LOG_LEVEL`; verify all five calls again.
- Error (attempt 5): preserving the environment removes the Windows runtime failure, but the live MCP call to `rush_test` still times out after review/lint/format succeed. Next action: compare direct `TestTool.run()` behavior with FastMCP dispatch before changing product code.
- Root cause (attempt 5): direct `TestTool.run()` completes, isolating the block to `pytest.exe` when it is spawned from the FastMCP stdio child. Resolution: invoke pytest with the active server interpreter (`sys.executable -m pytest`) instead of the Windows console-script wrapper.
- Error (attempt 6): `python -m pytest` still blocks only under live MCP. Root-cause hypothesis: pytest inherits the server's open JSON-RPC stdin pipe, whereas direct execution does not. Resolution under test: detach pytest stdin with `subprocess.DEVNULL`.
- Root cause (attempt 6): detaching pytest stdin resolves `rush_test` over MCP. The all-tool smoke now reaches `rush_security` and blocks in pip-audit, which also inherits the JSON-RPC stdin pipe. Next action: apply the same isolation centrally to all engine subprocesses.
- Error (attempt 7): the central stdin fix reaches security and exposes a pip-audit parser gap: pip-audit 2.10 returns a `dependencies` envelope, but Rush accepts only a legacy list and falsely reports clean. A combined fix patch matched ambiguously and made no changes; next action is a narrow parser + regression-test patch.
- Root cause (attempt 7): parsed pip-audit 2.10 envelopes now produce the real `PYSEC-2026-1845` finding, with a display compatibility detail fixed too: current rows use `name`, whereas legacy rows use `package`.
- Delivered `tests/test_mcp.py` and `docs/MCP.md`; corrected the shared ToolResult MCP schema, stdin isolation for every engine subprocess, venv-local engine version lookup, and pip-audit 2.10 parsing.
- Evidence: full project-venv suite passes **50/50** on Python 3.12.13. One official MCP stdio session initialized successfully, listed all five schemas, invoked all five tools, and received canonical JSON each time. Rush's debug startup NDJSON record was captured only from stderr.
- Note: `rush_security` correctly reports `fail` for `PYSEC-2026-1845` in development `pytest==8.3.4` (upgrade target `9.0.3`); that is a genuine scan result, not a Phase 5 test failure.

### Phase 6: Polish & Verification
- **Status:** complete
- **Started:** 2026-08-17
- Initial gate: all 50 tests pass, but `ruff check src tests` reports 91 violations (76 safe auto-fixes). Phase 6 begins by clearing that debt before release documentation and fresh-checkout validation.
- Error (fresh-checkout attempt 1): Git could not open a patch stored in the temporary parent directory after cloning. No Rush command ran and the source tree was untouched. Resolution: generate and apply the diff inside the clone with an explicit file-existence check.
- Completed the safe Ruff pass and manual structural fixes. Final project-venv gate: `ruff check` clean, `ruff format --check` clean, `pytest tests/ -q` **50 passed**, and `git diff --check` clean.
- Fresh-checkout validation passed through a Python-managed temporary clone (no shell trap or patch harness): `uv sync --frozen` completed; the installed `rush --help` returned successfully; `pytest tests/ -q` reported **46 passed, 4 skipped** because external engines are intentionally not bundled.

### Phase 7: Release Maintenance
- **Status:** complete
- **Started:** 2026-08-17
- Pushed `07d24d8 docs: record Phase 6 verification` to `origin/main`.
- Upgraded the locked test runner from `pytest==8.3.4` to `pytest==9.0.3`, removing the prior `PYSEC-2026-1845` finding.
- Declared `ruff==0.16.3` and `pip-audit==2.10.1` in the `dev` extra so CI uses reproducible tooling rather than undeclared local executables.
- Added `.github/workflows/ci.yml`: locked install; Ruff lint and format checks; pytest; pip-audit; whitespace check; and wheel/sdist build.
- Local CI-equivalent evidence: `uv lock`, `uv sync --all-extras --frozen`, Ruff clean, **50/50** tests, `pip-audit` reports no known vulnerabilities, `git diff --check` clean, and `uv build` emits both distribution artifacts.
- Remote CI run `32081247968` failed before project setup because `astral-sh/setup-uv` has release `v10.0.1` but no floating `v10` tag. Resolution: pin the verified releases exactly (`checkout@v7.0.1`, `setup-python@v7.0.0`, and `setup-uv@v10.0.1`) and rerun CI.
- Remote CI run `32081298431` passed all install, lint, format, test, audit, whitespace, and build steps in 22 seconds. It emitted no Node-20 deprecation annotation.

## Test Results

| Test | Input | Expected | Actual | Status |
|------|-------|----------|--------|--------|
| Full suite | `.venv/Scripts/python.exe -m pytest tests/ -q` | Tests pass | 50 passed | pass |
| MCP integration | `tests/test_mcp.py` | stdio handshake, clean schemas, structured calls | initialize/list/review/lint passed | pass |
| Five-tool MCP smoke | official `mcp` client | canonical JSON from each tool; logs on stderr | 4 `ok`, 1 genuine security `fail`; stderr verified | pass |
| Fresh checkout | temporary local clone + `uv sync --frozen` | install, CLI, and MCP test suite work | `rush --help`; 46 passed, 4 engine skips | pass |
| Release-maintenance CI gate | `uv sync --all-extras --frozen`; lint, tests, audit, build | reproducible quality and packaging checks | 50 passed; no known vulnerabilities; wheel + sdist built | pass |
| Remote CI | GitHub Actions run `32081298431` | workflow completes without platform warnings | all quality and build steps passed in 22s | pass |

### Phase 8: v0.2 Catalog & Routing Foundation
- **Status:** in_progress
- **Started:** 2026-08-17
- Restored the persistent project plan, progress, and findings before beginning v0.2 implementation.
- Read the approved implementation plan at `.hermes/plans/2026-08-17_164317-rush-v0-2-expansion.md`.
- Tool context: `rtk` is installed and used; no `context` executable is available; the codegraph service cannot query this unindexed repository.
- Built and queried Graft's local key-free wiring graph under `.hermes/graft/`. It found the intended refactor hotspots and reports fresh state. The first `graft callers ALL_TOOLS` query failed because module constants are not graph symbols; the corrected `graft grep` and `graft ask` queries located all registry consumers.
- TDD catalog slice: `tests/test_catalog.py` first failed because `rush.catalog` did not exist. Added `src/rush/catalog.py` with v0.1 metadata plus the v0.2 result extensions (`metrics`, `artifacts`, `metadata`).
- Regression correction: initially widening `ToolName` to `str` broke the existing literal contract and non-null optional extensions caused FastMCP to reject omitted fields. Restored the current literal pending tool registration and made v0.2 fields nullable.
- Evidence: focused catalog + real stdio MCP tests passed (**4 passed**); full project-v​​env suite passed **53/53**.
- TDD routing slice: `tests/test_routing.py` first failed for the absent routing module, then verified deterministic status ranking, stable finding ordering, metric/artifact merging, and generated-directory filtering. `src/rush/tools/lint.py` and `src/rush/tools/format.py` now share `routing.py` instead of duplicating file collection/status ranking.
- A combined migration patch was rejected because duplicate update lines were ambiguous; re-read the files and applied a context-specific replacement. Ruff then found one unused import; the prescribed `ruff --fix` and formatter resolved it.
- Evidence: routing/tool/MCP focused tests passed (**18 passed**); full project-v​​env suite passed **56/56**; Ruff, format check, and `git diff --check` passed.
- Next: write the failing catalog-driven CLI/MCP instruction test before removing static transport assumptions.

### 2026-08-17 — v0.2 foundation complete

- Added `docs/V0_2_SCOPE.md`, v0.2 requirements/architecture overlays, and an Unreleased changelog entry. The dependency policy preserves external engine discovery; no engine is silently installed.
- Replaced the five-name `ToolName` literal with `str`, added catalog-backed generic Click commands for ordinary path tools, and generated MCP server instructions from `TOOL_SPECS`. `review` and `format` retain their dedicated option surfaces.
- Evidence: focused base/CLI/MCP tests passed (**20 passed**); full project-v​​env suite passed **60/60**.
- Next: verify the static-analysis family against fixtures, skipped-engine behavior, real registry discovery, and the complete quality gate.
- Static-analysis delegation did not alter the repository: its API connection failed after retries. The capability work has been resumed locally; no delegation output is treated as implementation evidence.

## Error Log

| Timestamp | Error | Attempt | Resolution |
|-----------|-------|---------|------------|
| 2026-08-16 | pydantic_core import broken in Hermes system venv | 1 | Irrelevant — rush uses its own `.venv` |
| 2026-08-17 | Task 9 multi-document patch used a stale changelog heading | 1 | Re-read exact document contexts and applied targeted patches |

### 2026-08-17 — Task 9 in progress

- Began with `git status`, branch/log inspection, and a fresh Graft build/check.
- Wrote RED workflow safety tests; expected collection failure confirmed absent
  Task 9 modules. Implemented non-mutating commit validation, local CI
  inspection, dry-run release planning, and optional commitlint discovery.
- Focused evidence: `17 passed` with the project Python 3.12 environment.

### 2026-08-17 — Task 10 in progress

- Added deterministic multi-ecosystem project detection plus check-only lint,
  type, and test adapter maps. Fixture tests mock only subprocess execution.
- Full evidence: **108 passed, 7 expected external-engine skips** with the
  project Python 3.12 environment; Ruff, diff, and Graft graph checks passed.

### 2026-08-18 — Task 13 complete

- Added catalog-validated generic tool configuration, reference guides, and
  a checked `examples/rush.toml`.
- Evidence: configuration/catalog contracts passed and the project Python 3.12
  suite passed **112 tests with 7 expected external-engine skips**.

### 2026-08-18 — Task 14 complete

- Added a bounded Python-only representative-engine CI job; it does not
  provision all optional language runtimes.
- Local evidence: adapter suite **14 passed**, `pip-audit` reported no known
  vulnerabilities, and `uv build` produced wheel and source artifacts.

### 2026-08-18 — Task 15 release-candidate validation complete

- Fresh remote clone completed `uv sync --all-extras --frozen` in a new venv.
- Isolated clean-clone CLI/MCP catalog tests passed (**5 passed**) and a real
  lint run returned a canonical `ok` result.
- Built wheel and sdist installed independently in two fresh Python 3.12
  environments and both imported Rush successfully. No tag or release made.
- GitHub Actions CI passed for candidate `e9bb242`: full quality/package and
  bounded representative-engine jobs both completed successfully
  ([run 32184793416](https://github.com/jamesdsizemore/rush-cli/actions/runs/32184793416)).

### 2026-08-18 — Phase 02 Checkov adapter checkpoint

- Began and scoped the slice with RTK Git inspection, Graft architecture
  retrieval, context-mode Phase 02 acceptance retrieval, and pinned official
  Checkov `3.3.9` source/release/license reads.
- Replaced inherited text parsing with a local Terraform-only JSON adapter:
  `--directory DIR --framework terraform --output json --skip-download
  --download-external-modules false`. The child environment is allowlisted and
  does not inherit Bridgecrew/Prisma credentials or Checkov configuration.
- `IacTool` now aggregates TFLint then Checkov through the existing canonical
  routing helper. Both adapters are registered in the catalog fixture audit;
  all other Phase 02 candidates remain feasibility-gated.
- RED evidence: the new Checkov reference suite failed at four expected absent
  seams. GREEN evidence: promotion regression passed **34 tests**. Full quality
  and final repository gates remain pending for this active Phase 02 phase.
- Errors/recovery are recorded in `.hermes/implementation/phase-00-02-ledger.md`;
  no scanner was installed or executed, and local research remains untracked.

### 2026-08-18 — Phase 02 kubeconform feasibility checkpoint

- Began with RTK Git/scope inspection, Graft YAML routing discovery, and
  context-mode Phase 02/Phase 07 contract retrieval; used the pinned official
  kubeconform `0.8.0` release, license, usage, and CLI source.
- Recorded `P02-009`: kubeconform's default `master` schema version and HTTP
  schema resolution/cache violate Rush local-only rules without a Rush-owned
  schema corpus. Deferred it to Phase 07; no executable was installed or run.
- Error/recovery: this RTK build does not provide `rtk read`; bounded native
  reads were used only after Graft/context-mode located exact documentation
  anchors. RTK remained the Git/search/diff boundary.

### 2026-08-18 — Phase 02 actionlint adapter checkpoint

- Used RTK Git/scope boundaries, Graft engine/tool/registry discovery, and
  context-mode Phase 02 acceptance retrieval with official actionlint `1.7.12`
  source/release/license evidence.
- RED fixture evidence exposed inherited text parsing, implicit configuration,
  and external shellcheck/pyflakes child-integration risk. GREEN adapter uses
  explicit empty config, disables both child integrations, and parses JSON.
- Focused adapter gate: `3 passed`; Ruff check and format passed. Catalog,
  fixture registry, compatibility/evidence, decision, issue, and backlog records
  were updated; no scanner was installed or executed.

### 2026-08-18 — Phase 02 markdownlint adapter checkpoint

- Error discovered: the preexisting route named `markdownlint-cli2` conflicted
  with the pinned Phase 02 `markdownlint-cli 0.49.1` baseline and only parsed
  text output. Replaced it with contained JSON invocation and parser coverage.
- Focused routing/catalog/CLI/MCP/truth gate: `22 passed`; Ruff check and format
  passed. `P02-011`, compatibility, local evidence, and decision records were
  updated; no package installation or external scanner execution occurred.

### 2026-08-18 — Phase 02 Spectral adapter checkpoint

- RED fake-process tests exposed the inherited text adapter's missing JSON,
  ruleset, resolver, and remote-reference controls. GREEN uses an owned static
  no-extends ruleset and blocks external `$ref` before process launch.
- Focused catalog/routing/CLI/MCP/truth gate: `26 passed`; Ruff check and format
  passed. `P02-005`, compatibility, local evidence, findings, and fixture
  registration were updated; no package installation or executable run occurred.

### 2026-08-18 — Phase 02 ansible-lint feasibility checkpoint

- RTK/Graft/context-mode established that Rush has no Ansible engine/tool route;
  official `26.8.0` evidence shows SARIF but also project cache/write semantics
  and untrusted-content execution/configuration risk.
- Recorded `P02-012` and kept the candidate feasibility-gated. No adapter,
  catalog, YAML routing, installation, or executable invocation was added.

### 2026-08-18 — Phase 02 codespell feasibility checkpoint

- RTK/Graft/context-mode and official `2.4.3` source show no focused Rush seam,
  automatic project TOML discovery, and no structured output proof.
- Recorded `P02-013`; no generic content route, adapter, execution, or install
  was added.

### 2026-08-18 — Phase 02 Vale feasibility checkpoint

- Recovered the upstream-repository relocation correctly through the direct
  `v3.17.1` commit and versioned Vale config/sync sources. Two retrieval-command
  shape errors were logged and did not affect the repository.
- Recorded `P02-014`: global/project style discovery plus mutating/downloadable
  `sync` behavior lacks a Rush-owned local-corpus containment contract. No
  adapter, route, configuration, style artifact, install, or execution was added.

### 2026-08-18 — Phase 02 Lychee feasibility checkpoint

- RTK/Graft/context-mode confirmed no existing link-check/import seam and the
  governing plan's explicit no-live-network restriction.
- Recorded `P02-015`; no route, adapter, network permission, installation, or
  executable invocation was added.

## 5-Question Reboot Check

| Question | Answer |
|----------|--------|
| Where am I? | Phase 7 (Release Maintenance), complete |
| Where am I going? | Package publication when requested, then v0.2 scope selection |
| What's the goal? | Ship rush: Python CLI + stdio MCP server exposing review/lint/format/test/security tools |
| What have I learned? | stdio child engines must detach stdin; pip-audit 2.10 uses a dependencies envelope; MCP `env` replaces the inherited environment |
| What have I done? | Phases 1–7 complete: implementation, MCP integration, verification, security remediation, and a passing GitHub Actions pipeline |

### 2026-08-19 — Product documentation rewrite

- Rebuilt documentation for separate user, contributor, and maintainer
  audiences from the implementation, generated CLI surface, catalog,
  configuration model, engine registry, MCP server, tests, CI, and package
  metadata.
- Added onboarding, goal-oriented user chapters, eight tutorials, exact command
  and result references, a configuration cookbook, complete engine directory,
  MCP/CI/automation integrations, safety/privacy/security boundaries, developer
  recipes, maintainer runbooks, ADRs, and annotated example configurations.
- Recorded implementation gaps instead of marketing them as capability:
  permission-sensitive generic CLI flags, commit-message input, SBOM output
  controls, and release publication controls are not exposed; `review --llm`
  remains a deterministic no-call stub; some parsed settings lack consumers.
- Final evidence: 130 Markdown files cover all 32 tools and 27 engines; 235
  local links (including anchors) validate; 189 tests pass with 7 expected
  optional-engine skips; Ruff lint/format, pip-audit, `git diff --check`, RTK
  review, and Graft graph freshness all pass.
