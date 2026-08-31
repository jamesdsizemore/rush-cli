# P50 development remediation audit plan

## 1. Plan identity and status

- **Artifact:** `docs/phase-plans/P50-development-remediation-audit-plan.md`
- **Governing plan:** `docs/phase-plans/phase-50-slsa-attestation-security-suite-flagship-plan.md`
- **Audited checkout:** `C:/Users/james/developer/rush-cli/.worktrees/phase50-implementation`
- **Audited branch / revision:** `feat/phase-50-implementation` at `1fb3582` with uncommitted Phase 50 development
- **Planning status:** **Blocked for implementation.** Unconditional audit-reset and scope-isolation cards may run. Decision-governed feature cards may not run until D50-04, D50-07, D50-08, and D50-10 through D50-18 have explicit user dispositions recorded in the governing plan.
- **Implementation authority:** This document grants no authority to implement, commit, merge, tag, push, publish, release, or work on `main`. A future executor requires explicit user authorization and a non-main worktree.
- **Purpose:** Convert the audited defects into a deterministic, phase-based TDD remediation sequence. This is not an implementation report and does not declare Phase 50 complete.

## 2. Executive verdict

The current Phase 50 development is not eligible for PR50.16 or PR50.17 and is not safe to merge. The focused P50 tests pass, the full repository suite passes, Ruff passes, the lock check passes, and a wheel builds. Those results do not establish plan compliance because the submitted tests encode several prohibited behaviors and the installed-artifact tests execute against the source checkout.

The highest-risk defects are:

1. Decision-blocked work was implemented and then described as approved and complete without the required decision records.
2. IAM output invents actions, inserts default S3 permissions on empty input, and emits `Resource: "*"` as “least privilege.”
3. PR synthesis emits unsupported SLSA Level 3, architecture, compatibility, and all-tests-passing claims.
4. Attestation can report success for a missing or out-of-root subject.
5. Multiple artifact and cache writes bypass the shared contained atomic writer; media optimization mutates source files in place.
6. Dynamic profiling executes target code and masks failures; offline ONNX execution lacks the required decision, dependency, checksum, containment, and permission contract.
7. Dead-asset pruning is not bound to an explicit versioned manifest, fresh rescan, no-follow containment, and unchanged hashes.
8. Tool options, configuration, CLI, MCP, and compatibility routes do not have complete parity.
9. The packaging probes are source-tree tests, not isolated installed-wheel tests.
10. The evidence file contains unsupported approvals, corrupt control characters, invalid RED claims, incomplete route/dependency/wheel evidence, and a false completion statement.
11. Broad unrelated documentation and prior-phase plan churn has no Phase 50 task owner.
12. `git diff --check` fails.

## 3. Audit method and reproduced evidence

### 3.1 Sources inspected

- Governing Phase 50 plan, including decisions, exclusions, invariants, task cards, installed-artifact gate, and final gate.
- Current worktree status and tracked diff.
- All fourteen Phase 50 tool modules; shared `common.py`, catalog, configuration, CLI, MCP, and tool registry.
- All Phase 50 feature tests, catalog/config/CLI/MCP tests, packaging test, and implementation evidence.
- Public documentation and configuration anchors named by the governing plan.
- `pyproject.toml` and `uv.lock`.

### 3.2 Commands independently executed

| Command | Result | Audit meaning |
|---|---:|---|
| Project Python focused P50/core/route suite | 113 passed, 1 warning | Current assertions pass; correctness still depends on assertion quality. |
| Project Python full `tests/` suite | 933 passed, 1 warning | No regression detected by the current suite. |
| `tests/test_phase50_packaging.py` without isolated interpreter | 2 passed | Proves the test is capable of passing without installed-artifact conditions. |
| Same packaging test with `RUSH_PHASE50_WHEEL` set | 2 passed | Wheel membership is partly checked; installed CLI/MCP remains sourced from the checkout. |
| `ruff check src tests scripts` | passed | Static lint gate passes. |
| `ruff format --check src tests scripts` | 648 files formatted | Format gate passes. |
| `uv lock --check` | passed | Current lock is internally consistent; it does not contain the open-decision optional runtimes. |
| `uv build --out-dir .rush/p50-remediation-audit-dist` | sdist and wheel built | Buildability only; no isolated install or public MCP probe was performed by the submitted tests. |
| `git diff --check` | failed | EOF whitespace in five files blocks the final gate. |

### 3.3 Change-set facts

- 82 tracked paths are modified and 40 paths are untracked.
- The tracked diff contains 6,229 insertions and 1,298 deletions before counting untracked files.
- The evidence file claims completion while governing decisions and required task evidence remain open.
- The existing worktree has no local `.venv`; audit commands used `C:/Users/james/developer/rush-cli/.venv/Scripts` with `VIRTUAL_ENV` and `PYTHONPATH` cleared.
- Graft orientation was attempted first; the target implementation worktree was not indexed. The available map saved approximately 44,385,331 tokens but did not supply authoritative target-worktree source, so exact target files were inspected.

## 4. Governing invariants

Every remediation task must preserve all of these invariants:

1. No decision-blocked packet is represented as admitted, implemented, or complete.
2. CLI and MCP call the same registered `ToolFn` object; transports contain no feature business logic.
3. Every tool returns the canonical ToolResult fields: `tool`, `engine`, `engine_version`, `status`, `duration_ms`, `summary`, and `findings`.
4. Valid statuses are limited to the repository vocabulary and must reflect failures truthfully; errors may not be converted into `ok`, invented metrics, or empty findings.
5. Read-only analysis is the default. Slow execution, cache writes, artifact writes, and any other effect require the exact permission.
6. Every output/store path is relative, contained, no-follow, atomic, failure-preserving, and explicit.
7. No target source is overwritten by analysis or optimization. Generated output uses an explicit distinct target.
8. No license, legal compatibility, IAM resource, SLSA level, signature, reproducibility, trusted-builder, PR risk, reviewer, test-pass, coverage, or compatibility conclusion is inferred without exact supplied evidence and an admitted contract.
9. No subprocess shell mode, interpolated executable code, inherited MCP stdin, unbounded output, or unreported nonzero child result is allowed.
10. Optional runtime behavior is absent or `skipped` until its exact dependency and fixture decision is approved and locked.
11. Every GREEN card requires its named ordinary RED tests to collect and fail for the intended assertion. Module import or collection failure is not RED evidence.
12. Tests created by a RED card are immutable during the paired GREEN card.
13. Documentation changes are limited to exact active anchors named by the owning card.
14. Every changed path has exactly one task owner. Unowned files leave the phase incomplete.
15. No task performs Git lifecycle or release actions.

## 5. Decision and admission ledger

| Decision | Current audited state | Required disposition before implementation |
|---|---|---|
| D50-04 offline ONNX | Evidence claims approval; governing plan still says open; no optional runtime extra/lock entry exists. | User records exact runtime constraint, providers, model format, contained model rule, license evidence, checksum policy, and fixture, or defers/removes the packet. |
| D50-07 IAM | No decision record exists; unsafe implementation is present. | User approves a finite cited AWS map, literal-resource policy, supported providers, and unsupported-call behavior, or defers/removes generation. |
| D50-08 dynamic memory | No decision record exists; unapproved `tracemalloc` execution is present. | User approves exact optional sampler constraint, platforms, interval, child policy, and metric definition, or dynamic behavior is removed/deferred. |
| D50-10 prompt evaluation | Evidence claims narrowing without authority. | User approves recorded-run-only scope and deferred owner, or removes/defer packet. |
| D50-11 error catalog | Evidence claims narrowing without authority. | User approves exact Python/literal TypeScript scope and deferred Rust/source-rewrite owner, or removes/defer packet. |
| D50-12 provenance | Evidence claims narrowing without authority. | User approves trailer-only attribution and explicit unknown survival/causation, or removes/defer packet. |
| D50-13 license | Evidence claims narrowing without authority. | User approves exact evidence/allowlist/manual-review scope and defers legal compatibility, or removes/defer packet. |
| D50-14 cold start | Evidence claims narrowing without authority. | User approves Python static inventory plus permissioned import timing and defers Node/patching, or removes/defer packet. |
| D50-15 media | Evidence claims narrowing without authority. | User approves audit plus explicit PNG/WebP outputs and defers source/markup mutation, AVIF, and percentage claims, or removes/defer packet. |
| D50-16 TUI | Evidence claims a renderer without selecting the full-app versus noninteractive outcome. | User selects the public surface; no route/docs work begins before selection. |
| D50-17 benchmark | Evidence claims descriptive comparison without authority. | User approves supplied-sample comparison and explicit baseline store, or removes/defer packet. |
| D50-18 dead asset / PR synth | Evidence claims both narrowed packets without separate dispositions. | User separately approves conservative manifest-bound asset work and observed-evidence-only PR rendering, or removes/defer each packet. |

A future executor must stop if the governing plan and this ledger disagree. The governing plan controls; this remediation plan may be amended only after a recorded user decision.

## 6. Finding ledger and remediation ownership

