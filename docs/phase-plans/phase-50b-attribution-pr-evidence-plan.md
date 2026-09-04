# Phase 50b implementation plan — attribution, PR evidence, and workspace hygiene

## 1. Purpose and status

- **Operation:** Create the implementation plan for Phase 50b (sub-phase 2 of the decomposed Phase 50).
- **Planning status:** Implementation-ready after §4 admission passes.
- **Implementation status:** Not authorized by this plan. Code freeze in effect.
- **Authority:** Roadmap capability families I15, I27, and I28 from `docs/rush-token-innovation-enhancement-report-plan.md`.
- **Predecessor:** Accepted Phase 50a (Polyglot Error Catalog, License Matrix, and Cloud IAM Audit).
- **Successor:** Phase 50c (Performance Profiling, Offline Review, and Honest Provenance).
- **Boundary:** Git history inspection, static asset reference analysis, and PR evidence card synthesis. Strictly read-only; zero Git rewrites, zero Git hooks, and zero destructive file pruning.
- **Lifecycle boundary:** No commit, push, merge, tag, publish, release, hooks, or history rewrite.

---

## 2. Authority, evidence, and decisions

### 2.1 Authority order

1. User instructions and constraints (zero code modification during planning).
2. Repository `AGENTS.md` (read-only workflow tools, no Git history rewrites, no hooks, no frontend UI design, stdio MCP stdout).
3. Governing roadmap `docs/rush-token-innovation-enhancement-report-plan.md` (I15, I27, I28 requirements).
4. Repository remediation plan `docs/developer/repository-remediation-plan.md` and `docs/phase-plans/phase50-adversarial-review.md`.
5. Current repository source, tests, and configuration as empirical ground truth.

### 2.2 Current-state evidence

| Family | Existing Implementation | Existing Tests | Status in Repository |
|---|---|---|---|
| **I15 (AI Attribution)** | None | None | Needs complete clean implementation conforming to `src/rush/tools/base.py`. |
| **I27 (Dead Asset)** | `src/rush/tools/dead_asset.py` (stub) | `tests/test_phase50_slsa_attestation.py:test_dead_asset_scanner` | Basic prototype exists; scans only `index.html` `img` tags. Needs polyglot regex scanning, and must be strictly read-only (no deletion). |
| **I28 (PR Synthesize)** | `src/rush/tools/pr_synthesize.py` (stub) | `tests/test_phase50_slsa_attestation.py:test_pr_synthesizer` | Stub generates hardcoded markdown. Needs true tool-result aggregation, risk tiering, and CODEOWNERS routing. |

### 2.3 Closed decisions

- **Strictly read-only dead asset scanning:** Strike the dangerous "guarded prune" file deletion feature from rejected Phase 50. Rush is a quality analysis substrate; it never deletes user assets.
- **Zero Git history or hook mutations:** Phase 50b tools inspect git logs and trailers (`Co-authored-by:`, `AI-Generated:`); they never rewrite history, install pre-commit hooks, or commit code.
- **No external network egress:** PR synthesis outputs Markdown/JSON locally to stdout or an explicit output file. It never calls GitHub APIs directly without explicit user-provided credentials.
- **No heavy dependencies:** Rely strictly on Python 3.12 stdlib (`re`, `pathlib`, `json`, `datetime`) and existing `tree-sitter`. No `pillow` transcoding, no `textual` TUI.
- **Transport parity:** Register all 3 tools in `src/rush/catalog.py` (`TOOL_SPECS`), `src/rush/tools/__init__.py` (`ALL_TOOLS`), and expose CLI and MCP endpoints.

---

## 3. Goals, outcomes, exclusions, and invariants

### 3.1 Outcomes

1. **`rush provenance-ai` (I15):** Analyzes Git commits for AI generation markers, co-author trailers, and session continuity. Computes 30/60/90-day code survival curves and defect correlation rates.
2. **`rush dead-asset` (I27):** Scans source code (HTML, CSS, JS, TS, JSX, Markdown) for image, font, and media references. Identifies unreferenced files in static asset directories and reports potential disk space savings.
3. **`rush pr-synthesize` (I28):** Aggregates results of quality tools (tests, linter, typecheck, coverage, licenses, arch guard) and Git diff stats into a comprehensive PR review card with risk tiering (low, medium, high) and CODEOWNERS routing.
4. **Catalog expansion:** Increases catalog tool count from 41 to 44.

### 3.2 Exclusions

- Zero file deletion or automated file pruning.
- Zero Git branch, tag, commit, or hook mutations.
- Zero network API requests to remote Git hosting services.

### 3.3 Invariants

