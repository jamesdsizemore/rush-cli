# Phase 50c implementation plan — performance profiling, offline review, and honest provenance

## 1. Purpose and status

- **Operation:** Create the implementation plan for Phase 50c (sub-phase 3 of the decomposed Phase 50).
- **Planning status:** Implementation-ready after §4 admission passes.
- **Implementation status:** Not authorized by this plan. Code freeze in effect.
- **Authority:** Roadmap capability families I16, I19, I20, I24, and I26 from `docs/rush-token-innovation-enhancement-report-plan.md`.
- **Predecessor:** Accepted Phase 50b (Attribution, PR Evidence, and Workspace Hygiene).
- **Successor:** Phase 51 (Remediation Scope, Operation Inventory, and Release Probes).
- **Boundary:** Performance timing, memory profiling, benchmark statistics, external offline review discovery, and honest build provenance draft generation.
- **Lifecycle boundary:** No commit, push, merge, tag, publish, release, hooks, or history rewrite.

---

## 2. Authority, evidence, and decisions

### 2.1 Authority order

1. User instructions and constraints (zero code modification during planning).
2. Repository `AGENTS.md` (canonical `ToolResult` shape, engine discovery from environment, stdio MCP stdout, keep dependencies minimal).
3. `pyproject.toml` Architecture §13 (stdlib tomllib + hand-rolled, keep deps minimal, no pydantic).
4. Repository remediation plan `docs/developer/repository-remediation-plan.md` (R-013 honest provenance) and `docs/phase-plans/phase50-adversarial-review.md`.
5. Successor remediation plan `docs/phase-plans/phase-59-provenance-engine-conformance-plan.md`.

### 2.2 Current-state evidence

| Family | Existing Implementation | Existing Tests | Status in Repository |
|---|---|---|---|
| **I16 (Attest)** | `src/rush/tools/attest.py` (flawed) | `tests/test_phase50_slsa_attestation.py:test_slsa_attestation_generator` | Currently makes unsupported SLSA Level 3 claims and hashes commit string instead of artifact (Finding R-013). Needs complete rewrite to honest unsigned draft. |
| **I19 (Mem Profile)** | None | None | Needs implementation: static AST unclosed resource check + dynamic sampling. |
| **I20 (Cold Start)** | None | None | Needs implementation: `-X importtime` execution and waterfall analysis. |
| **I24 (Offline Review)** | None | None | Needs implementation: discovers external local LLM engines (`ollama`, `llama-cli`) on PATH; returns `skipped` if absent. |
| **I26 (Benchmark)** | None | None | Needs implementation: repeated benchmark suite with stdlib `statistics`. |

### 2.3 Closed decisions

- **Zero fraudulent SLSA Level 3 claims:** Strictly align `rush attest` with Phase 59. Local output is an **explicit unsigned provenance draft** by default, hashing the actual built distribution artifact (`.whl` or `.tar.gz`) from `dist/`. Never claim Level 3 or unverified hermeticity.
- **Zero `scipy` dependency:** Benchmark statistics (mean, median, standard deviation, percentiles, confidence intervals) are computed entirely with Python 3.12 stdlib `statistics` and `math`.
- **Zero bundled local LLM wheels:** Do not add `llama-cpp-python` or `onnxruntime` to dependencies or extras. Rush discovers external local engines (`ollama`, `llama-cli`) from PATH. If not installed, returns structured `status="skipped"` with installation instructions.
- **Pruned scope creep:**
  - Strike I22 full-screen Textual TUI to protect FastMCP stdio stdout from terminal escape sequences.
  - Strike I21 WebP/AVIF image transcoding and JSX rewriting to protect Rush's focus as a backend/systems quality substrate.
- **Transport parity:** Register all 5 tools in `src/rush/catalog.py` (`TOOL_SPECS`), `src/rush/tools/__init__.py` (`ALL_TOOLS`), with standard CLI and MCP interfaces.

---

## 3. Goals, outcomes, exclusions, and invariants

### 3.1 Outcomes