| Finding | Severity | Exact observed locations | Required remediation cards |
|---|---:|---|---|
| F50-01 Unauthorized decision-blocked implementation and false admission | P0 | plan:8-9, 71-85, 127-129; evidence:21-83, 375-376; catalog:408-634 | R50.0.1–R50.0.4 |
| F50-02 Unowned broad change set and failed diff check | P0 | `git status --short`; plan:27-30, 109-112, 2603-2608 | R50.0.1, R50.0.3 |
| F50-03 Invalid/corrupt TDD and completion evidence | P0 | evidence:24-26, 76, 81, 87-237, 299-320, 322-376 | R50.0.4, R50.4.2–R50.4.3 |
| F50-04 Mutable/nonfunctional typed configuration and precedence | P1 | config.py:44-48, 150-248; catalog.py:498-553; cli.py:101-113, 136-267; docs/CONFIGURATION.md:101-129 | R50.1.1–R50.1.2 |
| F50-05 Incomplete CLI/MCP routes, benchmark collision, wrong alias semantics, obsolete wrappers | P1 | cli.py:136-380, 489-501, 1255-1257, 2637-2790; mcp.py:51-58, 361-408 | R50.1.5–R50.1.6, R50.3.1–R50.3.2 |
| F50-06 Atomic output helper and callers do not meet no-follow/failure contract | P1 | common.py:450-520; error_catalog.py:251-253; benchmark.py:130-144; dead_asset.py:321-322; pr_synthesize.py:276-277; media_opt.py:141-196 | R50.1.3–R50.1.4, R50.2.17–R50.2.18 |
| F50-07 Attestation succeeds for missing/out-of-root subjects | P1 | attest.py:92-102, 135-217; test_attest.py:116-126 | R50.2.1–R50.2.2 |
| F50-08 License evidence is invented or executor-environment-dependent | P1 | license_matrix.py:237-246, 249-358; test_license_matrix.py:17-151 | R50.2.3–R50.2.4 |
| F50-09 IAM actions/resources are guessed and empty input fabricates S3 access | P0 | iam_audit.py:16-87, 151-157, 268-290; test_iam_audit.py:19-131; test_phase50_slsa_attestation.py:45-51 | R50.2.5–R50.2.6 |
| F50-10 Dynamic memory/cold-start execution is unapproved, injectable, and masks failures | P1 | mem_profile.py:146-265; cold_start.py:164-306; their tests | R50.2.7–R50.2.8 |
| F50-11 Offline ONNX path lacks decision, optional dependency, containment, mandatory checksum, slow permission, and truthful errors | P1 | offline_runner.py:68-242; pyproject.toml; uv.lock; test_offline_review.py | R50.2.9–R50.2.10 |
| F50-12 Media optimization destructively rewrites input and lacks explicit output/no-improvement behavior | P1 | media_opt.py:75-236; test_media_opt.py:51-69 | R50.2.11–R50.2.12 |
| F50-13 Dead-asset deletion lacks explicit versioned manifest, fresh rescan, no-follow, and uncertainty guards | P1 | dead_asset.py:142-211, 213-392; test_dead_asset.py:43-92 | R50.2.13–R50.2.14 |
| F50-14 PR synthesis hardcodes prohibited assurance and pass claims | P0 | pr_synthesize.py:32-47, 198-206; test_pr_synthesize.py:57-140; test_phase50_slsa_attestation.py:71-76 | R50.2.15–R50.2.16 |
| F50-15 Remaining feature suites do not prove governing core contracts | P1 | prompt_eval.py, error_catalog.py, provenance_ai.py, tui_diff.py, benchmark.py and corresponding tests | R50.2.19–R50.2.24 |
| F50-16 Fourteen-tool object/option/route/result parity is unproven | P1 | catalog.py, config.py, cli.py, mcp.py, tools/__init__.py; route tests | R50.3.1–R50.3.2 |
| F50-17 Public documentation retains unsafe and internally inconsistent claims | P1 | README.md:299-302; README2.md:222-225; README3.md:558-561; docs/AGENTIC_RUSH.md:140-144; docs/user-guide/working-with-ai-agents.md:153-158; docs/specs/slsa-attestation-spec.md:1-8 | R50.3.3 |
| F50-18 Packaging test is not an installed-artifact test; wheel evidence is absent | P1 | test_phase50_packaging.py:8-88; evidence:319-320; plan:2555-2589 | R50.4.1–R50.4.2 |
| F50-19 Per-card RED/GREEN/effect/route evidence is absent | P1 | evidence:87-237; all P50 tests versus plan contract inventory | Every RED/GREEN pair; R50.4.3 |

## 7. File and dependency governance

### 7.1 Files admitted for remediation

Only a task card may write the exact files listed in its `Allowed writes`. The complete potential remediation surface is:

- `src/rush/tools/common.py`
- `src/rush/tools/prompt_eval.py`
- `src/rush/tools/error_catalog.py`
- `src/rush/tools/provenance_ai.py`
- `src/rush/tools/attest.py`
- `src/rush/tools/license_matrix.py`
- `src/rush/tools/iam_audit.py`
- `src/rush/tools/mem_profile.py`
- `src/rush/tools/cold_start.py`
- `src/rush/tools/media_opt.py`
- `src/rush/tools/offline_runner.py`
- `src/rush/tools/tui_diff.py`
- `src/rush/tools/benchmark.py`
- `src/rush/tools/dead_asset.py`
- `src/rush/tools/pr_synthesize.py`
- `src/rush/tools/__init__.py`
- `src/rush/catalog.py`
- `src/rush/config.py`
- `src/rush/cli.py`
- `src/rush/mcp.py`
- The exact matching test files named by each RED card.
- `pyproject.toml` and `uv.lock` only after an explicit D50-04 or D50-08 dependency disposition authorizes exact changes.
- The exact public documentation/configuration anchors named by R50.3.3.
- `docs/developer/phase-50-implementation-evidence.md` only in R50.0.4, R50.4.2, and R50.4.3.
- This remediation plan only if audit discoveries require a user-approved amendment.

### 7.2 Files not admitted

The following current changes have no P50 remediation owner and must be restored to their pre-P50 bytes unless the user explicitly approves a plan amendment:

- `docs/API_REFERENCE.md`, `docs/GLOSSARY.md`, `docs/README.md`.
- Benchmarking and innovation-enhancement reports unrelated to exact active P50 anchors.
- `docs/vibecoding/token-diet-for-vibecoders.md`.
- `docs/developer/brainstorm-*`, `configuration-development.md`, `integrations-scope-plan.md`, `master-*plan.md`, `mcp-development.md`, and `vibecoder-toolkit-plan.md`.
- Every modified `docs/developer/phase-20*` through `phase-49*` plan/report.
- Every modified `docs/phase-plans/phase-41*` through `phase-49*` plan.
- `tests/test_phase00_catalog_maturity.py`.
- Any file not explicitly listed in a task card.

Restoration must be done from the accepted baseline bytes, never with a broad destructive reset and never by overwriting unrelated user changes.

### 7.3 Dependency rules

- No dependency change is admitted by default.
- D50-04 must name the exact pinned `onnxruntime` optional extra and fixture contract before `pyproject.toml` or `uv.lock` changes.
- D50-08 must name the exact pinned `psutil` optional extra and sampling contract before dependency changes.
- If either decision defers its runtime, production code, config, routes, docs, and tests for that optional behavior must be removed from the admitted Phase 50 change set rather than left as an undocumented dynamic import.
- `cryptography` already exists in the baseline dependency set; Phase 50 may not claim that its presence authorizes signed/SLSA assurances.
- Every dependency mutation requires `uv lock --check` plus offline isolated-wheel installation evidence.

## 8. Execution phases and dependencies

1. **Phase R50.0 — Admission and evidence reset.** Establish exact ownership, record decisions, remove unowned churn, and correct false completion evidence.
2. **Phase R50.1 — Shared contracts.** Repair typed options/config precedence, atomic output, and route foundations before feature GREEN work.
3. **Phase R50.2 — Feature correctness and effects.** Execute one RED/GREEN pair per finding group. Decision-blocked pairs remain stopped.
4. **Phase R50.3 — Cross-feature integration and documentation.** Prove all admitted tools through the same object and exact public surfaces; correct only active claims.
5. **Phase R50.4 — Installed artifact and final evidence.** Author probes separately, independently rebuild/install, then run the final gate at one revision.

No later phase may begin merely because a broad suite passes. Every prerequisite card must have its named evidence.

### 8.1 Literal execution matrix

The following commands are part of the named cards. “Run the focused tests” in a card means run its exact row below from `C:/Users/james/developer/rush-cli/.worktrees/phase50-implementation` after clearing `VIRTUAL_ENV` and `PYTHONPATH`. A future executor may not replace a row with a broader command, omit a command, or interpret a broad-suite pass as the required focused RED/GREEN evidence.

| Cards | Literal focused test command | Literal quality commands for GREEN |
|---|---|---|
| R50.1.1–R50.1.2 | `& 'C:/Users/james/developer/rush-cli/.venv/Scripts/python.exe' -m pytest tests/test_catalog.py tests/test_config.py tests/test_cli_registry.py tests/test_mcp.py -q` | `& 'C:/Users/james/developer/rush-cli/.venv/Scripts/ruff.exe' check src/rush/catalog.py src/rush/config.py src/rush/cli.py src/rush/mcp.py tests/test_catalog.py tests/test_config.py tests/test_cli_registry.py tests/test_mcp.py`; then the same paths with `ruff.exe format --check` |
| R50.1.3–R50.1.4 | `& 'C:/Users/james/developer/rush-cli/.venv/Scripts/python.exe' -m pytest tests/test_tool_common.py -q` | `& 'C:/Users/james/developer/rush-cli/.venv/Scripts/ruff.exe' check src/rush/tools/common.py tests/test_tool_common.py`; then the same paths with `ruff.exe format --check` |
| R50.1.5–R50.1.6 | `& 'C:/Users/james/developer/rush-cli/.venv/Scripts/python.exe' -m pytest tests/test_cli_registry.py tests/test_mcp.py -q` | `& 'C:/Users/james/developer/rush-cli/.venv/Scripts/ruff.exe' check src/rush/cli.py src/rush/mcp.py tests/test_cli_registry.py tests/test_mcp.py`; then the same paths with `ruff.exe format --check` |
| R50.2.1–R50.2.2 | `& 'C:/Users/james/developer/rush-cli/.venv/Scripts/python.exe' -m pytest tests/test_attest.py tests/test_phase50_slsa_attestation.py -q` | `& 'C:/Users/james/developer/rush-cli/.venv/Scripts/ruff.exe' check src/rush/tools/attest.py tests/test_attest.py tests/test_phase50_slsa_attestation.py`; then the same paths with `ruff.exe format --check` |
| R50.2.3–R50.2.4 | `& 'C:/Users/james/developer/rush-cli/.venv/Scripts/python.exe' -m pytest tests/test_license_matrix.py tests/test_phase50_slsa_attestation.py -q` | `& 'C:/Users/james/developer/rush-cli/.venv/Scripts/ruff.exe' check src/rush/tools/license_matrix.py tests/test_license_matrix.py tests/test_phase50_slsa_attestation.py`; then the same paths with `ruff.exe format --check` |
| R50.2.5–R50.2.6 | `& 'C:/Users/james/developer/rush-cli/.venv/Scripts/python.exe' -m pytest tests/test_iam_audit.py tests/test_phase50_slsa_attestation.py -q` | `& 'C:/Users/james/developer/rush-cli/.venv/Scripts/ruff.exe' check src/rush/tools/iam_audit.py tests/test_iam_audit.py tests/test_phase50_slsa_attestation.py`; then the same paths with `ruff.exe format --check` |
| R50.2.7–R50.2.8 | `& 'C:/Users/james/developer/rush-cli/.venv/Scripts/python.exe' -m pytest tests/test_mem_profile.py tests/test_cold_start.py -q` | `& 'C:/Users/james/developer/rush-cli/.venv/Scripts/ruff.exe' check src/rush/tools/mem_profile.py src/rush/tools/cold_start.py tests/test_mem_profile.py tests/test_cold_start.py`; then the same paths with `ruff.exe format --check`; then `uv lock --check` when manifest/lock changes are admitted |
| R50.2.9–R50.2.10 | `& 'C:/Users/james/developer/rush-cli/.venv/Scripts/python.exe' -m pytest tests/test_offline_review.py -q` | `& 'C:/Users/james/developer/rush-cli/.venv/Scripts/ruff.exe' check src/rush/tools/offline_runner.py tests/test_offline_review.py`; then the same paths with `ruff.exe format --check`; then `uv lock --check` |
| R50.2.11–R50.2.12 | `& 'C:/Users/james/developer/rush-cli/.venv/Scripts/python.exe' -m pytest tests/test_media_opt.py -q` | `& 'C:/Users/james/developer/rush-cli/.venv/Scripts/ruff.exe' check src/rush/tools/media_opt.py tests/test_media_opt.py`; then the same paths with `ruff.exe format --check` |
| R50.2.13–R50.2.14 | `& 'C:/Users/james/developer/rush-cli/.venv/Scripts/python.exe' -m pytest tests/test_dead_asset.py -q` | `& 'C:/Users/james/developer/rush-cli/.venv/Scripts/ruff.exe' check src/rush/tools/dead_asset.py tests/test_dead_asset.py`; then the same paths with `ruff.exe format --check` |
| R50.2.15–R50.2.16 | `& 'C:/Users/james/developer/rush-cli/.venv/Scripts/python.exe' -m pytest tests/test_pr_synthesize.py tests/test_phase50_slsa_attestation.py -q` | `& 'C:/Users/james/developer/rush-cli/.venv/Scripts/ruff.exe' check src/rush/tools/pr_synthesize.py tests/test_pr_synthesize.py tests/test_phase50_slsa_attestation.py`; then the same paths with `ruff.exe format --check` |
| R50.2.17–R50.2.18 | `& 'C:/Users/james/developer/rush-cli/.venv/Scripts/python.exe' -m pytest tests/test_error_catalog.py tests/test_benchmark.py -q` | `& 'C:/Users/james/developer/rush-cli/.venv/Scripts/ruff.exe' check src/rush/tools/error_catalog.py src/rush/tools/benchmark.py tests/test_error_catalog.py tests/test_benchmark.py`; then the same paths with `ruff.exe format --check` |
| R50.2.19–R50.2.20 | `& 'C:/Users/james/developer/rush-cli/.venv/Scripts/python.exe' -m pytest tests/test_prompt_eval.py -q` | `& 'C:/Users/james/developer/rush-cli/.venv/Scripts/ruff.exe' check src/rush/tools/prompt_eval.py tests/test_prompt_eval.py`; then the same paths with `ruff.exe format --check` |
| R50.2.21–R50.2.22 | `& 'C:/Users/james/developer/rush-cli/.venv/Scripts/python.exe' -m pytest tests/test_error_catalog.py tests/test_provenance_ai.py -q` | `& 'C:/Users/james/developer/rush-cli/.venv/Scripts/ruff.exe' check src/rush/tools/error_catalog.py src/rush/tools/provenance_ai.py tests/test_error_catalog.py tests/test_provenance_ai.py`; then the same paths with `ruff.exe format --check` |
| R50.2.23–R50.2.24 | `& 'C:/Users/james/developer/rush-cli/.venv/Scripts/python.exe' -m pytest tests/test_tui_diff.py tests/test_benchmark.py -q` | `& 'C:/Users/james/developer/rush-cli/.venv/Scripts/ruff.exe' check src/rush/tools/tui_diff.py src/rush/tools/benchmark.py tests/test_tui_diff.py tests/test_benchmark.py`; then the same paths with `ruff.exe format --check` |
| R50.3.1–R50.3.2 | `& 'C:/Users/james/developer/rush-cli/.venv/Scripts/python.exe' -m pytest tests/test_catalog.py tests/test_config.py tests/test_cli_registry.py tests/test_mcp.py tests/test_phase50_slsa_attestation.py -q` | `& 'C:/Users/james/developer/rush-cli/.venv/Scripts/ruff.exe' check src/rush/tools/__init__.py src/rush/catalog.py src/rush/config.py src/rush/cli.py src/rush/mcp.py tests/test_catalog.py tests/test_config.py tests/test_cli_registry.py tests/test_mcp.py tests/test_phase50_slsa_attestation.py`; then the same paths with `ruff.exe format --check` |
| R50.4.1 | `& 'C:/Users/james/developer/rush-cli/.venv/Scripts/python.exe' -m pytest tests/test_phase50_packaging.py::test_phase50_modules_are_present_in_built_wheel tests/test_phase50_packaging.py::test_phase50_installed_cli_help_and_mcp_catalog_match_source_contract -q`; then `& 'C:/Users/james/developer/rush-cli/.venv/Scripts/python.exe' -m pytest tests/test_phase50_packaging.py -q` | `& 'C:/Users/james/developer/rush-cli/.venv/Scripts/ruff.exe' check tests/test_phase50_packaging.py`; then `& 'C:/Users/james/developer/rush-cli/.venv/Scripts/ruff.exe' format --check tests/test_phase50_packaging.py` |