- Python 3.12 with `uv`.
- MCP stdio stdout is strictly JSON-RPC; diagnostics to stderr.
- Canonical `ToolResult` format across all transports.
- Portable `uv run` commands across Windows and POSIX.

---

## 4. Admission and predecessor gate

Before starting Phase 50b tasks:
1. Verify Phase 50a acceptance: all 41 catalog tools passing.
2. Verify clean git status: `git status --short --branch`.
3. Verify test baseline: `uv run python -m pytest -q` passes with `>= 875` tests.
4. Verify code formatting and linting: `uv run ruff check src tests scripts` and `uv run ruff format --check src tests scripts`.
5. Stop condition: If any test fails or working tree is dirty, stop and report blocker.

---

## 5. Requirement-ownership ledger

| Requirement ID | Family | Capability Description | Owning Tasks | Deliverable Files |
|---|---|---|---|---|
| **REQ-50B-I15-CORE** | I15 | Git trailer & AI attribution parser | P50B-001..P50B-004 | `src/rush/tools/provenance_ai.py`, `tests/test_provenance_ai.py` |
| **REQ-50B-I15-SURV** | I15 | Code survival rate & defect correlation | P50B-005..P50B-006 | `src/rush/tools/provenance_ai.py`, `tests/test_provenance_ai.py` |
| **REQ-50B-I27-CORE** | I27 | Polyglot asset reference scanner | P50B-007..P50B-010 | `src/rush/tools/dead_asset.py`, `tests/test_dead_asset.py` |
| **REQ-50B-I27-SAFE** | I27 | Read-only reporting and space savings calculation | P50B-011..P50B-012 | `src/rush/tools/dead_asset.py`, `tests/test_dead_asset.py` |
| **REQ-50B-I28-CORE** | I28 | ToolResult aggregation & risk tiering | P50B-013..P50B-016 | `src/rush/tools/pr_synthesize.py`, `tests/test_pr_synthesize.py` |
| **REQ-50B-I28-ROUTE** | I28 | CODEOWNERS parsing & reviewer recommendation | P50B-017..P50B-018 | `src/rush/tools/pr_synthesize.py`, `tests/test_pr_synthesize.py` |
| **REQ-50B-INTEG** | Shared | Catalog, CLI, MCP registration & docs | P50B-019..P50B-022 | `src/rush/catalog.py`, `src/rush/tools/__init__.py`, `docs/tools/*.md` |

---

## 6. Shared contracts and handoff

- **ToolFn Contract:** All three tools subclass `ToolFn` from `src/rush/tools/base.py`.
- **ToolResult Schema:**
  - `name`: `"provenance-ai"`, `"dead-asset"`, `"pr-synthesize"`
  - `status`: `"ok"`, `"warn"`, `"fail"`, `"skipped"`
  - `findings`: Structured list of `Finding` objects
  - `summary`: Concise metrics and assessment
- **Registration:**
  - `TOOL_SPECS` entries in `src/rush/catalog.py`.
  - Added to `ALL_TOOLS` in `src/rush/tools/__init__.py`.
- **Handoff:** Phase 50b delivers 44 canonical catalog tools with 100% test pass rate to Phase 50c.

---

## 7. Contract-test inventory

| Test File | Target Seam | Key Assertions |
|---|---|---|
| `tests/test_provenance_ai.py` | `ProvenanceAiTool` | Parses `Co-authored-by:`, `AI-Generated:` trailers; calculates 30-day commit line survival; correlates defect fixes. |
| `tests/test_dead_asset.py` | `DeadAssetTool` | Scans HTML `<img src>`, CSS `url()`, JS/TS `import ... from`, Markdown `![]()`; identifies unreferenced files; confirms read-only (zero file deletion). |
| `tests/test_pr_synthesize.py` | `PrSynthesizeTool` | Aggregates findings from multiple tools; assigns risk tier (low/med/high); parses `CODEOWNERS` and maps modified files to teams/owners. |
| `tests/test_phase50b_integration.py` | CLI & MCP transports | `rush provenance-ai`, `rush dead-asset`, `rush pr-synthesize` CLI execution; `rush_provenance_ai`, `rush_dead_asset`, `rush_pr_synthesize` MCP tools. |

---

## 8. File, dependency, and documentation governance

### 8.1 File writes

- **Production:**
  - `src/rush/tools/provenance_ai.py` (new)
  - `src/rush/tools/dead_asset.py` (rewrite existing prototype to be strictly read-only)
  - `src/rush/tools/pr_synthesize.py` (rewrite existing prototype)
  - `src/rush/catalog.py` (register 3 tool specs)
  - `src/rush/tools/__init__.py` (export and register in `ALL_TOOLS`)