1. **`rush attest` (I16):** Generates an honest, unpadded in-toto Statement v1 with SLSA v1.0 Provenance predicate binding real artifact hashes from `dist/`, marked explicitly as an unsigned draft.
2. **`rush mem-profile` (I19):** Detects unclosed file handles and database connections via static AST analysis, and samples RSS memory slope during test suite runs using stdlib `tracemalloc` (or optional `psutil` if present).
3. **`rush cold-start` (I20):** Executes `python -X importtime` on package entry points, builds an import timing waterfall, and flags slow top-level imports that should be deferred or lazy-loaded.
4. **`rush offline-review` (I24):** Integrates with external local LLM providers (e.g. Ollama, llama.cpp server) for air-gapped offline code review. Fails closed with `status="skipped"` when no external local runner is detected.
5. **`rush benchmark` (I26):** Executes repeated benchmark runs, computes descriptive statistics and p95 latencies via stdlib `statistics`, compares against previous baselines, and flags regressions.
6. **Cycle completion:** Reaches 49 canonical catalog tools, ready for Phase 51 admission.

### 3.2 Exclusions

- Zero `scipy`, zero `textual`, zero `llama-cpp-python`, zero `onnxruntime` dependencies.
- Zero claims of SLSA Build Level 3 for local CLI runs.
- Zero full-screen interactive terminal modes during MCP server execution.

### 3.3 Invariants

- Python 3.12 with `uv`.
- FastMCP stdio stdout is strictly reserved for JSON-RPC; all logs/diagnostics go to stderr.
- Canonical `ToolResult` format across all transports.
- All checks use portable `uv run` commands, compatible with POSIX and Windows.

---

## 4. Admission and predecessor gate

Before starting Phase 50c tasks:
1. Verify Phase 50b acceptance: all 44 catalog tools passing.
2. Verify clean git status: `git status --short --branch`.
3. Verify test baseline: `uv run python -m pytest -q` passes with `>= 905` tests.
4. Verify code formatting and linting: `uv run ruff check src tests scripts` and `uv run ruff format --check src tests scripts`.
5. Stop condition: If any test fails or working tree is dirty, stop and report blocker.

---

## 5. Requirement-ownership ledger

| Requirement ID | Family | Capability Description | Owning Tasks | Deliverable Files |
|---|---|---|---|---|
| **REQ-50C-I16-CORE** | I16 | Honest in-toto Statement v1 / SLSA v1.0 draft generator | P50C-001..P50C-004 | `src/rush/tools/attest.py`, `tests/test_attest.py` |
| **REQ-50C-I19-CORE** | I19 | Static unclosed resource check & RSS memory sampling | P50C-005..P50C-008 | `src/rush/tools/mem_profile.py`, `tests/test_mem_profile.py` |
| **REQ-50C-I20-CORE** | I20 | Python `-X importtime` waterfall analyzer | P50C-009..P50C-012 | `src/rush/tools/cold_start.py`, `tests/test_cold_start.py` |
| **REQ-50C-I24-CORE** | I24 | External local LLM engine discovery & review adapter | P50C-013..P50C-016 | `src/rush/tools/offline_runner.py`, `tests/test_offline_runner.py` |
| **REQ-50C-I26-CORE** | I26 | Repeated benchmark suite with stdlib `statistics` | P50C-017..P50C-020 | `src/rush/tools/benchmark.py`, `tests/test_benchmark.py` |
| **REQ-50C-INTEG** | Shared | Catalog, CLI, MCP registration & docs | P50C-021..P50C-024 | `src/rush/catalog.py`, `src/rush/tools/__init__.py`, `docs/tools/*.md` |

---

## 6. Shared contracts and handoff

- **ToolFn Contract:** All five tools subclass `ToolFn` from `src/rush/tools/base.py`.
- **ToolResult Schema:**
  - `name`: `"attest"`, `"mem-profile"`, `"cold-start"`, `"offline-review"`, `"benchmark"`
  - `status`: `"ok"`, `"warn"`, `"fail"`, `"skipped"`
  - `findings`: Structured list of `Finding` objects
  - `summary`: Concise metrics and assessment
- **Registration:**
  - `TOOL_SPECS` entries in `src/rush/catalog.py`.
  - Added to `ALL_TOOLS` in `src/rush/tools/__init__.py`.
- **Handoff:** Phase 50c completes the Phase 41–50 innovation cycle with 49 canonical catalog tools and passes directly into Phase 51 (Remediation Scope and Release Probes).