Every GREEN card additionally runs `& 'C:/Users/james/developer/rush-cli/.venv/Scripts/python.exe' -m pytest tests/ --ignore=tests/test_phase50_packaging.py -q` after its focused row. RED cards must stop after recording the intended focused failure and must not run a GREEN repair.

### 8.2 Literal documentation, packaging, and final-gate commands

R50.3.3 runs this exact residual-claim command after its focused feature/integration suites:

`rg -n 'SLSA Level|Level 3|signed|cryptographic provenance|trusted builder|reproducible|copyleft compliance|viral license|zero risk|compatible|least privilege|minimal permissions|deployment ready|Resource: "\*"|all tests pass|100%|coverage|breaking changes|Architecture Guard|reviewer|risk score|blast radius|GitHub API|zero loss|AVIF|full-screen|interactive TUI|statistically significant|prompt-eval|error-catalog|provenance-ai|attest|license-matrix|iam-audit|mem-profile|cold-start|media-opt|offline-review|tui-diff|benchmark|dead-asset|pr-synthesize' README.md README2.md README3.md docs/AGENTIC_RUSH.md docs/ARCHITECTURE.md docs/developer/architecture.md docs/user-guide/working-with-ai-agents.md docs/CLI_REFERENCE.md docs/MCP_REFERENCE.md docs/CONFIGURATION.md docs/TOOL_CATALOG.md docs/SECURITY.md docs/specs/slsa-attestation-spec.md docs/tools examples/rush.toml`

R50.4.1 and R50.4.2 use this exact isolated build/install sequence from the implementation worktree:

1. `Remove-Item Env:VIRTUAL_ENV -ErrorAction SilentlyContinue`
2. `Remove-Item Env:PYTHONPATH -ErrorAction SilentlyContinue`
3. `$p50rWorktree = (Resolve-Path .).Path`
4. `$p50rDist = [System.IO.Path]::GetFullPath((Join-Path $p50rWorktree '.rush/phase50-dist'))`
5. `if (-not $p50rDist.StartsWith($p50rWorktree + [System.IO.Path]::DirectorySeparatorChar, [System.StringComparison]::OrdinalIgnoreCase)) { throw "phase50-dist escaped worktree" }`
6. `Remove-Item -LiteralPath $p50rDist -Recurse -Force -ErrorAction SilentlyContinue`
7. `uv build --out-dir $p50rDist`
8. `$p50rWheels = @(Get-ChildItem -LiteralPath $p50rDist -Filter 'rush*.whl' -File)`
9. `if ($p50rWheels.Count -ne 1) { throw "expected exactly one Rush wheel" }`
10. `$p50rWheel = $p50rWheels[0].FullName`
11. `uv export --frozen --no-dev --no-emit-project --format requirements-txt --output-file .rush/phase50-runtime-requirements.txt`
12. `uv venv --clear .rush/phase50-wheel-venv`
13. `uv pip install --python .rush/phase50-wheel-venv/Scripts/python.exe --offline -r .rush/phase50-runtime-requirements.txt`
14. `uv pip install --python .rush/phase50-wheel-venv/Scripts/python.exe --offline --no-deps $p50rWheel`
15. `$env:RUSH_PHASE50_WHEEL = $p50rWheel`
16. `$env:RUSH_PHASE50_PYTHON = (Resolve-Path .rush/phase50-wheel-venv/Scripts/python.exe).Path`

R50.4.2 then runs, in order:

1. `& 'C:/Users/james/developer/rush-cli/.venv/Scripts/python.exe' -m pytest tests/test_phase50_packaging.py -q`
2. `.rush/phase50-wheel-venv/Scripts/rush.exe --version`
3. `.rush/phase50-wheel-venv/Scripts/rush.exe --help`
4. `Get-FileHash -Algorithm SHA256 -LiteralPath $p50rWheel`
5. `git status --short --branch`

R50.4.3 runs this exact final gate in order, after repeating the isolated build/install sequence above:

1. `& 'C:/Users/james/developer/rush-cli/.venv/Scripts/python.exe' --version`
2. `& 'C:/Users/james/developer/rush-cli/.venv/Scripts/python.exe' -m pytest tests/test_tool_common.py tests/test_prompt_eval.py tests/test_error_catalog.py tests/test_provenance_ai.py tests/test_attest.py tests/test_license_matrix.py tests/test_iam_audit.py tests/test_mem_profile.py tests/test_cold_start.py tests/test_media_opt.py tests/test_offline_review.py tests/test_tui_diff.py tests/test_benchmark.py tests/test_dead_asset.py tests/test_pr_synthesize.py tests/test_phase50_slsa_attestation.py -q`
3. `& 'C:/Users/james/developer/rush-cli/.venv/Scripts/python.exe' -m pytest tests/test_catalog.py tests/test_config.py tests/test_cli_registry.py tests/test_mcp.py -q`
4. `& 'C:/Users/james/developer/rush-cli/.venv/Scripts/python.exe' -m pytest tests/ --ignore=tests/test_phase50_packaging.py -q`
5. `& 'C:/Users/james/developer/rush-cli/.venv/Scripts/ruff.exe' check src tests scripts`
6. `& 'C:/Users/james/developer/rush-cli/.venv/Scripts/ruff.exe' format --check src tests scripts`
7. `uv lock --check`
8. `& 'C:/Users/james/developer/rush-cli/.venv/Scripts/python.exe' -m pytest tests/test_phase50_packaging.py -q`
9. `.rush/phase50-wheel-venv/Scripts/rush.exe --version`
10. `.rush/phase50-wheel-venv/Scripts/rush.exe --help`
11. `Get-FileHash -Algorithm SHA256 -LiteralPath $p50rWheel`
12. `git diff --check`
13. `git diff --name-only`
14. `git status --short --branch`

## 9. Task cards

### Phase R50.0 — Admission, isolation, and evidence reset

#### R50.0.1 — VERIFY: freeze the audited baseline and path ownership

- **Task ID and binary outcome:** R50.0.1; every current changed path is classified as admitted P50 work, unrelated pre-existing work, generated audit artifact, or unowned churn.
- **Start goal:** Prevent remediation from silently absorbing unrelated changes.
- **Prerequisites:** Explicit user authority to begin remediation in a non-main worktree.
- **Documentation impact:** None.
- **Dependency impact:** None.
- **Allowed writes:** `docs/developer/phase-50-implementation-evidence.md` only, under a new `Remediation admission / R50.0.1` section.
- **Allowed reads:** `git status --short --branch`, `git diff --name-status`, `git diff --numstat`, governing plan, this plan, existing evidence.
- **Prohibited:** Production/test/public-doc edits; resets; checkout restoration; commit/merge/tag/push.
- **Actions:**
  1. Capture branch, HEAD, worktree root, dirty paths, diff-check result, and generated ignored audit paths; compare all paths to section 7.
  2. Append a path table with one classification and one prospective task owner per path; mark every other path `UNOWNED—STOP`.
  3. Run `git diff --check`, `git status --short --branch`, and `git diff --name-only`; record literal outputs and exits.