- **Tests:**
  - `tests/test_provenance_ai.py` (new)
  - `tests/test_dead_asset.py` (rewrite/expand)
  - `tests/test_pr_synthesize.py` (rewrite/expand)
  - `tests/test_phase50b_integration.py` (new)
- **Documentation:**
  - `docs/tools/provenance_ai.md` (new)
  - `docs/tools/dead_asset.md` (new)
  - `docs/tools/pr_synthesize.md` (new)
  - `docs/TOOL_CATALOG.md` (update catalog entries)
  - `docs/CLI_REFERENCE.md` (update CLI commands)
  - `docs/MCP_REFERENCE.md` (update MCP tools)

### 8.2 Dependencies

- Zero new dependencies. Uses Python 3.12 stdlib (`pathlib`, `re`, `json`, `datetime`) and existing `tree-sitter`.
- Prohibited dependencies: `pillow` (transcoding), `textual`, `scipy`.

---

## 9. Ordered execution workstreams and atomic task cards

### Workstream 1: I15 AI Provenance & Attribution (Tasks P50B-001..P50B-006)

#### P50B-001 — RED: Pin Git commit trailer parsing
- **Action:** Create `tests/test_provenance_ai.py` with `test_parse_git_ai_trailers`. Mock git commit log outputs containing `Co-authored-by: Claude <...>`, `AI-Generated: true`.
- **Checks:** `uv run python -m pytest tests/test_provenance_ai.py -q` fails.

#### P50B-002 — GREEN: Implement Git trailer extractor
- **Action:** Create `src/rush/tools/provenance_ai.py` implementing `GitTrailerParser` using `run_subprocess(["git", "log", ...])`.
- **Checks:** `uv run python -m pytest tests/test_provenance_ai.py -q` passes.

#### P50B-003 — RED: Pin commit line survival tracking
- **Action:** Add `test_calculate_code_survival_rates` for 30, 60, and 90-day intervals.
- **Checks:** `uv run python -m pytest tests/test_provenance_ai.py -q` fails.

#### P50B-004 — GREEN: Implement code survival analyzer
- **Action:** Implement survival rate calculation comparing historical blame lines against current HEAD.
- **Checks:** `uv run python -m pytest tests/test_provenance_ai.py -q` passes.

#### P50B-005 — RED: Pin defect correlation logic
- **Action:** Add `test_correlate_defects_with_attributed_commits` asserting correlation between commits with fix trailers and prior AI-attributed changes.
- **Checks:** `uv run python -m pytest tests/test_provenance_ai.py -q` fails.

#### P50B-006 — GREEN: Complete ProvenanceAiTool with canonical ToolResult
- **Action:** Finalize `ProvenanceAiTool(ToolFn)` in `src/rush/tools/provenance_ai.py` emitting structured attribution findings and summary metrics.
- **Checks:** `uv run python -m pytest tests/test_provenance_ai.py -q` passes.

---

### Workstream 2: I27 Dead Asset Scanner (Tasks P50B-007..P50B-012)

#### P50B-007 — RED: Pin polyglot asset reference extraction
- **Action:** Create `tests/test_dead_asset.py` with `test_extract_asset_references_from_html`, `test_extract_asset_references_from_css`, `test_extract_asset_references_from_markdown`, `test_extract_asset_references_from_jsx`.
- **Checks:** `uv run python -m pytest tests/test_dead_asset.py -q` fails.

#### P50B-008 — GREEN: Implement polyglot asset reference extractor
- **Action:** Rewrite `src/rush/tools/dead_asset.py` with `AssetReferenceExtractor` scanning source files using regex patterns for `src=`, `href=`, `url()`, and markdown images.
- **Checks:** `uv run python -m pytest tests/test_dead_asset.py -q` passes.

#### P50B-009 — RED: Pin dead asset identification and size calculation
- **Action:** Add `test_identify_unreferenced_assets` comparing disk assets against referenced paths.
- **Checks:** `uv run python -m pytest tests/test_dead_asset.py -q` fails.

#### P50B-010 — GREEN: Implement unreferenced asset matcher
- **Action:** In `dead_asset.py`, index files in static directories and compute the set difference against referenced paths, summing potential byte savings.
- **Checks:** `uv run python -m pytest tests/test_dead_asset.py -q` passes.

#### P50B-011 — RED: Pin strict read-only guarantee (no deletion capability)
- **Action:** Add `test_dead_asset_scanner_never_deletes_files`, proving that calling the tool with any arguments leaves all files on disk intact.
- **Checks:** `uv run python -m pytest tests/test_dead_asset.py -q` passes.