---

## 7. Contract-test inventory

| Test File | Target Seam | Key Assertions |
|---|---|---|
| `tests/test_attest.py` | `AttestTool` | Generates in-toto Statement v1 / SLSA v1.0 draft; hashes actual `.whl`/`.tar.gz` from `dist/`; explicitly marks `status="ok"` with `draft=True`; never claims Level 3. |
| `tests/test_mem_profile.py` | `MemProfileTool` | Detects `open()` without context manager via AST; measures subprocess heap slope during pytest runs; handles missing optional `psutil` gracefully. |
| `tests/test_cold_start.py` | `ColdStartTool` | Parses `python -X importtime` stderr; calculates cumulative and self import duration; flags modules exceeding 10ms. |
| `tests/test_offline_runner.py` | `OfflineReviewTool` | Discovers `ollama` or local runner on PATH; returns `status="skipped"` when absent; parses structured response when mock runner responds. |
| `tests/test_benchmark.py` | `BenchmarkTool` | Runs 5 benchmark iterations; calculates mean, stdev, p95 using stdlib `statistics`; compares against baseline; flags >5% regression. |
| `tests/test_phase50c_integration.py` | CLI & MCP transports | `rush attest`, `rush mem-profile`, `rush cold-start`, `rush offline-review`, `rush benchmark` CLI execution and MCP endpoints. |

---

## 8. File, dependency, and documentation governance

### 8.1 File writes

- **Production:**
  - `src/rush/tools/attest.py` (rewrite existing flawed implementation)
  - `src/rush/tools/mem_profile.py` (new)
  - `src/rush/tools/cold_start.py` (new)
  - `src/rush/tools/offline_runner.py` (new)
  - `src/rush/tools/benchmark.py` (new)
  - `src/rush/catalog.py` (register tool specs)
  - `src/rush/tools/__init__.py` (export and register in `ALL_TOOLS`)
- **Tests:**
  - `tests/test_attest.py` (rewrite)
  - `tests/test_mem_profile.py` (new)
  - `tests/test_cold_start.py` (new)
  - `tests/test_offline_runner.py` (new)
  - `tests/test_benchmark.py` (new)
  - `tests/test_phase50c_integration.py` (new)
- **Documentation:**
  - `docs/tools/attest.md` (update)
  - `docs/tools/mem_profile.md` (new)
  - `docs/tools/cold_start.md` (new)
  - `docs/tools/offline_review.md` (new)
  - `docs/tools/benchmark.md` (new)
  - `docs/TOOL_CATALOG.md` (update catalog entries)
  - `docs/CLI_REFERENCE.md` (update CLI commands)
  - `docs/MCP_REFERENCE.md` (update MCP tools)

### 8.2 Dependencies

- Optional dependency: `psutil>=7.2,<8` (added to optional extras for deep process inspection, with pure-stdlib fallback).
- Prohibited dependencies: `scipy`, `textual`, `codebleu`, `llama-cpp-python`, `onnxruntime`.

---

## 9. Ordered execution workstreams and atomic task cards

### Workstream 1: I16 Honest Build Provenance Draft (Tasks P50C-001..P50C-004)

#### P50C-001 — RED: Pin honest unsigned provenance draft structure
- **Action:** Create `tests/test_attest.py` with `test_generate_unsigned_slsa_v1_draft`. Assert statement type `https://in-toto.io/Statement/v1`, predicate type `https://slsa.dev/provenance/v1.0`, and absence of "Level 3" claims.
- **Checks:** `uv run python -m pytest tests/test_attest.py -q` fails against current flawed implementation.

#### P50C-002 — GREEN: Implement SLSA v1.0 Statement generator
- **Action:** Rewrite `src/rush/tools/attest.py` to generate compliant in-toto Statement v1 with SLSA v1.0 predicate.
- **Checks:** `uv run python -m pytest tests/test_attest.py -q` passes.

#### P50C-003 — RED: Pin true artifact hashing from dist/
- **Action:** Add `test_attest_hashes_real_artifact_from_dist` and `test_attest_rejects_missing_artifact`.
- **Checks:** `uv run python -m pytest tests/test_attest.py -q` fails.