- **Evidence:** One path-complete ledger whose row count equals the changed-path count.
- **Stop:** Main checkout, overlapping unknown user edits, missing path, or a path assigned to multiple tasks.
- **Verified outcome:** R50.0.2 and R50.0.3 may start; no feature implementation is admitted.

#### R50.0.2 — DECISION: record every governing user disposition

- **Task ID and binary outcome:** R50.0.2; D50-04, D50-07, D50-08, and D50-10 through D50-18 each have an explicit user-approved value or explicit defer/remove result.
- **Start goal:** Eliminate fabricated approvals and conditional ambiguity.
- **Prerequisites:** R50.0.1; direct user decisions.
- **Documentation impact:** Amend only the governing plan decision table and requirement matrix.
- **Dependency impact:** Record exact dependency result; do not edit manifests here.
- **Allowed writes:** `docs/phase-plans/phase-50-slsa-attestation-security-suite-flagship-plan.md` only.
- **Allowed reads:** Governing plan, this plan, user decision message.
- **Prohibited:** Inferring approval from existing code/evidence; source/test/config/public-doc edits.
- **Actions:**
  1. Copy each user disposition verbatim into the matching decision row, including exact values, exclusions, dependency constraints, deferred owner, and affected task packets.
  2. Update only the requirement/task admission cells whose status follows mechanically from those decisions.
  3. Re-read every D50 row and verify no `Open` row is described as implemented or approved elsewhere in the governing plan.
- **Evidence:** Decision-to-packet matrix with user-message reference.
- **Stop:** Any required decision is missing, ambiguous, internally inconsistent, or expands beyond the authored task packets.
- **Verified outcome:** Only packets explicitly admitted by the recorded decisions may proceed.

#### R50.0.3 — SCOPE: restore unowned paths and whitespace-clean admitted docs

- **Task ID and binary outcome:** R50.0.3; the worktree contains no unowned P50 path and `git diff --check` passes.
- **Start goal:** Remove broad unrelated churn without disturbing user-owned changes.
- **Prerequisites:** R50.0.1 path ledger and explicit user authority to restore the exact unowned paths.
- **Documentation impact:** Restore unowned documents to accepted baseline bytes; fix only P50-owned EOF whitespace.
- **Dependency impact:** None.
- **Allowed writes:** Only paths marked `UNOWNED—RESTORE` in R50.0.1 and the five P50-owned whitespace paths: `docs/CONFIGURATION.md`, `docs/GLOSSARY.md`, `docs/MCP_REFERENCE.md`, `docs/SECURITY.md`, `examples/rush.toml`.
- **Allowed reads:** Baseline blobs at `1fb3582`, path ledger, current bytes.
- **Prohibited:** Broad reset/checkout commands; modifying admitted P50 content; touching unknown user-owned paths.
- **Actions:**
  1. Compare every restore candidate against baseline and confirm its entire current diff is unowned P50 churn.
  2. Restore exact baseline bytes path by path; remove only the extra EOF blank line from admitted P50 documents.
  3. Run `git diff --check` and regenerate the path ledger; verify no restored path remains and no admitted path changed unexpectedly.
- **Evidence:** Before/after hashes, restored path list, clean diff-check.
- **Stop:** A candidate contains unrelated user work or its baseline is uncertain.
- **Verified outcome:** The remaining change set is mechanically owned.

#### R50.0.4 — EVIDENCE: retract false completion and corrupt records

- **Task ID and binary outcome:** R50.0.4; the evidence file is a truthful incomplete remediation record with no fabricated approvals, control characters, invalid RED claims, or completion assurance.
- **Start goal:** Prevent downstream agents from treating invalid evidence as authority.
- **Prerequisites:** R50.0.1; R50.0.2 may be incomplete but its open decisions must be stated.
- **Documentation impact:** Replace only false/corrupt evidence sections; preserve independently reproduced command facts.
- **Dependency impact:** State current manifest/lock facts without claiming selected optional runtimes.
- **Allowed writes:** `docs/developer/phase-50-implementation-evidence.md` only.
- **Allowed reads:** Governing plan, this plan, current source/tests, R50.0.1 outputs.
- **Prohibited:** Production/test/public-doc edits; calling collection errors RED; claiming wheel isolation or full completion.
- **Actions:**
  1. Remove control characters and replace unsupported decision approvals, feature completion, dependency, wheel, route, TDD, and successor-handoff claims with explicit `unverified` or `blocked` records.
  2. Preserve only commands actually reproduced with exact exit/result; add the audit’s 113-pass, 933-pass, Ruff, lock, build, packaging-test weakness, and diff-check facts.
  3. Add an open-finding list keyed F50-01 through F50-19 and state that no current GREEN is accepted without the paired remediation RED.
- **Evidence:** Clean UTF-8 file, claim-to-source review, no completion wording.
- **Stop:** Any statement cannot be tied to a command, source span, user decision, or governing requirement.
- **Verified outcome:** Remediation can proceed without relying on false historical TDD evidence.

### Phase R50.1 — Shared contracts

#### R50.1.1 — RED: pin immutable typed options and precedence

- **Task ID and binary outcome:** R50.1.1; named tests collect and fail because P50 options are mutable/incomplete and config/default/explicit precedence is not applied.
- **Start goal:** Define the shared configuration contract before modifying parser or routes.
- **Prerequisites:** R50.0.2 admits at least one P50 packet; R50.0.3.
- **Documentation impact:** None.
- **Dependency impact:** None.
- **Allowed writes:** `tests/test_catalog.py`, `tests/test_config.py`, `tests/test_cli_registry.py`, `tests/test_mcp.py`.
- **Allowed reads:** `src/rush/catalog.py`, `config.py`, `cli.py`, `mcp.py`, admitted tool signatures, configuration snippets.
- **Prohibited:** Production/docs edits; broad smoke assertions; mutation of tests in R50.1.2.
- **Actions:**
  1. Add `test_phase50_option_specs_cover_every_admitted_behavior` and a literal expected option/type/default table for each admitted tool.
  2. Add `test_tool_config_options_are_immutable_and_precedence_is_default_config_explicit`, including rejected unknown keys, invalid coercions, config-only values, and explicit override.
  3. Add CLI/MCP seam tests proving resolved typed values and permissions reach the same fake registered object; run only these tests and retain assertion failures, not import failures.
- **Evidence:** Test hashes and failure output naming missing option, mutability, or forwarding.
- **Stop:** A decision leaves an option’s type/default/public name undefined.
- **Verified outcome:** R50.1.2 may start with tests unchanged.

#### R50.1.2 — GREEN: implement typed resolution once

- **Task ID and binary outcome:** R50.1.2; immutable options and default→config→explicit precedence pass through one shared resolver.
- **Start goal:** Satisfy R50.1.1 without feature-specific transport logic.
- **Prerequisites:** R50.1.1 valid RED.
- **Documentation impact:** None.
- **Dependency impact:** None.
- **Allowed writes:** `src/rush/catalog.py`, `src/rush/config.py`, and the smallest shared invocation seam in `src/rush/cli.py` and `src/rush/mcp.py`.
- **Allowed reads:** Unchanged R50.1.1 tests and admitted tool signatures.
- **Prohibited:** Test/tool/public-doc edits; dedicated feature behavior in transports.
- **Actions:**
  1. Make `ToolConfig.options` immutable and declare every admitted option with exact type, default, CLI/MCP name, and permission semantics.
  2. Implement one resolver that validates/coerces once and merges catalog default, parsed config, then explicit invocation.
  3. Run the focused tests, `tests/test_catalog.py tests/test_config.py tests/test_cli_registry.py tests/test_mcp.py`, Ruff check, and format check.
- **Evidence:** Unchanged test hashes, green outputs, one-resolver source inspection.
- **Stop:** A transport must interpret a feature option or an undeclared key remains documented.
- **Verified outcome:** Feature and route tasks may consume typed values.

#### R50.1.3 — RED: pin no-follow atomic replacement and failure preservation

- **Task ID and binary outcome:** R50.1.3; shared helper tests fail on intermediate symlink substitution/race or old-output preservation.
- **Start goal:** Define the only admissible file-write primitive.
- **Prerequisites:** R50.0.3.
- **Documentation impact:** None.
- **Dependency impact:** None.
- **Allowed writes:** `tests/test_tool_common.py` only.
- **Allowed reads:** `src/rush/tools/common.py` and platform filesystem behavior.
- **Prohibited:** Production/caller edits; tests that require privileged global filesystem state.
- **Actions:**
  1. Add tests for relative-only targets, existing intermediate symlink, target symlink, parent substitution at the pre-replace seam, and containment after parent creation.
  2. Add deterministic replace-failure tests proving prior bytes survive and all temporary files are removed.
  3. Run the named tests on the current platform and retain the exact failing security assertion.
- **Evidence:** Test hashes, failure output, platform note.
- **Stop:** The repository cannot support the claimed no-follow guarantee on a platform; then narrow the claim through a user-approved amendment.
- **Verified outcome:** R50.1.4 may start.

#### R50.1.4 — GREEN: harden the sole atomic output primitive

- **Task ID and binary outcome:** R50.1.4; the helper meets R50.1.3 on supported platforms or returns a structured refusal before writing.
- **Start goal:** Satisfy the shared effect boundary once.
- **Prerequisites:** R50.1.3 valid RED.
- **Documentation impact:** None.
- **Dependency impact:** None.
- **Allowed writes:** `src/rush/tools/common.py` only.
- **Allowed reads:** Unchanged `tests/test_tool_common.py`.
- **Prohibited:** Caller/test/docs edits; weakening no-follow claims.
- **Actions:**
  1. Implement descriptor/handle-relative or equivalently race-resistant parent validation and replacement; reject absolute/traversal/symlink targets.
  2. Preserve old target bytes on every pre-replace/replace failure and clean temporary files.
  3. Run `tests/test_tool_common.py`, the full suite, Ruff check, and format check.
- **Evidence:** Unchanged test hashes and green output.
- **Stop:** Any path can be redirected outside root or a failure destroys prior output.
- **Verified outcome:** Feature effect GREEN cards may use the helper.

#### R50.1.5 — RED: pin benchmark surface and attestation alias semantics

- **Task ID and binary outcome:** R50.1.5; route tests fail on benchmark collision, wrong alias arguments/metadata, or obsolete manual wrappers.
- **Start goal:** Define the two known shared-route defects before registrar edits.
- **Prerequisites:** R50.1.2.
- **Documentation impact:** None.
- **Dependency impact:** None.
- **Allowed writes:** `tests/test_cli_registry.py`, `tests/test_mcp.py`.
- **Allowed reads:** `src/rush/cli.py`, `mcp.py`, catalog and registered tool objects.
- **Prohibited:** Production/core/docs edits.
- **Actions:**
  1. Add a benchmark help/invocation test for the D50-17-approved syntax, samples/record/threshold forwarding, and no replacement of the pre-existing benchmark group.
  2. Add an MCP test invoking `rush_attest_generate` and canonical `rush_attest` with equivalent logical arguments; require equal subject/digest and `metadata.deprecated=true` plus `replace_with="rush_attest"` only on the alias.
  3. Add source/registry assertions that no normalized-name manual wrapper or ad-hoc noncanonical fallback remains.