#### P50B-012 — GREEN: Complete DeadAssetTool with canonical ToolResult
- **Action:** Finalize `DeadAssetTool(ToolFn)` emitting `Finding` for each dead asset with path, size, and status `warn` or `ok`.
- **Checks:** `uv run python -m pytest tests/test_dead_asset.py -q` passes.

---

### Workstream 3: I28 PR Synthesizer & Review Routing (Tasks P50B-013..P50B-018)

#### P50B-013 — RED: Pin quality tool result aggregation
- **Action:** Create `tests/test_pr_synthesize.py` with `test_aggregate_tool_results` mocking multiple `ToolResult` instances (lint, tests, coverage, security).
- **Checks:** `uv run python -m pytest tests/test_pr_synthesize.py -q` fails.

#### P50B-014 — GREEN: Implement quality result aggregator
- **Action:** Rewrite `src/rush/tools/pr_synthesize.py` implementing `QualityResultAggregator` compiling summaries and violation counts into a unified card data model.
- **Checks:** `uv run python -m pytest tests/test_pr_synthesize.py -q` passes.

#### P50B-015 — RED: Pin risk tiering calculation
- **Action:** Add `test_calculate_pr_risk_tier` testing thresholds for `low` (docs/small tests), `medium` (standard changes), `high` (security, db schema, core architecture).
- **Checks:** `uv run python -m pytest tests/test_pr_synthesize.py -q` fails.

#### P50B-016 — GREEN: Implement risk tiering engine
- **Action:** Implement deterministic risk score calculation based on changed file patterns, lines modified, and tool findings in `pr_synthesize.py`.
- **Checks:** `uv run python -m pytest tests/test_pr_synthesize.py -q` passes.

#### P50B-017 — RED: Pin CODEOWNERS file parsing and review routing
- **Action:** Add `test_parse_codeowners_routing` asserting that modified files correctly map to declared team or user handles.
- **Checks:** `uv run python -m pytest tests/test_pr_synthesize.py -q` fails.

#### P50B-018 — GREEN: Complete PrSynthesizeTool with canonical ToolResult
- **Action:** Finalize `PrSynthesizeTool(ToolFn)` rendering both a Markdown PR summary card and structured JSON findings.
- **Checks:** `uv run python -m pytest tests/test_pr_synthesize.py -q` passes.

---

### Workstream 4: Integration, Registration, Documentation & Graft (Tasks P50B-019..P50B-022)

#### P50B-019 — RED: Pin catalog and transport registration
- **Action:** Create `tests/test_phase50b_integration.py` asserting `provenance-ai`, `dead-asset`, and `pr-synthesize` are registered in `TOOL_SPECS`, in `ALL_TOOLS`, and have CLI and MCP endpoints.
- **Checks:** `uv run python -m pytest tests/test_phase50b_integration.py -q` fails.

#### P50B-020 — GREEN: Register tools in catalog, CLI, and MCP
- **Action:** Add specs in `src/rush/catalog.py`, add instances to `ALL_TOOLS` in `src/rush/tools/__init__.py`.
- **Checks:** `uv run python -m pytest tests/test_phase50b_integration.py tests/test_catalog.py tests/test_cli_registry.py -q` passes.

#### P50B-021 — DOCS: Author exact documentation pages
- **Action:** Create `docs/tools/provenance_ai.md`, `docs/tools/dead_asset.md`, `docs/tools/pr_synthesize.md`. Update `docs/TOOL_CATALOG.md`, `docs/CLI_REFERENCE.md`, `docs/MCP_REFERENCE.md`.
- **Checks:** Verify links and command syntax against registered options.

#### P50B-022 — GRAFT: Rebuild repository context graph
- **Action:** Run `npx @nanonets/graft build` or verify `graft/` index includes all newly added symbols.
- **Checks:** `uv run python -m pytest -q` passes; full suite reaches `>= 905` tests (875 from 50a + >=30 new tests).

---

## 10. Final verification and delivery gate

1. Run full test suite: `uv run python -m pytest tests/ -q`. All tests must pass (expected count >= 905).
2. Run linters: `uv run ruff check src tests scripts` (zero errors).
3. Run format check: `uv run ruff format --check src tests scripts` (zero diffs).
4. Verify catalog count: Exactly 44 tools registered in `TOOL_SPECS` and `ALL_TOOLS`.
5. Verify zero file pruning and zero git mutations occurred during execution.

---

## 11. Exit checklist and successor handoff

- [ ] All 22 task cards completed in RED/GREEN/VERIFY sequence.
- [ ] Strict read-only dead asset scanning; zero file deletion logic present.
- [ ] Clean handoff to Phase 50c (Performance Profiling, Offline Review, and Honest Provenance).