#### P50C-004 — GREEN: Complete AttestTool with canonical ToolResult
- **Action:** Implement `AttestTool(ToolFn)` in `src/rush/tools/attest.py`, binding real artifact digests and returning `status="ok"` with draft notice.
- **Checks:** `uv run python -m pytest tests/test_attest.py -q` passes.

---

### Workstream 2: I19 Memory & Resource Profiler (Tasks P50C-005..P50C-008)

#### P50C-005 — RED: Pin static unclosed resource detection
- **Action:** Create `tests/test_mem_profile.py` with `test_detect_unclosed_file_handles_ast` and `test_detect_unclosed_sockets_ast`.
- **Checks:** `uv run python -m pytest tests/test_mem_profile.py -q` fails.

#### P50C-006 — GREEN: Implement static resource leak detector
- **Action:** Create `src/rush/tools/mem_profile.py` with `StaticResourceAuditor` scanning AST for `open()`, `socket()`, and database connects without `with` context managers.
- **Checks:** `uv run python -m pytest tests/test_mem_profile.py -q` passes.

#### P50C-007 — RED: Pin memory sampling with stdlib tracemalloc fallback
- **Action:** Add `test_measure_memory_slope_during_execution` asserting fallback to `tracemalloc` if `psutil` is missing.
- **Checks:** `uv run python -m pytest tests/test_mem_profile.py -q` fails.

#### P50C-008 — GREEN: Complete MemProfileTool with canonical ToolResult
- **Action:** Finalize `MemProfileTool(ToolFn)` in `src/rush/tools/mem_profile.py` emitting leak findings and memory slope summaries.
- **Checks:** `uv run python -m pytest tests/test_mem_profile.py -q` passes.

---

### Workstream 3: I20 Cold-Start Import Profiler (Tasks P50C-009..P50C-012)

#### P50C-009 — RED: Pin python -X importtime parsing
- **Action:** Create `tests/test_cold_start.py` with `test_parse_importtime_output` parsing simulated import timing lines (`import time: self [us] | cumulative | imported package`).
- **Checks:** `uv run python -m pytest tests/test_cold_start.py -q` fails.

#### P50C-010 — GREEN: Implement importtime parser
- **Action:** Create `src/rush/tools/cold_start.py` implementing `ImportTimeParser` converting stderr lines into structured tree nodes.
- **Checks:** `uv run python -m pytest tests/test_cold_start.py -q` passes.

#### P50C-011 — RED: Pin slow import threshold and lazy-load suggestion
- **Action:** Add `test_flag_slow_imports_exceeding_threshold` asserting that imports taking >10ms cumulative time produce a finding with a lazy-import remediation suggestion.
- **Checks:** `uv run python -m pytest tests/test_cold_start.py -q` fails.

#### P50C-012 — GREEN: Complete ColdStartTool with canonical ToolResult
- **Action:** Finalize `ColdStartTool(ToolFn)` in `src/rush/tools/cold_start.py` executing isolated subprocess with `-X importtime` and returning findings.
- **Checks:** `uv run python -m pytest tests/test_cold_start.py -q` passes.

---

### Workstream 4: I24 Offline LLM Review Provider (Tasks P50C-013..P50C-016)

#### P50C-013 — RED: Pin external local engine discovery
- **Action:** Create `tests/test_offline_runner.py` with `test_discover_local_runner_on_path` and `test_missing_runner_returns_structured_skipped`.
- **Checks:** `uv run python -m pytest tests/test_offline_runner.py -q` fails.

#### P50C-014 — GREEN: Implement external runner discovery
- **Action:** Create `src/rush/tools/offline_runner.py` checking for `ollama` executable or custom local endpoint. Returns `status="skipped"` when absent.
- **Checks:** `uv run python -m pytest tests/test_offline_runner.py -q` passes.

#### P50C-015 — RED: Pin local review query and response parsing
- **Action:** Add `test_query_local_runner_and_parse_findings` with mocked local endpoint response.
- **Checks:** `uv run python -m pytest tests/test_offline_runner.py -q` fails.

#### P50C-016 — GREEN: Complete OfflineReviewTool with canonical ToolResult
- **Action:** Finalize `OfflineReviewTool(ToolFn)` in `src/rush/tools/offline_runner.py` executing review and mapping responses to canonical findings.
- **Checks:** `uv run python -m pytest tests/test_offline_runner.py -q` passes.