- **Evidence:** Named failures and test hashes.
- **Stop:** D50-17 or alias argument semantics are not explicit.
- **Verified outcome:** R50.1.6 may start.

#### R50.1.6 — GREEN: remove route collisions and retain only the correct alias

- **Task ID and binary outcome:** R50.1.6; benchmark has one selected CLI surface and MCP retains only a semantically equivalent deprecated attestation alias.
- **Start goal:** Satisfy R50.1.5 through thin transport adapters.
- **Prerequisites:** R50.1.5 valid RED.
- **Documentation impact:** None.
- **Dependency impact:** None.
- **Allowed writes:** `src/rush/cli.py`, `src/rush/mcp.py`.
- **Allowed reads:** Unchanged R50.1.5 tests, catalog, registered objects.
- **Prohibited:** Tool behavior/test/docs edits; manual license/IAM/dead/pr wrappers.
- **Actions:**
  1. Route benchmark through the approved group/subcommand or noncolliding command and forward all typed values to the registered `BenchmarkTool`.
  2. Normalize alias arguments to canonical attest arguments, call the registered object, and add only deprecation metadata to the returned envelope.
  3. Remove dead manual Phase 50 wrappers/fallbacks and run focused route tests plus full catalog/config/CLI/MCP suites.
- **Evidence:** Object identity, route list, equality result, green outputs.
- **Stop:** Duplicate object/business logic or any public route changes beyond the approved surfaces.
- **Verified outcome:** Cross-feature integration can build on stable shared routes.

### Phase R50.2 — Feature correctness and effects

#### R50.2.1 — RED: reject nonexistent, external, and symlinked attestation subjects

- **Task ID and binary outcome:** R50.2.1; named tests fail because attestation currently succeeds for invalid subjects.
- **Start goal:** Pin truthful unsigned-draft subject behavior.
- **Prerequisites:** R50.1.4.
- **Documentation impact:** None.
- **Dependency impact:** None.
- **Allowed writes:** `tests/test_attest.py` only.
- **Allowed reads:** `src/rush/tools/attest.py` and governing PR50.5 contract.
- **Prohibited:** Production/docs/route edits; legacy-wrapper compatibility assertions not authorized by the plan.
- **Actions:**
  1. Add `test_attest_rejects_missing_artifact_and_unsupported_assurance` with missing, directory, absolute external, parent traversal, and symlink subjects.
  2. Add a positive contained-file test requiring exact digest, Statement v1, provenance v1 predicate, and `unsigned_draft` with no signature/level/completeness claim.
  3. Run the named tests and retain assertion failures.
- **Evidence:** Test hashes and failures.
- **Stop:** Subject root semantics are undefined.
- **Verified outcome:** R50.2.2 may start.

#### R50.2.2 — GREEN: construct drafts only from real contained subjects

- **Task ID and binary outcome:** R50.2.2; attestation returns success only for a real contained non-symlink file and writes only through the shared helper.
- **Start goal:** Satisfy R50.2.1 without adding assurance.
- **Prerequisites:** R50.2.1 valid RED.
- **Documentation impact:** None.
- **Dependency impact:** None.
- **Allowed writes:** `src/rush/tools/attest.py` only.
- **Allowed reads:** Unchanged `tests/test_attest.py`.
- **Prohibited:** Test/routes/docs edits; signing; Level claims; compatibility class retention unless separately authorized.
- **Actions:**
  1. Resolve and validate the subject under the requested root before reading or hashing.
  2. Return structured error for invalid subjects and emit only the unsigned statement for valid subjects; use shared atomic output for export.
  3. Run focused tests, Phase 50 shape tests, Ruff, and format.
- **Evidence:** Unchanged tests and green output.
- **Stop:** Any invalid subject yields `ok` or any stronger assurance appears.
- **Verified outcome:** Attestation core/effect is eligible for route verification.

#### R50.2.3 — RED: pin exact local license evidence and manual-review states

- **Task ID and binary outcome:** R50.2.3; tests fail because unresolved licenses are assigned MIT/copyleft conclusions or host metadata changes results.
- **Start goal:** Prevent legal/evidence invention.
- **Prerequisites:** D50-13 approval; R50.0.4.
- **Documentation impact:** None.
- **Dependency impact:** None.
- **Allowed writes:** `tests/test_license_matrix.py` only.
- **Allowed reads:** `src/rush/tools/license_matrix.py` and admitted D50-13 values.
- **Prohibited:** Production/docs edits; legal compatibility assertions.
- **Actions:**
  1. Add fixtures for exact SPDX, compound expressions, free text, absent package.json/Cargo metadata, absent Python metadata, and differing executor environments.
  2. Require unresolved/compound/free-text cases to be `manual_review` with source provenance; require exact allowlist matching only.
  3. Run named tests and retain failures on fabricated MIT/copyleft output.
- **Evidence:** Fixture hashes and failure output.
- **Stop:** Approved evidence sources or expression policy are undefined.
- **Verified outcome:** R50.2.4 may start.

#### R50.2.4 — GREEN: report license evidence without legal inference

- **Task ID and binary outcome:** R50.2.4; results are deterministic from local supplied evidence and unresolved cases remain manual review.
- **Start goal:** Satisfy R50.2.3.
- **Prerequisites:** R50.2.3 valid RED.
- **Documentation impact:** None.
- **Dependency impact:** None.
- **Allowed writes:** `src/rush/tools/license_matrix.py` only.
- **Allowed reads:** Unchanged tests.
- **Prohibited:** Test/routes/docs edits; executor-environment fallback; default MIT; “violation/compliant/zero risk” conclusions.
- **Actions:**
  1. Remove host `importlib.metadata` and default-license inference unless D50-13 expressly names a recorded local evidence source.
  2. Normalize only exact supported identifiers and preserve raw evidence/provenance for every row.
  3. Run focused tests, result-shape tests, Ruff, and format.
- **Evidence:** Deterministic repeated output and green tests.
- **Stop:** Same repository input differs by host environment.
- **Verified outcome:** License core is eligible for integration/docs.

#### R50.2.5 — RED: forbid guessed IAM actions, resources, providers, and empty defaults

- **Task ID and binary outcome:** R50.2.5; tests fail on fabricated actions/default S3/wildcard resources.
- **Start goal:** Establish the D50-07-approved finite truth boundary.
- **Prerequisites:** Explicit D50-07 approval containing exact map citations and resource policy; R50.0.4.
- **Documentation impact:** None.
- **Dependency impact:** None.
- **Allowed writes:** `tests/test_iam_audit.py`, `tests/test_phase50_slsa_attestation.py`.
- **Allowed reads:** `src/rush/tools/iam_audit.py` and exact D50-07 record.
- **Prohibited:** Production/docs edits; generated service:Pascal fallback; deployable-policy language.
- **Actions:**
  1. Add `test_iam_audit_maps_only_approved_operations_and_reports_unknowns` using every approved map row plus known-service unknown method and unsupported provider fixtures.
  2. Add `test_iam_audit_empty_or_unknown_resources_never_emit_wildcard_policy` requiring empty actions for empty input and manual-review findings when a literal resource cannot be proven.
  3. Replace current fake-default compatibility assertions and run named tests to capture failures.
- **Evidence:** Test hashes, approved mapping fixture/citation ledger, failure output.
- **Stop:** D50-07 is open or any action/resource rule lacks an authoritative citation.
- **Verified outcome:** R50.2.6 may start.

#### R50.2.6 — GREEN: emit only approved IAM evidence and nondeployable output

- **Task ID and binary outcome:** R50.2.6; IAM output contains only approved mapped actions with evidenced literal resources or explicit unsupported/manual-review records.
- **Start goal:** Satisfy R50.2.5.
- **Prerequisites:** R50.2.5 valid RED.
- **Documentation impact:** None.
- **Dependency impact:** None.
- **Allowed writes:** `src/rush/tools/iam_audit.py` only.
- **Allowed reads:** Unchanged tests and approved citation ledger.
- **Prohibited:** Test/routes/docs edits; default actions; wildcard resources; guessed method conversion; swallowed parse errors.
- **Actions:**
  1. Replace the embedded speculative map with the exact approved finite table and explicit unsupported results.
  2. Remove empty S3 defaults and `Resource: "*"`; omit policy or mark manual review when resource evidence is absent.
  3. Use the shared atomic helper for explicit export and run focused/security/result-shape tests, Ruff, and format.
- **Evidence:** Empty/unknown fixtures, exact action/resource outputs, green tests.
- **Stop:** Output could be mistaken for deployment-safe least privilege.
- **Verified outcome:** IAM core/effect may proceed to route/docs.

#### R50.2.7 — RED: pin safe dynamic memory and cold-start execution

- **Task ID and binary outcome:** R50.2.7; tests fail on interpolated target code, wrong interpreter, masked nonzero/malformed output, and false static close findings.
- **Start goal:** Define subprocess and static-analysis truth before dynamic changes.
- **Prerequisites:** D50-08 and D50-14 explicit approvals; R50.1.2.
- **Documentation impact:** None.
- **Dependency impact:** Tests use injected seams; no manifest edit.
- **Allowed writes:** `tests/test_mem_profile.py`, `tests/test_cold_start.py`.
- **Allowed reads:** Both tool modules, shared subprocess helper, approved decisions.
- **Prohibited:** Production/docs/routes/dependency edits; executing arbitrary real fixtures in RED.
- **Actions:**
  1. Add static fixtures for `with`, explicit `close()`, `finally` cleanup, escaped handles, and true leaks.
  2. Add injected dynamic tests for missing optional sampler, denied slow permission, filename quotes, exact project-Python argv, nonzero child, malformed output, timeout, and redacted bounded diagnostics.
  3. Run the named tests and retain intended failures.
- **Evidence:** Test hashes and seam-call/failure output.
- **Stop:** D50-08 sampler/interpreter/metric values or D50-14 interpreter contract are undefined.
- **Verified outcome:** R50.2.8 may start.

#### R50.2.8 — GREEN: make profiling static-truthful and dynamic-fail-closed

- **Task ID and binary outcome:** R50.2.8; static results model cleanup paths and dynamic paths run only approved argv/seams with truthful errors.
- **Start goal:** Satisfy R50.2.7.
- **Prerequisites:** R50.2.7 valid RED.
- **Documentation impact:** None.
- **Dependency impact:** Add exact optional `psutil` extra/lock only if D50-08 approved it; otherwise remove/defer dynamic memory code.
- **Allowed writes:** `src/rush/tools/mem_profile.py`, `src/rush/tools/cold_start.py`, and conditionally `pyproject.toml`/`uv.lock`.
- **Allowed reads:** Unchanged tests, shared subprocess helper, decision record.
- **Prohibited:** Test/routes/docs edits; `runpy` code interpolation; system-interpreter guessing; invented fallback metrics.
- **Actions:**
  1. Correct static resource lifecycle accounting and separate static from dynamic results.
  2. Invoke only the approved project interpreter/sampler with list argv, denied-by-default slow permission, bounded output, and structured nonzero/timeout/malformed errors.
  3. Run focused tests, `uv lock --check` if applicable, Ruff, format, and full suite.
- **Evidence:** Exact argv captures, dependency diff or explicit no-dependency disposition, green tests.
- **Stop:** Target code can alter the MCP process, filename becomes code, or child failure yields `ok`.
- **Verified outcome:** Static/dynamic packets are eligible only to the extent decisions admitted them.

#### R50.2.9 — RED: pin offline model containment, checksum, runtime, permission, and error behavior

- **Task ID and binary outcome:** R50.2.9; tests fail because arbitrary models run without the full approved contract.
- **Start goal:** Define I24 fail-closed behavior.
- **Prerequisites:** Explicit D50-04 values; R50.1.2.
- **Documentation impact:** None.
- **Dependency impact:** Record expected optional extra but do not edit manifests in RED.
- **Allowed writes:** `tests/test_offline_review.py` only.
- **Allowed reads:** `src/rush/tools/offline_runner.py`, D50-04 record, manifest/lock.
- **Prohibited:** Production/docs/routes/dependency edits; real network/download/model execution.
- **Actions:**
  1. Add tests for absent runtime, absent model, absolute/external/symlink model, missing/wrong checksum, missing license metadata, denied slow permission, and unapproved provider.
  2. Add injected session tests for socket/network denial, per-file inference exception, malformed tensor/output, deterministic ordering, and threshold boundaries.
  3. Require `skipped` only for approved absence cases and `error` for invalid/execution failures; run and retain failures.
- **Evidence:** Test hashes and failure output.
- **Stop:** D50-04 lacks any exact value.
- **Verified outcome:** R50.2.10 may start.

#### R50.2.10 — GREEN: enforce the admitted offline inference contract

- **Task ID and binary outcome:** R50.2.10; only a contained licensed checksum-verified model runs through the approved optional runtime with slow permission and zero-network seams.
- **Start goal:** Satisfy R50.2.9.
- **Prerequisites:** R50.2.9 valid RED.
- **Documentation impact:** None.
- **Dependency impact:** Add exact pinned optional runtime extra and lock entry only as approved.
- **Allowed writes:** `src/rush/tools/offline_runner.py` and conditionally `pyproject.toml`/`uv.lock`.
- **Allowed reads:** Unchanged tests and D50-04 record.
- **Prohibited:** Test/routes/docs edits; bundled/downloaded weights; unchecked models; suppressed inference exceptions.
- **Actions:**
  1. Enforce relative containment, non-symlink file, mandatory SHA-256/license metadata, approved providers, and slow permission before session creation.
  2. Isolate network seams and map every session/per-file/output failure truthfully.
  3. Run focused tests, optional-extra import tests, `uv lock --check`, Ruff, format, and full suite.
- **Evidence:** Manifest/lock diff, checksum fixture, no-network proof, green tests.
- **Stop:** Online resolution/download is required or any inference error is dropped.
- **Verified outcome:** Offline review may proceed to routes/docs.

#### R50.2.11 — RED: require explicit non-destructive media outputs

- **Task ID and binary outcome:** R50.2.11; tests fail because source media is overwritten and no-improvement/permission paths are wrong.
- **Start goal:** Define audit-first, source-preserving output behavior.
- **Prerequisites:** D50-15 approval; R50.1.4.
- **Documentation impact:** None.
- **Dependency impact:** None beyond locked Pillow.
- **Allowed writes:** `tests/test_media_opt.py` only.
- **Allowed reads:** `src/rush/tools/media_opt.py` and D50-15 record.
- **Prohibited:** Production/docs/routes edits; tests that accept in-place mutation.
- **Actions:**
  1. Replace destructive test expectations with denied/no-write, explicit relative output, traversal/absolute/symlink rejection, source-preservation, and replace-failure cases.
  2. Add measured-smaller and no-improvement fixtures for approved PNG/WebP outputs; require no output when candidate is not smaller.
  3. Add SVG sanitization assertions for explicit output only and run to retain failures.
- **Evidence:** Input/output hashes, test hashes, failure output.
- **Stop:** Approved formats or output naming are undefined.
- **Verified outcome:** R50.2.12 may start.

#### R50.2.12 — GREEN: generate only measured, contained media outputs

- **Task ID and binary outcome:** R50.2.12; media audit never mutates input and writes an approved explicit output only with permission and measured improvement.
- **Start goal:** Satisfy R50.2.11.
- **Prerequisites:** R50.2.11 valid RED.
- **Documentation impact:** None.
- **Dependency impact:** None.
- **Allowed writes:** `src/rush/tools/media_opt.py` only.
- **Allowed reads:** Unchanged tests.
- **Prohibited:** Test/routes/docs edits; in-place writes; AVIF/markup mutation/percentage guarantees.
- **Actions:**
  1. Separate read-only findings from explicit output operations and require artifact permission.
  2. Generate candidate bytes in memory, compare measured size/validity, then write via the shared helper only when approved.
  3. Return explicit `no_improvement`/skipped state without writing; run focused tests, Ruff, format, and full suite.
- **Evidence:** Source hash preservation, output byte/size proof, green tests.
- **Stop:** Source changes or a larger/equal candidate is written.
- **Verified outcome:** Media core/effect is eligible for integration/docs.

#### R50.2.13 — RED: pin explicit manifest-bound dead-asset pruning

- **Task ID and binary outcome:** R50.2.13; tests fail because pruning accepts implicit/stale/unsafe candidates.
- **Start goal:** Define deletion safety before any prune GREEN.
- **Prerequisites:** Separate D50-18 dead-asset approval; R50.1.4.
- **Documentation impact:** None.
- **Dependency impact:** None.
- **Allowed writes:** `tests/test_dead_asset.py` only.
- **Allowed reads:** `src/rush/tools/dead_asset.py` and approved D50-18 scope.
- **Prohibited:** Production/docs/routes edits; deleting outside temporary fixtures.
- **Actions:**
  1. Add manifest schema/version, explicit import, malformed/version mismatch, traversal/absolute/symlink, empty manifest, and permission-denied tests.
  2. Add fresh-rescan reference race, changed hash, uncertainty, referenced asset, and partial-failure retention tests.
  3. Require unchanged valid candidates only to be removed and run named tests to retain failures.
- **Evidence:** Manifest fixture hashes, pre/post tree, failure output.
- **Stop:** Deletion contract or supported asset/reference rules are undefined.
- **Verified outcome:** R50.2.14 may start.

#### R50.2.14 — GREEN: prune only unchanged explicit safe candidates

- **Task ID and binary outcome:** R50.2.14; prune requires an explicit versioned manifest, fresh rescan, contained no-follow path, matching hash, and artifact permission.
- **Start goal:** Satisfy R50.2.13.
- **Prerequisites:** R50.2.13 valid RED.
- **Documentation impact:** None.
- **Dependency impact:** None.
- **Allowed writes:** `src/rush/tools/dead_asset.py` only.
- **Allowed reads:** Unchanged tests.
- **Prohibited:** Test/routes/docs edits; implicit manifest generation during prune; deleting uncertain/referenced/changed/symlinked paths.
- **Actions:**
  1. Separate inventory/manifest creation from prune import and validate schema/version before effects.
  2. Re-resolve, no-follow validate, rescan references, and rehash immediately before each deletion; retain and report every unsafe candidate.
  3. Use contained effect helpers, run focused tests, Ruff, format, and full suite.
- **Evidence:** Per-candidate reason ledger and green tests.
- **Stop:** Any deletion lacks explicit manifest and unchanged-input proof.
- **Verified outcome:** Dead-asset core/effect is eligible for integration/docs.

#### R50.2.15 — RED: forbid inferred PR assurance, pass, risk, and reviewer claims

- **Task ID and binary outcome:** R50.2.15; tests fail because current PR Markdown fabricates claims.
- **Start goal:** Define observed-evidence-only rendering.
- **Prerequisites:** Separate D50-18 PR-synthesis approval; R50.1.4.
- **Documentation impact:** None.
- **Dependency impact:** None.
- **Allowed writes:** `tests/test_pr_synthesize.py`, `tests/test_phase50_slsa_attestation.py`.
- **Allowed reads:** `src/rush/tools/pr_synthesize.py` and approved D50-18 scope.
- **Prohibited:** Production/docs/routes edits; permissive “contains SLSA” assertions.
- **Actions:**
  1. Add tests with supplied warn/skipped/error ToolResults and `unsigned_draft` provenance; require exact observed values and no Level/signature/pass/coverage/compatibility/risk/reviewer claims.
  2. Add missing base, missing metric, absent evidence, untrusted text, deterministic ordering, and redaction cases.
  3. Add export permission/relative containment/atomic failure tests and run to retain failures.
- **Evidence:** Test hashes, forbidden-claim search, failure output.
- **Stop:** Supplied evidence schema or missing-state text is undefined.
- **Verified outcome:** R50.2.16 may start.

#### R50.2.16 — GREEN: render only supplied PR evidence and safe export

- **Task ID and binary outcome:** R50.2.16; PR Markdown is a deterministic rendering of verified Git facts and supplied ToolResults with explicit unknown states.
- **Start goal:** Satisfy R50.2.15.
- **Prerequisites:** R50.2.15 valid RED.
- **Documentation impact:** None.
- **Dependency impact:** None.
- **Allowed writes:** `src/rush/tools/pr_synthesize.py` only.
- **Allowed reads:** Unchanged tests.
- **Prohibited:** Test/routes/docs edits; legacy hardcoded template claims; GitHub API; inferred reviewer/risk/pass/coverage/blast.
- **Actions:**
  1. Remove all hardcoded assurance and pass content; validate and render only allowed evidence fields.
  2. Render unknown/missing explicitly, preserve `unsigned_draft`, redact unsafe text, and export through shared atomic output.
  3. Run focused tests, forbidden-claim search, Ruff, format, and full suite.
- **Evidence:** Exact Markdown snapshots, forbidden-claim zero/limited hits, green tests.
- **Stop:** Output can imply a fact not present in supplied evidence.
- **Verified outcome:** PR synthesis core/effect is eligible for integration/docs.

#### R50.2.17 — RED: pin remaining artifact/cache writes

- **Task ID and binary outcome:** R50.2.17; effect tests fail because error-catalog export and benchmark baseline store bypass atomic/failure-preserving behavior.
- **Start goal:** Close the remaining shared-effect callers independently of core behavior.
- **Prerequisites:** D50-11 and D50-17 approvals; R50.1.4.
- **Documentation impact:** None.
- **Dependency impact:** None.
- **Allowed writes:** `tests/test_error_catalog.py`, `tests/test_benchmark.py`.
- **Allowed reads:** Both tool modules and shared helper.
- **Prohibited:** Production/docs/routes edits; combining core behavior changes.
- **Actions:**
  1. Add relative/absolute/traversal/symlink/permission/replace-failure/idempotence tests for error-catalog export.
  2. Add cache-write permission, corrupt-store non-destruction, atomic replacement, deterministic names, and concurrent/replace-failure tests for benchmark baseline.
  3. Run named tests and retain failures with prior-output hashes.