---

### Workstream 5: I26 Benchmark Runner (Tasks P50C-017..P50C-020)

#### P50C-017 — RED: Pin stdlib descriptive statistics calculation
- **Action:** Create `tests/test_benchmark.py` with `test_calculate_benchmark_statistics_stdlib`. Assert mean, median, stdev, p95 without importing `scipy`.
- **Checks:** `uv run python -m pytest tests/test_benchmark.py -q` fails.

#### P50C-018 — GREEN: Implement benchmark statistics using stdlib
- **Action:** Create `src/rush/tools/benchmark.py` implementing statistics calculation using `statistics.mean`, `statistics.median`, `statistics.stdev`, `statistics.quantiles`.
- **Checks:** `uv run python -m pytest tests/test_benchmark.py -q` passes.

#### P50C-019 — RED: Pin repeated execution and regression threshold
- **Action:** Add `test_detect_benchmark_regression` comparing current sample against baseline.
- **Checks:** `uv run python -m pytest tests/test_benchmark.py -q` fails.

#### P50C-020 — GREEN: Complete BenchmarkTool with canonical ToolResult
- **Action:** Finalize `BenchmarkTool(ToolFn)` executing multiple runs, saving baseline JSON, and reporting performance findings.
- **Checks:** `uv run python -m pytest tests/test_benchmark.py -q` passes.

---

### Workstream 6: Integration, Registration, Documentation & Graft (Tasks P50C-021..P50C-024)

#### P50C-021 — RED: Pin catalog and transport registration
- **Action:** Create `tests/test_phase50c_integration.py` asserting `attest`, `mem-profile`, `cold-start`, `offline-review`, and `benchmark` are in `TOOL_SPECS`, in `ALL_TOOLS`, and have CLI/MCP routes.
- **Checks:** `uv run python -m pytest tests/test_phase50c_integration.py -q` fails.

#### P50C-022 — GREEN: Register tools in catalog, CLI, and MCP
- **Action:** Add specs in `src/rush/catalog.py`, add instances to `ALL_TOOLS` in `src/rush/tools/__init__.py`.
- **Checks:** `uv run python -m pytest tests/test_phase50c_integration.py tests/test_catalog.py tests/test_cli_registry.py -q` passes.

#### P50C-023 — DOCS: Author exact documentation pages
- **Action:** Create `docs/tools/attest.md`, `docs/tools/mem_profile.md`, `docs/tools/cold_start.md`, `docs/tools/offline_review.md`, `docs/tools/benchmark.md`. Update `docs/TOOL_CATALOG.md`, `docs/CLI_REFERENCE.md`, `docs/MCP_REFERENCE.md`.
- **Checks:** Verify links and command syntax against registered options.

#### P50C-024 — GRAFT: Rebuild repository context graph
- **Action:** Run `npx @nanonets/graft build` or verify `graft/` index includes all newly added symbols.
- **Checks:** `uv run python -m pytest -q` passes; full suite reaches `>= 945` tests (905 from 50b + >=40 new tests).

---

## 10. Final verification and delivery gate

1. Run full test suite: `uv run python -m pytest tests/ -q`. All tests must pass (expected count >= 945).
2. Run linters: `uv run ruff check src tests scripts` (zero errors).
3. Run format check: `uv run ruff format --check src tests scripts` (zero diffs).
4. Verify catalog count: Exactly 49 tools registered in `TOOL_SPECS` and `ALL_TOOLS`.
5. Verify zero dependencies on `scipy`, `textual`, or bundled local LLMs.
6. Verify honest unsigned provenance draft format (no fraudulent SLSA Level 3 claims).

---

## 11. Exit checklist and successor handoff

- [ ] All 24 task cards completed in RED/GREEN/VERIFY sequence.
- [ ] Zero unverified SLSA claims, zero `scipy`/`textual` dependencies, zero hardcoded `.venv/Scripts/` paths.
- [ ] Phase 41–50 innovation cycle formally complete.
- [ ] Clean handoff to Phase 51 (Remediation Scope, Operation Inventory, and Release Probes).