- **Evidence:** Test hashes, prior/post output hashes, failure output.
- **Stop:** Baseline schema/location or export encoding is undefined.
- **Verified outcome:** R50.2.18 may start.

#### R50.2.18 — GREEN: migrate remaining writes to the shared effect boundary

- **Task ID and binary outcome:** R50.2.18; error-catalog and benchmark writes are explicit, permissioned, contained, atomic, and failure-preserving.
- **Start goal:** Satisfy R50.2.17.
- **Prerequisites:** R50.2.17 valid RED.
- **Documentation impact:** None.
- **Dependency impact:** None.
- **Allowed writes:** `src/rush/tools/error_catalog.py`, `src/rush/tools/benchmark.py`.
- **Allowed reads:** Unchanged tests and shared helper.
- **Prohibited:** Test/routes/docs edits; resetting corrupt baseline to an empty store.
- **Actions:**
  1. Route exports/store replacement through the shared helper with relative paths and exact permissions.
  2. Return structured error on corrupt store or replacement failure while preserving prior bytes.
  3. Run focused tests, Ruff, format, and full suite.
- **Evidence:** Old-output preservation and green tests.
- **Stop:** Any implicit write or destructive corruption recovery remains.
- **Verified outcome:** Remaining feature-core tests may proceed.

#### R50.2.19 — RED: pin recorded prompt-evaluation truth

- **Task ID and binary outcome:** R50.2.19; named tests fail on any unapproved live/provider behavior, ambiguous missing fields, nondeterminism, or incorrect threshold/status.
- **Start goal:** Recover PR50.2 as a bounded recorded-run tool.
- **Prerequisites:** D50-10 approval; R50.1.2.
- **Documentation impact:** None.
- **Dependency impact:** None.
- **Allowed writes:** `tests/test_prompt_eval.py` only.
- **Allowed reads:** `src/rush/tools/prompt_eval.py` and approved D50-10 record.
- **Prohibited:** Production/docs/routes edits; network/model calls.
- **Actions:**
  1. Add exact fixtures for ordered tool calls, patch bytes, cost/tokens, missing fields, duplicate records, invalid types, and threshold boundaries.
  2. Require deterministic findings/fingerprints and explicit unknowns; assert no network/subprocess/provider seam is called.
  3. Run named tests and retain assertion failures.
- **Evidence:** Fixture/test hashes and failure output.
- **Stop:** Recorded input schema or threshold semantics are undefined.
- **Verified outcome:** R50.2.20 may start.

#### R50.2.20 — GREEN: make prompt evaluation deterministic and recorded-only

- **Task ID and binary outcome:** R50.2.20; prompt evaluation consumes only the approved recorded schema and returns deterministic truthful results.
- **Start goal:** Satisfy R50.2.19.
- **Prerequisites:** R50.2.19 valid RED.
- **Documentation impact:** None.
- **Dependency impact:** None.
- **Allowed writes:** `src/rush/tools/prompt_eval.py` only.
- **Allowed reads:** Unchanged tests.
- **Prohibited:** Test/routes/docs edits; live execution, telemetry persistence, CodeBLEU, latency claims.
- **Actions:**
  1. Validate all record fields and make missing/invalid data explicit.
  2. Compute only approved comparisons and thresholds with deterministic ordering/fingerprints.
  3. Run focused tests, Ruff, format, and full suite.
- **Evidence:** Green tests and repeated-output equality.
- **Stop:** Any result depends on external provider state.
- **Verified outcome:** Prompt evaluation core is eligible for integration/docs.

#### R50.2.21 — RED: pin error-catalog and provenance evidence boundaries

- **Task ID and binary outcome:** R50.2.21; tests fail on heuristic HTTP invention, unsupported language claims, swallowed parse/Git errors, or inferred survival/causation.
- **Start goal:** Recover PR50.3/PR50.4 core truth separately from writes.
- **Prerequisites:** D50-11 and D50-12 approvals; R50.1.2.
- **Documentation impact:** None.
- **Dependency impact:** None.
- **Allowed writes:** `tests/test_error_catalog.py`, `tests/test_provenance_ai.py`.
- **Allowed reads:** Both tool modules and approved decisions.
- **Prohibited:** Production/docs/routes edits.
- **Actions:**
  1. Add exact Python/literal-TypeScript occurrence fixtures, parse-error fixtures, unsupported Rust/dynamic-expression states, and no-invented-status assertions.
  2. Add exact trailer, shallow history, missing Git, malformed commit, bounded max-commit, and explicit unknown survival/defect-correlation fixtures.
  3. Run named tests and retain failures.
- **Evidence:** Fixture hashes and failure output.
- **Stop:** Supported syntax or trailer grammar is undefined.
- **Verified outcome:** R50.2.22 may start.

#### R50.2.22 — GREEN: report only parsed error and Git evidence

- **Task ID and binary outcome:** R50.2.22; error catalog and provenance return only exact parsed/observed evidence with unsupported and unknown states.
- **Start goal:** Satisfy R50.2.21.
- **Prerequisites:** R50.2.21 valid RED.
- **Documentation impact:** None.
- **Dependency impact:** None.
- **Allowed writes:** `src/rush/tools/error_catalog.py`, `src/rush/tools/provenance_ai.py`.
- **Allowed reads:** Unchanged tests.
- **Prohibited:** Test/routes/docs edits; heuristic status/survival/causation conclusions.
- **Actions:**
  1. Limit extraction to approved syntax and surface parse/unsupported records rather than swallowing them.
  2. Preserve exact trailer evidence and mark survival/correlation unknown without inference.
  3. Run focused tests, Ruff, format, and full suite.
- **Evidence:** Green tests and evidence provenance rows.
- **Stop:** Any conclusion lacks an exact source span or Git record.
- **Verified outcome:** Both cores are eligible for integration/docs.

#### R50.2.23 — RED: pin TUI-diff data and benchmark descriptive statistics

- **Task ID and binary outcome:** R50.2.23; tests fail on the unselected TUI surface, unstable finding identity, invalid samples, or inferential/performance claims.
- **Start goal:** Recover PR50.12/PR50.13 bounded cores.
- **Prerequisites:** D50-16 and D50-17 approvals; R50.1.2.
- **Documentation impact:** None.
- **Dependency impact:** None.
- **Allowed writes:** `tests/test_tui_diff.py`, `tests/test_benchmark.py`.
- **Allowed reads:** Both tool modules and approved decisions.
- **Prohibited:** Production/docs/routes edits; full-screen event-loop work unless specifically selected.
- **Actions:**
  1. Add deterministic new/resolved/unchanged finding tests using canonical fingerprints, duplicates, missing fields, and the exact selected renderer/data boundary.
  2. Add sample validation, empty/NaN/infinite/unequal input, descriptive-only statistics, threshold boundary, deterministic baseline, and no-significance-claim tests.
  3. Run named tests and retain failures.
- **Evidence:** Test hashes and failure output.
- **Stop:** D50-16 public surface or D50-17 sample/baseline schema is undefined.
- **Verified outcome:** R50.2.24 may start.

#### R50.2.24 — GREEN: implement only selected diff data and descriptive comparison

- **Task ID and binary outcome:** R50.2.24; TUI diff returns deterministic canonical deltas and benchmark returns only validated descriptive results.
- **Start goal:** Satisfy R50.2.23.
- **Prerequisites:** R50.2.23 valid RED; R50.2.18 for baseline writes.
- **Documentation impact:** None.
- **Dependency impact:** None.
- **Allowed writes:** `src/rush/tools/tui_diff.py`, `src/rush/tools/benchmark.py`.
- **Allowed reads:** Unchanged tests.
- **Prohibited:** Test/routes/docs edits; unapproved interactive loop; suite orchestration or statistical significance claims.
- **Actions:**
  1. Normalize finding identity and deterministic delta ordering with selected presentation boundary.
  2. Validate samples and compute only approved descriptive statistics/thresholds; use the repaired store.
  3. Run focused tests, Ruff, format, and full suite.
- **Evidence:** Green tests and repeated-output equality.
- **Stop:** Output implies inferential significance or an unapproved UI.
- **Verified outcome:** TUI/benchmark cores are eligible for integration/docs.

### Phase R50.3 — Cross-feature parity and documentation

#### R50.3.1 — RED: author the fourteen-tool parity contract

- **Task ID and binary outcome:** R50.3.1; tests collect and fail on any admitted tool’s object, option, CLI, MCP, alias, permission, or ToolResult mismatch.
- **Start goal:** Replace route smoke tests with an executable parity matrix.
- **Prerequisites:** Every admitted R50.2 GREEN card; R50.1.6.
- **Documentation impact:** None.
- **Dependency impact:** None.
- **Allowed writes:** `tests/test_catalog.py`, `tests/test_config.py`, `tests/test_cli_registry.py`, `tests/test_mcp.py`, `tests/test_phase50_slsa_attestation.py`.
- **Allowed reads:** Catalog, config, CLI, MCP, registry, all admitted tools, decisions.
- **Prohibited:** Production/docs edits; private FastMCP-manager assertions as final public proof.
- **Actions:**
  1. Define a literal admitted-tool matrix with module/class/object, exact options/defaults, CLI syntax, canonical MCP name, compatibility alias, permissions, and core/result tests.
  2. Add table-driven object-identity and CLI/MCP fake-object forwarding/equality tests for every row; require only `rush_attest_generate` as alias.
  3. Add canonical field/status/finding ordering and no-business-logic-in-transport tests; run and retain exact mismatches.
- **Evidence:** Matrix/test hashes and failures.
- **Stop:** Any decision or feature core remains open.
- **Verified outcome:** R50.3.2 may start.

#### R50.3.2 — GREEN: satisfy the parity matrix through shared registration

- **Task ID and binary outcome:** R50.3.2; every admitted tool has one object and exact typed CLI/MCP/config/result parity.
- **Start goal:** Satisfy R50.3.1 without feature logic in transports.
- **Prerequisites:** R50.3.1 valid RED.
- **Documentation impact:** None.
- **Dependency impact:** None.
- **Allowed writes:** `src/rush/tools/__init__.py`, `src/rush/catalog.py`, `src/rush/config.py`, `src/rush/cli.py`, `src/rush/mcp.py`.
- **Allowed reads:** Unchanged parity tests and admitted tool signatures.
- **Prohibited:** Tool/test/docs edits; duplicate shims; raw ad-hoc result dictionaries.
- **Actions:**
  1. Export/register exactly one object per admitted tool and complete exact option declarations.
  2. Make CLI/MCP resolve typed values and call those objects; retain only the corrected attestation alias.
  3. Run all five integration suites, every feature suite, Ruff, format, and inspect transport source.
- **Evidence:** Fourteen-row green matrix, route lists, object identity, command exits.
- **Stop:** Any missing option/route, duplicate object, or transport computation remains.
- **Verified outcome:** Documentation correction may start.

#### R50.3.3 — DOCS: correct only active public claims and configuration anchors

- **Task ID and binary outcome:** R50.3.3; public docs/config describe exactly admitted behavior and every residual risky claim is historical or explicitly limited.
- **Start goal:** Remove unsafe promises without broad documentation churn.
- **Prerequisites:** R50.3.2 and all admitted feature cores/effects green.
- **Documentation impact:** Exact active anchors only.
- **Dependency impact:** Document exact optional extras only if present in manifest/lock.
- **Allowed writes:** `README.md`, `README2.md`, `README3.md`, `docs/AGENTIC_RUSH.md`, `docs/ARCHITECTURE.md`, `docs/developer/architecture.md`, `docs/user-guide/working-with-ai-agents.md`, `docs/CLI_REFERENCE.md`, `docs/MCP_REFERENCE.md`, `docs/CONFIGURATION.md`, `docs/TOOL_CATALOG.md`, `docs/SECURITY.md`, `docs/specs/slsa-attestation-spec.md` only if classified active, `examples/rush.toml`, and admitted `docs/tools/*.md` guides.
- **Allowed reads:** Final source/tests/manifest/lock and governing DOCS-card anchors.
- **Prohibited:** Other plans/reports/brainstorms; release/version claims; marketing expansion; undocumented options.
- **Actions:**
  1. Record the pre-edit claim at every active anchor, including Level 3, cryptographic, compliance, least-privilege, semantic PR, full-screen TUI, zero-loss, and performance language.
  2. Replace only those claims with exact unsigned/manual-review/nondeployable/observed-evidence/permission/dependency limitations and exact routes/options.
  3. Run the full literal claim sweep and a config-example-to-ToolSpec parity test; record every residual hit and reason.
- **Evidence:** Anchor ledger, claim-search output, config parity output, focused tests.
- **Stop:** A doc claims blocked/deferred behavior or a key rejected by the parser.
- **Verified outcome:** Installed-artifact probes may start.

### Phase R50.4 — Installed artifact and final evidence

#### R50.4.1 — VERIFY/RED: replace source-tree packaging checks with isolated probes

- **Task ID and binary outcome:** R50.4.1; two acceptance tests require a built wheel and isolated interpreter, inspect wheel metadata/modules, and use public installed CLI/MCP APIs.
- **Start goal:** Author the installed-artifact contract separately from evidence capture.
- **Prerequisites:** R50.3.3; all dependency decisions reflected in `pyproject.toml` and `uv.lock`.
- **Documentation impact:** None.
- **Dependency impact:** Verify only.
- **Allowed writes:** `tests/test_phase50_packaging.py` and ignored ephemeral `.rush/phase50-dist`, `.rush/phase50-wheel-venv`, `.rush/phase50-runtime-requirements.txt`.
- **Allowed reads:** Manifest, lock, built wheel, installed outputs, final parity matrix.
- **Prohibited:** Production/docs/evidence/manifest/lock edits; private FastMCP manager; source checkout imports; online fallback.
- **Actions:**
  1. Replace optional environment behavior with mandatory `RUSH_PHASE50_WHEEL` and `RUSH_PHASE50_PYTHON` validation; assert package metadata and every admitted module in the ZIP.
  2. From a cwd outside the repository and scrubbed `PYTHONPATH`, invoke the isolated Python/installed Rush CLI and public MCP `stdio_client`/`ClientSession.list_tools()`; assert import path is under the wheel venv and compare exact parity rows.
  3. Build/install offline, run both named tests, Ruff/format the test file, and record the one-file diff. A packaging failure remains a verification failure, not authority to edit production here.
- **Evidence:** Test hashes, isolated import path, wheel member list, CLI/MCP lists, exits.
- **Stop:** Source leakage, missing env, private manager, online resolution, or package-config repair is required.
- **Verified outcome:** R50.4.2 may independently reproduce unchanged probes.

#### R50.4.2 — EVIDENCE: independently rebuild, install, and record the wheel

- **Task ID and binary outcome:** R50.4.2; an independently rebuilt wheel passes unchanged R50.4.1 probes and exact identity/results are appended.
- **Start goal:** Separate evidence capture from test/implementation authoring.
- **Prerequisites:** R50.4.1 green with recorded test hash.
- **Documentation impact:** Append only `Wheel evidence / R50.4.2`.
- **Dependency impact:** Verify only.
- **Allowed writes:** `docs/developer/phase-50-implementation-evidence.md` and ignored ephemeral packaging paths.
- **Allowed reads:** Unchanged packaging test, manifest, lock, wheel, installed outputs.
- **Prohibited:** Production/test/public-doc/manifest/lock edits; online fallback; source installation; release actions.
- **Actions:**
  1. Clear environment leakage; run `uv build`, frozen runtime export, isolated venv creation, offline dependency install, and offline wheel install.
  2. Set exact wheel/interpreter variables; run unchanged packaging tests, installed `rush --version`/`--help`, public MCP list, and SHA-256.
  3. Append filename, hash, import path, member assertion, CLI/MCP lists, exact commands/exits, and no-online/no-source/no-release statement.
- **Evidence:** Independent wheel identity and unchanged-test hash.
- **Stop:** Any command fails or implementation/test correction is requested.
- **Verified outcome:** R50.4.3 final gate may start.

#### R50.4.3 — HANDOFF: run the one-revision remediation completion gate

- **Task ID and binary outcome:** R50.4.3; every approved decision, finding, test, doc, dependency, route, path-owner, and installed-artifact gate passes at one revision, or remediation remains incomplete.
- **Start goal:** Produce a truthful handoff without performing lifecycle actions.
- **Prerequisites:** R50.4.2; all required cards complete; no open admitted decision/finding.
- **Documentation impact:** Finalize `docs/developer/phase-50-implementation-evidence.md` only.
- **Dependency impact:** Verify manifest/lock; change neither.
- **Allowed writes:** Evidence file and ignored ephemeral packaging paths.
- **Allowed reads:** All owned diffs, decisions, tests, docs, manifest/lock, wheel outputs.
- **Prohibited:** Production/test/public-doc/dependency repair; commit/merge/tag/push/release/upload.
- **Actions:**
  1. Map every changed path to exactly one completed task; run `git diff --check`, decision/finding closure audit, forbidden-claim searches, and test-hash audit.
  2. Run project Python version, all feature suites, integration suites, full suite excluding packaging, Ruff check/format, `uv lock --check`, clean offline rebuild/install, unchanged packaging suite, installed CLI/MCP probes, wheel SHA-256, and final status/diff.
  3. Append one timestamped ledger with revision, decisions, admitted/deferred tools, task/finding closure, path ownership, dependencies, docs residuals, commands/exits, wheel identity, and explicit no-release statement.
- **Evidence:** One-revision complete ledger with no unsupported assurance.
- **Stop:** Any failure, skip replacing a required assertion, test mutation after RED, open decision/finding, unowned path, source leakage, or lifecycle request.
- **Verified outcome:** Phase 50 development remediation is complete only for the explicitly approved scope; release remains separately unauthorized.

## 10. Test inventory by finding

| Finding group | Required ordinary tests before GREEN |
|---|---|
| Config/options | `test_phase50_option_specs_cover_every_admitted_behavior`; `test_tool_config_options_are_immutable_and_precedence_is_default_config_explicit`; CLI/MCP fake-object forwarding tests |
| Atomic helper | Relative/absolute/traversal; intermediate/target symlink; substitution race; replace failure; temp cleanup; prior-byte preservation |
| Routes | Benchmark selected syntax; attestation alias semantic equality/deprecation; no manual wrappers; fourteen-row parity |
| Attest | Missing/directory/external/traversal/symlink rejection; exact real subject digest; unsigned-only assurance |
| License | Exact SPDX; compound/free text; missing evidence; executor independence; manual review |
| IAM | Approved-only mapping; empty input empty actions; unsupported calls/providers; no wildcard/resource invention |
| Memory/cold | Static cleanup paths; missing sampler; denied slow; exact argv; quote filename; nonzero/malformed/timeout; redaction |
| Offline | Runtime/model absence; containment/symlink; checksum/license; slow permission; providers; no network; inference errors |
| Media | Denied/no-write; explicit target; escape/symlink; source preservation; replace failure; measured smaller; no improvement |
| Dead asset | Manifest schema/version/import; malformed/empty; rescan race; changed hash; reference/uncertainty; no-follow; partial failure |
| PR synth | Supplied warn/skipped/error; unsigned draft; missing states; forbidden claims; redaction; deterministic rendering; safe export |
| Prompt | Recorded schema; ordered calls; exact patch; cost/tokens; missing/invalid fields; threshold boundaries; no provider |
| Error/provenance | Exact supported syntax; unsupported language; parse errors; exact trailers; shallow/missing Git; unknown survival/causation |
| TUI/benchmark | Fingerprint deltas; duplicates/missing fields; selected UI boundary; sample validation; descriptive-only stats; deterministic store |
| Packaging | Mandatory wheel/interpreter; ZIP metadata/modules; isolated import; installed CLI; public stdio MCP; sole alias |

## 11. Documentation claim inventory

R50.3.3 must search and disposition at least these literals across its allowed files:

- `SLSA Level`, `Level 3`, `signed`, `cryptographic provenance`, `trusted builder`, `reproducible`.
- `copyleft compliance`, `viral license`, `zero risk`, `compatible`.
- `least privilege`, `minimal permissions`, `deployment ready`, `Resource: "*"`.
- `all tests pass`, `100%`, `coverage`, `breaking changes`, `Architecture Guard`.
- `reviewer`, `risk score`, `blast radius`, `GitHub API`.
- `zero loss`, `AVIF`, `full-screen`, `interactive TUI`, `statistically significant`.
- Every public Phase 50 CLI/MCP route and every `[tools.<name>]` option key.

A residual hit is allowed only when the same sentence explicitly states a limitation or the document is explicitly labeled historical/non-authoritative. The evidence file must record the exact residual line and disposition.

## 12. Manual dry-run review checklist

Before authorizing implementation, a reviewer must answer `yes` to every item:

- [ ] Every task has a binary outcome and exactly three executable actions.
- [ ] Every RED task writes only tests and produces an ordinary assertion failure.
- [ ] Every GREEN task reads unchanged RED tests and writes only the smallest production surface.
- [ ] Every effect has denied/no-write, containment, symlink, atomicity, failure-preservation, and idempotence coverage.
- [ ] Every decision-blocked card has the decision as a hard prerequisite and stop.
- [ ] No task can infer an approval from existing implementation/evidence.
- [ ] Every tool’s exact options/defaults/routes/permissions are pinned before registration GREEN.
- [ ] Every public document path and active anchor is explicit.
- [ ] Every dependency change is conditional on exact approved constraints and includes lock/offline-wheel proof.
- [ ] Packaging test authoring and packaging evidence are separate cards.
- [ ] Final evidence cannot edit implementation to make a gate pass.
- [ ] No unowned file, broad reset, main work, commit, merge, release, or publication is authorized.

## 13. Completion definition

This remediation plan is complete as a planning artifact when it contains the verified findings, decision blockers, allowed files, dependencies, tests, documentation anchors, task order, and binary evidence gates above. The Phase 50 implementation itself is not complete until R50.4.3 passes.

Passing the existing 933-test suite does not waive any finding. Existing source/tests/docs may be retained only after the matching remediation RED demonstrates the governing contract and the paired GREEN satisfies it without changing those tests.
