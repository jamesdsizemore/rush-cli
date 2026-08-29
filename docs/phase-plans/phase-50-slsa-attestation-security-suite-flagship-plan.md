# Phase 50 implementation plan — evidence-safe security, analysis, and release-support tools

## Purpose and status

Define the exact decisions, contracts, TDD transitions, documentation corrections, and installed-artifact evidence required to complete the fourteen Phase 50 roadmap capabilities without unsupported assurance claims, noncanonical transport returns, unsafe write defaults, or coding-agent invention.

- **Artifact operation:** Revise.
- **Planning status:** **Blocked.** D50-04, D50-07, D50-08, and the feature-scope decisions D50-10 through D50-18 require explicit user disposition. No card whose named governing decision is open may begin; D50-08 blocks only PR50.8.3–PR50.8.9, while the independently owned static PR50.8.1–PR50.8.2 cards retain their stated prerequisites. No partial packet may be called complete.
- **Implementation status:** Not authorized by this plan.
- **Plan file:** docs/phase-plans/phase-50-slsa-attestation-security-suite-flagship-plan.md.
- **Plan-remediation branch/worktree:** codex/phase50-plan-remediation at C:\Users\james\developer\rush-cli\.rush\worktrees\phase50-plan-remediation.
- **Reviewed baseline:** f180ce0b61cc8cc6a2df04348811a88394e9bfbf.
- **Implementation branch/worktree:** Not authorized or selected. A future executor must stop on main and obtain explicit user authority for a non-main worktree.
- **Current package version:** 0.3.0. This phase does not change it.
- **Release status:** No commit, tag, package upload, publication, deployment, or release is authorized.
- **Last reviewed:** 2026-08-29.

### Decomposition decision

The safer structure is one shared-foundation plan plus separate per-capability implementation plans because the fourteen capabilities have independent product scope, tests, effects, dependencies, documentation, and exit gates. The user has authorized editing **only this existing P50 file**, so this revision does not create or replace plan files. Instead, this file contains an embedded shared-foundation packet and fourteen independently gated capability packets. Each packet has its own admission decision, RED/GREEN cycles, transport transitions, documentation ownership, and exit condition. Shared contracts are defined once in this file and referenced by packet ID; no packet may redefine them.

This single-file constraint is an artifact constraint, not permission to combine work. Cards may not batch tools, transports, effects, dependencies, documentation sweeps, or final evidence. If the user later authorizes separate files, this file remains the Phase 50 authority/index and the embedded packets may be moved verbatim without changing their requirement ownership.

### Artifact control and amendment procedure

- **Operation:** Revise.
- **Only planning file authorized to change in this planning task:** docs/phase-plans/phase-50-slsa-attestation-security-suite-flagship-plan.md.
- **Protected planning sources:** docs/developer/repository-remediation-plan.md; docs/developer/rush-token-innovation-enhancement-report-plan.md; docs/adr/0036-air-gapped-slm-local-onnx-runtime-and-slsa-attestation.md; every other phase plan.
- **Implementation writes:** None are authorized by this revision. Future implementation writes exist only inside an admitted task card.
- **Amendment authority:** A newly discovered production, test, fixture, configuration, dependency, lockfile, documentation, command, option, route, assurance, or lifecycle requirement stops the owning packet. The user must approve an amendment to this file naming the exact change before implementation resumes.

### How to use this plan

The requirement ledger, contract-test inventory, literal task allowlists, and task stop conditions are execution authority. A task may start only when its prerequisites are recorded. A new file, dependency, command, public option, assurance claim, or lifecycle action requires an approved amendment.

## Authority, current-state evidence, and conflicts

### Source-authority order

1. The user's current instructions: fix the skill and this plan; do not implement; do not work on main.
2. AGENTS.md, including canonical ToolResult, stdio-only MCP, shared implementation, optional-engine, safety, and no-release rules.
3. docs/developer/repository-remediation-plan.md, specifically R-013 and Phase 8 provenance corrections.
4. docs/developer/rush-token-innovation-enhancement-report-plan.md, Features I13–I22, I24, I26–I28 and Phase 50.
5. ADR-0036 where it does not conflict with newer authority.
6. Current source, tests, manifests, configuration, docs, and registrations at the reviewed baseline.
7. The HeadCleaner Phase R6 plan as structural/task-runbook evidence only.

### Repository-freshness findings

| ID | Verified observation | Required disposition |
|---|---|---|
| RS-50-01 | pyproject.toml already reports 0.3.0. | Preserve it; exclude version/release work. |
| RS-50-02 | attest.py, license_matrix.py, iam_audit.py, dead_asset.py, and pr_synthesize.py exist. | Modify through named RED/GREEN tasks; never classify as creates. |
| RS-50-03 | Nine other scoped modules do not exist. | Create only in their owning GREEN tasks. |
| RS-50-04 | tests/test_phase50_slsa_attestation.py contains five weak smoke tests; per-tool tests do not exist. | Preserve it as shared migration/parity suite and create literal per-tool suites. |
| RS-50-05 | The five existing tools return ad-hoc dictionaries/Markdown and bypass ToolFn, ALL_TOOLS, and TOOL_SPECS. | Migrate each feature to a canonical shared path. |
| RS-50-06 | CLI/MCP contain manual Phase 50 adapters; MCP serializes raw strings. | Replace business logic with shared ToolFn routes; preserve `rush_license_matrix`, `rush_iam_audit`, `rush_dead_asset`, and `rush_pr_synthesize` as canonical normalized names, and preserve only `rush_attest_generate` as a tested deprecated compatibility alias. |
| RS-50-07 | TOOL_SPECS contains none of the fourteen tools; ToolConfig accepts only engine_args/check. | Extend typed config-key authority before feature registration. |
| RS-50-08 | docs/tools and promised per-feature tests are absent. | Create only exact governed files. |
| RS-50-09 | scripts/sync_docs.py does not exist. | Remove it from every gate. |
| RS-50-10 | cryptography and Pillow are present but unused by Rush source. | Keep Pillow for I21; remove cryptography only after an exhaustive owner check. |
| RS-50-11 | No ONNX runtime, model, license, checksum, extra, or download contract exists. | Block I24 at D50-04. |

### Conflict and decision ledger

| Decision | Conflict | Resolution and authority | Status |
|---|---|---|---|
| D50-01 | Old plan says READY although paths, symbols, tests, docs, and commands are stale. | Current repository evidence controls; status is corrected before task authoring. | Resolved. |
| D50-02 | Old roadmap/ADR demand signed SLSA Level 3; R-013 proves current output is unsigned and unsupported. | Emit an unsigned in-toto Statement v1 provenance draft using the SLSA provenance v1 predicate. Remove Level, signed, reproducible, completeness, and trusted-builder claims. Signed verification remains outside this phase. | Resolved; PR50.5. |
| D50-03 | Old plan treats “final release” as authority to bump, commit, tag, publish, and update all docs. | A plan grants none of those actions. Phase 50 produces implementation and evidence only. | Resolved. |
| D50-04 | I24 says ONNX/GGUF, bundled model, optional runtime, download command, and zero-network guarantee without selecting them. | **Recommendation for approval:** use an optional pinned onnxruntime extra; accept only a user-supplied contained ONNX model with recorded license/SHA-256; bundle no weights; provide no download command; return skipped when runtime/model is absent. Record the exact constraint, providers, model format, checksum policy, and fixture before PR50.11. | Open local blocker. |
| D50-05 | Several features execute providers, tests, entry points, or writes while Rush denies effects by default. | Deterministic/read-only is default. Network, slow, cache-write, and artifact-write paths require matching ExecutionPermissions. | Resolved. |
| D50-06 | I22 is interactive but MCP cannot host a terminal event loop. | TuiDiffTool owns delta data. CLI may render with Rich; MCP returns canonical data without rendering. | Resolved. |
| D50-07 | I18 promises AWS/GCP/Azure least-privilege actions, but the repository contains no authoritative SDK-to-permission map and the current implementation invents AWS actions/resources. | **Recommendation for approval:** scope Phase 50 generation to a reviewed AWS mapping table backed by exact AWS service-authorization references; report GCP/Azure and unmapped calls as unsupported findings, never guessed policy. Record the approved providers, mapping entries, resource policy, and source citations before PR50.7. | Open local blocker. |
| D50-08 | I19 promises cross-platform dynamic heap/RSS deltas, but the repository has no process-memory sampler and no dependency authority for one. | **Recommendation for approval:** keep the static scanner dependency-free and add an optional pinned psutil extra for the explicit slow subprocess probe; absent psutil returns skipped. Record exact constraint, platforms, sampling interval, child-process policy, and metric definition before PR50.8. | Open only for the dynamic subfeature. |
| D50-09 | Current dynamic MCP registration preserves hyphens while the roadmap and existing Phase 50 public names use underscores. | Canonical MCP names are `rush_` plus `ToolFn.name` with `-` normalized to `_`. Existing `rush_license_matrix`, `rush_iam_audit`, `rush_dead_asset`, and `rush_pr_synthesize` become the canonical shared registrations, not duplicate aliases. `rush_attest_generate` alone remains a deprecated alias for canonical `rush_attest`. The shared registrar owns normalization; feature packets may not invent names. | Resolved; PR50.F3–F4. |
| D50-10 | I13 requires live multi-model FastMCP execution, CodeBLEU, telemetry, and performance claims; the proposed packet is recorded-run-only. | **Recommendation for approval:** Phase 50 implements deterministic recorded-run evaluation only; live provider execution, CodeBLEU, telemetry persistence, and latency claims are deferred to a separately authorized phase. Approval must identify the deferred owner or reject the narrowing. | Open; PR50.0.3 blocks PR50.2. |
| D50-11 | I14 promises Python, TypeScript, and Rust extraction plus generated type-safe builders; the bounded design supports Python and literal TypeScript only. | **Recommendation for approval:** implement Python and literal TypeScript audit/generation; defer Rust and application-source rewriting. Approval must name the deferred owner. | Open; PR50.0.4 blocks PR50.3. |
| D50-12 | I15 requires line survival analysis and defect correlation; exact commit trailers prove only commit attribution. | **Recommendation for approval:** implement trailer attribution and explicit unknown survival/correlation; defer line-lifecycle and defect-causation analysis until a trusted evidence model is approved. | Open; PR50.0.5 blocks PR50.4. |
| D50-13 | I17 requires linking-mechanics and SPDX compatibility conclusions that the repository cannot substantiate safely. | **Recommendation for approval:** implement exact local license evidence plus exact allowlist matching and manual-review states; defer linking and legal compatibility conclusions. | Open; PR50.0.6 blocks PR50.6. |
| D50-14 | I20 requires Python and Node isolated timing plus patch recommendations; the bounded design is Python-only and does not patch. | **Recommendation for approval:** implement deterministic Python AST inventory and permission-gated `-X importtime`; defer Node and patch generation. | Open; PR50.0.7 blocks PR50.9. |
| D50-15 | I21 promises zero-loss compression, AVIF/WebP conversion, markup insertion, and percentage savings; current evidence supports read-only audit and guarded explicit outputs only. | **Recommendation for approval:** implement SVG/CLS/raster audit, explicit sanitization, and PNG/WebP output only when measured; defer markup mutation, AVIF unless proven by the locked Pillow build, and percentage guarantees. | Open; PR50.0.8 blocks PR50.10. |
| D50-16 | I22 requires a full-screen keyboard event-loop TUI; MCP can expose only data and the proposed CLI renderer is not the promised application. | **Recommendation for approval:** either authorize the full CLI-only Rich application as a separate isolated packet, or narrow Phase 50 to delta data plus noninteractive rendering. No packet starts until one outcome is selected. | Open; PR50.0.9 blocks PR50.12. |
| D50-17 | I26 requires repeated suite execution and inferential significance; the bounded design compares supplied samples only. | **Recommendation for approval:** implement supplied-sample descriptive comparison and explicit baseline storage; defer suite orchestration and inferential significance. | Open; PR50.0.10 blocks PR50.13. |
| D50-18 | I27 includes CSS/design-token pruning and I28 includes risk scoring/reviewer routing; the bounded designs omit those claims. | **Recommendation for approval:** I27 owns conservative file-asset inventory/prune only and defers CSS/design tokens; I28 owns observed Git/ToolResult rendering only and defers risk/reviewer inference. Approval must disposition I27 and I28 separately. | Open; PR50.0.11 blocks PR50.14 and PR50.0.12 blocks PR50.15. |
| D50-19 | The previous plan called `dict[str, object]` typed configuration without defining key types, defaults, coercion, or validation. | Add immutable `ToolOptionSpec` declarations and a closed `ToolOptionValue` union. Parsing validates every key through its declaration before constructing `ToolConfig`; tools receive already typed values and may apply only feature-specific semantic checks. | Resolved; PR50.1.1–PR50.1.4. |

## Goals, verified outcomes, exclusions, and invariants

### Goals and outcomes

1. Every material subrequirement in I13–I22, I24, and I26–I28 has one explicit disposition, decision owner, task owner, test or deterministic proof, documentation disposition, dependency disposition, and closure evidence. An open decision is a blocker, not an implementation task.
2. Every tool returns tool, engine, engine_version, status, duration_ms, summary, and findings; optional detail stays in metrics, artifacts, metadata, or raw.
3. CLI and MCP invoke the same src/rush/tools object. Presentation may differ; behavior, status, findings, permissions, and evidence may not.
4. Read-only analysis is default. Network, slow subprocesses, cache writes, artifact writes, and interactive rendering require explicit permission.
5. No invented license, IAM, provenance, PR-gate, reproducibility, security, or performance claim survives.

### Scope explicitly excluded

- Signed/verified provenance, SLSA levels, trusted builders, signing keys, Cosign, and Git notes.
- Selecting or implementing I24 until D50-04 is approved and recorded.
- Bundling, downloading, licensing, or redistributing model weights.
- Live cloud/model/provider calls in tests or default execution.
- Creating IAM resources or presenting generated policies as deployment-safe.
- Legal advice or “zero-risk” license conclusions.
- Tool-runtime generation of user-project source, documentation, reports, or assets without artifact_write permission and contained paths.
- Asset deletion without artifact_write, exact manifest, and unchanged-input proof.
- Browser/web/frontend/visual-design work; I22 is terminal presentation over shared data only.
- Git history rewriting, hooks, commits, worktree creation, merges, tags, pushes, releases, uploads, or publication.
- Version bump, test-count promise, 100% coverage/docs sync, zero regressions, or all-capabilities claims.
- Unrelated CLI/MCP, cache, logging, provider, or phase-plan refactoring.
- New default telemetry or persistence.

### Inherited invariants

1. MCP stdout is JSON-RPC only; diagnostics stay on stderr.
2. Subprocesses use run_subprocess with stdin DEVNULL; no direct subprocess calls.
3. Missing optional engines/runtimes return skipped.
4. Status is ok, warn, fail, error, or skipped; severity is info, warn, or error.
5. Paths are resolved/contained before reads or writes; links may not escape.
6. Secrets, source bodies, prompts, credentials, signing material, and absolute host paths do not enter logs/errors.
7. Defaults are overridden by rush.toml, then explicit invocation arguments.
8. Each tools table maps to one TOOL_SPECS entry and contains only declared keys.

## Admission and predecessor gate

Implementation may start only after the user authorizes a non-main worktree. PR50.0.1 records git status --short --branch; git rev-parse HEAD; git log -1 --oneline; git worktree list; project Python version; focused baseline tests; Ruff check; and Ruff format check.

Stop admission on main, an unaccepted baseline, overlapping dirty changes, a non-3.12 project interpreter, or an unassigned baseline failure. D50-04 blocks PR50.11; D50-07 blocks PR50.7; D50-08 blocks only the dynamic branch of PR50.8. A GREEN task requires its named ordinary RED result. Collection errors, skips, XFAIL, XPASS, live services, and missing tooling are not RED evidence. A DOCS task requires its GREEN and parity tests.

## Requirement-ownership and scope-closure ledger

`Proposed owned` means the task packet is fully specified but cannot start until its governing open decision is approved. `Superseded` means a newer, higher-authority remediation finding forbids the original claim. `Deferred` is valid only after the named user decision records a successor owner.

| Requirement item | Roadmap behavior | Disposition and owner | Task owner | Proof | Dependency/docs |
|---|---|---|---|---|---|
| I13-A | Execute golden tasks across live target models through FastMCP. | Open D50-10; user decides owned versus deferred. | PR50.0.3 | Decision record. | Provider/runtime owner and prompt guide. |
| I13-B | Exact tool-order, patch, token, cost, and pass-rate matrix. | Proposed owned after D50-10 for recorded observations only. | PR50.2.1–PR50.2.5 | tests/test_prompt_eval.py plus route tests. | No package; docs/tools/prompt_eval.md. |
| I13-C | CodeBLEU, telemetry persistence, and latency target. | Open D50-10; no implementation authority. | PR50.0.3 | Decision record. | No manifest or telemetry writes before approval. |
| I14-A | Python/TypeScript/Rust exception inventory. | Open D50-11; Python and literal TypeScript proposed owned, Rust proposed deferred. | PR50.0.4; PR50.3.1–PR50.3.2 | tests/test_error_catalog.py. | Stdlib; docs/tools/error_catalog.md. |
| I14-B | Deterministic RFC 7807 module/docs generation. | Proposed owned after D50-11 with artifact permission and contained targets. | PR50.3.3–PR50.3.7 | write-denial, idempotence, containment tests. | No package; security/config docs. |
| I15-A | Commit-trailer AI attribution. | Proposed owned after D50-12. | PR50.4.1–PR50.4.5 | tests/test_provenance_ai.py. | Git CLI; docs/tools/provenance_ai.md. |
| I15-B | 30/60/90-day line survival and defect correlation. | Open D50-12; proposed deferred, never reported as zero or success. | PR50.0.5 | Decision record and unknown-state assertions. | No statistics package. |
| I16-A | Signed SLSA Level 3 provenance. | Superseded by R-013/D50-02; explicitly out of Phase 50. | PR50.5.1–PR50.5.8 correct the claim. | tests/test_attest.py and claim inventory. | Conditional cryptography removal; docs/tools/attest.md. |
| I16-B | Artifact-bound in-toto Statement v1 provenance draft. | Owned. | PR50.5.1–PR50.5.8 | digest/schema/export/route/package tests. | Stdlib/Git; exact public claim corrections. |
| I17-A | Exact local manifest/metadata license evidence. | Proposed owned after D50-13. | PR50.6.1–PR50.6.7 | tests/test_license_matrix.py. | Stdlib; docs/tools/license_matrix.md. |
| I17-B | Linking analysis, SPDX compatibility, and legal risk verdict. | Open D50-13; proposed deferred/manual review. | PR50.0.6 | Decision record and absence assertions. | No legal matrix package. |
| I18-A | SDK call to permission mapping. | Open D50-07; only an approved finite map may be owned. | PR50.7.0–PR50.7.5 | map equality and unsupported-call tests. | No HCL package unless separately approved. |
| I18-B | Infrastructure diff and deployable minimal policy. | Open D50-07; no implementation authority without exact parser/map/resource policy. | PR50.7.0 | Decision record. | IAM guide and claim correction. |
| I19-A | Static potential resource-lifecycle findings. | Owned independently of D50-08. | PR50.8.1–PR50.8.2 | tests/test_mem_profile.py static cases. | Stdlib; docs/tools/mem_profile.md. |
| I19-B | Dynamic child-process RSS/heap measurement. | Open D50-08. | PR50.8.3–PR50.8.9 | decision, permission, dependency, sampler, child-error, route, and documentation evidence. | Exact optional psutil constraint if approved. |
| I20-A | Python and Node import instrumentation and patch recommendations. | Open D50-14. | PR50.0.7 | Decision record. | No implementation before approval. |
| I20-B | Python AST inventory and explicit `-X importtime`. | Proposed owned after D50-14. | PR50.9.1–PR50.9.7 | static, slow, error, and route tests. | Existing runner; docs/tools/cold_start.md. |
| I21-A | SVG/CLS/raster audit. | Proposed owned after D50-15. | PR50.10.1–PR50.10.2 | audit/no-write tests. | Existing Pillow/stdlib XML. |
| I21-B | Explicit SVG sanitization and measured PNG/WebP output. | Proposed owned after D50-15. | PR50.10.3–PR50.10.9 | permission, containment, active-content, size tests. | Preserve Pillow constraint. |
| I21-C | Markup mutation, AVIF, zero-loss, and savings guarantee. | Open D50-15; no implementation authority. | PR50.0.8 | Decision/capability record. | No added imaging package. |
| I22-A | Commit/finding delta data. | Proposed owned under either D50-16 outcome. | PR50.12.1–PR50.12.7 | tests/test_tui_diff.py. | Existing Git/cache. |
| I22-B | Full-screen interactive CLI application. | Open D50-16. | PR50.0.9 and, if approved, a plan amendment with renderer/event-loop tests. | Decision record. | Existing Rich only unless amended. |
| I24-A | Optional local runtime, user model, checksum/license/provider policy. | Open D50-04. | PR50.0.2; PR50.11.1–PR50.11.6 | Complete decision and tests. | Exact optional package/lock/docs after approval. |
| I24-B | Bundled/downloaded weights and download command. | Excluded unless separately authorized; current recommendation rejects it. | PR50.0.2 | Absence/socket tests. | No weights or download dependency. |
| I26-A | Supplied-sample descriptive comparison and explicit baseline store. | Proposed owned after D50-17. | PR50.13.1–PR50.13.7 | tests/test_benchmark.py. | Stdlib; docs/tools/benchmark.md. |
| I26-B | Repeated suite execution, t-test, and significance claim. | Open D50-17; proposed deferred. | PR50.0.10 | Decision record. | No scipy/subprocess authority. |
| I27-A | Conservative file-asset inventory, manifest, and guarded prune. | Proposed owned after D50-18. | PR50.14.1–PR50.14.9 | tests/test_dead_asset.py. | Stdlib; docs/tools/dead_asset.md. |
| I27-B | CSS/design-token pruning and Git rollback. | Open D50-18; proposed deferred/rejected for safety. | PR50.0.11 | Decision record and absence tests. | No parser package. |
| I28-A | Observed Git/ToolResult PR Markdown and contained export. | Proposed owned after D50-18. | PR50.15.1–PR50.15.7 | tests/test_pr_synthesize.py. | Git CLI; docs/tools/pr_synthesize.md. |
| I28-B | Risk tiers, reviewer routing, badges, and GitHub integration. | Open D50-18; proposed deferred. | PR50.0.12 | Decision record and unsupported-claim tests. | No GitHub API package. |
| Shared-A | Typed declaration-backed configuration. | Owned. | PR50.1.1–PR50.1.4 | tests/test_catalog.py; tests/test_config.py. | No dependency; config docs in feature packets. |
| Shared-B | Canonical registry/CLI/MCP names and one deprecated compatibility alias. | Owned. | PR50.F3–F4 and per-feature integration cards. | tests/test_cli_registry.py; tests/test_mcp.py; tests/test_phase50_slsa_attestation.py. | Four existing underscore names become canonical; only `rush_attest_generate` remains an alias. |
| Shared-C | Contained no-follow path resolution and failure-preserving atomic byte output. | Owned. | PR50.1.5–PR50.1.6 | tests/test_tool_common.py. | Stdlib only; every artifact/store effect depends on this helper. |
| Shared-D | Source/wheel parity and final evidence. | Owned only after every decision is resolved and every selected packet is complete. | PR50.16.1–PR50.17 | packaging and full gates. | No release action. |

## Shared contracts and cross-phase handoff

| Class/source | Registry/config | CLI | MCP |
|---|---|---|---|
| PromptEvalTool / prompt_eval.py | prompt-eval | rush prompt-eval | rush_prompt_eval |
| ErrorCatalogTool / error_catalog.py | error-catalog | rush error-catalog | rush_error_catalog |
| ProvenanceAiTool / provenance_ai.py | provenance-ai | rush provenance-ai | rush_provenance_ai |
| AttestationTool / attest.py | attest | rush attest | rush_attest; deprecated rush_attest_generate alias |
| LicenseMatrixTool / license_matrix.py | license-matrix | rush license-matrix | rush_license_matrix; existing name becomes the canonical normalized route |
| IamAuditTool / iam_audit.py | iam-audit | rush iam-audit | rush_iam_audit; existing name becomes the canonical normalized route |
| MemProfileTool / mem_profile.py | mem-profile | rush mem-profile | rush_mem_profile |
| ColdStartTool / cold_start.py | cold-start | rush cold-start | rush_cold_start |
| MediaOptTool / media_opt.py | media-opt | rush media-opt | rush_media_opt |
| OfflineReviewTool / offline_runner.py | offline-review | rush offline-review; rush review --offline adapter | rush_offline_review |
| TuiDiffTool / tui_diff.py | tui-diff | rush tui-diff; rush tui diff adapter | rush_tui_diff |
| BenchmarkTool / benchmark.py | benchmark | rush benchmark | rush_benchmark |
| DeadAssetTool / dead_asset.py | dead-asset | rush dead-asset | rush_dead_asset; existing name becomes the canonical normalized route |
| PrSynthesizeTool / pr_synthesize.py | pr-synthesize | rush pr-synthesize | rush_pr_synthesize; existing name becomes the canonical normalized route |

- ok means completed without an actionable finding; warn means findings/manual review; fail means an explicit selected policy threshold failed; skipped means optional evidence/runtime/permission is unavailable; error means malformed input, containment failure, corrupt evidence, or internal failure.
- `ToolOptionValue` is exactly `str | int | float | bool | tuple[str, ...]`. `ToolOptionSpec` is immutable and contains `name`, `value_type`, `default`, `required`, `choices`, `minimum`, `maximum`, and `path_kind` (`none`, `file`, or `directory`). `ToolSpec.option_specs` is an immutable tuple. `ToolConfig.options` is a read-only mapping of declared names to validated `ToolOptionValue` values. `_parse` rejects undeclared keys, booleans passed as integers, wrong scalar/list types, invalid choices, out-of-range numbers, and absolute or parent-traversing configured paths. No tool receives `object` values or performs generic TOML coercion.
- Precedence is declaration default, then `rush.toml`, then an explicit invocation argument. An omitted invocation argument does not overwrite configured data. Feature-specific semantic checks occur inside the owning ToolFn only after shared type validation.
- The shared MCP registrar normalizes `-` to `_`; no feature registers a second canonical name manually. The four existing normalized names become their tools' canonical shared registrations and their migration shims are removed by the owning integration cards. Only `rush_attest_generate` may remain as a compatibility wrapper, containing argument normalization plus one `rush_attest` ToolFn call and explicit deprecation metadata.
- Network, download, browser, and runtime build permission are not used by Phase 50 tool behavior. The final evidence gate invokes `uv build` only to inspect a local wheel. slow covers only approved I19 dynamic probing, I20 import timing, and I24 local inference. cache_write covers I26 baseline recording. artifact_write covers I14 generation, I16 export, I21 outputs, I27 manifest/prune, I28 export, and any other explicitly named export.
- The remediation provenance phase may consume only the unsigned draft. It may not cite Phase 50 as SLSA, signature, reproducibility, or builder-trust evidence.

## Contract-test inventory

Every RED, GREEN, DEPENDENCY, DOCS, VERIFY, and EVIDENCE card contains its own literal command sequence; decision-only cards instead contain exact evidence fields and no implementation command. RED commands name every test node. Core/effect GREEN commands rerun the unchanged owning test file and literal Ruff paths. Integration GREEN commands additionally run `.venv/Scripts/python.exe -m pytest tests/test_catalog.py tests/test_cli_registry.py tests/test_mcp.py -q` plus the owning feature file. A coding agent must not substitute a differently scoped command or treat an unexecuted broader suite as evidence.

| File | Exact mandatory tests |
|---|---|
| tests/test_tool_common.py | test_resolve_contained_output_rejects_absolute_parent_and_symlink; test_atomic_write_replaces_only_contained_target_and_is_deterministic; test_atomic_write_preserves_existing_target_and_removes_temp_on_failure |
| tests/test_prompt_eval.py | test_prompt_eval_scores_normalized_fixture_runs_without_network; test_prompt_eval_retains_failed_cases_and_reports_matrix |
| tests/test_error_catalog.py | test_error_catalog_extracts_stable_codes_without_writing; test_error_catalog_generate_requires_permission; test_error_catalog_generate_is_contained_atomic_and_idempotent; test_error_catalog_generate_rejects_escape_and_preserves_existing_files |
| tests/test_provenance_ai.py | test_provenance_ai_uses_commit_trailers_and_reports_shallow_history; test_provenance_ai_does_not_claim_unobserved_survival_or_defect_correlation |
| tests/test_attest.py | test_attest_emits_unsigned_v1_draft_for_real_artifact; test_attest_rejects_missing_artifact_and_unsupported_assurance; test_attest_export_requires_artifact_permission; test_attest_export_is_contained_atomic_and_preserves_existing_file_on_error |
| tests/test_license_matrix.py | test_license_matrix_reports_fixture_metadata_without_inventing_licenses; test_license_matrix_exact_allowlist_match_is_allowed; test_license_matrix_marks_missing_compound_free_text_and_unrecognized_for_manual_review |
| tests/test_iam_audit.py | test_iam_audit_maps_only_approved_fixture_calls_without_defaults; test_iam_audit_reports_unsupported_calls_resources_and_infrastructure_truthfully |
| tests/test_mem_profile.py | test_mem_profile_flags_potential_unclosed_resources_statically; test_mem_profile_static_excludes_proven_with_finally_and_close_paths; test_mem_profile_dynamic_denied_without_slow_permission; test_mem_profile_dynamic_missing_psutil_is_skipped_without_runner; test_mem_profile_dynamic_uses_approved_samples_and_child_policy; test_mem_profile_dynamic_preserves_nonzero_child_failure |
| tests/test_cold_start.py | test_cold_start_static_import_inventory_is_deterministic; test_cold_start_execution_denied_without_slow_permission; test_cold_start_execution_uses_project_python_importtime_argv; test_cold_start_execution_parses_observed_rows_and_threshold; test_cold_start_execution_preserves_nonzero_and_syntax_errors |
| tests/test_media_opt.py | test_media_opt_audit_reports_svg_cls_and_raster_evidence_without_writes; test_media_opt_sanitize_requires_permission_and_explicit_output; test_media_opt_sanitize_removes_active_content_and_preserves_safe_nodes; test_media_opt_sanitize_rejects_escape_and_preserves_source_and_old_output; test_media_opt_optimize_requires_permission_and_explicit_output; test_media_opt_optimize_writes_only_smaller_deterministic_png_or_webp; test_media_opt_optimize_preserves_files_on_no_improvement_escape_or_error |
| tests/test_offline_review.py | test_offline_review_missing_runtime_or_model_is_skipped_without_network; test_offline_review_fake_session_returns_valid_findings_and_rejects_socket_use |
| tests/test_tui_diff.py | test_tui_diff_computes_commit_deltas_from_fixture_records; test_tui_diff_cli_renderer_receives_identical_raw_delta |
| tests/test_benchmark.py | test_benchmark_compares_fixed_samples_against_threshold; test_benchmark_record_requires_cache_write_and_writes_versioned_schema; test_benchmark_record_rejects_invalid_samples_and_escaping_path; test_benchmark_record_preserves_existing_store_on_replace_failure |
| tests/test_dead_asset.py | test_dead_asset_marks_literal_dynamic_and_unreadable_references_without_deleting; test_dead_asset_manifest_export_requires_artifact_permission; test_dead_asset_manifest_export_is_deterministic_contained_and_atomic; test_dead_asset_manifest_export_preserves_existing_file_on_error; test_dead_asset_prune_denied_is_noop; test_dead_asset_prune_deletes_only_unchanged_revalidated_manifest_candidates; test_dead_asset_prune_retains_changed_referenced_uncertain_or_invalid_entries |
| tests/test_pr_synthesize.py | test_pr_synthesize_renders_only_observed_evidence; test_pr_synthesize_missing_base_or_metric_is_explicit_not_success; test_pr_synthesize_export_requires_artifact_permission; test_pr_synthesize_export_is_contained_atomic_and_deterministic; test_pr_synthesize_export_preserves_existing_file_on_error |
| tests/test_phase50_slsa_attestation.py | test_phase50_each_implemented_tool_has_catalog_registry_cli_and_mcp_parity; test_phase50_attest_generate_alias_calls_shared_tool_and_is_deprecated; test_phase50_manual_transport_implementations_are_removed; test_phase50_results_have_required_canonical_fields_and_status_vocabulary |
| tests/test_phase50_packaging.py | test_phase50_modules_are_present_in_built_wheel; test_phase50_installed_cli_help_and_mcp_catalog_match_source_contract |

The integration RED cards add these exact nodes to the existing shared test files. Each row is indivisible: all three tests must be RED before the corresponding registry/transport GREEN starts.

| Packet | tests/test_catalog.py | tests/test_cli_registry.py | tests/test_mcp.py |
|---|---|---|---|
| PR50.2 prompt-eval | test_prompt_eval_catalog_declares_typed_options_and_single_object | test_prompt_eval_cli_forwards_path_and_returns_tool_result | test_prompt_eval_mcp_uses_canonical_name_and_matches_cli |
| PR50.3 error-catalog | test_error_catalog_catalog_declares_generation_options | test_error_catalog_cli_forwards_guarded_generation_arguments | test_error_catalog_mcp_matches_cli_and_uses_canonical_name |
| PR50.4 provenance-ai | test_provenance_ai_catalog_declares_trailers_and_since_days | test_provenance_ai_cli_uses_registered_tool | test_provenance_ai_mcp_matches_cli_and_uses_canonical_name |
| PR50.5 attest | test_attest_catalog_declares_unsigned_draft_options | test_attest_cli_and_canonical_mcp_share_registered_tool | test_attest_generate_alias_is_deprecated_and_uses_registered_tool |
| PR50.6 license-matrix | test_license_matrix_catalog_declares_evidence_policy_options | test_license_matrix_cli_and_mcp_return_same_tool_result | test_license_matrix_transports_do_not_construct_scanner |
| PR50.7 iam-audit | test_iam_audit_catalog_declares_only_approved_scope | test_iam_audit_cli_and_mcp_return_same_tool_result | test_iam_audit_transports_contain_no_policy_synthesis |
| PR50.8 mem-profile | test_mem_profile_catalog_exposes_only_admitted_options | test_mem_profile_cli_forwards_admitted_mode_and_permission | test_mem_profile_mcp_uses_canonical_name_and_matches_cli |
| PR50.9 cold-start | test_cold_start_catalog_declares_python_scope_options | test_cold_start_cli_forwards_entry_execution_and_threshold | test_cold_start_mcp_uses_canonical_name_and_matches_cli |
| PR50.10 media-opt | test_media_opt_catalog_declares_exact_operation_options | test_media_opt_cli_forwards_audit_sanitize_and_optimize_arguments | test_media_opt_mcp_uses_canonical_name_and_matches_cli |
| PR50.11 offline-review | test_offline_review_catalog_declares_approved_runtime_options | test_offline_review_cli_forms_share_registered_tool | test_offline_review_mcp_uses_canonical_name_without_network |
| PR50.12 tui-diff | test_tui_diff_catalog_declares_commit_count_option | test_tui_diff_cli_forms_share_raw_data_and_renderer_boundary | test_tui_diff_mcp_returns_raw_data_without_control_codes |
| PR50.13 benchmark | test_benchmark_catalog_declares_comparison_and_store_options | test_benchmark_cli_forwards_compare_record_and_cache_permission | test_benchmark_mcp_uses_canonical_name_and_matches_cli |
| PR50.14 dead-asset | test_dead_asset_catalog_declares_inventory_manifest_and_prune_options | test_dead_asset_cli_forwards_operations_and_artifact_permission | test_dead_asset_mcp_uses_canonical_name_without_scanner_construction |
| PR50.15 pr-synthesize | test_pr_synthesize_catalog_declares_evidence_and_output_options | test_pr_synthesize_cli_forwards_base_evidence_output_and_permission | test_pr_synthesize_mcp_uses_canonical_name_without_hardcoded_claims |

The inventory above names the retained end-state tests. The ordered task packets below split each independently observable behavior into its own RED/GREEN cycle. A GREEN card has no test-file write authority unless it explicitly names import or fixture wiring that must change while preserving every RED assertion; the default is that RED tests are read-only during GREEN.

### Typed configuration key contract

| Tool | Key | Type/default | Shared validation | Feature semantic validation |
|---|---|---|---|---|
| prompt-eval | benchmark_tasks_dir | directory path / `tests/golden_tasks` | contained relative directory | directory contains task JSON records |
| prompt-eval | recorded_runs_file | file path / `.rush/recorded-runs.json` | contained relative file | record schema and unique model/task pairs |
| error-catalog | prefix | str / `ERR_` | nonempty | uppercase ASCII plus trailing underscore |
| error-catalog | output_module | file path / `src/errors.py` | contained relative file | `.py` suffix |
| error-catalog | export_docs | file path / `docs/errors.md` | contained relative file | `.md` suffix |
| provenance-ai | ai_commit_trailers | tuple[str, ...] / exact approved trailer names | nonempty strings | case-sensitive trailer-key matching |
| provenance-ai | since_days | int / `90` | 1–3650 | none |
| attest | export_path | file path / no default | contained relative file | `.json` or `.intoto.jsonl` as selected by invocation |
| license-matrix | project_license | str / no default | nonempty when present | evidence label only, not legal classification |
| license-matrix | allowed_licenses | tuple[str, ...] / empty | exact strings | exact match only |
| iam-audit | cloud_provider | str / decision value | approved choice only | D50-07 map membership |
| iam-audit | infrastructure_dir | directory path / decision value | contained relative directory | D50-07 parser scope |
| mem-profile | mode | str / `static` | choices `static`, `dynamic` | dynamic additionally requires D50-08 and slow permission |
| mem-profile | probe_command | tuple[str, ...] / empty | nonempty argv for dynamic | no shell string |
| mem-profile | sample_interval_ms | int / decision value | 10–5000 | D50-08 exact value |
| mem-profile | max_heap_delta_mb | float / `50.0` | greater than zero | metric interpretation from D50-08 |
| cold-start | entry | file path / no default | contained regular file | `.py` only under D50-14 proposal |
| cold-start | threshold_ms | float / `50.0` | zero or greater | applied only to observed timings |
| media-opt | operation | str / `audit` | choices `audit`, `sanitize`, `optimize` | D50-15 admitted operations only |
| media-opt | output | file path / no default | contained relative file | required for write operations |
| media-opt | target_format | str / `webp` | admitted format choice | checked against locked Pillow capability |
| media-opt | max_image_dim | int / `2048` | 1–32768 | no implicit resize in audit mode |
| offline-review | model_path/checksum/providers/max_threads | exact D50-04 types/defaults | unavailable until decision | unavailable until decision |
| tui-diff | default_commit_count | int / `10` | 1–1000 | none |
| benchmark | baseline_path | file path / `.rush/baselines.json` | contained relative file | versioned JSON schema |
| benchmark | threshold_pct | float / `20.0` | zero or greater | selected metric only |
| benchmark | fail_on | str / empty | admitted metric choice | empty means warn, never fail |
| dead-asset | asset_dirs | tuple[str, ...] / `public`, `assets` | contained relative directories | finite extension inventory |
| dead-asset | source_dirs | tuple[str, ...] / `src` | contained relative directories | finite source extension inventory |
| pr-synthesize | base_ref | str / `main` | nonempty argv value | must resolve through Git without fallback |
| pr-synthesize | evidence_file | file path / no default | contained relative file | ToolResult minimum schema |

### Evidence-file schema

`docs/developer/phase-50-implementation-evidence.md` is one append-only implementation record with these exact second-level headings in this order: `Baseline`, `Decision records`, `RED observations`, `GREEN observations`, `Route parity`, `Dependency and lock evidence`, `Documentation claim corrections`, `Wheel evidence`, `Changed-path ownership`, `Final command ledger`, and `Successor handoff`. Each task appends only beneath its named heading and uses a third-level heading equal to its task ID. Rewriting or deleting another task's entry is prohibited. Every command entry records command text, UTC timestamp, exit code, and a bounded result summary; secrets and absolute host paths are redacted.

## File, dependency, and documentation governance

### Existing files potentially authorized by future task cards

src/rush/catalog.py; src/rush/config.py; src/rush/cli.py; src/rush/mcp.py; src/rush/tools/__init__.py; src/rush/tools/common.py; src/rush/tools/attest.py; src/rush/tools/license_matrix.py; src/rush/tools/iam_audit.py; src/rush/tools/dead_asset.py; src/rush/tools/pr_synthesize.py; tests/test_phase50_slsa_attestation.py; tests/test_catalog.py; tests/test_config.py; tests/test_cli_registry.py; tests/test_mcp.py; pyproject.toml; uv.lock; examples/rush.toml; README.md; README2.md; README3.md; docs/README.md; docs/AGENTIC_RUSH.md; docs/API_REFERENCE.md; docs/ARCHITECTURE.md; docs/developer/architecture.md; docs/developer/contributor-onboarding.md; docs/CLI_REFERENCE.md; docs/CLI_COOKBOOK.md; docs/MCP_REFERENCE.md; docs/CONFIGURATION.md; docs/TOOL_CATALOG.md; docs/SECURITY.md; docs/RELEASE.md; docs/USER_GUIDE.md; docs/FAQ.md; docs/GLOSSARY.md; docs/VIBECODING.md; docs/workflows/supply_chain_security_and_flagship_release.md; docs/tutorials/before-a-pull-request.md; docs/user-guide/advanced-checks.md; docs/user-guide/checking-code.md; docs/user-guide/everyday-workflow.md; docs/user-guide/faq.md; docs/user-guide/working-with-ai-agents.md.

### New files authorized

src/rush/tools/prompt_eval.py; src/rush/tools/error_catalog.py; src/rush/tools/provenance_ai.py; src/rush/tools/mem_profile.py; src/rush/tools/cold_start.py; src/rush/tools/media_opt.py; src/rush/tools/offline_runner.py; src/rush/tools/tui_diff.py; src/rush/tools/benchmark.py; tests/test_tool_common.py; tests/test_prompt_eval.py; tests/test_error_catalog.py; tests/test_provenance_ai.py; tests/test_attest.py; tests/test_license_matrix.py; tests/test_iam_audit.py; tests/test_mem_profile.py; tests/test_cold_start.py; tests/test_media_opt.py; tests/test_offline_review.py; tests/test_tui_diff.py; tests/test_benchmark.py; tests/test_dead_asset.py; tests/test_pr_synthesize.py; tests/test_phase50_packaging.py; docs/developer/phase-50-implementation-evidence.md; docs/tools/prompt_eval.md; docs/tools/error_catalog.md; docs/tools/provenance_ai.md; docs/tools/attest.md; docs/tools/license_matrix.md; docs/tools/iam_audit.md; docs/tools/mem_profile.md; docs/tools/cold_start.md; docs/tools/media_opt.md; docs/tools/offline_runner.md; docs/tools/tui_diff.md; docs/tools/benchmark.md; docs/tools/dead_asset.md; docs/tools/pr_synthesize.md. The three offline paths remain unauthorized until D50-04 is accepted. Dynamic I19 dependency/lock writes remain unauthorized until D50-08 is accepted.

All unlisted files are protected. The inventory above is not write authority: a future task may write only its literal `Allowed writes`. Do not edit other plans, the roadmap, ADRs, specifications, reports, version sources, CI, Git metadata, or unrelated user changes.

### Binding allowed-read resolution

The table below makes every task-card shorthand finite. Terms such as `tool`, `green tool`, `integration tests`, `registrars`, `typed-key table`, `permissions`, `runner`, `current routes`, `decision evidence`, and `unchanged tests/helpers` mean only the paths in the matching row. `Roadmap Ixx` means only the cited Ixx section in docs/developer/rush-token-innovation-enhancement-report-plan.md; `R-013` means only that finding and its Phase 8 disposition in docs/developer/repository-remediation-plan.md; `ADR-0036` means docs/adr/0036-air-gapped-slm-local-onnx-runtime-and-slsa-attestation.md. A DOCS card may additionally read only its literal `Allowed writes`, its exact row in the active documentation correction ledger, and its already-green source/tests. The card's literal `Allowed reads` may otherwise narrow the matching row but cannot broaden it. Graft/CodeGraph discovery may return other paths, but the agent must stop and amend the plan before opening them. The only other general exceptions are this P50 plan itself, the implementation evidence file once created, Python stdlib documentation available in the environment, and the exact user-approved primary reference named in a decision record.

| Packet | Exact read-only inventory |
|---|---|
| PR50.0 decisions | docs/developer/repository-remediation-plan.md; docs/developer/rush-token-innovation-enhancement-report-plan.md; docs/adr/0036-air-gapped-slm-local-onnx-runtime-and-slsa-attestation.md; this P50 plan; docs/developer/phase-50-implementation-evidence.md; the feature's exact row below; pyproject.toml and uv.lock only when the decision concerns a dependency. |
| PR50.1 shared configuration/filesystem | src/rush/catalog.py; src/rush/config.py; src/rush/permissions.py; src/rush/tools/common.py; scripts/benchmarks/jobs.py; tests/test_catalog.py; tests/test_config.py; tests/test_tool_common.py; tests/test_cli_registry.py; tests/test_mcp.py. |
| PR50.F MCP normalization | src/rush/mcp.py; src/rush/catalog.py; src/rush/tools/__init__.py; src/rush/tools/attest.py; src/rush/tools/license_matrix.py; src/rush/tools/iam_audit.py; src/rush/tools/dead_asset.py; src/rush/tools/pr_synthesize.py; tests/test_mcp.py; tests/test_cli_registry.py; tests/test_phase50_slsa_attestation.py. |
| PR50.2 prompt-eval | src/rush/tools/prompt_eval.py; src/rush/tools/ai_eval.py; src/rush/tools/base.py; src/rush/tools/common.py; src/rush/tools/__init__.py; src/rush/catalog.py; src/rush/cli.py; src/rush/mcp.py; tests/test_ai_eval.py; tests/test_prompt_eval.py; tests/test_catalog.py; tests/test_cli_registry.py; tests/test_mcp.py. |
| PR50.3 error-catalog | src/rush/tools/error_catalog.py; src/rush/tools/base.py; src/rush/tools/common.py; src/rush/permissions.py; src/rush/tools/__init__.py; src/rush/catalog.py; src/rush/cli.py; src/rush/mcp.py; tests/test_error_catalog.py; tests/test_tool_common.py; tests/test_catalog.py; tests/test_cli_registry.py; tests/test_mcp.py. |
| PR50.4 provenance-ai | src/rush/tools/provenance_ai.py; src/rush/tools/common.py; src/rush/cache.py; src/rush/tools/__init__.py; src/rush/catalog.py; src/rush/cli.py; src/rush/mcp.py; tests/test_provenance_ai.py; tests/test_catalog.py; tests/test_cli_registry.py; tests/test_mcp.py. |
| PR50.5 attest | src/rush/tools/attest.py; src/rush/tools/common.py; src/rush/permissions.py; src/rush/tools/__init__.py; src/rush/catalog.py; src/rush/cli.py; src/rush/mcp.py; tests/test_attest.py; tests/test_tool_common.py; tests/test_phase50_slsa_attestation.py; tests/test_catalog.py; tests/test_cli_registry.py; tests/test_mcp.py; pyproject.toml; uv.lock. |
| PR50.6 license-matrix | src/rush/tools/license_matrix.py; src/rush/tools/__init__.py; src/rush/catalog.py; src/rush/cli.py; src/rush/mcp.py; tests/test_license_matrix.py; tests/test_phase50_slsa_attestation.py; tests/test_catalog.py; tests/test_cli_registry.py; tests/test_mcp.py. |
| PR50.7 iam-audit | src/rush/tools/iam_audit.py; src/rush/tools/__init__.py; src/rush/catalog.py; src/rush/cli.py; src/rush/mcp.py; tests/test_iam_audit.py; tests/test_phase50_slsa_attestation.py; tests/test_catalog.py; tests/test_cli_registry.py; tests/test_mcp.py. |
| PR50.8 mem-profile | src/rush/tools/mem_profile.py; src/rush/tools/common.py; src/rush/permissions.py; src/rush/tools/__init__.py; src/rush/catalog.py; src/rush/cli.py; src/rush/mcp.py; tests/test_mem_profile.py; tests/test_catalog.py; tests/test_cli_registry.py; tests/test_mcp.py; pyproject.toml; uv.lock. |
| PR50.9 cold-start | src/rush/tools/cold_start.py; src/rush/tools/common.py; src/rush/permissions.py; src/rush/tools/__init__.py; src/rush/catalog.py; src/rush/cli.py; src/rush/mcp.py; tests/test_cold_start.py; tests/test_catalog.py; tests/test_cli_registry.py; tests/test_mcp.py. |
| PR50.10 media-opt | src/rush/tools/media_opt.py; src/rush/tools/common.py; src/rush/permissions.py; src/rush/tools/__init__.py; src/rush/catalog.py; src/rush/cli.py; src/rush/mcp.py; tests/test_media_opt.py; tests/test_tool_common.py; tests/test_catalog.py; tests/test_cli_registry.py; tests/test_mcp.py; pyproject.toml; uv.lock. |
| PR50.11 offline-review | src/rush/tools/offline_runner.py; src/rush/tools/review.py; src/rush/tools/common.py; src/rush/permissions.py; src/rush/tools/__init__.py; src/rush/catalog.py; src/rush/cli.py; src/rush/mcp.py; tests/test_offline_review.py; tests/test_catalog.py; tests/test_cli_registry.py; tests/test_mcp.py; pyproject.toml; uv.lock. |
| PR50.12 tui-diff | src/rush/tools/tui_diff.py; src/rush/cache.py; src/rush/tools/common.py; src/rush/tools/__init__.py; src/rush/catalog.py; src/rush/cli.py; src/rush/mcp.py; tests/test_tui_diff.py; tests/test_catalog.py; tests/test_cli_registry.py; tests/test_mcp.py. |
| PR50.13 benchmark | src/rush/tools/benchmark.py; src/rush/tools/common.py; src/rush/permissions.py; src/rush/tools/__init__.py; src/rush/catalog.py; src/rush/cli.py; src/rush/mcp.py; tests/test_benchmark.py; tests/test_tool_common.py; tests/test_catalog.py; tests/test_cli_registry.py; tests/test_mcp.py. |
| PR50.14 dead-asset | src/rush/tools/dead_asset.py; src/rush/tools/common.py; src/rush/permissions.py; src/rush/tools/__init__.py; src/rush/catalog.py; src/rush/cli.py; src/rush/mcp.py; tests/test_dead_asset.py; tests/test_tool_common.py; tests/test_phase50_slsa_attestation.py; tests/test_catalog.py; tests/test_cli_registry.py; tests/test_mcp.py. |
| PR50.15 pr-synthesize | src/rush/tools/pr_synthesize.py; src/rush/tools/provenance_ai.py; src/rush/tools/attest.py; src/rush/tools/common.py; src/rush/permissions.py; src/rush/tools/__init__.py; src/rush/catalog.py; src/rush/cli.py; src/rush/mcp.py; tests/test_pr_synthesize.py; tests/test_tool_common.py; tests/test_phase50_slsa_attestation.py; tests/test_catalog.py; tests/test_cli_registry.py; tests/test_mcp.py. |
| PR50.16–17 gates | every Phase 50 source/test/doc/config path explicitly listed in this plan; pyproject.toml; uv.lock; no other repository path. |

- Keep pillow==12.3.0 for I21.
- Remove cryptography==50.0.0 in PR50.5.7 only after an exhaustive source import check proves no other owner.
- Do not edit manifests for I24 until D50-04 names the exact extra/constraint.
- No feature except the D50-08-approved I19 dynamic probe and D50-04-approved I24 adapter may add a package.
- Each DOCS card creates one feature guide and changes only its named active references and exact anchored claims. Roadmaps, ADRs, old phase plans, specifications, reports, and backlog documents remain historical/authority evidence and are read-only unless a later user-approved plan amendment names them. There is no validator, fake sync command, global sweep, or percentage claim.

### Active documentation correction ledger

This ledger is binding discovery, not blanket write authority. A DOCS card may change only the intersection of its `Allowed writes` and the anchors below. Before editing, record the current text at every changed anchor in `Documentation claim corrections / <task ID>`; after editing, record the replacement and the focused search result. If a required active claim exists outside the row, stop and amend this plan rather than broadening the sweep.

| DOCS card | Exact existing anchors to inspect/change | Exact claim operation |
|---|---|---|
| PR50.2.5 | `prompt-eval` command insertion in docs/CLI_REFERENCE.md; `rush_prompt_eval` insertion in docs/MCP_REFERENCE.md; `[tools.prompt-eval]` insertion in docs/CONFIGURATION.md and examples/rush.toml; `prompt-eval` row in docs/TOOL_CATALOG.md | Add recorded-input schema/statuses and explicitly exclude provider execution, CodeBLEU, telemetry, cache, and network. |
| PR50.3.7 | `error-catalog` command/tool/config/catalog/example insertions in docs/CLI_REFERENCE.md, docs/MCP_REFERENCE.md, docs/CONFIGURATION.md, docs/TOOL_CATALOG.md, and examples/rush.toml; generated-artifact rule in docs/SECURITY.md | Add audit/generate boundaries and contained atomic outputs; exclude source rewrite and implicit generation. |
| PR50.4.5 | `provenance-ai` command/tool/config/catalog/example insertions | Add exact trailer denominator, shallow-history flag, and unknown survival/correlation states; exclude causal/authorship claims. |
| PR50.5.8 | README.md/README2.md/README3.md badge, summary, Pillar 9, command, MCP, and score rows; docs/README.md Phase 50 list; docs/ARCHITECTURE.md attestation-generator entry; `attest` entries in docs/CLI_REFERENCE.md, docs/MCP_REFERENCE.md, docs/CONFIGURATION.md, docs/TOOL_CATALOG.md; docs/SECURITY.md Phase 50 heading/body; docs/GLOSSARY.md generator term; attestation claims in docs/user-guide/faq.md, docs/user-guide/working-with-ai-agents.md, and docs/tutorials/before-a-pull-request.md; examples/rush.toml | Replace signed/Level/verified/reproducible/builder-trust claims with real-artifact Statement/v1 `unsigned_draft`, guarded export, canonical route, deprecated alias, and explicit non-goals; remove false badge/score. |
| PR50.6.7 | README.md/README2.md/README3.md Pillar 9 and command rows; docs/README.md Phase 50 list; `license-matrix` entries in docs/CLI_REFERENCE.md, docs/CLI_COOKBOOK.md, docs/MCP_REFERENCE.md, docs/CONFIGURATION.md, docs/TOOL_CATALOG.md, docs/USER_GUIDE.md, docs/VIBECODING.md, docs/user-guide/advanced-checks.md, docs/user-guide/checking-code.md, docs/user-guide/everyday-workflow.md, docs/user-guide/faq.md, docs/workflows/supply_chain_security_and_flagship_release.md, and examples/rush.toml | Replace compatibility/copyright/copolyft certainty with evidence source, exact allowlist match, `manual_review`, and no-legal-advice boundary. |
| PR50.7.5 | README.md/README2.md/README3.md Pillar 9 and command rows; IAM row in docs/AGENTIC_RUSH.md; Phase 50 entries in docs/ARCHITECTURE.md and docs/developer/architecture.md; `iam-audit` entries in docs/CLI_REFERENCE.md, docs/MCP_REFERENCE.md, docs/CONFIGURATION.md, docs/TOOL_CATALOG.md, docs/SECURITY.md, and examples/rush.toml | Replace synthesized/deployable/least-privilege/default-wildcard claims with the approved finite map, unknown resources/infrastructure, and mandatory review. |
| PR50.8.9 | `mem-profile` command/tool/config/catalog/example insertions | Distinguish static `potential` evidence from D50-08-approved optional sampling; document skipped states and never claim a proven leak. |
| PR50.9.7 | `cold-start` command/tool/config/catalog/example insertions | State Python-only AST inventory and explicit slow `-X importtime`; exclude Node, patches, and percent-improvement claims. |
| PR50.10.9 | `media-opt` command/tool/config/catalog/example insertions; media output rule in docs/SECURITY.md | State audit default, exact SVG rules, measured PNG/WebP candidate semantics, containment, and `no_improvement`; exclude automatic markup edits, AVIF unless locked support is proved, zero-loss, and savings guarantees. |
| PR50.11.6 | `offline-review` command/tool/config/catalog/example insertions; offline-model rule in docs/SECURITY.md | Only after D50-04: document the exact optional extra, user-supplied checksum/license evidence, slow permission, skipped states, and no bundle/download/network fallback. |
| PR50.12.7 | `tui-diff` command/tool/config/catalog/example insertions | State canonical raw delta data, bounded CLI-only noninteractive rendering, and unknown evidence; exclude full-screen/event-loop/60-FPS claims unless the plan is amended. |
| PR50.13.7 | `benchmark` command/tool/config/catalog/example insertions | State supplied arrays/units, exact descriptive formulas, threshold/fail policy, and explicit baseline record; exclude suite orchestration and statistical significance. |
| PR50.14.9 | README.md/README2.md/README3.md Pillar 9 and command rows; dead-asset row in docs/AGENTIC_RUSH.md; Phase 50 entries in docs/ARCHITECTURE.md and docs/developer/architecture.md; `dead-asset` entries in docs/CLI_REFERENCE.md, docs/MCP_REFERENCE.md, docs/CONFIGURATION.md, docs/TOOL_CATALOG.md, docs/SECURITY.md, and examples/rush.toml | Replace perfect-detection/safe-prune/Git-rollback/CSS-token claims with referenced/candidate/uncertain states and the manifest/hash/rescan/permission protocol. |
| PR50.15.7 | README.md/README2.md/README3.md Pillar 9 and command rows; PR-synthesis row in docs/AGENTIC_RUSH.md; Phase 50 entries in docs/ARCHITECTURE.md and docs/developer/architecture.md; `pr-synthesize` entries in docs/CLI_REFERENCE.md, docs/MCP_REFERENCE.md, docs/CONFIGURATION.md, docs/TOOL_CATALOG.md, docs/SECURITY.md, and examples/rush.toml | Replace inferred reviewer/risk/test/coverage/blast/SLSA/pass claims with supplied ToolResult/Git evidence, explicit missing states, contained export, and no GitHub API. |

Every row also creates its named `docs/tools/*.md` guide. Historical roadmap, ADR, specification, plan, report, backlog, and release-history claims are never “corrected” by these cards; they remain read-only evidence of the requirement conflict.

## Ordered execution workstreams and atomic task cards

The task runbook is the implementation authority. Read every card as if it were the only task available: phase inventories do not grant writes, neighboring cards do not supply omitted design, and a failed discovery or verification condition requires a stop rather than improvisation.

### PR50.0 — Admission and unresolved decision

#### PR50.0.1 — EVIDENCE: establish the implementation baseline

- **Task ID and binary outcome:** PR50.0.1; an accepted non-main baseline is recorded, or implementation is stopped.
- **Start goal:** Prove checkout, revision, dirty state, interpreter, existing Phase 50 behavior, and pre-existing failures before any test or source edit.
- **Prerequisites:** Explicit user authority for a non-main implementation worktree. This planning worktree does not grant implementation authority.
- **Documentation impact:** Create docs/developer/phase-50-implementation-evidence.md for evidence only.
- **Dependency impact:** None.
- **Allowed writes:** docs/developer/phase-50-implementation-evidence.md only.
- **Allowed reads:** AGENTS.md; pyproject.toml; uv.lock; docs/developer/repository-remediation-plan.md; docs/developer/rush-token-innovation-enhancement-report-plan.md; this plan; git/worktree metadata; paths named in this plan.
- **Prohibited:** Creating a branch/worktree; code, test, dependency, config, or guide edits; using main; repairing or hiding baseline failures.
- **Actions:**
  1. Run `git status --short --branch`, `git rev-parse HEAD`, `git log -1 --oneline`, `git worktree list`, `.venv/Scripts/python.exe --version`, `.venv/Scripts/python.exe -m pytest tests/test_phase50_slsa_attestation.py tests/test_catalog.py tests/test_cli_registry.py tests/test_mcp.py -q`, `.venv/Scripts/ruff.exe check src tests scripts`, and `.venv/Scripts/ruff.exe format --check src tests scripts`. Record each exit and failure without repair.
  2. Make this exact change in only docs/developer/phase-50-implementation-evidence.md: record timestamp, checkout, branch, HEAD, dirty paths, Python version, each command/exit, each pre-existing failure, approver, D50-04 state, and every Phase 50 source/test/doc path classified as existing or absent.
  3. Run `git status --short`. The evidence file must be the only new path. Compare its inventory to the repository and retain the command transcripts.
- **Evidence:** Literal commands, exits, SHA, dirty paths, path classification, D50-04 status, timestamp, approver.
- **Stop:** Main; unauthorized worktree/revision; non-3.12 interpreter; overlapping dirty path without ownership; unclassified baseline failure.
- **Verified outcome:** PR50.1.1 and feature RED cards may start; no GREEN card is unlocked.

#### PR50.0.2 — DECISION: close or isolate I24

- **Task ID and binary outcome:** PR50.0.2; D50-04 is fully approved and recorded, or all PR50.11 work remains blocked.
- **Start goal:** Prevent the executor from choosing a runtime, version, provider, model, license, checksum, or download policy.
- **Prerequisites:** PR50.0.1 and an explicit user decision.
- **Documentation impact:** Update only D50-04 in docs/developer/phase-50-implementation-evidence.md.
- **Dependency impact:** Record an exact optional constraint; install nothing.
- **Allowed writes:** docs/developer/phase-50-implementation-evidence.md only.
- **Allowed reads:** ADR-0036; roadmap I24; pyproject.toml; uv.lock; user-supplied model/runtime evidence.
- **Prohibited:** Dependency resolution, model download/bundling/generation, inference, or treating the plan recommendation as approval.
- **Actions:**
  1. Inspect the decision for package, exact constraint, providers, ONNX format, user-supplied path, license evidence, SHA-256 rule, zero-download rule, socket-denial test seam, and absent-runtime/model behavior.
  2. Make this exact change in only the evidence file: record owner/date/literal values/sources and skipped-without-network behavior. If one field is missing, record the missing fields and keep D50-04 blocked.
  3. Re-inspect the record against every PR50.11 prerequisite and confirm that it unlocks all PR50.11 cards or none.
- **Evidence:** Complete decision record or explicit blocker.
- **Stop:** Partial approval, unpinned dependency, unknown license/checksum, download/bundle assumption, weakened zero-network claim.
- **Verified outcome:** I24 is exactly admitted or isolated without blocking other features.

#### PR50.0.3 — DECISION: disposition I13 live evaluation versus recorded evidence

- **Task ID and binary outcome:** PR50.0.3; D50-10 records an approved I13 scope and successor owner, or every PR50.2 card remains blocked.
- **Start goal:** Prevent the executor from silently replacing live multi-model evaluation, CodeBLEU, telemetry, and latency requirements.
- **Prerequisites:** PR50.0.1 and explicit user decision.
- **Documentation impact:** Record D50-10 only in implementation evidence.
- **Dependency impact:** Record whether any provider/CodeBLEU dependency is authorized; install nothing.
- **Allowed writes:** docs/developer/phase-50-implementation-evidence.md only.
- **Allowed reads:** roadmap I13; repository AI-eval/token/MCP seams; D50-10 recommendation.
- **Prohibited:** Test/source/manifest/public-doc edits; treating recommendation as approval.
- **Actions:**
  1. Inspect the decision for live versus recorded execution, models, task source, patch metric, token/cost source, network, telemetry, latency target, and successor owner for every deferred item.
  2. Make this exact change in only the evidence file: record owner/date and one literal disposition for every field under `Decision records / PR50.0.3`; missing fields remain blockers.
  3. Reconcile the record against I13-A/B/C and confirm all PR50.2 cards unlock or none.
- **Evidence:** Complete D50-10 record or blocker.
- **Stop:** Partial/implicit approval, live credentials in tests, or unnamed deferred owner.
- **Verified outcome:** PR50.2 may start only after complete approval.

#### PR50.0.4 — DECISION: disposition I14 language and generation scope

- **Task ID and binary outcome:** PR50.0.4; D50-11 selects exact languages/generation behavior and deferred owner, or PR50.3 remains blocked.
- **Start goal:** Prevent invented Rust parsing or source rewriting.
- **Prerequisites:** PR50.0.1 and explicit user decision.
- **Documentation impact:** Evidence record only.
- **Dependency impact:** Record any parser decision; install nothing.
- **Allowed writes:** docs/developer/phase-50-implementation-evidence.md only.
- **Allowed reads:** roadmap I14; current parser/helpers; D50-11.
- **Prohibited:** Test/source/manifest/public-doc edits.
- **Actions:**
  1. Inspect decision for Python forms, TypeScript forms, Rust disposition, generated Python/module/docs schemas, source-rewrite exclusion, and successor owner.
  2. Record every literal field under `Decision records / PR50.0.4`; no default language or generator behavior.
  3. Reconcile against I14-A/B and confirm the entire packet unlocks or none.
- **Evidence:** Complete D50-11 record or blocker.
- **Stop:** Supported syntax/output schema/deferred owner missing.
- **Verified outcome:** PR50.3 may start only after complete approval.

#### PR50.0.5 — DECISION: disposition I15 attribution, survival, and correlation

- **Task ID and binary outcome:** PR50.0.5; D50-12 names the exact evidence boundary and deferred owner, or PR50.4 remains blocked.
- **Start goal:** Prevent commit attribution from being presented as line survival or defect causation.
- **Prerequisites:** PR50.0.1 and explicit user decision.
- **Documentation impact:** Evidence record only.
- **Dependency impact:** Record any approved statistics/evidence dependency; install nothing.
- **Allowed writes:** docs/developer/phase-50-implementation-evidence.md only.
- **Allowed reads:** roadmap I15; Git/flight-recorder evidence seams; D50-12.
- **Prohibited:** Test/source/manifest/public-doc edits; inferred evidence.
- **Actions:**
  1. Inspect decision for trailer keys, denominator, history window, shallow behavior, survival/correlation disposition, unknown-state wording, and successor owner.
  2. Record exact values under `Decision records / PR50.0.5`.
  3. Reconcile against I15-A/B and unlock all PR50.4 cards or none.
- **Evidence:** Complete D50-12 record or blocker.
- **Stop:** Unknown values can be rendered as zero/success or deferred owner absent.
- **Verified outcome:** PR50.4 may start only after complete approval.

#### PR50.0.6 — DECISION: disposition I17 evidence versus linking/legal analysis

- **Task ID and binary outcome:** PR50.0.6; D50-13 approves an exact evidence/policy boundary and successor owner, or PR50.6 remains blocked.
- **Start goal:** Prevent license evidence from becoming unsupported legal compatibility.
- **Prerequisites:** PR50.0.1 and explicit user decision.
- **Documentation impact:** Evidence record only.
- **Dependency impact:** Record parser/policy packages if any; install nothing.
- **Allowed writes:** docs/developer/phase-50-implementation-evidence.md only.
- **Allowed reads:** roadmap I17; current license scanner/manifests; D50-13.
- **Prohibited:** Test/source/manifest/public-doc edits; legal conclusion.
- **Actions:**
  1. Inspect decision for supported manifests, metadata sources, exact allowlist rule, compound/free-text/copyleft handling, linking/SPDX disposition, legal disclaimer, and successor owner.
  2. Record all fields under `Decision records / PR50.0.6`.
  3. Reconcile I17-A/B and unlock the packet or none.
- **Evidence:** Complete D50-13 record or blocker.
- **Stop:** Any evidence source/classification/deferred owner missing.
- **Verified outcome:** PR50.6 may start only after complete approval.

#### PR50.0.7 — DECISION: disposition I20 Python, Node, execution, and patches

- **Task ID and binary outcome:** PR50.0.7; D50-14 selects exact runtime/language scope and successor owner, or PR50.9 remains blocked.
- **Start goal:** Prevent Python-only implementation from silently closing Node/patch requirements.
- **Prerequisites:** PR50.0.1 and explicit user decision.
- **Documentation impact:** Evidence record only.
- **Dependency impact:** Record any Node/parser dependency; install nothing.
- **Allowed writes:** docs/developer/phase-50-implementation-evidence.md only.
- **Allowed reads:** roadmap I20; runner/interpreter seams; D50-14.
- **Prohibited:** Test/source/manifest/public-doc edits.
- **Actions:**
  1. Inspect decision for admitted languages, static/slow modes, interpreter, sandbox wording, timing format, threshold, patch behavior, and successor owner.
  2. Record exact values under `Decision records / PR50.0.7`.
  3. Reconcile I20-A/B and unlock the packet or none.
- **Evidence:** Complete D50-14 record or blocker.
- **Stop:** Language/execution/patch disposition incomplete.
- **Verified outcome:** PR50.9 may start only after complete approval.

#### PR50.0.8 — DECISION: disposition I21 audit and mutation scope

- **Task ID and binary outcome:** PR50.0.8; D50-15 selects exact formats/operations/claims and successor owner, or PR50.10 remains blocked.
- **Start goal:** Prevent implicit markup mutation, unsupported AVIF, or savings/zero-loss claims.
- **Prerequisites:** PR50.0.1 and explicit user decision.
- **Documentation impact:** Evidence record only.
- **Dependency impact:** Record exact imaging dependency disposition; install nothing.
- **Allowed writes:** docs/developer/phase-50-implementation-evidence.md only.
- **Allowed reads:** roadmap I21; locked Pillow manifest/capabilities; D50-15.
- **Prohibited:** Test/source/manifest/public-doc edits; capability inference.
- **Actions:**
  1. Inspect decision for audit rules, sanitize allowlist, PNG/WebP/AVIF admission, output/replace semantics, markup behavior, size/equivalence claims, and successor owner.
  2. Record exact values under `Decision records / PR50.0.8`.
  3. Reconcile I21-A/B/C and unlock the packet or none.
- **Evidence:** Complete D50-15 record or blocker.
- **Stop:** Format/operation/claim/deferred owner missing.
- **Verified outcome:** PR50.10 may start only after complete approval.

#### PR50.0.9 — DECISION: select I22 full-screen application or bounded renderer

- **Task ID and binary outcome:** PR50.0.9; D50-16 selects one complete CLI outcome and test boundary, or PR50.12 remains blocked.
- **Start goal:** Prevent a thin table from being called the promised full-screen TUI.
- **Prerequisites:** PR50.0.1 and explicit user decision.
- **Documentation impact:** Evidence record only.
- **Dependency impact:** Record any new terminal dependency; install nothing.
- **Allowed writes:** docs/developer/phase-50-implementation-evidence.md only.
- **Allowed reads:** roadmap I22; Rich/CLI/cache/Git seams; D50-16.
- **Prohibited:** Test/source/manifest/public-doc edits; blended outcomes.
- **Actions:**
  1. Inspect decision for delta data, identity, cache source, full-screen/event-loop/keys/render behavior, noninteractive fallback, MCP data, and successor owner if narrowed.
  2. Record one selected outcome under `Decision records / PR50.0.9`; if full-screen is selected, record that PR50.12 requires an approved plan amendment before implementation.
  3. Reconcile I22-A/B and confirm current bounded cards unlock only for the bounded selection.
- **Evidence:** Complete D50-16 selection or blocker.
- **Stop:** Outcome mixes full-screen claims with thin implementation.
- **Verified outcome:** Current PR50.12 cards start only for bounded selection; full-screen selection triggers amendment.

#### PR50.0.10 — DECISION: disposition I26 orchestration and statistical claims

- **Task ID and binary outcome:** PR50.0.10; D50-17 selects supplied samples versus repeated execution/significance and successor owner, or PR50.13 remains blocked.
- **Start goal:** Prevent descriptive deltas from being called statistical significance.
- **Prerequisites:** PR50.0.1 and explicit user decision.
- **Documentation impact:** Evidence record only.
- **Dependency impact:** Record any runner/statistics package; install nothing.
- **Allowed writes:** docs/developer/phase-50-implementation-evidence.md only.
- **Allowed reads:** roadmap I26; runner/store seams; D50-17.
- **Prohibited:** Test/source/manifest/public-doc edits.
- **Actions:**
  1. Inspect decision for sample source, execution count, formulas, percentile, significance, baseline initialization, units, thresholds, and successor owner.
  2. Record exact values under `Decision records / PR50.0.10`.
  3. Reconcile I26-A/B and unlock packet or none.
- **Evidence:** Complete D50-17 record or blocker.
- **Stop:** Sample/statistic/store/deferred owner missing.
- **Verified outcome:** PR50.13 may start only after complete approval.

#### PR50.0.11 — DECISION: disposition I27 file assets versus CSS/design tokens

- **Task ID and binary outcome:** PR50.0.11; I27 portion of D50-18 records exact inventory/prune scope and successor owner, or PR50.14 remains blocked.
- **Start goal:** Prevent file-asset scanning from silently closing design-token pruning.
- **Prerequisites:** PR50.0.1 and explicit user decision.
- **Documentation impact:** Evidence record only.
- **Dependency impact:** Record any parser package; install nothing.
- **Allowed writes:** docs/developer/phase-50-implementation-evidence.md only.
- **Allowed reads:** roadmap I27; current scanner; D50-18.
- **Prohibited:** Test/source/manifest/public-doc edits; Git rollback assumption.
- **Actions:**
  1. Inspect decision for asset/source extensions, literal/dynamic matching, CSS/design-token disposition, manifest/prune guards, recovery responsibility, and successor owner.
  2. Record exact values under `Decision records / PR50.0.11`.
  3. Reconcile I27-A/B and unlock packet or none.
- **Evidence:** Complete I27 decision or blocker.
- **Stop:** Any scope/guard/deferred owner missing.
- **Verified outcome:** PR50.14 may start only after complete approval.

#### PR50.0.12 — DECISION: disposition I28 observed evidence versus risk/reviewer inference

- **Task ID and binary outcome:** PR50.0.12; I28 portion of D50-18 records exact evidence/template/output scope and successor owner, or PR50.15 remains blocked.
- **Start goal:** Prevent unsupported risk tiers, reviewers, badges, or GitHub behavior.
- **Prerequisites:** PR50.0.1 and explicit user decision.
- **Documentation impact:** Evidence record only.
- **Dependency impact:** Record any ownership/risk/GitHub dependency; install nothing.
- **Allowed writes:** docs/developer/phase-50-implementation-evidence.md only.
- **Allowed reads:** roadmap I28; current synthesizer; Git/ToolResult seams; D50-18.
- **Prohibited:** Test/source/manifest/public-doc edits; inferred success.
- **Actions:**
  1. Inspect decision for Git inputs, ToolResult schema, missing states, risk/reviewer/badge/GitHub disposition, output permission, and successor owner.
  2. Record exact values under `Decision records / PR50.0.12`.
  3. Reconcile I28-A/B and unlock packet or none.
- **Evidence:** Complete I28 decision or blocker.
- **Stop:** Any evidence/claim/deferred owner missing.
- **Verified outcome:** PR50.15 may start only after complete approval.

### PR50.1 — Shared typed configuration contract

#### PR50.1.1 — RED: pin immutable typed option declarations

- **Task ID and binary outcome:** PR50.1.1; `test_tool_option_spec_declares_closed_types_and_constraints` and `test_tool_spec_exposes_immutable_option_specs` fail because typed option declarations do not exist.
- **Start goal:** Pin the declaration schema without changing TOML parsing.
- **Prerequisites:** PR50.0.1.
- **Documentation impact:** None.
- **Dependency impact:** None.
- **Allowed writes:** tests/test_catalog.py only.
- **Allowed reads:** src/rush/catalog.py; tests/test_catalog.py; every `ToolSpec(` construction returned by `rg -n "ToolSpec\\(" src tests`.
- **Prohibited:** Production/configuration/docs edits; Phase 50 ToolSpecs; parser assertions; arbitrary option values.
- **Actions:**
  1. Run `graft ask "ToolSpec constructions and positional callers" --source`; if Graft is unavailable, run `rg -n "ToolSpec\\(" src tests`. Inspect src/rush/catalog.py:36-47 and tests/test_catalog.py. Proceed only when `ToolOptionSpec`, `ToolOptionValue`, and `option_specs` are absent and all current positional fields can remain in place.
  2. Make this exact change in only tests/test_catalog.py: add the two named tests. Arrange `ToolOptionSpec` declarations for string, integer, float, boolean, string-tuple, and contained-path kinds; assert frozen instances, closed type vocabulary, validated defaults/choices/ranges/path kind, immutable tuple ownership on `ToolSpec`, and unchanged positional construction for existing fields.
  3. Run `.venv/Scripts/python.exe -m pytest tests/test_catalog.py::test_tool_option_spec_declares_closed_types_and_constraints tests/test_catalog.py::test_tool_spec_exposes_immutable_option_specs -q`. Retain ordinary assertion/import failures naming the absent declarations; then run `.venv/Scripts/python.exe -m pytest tests/test_catalog.py -q` and record the same defect without collection failure.
- **Evidence:** Two named RED results, caller inventory, and unchanged-field observation under `RED observations / PR50.1.1`.
- **Stop:** A positional caller cannot be preserved, a type/default rule is undecided, or failure is collection/tooling-related.
- **Verified outcome:** PR50.1.2 may start.

#### PR50.1.2 — GREEN: implement immutable typed option declarations

- **Task ID and binary outcome:** PR50.1.2; the declaration tests pass while all existing ToolSpec constructions remain compatible.
- **Start goal:** Add only the shared declaration types; do not change parsing.
- **Prerequisites:** Intended RED from PR50.1.1.
- **Documentation impact:** None.
- **Dependency impact:** None.
- **Allowed writes:** src/rush/catalog.py only.
- **Allowed reads:** tests/test_catalog.py; every exact `ToolSpec(` caller recorded by PR50.1.1.
- **Prohibited:** src/rush/config.py; test edits; Phase 50 registration; tool-name/maturity changes; docs/examples.
- **Actions:**
  1. Re-read the PR50.1.1 RED diff and every recorded caller. Confirm the two RED assertions remain unchanged and `ToolSpec` can append one defaulted field without reordering existing fields.
  2. Make this exact change in only src/rush/catalog.py: define frozen `ToolOptionSpec`, the closed `ToolOptionValue` alias, and `ToolSpec.option_specs: tuple[ToolOptionSpec, ...] = ()`; validate declaration invariants in `ToolOptionSpec.__post_init__` without feature-specific keys. Preserve every existing ToolSpec field and value.
  3. Run `.venv/Scripts/python.exe -m pytest tests/test_catalog.py::test_tool_option_spec_declares_closed_types_and_constraints tests/test_catalog.py::test_tool_spec_exposes_immutable_option_specs -q`, `.venv/Scripts/python.exe -m pytest tests/test_catalog.py -q`, `.venv/Scripts/python.exe -m pytest tests/test_cli_registry.py tests/test_mcp.py -q`, `.venv/Scripts/ruff.exe check src/rush/catalog.py tests/test_catalog.py`, and `.venv/Scripts/ruff.exe format --check src/rush/catalog.py tests/test_catalog.py`. Re-run `rg -n "ToolSpec\\(" src tests` and compare the caller set.
- **Evidence:** Unchanged RED assertions, green outputs, caller comparison, one-file production diff.
- **Stop:** Any test edit is needed, a current ToolSpec value changes, or feature-specific parsing enters catalog.py.
- **Verified outcome:** PR50.1.3 may start; no feature registration is unlocked.

#### PR50.1.3 — RED: pin declared-option parsing and rejection

- **Task ID and binary outcome:** PR50.1.3; three ordinary tests fail because `_parse` discards declared values and does not reject undeclared or mistyped values.
- **Start goal:** Pin parser behavior separately from the declaration type.
- **Prerequisites:** PR50.1.2 green.
- **Documentation impact:** None.
- **Dependency impact:** None.
- **Allowed writes:** tests/test_config.py only.
- **Allowed reads:** src/rush/config.py:42-149; src/rush/catalog.py `ToolOptionSpec`; tests/test_config.py; `rg -n "ToolConfig\\(|\\.engine_args|\\.check" src tests` results.
- **Prohibited:** Production/catalog/docs edits; feature-specific keys; coercing strings to numbers or booleans.
- **Actions:**
  1. Run the exact `rg` command above and inspect every ToolConfig constructor/read. Confirm `_parse` currently reads only engine_args/check and silently ignores other keys.
  2. Make this exact change in only tests/test_config.py: add `test_tool_config_preserves_declared_typed_options`, `test_tool_config_rejects_undeclared_option`, and `test_tool_config_rejects_wrong_type_range_choice_and_path`. Arrange a temporary catalog entry with all shared option kinds; Act through `_parse`; Assert exact typed values, immutable mapping, precedence-compatible engine_args/check, tool/key/type in errors, bool-not-int handling, and rejection of absolute/`..` paths.
  3. Run `.venv/Scripts/python.exe -m pytest tests/test_config.py::test_tool_config_preserves_declared_typed_options tests/test_config.py::test_tool_config_rejects_undeclared_option tests/test_config.py::test_tool_config_rejects_wrong_type_range_choice_and_path -q`, then `.venv/Scripts/python.exe -m pytest tests/test_config.py -q`. Retain only assertion failures caused by current discard/acceptance behavior.
- **Evidence:** Three RED results and complete caller inventory under `RED observations / PR50.1.3`.
- **Stop:** A value type/default remains undefined, a test mutates global catalog state without restoration, or failure is unrelated.
- **Verified outcome:** PR50.1.4 may start.

#### PR50.1.4 — GREEN: validate and preserve declared options

- **Task ID and binary outcome:** PR50.1.4; `_parse` returns immutable declared typed values and rejects every undeclared or invalid value without changing existing config behavior.
- **Start goal:** Satisfy only the PR50.1.3 parser contract.
- **Prerequisites:** PR50.1.3 RED.
- **Documentation impact:** None.
- **Dependency impact:** None.
- **Allowed writes:** src/rush/config.py only.
- **Allowed reads:** src/rush/catalog.py declarations; tests/test_config.py; caller inventory from PR50.1.3.
- **Prohibited:** Test edits; Phase 50 keys; nested arbitrary data; generic string coercion; unrelated config refactor.
- **Actions:**
  1. Reinspect `_parse`, the exact RED assertions, and existing error wording tests. Confirm one validation helper inside config.py can implement the closed declaration rules.
  2. Make this exact change in only src/rush/config.py: append an immutable `options` mapping to ToolConfig; validate reserved and declared keys; copy declaration defaults then TOML values; enforce exact shared types/choices/ranges/path rules; retain engine_args/check behavior and unknown-tool/maturity rejection.
  3. Run `.venv/Scripts/python.exe -m pytest tests/test_config.py::test_tool_config_preserves_declared_typed_options tests/test_config.py::test_tool_config_rejects_undeclared_option tests/test_config.py::test_tool_config_rejects_wrong_type_range_choice_and_path -q`, `.venv/Scripts/python.exe -m pytest tests/test_catalog.py tests/test_config.py -q`, `.venv/Scripts/python.exe -m pytest tests/test_cli_registry.py tests/test_mcp.py -q`, `.venv/Scripts/ruff.exe check src/rush/config.py tests/test_catalog.py tests/test_config.py`, and `.venv/Scripts/ruff.exe format --check src/rush/config.py tests/test_catalog.py tests/test_config.py`. Reinspect the diff for `object`, `Any`, or undeclared-key fallback.
- **Evidence:** RED link, focused/broader green outputs, immutable mapping assertion, one-file production diff.
- **Stop:** A RED assertion must change, existing config semantics regress, or feature-specific validation is required.
- **Verified outcome:** PR50.1.5 may start; admitted read-only feature core cards may start, but no effect card is unlocked.

#### PR50.1.5 — RED: pin shared contained atomic output semantics

- **Task ID and binary outcome:** PR50.1.5; three ordinary tests fail because Rush has no shared no-follow contained-output resolver or failure-preserving atomic byte writer.
- **Start goal:** Give every later artifact/store effect one tested filesystem primitive instead of asking each feature agent to invent containment and replacement behavior.
- **Prerequisites:** PR50.1.4 green.
- **Documentation impact:** None.
- **Dependency impact:** Python stdlib `os`, `tempfile`, and `pathlib` only; add no package.
- **Allowed writes:** Create tests/test_tool_common.py only.
- **Allowed reads:** src/rush/tools/common.py; src/rush/permissions.py; scripts/benchmarks/jobs.py `_write_json_atomic` only as non-production evidence; tests for current contained path handling returned by `rg -n "is_relative_to|resolve\\(|os.replace|Path.replace" src tests`.
- **Prohibited:** Production/docs/manifest edits; real project files; permission-policy tests; deletion; accepting absolute paths, `..`, symlinked existing parents, or symlink targets.
- **Actions:**
  1. Run `graft skeleton src/rush/tools/common.py`; then run `rg -n "is_relative_to|resolve\\(|os.replace|Path.replace|mkstemp|NamedTemporaryFile" src/rush/tools/common.py src/rush/permissions.py src tests scripts/benchmarks/jobs.py`. Record that no production helper satisfies the complete contract and record the exact existing callers that could conflict with the proposed names.
  2. Make this exact change in only tests/test_tool_common.py: add `test_resolve_contained_output_rejects_absolute_parent_and_symlink`, arranging a temporary root, valid nested target, absolute target, `..`, symlinked parent, and symlink target and asserting the valid target plus deterministic errors for every escape; add `test_atomic_write_replaces_only_contained_target_and_is_deterministic`, asserting same-directory temp placement, byte-exact repeated output, fsync-before-replace call order, and no residue; add `test_atomic_write_preserves_existing_target_and_removes_temp_on_failure`, injecting write/fsync/replace failures and asserting the old target bytes survive and every temp file is removed. Import proposed helpers inside each test body so collection succeeds.
  3. Run `.venv/Scripts/python.exe -m pytest tests/test_tool_common.py::test_resolve_contained_output_rejects_absolute_parent_and_symlink tests/test_tool_common.py::test_atomic_write_replaces_only_contained_target_and_is_deterministic tests/test_tool_common.py::test_atomic_write_preserves_existing_target_and_removes_temp_on_failure -q`, then `.venv/Scripts/python.exe -m pytest tests/test_tool_common.py -q`. Retain only failures for the absent helper names or asserted filesystem behavior.
- **Evidence:** Existing-helper inventory, three named RED results, fixture tree/hashes, and injected call order under `RED observations / PR50.1.5`.
- **Stop:** Windows cannot exercise the symlink cases under the project test policy, helper names conflict, atomicity requires an unapproved package, or a failure is collection/tooling-related.
- **Verified outcome:** PR50.1.6 may start.

#### PR50.1.6 — GREEN: implement shared contained atomic byte output

- **Task ID and binary outcome:** PR50.1.6; all three shared filesystem tests pass and later effect cards have one exact contained-output/atomic-replace dependency.
- **Start goal:** Implement only the shared primitive; permission selection and feature semantics remain in each caller.
- **Prerequisites:** Intended RED from PR50.1.5.
- **Documentation impact:** None.
- **Dependency impact:** None.
- **Allowed writes:** src/rush/tools/common.py only.
- **Allowed reads:** tests/test_tool_common.py; src/rush/permissions.py; the exact existing src/rush/tools/common.py callers recorded by PR50.1.5.
- **Prohibited:** Test/permission/docs/manifest/feature edits; deletion; implicit directory creation outside the supplied root; swallowing write/fsync/replace errors; feature-specific JSON or text encoding.
- **Actions:**
  1. Re-read the unchanged PR50.1.5 assertions and every current common.py caller. Fix the API as `resolve_contained_output(root: Path, relative: str | Path) -> Path` and `atomic_write_bytes(root: Path, relative: str | Path, data: bytes) -> Path`; do not add alternate overloads.
  2. Make this exact change in only src/rush/tools/common.py: reject absolute and parent-traversing relative paths; resolve the root and existing path components without following a symlink into/outside the root; reject an existing symlink target; create the target parent only inside root; create a uniquely named temp file in the target parent; write and flush bytes, `os.fsync`, recheck target/parent containment and symlink state, `os.replace` the temp onto the target, and remove the temp on every failure. Return the final path. Do not check `ExecutionPermissions`; callers must do that before invoking the helper.
  3. Run `.venv/Scripts/python.exe -m pytest tests/test_tool_common.py::test_resolve_contained_output_rejects_absolute_parent_and_symlink tests/test_tool_common.py::test_atomic_write_replaces_only_contained_target_and_is_deterministic tests/test_tool_common.py::test_atomic_write_preserves_existing_target_and_removes_temp_on_failure -q`, `.venv/Scripts/python.exe -m pytest tests/test_tool_common.py -q`, `.venv/Scripts/ruff.exe check src/rush/tools/common.py tests/test_tool_common.py`, `.venv/Scripts/ruff.exe format --check src/rush/tools/common.py tests/test_tool_common.py`, and `rg -n "is_relative_to|resolve\(|os.replace|Path.replace|mkstemp|NamedTemporaryFile|resolve_contained_output|atomic_write_bytes" src/rush/tools/common.py src/rush/permissions.py src tests scripts/benchmarks/jobs.py`; record the caller comparison and one-file production diff.
- **Evidence:** Unchanged RED assertions, green outputs, no-residue/old-file hashes, caller comparison, and exact public helper signatures under `GREEN observations / PR50.1.6`.
- **Stop:** Any test edit is required, a current common.py caller regresses, Windows behavior differs from the pinned contract, or permission/feature logic enters the helper.
- **Verified outcome:** PR50.F3 and all decision-admitted effect RED cards may start.

### Feature-card execution rule

Every capability packet separates core behavior, permissioned effects, catalog/registry, CLI, MCP, dependency, documentation, and installed-artifact transitions whenever they are independently observable. A core GREEN card may write only its tool module. Registry/transport files are prohibited until the packet's core and effect contracts are green. Tests written by a RED card are read-only in GREEN unless the card explicitly permits import/fixture wiring and lists the assertions that remain unchanged.

For a missing module, import occurs inside the named test body; collection must succeed. The focused RED command must execute every named test and report the exact missing module/class or wrong behavior. A route-not-found failure proves only route registration and may appear only in a route RED card; it never authorizes core behavior.

ToolFn.name remains hyphenated. PR50.F3 changes the shared MCP registrar once to expose the normalized underscore name. The four historical names `rush_license_matrix`, `rush_iam_audit`, `rush_dead_asset`, and `rush_pr_synthesize` become their tools' canonical normalized registrations; they are not aliases. `rush_attest_generate` is the only separate deprecated compatibility alias because canonical attest is `rush_attest`.

#### PR50.F3 — RED: pin canonical MCP name normalization

- **Task ID and binary outcome:** PR50.F3; focused MCP tests fail because dynamic catalog names preserve hyphens and existing Phase 50 manual routes contain business logic.
- **Start goal:** Pin one shared naming rule before any new tool is registered.
- **Prerequisites:** PR50.0.1 and D50-09.
- **Documentation impact:** None.
- **Dependency impact:** None.
- **Allowed writes:** tests/test_mcp.py; tests/test_phase50_slsa_attestation.py.
- **Allowed reads:** src/rush/mcp.py `_register_tools`; src/rush/tools/__init__.py `ALL_TOOLS`; src/rush/catalog.py; current MCP tests.
- **Prohibited:** Production/docs edits; feature registration; alias removal; testing private FastMCP internals instead of `build_server`.
- **Actions:**
  1. Run `graft ask "_register_tools build_server MCP tool names" --source`; if unavailable, run `rg -n "def _register_tools|name=f\"rush_|server.add_tool" src/rush/mcp.py tests/test_mcp.py tests/test_phase50_slsa_attestation.py`. Confirm a hyphenated fixture ToolFn becomes a hyphenated MCP name and enumerate the five manual Phase 50 wrappers.
  2. Make this exact change in only the two test files: add `test_mcp_catalog_names_normalize_toolfn_hyphens_to_underscores`; add `test_phase50_manual_mcp_names_contain_no_business_implementations`. Arrange an injected hyphenated ToolFn and the real server; assert one underscore canonical name, no hyphen variant, the four future canonical names and `rush_attest_generate` remain visible during migration, only `rush_attest_generate` is marked alias/deprecated, and no manual route constructs a scanner/generator/synthesizer.
  3. Run `.venv/Scripts/python.exe -m pytest tests/test_mcp.py::test_mcp_catalog_names_normalize_toolfn_hyphens_to_underscores tests/test_phase50_slsa_attestation.py::test_phase50_manual_mcp_names_contain_no_business_implementations -q`, then `.venv/Scripts/python.exe -m pytest tests/test_mcp.py tests/test_phase50_slsa_attestation.py -q`. Retain ordinary failures for current naming or route business logic.
- **Evidence:** Current-name inventory, two RED results, and server-visible tool list.
- **Stop:** FastMCP exposes a documented conflicting constraint, an existing non-Phase-50 route depends on hyphens, or failure is collection/tooling-related.
- **Verified outcome:** PR50.F4 may start.

#### PR50.F4 — GREEN: normalize shared MCP names and isolate the compatibility alias

- **Task ID and binary outcome:** PR50.F4; shared registration emits underscore canonical names, the five temporary manual routes contain no business implementation, and only `rush_attest_generate` is classified as an alias.
- **Start goal:** Change only shared naming and the temporary manual routes; do not migrate feature implementations.
- **Prerequisites:** PR50.F3 RED.
- **Documentation impact:** None until feature DOCS cards.
- **Dependency impact:** None.
- **Allowed writes:** src/rush/mcp.py only.
- **Allowed reads:** the two RED test files; src/rush/tools/__init__.py; existing five Phase 50 tool modules.
- **Prohibited:** Test edits; feature algorithm changes; new feature registration; unrelated MCP cleanup; stdout diagnostics.
- **Actions:**
  1. Reinspect `_register_tools` and each wrapper. Confirm the shared name expression is the only canonical registration seam and record each wrapper signature that compatibility must retain.
  2. Make this exact change in only src/rush/mcp.py: set canonical name to `f"rush_{tool.name.replace('-', '_')}"`; remove scanner/generator/synthesizer business logic from the five manual routes and reduce them to argument normalization plus lookup/call of the registered ToolFn when that ToolFn exists, while preserving current behavior until each owning feature integration card replaces the four canonical-name shims. Only `rush_attest_generate` may remain as an alias after all integrations.
  3. Run `.venv/Scripts/python.exe -m pytest tests/test_mcp.py::test_mcp_catalog_names_normalize_toolfn_hyphens_to_underscores tests/test_phase50_slsa_attestation.py::test_phase50_manual_mcp_names_contain_no_business_implementations -q`, `.venv/Scripts/python.exe -m pytest tests/test_mcp.py tests/test_phase50_slsa_attestation.py tests/test_cli_registry.py -q`, `.venv/Scripts/ruff.exe check src/rush/mcp.py tests/test_mcp.py tests/test_phase50_slsa_attestation.py`, and `.venv/Scripts/ruff.exe format --check src/rush/mcp.py tests/test_mcp.py tests/test_phase50_slsa_attestation.py`. Reinspect stdout writes and `server.add_tool` names.
- **Evidence:** RED link, canonical name list, wrapper source inspection, green outputs.
- **Stop:** `rush_attest_generate` must disappear, any other historical normalized name would become a duplicate alias, a wrapper needs business logic, or a non-Phase-50 route breaks.
- **Verified outcome:** Per-feature integration RED cards may assume underscore canonical MCP names.

### PR50.2 — I13 recorded prompt evaluation — blocked by D50-10

#### PR50.2.1 — RED: define a deterministic recorded-run matrix

- **Task ID and binary outcome:** PR50.2.1; both direct-tool tests execute and fail only because the recorded-run aggregation module or asserted core behavior is absent.
- **Start goal:** Define recorded-run aggregation without provider calls, benchmark execution, telemetry, or network.
- **Prerequisites:** PR50.0.1 and approved D50-10.
- **Documentation impact:** None.
- **Dependency impact:** None.
- **Allowed writes:** Create tests/test_prompt_eval.py.
- **Allowed reads:** src/rush/tools/ai_eval.py; src/rush/tools/base.py; tests/test_ai_eval.py; approved D50-10 record; roadmap I13.
- **Prohibited:** Collection-time import of missing module; live models; CodeBLEU; telemetry/cache/artifact writes; production edits.
- **Actions:**
  1. Run `graft ask "AiEvalTool ToolFn result construction" --source`; if unavailable, run `rg -n "class AiEvalTool|class ToolFn|ToolResult" src/rush/tools tests`. Inspect the exact result/finding constructors. Confirm `src/rush/tools/prompt_eval.py` is absent and import it only inside each test body so collection succeeds.
  2. Make this exact change in only tests/test_prompt_eval.py: add `test_prompt_eval_scores_normalized_fixture_runs_without_network`, arranging two contained task records and recorded runs with model, task_id, expected/observed tool sequence, patch_match, input_tokens, output_tokens, and cost_usd; instantiate `PromptEvalTool` directly with a socket-denial spy; assert exact ToolResult fields and per-model matrix calculations. Add `test_prompt_eval_retains_failed_cases_and_reports_matrix`, arranging one pass/one fail and asserting warn plus the exact failed task/model/reason finding. Do not invoke CLI, MCP, catalog, or ALL_TOOLS.
  3. Run `.venv/Scripts/python.exe -m pytest tests/test_prompt_eval.py::test_prompt_eval_scores_normalized_fixture_runs_without_network tests/test_prompt_eval.py::test_prompt_eval_retains_failed_cases_and_reports_matrix -q`, then `.venv/Scripts/python.exe -m pytest tests/test_prompt_eval.py -q`. Both test bodies must execute and fail only because the named module/class/behavior is absent.
- **Evidence:** Named tests, embedded record schema, focused RED.
- **Stop:** Live credentials/model needed, cost inferred, new dependency needed, or failure unrelated.
- **Verified outcome:** PR50.2.2 may start.

#### PR50.2.2 — GREEN: implement local recorded-run aggregation

- **Task ID and binary outcome:** PR50.2.2; one private, read-only PromptEvalTool computes the pinned recorded-run matrix and passes both direct-tool tests; public registration remains absent.
- **Start goal:** Implement only recorded input; live evaluation is excluded.
- **Prerequisites:** PR50.1.2 and intended RED from PR50.2.1.
- **Documentation impact:** None.
- **Dependency impact:** None.
- **Allowed writes:** Create src/rush/tools/prompt_eval.py only.
- **Allowed reads:** src/rush/tools/ai_eval.py; src/rush/tools/base.py; src/rush/tools/common.py; tests/test_prompt_eval.py; D50-10 evidence.
- **Prohibited:** Test, registry, catalog, CLI, MCP, configuration, docs, dependency, socket, subprocess, write, CodeBLEU, or telemetry changes.
- **Actions:**
  1. Inspect only the named helper/result constructors and unchanged RED assertions. Confirm the class can accept injected filesystem/socket boundaries and typed options without transport imports.
  2. Make this exact change in only src/rush/tools/prompt_eval.py: create `PromptEvalTool` named `prompt-eval`; resolve the two configured contained paths; validate exact record fields and unique model/task pairs; compute exact sequence match, patch_match, token/cost totals, pass rates, and baseline deltas; retain every failed case as a Finding; return error for malformed/escaping data, warn for failures, ok when all pass, and skipped when records are absent. Include no registry object or transport code.
  3. Run `.venv/Scripts/python.exe -m pytest tests/test_prompt_eval.py::test_prompt_eval_scores_normalized_fixture_runs_without_network tests/test_prompt_eval.py::test_prompt_eval_retains_failed_cases_and_reports_matrix -q`, `.venv/Scripts/python.exe -m pytest tests/test_prompt_eval.py -q`, `.venv/Scripts/ruff.exe check src/rush/tools/prompt_eval.py tests/test_prompt_eval.py`, and `.venv/Scripts/ruff.exe format --check src/rush/tools/prompt_eval.py tests/test_prompt_eval.py`. Reinspect with `rg -n "socket|subprocess|telemetry|ALL_TOOLS|TOOL_SPECS|click|FastMCP" src/rush/tools/prompt_eval.py`; only type/import strings explicitly permitted by the card may appear.
- **Evidence:** RED link, green outputs, socket-denial proof, changed paths.
- **Stop:** Inferred cost, live execution, path escape, duplicate transport logic.
- **Verified outcome:** PR50.2.3 may start; no public route exists yet.

#### PR50.2.3 — RED: pin prompt-eval catalog, CLI, and MCP exposure

- **Task ID and binary outcome:** PR50.2.3; route tests fail because the green core is not registered or publicly exposed.
- **Start goal:** Pin integration only after core behavior is green.
- **Prerequisites:** PR50.1.4, PR50.F4, and PR50.2.2.
- **Documentation impact:** None.
- **Dependency impact:** None.
- **Allowed writes:** tests/test_catalog.py; tests/test_cli_registry.py; tests/test_mcp.py.
- **Allowed reads:** src/rush/tools/prompt_eval.py; src/rush/tools/__init__.py; src/rush/catalog.py; src/rush/cli.py `build_catalog_path_command`; src/rush/mcp.py `_register_tools`.
- **Prohibited:** Production/core/docs edits; custom CLI/MCP business logic.
- **Actions:**
  1. Inspect the exact registrars with `graft ask "ALL_TOOLS TOOL_SPECS build_catalog_path_command _register_tools" --source` or bounded `rg`. Confirm the core is absent from all registries and the generic CLI accepts a required PATH.
  2. Make this exact change in only the three tests: add `test_prompt_eval_catalog_declares_typed_options_and_single_object`, `test_prompt_eval_cli_forwards_path_and_returns_tool_result`, and `test_prompt_eval_mcp_uses_canonical_name_and_matches_cli`; assert the two exact `ToolOptionSpec` declarations, one exported object identity in ALL_TOOLS, `rush prompt-eval PATH --json`, canonical `rush_prompt_eval`, canonical result equality through injected fixtures, and no manual MCP wrapper.
  3. Run `.venv/Scripts/python.exe -m pytest tests/test_catalog.py::test_prompt_eval_catalog_declares_typed_options_and_single_object tests/test_cli_registry.py::test_prompt_eval_cli_forwards_path_and_returns_tool_result tests/test_mcp.py::test_prompt_eval_mcp_uses_canonical_name_and_matches_cli -q`, then `.venv/Scripts/python.exe -m pytest tests/test_catalog.py tests/test_cli_registry.py tests/test_mcp.py -q`. Retain failures only for missing registration, route, or option declarations.
- **Evidence:** Three route RED results and current registrar observations.
- **Stop:** Generic PATH route cannot carry the contract, another command owns the name, or route behavior requires core changes.
- **Verified outcome:** PR50.2.4 may start.

#### PR50.2.4 — GREEN: register prompt-eval through shared transports

- **Task ID and binary outcome:** PR50.2.4; catalog, ALL_TOOLS, generic CLI, and normalized MCP expose one PromptEvalTool object.
- **Start goal:** Satisfy only the integration RED.
- **Prerequisites:** PR50.2.3 RED.
- **Documentation impact:** None.
- **Dependency impact:** None.
- **Allowed writes:** src/rush/tools/__init__.py; src/rush/catalog.py.
- **Allowed reads:** integration RED tests; src/rush/tools/prompt_eval.py; shared registrars.
- **Prohibited:** Core/test/CLI/MCP/docs edits; aliases; custom adapters.
- **Actions:**
  1. Reinspect object construction and ToolSpec ordering; confirm generic registration alone creates both public routes.
  2. Make this exact change in only the two allowed files: export/register one PromptEvalTool instance; add one real-adapter ToolSpec with the exact typed option declarations and descriptions limited to recorded-run behavior.
  3. Run `.venv/Scripts/python.exe -m pytest tests/test_catalog.py::test_prompt_eval_catalog_declares_typed_options_and_single_object tests/test_cli_registry.py::test_prompt_eval_cli_forwards_path_and_returns_tool_result tests/test_mcp.py::test_prompt_eval_mcp_uses_canonical_name_and_matches_cli -q`, `.venv/Scripts/python.exe -m pytest tests/test_prompt_eval.py tests/test_catalog.py tests/test_cli_registry.py tests/test_mcp.py -q`, `.venv/Scripts/ruff.exe check src/rush/tools/prompt_eval.py src/rush/tools/__init__.py src/rush/catalog.py tests/test_prompt_eval.py tests/test_catalog.py tests/test_cli_registry.py tests/test_mcp.py`, and `.venv/Scripts/ruff.exe format --check src/rush/tools/prompt_eval.py src/rush/tools/__init__.py src/rush/catalog.py tests/test_prompt_eval.py tests/test_catalog.py tests/test_cli_registry.py tests/test_mcp.py`. Reinspect object identity and server names.
- **Evidence:** RED link, object identity, route equality, green outputs.
- **Stop:** A transport edit is required, a second object is constructed, or description exceeds D50-10.
- **Verified outcome:** PR50.2.5 may start.

#### PR50.2.5 — DOCS: document recorded-only prompt evaluation

- **Task ID and binary outcome:** PR50.2.5; exact record schema, routes, config, statuses, and exclusions are documented.
- **Start goal:** Document only PR50.2.2 behavior.
- **Prerequisites:** PR50.2.4 green.
- **Documentation impact:** Create docs/tools/prompt_eval.md; modify docs/CLI_REFERENCE.md, docs/MCP_REFERENCE.md, docs/CONFIGURATION.md, docs/TOOL_CATALOG.md, examples/rush.toml.
- **Dependency impact:** None.
- **Allowed writes:** The six named paths only.
- **Allowed reads:** PromptEvalTool, ToolSpec, its tests.
- **Prohibited:** Live execution/FastMCP replay/CodeBLEU/telemetry/performance claims.
- **Actions:**
  1. Inspect source/tests and exact reference insertion points; stop if a generated owner controls one.
  2. Make this exact change in only the allowed files: document `prompt-eval PATH --json`, `rush_prompt_eval`, both typed config keys/defaults, required JSON fields, status meanings, no-write/no-network behavior, and the D50-10-approved recorded-only limit at the existing alphabetic command/tool/config insertion anchors.
  3. Run `.venv/Scripts/python.exe -m pytest tests/test_prompt_eval.py tests/test_catalog.py tests/test_cli_registry.py tests/test_mcp.py -q`; then run `rg -n "prompt-eval|rush_prompt_eval|benchmark_tasks_dir|recorded_runs_file"` on the six allowed files and record exact anchors.
- **Evidence:** Tests and focused documentation search.
- **Stop:** Name/key mismatch, unsupported claim, unlisted required path.
- **Verified outcome:** Only the D50-10-approved I13 disposition is closed; deferred items and successor owner remain explicit.

### PR50.3 — I14 error catalog preview and explicit artifacts — blocked by D50-11

#### PR50.3.1 — RED: pin deterministic read-only extraction

- **Task ID and binary outcome:** PR50.3.1; the direct audit test executes and fails only because deterministic read-only extraction is absent.
- **Start goal:** Define Python and literal TypeScript exception extraction without rewriting application error handling.
- **Prerequisites:** PR50.0.1 and approved D50-11.
- **Documentation impact:** None.
- **Dependency impact:** None.
- **Allowed writes:** Create tests/test_error_catalog.py.
- **Allowed reads:** roadmap I14; approved D50-11; src/rush/tools/base.py; Python ast patterns; literal TypeScript fixture patterns.
- **Prohibited:** Collection-time missing import; Rust support; fixture-source mutation; unpermitted writes; scripts/sync_docs.py.
- **Actions:**
  1. Run `graft ask "Python AST visitors and ToolFn result findings" --source` or bounded `rg -n "ast.NodeVisitor|class ToolFn" src/rush/tools tests`. Confirm the module is absent and import only inside test bodies.
  2. Make this exact change in only the test file: add `test_error_catalog_extracts_stable_codes_without_writing` using one Python `raise ValueError`, one literal TypeScript `throw new Error`, one unsupported expression, and a tree-hash spy. Assert deterministic content-derived codes, language/path/line/type/message evidence, RFC 7807 preview fields, warn for unsupported expression, and byte-identical tree. Do not assert generation or routes.
  3. Run `.venv/Scripts/python.exe -m pytest tests/test_error_catalog.py::test_error_catalog_extracts_stable_codes_without_writing -q`, then `.venv/Scripts/python.exe -m pytest tests/test_error_catalog.py -q`. Retain only exact missing module, class, or scan-behavior failures with successful collection.
- **Evidence:** Exact fixtures, paths, named RED failures.
- **Stop:** Scan-order code assignment, implicit write, new parser dependency, or source rewrite required.
- **Verified outcome:** PR50.3.2 may start.

#### PR50.3.2 — GREEN: implement deterministic read-only preview

- **Task ID and binary outcome:** PR50.3.2; the private ErrorCatalogTool extracts the pinned Python and literal TypeScript cases, renders deterministic previews, and performs no writes.
- **Start goal:** Satisfy PR50.3.1 using stdlib parsing.
- **Prerequisites:** PR50.1.2 and PR50.3.1 RED.
- **Documentation impact:** None.
- **Dependency impact:** None.
- **Allowed writes:** Create src/rush/tools/error_catalog.py only.
- **Allowed reads:** src/rush/tools/base.py; Python ast helpers; tests/test_error_catalog.py; D50-11.
- **Prohibited:** Test, registry, CLI, MCP, permission, write, docs, dependency, Rust, source-rewrite, or telemetry changes.
- **Actions:**
  1. Inspect unchanged PR50.3.1 assertions and the exact AST/finding constructors; confirm audit can remain pure and accepts injected reads.
  2. Make this exact change in only src/rush/tools/error_catalog.py: create `ErrorCatalogTool` named `error-catalog`; implement only read-only Python and literal TypeScript extraction, deterministic ID inputs, RFC 7807 previews, unsupported-expression warnings, malformed-input errors, and no-write audit. Do not add generation branches, option declarations, registration, or transports.
  3. Run `.venv/Scripts/python.exe -m pytest tests/test_error_catalog.py::test_error_catalog_extracts_stable_codes_without_writing -q`, `.venv/Scripts/python.exe -m pytest tests/test_error_catalog.py -q`, `.venv/Scripts/ruff.exe check src/rush/tools/error_catalog.py tests/test_error_catalog.py`, and `.venv/Scripts/ruff.exe format --check src/rush/tools/error_catalog.py tests/test_error_catalog.py`. Reinspect with `rg -n "write_text|open\\(.*[wa]|replace\\(|unlink|click|FastMCP|ALL_TOOLS" src/rush/tools/error_catalog.py` and retain a no-write result.
- **Evidence:** RED link, green commands, write-call review.
- **Stop:** Escape, denied write, nondeterministic IDs, duplicate transport behavior.
- **Verified outcome:** PR50.3.3 may start; audit remains private/unregistered.

#### PR50.3.3 — RED: pin permissioned contained catalog generation

- **Task ID and binary outcome:** PR50.3.3; generation tests fail because the audit-only tool has no guarded artifact branch.
- **Start goal:** Pin writes independently from extraction.
- **Prerequisites:** PR50.1.6 and PR50.3.2.
- **Documentation impact:** None.
- **Dependency impact:** None.
- **Allowed writes:** tests/test_error_catalog.py only.
- **Allowed reads:** src/rush/tools/error_catalog.py; src/rush/permissions.py `ExecutionPermissions`; src/rush/tools/common.py `resolve_contained_output` and `atomic_write_bytes`; tests/test_tool_common.py.
- **Prohibited:** Production/docs/route edits; scanned-source mutation; implicit output defaults.
- **Actions:**
  1. Inspect `ExecutionPermissions.artifact_write`, `resolve_contained_output`, `atomic_write_bytes`, and their exact PR50.1.5 tests. Confirm ErrorCatalogTool audit is green and contains no write branch.
  2. Make this exact change in only the test file: add `test_error_catalog_generate_requires_permission`, `test_error_catalog_generate_is_contained_atomic_and_idempotent`, and `test_error_catalog_generate_rejects_escape_and_preserves_existing_files`. Arrange denied/permitted permissions, configured `.py`/`.md` outputs, replace failure, `..`, symlink, and repeated runs; assert skipped/no-write, exact artifacts, byte identity, old-file preservation, and error/no outside write.
  3. Run `.venv/Scripts/python.exe -m pytest tests/test_error_catalog.py::test_error_catalog_generate_requires_permission tests/test_error_catalog.py::test_error_catalog_generate_is_contained_atomic_and_idempotent tests/test_error_catalog.py::test_error_catalog_generate_rejects_escape_and_preserves_existing_files -q`, then `.venv/Scripts/python.exe -m pytest tests/test_error_catalog.py -q`. Retain failures only for absent generation behavior.
- **Evidence:** Three effect RED results, fixture hashes, and named permission/atomic seams.
- **Stop:** Required helper cannot provide no-follow containment/atomicity, output schema is undecided, or test touches real project files.
- **Verified outcome:** PR50.3.4 may start.

#### PR50.3.4 — GREEN: add guarded deterministic catalog artifacts

- **Task ID and binary outcome:** PR50.3.4; generation writes only exact configured contained artifacts with permission and preserves audit behavior.
- **Start goal:** Satisfy only effect tests.
- **Prerequisites:** PR50.3.3 RED.
- **Documentation impact:** None.
- **Dependency impact:** None.
- **Allowed writes:** src/rush/tools/error_catalog.py only.
- **Allowed reads:** tests/test_error_catalog.py; tests/test_tool_common.py; src/rush/permissions.py; src/rush/tools/common.py.
- **Prohibited:** Test/registry/transport/docs edits; scanned-source changes; new parser package.
- **Actions:**
  1. Reinspect the three unchanged RED assertions and helper signatures; confirm exact output_module/export_docs inputs are sufficient.
  2. Make this exact change in only the module: add `generate` operation requiring artifact_write; validate contained configured targets; render deterministic type-safe constants/problem-details helpers and Markdown from audit records; write temp then replace; return artifacts; preserve old files on error and audit no-write behavior.
  3. Run `.venv/Scripts/python.exe -m pytest tests/test_error_catalog.py::test_error_catalog_generate_requires_permission tests/test_error_catalog.py::test_error_catalog_generate_is_contained_atomic_and_idempotent tests/test_error_catalog.py::test_error_catalog_generate_rejects_escape_and_preserves_existing_files tests/test_error_catalog.py::test_error_catalog_extracts_stable_codes_without_writing -q`, `.venv/Scripts/python.exe -m pytest tests/test_error_catalog.py -q`, `.venv/Scripts/ruff.exe check src/rush/tools/error_catalog.py tests/test_error_catalog.py`, and `.venv/Scripts/ruff.exe format --check src/rush/tools/error_catalog.py tests/test_error_catalog.py`. Reinspect every write call and its immediately preceding permission/containment branch.
- **Evidence:** RED link, write guard trace, hashes, green outputs.
- **Stop:** Any implicit target, scanned-source edit, non-atomic branch, or weakened audit result appears.
- **Verified outcome:** PR50.3.5 may start.

#### PR50.3.5 — RED: pin error-catalog registry, CLI options, and MCP arguments

- **Task ID and binary outcome:** PR50.3.5; integration tests fail because the green tool is not registered and no public route forwards the generation contract.
- **Start goal:** Pin public exposure without changing core behavior.
- **Prerequisites:** PR50.1.4, PR50.F4, PR50.3.4.
- **Documentation impact:** None.
- **Dependency impact:** None.
- **Allowed writes:** tests/test_catalog.py; tests/test_cli_registry.py; tests/test_mcp.py.
- **Allowed reads:** exact ErrorCatalogTool signature; registrars; `_run_tool`; shared typed-key table.
- **Prohibited:** Production/core/docs edits; transport-specific business logic.
- **Actions:**
  1. Inspect generic PATH limitations and `_run_tool` extra-argument patterns. Confirm generation needs a thin CLI adapter while MCP can use the registered callable.
  2. Add `test_error_catalog_catalog_declares_generation_options`, `test_error_catalog_cli_forwards_guarded_generation_arguments`, and `test_error_catalog_mcp_matches_cli_and_uses_canonical_name`; assert one ToolSpec/ALL_TOOLS object, three option declarations, audit CLI, `--generate-catalog --output-module --export-docs`, normalized `rush_error_catalog`, permission forwarding, ToolResult equality, and absence of manual MCP logic.
  3. Run `.venv/Scripts/python.exe -m pytest tests/test_catalog.py::test_error_catalog_catalog_declares_generation_options tests/test_cli_registry.py::test_error_catalog_cli_forwards_guarded_generation_arguments tests/test_mcp.py::test_error_catalog_mcp_matches_cli_and_uses_canonical_name -q`, then `.venv/Scripts/python.exe -m pytest tests/test_catalog.py tests/test_cli_registry.py tests/test_mcp.py -q`; retain missing route or option failures.
- **Evidence:** Route RED results and signature-forwarding matrix.
- **Stop:** Public arguments cannot map one-to-one to the ToolFn or require a core redesign.
- **Verified outcome:** PR50.3.6 may start.

#### PR50.3.6 — GREEN: register error-catalog and add a thin CLI adapter

- **Task ID and binary outcome:** PR50.3.6; one registered ErrorCatalogTool backs catalog, CLI, and normalized MCP behavior.
- **Start goal:** Satisfy integration RED only.
- **Prerequisites:** PR50.3.5 RED.
- **Documentation impact:** None.
- **Dependency impact:** None.
- **Allowed writes:** src/rush/tools/__init__.py; src/rush/catalog.py; src/rush/cli.py.
- **Allowed reads:** integration tests; ErrorCatalogTool; shared registrars.
- **Prohibited:** Core/test/MCP/docs edits; duplicate object or business logic.
- **Actions:**
  1. Reinspect `_run_tool` and Click option conventions; confirm one thin adapter is sufficient.
  2. Export/register one object; add one ToolSpec with exact option specs; add only argument declarations/normalization and one `_run_tool` call in CLI. Make no mcp.py change.
  3. Run `.venv/Scripts/python.exe -m pytest tests/test_catalog.py::test_error_catalog_catalog_declares_generation_options tests/test_cli_registry.py::test_error_catalog_cli_forwards_guarded_generation_arguments tests/test_mcp.py::test_error_catalog_mcp_matches_cli_and_uses_canonical_name -q`, `.venv/Scripts/python.exe -m pytest tests/test_error_catalog.py tests/test_catalog.py tests/test_cli_registry.py tests/test_mcp.py -q`, `.venv/Scripts/ruff.exe check src/rush/tools/error_catalog.py src/rush/tools/__init__.py src/rush/catalog.py src/rush/cli.py tests/test_error_catalog.py tests/test_catalog.py tests/test_cli_registry.py tests/test_mcp.py`, and `.venv/Scripts/ruff.exe format --check src/rush/tools/error_catalog.py src/rush/tools/__init__.py src/rush/catalog.py src/rush/cli.py tests/test_error_catalog.py tests/test_catalog.py tests/test_cli_registry.py tests/test_mcp.py`. Reinspect the CLI function body for extraction, rendering, or write logic.
- **Evidence:** Object identity, route equality, green outputs, thin-adapter source inspection.
- **Stop:** CLI contains business logic, MCP edit is needed, or option precedence diverges.
- **Verified outcome:** PR50.3.7 may start.

#### PR50.3.7 — DOCS: document audit/generate boundaries

- **Task ID and binary outcome:** PR50.3.7; supported forms, preview semantics, explicit writes, and limits are documented.
- **Start goal:** Prevent generated previews from being represented as automatic remediation.
- **Prerequisites:** PR50.3.6 green.
- **Documentation impact:** Create docs/tools/error_catalog.md; modify CLI/MCP/CONFIGURATION/TOOL_CATALOG/SECURITY references and examples/rush.toml.
- **Dependency impact:** None.
- **Allowed writes:** docs/tools/error_catalog.md; docs/CLI_REFERENCE.md; docs/MCP_REFERENCE.md; docs/CONFIGURATION.md; docs/TOOL_CATALOG.md; docs/SECURITY.md; examples/rush.toml.
- **Allowed reads:** src/rush/tools/error_catalog.py; tests/test_error_catalog.py; tests/test_catalog.py; tests/test_cli_registry.py; tests/test_mcp.py; the seven allowed documentation/configuration paths.
- **Prohibited:** Full-polyglot, application-rewrite, API-correctness, sync-script, or implicit-write claims.
- **Actions:**
  1. Inspect the `error-catalog` command, MCP tool, config table, catalog row, generated-artifact security rule, and example anchors in the six existing allowed files; record the pre-edit claim at each changed anchor.
  2. Make this exact change only at those anchors and in docs/tools/error_catalog.md: document the audit default, explicit generate operation plus `artifact_write`, supported Python/literal-TypeScript forms, deterministic ID inputs, RFC 7807 preview fields, contained atomic output, unsupported-expression warnings, and manual deletion of generated artifacts as rollback.
  3. Run `.venv/Scripts/python.exe -m pytest tests/test_error_catalog.py tests/test_catalog.py tests/test_cli_registry.py tests/test_mcp.py -q`; then run `rg -n "error-catalog|rush_error_catalog|generate-catalog|output_module|export_docs|allow-artifact-write" docs/tools/error_catalog.md docs/CLI_REFERENCE.md docs/MCP_REFERENCE.md docs/CONFIGURATION.md docs/TOOL_CATALOG.md docs/SECURITY.md examples/rush.toml` and record every exact changed anchor.
- **Evidence:** Tests and docs search.
- **Stop:** Unsupported claim or mismatched option.
- **Verified outcome:** Only the D50-11-approved I14 disposition is closed; Rust/deferred work remains named.

### PR50.4 — I15 evidence-bounded AI attribution — blocked by D50-12

#### PR50.4.1 — RED: pin trailer attribution and unknown metrics

- **Task ID and binary outcome:** PR50.4.1; tests fail because provenance-ai is absent while exact observed/unknown states are asserted.
- **Start goal:** Attribute only exact configured trailers; shallow or insufficient history must not become a success claim.
- **Prerequisites:** PR50.0.1 and approved D50-12.
- **Documentation impact:** None.
- **Dependency impact:** Git is environment-discovered.
- **Allowed writes:** Create tests/test_provenance_ai.py.
- **Allowed reads:** roadmap I15; run_subprocess; Git tools; route registrars.
- **Prohibited:** Live developer history; telemetry/flight records; survival/regression packages; inferred AI labels.
- **Actions:**
  1. Inspect run_subprocess and a Git-backed tool's missing-engine result. Confirm provenance-ai is absent.
  2. Make this exact change in only the test file: add `test_provenance_ai_uses_commit_trailers_and_reports_shallow_history` with an injected four-commit transcript, two exact AI trailers, one human commit, and shallow marker; instantiate the tool directly and assert counts, 50 percent attribution, shallow_history true, survival_30d unknown. Add `test_provenance_ai_does_not_claim_unobserved_survival_or_defect_correlation` with young commits/no bug mapping; assert unknown rather than zero/success and explanatory findings. Do not exercise CLI, MCP, catalog, or live Git.
  3. Run `.venv/Scripts/python.exe -m pytest tests/test_provenance_ai.py::test_provenance_ai_uses_commit_trailers_and_reports_shallow_history tests/test_provenance_ai.py::test_provenance_ai_does_not_claim_unobserved_survival_or_defect_correlation -q`, then `.venv/Scripts/python.exe -m pytest tests/test_provenance_ai.py -q`; retain absent-contract failures and the injected-runner assertion proving no live Git data was read.
- **Evidence:** Fake transcripts and named RED output.
- **Stop:** Line authorship needed, shallow treated complete, dependency proposed.
- **Verified outcome:** PR50.4.2 may start.

#### PR50.4.2 — GREEN: implement observed trailer reporting

- **Task ID and binary outcome:** PR50.4.2; one private ProvenanceAiTool reports exact trailer attribution and explicit unknowns; registration and transports remain absent.
- **Start goal:** Implement only evidence pinned by PR50.4.1.
- **Prerequisites:** PR50.1.2 and PR50.4.1 RED.
- **Documentation impact:** None.
- **Dependency impact:** None; absent Git returns skipped.
- **Allowed writes:** Create src/rush/tools/provenance_ai.py only.
- **Allowed reads:** run_subprocess/skipped_result; Git helpers; RED evidence.
- **Prohibited:** Test, registry, catalog, CLI, MCP, docs, dependency, blame/-S, flight-recorder, telemetry, or invented-label changes.
- **Actions:**
  1. Inspect run_subprocess argv pattern and exact Git commands for hash/timestamp/message/trailers and shallow state.
  2. Make this exact change in only src/rush/tools/provenance_ai.py: create `ProvenanceAiTool` named `provenance-ai` with injected runner; exact case-sensitive configured trailer match; observed counts/percentage; shallow metadata; eligibility windows; unknown survival/correlation without evidence; argv plus stdin DEVNULL; skipped for missing Git/not repo; error malformed output; warn incomplete/unknown requested metrics; ok only complete attribution. Do not register it.
  3. Run `.venv/Scripts/python.exe -m pytest tests/test_provenance_ai.py::test_provenance_ai_uses_commit_trailers_and_reports_shallow_history tests/test_provenance_ai.py::test_provenance_ai_does_not_claim_unobserved_survival_or_defect_correlation -q`, `.venv/Scripts/python.exe -m pytest tests/test_provenance_ai.py -q`, `.venv/Scripts/ruff.exe check src/rush/tools/provenance_ai.py tests/test_provenance_ai.py`, and `.venv/Scripts/ruff.exe format --check src/rush/tools/provenance_ai.py tests/test_provenance_ai.py`. Reinspect argv and search for blame, `-S`, telemetry, survival calculation, and route imports.
- **Evidence:** RED link, fake-call assertions, command outputs.
- **Stop:** Ambiguous Git parse, unknown converted to zero, new evidence source needed.
- **Verified outcome:** PR50.4.3 may start; the core remains private.

#### PR50.4.3 — RED: pin provenance-ai registration and public route equality

- **Task ID and binary outcome:** PR50.4.3; integration tests fail because the green core is absent from catalog, ALL_TOOLS, CLI, and normalized MCP.
- **Start goal:** Pin only public exposure and typed options.
- **Prerequisites:** PR50.1.4, PR50.F4, PR50.4.2.
- **Documentation impact:** None.
- **Dependency impact:** None.
- **Allowed writes:** tests/test_catalog.py; tests/test_cli_registry.py; tests/test_mcp.py.
- **Allowed reads:** ProvenanceAiTool signature; registrars; shared option table.
- **Prohibited:** Production/core/docs edits; live Git; custom transport implementation.
- **Actions:**
  1. Inspect registrars and confirm generic PATH route is compatible.
  2. Add `test_provenance_ai_catalog_declares_trailers_and_since_days`, `test_provenance_ai_cli_uses_registered_tool`, and `test_provenance_ai_mcp_matches_cli_and_uses_canonical_name`; assert exact two option specs, one object identity, `rush provenance-ai PATH --json`, `rush_provenance_ai`, injected history equality, and no manual wrapper.
  3. Run `.venv/Scripts/python.exe -m pytest tests/test_catalog.py::test_provenance_ai_catalog_declares_trailers_and_since_days tests/test_cli_registry.py::test_provenance_ai_cli_uses_registered_tool tests/test_mcp.py::test_provenance_ai_mcp_matches_cli_and_uses_canonical_name -q`, then `.venv/Scripts/python.exe -m pytest tests/test_catalog.py tests/test_cli_registry.py tests/test_mcp.py -q`; retain missing registration or route failures.
- **Evidence:** Route RED outputs and argument matrix.
- **Stop:** Generic route cannot pass the path/options or core behavior changes are required.
- **Verified outcome:** PR50.4.4 may start.

#### PR50.4.4 — GREEN: register provenance-ai through shared transports

- **Task ID and binary outcome:** PR50.4.4; one ProvenanceAiTool object is exposed through exact catalog, CLI, and MCP contracts.
- **Start goal:** Satisfy integration tests only.
- **Prerequisites:** PR50.4.3 RED.
- **Documentation impact:** None.
- **Dependency impact:** None.
- **Allowed writes:** src/rush/tools/__init__.py; src/rush/catalog.py.
- **Allowed reads:** integration tests; tool module; registrars.
- **Prohibited:** Core/test/CLI/MCP/docs edits or aliases.
- **Actions:**
  1. Reinspect ToolSpec ordering and object identity requirements.
  2. Export/register one object and one ToolSpec with exact typed trailer/since declarations and evidence-bounded descriptions.
  3. Run `.venv/Scripts/python.exe -m pytest tests/test_catalog.py::test_provenance_ai_catalog_declares_trailers_and_since_days tests/test_cli_registry.py::test_provenance_ai_cli_uses_registered_tool tests/test_mcp.py::test_provenance_ai_mcp_matches_cli_and_uses_canonical_name -q`, `.venv/Scripts/python.exe -m pytest tests/test_provenance_ai.py tests/test_catalog.py tests/test_cli_registry.py tests/test_mcp.py -q`, `.venv/Scripts/ruff.exe check src/rush/tools/provenance_ai.py src/rush/tools/__init__.py src/rush/catalog.py tests/test_provenance_ai.py tests/test_catalog.py tests/test_cli_registry.py tests/test_mcp.py`, and `.venv/Scripts/ruff.exe format --check src/rush/tools/provenance_ai.py src/rush/tools/__init__.py src/rush/catalog.py tests/test_provenance_ai.py tests/test_catalog.py tests/test_cli_registry.py tests/test_mcp.py`; reinspect names and identity.
- **Evidence:** RED link, route equality, green outputs.
- **Stop:** Custom transport or second object is required.
- **Verified outcome:** PR50.4.5 may start.

#### PR50.4.5 — DOCS: state attribution evidence limits

- **Task ID and binary outcome:** PR50.4.5; exact trailer, denominator, shallow, and unknown semantics are documented.
- **Start goal:** Prevent causal or authorship claims from entering downstream PR cards.
- **Prerequisites:** PR50.4.4 green.
- **Documentation impact:** Create docs/tools/provenance_ai.md; modify CLI/MCP/CONFIGURATION/TOOL_CATALOG references and examples.
- **Dependency impact:** None.
- **Allowed writes:** docs/tools/provenance_ai.md; docs/CLI_REFERENCE.md; docs/MCP_REFERENCE.md; docs/CONFIGURATION.md; docs/TOOL_CATALOG.md; examples/rush.toml.
- **Allowed reads:** src/rush/tools/provenance_ai.py; tests/test_provenance_ai.py; tests/test_catalog.py; tests/test_cli_registry.py; tests/test_mcp.py; the six allowed documentation/configuration paths.
- **Prohibited:** AI line ratio, survival curve, defect causation, telemetry correlation, complete-history claim when shallow.
- **Actions:**
  1. Inspect the `provenance-ai` command, MCP tool, config table, catalog row, and example anchors in docs/CLI_REFERENCE.md, docs/MCP_REFERENCE.md, docs/CONFIGURATION.md, docs/TOOL_CATALOG.md, and examples/rush.toml; record each pre-edit anchor.
  2. Make this exact change only at those anchors and in docs/tools/provenance_ai.md: document observed commit denominator, exact trailer keys, shallow state, unknown survival/correlation metrics, missing-Git skipped, canonical CLI/MCP names, and read-only behavior.
  3. Run `.venv/Scripts/python.exe -m pytest tests/test_provenance_ai.py tests/test_catalog.py tests/test_cli_registry.py tests/test_mcp.py -q`; then run `rg -n "provenance-ai|rush_provenance_ai|ai_commit_trailers|since_days|unknown|shallow" docs/tools/provenance_ai.md docs/CLI_REFERENCE.md docs/MCP_REFERENCE.md docs/CONFIGURATION.md docs/TOOL_CATALOG.md examples/rush.toml` and record every exact changed anchor.
- **Evidence:** Tests and docs search.
- **Stop:** Wording implies causality or unobserved authorship.
- **Verified outcome:** Only the D50-12-approved I15 disposition is closed; survival/correlation remain deferred or blocked.

### PR50.5 — I16 unsigned provenance draft

#### PR50.5.1 — RED: prove existing unsupported assurance

- **Task ID and binary outcome:** PR50.5.1; both direct-tool tests execute and fail only where the current statement schema, artifact subject, or unsigned-assurance behavior violates the pinned contract.
- **Start goal:** Pin R-013 before changing attestation code.
- **Prerequisites:** PR50.0.1.
- **Documentation impact:** None.
- **Dependency impact:** None.
- **Allowed writes:** Create tests/test_attest.py only.
- **Allowed reads:** attest.py generate_attestation; cli.py attest_cmd; mcp.py Phase 50 block; R-013/Phase 8.
- **Prohibited:** Production/docs/deps; signature/key/Cosign/Git-note tests; commit-as-artifact.
- **Actions:**
  1. Inspect current generator/routes/descriptions and run the existing weak test.
  2. Make this exact change in only tests/test_attest.py: add `test_attest_emits_unsigned_v1_draft_for_real_artifact` using known bytes/injected HEAD; instantiate the production class directly and assert canonical result, Statement/v1, provenance/v1, actual subject name/digest, unsigned_draft metadata, and absence of signature/level/builder/reproducible/completeness/quality-pass claims. Add `test_attest_rejects_missing_artifact_and_unsupported_assurance` for absent/escaping/directory targets and unsupported assurance/signing inputs. Do not add route, export, or dependency assertions; PR50.5.5 owns smoke/route migration.
  3. Run `.venv/Scripts/python.exe -m pytest tests/test_attest.py::test_attest_emits_unsigned_v1_draft_for_real_artifact tests/test_attest.py::test_attest_rejects_missing_artifact_and_unsupported_assurance -q`, then `.venv/Scripts/python.exe -m pytest tests/test_attest.py -q`; retain only direct-tool failures from old v0.1/v0.2 fields, fallback subject, or unsupported assurance.
- **Evidence:** Weak baseline, known digest, named RED failures.
- **Stop:** Tooling failure, commit accepted as artifact, signed/level behavior introduced.
- **Verified outcome:** PR50.5.2 may start.

#### PR50.5.2 — GREEN: migrate attest to a canonical unsigned draft

- **Task ID and binary outcome:** PR50.5.2; the private AttestationTool produces only the pinned unsigned Statement v1 draft for a real artifact; export and public-route behavior remain unchanged.
- **Start goal:** Remove unsupported assurance in the private core while leaving every current public route untouched for PR50.5.5–PR50.5.6.
- **Prerequisites:** PR50.1.2 and PR50.5.1 RED.
- **Documentation impact:** None.
- **Dependency impact:** None in this card; PR50.5.7 owns cryptography evidence/removal.
- **Allowed writes:** src/rush/tools/attest.py only.
- **Allowed reads:** R-013; tests/test_attest.py; tests/test_phase50_slsa_attestation.py; exact current generator callers for behavioral evidence.
- **Prohibited:** Test, registry, CLI, MCP, export, dependency, docs, signing, key, Cosign, Git-note, level/builder/quality/reproducibility/completeness, commit-fallback, release/version changes.
- **Actions:**
  1. Inspect unchanged statement RED assertions and the current generator only. Confirm target API `AttestationTool.run(path, target_artifact)` can be implemented without export or transport branches.
  2. Make this exact change in only src/rush/tools/attest.py: replace the unsupported generator with `AttestationTool` named `attest`; require a contained regular artifact; stream SHA-256; build Statement/v1 with provenance/v1 and only observed subject/source materials; set metadata assurance `unsigned_draft`; reject unsupported assurance/signing inputs; include no export, registry, or transport code.
  3. Run `.venv/Scripts/python.exe -m pytest tests/test_attest.py::test_attest_emits_unsigned_v1_draft_for_real_artifact tests/test_attest.py::test_attest_rejects_missing_artifact_and_unsupported_assurance -q`, `.venv/Scripts/python.exe -m pytest tests/test_attest.py -q`, `.venv/Scripts/ruff.exe check src/rush/tools/attest.py tests/test_attest.py`, and `.venv/Scripts/ruff.exe format --check src/rush/tools/attest.py tests/test_attest.py`. Reinspect the emitted predicate keys and search for `sign`, `level`, `builder`, `reproduc`, `complete`, `quality`, `git note`, and commit-subject fallback.
- **Evidence:** PR50.5.1 RED link, artifact digest/schema assertions, private ToolFn identity, assurance-term search, and one-file production diff.
- **Stop:** Unsupported field, non-artifact subject, escape, export/registry/transport logic, or any test/dependency/public-route change is required.
- **Verified outcome:** PR50.5.3 may start; no artifact write or public migration is authorized.

#### PR50.5.3 — RED: pin permissioned attestation export

- **Task ID and binary outcome:** PR50.5.3; export tests fail because the core produces data but cannot write it.
- **Start goal:** Pin artifact effects separately from statement construction.
- **Prerequisites:** PR50.1.6 and PR50.5.2.
- **Documentation impact:** None.
- **Dependency impact:** None.
- **Allowed writes:** tests/test_attest.py only.
- **Allowed reads:** src/rush/tools/attest.py; src/rush/permissions.py `ExecutionPermissions`; src/rush/tools/common.py `resolve_contained_output` and `atomic_write_bytes`; tests/test_tool_common.py.
- **Prohibited:** Production/routes/docs/dependencies; signing/key behavior.
- **Actions:**
  1. Inspect `ExecutionPermissions.artifact_write`, `resolve_contained_output`, `atomic_write_bytes`, and the PR50.1.5 failure-preservation tests; confirm the core has no export branch.
  2. Add `test_attest_export_requires_artifact_permission` and `test_attest_export_is_contained_atomic_and_preserves_existing_file_on_error`; arrange denied, allowed, escape, symlink, and replace failure; assert skipped/no-write, byte-exact Statement output, error/no outside write, and old-file preservation.
  3. Run `.venv/Scripts/python.exe -m pytest tests/test_attest.py::test_attest_export_requires_artifact_permission tests/test_attest.py::test_attest_export_is_contained_atomic_and_preserves_existing_file_on_error -q`, then `.venv/Scripts/python.exe -m pytest tests/test_attest.py -q`; retain absent-export failures only.
- **Evidence:** Effect RED results, helper paths, output hashes.
- **Stop:** No helper can satisfy containment/atomicity or export encoding is undecided.
- **Verified outcome:** PR50.5.4 may start.

#### PR50.5.4 — GREEN: add guarded unsigned-draft export

- **Task ID and binary outcome:** PR50.5.4; export writes only a contained unsigned draft with artifact permission.
- **Start goal:** Satisfy only PR50.5.3.
- **Prerequisites:** PR50.5.3 RED.
- **Documentation impact:** None.
- **Dependency impact:** None.
- **Allowed writes:** src/rush/tools/attest.py only.
- **Allowed reads:** tests/test_attest.py; tests/test_tool_common.py; src/rush/permissions.py; src/rush/tools/common.py.
- **Prohibited:** Test/route/docs/dependency/signing changes.
- **Actions:**
  1. Reinspect unchanged effect assertions and helper signatures.
  2. Add optional `export_path`/permissions branch: deny without artifact_write; resolve/no-follow contained path; serialize deterministic UTF-8 JSON; temp-write then replace; return artifact metadata; never alter the statement contract.
  3. Run `.venv/Scripts/python.exe -m pytest tests/test_attest.py::test_attest_export_requires_artifact_permission tests/test_attest.py::test_attest_export_is_contained_atomic_and_preserves_existing_file_on_error tests/test_attest.py::test_attest_emits_unsigned_v1_draft_for_real_artifact tests/test_attest.py::test_attest_rejects_missing_artifact_and_unsupported_assurance -q`, `.venv/Scripts/python.exe -m pytest tests/test_attest.py -q`, `.venv/Scripts/ruff.exe check src/rush/tools/attest.py tests/test_attest.py`, and `.venv/Scripts/ruff.exe format --check src/rush/tools/attest.py tests/test_attest.py`; trace every write to its guard.
- **Evidence:** RED link, write trace, hashes, green outputs.
- **Stop:** Statement fields change, implicit output appears, or export can escape.
- **Verified outcome:** PR50.5.5 may start.

#### PR50.5.5 — RED: pin attest catalog, CLI, canonical MCP, and deprecated alias

- **Task ID and binary outcome:** PR50.5.5; integration tests fail because current transports instantiate the old generator and advertise false assurance.
- **Start goal:** Pin one-object route migration and compatibility.
- **Prerequisites:** PR50.1.4, PR50.F4, PR50.5.4.
- **Documentation impact:** None.
- **Dependency impact:** None.
- **Allowed writes:** tests/test_catalog.py; tests/test_cli_registry.py; tests/test_mcp.py; tests/test_phase50_slsa_attestation.py.
- **Allowed reads:** AttestationTool; current CLI/MCP blocks; registrars.
- **Prohibited:** Production/core/docs/dependency edits; alias removal.
- **Actions:**
  1. Inspect exact current command/wrapper source and record false descriptions/signatures.
  2. Add `test_attest_catalog_declares_unsigned_draft_options`, `test_attest_cli_and_canonical_mcp_share_registered_tool`, and `test_attest_generate_alias_is_deprecated_and_uses_registered_tool`; assert one ToolSpec/object, `rush attest PATH --target-artifact FILE [--export-intoto FILE]`, canonical `rush_attest`, deprecated `rush_attest_generate`, permission forwarding, ToolResult equality, deprecation metadata, and absence of old generator construction/business logic.
  3. Run `.venv/Scripts/python.exe -m pytest tests/test_catalog.py::test_attest_catalog_declares_unsigned_draft_options tests/test_cli_registry.py::test_attest_cli_and_canonical_mcp_share_registered_tool tests/test_mcp.py::test_attest_generate_alias_is_deprecated_and_uses_registered_tool -q`, then `.venv/Scripts/python.exe -m pytest tests/test_catalog.py tests/test_cli_registry.py tests/test_mcp.py tests/test_phase50_slsa_attestation.py -q`; retain route, description, or object failures.
- **Evidence:** Route RED outputs and current false-claim inventory.
- **Stop:** Compatibility signature cannot map without ambiguity or core changes are required.
- **Verified outcome:** PR50.5.6 may start.

#### PR50.5.6 — GREEN: migrate attest routes to one ToolFn

- **Task ID and binary outcome:** PR50.5.6; one AttestationTool backs catalog, CLI, canonical MCP, and deprecated alias.
- **Start goal:** Satisfy integration only.
- **Prerequisites:** PR50.5.5 RED.
- **Documentation impact:** None.
- **Dependency impact:** None.
- **Allowed writes:** src/rush/tools/__init__.py; src/rush/catalog.py; src/rush/cli.py; src/rush/mcp.py.
- **Allowed reads:** integration tests; AttestationTool.
- **Prohibited:** Core/test/docs/dependency edits; unrelated route cleanup.
- **Actions:**
  1. Reinspect `_run_tool`, shared MCP lookup, and legacy signature.
  2. Export/register one object; add exact ToolSpec; replace CLI body with options plus one `_run_tool` call; make `rush_attest_generate` normalize its argument, call the same object, return ToolResult, and expose deprecation text. Remove old generator construction and false descriptions.
  3. Run `.venv/Scripts/python.exe -m pytest tests/test_catalog.py::test_attest_catalog_declares_unsigned_draft_options tests/test_cli_registry.py::test_attest_cli_and_canonical_mcp_share_registered_tool tests/test_mcp.py::test_attest_generate_alias_is_deprecated_and_uses_registered_tool -q`, `.venv/Scripts/python.exe -m pytest tests/test_attest.py tests/test_catalog.py tests/test_cli_registry.py tests/test_mcp.py tests/test_phase50_slsa_attestation.py -q`, `.venv/Scripts/ruff.exe check src/rush/tools/attest.py src/rush/tools/__init__.py src/rush/catalog.py src/rush/cli.py src/rush/mcp.py tests/test_attest.py tests/test_catalog.py tests/test_cli_registry.py tests/test_mcp.py tests/test_phase50_slsa_attestation.py`, and `.venv/Scripts/ruff.exe format --check src/rush/tools/attest.py src/rush/tools/__init__.py src/rush/catalog.py src/rush/cli.py src/rush/mcp.py tests/test_attest.py tests/test_catalog.py tests/test_cli_registry.py tests/test_mcp.py tests/test_phase50_slsa_attestation.py`; reinspect source for duplicate implementation.
- **Evidence:** Object identity, route equality, deprecation result, green outputs.
- **Stop:** Alias contains business logic, raw string return remains, or false assurance remains in transport descriptions.
- **Verified outcome:** PR50.5.7 may start.

#### PR50.5.7 — EVIDENCE/DEPENDENCY: disposition cryptography ownership

- **Task ID and binary outcome:** PR50.5.7; cryptography remains with a named owner or is removed with a frozen lock, never by assumption.
- **Start goal:** Isolate dependency mutation from behavior and routes.
- **Prerequisites:** PR50.5.6.
- **Documentation impact:** Record only in implementation evidence.
- **Dependency impact:** Conditional removal of `cryptography==50.0.0` from pyproject.toml and uv.lock.
- **Allowed writes:** pyproject.toml; uv.lock; docs/developer/phase-50-implementation-evidence.md.
- **Allowed reads:** src; tests; scripts; pyproject.toml; uv.lock.
- **Prohibited:** Source/test/doc/version edits; adding/replacing packages.
- **Actions:**
  1. Run `rg -n "(^|[^A-Za-z])cryptography([^A-Za-z]|$)|from cryptography|import cryptography" src tests scripts pyproject.toml`. Record every owner. Stop removal on any owner outside deleted attest behavior.
  2. If no owner remains, remove only the exact direct constraint and run `uv lock`; otherwise change only the evidence file and retain the dependency with owner paths.
  3. Run `uv lock --check`, `.venv/Scripts/python.exe -m pytest tests/test_attest.py tests/test_catalog.py tests/test_cli_registry.py tests/test_mcp.py tests/test_phase50_slsa_attestation.py -q`, `.venv/Scripts/ruff.exe check src tests scripts`, `.venv/Scripts/ruff.exe format --check src tests scripts`, and `rg -n "(^|[^A-Za-z])cryptography([^A-Za-z]|$)|from cryptography|import cryptography" src tests scripts pyproject.toml`. Record manifest/lock diff or retained-owner evidence.
- **Evidence:** Exact search, owner disposition, lock command/exits.
- **Stop:** Ambiguous/transitive owner, unrelated lock change, network-only resolution, or version change.
- **Verified outcome:** PR50.5.8 may start.

#### PR50.5.8 — DOCS: correct exact active provenance claims

- **Task ID and binary outcome:** PR50.5.8; every named active reference describes an unsigned draft and no stronger assurance.
- **Start goal:** Correct public R-013 claims.
- **Prerequisites:** PR50.5.7 complete.
- **Documentation impact:** Create docs/tools/attest.md; correct all named public references.
- **Dependency impact:** Mention cryptography only if actually removed.
- **Allowed writes:** docs/tools/attest.md; README.md; README2.md; README3.md; docs/README.md; docs/ARCHITECTURE.md; docs/CLI_REFERENCE.md; docs/MCP_REFERENCE.md; docs/CONFIGURATION.md; docs/TOOL_CATALOG.md; docs/SECURITY.md; docs/GLOSSARY.md; docs/user-guide/faq.md; docs/user-guide/working-with-ai-agents.md; docs/tutorials/before-a-pull-request.md; examples/rush.toml.
- **Allowed reads:** Green tool/tests, R-013, dependency evidence.
- **Prohibited:** Roadmap/ADR/remediation/changelog/version/release metadata edits; signed/verified/SLSA-level/reproducible/complete/trusted wording.
- **Actions:**
  1. Inspect only the exact active anchors recorded in the documentation claim-correction inventory: README badge/summary/Pillar 9/command/MCP/score rows; equivalent README2/3 anchors; docs/README Phase 50 list; docs/ARCHITECTURE generator entry; CLI/MCP command entries; SECURITY Phase 50 heading/body; GLOSSARY generator term; user-guide FAQ and AI-agent entries; pre-PR tutorial. Stop if an unlisted active file requires correction.
  2. Make this exact change in only the allowed files: replace active signed/Level/verified language with mandatory real artifact, Statement/v1, provenance/v1, `unsigned_draft`, guarded export, `rush_attest`, deprecated `rush_attest_generate`, and explicit non-goals. Remove the false badge/100-percent score rather than relabeling it. Historical roadmaps/ADRs/specs/plans remain untouched.
  3. Run `.venv/Scripts/python.exe -m pytest tests/test_attest.py tests/test_catalog.py tests/test_cli_registry.py tests/test_mcp.py tests/test_phase50_slsa_attestation.py -q`; then run `rg -n "SLSA Level 3|cryptographic build provenance|signed build provenance|verified.*provenance|trusted builder|reproducible" docs/tools/attest.md README.md README2.md README3.md docs/README.md docs/ARCHITECTURE.md docs/CLI_REFERENCE.md docs/MCP_REFERENCE.md docs/CONFIGURATION.md docs/TOOL_CATALOG.md docs/SECURITY.md docs/GLOSSARY.md docs/user-guide/faq.md docs/user-guide/working-with-ai-agents.md docs/tutorials/before-a-pull-request.md examples/rush.toml`. Every remaining hit must be an explicit non-goal sentence in docs/tools/attest.md; record each hit.
- **Evidence:** Green tests and before/after claim inventory.
- **Stop:** False active claim remains or unlisted file is required.
- **Verified outcome:** I16 is closed only as the R-013-corrected unsigned-draft contract; signed/SLSA assurance remains explicitly out of scope.

### PR50.6 — I17 evidence-preserving license matrix — blocked by D50-13

#### PR50.6.1 — RED: expose invented dependency licenses

- **Task ID and binary outcome:** PR50.6.1; the direct-tool extraction test executes and fails only if local metadata evidence is missing, reordered, or replaced by invented license truth.
- **Start goal:** Pin exact manifest/metadata evidence, unknown states, and policy behavior before changing the scanner.
- **Prerequisites:** PR50.0.1 and approved D50-13.
- **Documentation impact:** None.
- **Dependency impact:** None.
- **Allowed writes:** Create tests/test_license_matrix.py only.
- **Allowed reads:** src/rush/tools/license_matrix.py; current CLI/MCP routes; roadmap I17; importlib.metadata patterns; pyproject/package/Cargo manifest parsers already in the repository.
- **Prohibited:** Live registry queries, legal conclusions, inferred linking mechanics, broad SPDX compatibility algebra, production/docs edits.
- **Actions:**
  1. Inspect LicenseMatrixScanner.scan_licenses and its callers. Run the current smoke test and record that every dependency becomes MIT / Apache-2.0 (Dual).
  2. Make this exact change in only tests/test_license_matrix.py: add `test_license_matrix_reports_fixture_metadata_without_inventing_licenses`, arranging pyproject.toml, package.json, and Cargo.toml fixtures plus injected metadata for MIT, GPL-3.0-only, and missing license; instantiate the tool directly and assert normalized dependency/specifier plus exact evidence string/source, with missing evidence unknown. Do not assert policy, CLI, MCP, public-route, or smoke behavior; PR50.6.5 owns route migration.
  3. Run `.venv/Scripts/python.exe -m pytest tests/test_license_matrix.py::test_license_matrix_reports_fixture_metadata_without_inventing_licenses -q`, then `.venv/Scripts/python.exe -m pytest tests/test_license_matrix.py -q`. Retain only direct extraction failures for invented licenses, lost evidence, or wrong canonical shape.
- **Evidence:** Fixture manifests/metadata, named RED failures, legacy baseline.
- **Stop:** A test needs a package registry, legal interpretation, guessed license, or inferred static/dynamic linking.
- **Verified outcome:** PR50.6.2 may start.

#### PR50.6.2 — GREEN: extract deterministic local license evidence

- **Task ID and binary outcome:** PR50.6.2; the private scanner returns deterministic local metadata evidence without policy classification, fallback licenses, network access, or public registration.
- **Start goal:** Remove false permissive classification without pretending to decide license compatibility.
- **Prerequisites:** PR50.1.2 and PR50.6.1 RED.
- **Documentation impact:** None.
- **Dependency impact:** None.
- **Allowed writes:** src/rush/tools/license_matrix.py only.
- **Allowed reads:** Local manifest parsing helpers; importlib.metadata; route registrars; RED evidence.
- **Prohibited:** Test, registry, CLI, MCP, docs, dependency, network, policy-verdict, legal-advice, license-guessing, linking-classification changes.
- **Actions:**
  1. Inspect current parser implementation/callers and exact fixture syntaxes; confirm extraction can be isolated from policy.
  2. Make this exact change in only src/rush/tools/license_matrix.py: implement `LicenseMatrixTool` named `license-matrix`; extract normalized dependency names/specifiers from the three fixture syntaxes using stdlib parsing; obtain evidence only from manifest fields or injected/local metadata; retain exact value/source; return unknown when absent. Include no allowlist verdict, registration, or transports.
  3. Run `.venv/Scripts/python.exe -m pytest tests/test_license_matrix.py::test_license_matrix_reports_fixture_metadata_without_inventing_licenses -q`, `.venv/Scripts/python.exe -m pytest tests/test_license_matrix.py -q`, `.venv/Scripts/ruff.exe check src/rush/tools/license_matrix.py tests/test_license_matrix.py`, and `.venv/Scripts/ruff.exe format --check src/rush/tools/license_matrix.py tests/test_license_matrix.py`. Search the module for constant or fallback license strings and network calls.
- **Evidence:** RED link, exact evidence preservation, private ToolFn identity, no-network inspection.
- **Stop:** A dependency is assigned a license without local evidence, a manual-review item becomes pass/fail legal advice, or public-route behavior enters the private core.
- **Verified outcome:** PR50.6.3 may start; evidence extraction is green and private.

#### PR50.6.3 — RED: pin exact allowlist and manual-review policy

- **Task ID and binary outcome:** PR50.6.3; policy tests fail because evidence is not yet classified under the approved conservative contract.
- **Start goal:** Separate policy state from extraction.
- **Prerequisites:** PR50.6.2.
- **Documentation impact:** None.
- **Dependency impact:** None.
- **Allowed writes:** tests/test_license_matrix.py only.
- **Allowed reads:** green tool; approved D50-13; typed option table.
- **Prohibited:** Production/routes/docs edits; legal/linking assertions.
- **Actions:**
  1. Reinspect extracted evidence records and D50-13. Confirm exact-match allowlist is the only admitted pass rule.
  2. Add `test_license_matrix_exact_allowlist_match_is_allowed` and `test_license_matrix_marks_missing_compound_free_text_and_unrecognized_for_manual_review`; arrange MIT, GPL, `MIT OR Apache-2.0`, classifier text, and missing evidence; assert only exact configured match is allowed, every other state is manual_review/warn, and no legal/viral/compatible verdict appears.
  3. Run `.venv/Scripts/python.exe -m pytest tests/test_license_matrix.py::test_license_matrix_exact_allowlist_match_is_allowed tests/test_license_matrix.py::test_license_matrix_marks_missing_compound_free_text_and_unrecognized_for_manual_review -q`, then `.venv/Scripts/python.exe -m pytest tests/test_license_matrix.py -q`; retain absent-policy failures.
- **Evidence:** Two policy RED results and exact evidence fixtures.
- **Stop:** D50-13 does not approve the conservative policy or a legal matrix is required.
- **Verified outcome:** PR50.6.4 may start.

#### PR50.6.4 — GREEN: apply exact evidence policy without legal inference

- **Task ID and binary outcome:** PR50.6.4; exact allowlist matches are distinguished from manual review with no legal conclusion.
- **Start goal:** Satisfy policy tests only.
- **Prerequisites:** PR50.6.3 RED.
- **Documentation impact:** None.
- **Dependency impact:** None.
- **Allowed writes:** src/rush/tools/license_matrix.py only.
- **Allowed reads:** unchanged policy tests and D50-13.
- **Prohibited:** Test/routes/docs/dependency/linking/legal changes.
- **Actions:**
  1. Reinspect unchanged assertions and extraction record fields.
  2. Add project_license/allowed_licenses semantic handling: exact evidence/allowlist equality may produce allowed; all other values produce manual_review/warn findings; missing project policy never becomes pass/fail.
  3. Run `.venv/Scripts/python.exe -m pytest tests/test_license_matrix.py::test_license_matrix_reports_fixture_metadata_without_inventing_licenses tests/test_license_matrix.py::test_license_matrix_exact_allowlist_match_is_allowed tests/test_license_matrix.py::test_license_matrix_marks_missing_compound_free_text_and_unrecognized_for_manual_review -q`, `.venv/Scripts/python.exe -m pytest tests/test_license_matrix.py -q`, `.venv/Scripts/ruff.exe check src/rush/tools/license_matrix.py tests/test_license_matrix.py`, and `.venv/Scripts/ruff.exe format --check src/rush/tools/license_matrix.py tests/test_license_matrix.py`; search for `viral`, `contamination`, `compatible`, and guessed fallback values.
- **Evidence:** RED link and green policy matrix.
- **Stop:** Any nonexact value is classified allowed or wording becomes legal advice.
- **Verified outcome:** PR50.6.5 may start.

#### PR50.6.5 — RED: pin license-matrix registry and route migration

- **Task ID and binary outcome:** PR50.6.5; integration tests fail on absent catalog registration and current manual/raw transports.
- **Start goal:** Pin one-object public behavior.
- **Prerequisites:** PR50.1.4, PR50.F4, PR50.6.4.
- **Documentation impact:** None.
- **Dependency impact:** None.
- **Allowed writes:** tests/test_catalog.py; tests/test_cli_registry.py; tests/test_mcp.py; tests/test_phase50_slsa_attestation.py.
- **Allowed reads:** green tool; current CLI/MCP; registrars.
- **Prohibited:** Production/core/docs edits.
- **Actions:**
  1. Inspect current manual routes and signatures.
  2. Add `test_license_matrix_catalog_declares_evidence_policy_options`, `test_license_matrix_cli_and_mcp_return_same_tool_result`, and `test_license_matrix_transports_do_not_construct_scanner`; assert exact option specs, one object, generic CLI, canonical `rush_license_matrix` with no duplicate alias, ToolResult equality, and no scanner construction in transports.
  3. Run `.venv/Scripts/python.exe -m pytest tests/test_catalog.py::test_license_matrix_catalog_declares_evidence_policy_options tests/test_cli_registry.py::test_license_matrix_cli_and_mcp_return_same_tool_result tests/test_mcp.py::test_license_matrix_transports_do_not_construct_scanner -q`, then `.venv/Scripts/python.exe -m pytest tests/test_catalog.py tests/test_cli_registry.py tests/test_mcp.py tests/test_phase50_slsa_attestation.py -q`; retain route or raw-object failures.
- **Evidence:** Integration RED results and current route inventory.
- **Stop:** Existing public signature cannot map exactly or core changes are needed.
- **Verified outcome:** PR50.6.6 may start.

#### PR50.6.6 — GREEN: register license-matrix and remove transport business logic

- **Task ID and binary outcome:** PR50.6.6; one LicenseMatrixTool backs all public routes.
- **Start goal:** Satisfy integration only.
- **Prerequisites:** PR50.6.5 RED.
- **Documentation impact:** None.
- **Dependency impact:** None.
- **Allowed writes:** src/rush/tools/__init__.py; src/rush/catalog.py; src/rush/cli.py; src/rush/mcp.py.
- **Allowed reads:** integration tests and green tool.
- **Prohibited:** Core/test/docs/dependency edits; unrelated transports.
- **Actions:**
  1. Reinspect shared registrars and existing public name.
  2. Export/register one object; add exact ToolSpec/options; replace CLI and MCP bodies with thin shared calls, retaining `rush_license_matrix` as the normalized canonical route rather than a duplicate alias.
  3. Run `.venv/Scripts/python.exe -m pytest tests/test_catalog.py::test_license_matrix_catalog_declares_evidence_policy_options tests/test_cli_registry.py::test_license_matrix_cli_and_mcp_return_same_tool_result tests/test_mcp.py::test_license_matrix_transports_do_not_construct_scanner -q`, `.venv/Scripts/python.exe -m pytest tests/test_license_matrix.py tests/test_catalog.py tests/test_cli_registry.py tests/test_mcp.py tests/test_phase50_slsa_attestation.py -q`, `.venv/Scripts/ruff.exe check src/rush/tools/license_matrix.py src/rush/tools/__init__.py src/rush/catalog.py src/rush/cli.py src/rush/mcp.py tests/test_license_matrix.py tests/test_catalog.py tests/test_cli_registry.py tests/test_mcp.py tests/test_phase50_slsa_attestation.py`, and `.venv/Scripts/ruff.exe format --check src/rush/tools/license_matrix.py src/rush/tools/__init__.py src/rush/catalog.py src/rush/cli.py src/rush/mcp.py tests/test_license_matrix.py tests/test_catalog.py tests/test_cli_registry.py tests/test_mcp.py tests/test_phase50_slsa_attestation.py`; reinspect transports for scanner construction.
- **Evidence:** Object identity, route equality, green outputs.
- **Stop:** Duplicate object/business logic or raw dict/string return remains.
- **Verified outcome:** PR50.6.7 may start.

#### PR50.6.7 — DOCS: document evidence sources and nonlegal semantics

- **Task ID and binary outcome:** PR50.6.7; users can distinguish evidence, policy match, and manual review.
- **Start goal:** Remove existing claims of copyleft compliance certainty.
- **Prerequisites:** PR50.6.6 green.
- **Documentation impact:** Create docs/tools/license_matrix.md; correct exact public references.
- **Dependency impact:** None.
- **Allowed writes:** docs/tools/license_matrix.md; README.md; README2.md; README3.md; docs/README.md; docs/CLI_REFERENCE.md; docs/CLI_COOKBOOK.md; docs/MCP_REFERENCE.md; docs/CONFIGURATION.md; docs/TOOL_CATALOG.md; docs/USER_GUIDE.md; docs/VIBECODING.md; docs/user-guide/advanced-checks.md; docs/user-guide/checking-code.md; docs/user-guide/everyday-workflow.md; docs/user-guide/faq.md; docs/workflows/supply_chain_security_and_flagship_release.md; examples/rush.toml.
- **Allowed reads:** src/rush/tools/license_matrix.py; tests/test_license_matrix.py; tests/test_catalog.py; tests/test_cli_registry.py; tests/test_mcp.py; the eighteen allowed documentation/configuration paths.
- **Prohibited:** Legal-safe, contamination, viral, zero-risk, complete detection, or linking-mechanics claims.
- **Actions:**
  1. Inspect these exact active anchors and no others: the Pillar 9 and command-list entries in README.md, README2.md, and README3.md; the Phase 50 list in docs/README.md; the `license-matrix` entries in docs/CLI_REFERENCE.md, docs/CLI_COOKBOOK.md, docs/MCP_REFERENCE.md, docs/CONFIGURATION.md, docs/TOOL_CATALOG.md, docs/USER_GUIDE.md, docs/VIBECODING.md, docs/user-guide/advanced-checks.md, docs/user-guide/checking-code.md, docs/user-guide/everyday-workflow.md, docs/user-guide/faq.md, docs/workflows/supply_chain_security_and_flagship_release.md, and examples/rush.toml. Record the pre-edit claim at each changed anchor.
  2. Make this exact change only at those anchors and in the new guide: document manifest/metadata evidence sources, exact allowlist match, `manual_review`, no-network/no-legal-advice boundaries, canonical CLI/MCP names, typed keys, and missing-evidence behavior. Replace any claim of compatibility, copyleft safety, viral-risk detection, or complete detection; do not alter unrelated prose in the same file.
  3. Run `.venv/Scripts/python.exe -m pytest tests/test_license_matrix.py tests/test_phase50_slsa_attestation.py tests/test_catalog.py tests/test_cli_registry.py tests/test_mcp.py -q`; then run `rg -n "license-matrix|rush_license_matrix|viral|contamination|zero-risk|100% detection|manual_review" docs/tools/license_matrix.md README.md README2.md README3.md docs/README.md docs/CLI_REFERENCE.md docs/CLI_COOKBOOK.md docs/MCP_REFERENCE.md docs/CONFIGURATION.md docs/TOOL_CATALOG.md docs/USER_GUIDE.md docs/VIBECODING.md docs/user-guide/advanced-checks.md docs/user-guide/checking-code.md docs/user-guide/everyday-workflow.md docs/user-guide/faq.md docs/workflows/supply_chain_security_and_flagship_release.md examples/rush.toml`; record each remaining hit and prove that it is the explicit nonlegal limitation rather than an active capability claim.
- **Evidence:** Tests and claim inventory.
- **Stop:** Unsupported legal conclusion remains or a required file is unlisted.
- **Verified outcome:** Only the D50-13-approved evidence/manual-review scope is closed; linking/legal analysis remains explicit.

### PR50.7 — I18 approved IAM action evidence

#### PR50.7.0 — DECISION: freeze provider, call map, resources, and infrastructure scope

- **Task ID and binary outcome:** PR50.7.0; every D50-07 field is approved and recorded, or PR50.7 remains blocked with no test/source edit.
- **Start goal:** Give the coding agent a finite reviewed mapping rather than asking it to invent cloud permissions.
- **Prerequisites:** PR50.0.1 and explicit approval of D50-07.
- **Documentation impact:** Record mapping decision in docs/developer/phase-50-implementation-evidence.md.
- **Dependency impact:** None.
- **Allowed writes:** docs/developer/phase-50-implementation-evidence.md only.
- **Allowed reads:** iam_audit.py; roadmap I18; approved primary provider references; current routes.
- **Prohibited:** Test/production/docs/dependency edits; guessing actions/resources; wildcard/default policy; unsupported provider generation; deployment claims.
- **Actions:**
  1. Inspect the approved record for provider, exact SDK call shapes, exact action strings, resource handling, primary-reference URL/revision, unsupported-call behavior, and infrastructure comparison scope. If any item is absent, record the blocker and do not create RED tests.
  2. Make this exact change in only the evidence file: under `Decision records / PR50.7.0`, record owner/date, one provider, every exact SDK receiver/method/action tuple, literal-resource rule, unknown-resource behavior, primary-reference URL/revision, infrastructure parser/file scope, unsupported-call behavior, and explicit nondeployment language. Missing fields are recorded as blockers, not defaults.
  3. Re-read the record against D50-07 and the typed-key table. Confirm every required field is literal and that it unlocks the whole packet or none.
- **Evidence:** Complete approved finite map and scope record, or explicit blocker.
- **Stop:** Missing mapping field, unreviewed action, wildcard/default resource, or requirement to parse infrastructure not approved.
- **Verified outcome:** PR50.7.1 may start only with complete D50-07 evidence.

#### PR50.7.1 — RED: expose invented IAM defaults and pin approved-map behavior

- **Task ID and binary outcome:** PR50.7.1; direct tool tests fail on current defaults/wildcards or absent approved-map behavior.
- **Start goal:** Pin only extraction/classification from the approved finite map.
- **Prerequisites:** PR50.7.0 complete.
- **Documentation impact:** None.
- **Dependency impact:** None unless D50-07 explicitly approved a parser, which requires a separate plan amendment/task.
- **Allowed writes:** Create tests/test_iam_audit.py only.
- **Allowed reads:** iam_audit.py; approved map evidence; ast; existing smoke test.
- **Prohibited:** Production/routes/docs/dependency edits; unapproved call/action/resource.
- **Actions:**
  1. Inspect current synthesizer and exact approved entries beside fixture ASTs; import tool inside test bodies.
  2. Add `test_iam_audit_maps_only_approved_fixture_calls_without_defaults` and `test_iam_audit_reports_unsupported_calls_resources_and_infrastructure_truthfully`; assert empty input yields empty actions, exact approved calls map exactly, unsupported calls/provider/absent infrastructure warn, resources remain unknown without literal evidence, and no policy/`Resource: *` is synthesized. Do not assert routes.
  3. Run `.venv/Scripts/python.exe -m pytest tests/test_iam_audit.py::test_iam_audit_maps_only_approved_fixture_calls_without_defaults tests/test_iam_audit.py::test_iam_audit_reports_unsupported_calls_resources_and_infrastructure_truthfully -q`, then `.venv/Scripts/python.exe -m pytest tests/test_iam_audit.py -q`; retain default, wildcard, or ad-hoc failures only. PR50.7.3 owns smoke/route migration.
- **Evidence:** Map-backed RED results and current-invention inventory.
- **Stop:** Fixture uses any unapproved entry or infrastructure scope is incomplete.
- **Verified outcome:** PR50.7.2 may start.

#### PR50.7.2 — GREEN: extract only approved actions and report unknowns

- **Task ID and binary outcome:** PR50.7.2; iam-audit emits reviewed required-action evidence and never invents a deployable policy.
- **Start goal:** Replace heuristic method-prefix mapping and defaults with the finite approved contract.
- **Prerequisites:** PR50.1.2 and PR50.7.1 approved RED.
- **Documentation impact:** None.
- **Dependency impact:** None.
- **Allowed writes:** src/rush/tools/iam_audit.py only.
- **Allowed reads:** Approved map evidence; ast patterns; unchanged RED tests.
- **Prohibited:** Test/registry/CLI/MCP/docs/dependency edits; unapproved provider; Resource `*`; default actions; deployment/least-privilege guarantee.
- **Actions:**
  1. Inspect approved map entries beside the exact fixture ASTs. Trace all IamPolicySynthesizer callers and the current manual `rush_iam_audit` route that will become the canonical normalized registration.
  2. Make this exact change in only src/rush/tools/iam_audit.py: replace synthesizer with `IamAuditTool` named `iam-audit`; copy the approved literal mapping exactly; resolve only approved AST receiver/service/method shapes; output observed_calls, required_actions, unsupported_calls, literal_resource_evidence, and infrastructure_state; warn on unsupported/unknown/absent; error malformed input; never emit a deployable policy.
  3. Compare the mapping byte-for-byte to evidence; run `.venv/Scripts/python.exe -m pytest tests/test_iam_audit.py::test_iam_audit_maps_only_approved_fixture_calls_without_defaults tests/test_iam_audit.py::test_iam_audit_reports_unsupported_calls_resources_and_infrastructure_truthfully -q`, `.venv/Scripts/python.exe -m pytest tests/test_iam_audit.py -q`, `.venv/Scripts/ruff.exe check src/rush/tools/iam_audit.py tests/test_iam_audit.py`, and `.venv/Scripts/ruff.exe format --check src/rush/tools/iam_audit.py tests/test_iam_audit.py`; then run `rg -n "Resource|AdministratorAccess|[A-Za-z0-9]+:\\*" src/rush/tools/iam_audit.py` with zero policy/default hits.
- **Evidence:** Map equality, RED link, command outputs, private ToolFn identity.
- **Stop:** Any action/resource is not in approved evidence or result wording implies deployment safety.
- **Verified outcome:** PR50.7.3 may start; the core remains private.

#### PR50.7.3 — RED: pin iam-audit registry and route migration

- **Task ID and binary outcome:** PR50.7.3; integration tests fail on absent registration and current manual policy-synthesizer routes.
- **Start goal:** Pin one-object public evidence behavior.
- **Prerequisites:** PR50.1.4, PR50.F4, PR50.7.2.
- **Documentation impact:** None.
- **Dependency impact:** None.
- **Allowed writes:** tests/test_catalog.py; tests/test_cli_registry.py; tests/test_mcp.py; tests/test_phase50_slsa_attestation.py.
- **Allowed reads:** green tool; current routes; approved keys.
- **Prohibited:** Production/core/docs edits.
- **Actions:**
  1. Inspect current manual routes and exact canonical name.
  2. Add `test_iam_audit_catalog_declares_only_approved_scope`, `test_iam_audit_cli_and_mcp_return_same_tool_result`, and `test_iam_audit_transports_contain_no_policy_synthesis`; assert exact approved option specs, one object, CLI, canonical `rush_iam_audit`, ToolResult equality, and no synthesizer/default/policy wording in transports.
  3. Run `.venv/Scripts/python.exe -m pytest tests/test_catalog.py::test_iam_audit_catalog_declares_only_approved_scope tests/test_cli_registry.py::test_iam_audit_cli_and_mcp_return_same_tool_result tests/test_mcp.py::test_iam_audit_transports_contain_no_policy_synthesis -q`, then `.venv/Scripts/python.exe -m pytest tests/test_catalog.py tests/test_cli_registry.py tests/test_mcp.py tests/test_phase50_slsa_attestation.py -q`; retain integration failures.
- **Evidence:** Route RED outputs and false-description inventory.
- **Stop:** Public arguments exceed D50-07 or core changes are needed.
- **Verified outcome:** PR50.7.4 may start.

#### PR50.7.4 — GREEN: register iam-audit and remove transport synthesis

- **Task ID and binary outcome:** PR50.7.4; one IamAuditTool backs catalog, CLI, and canonical MCP.
- **Start goal:** Satisfy integration only.
- **Prerequisites:** PR50.7.3 RED.
- **Documentation impact:** None.
- **Dependency impact:** None.
- **Allowed writes:** src/rush/tools/__init__.py; src/rush/catalog.py; src/rush/cli.py; src/rush/mcp.py.
- **Allowed reads:** integration tests and green tool.
- **Prohibited:** Core/test/docs edits; policy generation; unrelated routes.
- **Actions:**
  1. Reinspect registrars/current signature.
  2. Export/register one object; add exact ToolSpec/options; replace CLI/MCP bodies with thin shared calls and evidence-only descriptions. Existing `rush_iam_audit` is the normalized canonical name.
  3. Run `.venv/Scripts/python.exe -m pytest tests/test_catalog.py::test_iam_audit_catalog_declares_only_approved_scope tests/test_cli_registry.py::test_iam_audit_cli_and_mcp_return_same_tool_result tests/test_mcp.py::test_iam_audit_transports_contain_no_policy_synthesis -q`, `.venv/Scripts/python.exe -m pytest tests/test_iam_audit.py tests/test_catalog.py tests/test_cli_registry.py tests/test_mcp.py tests/test_phase50_slsa_attestation.py -q`, `.venv/Scripts/ruff.exe check src/rush/tools/iam_audit.py src/rush/tools/__init__.py src/rush/catalog.py src/rush/cli.py src/rush/mcp.py tests/test_iam_audit.py tests/test_catalog.py tests/test_cli_registry.py tests/test_mcp.py tests/test_phase50_slsa_attestation.py`, and `.venv/Scripts/ruff.exe format --check src/rush/tools/iam_audit.py src/rush/tools/__init__.py src/rush/catalog.py src/rush/cli.py src/rush/mcp.py tests/test_iam_audit.py tests/test_catalog.py tests/test_cli_registry.py tests/test_mcp.py tests/test_phase50_slsa_attestation.py`; reinspect transports for synthesizer construction or claims.
- **Evidence:** Object identity, route equality, green outputs.
- **Stop:** Any route emits policy/defaults or duplicates behavior.
- **Verified outcome:** PR50.7.5 may start.

#### PR50.7.5 — DOCS: document IAM evidence and unsupported states

- **Task ID and binary outcome:** PR50.7.5; provider scope, exact map authority, unknown resources, and nondeployment semantics are documented.
- **Start goal:** Remove “synthesized least privilege” claims not supported by the tool.
- **Prerequisites:** PR50.7.4 green.
- **Documentation impact:** Create docs/tools/iam_audit.md; correct public references.
- **Dependency impact:** None.
- **Allowed writes:** docs/tools/iam_audit.md; README.md; README2.md; README3.md; docs/AGENTIC_RUSH.md; docs/ARCHITECTURE.md; docs/developer/architecture.md; docs/CLI_REFERENCE.md; docs/MCP_REFERENCE.md; docs/CONFIGURATION.md; docs/TOOL_CATALOG.md; docs/SECURITY.md; examples/rush.toml.
- **Allowed reads:** src/rush/tools/iam_audit.py; tests/test_iam_audit.py; tests/test_catalog.py; tests/test_cli_registry.py; tests/test_mcp.py; the approved D50-07 record; the thirteen allowed documentation/configuration paths.
- **Prohibited:** Least-privilege/deployable/complete/provider claims beyond approved map.
- **Actions:**
  1. Inspect these exact active anchors and no others: the Pillar 9 and command-list entries in README.md, README2.md, and README3.md; the IAM tool row in docs/AGENTIC_RUSH.md; the Phase 50 tool entry in docs/ARCHITECTURE.md and docs/developer/architecture.md; the `iam-audit` entries in docs/CLI_REFERENCE.md, docs/MCP_REFERENCE.md, docs/CONFIGURATION.md, docs/TOOL_CATALOG.md, docs/SECURITY.md, and examples/rush.toml. Record the pre-edit claim at every changed anchor.
  2. Make this exact change only at those anchors and in the new guide: document the reviewed provider/map revision, observed versus mapped calls, unknown resource/infrastructure states, unsupported warnings, canonical CLI/MCP names, typed config, and mandatory human/cloud review. Replace `synthesize`, `least privilege`, deployable-policy, and wildcard-default claims; do not alter unrelated prose.
  3. Run `.venv/Scripts/python.exe -m pytest tests/test_iam_audit.py tests/test_phase50_slsa_attestation.py tests/test_catalog.py tests/test_cli_registry.py tests/test_mcp.py -q`; then run `rg -n "iam-audit|rush_iam_audit|least-privilege|deployable|Resource.*\\*" docs/tools/iam_audit.md README.md README2.md README3.md docs/AGENTIC_RUSH.md docs/ARCHITECTURE.md docs/developer/architecture.md docs/CLI_REFERENCE.md docs/MCP_REFERENCE.md docs/CONFIGURATION.md docs/TOOL_CATALOG.md docs/SECURITY.md examples/rush.toml`; record every remaining hit and prove it is a limitation or exact map example rather than an active synthesis claim.
- **Evidence:** Tests and claim inventory.
- **Stop:** Documentation exceeds D50-07 evidence.
- **Verified outcome:** Only the exact D50-07-approved evidence scope is closed; policy generation remains absent unless separately approved.

### PR50.8 — I19 static resource audit and optional dynamic probe

#### PR50.8.1 — RED: pin dependency-free static potential-resource findings

- **Task ID and binary outcome:** PR50.8.1; static tests fail because mem-profile is absent while positive/negative AST rules are exact.
- **Start goal:** Pin static evidence without any dynamic or dependency behavior.
- **Prerequisites:** PR50.0.1.
- **Documentation impact:** None.
- **Dependency impact:** None.
- **Allowed writes:** Create tests/test_mem_profile.py only.
- **Allowed reads:** roadmap I19; Python ast patterns; ToolFn/Finding constructors.
- **Prohibited:** Production/dependency edits; executing live project tests; treating static patterns as proof of leaks; collection-time import.
- **Actions:**
  1. Inspect exact AST/result patterns; define only Python open/cursor/connect assigned outside proven with/finally/close and module-level mutable list/dict growth. Confirm module absent and import inside test.
  2. Add `test_mem_profile_flags_potential_unclosed_resources_statically` and `test_mem_profile_static_excludes_proven_with_finally_and_close_paths`; assert rule/path/line, `potential` wording, deterministic order, no source execution, and negative cases. Add no dynamic assertions.
  3. Run `.venv/Scripts/python.exe -m pytest tests/test_mem_profile.py::test_mem_profile_flags_potential_unclosed_resources_statically tests/test_mem_profile.py::test_mem_profile_static_excludes_proven_with_finally_and_close_paths -q`, then `.venv/Scripts/python.exe -m pytest tests/test_mem_profile.py -q`; retain missing static-contract failures only.
- **Evidence:** Static fixture hashes and two RED results.
- **Stop:** Cross-platform metric undefined, dependency unapproved, real tests executed, or AST result called a proven leak.
- **Verified outcome:** Static PR50.8.2 work may start; dynamic work starts only after D50-08.

#### PR50.8.2 — GREEN: implement static potential-resource findings

- **Task ID and binary outcome:** PR50.8.2; mem-profile returns only the pinned deterministic static findings.
- **Start goal:** Implement static behavior only.
- **Prerequisites:** PR50.8.1 RED.
- **Documentation impact:** None.
- **Dependency impact:** None.
- **Allowed writes:** Create src/rush/tools/mem_profile.py only.
- **Allowed reads:** AST patterns and unchanged static tests.
- **Prohibited:** Test/registry/routes/docs/dependency/subprocess/dynamic behavior; definite-leak wording.
- **Actions:**
  1. Reinspect unchanged static assertions and exact AST contexts.
  2. Create `MemProfileTool` named `mem-profile` with static mode only; recognize exactly pinned patterns, exclude proven cleanup paths, emit potential findings, preserve syntax errors, and execute nothing.
  3. Run `.venv/Scripts/python.exe -m pytest tests/test_mem_profile.py::test_mem_profile_flags_potential_unclosed_resources_statically tests/test_mem_profile.py::test_mem_profile_static_excludes_proven_with_finally_and_close_paths -q`, `.venv/Scripts/python.exe -m pytest tests/test_mem_profile.py -q`, `.venv/Scripts/ruff.exe check src/rush/tools/mem_profile.py tests/test_mem_profile.py`, and `.venv/Scripts/ruff.exe format --check src/rush/tools/mem_profile.py tests/test_mem_profile.py`; search for subprocess, psutil, permissions, or registry imports.
- **Evidence:** PR50.8.1 RED link, unchanged static assertions, green commands, and no-execution inspection.
- **Stop:** The finite AST contract broadens, a potential finding becomes a proven-leak claim, or any subprocess, sampler, permission, dependency, registry, or transport behavior enters the static core.
- **Verified outcome:** PR50.8.3 may start; static core is private.

#### PR50.8.3 — DECISION: admit or block dynamic sampling

- **Task ID and binary outcome:** PR50.8.3; D50-08 records exact package constraint, platforms, interval, child policy, and metric, or dynamic work remains blocked with no manifest/test edit.
- **Start goal:** Keep dependency/product choice out of implementation.
- **Prerequisites:** PR50.0.1 and explicit user decision.
- **Documentation impact:** Evidence record only.
- **Dependency impact:** Record exact optional psutil constraint; install nothing.
- **Allowed writes:** docs/developer/phase-50-implementation-evidence.md only.
- **Allowed reads:** pyproject.toml; uv.lock; primary psutil API/platform evidence supplied for decision.
- **Prohibited:** Test/source/manifest edits or partial approval.
- **Actions:**
  1. Inspect decision for exact constraint, supported platforms, sample interval, launched-child/descendant rule, RSS/heap metric, exit/failure preservation, and missing-package behavior.
  2. Record every literal field under `Decision records / PR50.8.3`, or record missing fields and blocked status.
  3. Reconcile record against typed keys and confirm all dynamic cards unlock or none.
- **Evidence:** Complete D50-08 record or blocker.
- **Stop:** Any field/authority missing.
- **Verified outcome:** PR50.8.4 may start only if complete.

#### PR50.8.4 — RED: pin slow permission, optional sampler, and child failure

- **Task ID and binary outcome:** PR50.8.4; dynamic tests fail because static tool has no approved probe.
- **Start goal:** Pin dynamic behavior without running a real suite.
- **Prerequisites:** PR50.8.2 and complete PR50.8.3.
- **Documentation impact:** None.
- **Dependency impact:** None in RED.
- **Allowed writes:** tests/test_mem_profile.py only.
- **Allowed reads:** static tool; run_subprocess; permissions; D50-08.
- **Prohibited:** Production/manifest/docs edits; real child process/suite.
- **Actions:**
  1. Inspect exact runner/permission injection seams.
  2. Add `test_mem_profile_dynamic_denied_without_slow_permission`, `test_mem_profile_dynamic_missing_psutil_is_skipped_without_runner`, `test_mem_profile_dynamic_uses_approved_samples_and_child_policy`, and `test_mem_profile_dynamic_preserves_nonzero_child_failure`; assert no runner when denied/missing, exact argv, the D50-08 metric/interval/child policy, and original nonzero exit evidence.
  3. Run `.venv/Scripts/python.exe -m pytest tests/test_mem_profile.py::test_mem_profile_dynamic_denied_without_slow_permission tests/test_mem_profile.py::test_mem_profile_dynamic_missing_psutil_is_skipped_without_runner tests/test_mem_profile.py::test_mem_profile_dynamic_uses_approved_samples_and_child_policy tests/test_mem_profile.py::test_mem_profile_dynamic_preserves_nonzero_child_failure -q`, then `.venv/Scripts/python.exe -m pytest tests/test_mem_profile.py -q`; retain absent-dynamic failures.
- **Evidence:** Four RED results and injected call trace.
- **Stop:** Real psutil/process required or metric differs from decision.
- **Verified outcome:** PR50.8.5 may start.

#### PR50.8.5 — DEPENDENCY: add only the approved optional sampler runtime

- **Task ID and binary outcome:** PR50.8.5; pyproject.toml and uv.lock contain exactly the D50-08-approved optional psutil constraint and no default/runtime alternative, or dynamic implementation remains blocked.
- **Start goal:** Isolate dependency mutation from sampler behavior.
- **Prerequisites:** Complete PR50.8.3 and intended RED from PR50.8.4.
- **Documentation impact:** Append dependency evidence only.
- **Dependency impact:** Add exactly the approved optional constraint/extra and refresh uv.lock.
- **Allowed writes:** pyproject.toml; uv.lock; docs/developer/phase-50-implementation-evidence.md.
- **Allowed reads:** approved D50-08 record; pyproject.toml; uv.lock; current optional-extra tables.
- **Prohibited:** Source/test/public-doc/version edits; alternate sampler packages; default dependency; unrelated lock update.
- **Actions:**
  1. Compare the exact package name, constraint, extra name, supported platforms, and import name to D50-08 and the current optional-extra syntax. Stop on any mismatch.
  2. Make this exact change in only pyproject.toml, uv.lock, and the evidence file: add the single approved optional constraint/extra, run `uv lock`, and record the exact added/changed lock nodes plus proof that the default dependency set is unchanged.
  3. Run `uv lock --check`; run `git diff -- pyproject.toml uv.lock`; and run `rg -n "psutil|mem-profile|mem_profile" pyproject.toml uv.lock`. Record every changed lock node and stop if any is unrelated to the approved constraint.
- **Evidence:** Complete D50-08 link, manifest/lock diff, frozen constraint/extra, commands/exits under `Dependency and lock evidence / PR50.8.5`.
- **Stop:** Unrelated lock churn, network-only resolution, alternate/default package, or decision mismatch.
- **Verified outcome:** PR50.8.6 may start.

#### PR50.8.6 — GREEN: implement the approved optional dynamic probe

- **Task ID and binary outcome:** PR50.8.6; dynamic mode passes every PR50.8.4 test using only the D50-08-approved optional runtime and preserves the static contract.
- **Start goal:** Satisfy dynamic behavior without changing dependency, tests, routes, or docs.
- **Prerequisites:** PR50.8.4 RED and PR50.8.5 complete.
- **Documentation impact:** Append GREEN evidence only.
- **Dependency impact:** None; consume the exact optional constraint from PR50.8.5.
- **Allowed writes:** src/rush/tools/mem_profile.py; docs/developer/phase-50-implementation-evidence.md.
- **Allowed reads:** tests/test_mem_profile.py; src/rush/tools/common.py; src/rush/permissions.py; approved D50-08 record; pyproject.toml; uv.lock.
- **Prohibited:** Test/registry/transport/public-doc/manifest/lock edits; direct subprocess; alternate package/provider; network; unapproved child or metric semantics.
- **Actions:**
  1. Reinspect the four unchanged PR50.8.4 tests, `ExecutionPermissions.slow`, `run_subprocess`, the exact optional import, and every D50-08 field.
  2. Make this exact change in only src/rush/tools/mem_profile.py: add dynamic mode requiring slow permission; lazily import only the approved psutil API; invoke the exact argv through `run_subprocess`; apply the approved interval, launched-child/descendant policy, and metric; return skipped when the optional runtime is absent; preserve child nonzero exit/output as error evidence; keep static mode byte-for-byte behaviorally compatible.
  3. Run `.venv/Scripts/python.exe -m pytest tests/test_mem_profile.py::test_mem_profile_dynamic_denied_without_slow_permission tests/test_mem_profile.py::test_mem_profile_dynamic_missing_psutil_is_skipped_without_runner tests/test_mem_profile.py::test_mem_profile_dynamic_uses_approved_samples_and_child_policy tests/test_mem_profile.py::test_mem_profile_dynamic_preserves_nonzero_child_failure -q`, `.venv/Scripts/python.exe -m pytest tests/test_mem_profile.py -q`, `uv lock --check`, `.venv/Scripts/ruff.exe check src/rush/tools/mem_profile.py tests/test_mem_profile.py`, and `.venv/Scripts/ruff.exe format --check src/rush/tools/mem_profile.py tests/test_mem_profile.py`; run `rg -n "subprocess\\.|Popen|run\\(" src/rush/tools/mem_profile.py` to reject direct subprocess use.
- **Evidence:** PR50.8.4 RED link, exact runtime import, runner call trace, static regression result, and green commands under `GREEN observations / PR50.8.6`.
- **Stop:** A RED assertion changes, runtime/metric/child behavior differs from D50-08, direct subprocess/network appears, or lock/manifest change is needed.
- **Verified outcome:** PR50.8.7 may start.

#### PR50.8.7 — RED: pin mem-profile registration and public modes

- **Task ID and binary outcome:** PR50.8.7; integration tests fail because admitted mem-profile behavior is not registered.
- **Start goal:** Pin public options/routes without production edits.
- **Prerequisites:** PR50.1.4, PR50.F4, PR50.8.2 and, when dynamic admitted, PR50.8.6.
- **Documentation impact:** None.
- **Dependency impact:** None.
- **Allowed writes:** tests/test_catalog.py; tests/test_cli_registry.py; tests/test_mcp.py.
- **Allowed reads:** tool signature, registrars, typed-key table.
- **Prohibited:** Production/core/CLI/MCP/docs edits; blocked dynamic keys.
- **Actions:**
  1. Inspect tool signature, registrars, and admitted D50-08 state.
  2. Make this exact change in only the three tests: add `test_mem_profile_catalog_exposes_only_admitted_options`, `test_mem_profile_cli_forwards_admitted_mode_and_permission`, and `test_mem_profile_mcp_uses_canonical_name_and_matches_cli`; assert exact admitted option specs, one object, generic CLI, `rush_mem_profile`, permission forwarding, and ToolResult equality; omit dynamic options when blocked.
  3. Run `.venv/Scripts/python.exe -m pytest tests/test_catalog.py::test_mem_profile_catalog_exposes_only_admitted_options tests/test_cli_registry.py::test_mem_profile_cli_forwards_admitted_mode_and_permission tests/test_mcp.py::test_mem_profile_mcp_uses_canonical_name_and_matches_cli -q`, then `.venv/Scripts/python.exe -m pytest tests/test_catalog.py tests/test_cli_registry.py tests/test_mcp.py -q`; retain missing registration or route failures.
- **Evidence:** Route RED results and admitted-key matrix.
- **Stop:** Custom transport needed, decision state ambiguous, or blocked keys would be exposed.
- **Verified outcome:** PR50.8.8 may start.

#### PR50.8.8 — GREEN: register only admitted mem-profile modes

- **Task ID and binary outcome:** PR50.8.8; one MemProfileTool backs catalog, generic CLI, and normalized MCP with only admitted options.
- **Start goal:** Satisfy integration RED only.
- **Prerequisites:** PR50.8.7 RED.
- **Documentation impact:** None.
- **Dependency impact:** None.
- **Allowed writes:** src/rush/tools/__init__.py; src/rush/catalog.py.
- **Allowed reads:** integration tests/tool/decision record.
- **Prohibited:** Core/test/CLI/MCP/docs/dependency edits; blocked dynamic keys.
- **Actions:**
  1. Reinspect unchanged route assertions and exact decision state.
  2. Make this exact change in only the two allowed files: export/register one object and one ToolSpec containing static options plus dynamic options only when D50-08 is complete.
  3. Run `.venv/Scripts/python.exe -m pytest tests/test_catalog.py::test_mem_profile_catalog_exposes_only_admitted_options tests/test_cli_registry.py::test_mem_profile_cli_forwards_admitted_mode_and_permission tests/test_mcp.py::test_mem_profile_mcp_uses_canonical_name_and_matches_cli -q`, `.venv/Scripts/python.exe -m pytest tests/test_mem_profile.py tests/test_catalog.py tests/test_cli_registry.py tests/test_mcp.py -q`, `uv lock --check` when D50-08 admitted the dependency, `.venv/Scripts/ruff.exe check src/rush/tools/mem_profile.py src/rush/tools/__init__.py src/rush/catalog.py tests/test_mem_profile.py tests/test_catalog.py tests/test_cli_registry.py tests/test_mcp.py`, and `.venv/Scripts/ruff.exe format --check src/rush/tools/mem_profile.py src/rush/tools/__init__.py src/rush/catalog.py tests/test_mem_profile.py tests/test_catalog.py tests/test_cli_registry.py tests/test_mcp.py`; inspect object identity, names, and options.
- **Evidence:** RED link, object identity, route equality, green outputs.
- **Stop:** Custom transport/second object required or blocked option appears.
- **Verified outcome:** PR50.8.9 may start.

#### PR50.8.9 — DOCS: distinguish static potential from sampled measurement

- **Task ID and binary outcome:** PR50.8.9; users can see which mode ran, what it proves, and why it may be skipped.
- **Start goal:** Prevent static heuristics and optional samples from becoming production leak claims.
- **Prerequisites:** PR50.8.8 green.
- **Documentation impact:** Create docs/tools/mem_profile.md; update CLI/MCP/CONFIGURATION/TOOL_CATALOG references and examples.
- **Dependency impact:** Document optional extra only if approved/added.
- **Allowed writes:** docs/tools/mem_profile.md; docs/CLI_REFERENCE.md; docs/MCP_REFERENCE.md; docs/CONFIGURATION.md; docs/TOOL_CATALOG.md; examples/rush.toml.
- **Allowed reads:** src/rush/tools/mem_profile.py; tests/test_mem_profile.py; tests/test_catalog.py; tests/test_cli_registry.py; tests/test_mcp.py; approved D50-08 record; pyproject.toml; uv.lock; the six allowed documentation/configuration paths.
- **Prohibited:** 100-percent detection, proven leak, platform guarantee, or dependency claim not implemented.
- **Actions:**
  1. Inspect the `mem-profile` command, MCP tool, config table, catalog row, and example anchors in docs/CLI_REFERENCE.md, docs/MCP_REFERENCE.md, docs/CONFIGURATION.md, docs/TOOL_CATALOG.md, and examples/rush.toml; reconcile them against the admitted D50-08 state and record each pre-edit anchor.
  2. Make this exact change only at those anchors and in docs/tools/mem_profile.md: document static supported patterns and false-positive boundary; if admitted, dynamic permission, exact optional dependency, child policy, metric, and failure preservation; canonical routes and typed config. If D50-08 is blocked, document static mode only and the blocker.
  3. Run `.venv/Scripts/python.exe -m pytest tests/test_mem_profile.py tests/test_catalog.py tests/test_cli_registry.py tests/test_mcp.py -q`; then run `rg -n "mem-profile|rush_mem_profile|potential|allow-slow|psutil|peak_rss_mb" docs/tools/mem_profile.md docs/CLI_REFERENCE.md docs/MCP_REFERENCE.md docs/CONFIGURATION.md docs/TOOL_CATALOG.md examples/rush.toml` and record each exact changed anchor.
- **Evidence:** Tests and docs search.
- **Stop:** Documentation claims dynamic support while D50-08 is open.
- **Verified outcome:** Static scope closes; dynamic scope closes only if D50-08 and its RED/GREEN evidence are complete. I19 is never called fully closed while dynamic remains blocked.

### PR50.9 — I20 Python cold-start evidence — blocked by D50-14

#### PR50.9.1 — RED: pin deterministic Python import inventory without execution

- **Task ID and binary outcome:** PR50.9.1; static inventory tests fail because cold-start is absent.
- **Start goal:** Scope this phase to Python; do not promise Node instrumentation or automatic lazy-import patches.
- **Prerequisites:** PR50.0.1 and approved D50-14.
- **Documentation impact:** None.
- **Dependency impact:** None.
- **Allowed writes:** Create tests/test_cold_start.py.
- **Allowed reads:** roadmap I20; run_subprocess; permissions; Python -X importtime output patterns.
- **Prohibited:** Executing fixture during static mode; Node support; auto patches; direct subprocess; performance claims.
- **Actions:**
  1. Inspect run_subprocess and permission-gated tools. Confirm cold-start is absent.
  2. Make this exact change in only the test file: add `test_cold_start_static_import_inventory_is_deterministic` with a Python entry containing top-level and function-local imports plus an execution sentinel; instantiate the tool directly and assert ordered module/path/line/scope inventory and zero runner/sentinel calls. Add no timing assertions.
  3. Run `.venv/Scripts/python.exe -m pytest tests/test_cold_start.py::test_cold_start_static_import_inventory_is_deterministic -q`, then `.venv/Scripts/python.exe -m pytest tests/test_cold_start.py -q`; retain missing-contract failures.
- **Evidence:** Fixture source, expected argv/timing rows, named RED.
- **Stop:** Node behavior required, source executes in static mode, interpreter differs from project Python, or subprocess error is hidden.
- **Verified outcome:** PR50.9.2 may start.

#### PR50.9.2 — GREEN: implement Python import inventory without execution

- **Task ID and binary outcome:** PR50.9.2; cold-start statically inventories Python imports without executing source.
- **Start goal:** Implement only the tested evidence; recommendations remain findings, not patches.
- **Prerequisites:** PR50.1.2 and PR50.9.1 RED.
- **Documentation impact:** None.
- **Dependency impact:** None.
- **Allowed writes:** Create src/rush/tools/cold_start.py only.
- **Allowed reads:** run_subprocess; permissions; CLI extra_kwargs patterns.
- **Prohibited:** Test/registry/CLI/MCP/docs/dependency edits; Node, subprocess, source edits, execution, timing behavior.
- **Actions:**
  1. Inspect interpreter discovery and run_subprocess signature; confirm exact CLI flags --entry, --execute, --threshold-ms can call _run_tool.
  2. Make this exact change in only src/rush/tools/cold_start.py: create `ColdStartTool` named `cold-start`; parse a contained regular `.py` entry with ast into deterministic top-level/local import records; preserve syntax/path errors; execute nothing and expose no timing branch.
  3. Run `.venv/Scripts/python.exe -m pytest tests/test_cold_start.py::test_cold_start_static_import_inventory_is_deterministic -q`, `.venv/Scripts/python.exe -m pytest tests/test_cold_start.py -q`, `.venv/Scripts/ruff.exe check src/rush/tools/cold_start.py tests/test_cold_start.py`, and `.venv/Scripts/ruff.exe format --check src/rush/tools/cold_start.py tests/test_cold_start.py`; search the module for subprocess, importlib execution, registry, or transport imports.
- **Evidence:** RED link, argv assertions, commands.
- **Stop:** Entry escape, implicit execution, unsupported output silently parsed, or patch suggestion presented as applied.
- **Verified outcome:** PR50.9.3 may start; static core remains private.

#### PR50.9.3 — RED: pin explicit slow `-X importtime` execution

- **Task ID and binary outcome:** PR50.9.3; timing tests fail because static tool has no slow branch.
- **Start goal:** Pin permission, argv, parsing, threshold, and error preservation separately.
- **Prerequisites:** PR50.9.2.
- **Documentation impact:** None.
- **Dependency impact:** None.
- **Allowed writes:** tests/test_cold_start.py only.
- **Allowed reads:** static tool; run_subprocess; permissions; interpreter discovery.
- **Prohibited:** Production/routes/docs edits; real fixture execution.
- **Actions:**
  1. Inspect exact injected runner/interpreter seams.
  2. Add `test_cold_start_execution_denied_without_slow_permission`, `test_cold_start_execution_uses_project_python_importtime_argv`, `test_cold_start_execution_parses_observed_rows_and_threshold`, and `test_cold_start_execution_preserves_nonzero_and_syntax_errors`; assert no call when denied, exact `[project-python, -X, importtime, entry]` argv, injected stderr rows/threshold findings, contained `.py` only, and no fabricated timing.
  3. Run `.venv/Scripts/python.exe -m pytest tests/test_cold_start.py::test_cold_start_execution_denied_without_slow_permission tests/test_cold_start.py::test_cold_start_execution_uses_project_python_importtime_argv tests/test_cold_start.py::test_cold_start_execution_parses_observed_rows_and_threshold tests/test_cold_start.py::test_cold_start_execution_preserves_nonzero_and_syntax_errors -q`, then `.venv/Scripts/python.exe -m pytest tests/test_cold_start.py -q`; retain absent-timing failures.
- **Evidence:** Dynamic RED results and exact argv.
- **Stop:** Project interpreter cannot be selected deterministically or output grammar is undecided.
- **Verified outcome:** PR50.9.4 may start.

#### PR50.9.4 — GREEN: add permission-gated Python import timing

- **Task ID and binary outcome:** PR50.9.4; explicit slow mode parses observed importtime rows and preserves failures.
- **Start goal:** Satisfy timing tests only.
- **Prerequisites:** PR50.9.3 RED.
- **Documentation impact:** None.
- **Dependency impact:** None.
- **Allowed writes:** src/rush/tools/cold_start.py only.
- **Allowed reads:** unchanged timing tests; runner/permissions/interpreter helpers.
- **Prohibited:** Test/registry/routes/docs edits; Node; shell string; patch generation.
- **Actions:**
  1. Reinspect assertions and helper signatures.
  2. Add execution branch requiring slow, contained `.py`, exact argv via run_subprocess, bounded parsing of self/cumulative microseconds/module, observed threshold findings, and preserved errors.
  3. Run `.venv/Scripts/python.exe -m pytest tests/test_cold_start.py -q`, `.venv/Scripts/ruff.exe check src/rush/tools/cold_start.py tests/test_cold_start.py`, and `.venv/Scripts/ruff.exe format --check src/rush/tools/cold_start.py tests/test_cold_start.py`; inspect the asserted argv and run `rg -n "subprocess\\.|Popen|run\\(" src/rush/tools/cold_start.py` to reject direct subprocess use.
- **Evidence:** RED link, call trace, green outputs.
- **Stop:** Implicit execution, unsupported output accepted, or error hidden.
- **Verified outcome:** PR50.9.5 may start.

#### PR50.9.5 — RED: pin cold-start registration, CLI flags, and MCP equality

- **Task ID and binary outcome:** PR50.9.5; integration tests fail because the green tool has no public contract.
- **Start goal:** Pin exact public arguments only.
- **Prerequisites:** PR50.1.4, PR50.F4, PR50.9.4.
- **Documentation impact:** None.
- **Dependency impact:** None.
- **Allowed writes:** tests/test_catalog.py; tests/test_cli_registry.py; tests/test_mcp.py.
- **Allowed reads:** tool signature; registrars; `_run_tool`.
- **Prohibited:** Production/core/docs edits.
- **Actions:**
  1. Inspect generic CLI and confirm custom flags are required.
  2. Add `test_cold_start_catalog_declares_python_scope_options`, `test_cold_start_cli_forwards_entry_execution_and_threshold`, and `test_cold_start_mcp_uses_canonical_name_and_matches_cli`; assert exact option specs, one object, `rush cold-start PATH --entry FILE [--execute --threshold-ms N]`, `rush_cold_start`, permission/argument forwarding, and ToolResult equality.
  3. Run `.venv/Scripts/python.exe -m pytest tests/test_catalog.py::test_cold_start_catalog_declares_python_scope_options tests/test_cli_registry.py::test_cold_start_cli_forwards_entry_execution_and_threshold tests/test_mcp.py::test_cold_start_mcp_uses_canonical_name_and_matches_cli -q`, then `.venv/Scripts/python.exe -m pytest tests/test_catalog.py tests/test_cli_registry.py tests/test_mcp.py -q`; retain integration failures.
- **Evidence:** Route RED results and argument matrix.
- **Stop:** Arguments cannot map one-to-one to the tool.
- **Verified outcome:** PR50.9.6 may start.

#### PR50.9.6 — GREEN: register cold-start with a thin CLI adapter

- **Task ID and binary outcome:** PR50.9.6; one ColdStartTool backs catalog, CLI, and MCP.
- **Start goal:** Satisfy integration only.
- **Prerequisites:** PR50.9.5 RED.
- **Documentation impact:** None.
- **Dependency impact:** None.
- **Allowed writes:** src/rush/tools/__init__.py; src/rush/catalog.py; src/rush/cli.py.
- **Allowed reads:** integration tests and tool.
- **Prohibited:** Core/test/MCP/docs edits.
- **Actions:**
  1. Reinspect `_run_tool` and Click conventions.
  2. Export/register one object; add exact ToolSpec/options; add only flags/normalization plus one `_run_tool` call. Shared MCP needs no edit.
  3. Run `.venv/Scripts/python.exe -m pytest tests/test_catalog.py::test_cold_start_catalog_declares_python_scope_options tests/test_cli_registry.py::test_cold_start_cli_forwards_entry_execution_and_threshold tests/test_mcp.py::test_cold_start_mcp_uses_canonical_name_and_matches_cli -q`, `.venv/Scripts/python.exe -m pytest tests/test_cold_start.py tests/test_catalog.py tests/test_cli_registry.py tests/test_mcp.py -q`, `.venv/Scripts/ruff.exe check src/rush/tools/cold_start.py src/rush/tools/__init__.py src/rush/catalog.py src/rush/cli.py tests/test_cold_start.py tests/test_catalog.py tests/test_cli_registry.py tests/test_mcp.py`, and `.venv/Scripts/ruff.exe format --check src/rush/tools/cold_start.py src/rush/tools/__init__.py src/rush/catalog.py src/rush/cli.py tests/test_cold_start.py tests/test_catalog.py tests/test_cli_registry.py tests/test_mcp.py`; inspect CLI for timing or parser logic.
- **Evidence:** Object identity, route equality, green outputs.
- **Stop:** CLI contains business logic or second object.
- **Verified outcome:** PR50.9.7 may start.

#### PR50.9.7 — DOCS: document Python-only static/slow modes

- **Task ID and binary outcome:** PR50.9.7; Python scope, importtime measurement, permission, errors, and non-goals are exact.
- **Start goal:** Remove roadmap performance and Node implications from the implemented contract.
- **Prerequisites:** PR50.9.6 green.
- **Documentation impact:** Create docs/tools/cold_start.md; update CLI/MCP/CONFIGURATION/TOOL_CATALOG references and examples.
- **Dependency impact:** None.
- **Allowed writes:** docs/tools/cold_start.md; docs/CLI_REFERENCE.md; docs/MCP_REFERENCE.md; docs/CONFIGURATION.md; docs/TOOL_CATALOG.md; examples/rush.toml.
- **Allowed reads:** src/rush/tools/cold_start.py; tests/test_cold_start.py; tests/test_catalog.py; tests/test_cli_registry.py; tests/test_mcp.py; the six allowed documentation/configuration paths.
- **Prohibited:** Node, sandbox guarantee, percent improvement, automatic patch, universal timing accuracy.
- **Actions:**
  1. Inspect the `cold-start` command, MCP tool, config table, catalog row, and example anchors in docs/CLI_REFERENCE.md, docs/MCP_REFERENCE.md, docs/CONFIGURATION.md, docs/TOOL_CATALOG.md, and examples/rush.toml; record each pre-edit anchor.
  2. Make this exact change only at those anchors and in docs/tools/cold_start.md: document static Python AST mode; explicit slow `-X importtime` mode; child-code execution warning; threshold and error preservation; canonical routes; Python-only and no-patch exclusions.
  3. Run `.venv/Scripts/python.exe -m pytest tests/test_cold_start.py tests/test_catalog.py tests/test_cli_registry.py tests/test_mcp.py -q`; then run `rg -n "cold-start|rush_cold_start|importtime|allow-slow|Python-only|Node" docs/tools/cold_start.md docs/CLI_REFERENCE.md docs/MCP_REFERENCE.md docs/CONFIGURATION.md docs/TOOL_CATALOG.md examples/rush.toml` and record each exact changed anchor.
- **Evidence:** Tests and docs search.
- **Stop:** Docs imply isolation/performance not tested.
- **Verified outcome:** Only the D50-14-approved Python behavior is closed; Node/patch work remains explicit.

### PR50.10 — I21 read-only media audit and guarded raster/SVG output — blocked by D50-15

#### PR50.10.1 — RED: pin byte-identical SVG, CLS, and raster audit

- **Task ID and binary outcome:** PR50.10.1; the direct audit test executes and fails only because exact media metadata/CLS evidence and no-write behavior are absent.
- **Start goal:** Separate evidence-only audit from explicit asset output; do not auto-edit markup.
- **Prerequisites:** PR50.0.1 and approved D50-15.
- **Documentation impact:** None.
- **Dependency impact:** Existing pillow==12.3.0 only.
- **Allowed writes:** Create tests/test_media_opt.py.
- **Allowed reads:** roadmap I21; Pillow manifest/lock; XML/HTML helper patterns; permissions/containment.
- **Prohibited:** Markup rewrites, AVIF unless current Pillow build proves support, lossy “zero-loss” claims, production/docs edits.
- **Actions:**
  1. Inspect Pillow constraint and write-gated tools. Confirm media-opt is absent.
  2. Make this exact change in only the test file: add `test_media_opt_audit_reports_svg_cls_and_raster_evidence_without_writes` with malicious/safe SVG, literal HTML/JSX img tags with/without dimensions, and PNG; instantiate the tool directly; assert exact findings, raster metadata, unsupported syntax warnings, and byte-identical tree. Add no sanitize/optimize assertions.
  3. Run `.venv/Scripts/python.exe -m pytest tests/test_media_opt.py::test_media_opt_audit_reports_svg_cls_and_raster_evidence_without_writes -q`, then `.venv/Scripts/python.exe -m pytest tests/test_media_opt.py -q`; retain absent-contract failures.
- **Evidence:** Fixture hashes/sizes, named RED.
- **Stop:** Test expects markup mutation, lossy equivalence, unproved AVIF, or implicit source overwrite.
- **Verified outcome:** PR50.10.2 may start.

#### PR50.10.2 — GREEN: implement deterministic read-only media audit

- **Task ID and binary outcome:** PR50.10.2; the private MediaOptTool performs the pinned read-only audit and exposes no sanitizer, optimizer, write, registry, or transport behavior.
- **Start goal:** Satisfy tested SVG/CLS/raster behavior with current Pillow and stdlib XML.
- **Prerequisites:** PR50.1.2 and PR50.10.1 RED.
- **Documentation impact:** None.
- **Dependency impact:** Preserve pillow==12.3.0; add nothing.
- **Allowed writes:** Create src/rush/tools/media_opt.py only.
- **Allowed reads:** Pillow APIs already imported by Rush; Python `xml.etree.ElementTree`; src/rush/tools/common.py; src/rush/permissions.py; src/rush/cli.py `_run_tool`.
- **Prohibited:** Test/registry/route/docs/dependency/write edits; markup mutation; source deletion; telemetry.
- **Actions:**
  1. Inspect exact Pillow save formats available in the project interpreter and existing containment helpers. Record supported format set in test evidence; do not broaden it.
  2. Make this exact change in only src/rush/tools/media_opt.py: create `MediaOptTool` named `media-opt`; implement audit-only SVG active-content/external-reference checks, literal HTML/JSX img dimension checks, and Pillow raster metadata inspection; emit warnings for unsupported syntax; write nothing.
  3. Run `.venv/Scripts/python.exe -m pytest tests/test_media_opt.py::test_media_opt_audit_reports_svg_cls_and_raster_evidence_without_writes -q`, `.venv/Scripts/python.exe -m pytest tests/test_media_opt.py -q`, `.venv/Scripts/ruff.exe check src/rush/tools/media_opt.py tests/test_media_opt.py`, and `.venv/Scripts/ruff.exe format --check src/rush/tools/media_opt.py tests/test_media_opt.py`; search for write, delete, replace, registry, or transport code.
- **Evidence:** RED link, format capability record, before/after hashes, commands.
- **Stop:** Unsupported format, source overwrite without exact flag, larger replacement, or sanitizer retains active content.
- **Verified outcome:** PR50.10.3 may start; audit core remains private.

#### PR50.10.3 — RED: pin explicit SVG sanitization output

- **Task ID and binary outcome:** PR50.10.3; sanitizer tests fail because audit has no artifact branch.
- **Start goal:** Pin active-content removal separately from raster optimization.
- **Prerequisites:** PR50.1.6 and PR50.10.2.
- **Documentation impact:** None.
- **Dependency impact:** None.
- **Allowed writes:** tests/test_media_opt.py only.
- **Allowed reads:** src/rush/tools/media_opt.py; src/rush/permissions.py; src/rush/tools/common.py; tests/test_tool_common.py; Python `xml.etree.ElementTree` behavior exercised by tests/test_media_opt.py.
- **Prohibited:** Production/routes/docs edits; raster/markup behavior.
- **Actions:**
  1. Inspect the exact active-content rules, `ExecutionPermissions.artifact_write`, `resolve_contained_output`, `atomic_write_bytes`, and the PR50.1.5 failure-preservation tests.
  2. Add `test_media_opt_sanitize_requires_permission_and_explicit_output`, `test_media_opt_sanitize_removes_active_content_and_preserves_safe_nodes`, and `test_media_opt_sanitize_rejects_escape_and_preserves_source_and_old_output`; assert denied/no-write, explicit contained output, script/event/foreignObject/external-reference removal, safe-node retention, escape/symlink rejection, source preservation, and replace-failure preservation.
  3. Run `.venv/Scripts/python.exe -m pytest tests/test_media_opt.py::test_media_opt_sanitize_requires_permission_and_explicit_output tests/test_media_opt.py::test_media_opt_sanitize_removes_active_content_and_preserves_safe_nodes tests/test_media_opt.py::test_media_opt_sanitize_rejects_escape_and_preserves_source_and_old_output -q`, then `.venv/Scripts/python.exe -m pytest tests/test_media_opt.py -q`; retain absent-sanitizer failures.
- **Evidence:** Sanitizer RED results and fixture hashes.
- **Stop:** Allowlist/schema is incomplete or ElementTree cannot enforce the approved rules.
- **Verified outcome:** PR50.10.4 may start.

#### PR50.10.4 — GREEN: add permissioned contained SVG sanitization

- **Task ID and binary outcome:** PR50.10.4; sanitizer creates only an explicit safe contained output.
- **Start goal:** Satisfy sanitizer tests only.
- **Prerequisites:** PR50.10.3 RED.
- **Documentation impact:** None.
- **Dependency impact:** None.
- **Allowed writes:** src/rush/tools/media_opt.py only.
- **Allowed reads:** unchanged sanitizer tests/helpers.
- **Prohibited:** Test/route/docs/raster/markup/dependency changes.
- **Actions:**
  1. Reinspect assertions and exact allowlist.
  2. Add sanitize operation requiring artifact_write/output; remove only pinned active nodes/attributes/references; temp-write then replace contained output; preserve source/old output on error.
  3. Run `.venv/Scripts/python.exe -m pytest tests/test_media_opt.py -q`, `.venv/Scripts/ruff.exe check src/rush/tools/media_opt.py tests/test_media_opt.py`, and `.venv/Scripts/ruff.exe format --check src/rush/tools/media_opt.py tests/test_media_opt.py`; trace every write and rescan sanitized bytes with the audit branch.
- **Evidence:** RED link, post-sanitize audit, hashes, green outputs.
- **Stop:** Active content remains or source/old output can be lost.
- **Verified outcome:** PR50.10.5 may start.

#### PR50.10.5 — RED: pin measured PNG/WebP candidate output

- **Task ID and binary outcome:** PR50.10.5; raster tests fail because no optimization branch exists.
- **Start goal:** Pin format capability, deterministic save, and no-larger replacement independently.
- **Prerequisites:** PR50.1.6 and PR50.10.4.
- **Documentation impact:** None.
- **Dependency impact:** Preserve Pillow only.
- **Allowed writes:** tests/test_media_opt.py; docs/developer/phase-50-implementation-evidence.md only for locked-interpreter capability output.
- **Allowed reads:** locked Pillow APIs/version from pyproject.toml and uv.lock; src/rush/tools/media_opt.py; src/rush/permissions.py; src/rush/tools/common.py; tests/test_tool_common.py.
- **Prohibited:** Production/manifest/routes/docs edits; AVIF unless capability decision amended; source overwrite.
- **Actions:**
  1. Run the project interpreter capability probe named in evidence and record exact supported formats; no external files or network.
  2. Add `test_media_opt_optimize_requires_permission_and_explicit_output`, `test_media_opt_optimize_writes_only_smaller_deterministic_png_or_webp`, and `test_media_opt_optimize_preserves_files_on_no_improvement_escape_or_error`; assert denied/no-write, deterministic explicit output, smaller-candidate replacement, equal/larger `no_improvement` with unchanged files, escape/symlink rejection, and Pillow-error preservation.
  3. Run `.venv/Scripts/python.exe -m pytest tests/test_media_opt.py::test_media_opt_optimize_requires_permission_and_explicit_output tests/test_media_opt.py::test_media_opt_optimize_writes_only_smaller_deterministic_png_or_webp tests/test_media_opt.py::test_media_opt_optimize_preserves_files_on_no_improvement_escape_or_error -q`, then `.venv/Scripts/python.exe -m pytest tests/test_media_opt.py -q`; retain absent-optimizer failures.
- **Evidence:** Capability record, sizes/hashes, raster RED results.
- **Stop:** Locked Pillow capability differs from D50-15 or deterministic parameters are undecided.
- **Verified outcome:** PR50.10.6 may start.

#### PR50.10.6 — GREEN: add measured explicit raster output

- **Task ID and binary outcome:** PR50.10.6; permitted optimization writes only a smaller deterministic candidate to an explicit output.
- **Start goal:** Satisfy raster tests only.
- **Prerequisites:** PR50.10.5 RED.
- **Documentation impact:** None.
- **Dependency impact:** None.
- **Allowed writes:** src/rush/tools/media_opt.py only.
- **Allowed reads:** raster tests/capability evidence/Pillow/helpers.
- **Prohibited:** Test/routes/docs/manifest/AVIF/markup/source-overwrite changes.
- **Actions:**
  1. Reinspect supported formats and unchanged assertions.
  2. Add optimize operation requiring artifact_write/output; use exact PNG/WebP deterministic parameters; compare candidate bytes before atomic output replacement; return no_improvement without changing files when not smaller.
  3. Run `.venv/Scripts/python.exe -m pytest tests/test_media_opt.py -q`, `.venv/Scripts/ruff.exe check src/rush/tools/media_opt.py tests/test_media_opt.py`, and `.venv/Scripts/ruff.exe format --check src/rush/tools/media_opt.py tests/test_media_opt.py`; compare hashes and trace writes.
- **Evidence:** RED link, sizes/hashes, green outputs.
- **Stop:** Larger/equal output replaces, source changes, or unsupported format is accepted.
- **Verified outcome:** PR50.10.7 may start.

#### PR50.10.7 — RED: pin media-opt registration and public operations

- **Task ID and binary outcome:** PR50.10.7; integration tests fail because the complete core is not public.
- **Start goal:** Pin exact options/routes and permission forwarding.
- **Prerequisites:** PR50.1.4, PR50.F4, PR50.10.6.
- **Documentation impact:** None.
- **Dependency impact:** None.
- **Allowed writes:** tests/test_catalog.py; tests/test_cli_registry.py; tests/test_mcp.py.
- **Allowed reads:** tool signature; registrars; typed keys.
- **Prohibited:** Production/core/docs edits.
- **Actions:**
  1. Inspect generic CLI and determine exact custom flags.
  2. Add `test_media_opt_catalog_declares_exact_operation_options`, `test_media_opt_cli_forwards_audit_sanitize_and_optimize_arguments`, and `test_media_opt_mcp_uses_canonical_name_and_matches_cli`; assert exact four option specs, one object, audit/sanitize/optimize CLI arguments, `rush_media_opt`, permission forwarding, and ToolResult equality.
  3. Run `.venv/Scripts/python.exe -m pytest tests/test_catalog.py::test_media_opt_catalog_declares_exact_operation_options tests/test_cli_registry.py::test_media_opt_cli_forwards_audit_sanitize_and_optimize_arguments tests/test_mcp.py::test_media_opt_mcp_uses_canonical_name_and_matches_cli -q`, then `.venv/Scripts/python.exe -m pytest tests/test_catalog.py tests/test_cli_registry.py tests/test_mcp.py -q`; retain integration failures.
- **Evidence:** Route RED results and argument matrix.
- **Stop:** A public argument is undefined or core redesign required.
- **Verified outcome:** PR50.10.8 may start.

#### PR50.10.8 — GREEN: register media-opt with thin CLI routing

- **Task ID and binary outcome:** PR50.10.8; one MediaOptTool backs catalog, CLI, and MCP.
- **Start goal:** Satisfy integration only.
- **Prerequisites:** PR50.10.7 RED.
- **Documentation impact:** None.
- **Dependency impact:** None.
- **Allowed writes:** src/rush/tools/__init__.py; src/rush/catalog.py; src/rush/cli.py.
- **Allowed reads:** integration tests/tool.
- **Prohibited:** Core/test/MCP/docs/dependency edits.
- **Actions:**
  1. Reinspect `_run_tool`/Click conventions.
  2. Export/register one object; add exact ToolSpec/options; add flags/normalization plus one `_run_tool` call. No MCP edit.
  3. Run `.venv/Scripts/python.exe -m pytest tests/test_catalog.py::test_media_opt_catalog_declares_exact_operation_options tests/test_cli_registry.py::test_media_opt_cli_forwards_audit_sanitize_and_optimize_arguments tests/test_mcp.py::test_media_opt_mcp_uses_canonical_name_and_matches_cli -q`, `.venv/Scripts/python.exe -m pytest tests/test_media_opt.py tests/test_catalog.py tests/test_cli_registry.py tests/test_mcp.py -q`, `uv lock --check`, `.venv/Scripts/ruff.exe check src/rush/tools/media_opt.py src/rush/tools/__init__.py src/rush/catalog.py src/rush/cli.py tests/test_media_opt.py tests/test_catalog.py tests/test_cli_registry.py tests/test_mcp.py`, and `.venv/Scripts/ruff.exe format --check src/rush/tools/media_opt.py src/rush/tools/__init__.py src/rush/catalog.py src/rush/cli.py tests/test_media_opt.py tests/test_catalog.py tests/test_cli_registry.py tests/test_mcp.py`; inspect CLI for image or XML logic.
- **Evidence:** Object identity, route equality, green outputs.
- **Stop:** Business logic enters CLI or second object appears.
- **Verified outcome:** PR50.10.9 may start.

#### PR50.10.9 — DOCS: document audit, guarded outputs, and non-goals

- **Task ID and binary outcome:** PR50.10.9; supported formats, SVG rules, CLS evidence, permissions, and no-markup-write boundary are documented.
- **Start goal:** Prevent “zero-loss,” automatic fixes, and percentage savings claims.
- **Prerequisites:** PR50.10.8 green.
- **Documentation impact:** Create docs/tools/media_opt.md; update CLI/MCP/CONFIGURATION/TOOL_CATALOG/SECURITY references and examples.
- **Dependency impact:** Document existing Pillow version only.
- **Allowed writes:** docs/tools/media_opt.md; docs/CLI_REFERENCE.md; docs/MCP_REFERENCE.md; docs/CONFIGURATION.md; docs/TOOL_CATALOG.md; docs/SECURITY.md; examples/rush.toml.
- **Allowed reads:** src/rush/tools/media_opt.py; tests/test_media_opt.py; tests/test_catalog.py; tests/test_cli_registry.py; tests/test_mcp.py; locked-interpreter format evidence; the seven allowed documentation/configuration paths.
- **Prohibited:** Zero-loss, automatic markup fix, guaranteed percent reduction, unsupported AVIF, overwrite-by-default.
- **Actions:**
  1. Inspect the `media-opt` command, MCP tool, config table, catalog row, media-write security rule, and example configuration anchors in the six existing allowed files; record the pre-edit claim at every changed anchor.
  2. Make this exact change only at those anchors and in docs/tools/media_opt.md: document audit-only default, explicit output semantics, `artifact_write`, the locked supported format set, `no_improvement`, exact SVG removal rules, CLS finding-only behavior, containment, source preservation, and old-output preservation. Replace zero-loss, automatic markup rewrite, percentage saving, AVIF, and overwrite-by-default claims.
  3. Run `.venv/Scripts/python.exe -m pytest tests/test_media_opt.py tests/test_catalog.py tests/test_cli_registry.py tests/test_mcp.py -q`; then run `rg -n "media-opt|rush_media_opt|zero-loss|30%|AVIF|allow-artifact-write|no_improvement" docs/tools/media_opt.md docs/CLI_REFERENCE.md docs/MCP_REFERENCE.md docs/CONFIGURATION.md docs/TOOL_CATALOG.md docs/SECURITY.md examples/rush.toml` and record every remaining hit with its explicit limitation or measured status.
- **Evidence:** Tests and docs claim inventory.
- **Stop:** Docs exceed measured/tested behavior.
- **Verified outcome:** Only D50-15-approved behavior is closed; markup/AVIF/guarantee dispositions remain explicit.

### PR50.11 — I24 local offline review, blocked by D50-04

#### PR50.11.1 — RED: pin the approved runtime/model and zero-network contract

- **Task ID and binary outcome:** PR50.11.1; tests fail because the approved adapter is absent, or no test is written and I24 remains blocked.
- **Start goal:** Convert a complete D50-04 decision into executable tests without a real model.
- **Prerequisites:** PR50.0.2 records every approved field.
- **Documentation impact:** None.
- **Dependency impact:** Approved optional runtime only; no manifest edit in RED.
- **Allowed writes:** Create tests/test_offline_review.py.
- **Allowed reads:** D50-04 evidence; roadmap I24; ReviewTool normalization; permissions; manifests.
- **Prohibited:** Download/bundle; live inference; sockets; dependency/source/docs edits; partial decision.
- **Actions:**
  1. Inspect D50-04 field by field against planned keys, providers, checksum/license rules, and missing-component behavior. Stop if one field is absent.
  2. Make this exact change in only the test file: add test_offline_review_missing_runtime_or_model_is_skipped_without_network, guarding socket.socket/create_connection and asserting skipped/no download hint; add test_offline_review_fake_session_returns_valid_findings_and_rejects_socket_use, injecting the approved fake session/preprocessor and contained model with checksum, asserting normalized findings/provider/checksum identity and error on checksum mismatch, escape, or malformed output.
  3. Run `.venv/Scripts/python.exe -m pytest tests/test_offline_review.py::test_offline_review_missing_runtime_or_model_is_skipped_without_network tests/test_offline_review.py::test_offline_review_fake_session_returns_valid_findings_and_rejects_socket_use -q`, then `.venv/Scripts/python.exe -m pytest tests/test_offline_review.py -q`; retain absent-contract failures only.
- **Evidence:** Decision reference, fake-session contract, socket guard, named RED.
- **Stop:** Inferred field, real runtime/model/network needed, undecided output.
- **Verified outcome:** PR50.11.2 may start only with D50-04 closed.

#### PR50.11.2 — GREEN: implement only the approved adapter

- **Task ID and binary outcome:** PR50.11.2; optional local review uses the approved model/runtime and otherwise skips without network.
- **Start goal:** Satisfy RED without weights or download behavior.
- **Prerequisites:** PR50.1.2 and PR50.11.1 RED.
- **Documentation impact:** None.
- **Dependency impact:** None in this card; PR50.11.3 owns manifest/lock.
- **Allowed writes:** Create src/rush/tools/offline_runner.py only.
- **Allowed reads:** Approved decision; ReviewTool; containment; permissions.
- **Prohibited:** Manual MCP logic; weights; alternate runtime/provider; network fallback; source/prompt logs.
- **Actions:**
  1. Inspect approved runtime API and current optional-extra syntax. Confirm review --offline can pass exact options through _run_tool to one ToolFn.
  2. Make this exact change in only src/rush/tools/offline_runner.py: create `OfflineReviewTool` named `offline-review`; require slow; resolve contained user model; verify exact SHA-256/license metadata; lazily import only the D50-04 runtime and select only approved providers; construct bounded input; normalize output. Missing runtime/model is skipped; checksum/path/schema failures error; include no socket/download/registry/transport code.
  3. Run `.venv/Scripts/python.exe -m pytest tests/test_offline_review.py::test_offline_review_missing_runtime_or_model_is_skipped_without_network tests/test_offline_review.py::test_offline_review_fake_session_returns_valid_findings_and_rejects_socket_use -q`, `.venv/Scripts/python.exe -m pytest tests/test_offline_review.py -q`, `.venv/Scripts/ruff.exe check src/rush/tools/offline_runner.py tests/test_offline_review.py`, and `.venv/Scripts/ruff.exe format --check src/rush/tools/offline_runner.py tests/test_offline_review.py`; inspect imports, sockets, and logs and confirm source or prompt bytes never enter diagnostics.
- **Evidence:** RED link, checksum/socket tests, lock evidence.
- **Stop:** Runtime differs, network exists, identity unverified, source reaches diagnostics.
- **Verified outcome:** PR50.11.3 may start; core is green/private and manifests unchanged.

#### PR50.11.3 — DEPENDENCY: add only the approved optional runtime

- **Task ID and binary outcome:** PR50.11.3; pyproject/lock contain exactly the D50-04 optional runtime constraint or the packet stops.
- **Start goal:** Isolate dependency mutation from behavior.
- **Prerequisites:** PR50.11.2 and complete D50-04.
- **Documentation impact:** Evidence record only.
- **Dependency impact:** Add exact optional extra and run uv lock.
- **Allowed writes:** pyproject.toml; uv.lock; docs/developer/phase-50-implementation-evidence.md.
- **Allowed reads:** D50-04; current optional extras; runtime import in offline_runner.py.
- **Prohibited:** Source/test/public-doc/version changes; alternate packages/providers; weights.
- **Actions:**
  1. Compare exact package/constraint/extra name to D50-04 and current manifest syntax.
  2. Make this exact change in only pyproject.toml, uv.lock, and the evidence file: add only the approved optional constraint/extra, run `uv lock`, and record exact lock nodes plus no default dependency.
  3. Run `uv lock --check`, `.venv/Scripts/python.exe -m pytest tests/test_offline_review.py -q`, `.venv/Scripts/ruff.exe check src/rush/tools/offline_runner.py tests/test_offline_review.py`, and `.venv/Scripts/ruff.exe format --check src/rush/tools/offline_runner.py tests/test_offline_review.py`; inspect the exact pyproject.toml and uv.lock diff.
- **Evidence:** Decision link, manifest/lock diff, commands/exits.
- **Stop:** Unrelated lock churn, network-only resolution, alternate package, or default install.
- **Verified outcome:** PR50.11.4 may start.

#### PR50.11.4 — RED: pin offline-review registry, CLI adapter, and MCP equality

- **Task ID and binary outcome:** PR50.11.4; integration tests fail because the green optional tool is not public.
- **Start goal:** Pin exact approved options and both CLI forms.
- **Prerequisites:** PR50.1.4, PR50.F4, PR50.11.3.
- **Documentation impact:** None.
- **Dependency impact:** None.
- **Allowed writes:** tests/test_catalog.py; tests/test_cli_registry.py; tests/test_mcp.py.
- **Allowed reads:** tool signature; registrars; current review command.
- **Prohibited:** Production/core/docs edits; real runtime/model.
- **Actions:**
  1. Inspect `review` and generic command registration; confirm exact D50-04 keys.
  2. Make this exact change in only the three tests: add `test_offline_review_catalog_declares_approved_runtime_options`, `test_offline_review_cli_forms_share_registered_tool`, and `test_offline_review_mcp_uses_canonical_name_without_network`; assert one ToolSpec/object, `rush offline-review PATH`, `rush review PATH --offline`, `rush_offline_review`, missing-runtime skipped, injected-result equality, and no network/download route.
  3. Run `.venv/Scripts/python.exe -m pytest tests/test_catalog.py::test_offline_review_catalog_declares_approved_runtime_options tests/test_cli_registry.py::test_offline_review_cli_forms_share_registered_tool tests/test_mcp.py::test_offline_review_mcp_uses_canonical_name_without_network -q`, then `.venv/Scripts/python.exe -m pytest tests/test_catalog.py tests/test_cli_registry.py tests/test_mcp.py -q`; retain missing integration failures.
- **Evidence:** Route RED outputs and argument matrix.
- **Stop:** Two CLI forms cannot normalize identically or decision lacks a key.
- **Verified outcome:** PR50.11.5 may start.

#### PR50.11.5 — GREEN: register offline-review and adapt `review --offline`

- **Task ID and binary outcome:** PR50.11.5; one OfflineReviewTool backs both CLI forms and normalized MCP.
- **Start goal:** Satisfy integration only.
- **Prerequisites:** PR50.11.4 RED.
- **Documentation impact:** None.
- **Dependency impact:** None.
- **Allowed writes:** src/rush/tools/__init__.py; src/rush/catalog.py; src/rush/cli.py.
- **Allowed reads:** integration tests/tool/review command.
- **Prohibited:** Core/test/MCP/docs/dependency edits.
- **Actions:**
  1. Reinspect argument precedence and `_run_tool`.
  2. Make this exact change in only the three production files: export/register one object and exact ToolSpec/options; add thin `review --offline` normalization and generic route behavior, both making one `_run_tool` call.
  3. Run `.venv/Scripts/python.exe -m pytest tests/test_catalog.py::test_offline_review_catalog_declares_approved_runtime_options tests/test_cli_registry.py::test_offline_review_cli_forms_share_registered_tool tests/test_mcp.py::test_offline_review_mcp_uses_canonical_name_without_network -q`, `.venv/Scripts/python.exe -m pytest tests/test_offline_review.py tests/test_catalog.py tests/test_cli_registry.py tests/test_mcp.py -q`, `uv lock --check`, `.venv/Scripts/ruff.exe check src/rush/tools/offline_runner.py src/rush/tools/__init__.py src/rush/catalog.py src/rush/cli.py tests/test_offline_review.py tests/test_catalog.py tests/test_cli_registry.py tests/test_mcp.py`, and `.venv/Scripts/ruff.exe format --check src/rush/tools/offline_runner.py src/rush/tools/__init__.py src/rush/catalog.py src/rush/cli.py tests/test_offline_review.py tests/test_catalog.py tests/test_cli_registry.py tests/test_mcp.py`; inspect CLI for runtime or model logic.
- **Evidence:** Object identity, both CLI forms/MCP equality, green outputs.
- **Stop:** Duplicate object/business logic or cloud fallback.
- **Verified outcome:** PR50.11.6 may start.

#### PR50.11.6 — DOCS: document approved offline support

- **Task ID and binary outcome:** PR50.11.6; installation, model evidence, permissions, skips, and zero-download behavior match implementation.
- **Start goal:** Document only approved behavior.
- **Prerequisites:** PR50.11.5 green.
- **Documentation impact:** Create docs/tools/offline_runner.md; update CLI/MCP/CONFIGURATION/TOOL_CATALOG/SECURITY references and example.
- **Dependency impact:** Exact optional extra.
- **Allowed writes:** docs/tools/offline_runner.md; docs/CLI_REFERENCE.md; docs/MCP_REFERENCE.md; docs/CONFIGURATION.md; docs/TOOL_CATALOG.md; docs/SECURITY.md; examples/rush.toml.
- **Allowed reads:** src/rush/tools/offline_runner.py; tests/test_offline_review.py; tests/test_catalog.py; tests/test_cli_registry.py; tests/test_mcp.py; approved D50-04 record; pyproject.toml; uv.lock; the seven allowed documentation/configuration paths.
- **Prohibited:** Bundled model, download command, universal air-gap, unsupported provider/device/performance, cloud fallback.
- **Actions:**
  1. Inspect the `offline-review` command, MCP tool, config table, catalog row, offline-model security rule, and example anchors in docs/CLI_REFERENCE.md, docs/MCP_REFERENCE.md, docs/CONFIGURATION.md, docs/TOOL_CATALOG.md, docs/SECURITY.md, and examples/rush.toml; reconcile every field against D50-04 and record each pre-edit anchor.
  2. Make this exact change only at those anchors and in docs/tools/offline_runner.md: document the user-supplied model/license/SHA-256 evidence, exact optional install, slow permission, missing-component skipped, checksum/schema errors, no bundle/download, and tested socket boundary.
  3. Run `.venv/Scripts/python.exe -m pytest tests/test_offline_review.py tests/test_catalog.py tests/test_cli_registry.py tests/test_mcp.py -q` and `uv lock --check`; then run `rg -n "offline-review|rush_offline_review|optional runtime|download|bundled|allow-slow|sha256" docs/tools/offline_runner.md docs/CLI_REFERENCE.md docs/MCP_REFERENCE.md docs/CONFIGURATION.md docs/TOOL_CATALOG.md docs/SECURITY.md examples/rush.toml` and record every exact changed anchor. Compare the documented package name and constraint directly to the exact D50-04 record and `pyproject.toml`; stop on any difference.
- **Evidence:** Tests, lock check, docs search.
- **Stop:** Docs exceed D50-04 or green evidence.
- **Verified outcome:** I24 closes only with D50-04; otherwise blocked.

### PR50.12 — I22 shared quality-diff data and CLI-only rendering — blocked by D50-16

#### PR50.12.1 — RED: pin canonical commit/finding deltas

- **Task ID and binary outcome:** PR50.12.1; the direct-tool delta test executes and fails only because canonical introduced/resolved/persisting/unknown data is absent.
- **Start goal:** Define data independently from Rich rendering and terminal input.
- **Prerequisites:** PR50.0.1 and approved D50-16 outcome.
- **Documentation impact:** None.
- **Dependency impact:** Existing Rich/Git.
- **Allowed writes:** Create tests/test_tui_diff.py.
- **Allowed reads:** roadmap I22; src/rush/cache.py public reads; Git helpers; ToolResult; CLI groups.
- **Prohibited:** Real event loop; MCP rendering; cache writes; raw DB query when public reader exists.
- **Actions:**
  1. Inspect cache public readers and Git helpers. Record available commit/tool/status/fingerprint/rule/path/severity/timestamp fields. Stop if two-commit evidence cannot be read.
  2. Make this exact change in only the test file: add `test_tui_diff_computes_commit_deltas_from_fixture_records` asserting deterministic introduced/resolved/persisting sets, status/count deltas, fingerprint identity, explicit uncorrelated records, and unknown for missing evidence. Instantiate the tool directly with injected readers; add no Rich, CLI, MCP, or renderer assertions.
  3. Run `.venv/Scripts/python.exe -m pytest tests/test_tui_diff.py::test_tui_diff_computes_commit_deltas_from_fixture_records -q`, then `.venv/Scripts/python.exe -m pytest tests/test_tui_diff.py -q`; retain absent-contract failures and confirm injected readers received every call so no real cache or terminal input was used.
- **Evidence:** Fixture schema and named RED.
- **Stop:** Reader lacks required fields, identity is message-only, or MCP must render.
- **Verified outcome:** PR50.12.2 may start.

#### PR50.12.2 — GREEN: implement canonical delta data

- **Task ID and binary outcome:** PR50.12.2; the private TuiDiffTool returns the pinned canonical delta data without rendering, terminal control codes, registry, CLI, or MCP behavior.
- **Start goal:** Keep calculation in tui_diff.py and presentation in cli.py.
- **Prerequisites:** PR50.1.2 and PR50.12.1 RED.
- **Documentation impact:** None.
- **Dependency impact:** None.
- **Allowed writes:** Create src/rush/tools/tui_diff.py only.
- **Allowed reads:** Confirmed cache/Git readers; Rich patterns; RED.
- **Prohibited:** Test/registry/CLI/MCP/docs/dependency edits; Rich/event loop/cache writes/invented score.
- **Actions:**
  1. Inspect reader signatures and CLI registration. Use fingerprint identity; only use rule/path/line/message tuple when all exist; otherwise mark uncorrelated.
  2. Make this exact change in only src/rush/tools/tui_diff.py: create `TuiDiffTool` named `tui-diff` with injected readers, refs/count, fingerprint-first identity, deterministic delta sets, uncorrelated records, and unknowns; include no Rich/Click/registration/write code.
  3. Run `.venv/Scripts/python.exe -m pytest tests/test_tui_diff.py::test_tui_diff_computes_commit_deltas_from_fixture_records -q`, `.venv/Scripts/python.exe -m pytest tests/test_tui_diff.py -q`, `.venv/Scripts/ruff.exe check src/rush/tools/tui_diff.py tests/test_tui_diff.py`, and `.venv/Scripts/ruff.exe format --check src/rush/tools/tui_diff.py tests/test_tui_diff.py`; search the module for Rich, Click, input/event-loop, SQL writes, and registry imports.
- **Evidence:** RED link, identity proof, CLI/MCP equality.
- **Stop:** Schema change, score invention, ToolFn rendering, missing side becomes zero.
- **Verified outcome:** PR50.12.3 may start; delta core remains private.

#### PR50.12.3 — RED: pin CLI-only noninteractive rendering boundary

- **Task ID and binary outcome:** PR50.12.3; renderer tests fail because no presentation function consumes the green raw delta.
- **Start goal:** Pin presentation separately from calculation and MCP.
- **Prerequisites:** PR50.12.2 and D50-16 selecting the bounded renderer. A full-screen selection requires a plan amendment with event-loop tasks instead.
- **Documentation impact:** None.
- **Dependency impact:** Existing Rich only.
- **Allowed writes:** tests/test_tui_diff.py; tests/test_cli_registry.py.
- **Allowed reads:** TuiDiffTool result schema; existing Rich render helpers; cli.py.
- **Prohibited:** Production/MCP/docs edits; full-screen/event loop unless amended.
- **Actions:**
  1. Inspect exact Rich helper patterns and noninteractive detection.
  2. Add `test_tui_diff_cli_renderer_receives_identical_raw_delta` and `test_tui_diff_noninteractive_output_has_no_control_codes`; use renderer spy and fixed terminal capability; assert presentation does not alter result data.
  3. Run `.venv/Scripts/python.exe -m pytest tests/test_tui_diff.py::test_tui_diff_cli_renderer_receives_identical_raw_delta tests/test_cli_registry.py::test_tui_diff_noninteractive_output_has_no_control_codes -q`, then `.venv/Scripts/python.exe -m pytest tests/test_tui_diff.py tests/test_cli_registry.py -q`; retain absent-renderer failures.
- **Evidence:** Renderer RED results and raw-delta equality.
- **Stop:** D50-16 selects full-screen or rendering requires core/schema change.
- **Verified outcome:** PR50.12.4 may start.

#### PR50.12.4 — GREEN: add thin CLI rendering without changing data

- **Task ID and binary outcome:** PR50.12.4; CLI renderer consumes raw delta while ToolFn remains presentation-free.
- **Start goal:** Satisfy renderer tests only.
- **Prerequisites:** PR50.12.3 RED.
- **Documentation impact:** None.
- **Dependency impact:** None.
- **Allowed writes:** src/rush/cli.py only.
- **Allowed reads:** renderer tests/result schema/Rich helpers.
- **Prohibited:** Test/core/MCP/registry/docs edits; event loop/full-screen state.
- **Actions:**
  1. Reinspect unchanged renderer assertions.
  2. Add one pure presentation helper for the exact raw delta fields and noninteractive fallback; no Git/cache calculation or ToolFn construction.
  3. Run `.venv/Scripts/python.exe -m pytest tests/test_tui_diff.py::test_tui_diff_computes_commit_deltas_from_fixture_records tests/test_tui_diff.py::test_tui_diff_cli_renderer_receives_identical_raw_delta tests/test_cli_registry.py::test_tui_diff_noninteractive_output_has_no_control_codes -q`, `.venv/Scripts/python.exe -m pytest tests/test_tui_diff.py tests/test_cli_registry.py -q`, `.venv/Scripts/ruff.exe check src/rush/cli.py tests/test_tui_diff.py tests/test_cli_registry.py`, and `.venv/Scripts/ruff.exe format --check src/rush/cli.py tests/test_tui_diff.py tests/test_cli_registry.py`; inspect the helper for reads, writes, or calculation.
- **Evidence:** RED link, raw equality, green outputs.
- **Stop:** Renderer mutates data or performs calculation/I/O beyond terminal output.
- **Verified outcome:** PR50.12.5 may start.

#### PR50.12.5 — RED: pin tui-diff registration, nested CLI, and MCP data

- **Task ID and binary outcome:** PR50.12.5; integration tests fail because the tool is not registered and routes do not share data.
- **Start goal:** Pin public routing independently.
- **Prerequisites:** PR50.1.4, PR50.F4, PR50.12.4.
- **Documentation impact:** None.
- **Dependency impact:** None.
- **Allowed writes:** tests/test_catalog.py; tests/test_cli_registry.py; tests/test_mcp.py.
- **Allowed reads:** tool/renderer/registrars.
- **Prohibited:** Production/core/docs edits.
- **Actions:**
  1. Inspect CLI group/generic registration conflicts.
  2. Add `test_tui_diff_catalog_declares_commit_count_option`, `test_tui_diff_cli_forms_share_raw_data_and_renderer_boundary`, and `test_tui_diff_mcp_returns_raw_data_without_control_codes`; assert exact option spec, one object, `rush tui-diff PATH --json`, `rush tui diff PATH`, `rush_tui_diff`, identical raw data, CLI-only renderer, and no MCP control codes.
  3. Run `.venv/Scripts/python.exe -m pytest tests/test_catalog.py::test_tui_diff_catalog_declares_commit_count_option tests/test_cli_registry.py::test_tui_diff_cli_forms_share_raw_data_and_renderer_boundary tests/test_mcp.py::test_tui_diff_mcp_returns_raw_data_without_control_codes -q`, then `.venv/Scripts/python.exe -m pytest tests/test_catalog.py tests/test_cli_registry.py tests/test_mcp.py -q`; retain integration failures.
- **Evidence:** Route RED outputs and command-conflict observation.
- **Stop:** Duplicate command name or full-screen decision unresolved.
- **Verified outcome:** PR50.12.6 may start.

#### PR50.12.6 — GREEN: register tui-diff and connect only CLI rendering

- **Task ID and binary outcome:** PR50.12.6; one TuiDiffTool backs generic/nested CLI and MCP data.
- **Start goal:** Satisfy integration only.
- **Prerequisites:** PR50.12.5 RED.
- **Documentation impact:** None.
- **Dependency impact:** None.
- **Allowed writes:** src/rush/tools/__init__.py; src/rush/catalog.py; src/rush/cli.py.
- **Allowed reads:** integration tests/tool/renderer.
- **Prohibited:** Core/test/MCP/docs edits.
- **Actions:**
  1. Reinspect command registration order.
  2. Export/register one object and exact ToolSpec; connect nested CLI through `_run_tool` and renderer, keep JSON/noninteractive raw; no MCP edit.
  3. Run `.venv/Scripts/python.exe -m pytest tests/test_catalog.py::test_tui_diff_catalog_declares_commit_count_option tests/test_cli_registry.py::test_tui_diff_cli_forms_share_raw_data_and_renderer_boundary tests/test_mcp.py::test_tui_diff_mcp_returns_raw_data_without_control_codes -q`, `.venv/Scripts/python.exe -m pytest tests/test_tui_diff.py tests/test_catalog.py tests/test_cli_registry.py tests/test_mcp.py -q`, `.venv/Scripts/ruff.exe check src/rush/tools/tui_diff.py src/rush/tools/__init__.py src/rush/catalog.py src/rush/cli.py tests/test_tui_diff.py tests/test_catalog.py tests/test_cli_registry.py tests/test_mcp.py`, and `.venv/Scripts/ruff.exe format --check src/rush/tools/tui_diff.py src/rush/tools/__init__.py src/rush/catalog.py src/rush/cli.py tests/test_tui_diff.py tests/test_catalog.py tests/test_cli_registry.py tests/test_mcp.py`; inspect MCP output for control codes and CLI for duplicate calculation.
- **Evidence:** Object identity, route equality, green outputs.
- **Stop:** Duplicate command/business logic or MCP rendering.
- **Verified outcome:** PR50.12.7 may start.

#### PR50.12.7 — DOCS: document calculation/rendering separation

- **Task ID and binary outcome:** PR50.12.7; interactive CLI, canonical data, evidence limits, and no-write behavior are exact.
- **Start goal:** Remove full-screen/60-FPS/universal-history claims.
- **Prerequisites:** PR50.12.6 green.
- **Documentation impact:** Create docs/tools/tui_diff.md; update CLI/MCP/CONFIGURATION/TOOL_CATALOG references and example.
- **Dependency impact:** None.
- **Allowed writes:** docs/tools/tui_diff.md; docs/CLI_REFERENCE.md; docs/MCP_REFERENCE.md; docs/CONFIGURATION.md; docs/TOOL_CATALOG.md; examples/rush.toml.
- **Allowed reads:** src/rush/tools/tui_diff.py; src/rush/cli.py renderer; tests/test_tui_diff.py; tests/test_catalog.py; tests/test_cli_registry.py; tests/test_mcp.py; the six allowed documentation/configuration paths.
- **Prohibited:** MCP TUI, complete history, invented score, frame-rate claim.
- **Actions:**
  1. Inspect fields, identity fallback, flags, routes, terminal behavior.
  2. Make this exact change only at the `tui-diff` command, MCP tool, config table, catalog row, and example anchors in docs/CLI_REFERENCE.md, docs/MCP_REFERENCE.md, docs/CONFIGURATION.md, docs/TOOL_CATALOG.md, and examples/rush.toml and in docs/tools/tui_diff.md: document CLI-only rendering; MCP/noninteractive raw data; required cache evidence; exact delta definitions; unknowns; and read-only behavior.
  3. Run `.venv/Scripts/python.exe -m pytest tests/test_tui_diff.py tests/test_catalog.py tests/test_cli_registry.py tests/test_mcp.py -q`; then run `rg -n "tui diff|tui-diff|rush_tui_diff|60 FPS|full-screen|introduced|resolved|unknown" docs/tools/tui_diff.md docs/CLI_REFERENCE.md docs/MCP_REFERENCE.md docs/CONFIGURATION.md docs/TOOL_CATALOG.md examples/rush.toml` and record every exact changed anchor.
- **Evidence:** Tests and docs search.
- **Stop:** Docs imply unavailable data.
- **Verified outcome:** Only the D50-16-selected outcome is closed; a nonselected full-screen promise is explicitly deferred or blocked.

### PR50.13 — I26 fixed-sample benchmark and guarded baseline — blocked by D50-17

#### PR50.13.1 — RED: pin supplied-sample comparison math

- **Task ID and binary outcome:** PR50.13.1; the direct comparison test executes and fails only because the pinned supplied-sample statistics, delta, and threshold semantics are absent.
- **Start goal:** Compare supplied numeric samples; execute no quality suite.
- **Prerequisites:** PR50.0.1 and approved D50-17.
- **Documentation impact:** None.
- **Dependency impact:** Stdlib statistics.
- **Allowed writes:** Create tests/test_benchmark.py.
- **Allowed reads:** docs/developer/rush-token-innovation-enhancement-report-plan.md I26; src/rush/permissions.py `ExecutionPermissions.cache_write`; src/rush/tools/common.py; tests/test_tool_common.py.
- **Prohibited:** Test/lint execution; t-test claims; telemetry; implicit baseline.
- **Actions:**
  1. Inspect cache_write and atomic-store patterns. Confirm benchmark is absent.
  2. Make this exact change in only the test file: add `test_benchmark_compares_fixed_samples_against_threshold` with exact baseline/current arrays; instantiate tool directly; assert count, mean, population stddev, nearest-rank p95, delta_pct, threshold, unit mismatch error, absent baseline skipped, and fail only for selected fail_on metric. Add no store assertions.
  3. Run `.venv/Scripts/python.exe -m pytest tests/test_benchmark.py::test_benchmark_compares_fixed_samples_against_threshold -q`, then `.venv/Scripts/python.exe -m pytest tests/test_benchmark.py -q`; retain absent-contract failures.
- **Evidence:** Arrays/expected numbers, write assertions, RED.
- **Stop:** Inferential statistic invented, command executed, absent baseline passes, nonfinite accepted.
- **Verified outcome:** PR50.13.2 may start.

#### PR50.13.2 — GREEN: implement deterministic supplied-sample comparison

- **Task ID and binary outcome:** PR50.13.2; the private BenchmarkTool computes only the pinned comparison result and performs no store, cache, registry, or transport operation.
- **Start goal:** Implement pinned descriptive statistics without orchestration.
- **Prerequisites:** PR50.1.2 and PR50.13.1 RED.
- **Documentation impact:** None.
- **Dependency impact:** None.
- **Allowed writes:** Create src/rush/tools/benchmark.py only.
- **Allowed reads:** Python stdlib `statistics`; src/rush/tools/common.py; src/rush/permissions.py; tests/test_benchmark.py; tests/test_tool_common.py.
- **Prohibited:** Test/registry/routes/docs/dependency/store writes; subprocess/tool execution; scipy; telemetry.
- **Actions:**
  1. Inspect `resolve_contained_output`, `atomic_write_bytes`, `ExecutionPermissions.cache_write`, and custom CLI adapter patterns in src/rush/cli.py. Fix input as contained samples JSON plus compare/record operation.
  2. Make this exact change in only src/rush/tools/benchmark.py: create `BenchmarkTool` named `benchmark`; validate finite nonempty arrays/units; compute exact count/mean/population stddev/nearest-rank p95/delta; absent baseline skipped; regression warn unless exact fail_on then fail. Include no store/permission/registry/transport code.
  3. Run `.venv/Scripts/python.exe -m pytest tests/test_benchmark.py::test_benchmark_compares_fixed_samples_against_threshold -q`, `.venv/Scripts/python.exe -m pytest tests/test_benchmark.py -q`, `.venv/Scripts/ruff.exe check src/rush/tools/benchmark.py tests/test_benchmark.py`, and `.venv/Scripts/ruff.exe format --check src/rush/tools/benchmark.py tests/test_benchmark.py`; search for subprocess, scipy, store writes, or registry imports.
- **Evidence:** RED link, math assertions, commands.
- **Stop:** Unit mismatch, implicit execution, non-atomic write, absent baseline green.
- **Verified outcome:** PR50.13.3 may start; comparison core remains private.

#### PR50.13.3 — RED: pin permissioned atomic baseline storage

- **Task ID and binary outcome:** PR50.13.3; store tests fail because comparison core cannot record.
- **Start goal:** Pin persistence independently from math.
- **Prerequisites:** PR50.1.6 and PR50.13.2.
- **Documentation impact:** None.
- **Dependency impact:** None.
- **Allowed writes:** tests/test_benchmark.py only.
- **Allowed reads:** src/rush/tools/benchmark.py; src/rush/permissions.py; src/rush/tools/common.py; tests/test_tool_common.py.
- **Prohibited:** Production/routes/docs edits; implicit baseline initialization.
- **Actions:**
  1. Inspect `ExecutionPermissions.cache_write`, `resolve_contained_output`, `atomic_write_bytes`, and the PR50.1.5 failure-preservation tests.
  2. Add `test_benchmark_record_requires_cache_write_and_writes_versioned_schema`, `test_benchmark_record_rejects_invalid_samples_and_escaping_path`, and `test_benchmark_record_preserves_existing_store_on_replace_failure`; assert denied no-write, allowed units/samples, malformed/nonfinite/empty rejection, contained path, and old-file preservation.
  3. Run `.venv/Scripts/python.exe -m pytest tests/test_benchmark.py::test_benchmark_record_requires_cache_write_and_writes_versioned_schema tests/test_benchmark.py::test_benchmark_record_rejects_invalid_samples_and_escaping_path tests/test_benchmark.py::test_benchmark_record_preserves_existing_store_on_replace_failure -q`, then `.venv/Scripts/python.exe -m pytest tests/test_benchmark.py -q`; retain absent-store failures.
- **Evidence:** Store RED results and fixture hashes.
- **Stop:** Store schema/path is undefined or helper cannot preserve old file.
- **Verified outcome:** PR50.13.4 may start.

#### PR50.13.4 — GREEN: add explicit atomic baseline recording

- **Task ID and binary outcome:** PR50.13.4; record operation writes only with cache_write to the contained versioned store.
- **Start goal:** Satisfy storage tests only.
- **Prerequisites:** PR50.13.3 RED.
- **Documentation impact:** None.
- **Dependency impact:** None.
- **Allowed writes:** src/rush/tools/benchmark.py only.
- **Allowed reads:** unchanged store tests/helpers.
- **Prohibited:** Test/routes/docs/dependency/subprocess changes.
- **Actions:**
  1. Reinspect assertions/helper signatures.
  2. Add explicit record operation requiring cache_write; validate schema; write temp then replace contained path; never auto-initialize during compare.
  3. Run `.venv/Scripts/python.exe -m pytest tests/test_benchmark.py -q`, `.venv/Scripts/ruff.exe check src/rush/tools/benchmark.py tests/test_benchmark.py`, and `.venv/Scripts/ruff.exe format --check src/rush/tools/benchmark.py tests/test_benchmark.py`; trace every write to the explicit record operation and cache permission.
- **Evidence:** RED link, write trace, hashes, green outputs.
- **Stop:** Compare writes, denied path changes, or old file can be lost.
- **Verified outcome:** PR50.13.5 may start.

#### PR50.13.5 — RED: pin benchmark registration and operation routes

- **Task ID and binary outcome:** PR50.13.5; integration tests fail because complete tool is private.
- **Start goal:** Pin exact typed options, CLI operations, MCP, and permissions.
- **Prerequisites:** PR50.1.4, PR50.F4, PR50.13.4.
- **Documentation impact:** None.
- **Dependency impact:** None.
- **Allowed writes:** tests/test_catalog.py; tests/test_cli_registry.py; tests/test_mcp.py.
- **Allowed reads:** tool/registrars/typed keys.
- **Prohibited:** Production/core/docs edits.
- **Actions:**
  1. Inspect generic/custom CLI needs.
  2. Add `test_benchmark_catalog_declares_comparison_and_store_options`, `test_benchmark_cli_forwards_compare_record_and_cache_permission`, and `test_benchmark_mcp_uses_canonical_name_and_matches_cli`; assert exact three option specs, one object, compare/record CLI flags, `rush_benchmark`, cache permission forwarding, and ToolResult equality.
  3. Run `.venv/Scripts/python.exe -m pytest tests/test_catalog.py::test_benchmark_catalog_declares_comparison_and_store_options tests/test_cli_registry.py::test_benchmark_cli_forwards_compare_record_and_cache_permission tests/test_mcp.py::test_benchmark_mcp_uses_canonical_name_and_matches_cli -q`, then `.venv/Scripts/python.exe -m pytest tests/test_catalog.py tests/test_cli_registry.py tests/test_mcp.py -q`; retain integration failures.
- **Evidence:** Route RED results and argument matrix.
- **Stop:** Operation inputs are undefined or core change required.
- **Verified outcome:** PR50.13.6 may start.

#### PR50.13.6 — GREEN: register benchmark with thin CLI operations

- **Task ID and binary outcome:** PR50.13.6; one BenchmarkTool backs catalog, CLI, and MCP.
- **Start goal:** Satisfy integration only.
- **Prerequisites:** PR50.13.5 RED.
- **Documentation impact:** None.
- **Dependency impact:** None.
- **Allowed writes:** src/rush/tools/__init__.py; src/rush/catalog.py; src/rush/cli.py.
- **Allowed reads:** integration tests/tool.
- **Prohibited:** Core/test/MCP/docs edits.
- **Actions:**
  1. Reinspect `_run_tool`/Click conventions.
  2. Export/register one object; add exact ToolSpec/options; add only compare/record argument normalization plus one `_run_tool` call.
  3. Run `.venv/Scripts/python.exe -m pytest tests/test_catalog.py::test_benchmark_catalog_declares_comparison_and_store_options tests/test_cli_registry.py::test_benchmark_cli_forwards_compare_record_and_cache_permission tests/test_mcp.py::test_benchmark_mcp_uses_canonical_name_and_matches_cli -q`, `.venv/Scripts/python.exe -m pytest tests/test_benchmark.py tests/test_catalog.py tests/test_cli_registry.py tests/test_mcp.py -q`, `.venv/Scripts/ruff.exe check src/rush/tools/benchmark.py src/rush/tools/__init__.py src/rush/catalog.py src/rush/cli.py tests/test_benchmark.py tests/test_catalog.py tests/test_cli_registry.py tests/test_mcp.py`, and `.venv/Scripts/ruff.exe format --check src/rush/tools/benchmark.py src/rush/tools/__init__.py src/rush/catalog.py src/rush/cli.py tests/test_benchmark.py tests/test_catalog.py tests/test_cli_registry.py tests/test_mcp.py`; inspect CLI for statistics or store logic.
- **Evidence:** Object identity, route equality, green outputs.
- **Stop:** Business logic in CLI or duplicate object.
- **Verified outcome:** PR50.13.7 may start.

#### PR50.13.7 — DOCS: document supplied samples and baseline semantics

- **Task ID and binary outcome:** PR50.13.7; schema, math, threshold/fail policy, and permission are documented.
- **Start goal:** Remove statistical-significance and automatic-suite claims.
- **Prerequisites:** PR50.13.6 green.
- **Documentation impact:** Create docs/tools/benchmark.md; update CLI/MCP/CONFIGURATION/TOOL_CATALOG references and example.
- **Dependency impact:** None.
- **Allowed writes:** docs/tools/benchmark.md; docs/CLI_REFERENCE.md; docs/MCP_REFERENCE.md; docs/CONFIGURATION.md; docs/TOOL_CATALOG.md; examples/rush.toml.
- **Allowed reads:** src/rush/tools/benchmark.py; tests/test_benchmark.py; tests/test_catalog.py; tests/test_cli_registry.py; tests/test_mcp.py; the six allowed documentation/configuration paths.
- **Prohibited:** t-test/significance, automatic runs, prevention guarantee, implicit initialization.
- **Actions:**
  1. Inspect the `benchmark` command, MCP tool, config table, catalog row, and example anchors in docs/CLI_REFERENCE.md, docs/MCP_REFERENCE.md, docs/CONFIGURATION.md, docs/TOOL_CATALOG.md, and examples/rush.toml; record each pre-edit anchor.
  2. Make this exact change only at those anchors and in docs/tools/benchmark.md: document supplied arrays/units, exact mean/population-stddev/nearest-rank-p95/delta formulas, missing-baseline skipped, threshold/`fail_on`, explicit `cache_write` record, contained atomic path, and canonical routes.
  3. Run `.venv/Scripts/python.exe -m pytest tests/test_benchmark.py tests/test_catalog.py tests/test_cli_registry.py tests/test_mcp.py -q`; then run `rg -n "benchmark|rush_benchmark|statistically significant|record-baseline|cache-write|p95|fail_on" docs/tools/benchmark.md docs/CLI_REFERENCE.md docs/MCP_REFERENCE.md docs/CONFIGURATION.md docs/TOOL_CATALOG.md examples/rush.toml` and record every exact changed anchor.
- **Evidence:** Tests and docs search.
- **Stop:** Docs claim inferential statistics or execution.
- **Verified outcome:** Only D50-17-approved supplied-sample/store behavior is closed; suite execution/significance remains explicit.

### PR50.14 — I27 conservative dead-asset inventory and manifest-bound prune — blocked by D50-18

#### PR50.14.1 — RED: pin conservative inventory and uncertain references

- **Task ID and binary outcome:** PR50.14.1; the direct audit test executes and fails only because the pinned inventory and literal/dynamic-reference states are absent or incorrect.
- **Start goal:** Make deletion impossible unless a prior manifest, current hash, permission, containment, and re-scan agree.
- **Prerequisites:** PR50.0.1 and explicit D50-18 disposition for I27.
- **Documentation impact:** None.
- **Dependency impact:** None.
- **Allowed writes:** Create tests/test_dead_asset.py only.
- **Allowed reads:** dead_asset.py; current CLI/MCP routes; roadmap I27; containment/hash patterns.
- **Prohibited:** Production/docs edits; real repository assets; glob deletion; Git as rollback.
- **Actions:**
  1. Inspect DeadAssetScanner.scan_dead_assets, supported extensions/reference rules, and every caller.
  2. Make this exact change in only tests: add `test_dead_asset_marks_literal_dynamic_and_unreadable_references_without_deleting` with literal import/url, unreferenced asset, dynamic `icon-{name}.svg` prefix, unsupported/unreadable source, and tree hash; instantiate tool directly; assert referenced/candidate/uncertain sets, evidence, and byte-identical tree. Add no manifest/prune/route assertions.
  3. Run `.venv/Scripts/python.exe -m pytest tests/test_dead_asset.py::test_dead_asset_marks_literal_dynamic_and_unreadable_references_without_deleting -q`, then `.venv/Scripts/python.exe -m pytest tests/test_dead_asset.py -q`; retain only inventory-state failures in the direct-tool test. PR50.14.7 owns smoke/route migration.
- **Evidence:** Fixture hashes, manifest schema, named RED.
- **Stop:** Current scan alone authorizes deletion, uncertain becomes dead, or recovery assumes Git.
- **Verified outcome:** PR50.14.2 may start.

#### PR50.14.2 — GREEN: implement conservative read-only inventory

- **Task ID and binary outcome:** PR50.14.2; the private DeadAssetTool returns the pinned inventory/reference states without manifest export, deletion, registry, or transport behavior.
- **Start goal:** Replace broad confidence with a two-step delete protocol.
- **Prerequisites:** PR50.1.2 and PR50.14.1 RED.
- **Documentation impact:** None.
- **Dependency impact:** None.
- **Allowed writes:** src/rush/tools/dead_asset.py only.
- **Allowed reads:** src/rush/tools/common.py; src/rush/permissions.py; src/rush/tools/dead_asset.py; tests/test_dead_asset.py; tests/test_tool_common.py; src/rush/catalog.py; src/rush/tools/__init__.py.
- **Prohibited:** Test/registry/route/docs/dependency/manifest/delete edits; CSS/design tokens; new parser.
- **Actions:**
  1. Inspect and freeze the finite asset/source extension sets in tests. Unsupported languages and unreadable files must make affected candidates uncertain.
  2. Make this exact change in only src/rush/tools/dead_asset.py: replace scanner with `DeadAssetTool` named `dead-asset`; inventory contained regular assets; scan only frozen extension/literal/dynamic-prefix rules; classify referenced/candidate/uncertain with evidence; unsupported/unreadable sources force uncertainty; write/delete nothing.
  3. Run `.venv/Scripts/python.exe -m pytest tests/test_dead_asset.py::test_dead_asset_marks_literal_dynamic_and_unreadable_references_without_deleting -q`, `.venv/Scripts/python.exe -m pytest tests/test_dead_asset.py -q`, `.venv/Scripts/ruff.exe check src/rush/tools/dead_asset.py tests/test_dead_asset.py`, and `.venv/Scripts/ruff.exe format --check src/rush/tools/dead_asset.py tests/test_dead_asset.py`; search for manifest, write, unlink, registry, or transport code.
- **Evidence:** RED link, unlink guard trace, commands, private ToolFn identity.
- **Stop:** Deletion bypasses manifest/hash/rescan/permission/containment or unsupported source becomes candidate.
- **Verified outcome:** PR50.14.3 may start; inventory core remains private.

#### PR50.14.3 — RED: pin permissioned deterministic deletion manifest export

- **Task ID and binary outcome:** PR50.14.3; manifest tests fail because audit cannot export.
- **Start goal:** Pin evidence artifact separately from deletion.
- **Prerequisites:** PR50.1.6 and PR50.14.2.
- **Documentation impact:** None.
- **Dependency impact:** None.
- **Allowed writes:** tests/test_dead_asset.py only.
- **Allowed reads:** src/rush/tools/dead_asset.py; src/rush/permissions.py; src/rush/tools/common.py; tests/test_tool_common.py.
- **Prohibited:** Production/routes/docs edits; deletion.
- **Actions:**
  1. Inspect `ExecutionPermissions.artifact_write`, `resolve_contained_output`, `atomic_write_bytes`, the PR50.1.5 failure-preservation tests, and the exact inventory record fields.
  2. Add `test_dead_asset_manifest_export_requires_artifact_permission`, `test_dead_asset_manifest_export_is_deterministic_contained_and_atomic`, and `test_dead_asset_manifest_export_preserves_existing_file_on_error`; assert denied/no-write, allowed versioned manifest containing relative path/SHA-256/size/reason/state, deterministic rerun, escape/symlink rejection, and replace-failure preservation.
  3. Run `.venv/Scripts/python.exe -m pytest tests/test_dead_asset.py::test_dead_asset_manifest_export_requires_artifact_permission tests/test_dead_asset.py::test_dead_asset_manifest_export_is_deterministic_contained_and_atomic tests/test_dead_asset.py::test_dead_asset_manifest_export_preserves_existing_file_on_error -q`, then `.venv/Scripts/python.exe -m pytest tests/test_dead_asset.py -q`; retain absent-export failures.
- **Evidence:** Manifest RED results and hashes.
- **Stop:** Manifest schema or atomic helper is undefined.
- **Verified outcome:** PR50.14.4 may start.

#### PR50.14.4 — GREEN: add guarded manifest export without deletion

- **Task ID and binary outcome:** PR50.14.4; audit optionally exports exact candidate evidence with artifact permission.
- **Start goal:** Satisfy manifest tests only.
- **Prerequisites:** PR50.14.3 RED.
- **Documentation impact:** None.
- **Dependency impact:** None.
- **Allowed writes:** src/rush/tools/dead_asset.py only.
- **Allowed reads:** unchanged manifest tests/helpers.
- **Prohibited:** Test/routes/docs/delete changes.
- **Actions:**
  1. Reinspect assertions/helpers.
  2. Add explicit export operation requiring artifact_write and contained path; serialize versioned candidate records deterministically; temp-write/replace; never delete.
  3. Run `.venv/Scripts/python.exe -m pytest tests/test_dead_asset.py -q`, `.venv/Scripts/ruff.exe check src/rush/tools/dead_asset.py tests/test_dead_asset.py`, and `.venv/Scripts/ruff.exe format --check src/rush/tools/dead_asset.py tests/test_dead_asset.py`; trace writes and confirm zero unlink.
- **Evidence:** RED link, hashes, write trace, green outputs.
- **Stop:** Uncertain/referenced enters candidates or export deletes.
- **Verified outcome:** PR50.14.5 may start.

#### PR50.14.5 — RED: pin manifest/hash/rescan guarded prune

- **Task ID and binary outcome:** PR50.14.5; prune tests fail because no deletion branch exists.
- **Start goal:** Pin every deletion guard independently.
- **Prerequisites:** PR50.1.6 and PR50.14.4.
- **Documentation impact:** None.
- **Dependency impact:** None.
- **Allowed writes:** tests/test_dead_asset.py only.
- **Allowed reads:** tool; permissions; containment/hash helpers.
- **Prohibited:** Production/routes/docs edits; real repository assets; Git rollback.
- **Actions:**
  1. Inspect manifest reader/hash/containment seams.
  2. Add `test_dead_asset_prune_denied_is_noop`, `test_dead_asset_prune_deletes_only_unchanged_revalidated_manifest_candidates`, and `test_dead_asset_prune_retains_changed_referenced_uncertain_or_invalid_entries`; assert deletion only when manifest candidate, current hash, no-symlink containment, and fresh rescan all agree, while changed hash, new reference, uncertain, missing, escape, symlink, malformed, and version-mismatch entries remain with findings.
  3. Run `.venv/Scripts/python.exe -m pytest tests/test_dead_asset.py::test_dead_asset_prune_denied_is_noop tests/test_dead_asset.py::test_dead_asset_prune_deletes_only_unchanged_revalidated_manifest_candidates tests/test_dead_asset.py::test_dead_asset_prune_retains_changed_referenced_uncertain_or_invalid_entries -q`, then `.venv/Scripts/python.exe -m pytest tests/test_dead_asset.py -q`; retain absent-prune failures.
- **Evidence:** Prune RED matrix and fixture hashes.
- **Stop:** Any guard cannot be deterministically tested or recovery assumes Git.
- **Verified outcome:** PR50.14.6 may start.

#### PR50.14.6 — GREEN: delete only unchanged revalidated manifest candidates

- **Task ID and binary outcome:** PR50.14.6; prune deletes only entries passing every pinned guard.
- **Start goal:** Satisfy prune tests only.
- **Prerequisites:** PR50.14.5 RED.
- **Documentation impact:** None.
- **Dependency impact:** None.
- **Allowed writes:** src/rush/tools/dead_asset.py only.
- **Allowed reads:** unchanged prune tests/helpers.
- **Prohibited:** Test/routes/docs/CSS/design-token changes; glob deletion.
- **Actions:**
  1. Reinspect every assertion and helper.
  2. Add explicit prune requiring artifact_write/manifest; validate schema; re-resolve/no-follow, hash, and rerun inventory; unlink only unchanged candidates with all guards true; retain/report every other entry.
  3. Run `.venv/Scripts/python.exe -m pytest tests/test_dead_asset.py -q`, `.venv/Scripts/ruff.exe check src/rush/tools/dead_asset.py tests/test_dead_asset.py`, and `.venv/Scripts/ruff.exe format --check src/rush/tools/dead_asset.py tests/test_dead_asset.py`; trace each unlink to all guards.
- **Evidence:** RED link, unlink guard trace, hashes, green outputs.
- **Stop:** Any guard can be bypassed or partial error silently deletes.
- **Verified outcome:** PR50.14.7 may start.

#### PR50.14.7 — RED: pin dead-asset registration and route migration

- **Task ID and binary outcome:** PR50.14.7; integration tests fail because complete tool is private and current routes return ad-hoc data.
- **Start goal:** Pin exact operations/options/routes.
- **Prerequisites:** PR50.1.4, PR50.F4, PR50.14.6.
- **Documentation impact:** None.
- **Dependency impact:** None.
- **Allowed writes:** tests/test_catalog.py; tests/test_cli_registry.py; tests/test_mcp.py; tests/test_phase50_slsa_attestation.py.
- **Allowed reads:** tool/current routes/registrars.
- **Prohibited:** Production/core/docs edits.
- **Actions:**
  1. Inspect current scanner routes/signatures.
  2. Add `test_dead_asset_catalog_declares_inventory_manifest_and_prune_options`, `test_dead_asset_cli_forwards_operations_and_artifact_permission`, and `test_dead_asset_mcp_uses_canonical_name_without_scanner_construction`; assert exact option specs, one object, audit/export/prune CLI arguments, canonical `rush_dead_asset`, permission forwarding, ToolResult equality, and no scanner construction.
  3. Run `.venv/Scripts/python.exe -m pytest tests/test_catalog.py::test_dead_asset_catalog_declares_inventory_manifest_and_prune_options tests/test_cli_registry.py::test_dead_asset_cli_forwards_operations_and_artifact_permission tests/test_mcp.py::test_dead_asset_mcp_uses_canonical_name_without_scanner_construction -q`, then `.venv/Scripts/python.exe -m pytest tests/test_catalog.py tests/test_cli_registry.py tests/test_mcp.py tests/test_phase50_slsa_attestation.py -q`; retain route or raw-result failures.
- **Evidence:** Integration RED results and signature matrix.
- **Stop:** Public operation undefined or core redesign required.
- **Verified outcome:** PR50.14.8 may start.

#### PR50.14.8 — GREEN: register dead-asset and remove transport scanning

- **Task ID and binary outcome:** PR50.14.8; one DeadAssetTool backs catalog, CLI, and MCP.
- **Start goal:** Satisfy integration only.
- **Prerequisites:** PR50.14.7 RED.
- **Documentation impact:** None.
- **Dependency impact:** None.
- **Allowed writes:** src/rush/tools/__init__.py; src/rush/catalog.py; src/rush/cli.py; src/rush/mcp.py.
- **Allowed reads:** integration tests/tool.
- **Prohibited:** Core/test/docs edits; unrelated routes.
- **Actions:**
  1. Reinspect registrars/current signature.
  2. Export/register one object and exact ToolSpec/options; replace CLI/MCP bodies with thin shared calls. `rush_dead_asset` is canonical normalized name.
  3. Run `.venv/Scripts/python.exe -m pytest tests/test_catalog.py::test_dead_asset_catalog_declares_inventory_manifest_and_prune_options tests/test_cli_registry.py::test_dead_asset_cli_forwards_operations_and_artifact_permission tests/test_mcp.py::test_dead_asset_mcp_uses_canonical_name_without_scanner_construction -q`, `.venv/Scripts/python.exe -m pytest tests/test_dead_asset.py tests/test_catalog.py tests/test_cli_registry.py tests/test_mcp.py tests/test_phase50_slsa_attestation.py -q`, `.venv/Scripts/ruff.exe check src/rush/tools/dead_asset.py src/rush/tools/__init__.py src/rush/catalog.py src/rush/cli.py src/rush/mcp.py tests/test_dead_asset.py tests/test_catalog.py tests/test_cli_registry.py tests/test_mcp.py tests/test_phase50_slsa_attestation.py`, and `.venv/Scripts/ruff.exe format --check src/rush/tools/dead_asset.py src/rush/tools/__init__.py src/rush/catalog.py src/rush/cli.py src/rush/mcp.py tests/test_dead_asset.py tests/test_catalog.py tests/test_cli_registry.py tests/test_mcp.py tests/test_phase50_slsa_attestation.py`; inspect transports for scanner or delete logic.
- **Evidence:** Object identity, route equality, green outputs.
- **Stop:** Duplicate behavior/object or raw return remains.
- **Verified outcome:** PR50.14.9 may start.

#### PR50.14.9 — DOCS: document the two-step prune protocol

- **Task ID and binary outcome:** PR50.14.9; audit states, manifest fields, deletion guards, and recovery responsibility are explicit.
- **Start goal:** Remove perfect-detection and safe-prune claims.
- **Prerequisites:** PR50.14.8 green.
- **Documentation impact:** Create docs/tools/dead_asset.md; correct public references.
- **Dependency impact:** None.
- **Allowed writes:** docs/tools/dead_asset.md; README.md; README2.md; README3.md; docs/AGENTIC_RUSH.md; docs/ARCHITECTURE.md; docs/developer/architecture.md; docs/CLI_REFERENCE.md; docs/MCP_REFERENCE.md; docs/CONFIGURATION.md; docs/TOOL_CATALOG.md; docs/SECURITY.md; examples/rush.toml.
- **Allowed reads:** src/rush/tools/dead_asset.py; tests/test_dead_asset.py; tests/test_catalog.py; tests/test_cli_registry.py; tests/test_mcp.py; the thirteen allowed documentation/configuration paths.
- **Prohibited:** Safe-prune guarantee, 100-percent identification, Git rollback, CSS-token claim.
- **Actions:**
  1. Inspect these exact active anchors and no others: the Pillar 9 and command-list entries in README.md, README2.md, and README3.md; the dead-asset tool row in docs/AGENTIC_RUSH.md; the Phase 50 tool entry in docs/ARCHITECTURE.md and docs/developer/architecture.md; the `dead-asset` entries in docs/CLI_REFERENCE.md, docs/MCP_REFERENCE.md, docs/CONFIGURATION.md, docs/TOOL_CATALOG.md, docs/SECURITY.md, and examples/rush.toml. Record the pre-edit claim at every changed anchor.
  2. Make this exact change only at those anchors and in the new guide: document referenced/candidate/uncertain states; audit/no-delete default; versioned manifest fields; hash/no-follow/rescan/permission guards; canonical route; and explicit backup/recovery responsibility. Replace safe-prune, perfect-detection, Git-rollback, and CSS/design-token claims; do not alter unrelated prose.
  3. Run `.venv/Scripts/python.exe -m pytest tests/test_dead_asset.py tests/test_phase50_slsa_attestation.py tests/test_catalog.py tests/test_cli_registry.py tests/test_mcp.py -q`; then run `rg -n "dead-asset|rush_dead_asset|100%|zero false|prune|manifest|uncertain" docs/tools/dead_asset.md README.md README2.md README3.md docs/AGENTIC_RUSH.md docs/ARCHITECTURE.md docs/developer/architecture.md docs/CLI_REFERENCE.md docs/MCP_REFERENCE.md docs/CONFIGURATION.md docs/TOOL_CATALOG.md docs/SECURITY.md examples/rush.toml` and record every remaining hit with its limitation or guarded-protocol context.
- **Evidence:** Tests and claim inventory.
- **Stop:** Candidate is portrayed as proven dead or deletion as recoverable.
- **Verified outcome:** Only D50-18-approved file-asset behavior is closed; CSS/design-token scope remains explicit.

### PR50.15 — I28 evidence-only PR synthesis — blocked by D50-18

#### PR50.15.1 — RED: expose fabricated quality and assurance claims

- **Task ID and binary outcome:** PR50.15.1; both direct rendering tests execute and fail only because observed Git/ToolResult evidence is not rendered with explicit missing states and no fabricated claims.
- **Start goal:** Pin a card that distinguishes observed Git/ToolResult evidence from unavailable evidence.
- **Prerequisites:** PR50.0.1 and explicit D50-18 disposition for I28.
- **Documentation impact:** None.
- **Dependency impact:** Git environment only.
- **Allowed writes:** Create tests/test_pr_synthesize.py only.
- **Allowed reads:** pr_synthesize.py; routes; roadmap I28; ToolResult; Git helpers; PR50.4/5 schemas.
- **Prohibited:** Live developer Git; GitHub API; reviewer invention; success badges; production/docs edits.
- **Actions:**
  1. Inspect synthesize_pr_card and enumerate every hardcoded claim. Capture current output using injected Git diff evidence.
  2. Make this exact change in only tests: add `test_pr_synthesize_renders_only_observed_evidence` with injected base/head/diff and supplied ToolResults containing warn, skipped, and unsigned_draft; instantiate tool directly; assert changed files/exact statuses/evidence IDs and absence of pass badge, Level, reviewer, coverage, blast, or risk claim. Add `test_pr_synthesize_missing_base_or_metric_is_explicit_not_success`; assert missing base skipped/error and absent metric says not supplied. Add no output/route assertions.
  3. Run `.venv/Scripts/python.exe -m pytest tests/test_pr_synthesize.py::test_pr_synthesize_renders_only_observed_evidence tests/test_pr_synthesize.py::test_pr_synthesize_missing_base_or_metric_is_explicit_not_success -q`, then `.venv/Scripts/python.exe -m pytest tests/test_pr_synthesize.py -q`; retain only direct rendering failures for hardcoded claims or missing-state handling. PR50.15.5 owns smoke/route migration.
- **Evidence:** False-output inventory, fixture results, named RED.
- **Stop:** Risk/reviewer formula is undefined, missing becomes success, or live API needed.
- **Verified outcome:** PR50.15.2 may start.

#### PR50.15.2 — GREEN: render only observed Git and ToolResult evidence

- **Task ID and binary outcome:** PR50.15.2; the private PrSynthesizeTool renders only the pinned observed evidence and missing-state markers; export and public registration remain absent.
- **Start goal:** Remove hardcoded verdicts in one private core that later integration cards can share across routes.
- **Prerequisites:** PR50.1.2, PR50.4.2, PR50.5.2, PR50.15.1 RED.
- **Documentation impact:** None.
- **Dependency impact:** None.
- **Allowed writes:** src/rush/tools/pr_synthesize.py only.
- **Allowed reads:** Git helpers; ToolResult; provenance/attribution schemas; registrars.
- **Prohibited:** Test/registry/route/docs/dependency/output edits; GitHub API; inferred reviewers/risk; unsupported badges.
- **Actions:**
  1. Inspect all callers. Fix exact inputs as base_ref, contained ToolResult JSON list, and optional output. Confirm no canonical source supplies reviewer ownership/risk formula; omit them.
  2. Make this exact change in only src/rush/tools/pr_synthesize.py: replace synthesizer with `PrSynthesizeTool` named `pr-synthesize`; use run_subprocess argv for verified base/diff; validate supplied ToolResult minimum fields; render only Changed files, Supplied quality evidence, Provenance status, Missing evidence, and Limitations; preserve statuses/unsigned_draft; missing base skipped/error; include no output/registry/transport code.
  3. Run `.venv/Scripts/python.exe -m pytest tests/test_pr_synthesize.py::test_pr_synthesize_renders_only_observed_evidence tests/test_pr_synthesize.py::test_pr_synthesize_missing_base_or_metric_is_explicit_not_success -q`, `.venv/Scripts/python.exe -m pytest tests/test_pr_synthesize.py -q`, `.venv/Scripts/ruff.exe check src/rush/tools/pr_synthesize.py tests/test_pr_synthesize.py`, and `.venv/Scripts/ruff.exe format --check src/rush/tools/pr_synthesize.py tests/test_pr_synthesize.py`; search templates for pass, verified, Level, reviewer, risk, or coverage claims and inspect Git argv.
- **Evidence:** PR50.15.1 RED link, claim search, private ToolFn identity, Git argv trace, and green commands.
- **Stop:** Statement lacks evidence, missing base falls back, or write is implicit.
- **Verified outcome:** PR50.15.3 may start; renderer core remains private.

#### PR50.15.3 — RED: pin permissioned contained PR Markdown export

- **Task ID and binary outcome:** PR50.15.3; export tests fail because renderer cannot write.
- **Start goal:** Pin artifact effect separately from evidence rendering.
- **Prerequisites:** PR50.1.6 and PR50.15.2.
- **Documentation impact:** None.
- **Dependency impact:** None.
- **Allowed writes:** tests/test_pr_synthesize.py only.
- **Allowed reads:** src/rush/tools/pr_synthesize.py; src/rush/permissions.py; src/rush/tools/common.py; tests/test_tool_common.py.
- **Prohibited:** Production/routes/docs edits; GitHub API.
- **Actions:**
  1. Inspect exact artifact helpers.
  2. Add `test_pr_synthesize_export_requires_artifact_permission`, `test_pr_synthesize_export_is_contained_atomic_and_deterministic`, and `test_pr_synthesize_export_preserves_existing_file_on_error`; assert denied no-write, explicit contained atomic output, deterministic rerun, escape/symlink rejection, replace-failure preservation, and exported Markdown byte equality with the result artifact text.
  3. Run `.venv/Scripts/python.exe -m pytest tests/test_pr_synthesize.py::test_pr_synthesize_export_requires_artifact_permission tests/test_pr_synthesize.py::test_pr_synthesize_export_is_contained_atomic_and_deterministic tests/test_pr_synthesize.py::test_pr_synthesize_export_preserves_existing_file_on_error -q`, then `.venv/Scripts/python.exe -m pytest tests/test_pr_synthesize.py -q`; retain absent-export failures.
- **Evidence:** Export RED results and hashes.
- **Stop:** Output encoding/path is undefined or helper cannot preserve old file.
- **Verified outcome:** PR50.15.4 may start.

#### PR50.15.4 — GREEN: add guarded PR Markdown export

- **Task ID and binary outcome:** PR50.15.4; export writes only observed Markdown with artifact permission.
- **Start goal:** Satisfy export tests only.
- **Prerequisites:** PR50.15.3 RED.
- **Documentation impact:** None.
- **Dependency impact:** None.
- **Allowed writes:** src/rush/tools/pr_synthesize.py only.
- **Allowed reads:** unchanged export tests/helpers.
- **Prohibited:** Test/routes/docs/GitHub changes.
- **Actions:**
  1. Reinspect assertions/helpers.
  2. Add optional output branch requiring artifact_write and contained atomic replace; write exactly rendered Markdown; preserve old file on error.
  3. Run `.venv/Scripts/python.exe -m pytest tests/test_pr_synthesize.py -q`, `.venv/Scripts/ruff.exe check src/rush/tools/pr_synthesize.py tests/test_pr_synthesize.py`, and `.venv/Scripts/ruff.exe format --check src/rush/tools/pr_synthesize.py tests/test_pr_synthesize.py`; trace writes and compare bytes.
- **Evidence:** RED link, hashes, write trace, green outputs.
- **Stop:** Export adds claims or implicit output.
- **Verified outcome:** PR50.15.5 may start.

#### PR50.15.5 — RED: pin pr-synthesize registration and route migration

- **Task ID and binary outcome:** PR50.15.5; integration tests fail because complete tool is private/current routes return raw Markdown.
- **Start goal:** Pin exact options and preserve `rush_pr_synthesize` as the canonical normalized route without a duplicate alias.
- **Prerequisites:** PR50.1.4, PR50.F4, PR50.15.4.
- **Documentation impact:** None.
- **Dependency impact:** None.
- **Allowed writes:** tests/test_catalog.py; tests/test_cli_registry.py; tests/test_mcp.py; tests/test_phase50_slsa_attestation.py.
- **Allowed reads:** tool/current routes/registrars.
- **Prohibited:** Production/core/docs edits.
- **Actions:**
  1. Inspect current signatures/raw returns.
  2. Add `test_pr_synthesize_catalog_declares_evidence_and_output_options`, `test_pr_synthesize_cli_forwards_base_evidence_output_and_permission`, and `test_pr_synthesize_mcp_uses_canonical_name_without_hardcoded_claims`; assert exact option specs, one object, CLI base/evidence/output arguments, canonical `rush_pr_synthesize`, permission forwarding, ToolResult equality, and no synthesizer construction/hardcoded claims in transports.
  3. Run `.venv/Scripts/python.exe -m pytest tests/test_catalog.py::test_pr_synthesize_catalog_declares_evidence_and_output_options tests/test_cli_registry.py::test_pr_synthesize_cli_forwards_base_evidence_output_and_permission tests/test_mcp.py::test_pr_synthesize_mcp_uses_canonical_name_without_hardcoded_claims -q`, then `.venv/Scripts/python.exe -m pytest tests/test_catalog.py tests/test_cli_registry.py tests/test_mcp.py tests/test_phase50_slsa_attestation.py -q`; retain integration or raw-result failures.
- **Evidence:** Route RED results and current false-claim inventory.
- **Stop:** Public arguments undefined or core redesign required.
- **Verified outcome:** PR50.15.6 may start.

#### PR50.15.6 — GREEN: register pr-synthesize and remove transport synthesis

- **Task ID and binary outcome:** PR50.15.6; one PrSynthesizeTool backs catalog, CLI, and MCP.
- **Start goal:** Satisfy integration only.
- **Prerequisites:** PR50.15.5 RED.
- **Documentation impact:** None.
- **Dependency impact:** None.
- **Allowed writes:** src/rush/tools/__init__.py; src/rush/catalog.py; src/rush/cli.py; src/rush/mcp.py.
- **Allowed reads:** integration tests/tool.
- **Prohibited:** Core/test/docs edits; unrelated routes.
- **Actions:**
  1. Reinspect registrars/current signature.
  2. Export/register one object and exact ToolSpec/options; replace CLI/MCP bodies with thin shared calls. `rush_pr_synthesize` is canonical normalized name.
  3. Run `.venv/Scripts/python.exe -m pytest tests/test_catalog.py::test_pr_synthesize_catalog_declares_evidence_and_output_options tests/test_cli_registry.py::test_pr_synthesize_cli_forwards_base_evidence_output_and_permission tests/test_mcp.py::test_pr_synthesize_mcp_uses_canonical_name_without_hardcoded_claims -q`, `.venv/Scripts/python.exe -m pytest tests/test_pr_synthesize.py tests/test_catalog.py tests/test_cli_registry.py tests/test_mcp.py tests/test_phase50_slsa_attestation.py -q`, `.venv/Scripts/ruff.exe check src/rush/tools/pr_synthesize.py src/rush/tools/__init__.py src/rush/catalog.py src/rush/cli.py src/rush/mcp.py tests/test_pr_synthesize.py tests/test_catalog.py tests/test_cli_registry.py tests/test_mcp.py tests/test_phase50_slsa_attestation.py`, and `.venv/Scripts/ruff.exe format --check src/rush/tools/pr_synthesize.py src/rush/tools/__init__.py src/rush/catalog.py src/rush/cli.py src/rush/mcp.py tests/test_pr_synthesize.py tests/test_catalog.py tests/test_cli_registry.py tests/test_mcp.py tests/test_phase50_slsa_attestation.py`; inspect transports for templates or claims.
- **Evidence:** Object identity, route equality, green outputs.
- **Stop:** Duplicate behavior/object or raw string remains.
- **Verified outcome:** PR50.15.7 may start.

#### PR50.15.7 — DOCS: document evidence inputs and missing states

- **Task ID and binary outcome:** PR50.15.7; evidence schema, missing states, write permission, routes, and no GitHub integration are exact.
- **Start goal:** Remove accurate-risk/reviewer/test-proof claims.
- **Prerequisites:** PR50.15.6 green.
- **Documentation impact:** Create docs/tools/pr_synthesize.md; correct public references.
- **Dependency impact:** None.
- **Allowed writes:** docs/tools/pr_synthesize.md; README.md; README2.md; README3.md; docs/AGENTIC_RUSH.md; docs/ARCHITECTURE.md; docs/developer/architecture.md; docs/CLI_REFERENCE.md; docs/MCP_REFERENCE.md; docs/CONFIGURATION.md; docs/TOOL_CATALOG.md; docs/SECURITY.md; examples/rush.toml.
- **Allowed reads:** src/rush/tools/pr_synthesize.py; tests/test_pr_synthesize.py; tests/test_catalog.py; tests/test_cli_registry.py; tests/test_mcp.py; the thirteen allowed documentation/configuration paths.
- **Prohibited:** GitHub upload/opening, accurate risk/reviewer routing, automatic test/coverage/blast/provenance claims.
- **Actions:**
  1. Inspect these exact active anchors and no others: the Pillar 9 and command-list entries in README.md, README2.md, and README3.md; the PR-synthesis tool row in docs/AGENTIC_RUSH.md; the Phase 50 tool entry in docs/ARCHITECTURE.md and docs/developer/architecture.md; the `pr-synthesize` entries in docs/CLI_REFERENCE.md, docs/MCP_REFERENCE.md, docs/CONFIGURATION.md, docs/TOOL_CATALOG.md, docs/SECURITY.md, and examples/rush.toml. Record the pre-edit claim at every changed anchor.
  2. Make this exact change only at those anchors and in the new guide: document the supplied ToolResult minimum schema, verified Git base/diff inputs, missing-evidence markers, `unsigned_draft` propagation, contained output permission, canonical CLI/MCP names, and no GitHub API. Replace inferred reviewer, risk, test, coverage, blast-radius, SLSA-level, and pass-badge claims; do not alter unrelated prose.
  3. Run `.venv/Scripts/python.exe -m pytest tests/test_pr_synthesize.py tests/test_phase50_slsa_attestation.py tests/test_catalog.py tests/test_cli_registry.py tests/test_mcp.py -q`; then run `rg -n "pr-synthesize|rush_pr_synthesize|reviewer|risk tier|SLSA|coverage|passed|GitHub API" docs/tools/pr_synthesize.md README.md README2.md README3.md docs/AGENTIC_RUSH.md docs/ARCHITECTURE.md docs/developer/architecture.md docs/CLI_REFERENCE.md docs/MCP_REFERENCE.md docs/CONFIGURATION.md docs/TOOL_CATALOG.md docs/SECURITY.md examples/rush.toml` and record every remaining hit with its explicit limitation or supplied-evidence context.
- **Evidence:** Tests and claim inventory.
- **Stop:** Documentation promotes inferred claims.
- **Verified outcome:** Only D50-18-approved observed-evidence behavior is closed; risk/reviewer/GitHub scope remains explicit.

### PR50.16 — Cross-feature parity and installed-artifact evidence

#### PR50.16.1 — VERIFY: prove one object per tool and preserve the explicit compatibility alias

- **Task ID and binary outcome:** PR50.16.1; all fourteen decision-dispositioned capability packets have registry, CLI, MCP, result-shape, typed-option, and compatibility parity, or verification stops on the exact mismatch.
- **Start goal:** Verify integration after individual GREEN cards without creating a new implementation workstream.
- **Prerequisites:** D50-04, D50-07, D50-08, and D50-10–D50-18 are completely dispositioned; every behavior/effect/integration card required by those dispositions is green; every required DOCS card is complete. A decision selecting behavior outside the currently authored packet requires an approved plan amendment before this task.
- **Documentation impact:** Record the parity matrix in docs/developer/phase-50-implementation-evidence.md.
- **Dependency impact:** None.
- **Allowed writes:** docs/developer/phase-50-implementation-evidence.md only.
- **Allowed reads:** TOOL_SPECS; ALL_TOOLS; cli.py command registry; build_server tool manager; every implemented Phase 50 ToolFn; config examples; deprecated alias wrappers.
- **Prohibited:** Production edits; converting a blocked feature into a placeholder; deleting `rush_attest_generate`; retaining duplicate canonical-name shims; weakening assertions to match current output.
- **Actions:**
  1. Inspect the exact fourteen-tool disposition from decision evidence and compare every admitted tool with TOOL_SPECS, ALL_TOOLS object identity, `CliRunner --help`, `build_server` names, typed option declarations, and the sole deprecated `rush_attest_generate` alias. Prove the other four historical underscore names are canonical registrations with no duplicate shim. Inspect transport source for `_run_tool`/registered-object calls only. Stop on the first missing per-feature integration test; do not create it here.
  2. Make this exact change in only the evidence file: write a fourteen-row matrix under `Route parity / PR50.16.1` containing requirement disposition, ToolFn/class/module, ToolSpec/options, ALL_TOOLS object identity, CLI routes, canonical underscore MCP route, compatibility alias, result-shape test, integration task, and command exit. Record nonselected subrequirements as approved deferred—not “implemented.”
  3. Run `.venv/Scripts/python.exe -m pytest tests/test_tool_common.py tests/test_prompt_eval.py tests/test_error_catalog.py tests/test_provenance_ai.py tests/test_attest.py tests/test_license_matrix.py tests/test_iam_audit.py tests/test_mem_profile.py tests/test_cold_start.py tests/test_media_opt.py tests/test_offline_review.py tests/test_tui_diff.py tests/test_benchmark.py tests/test_dead_asset.py tests/test_pr_synthesize.py tests/test_phase50_slsa_attestation.py tests/test_catalog.py tests/test_config.py tests/test_cli_registry.py tests/test_mcp.py -q`. Reinspect CLI/MCP source and record the exact matrix and exit.
- **Evidence:** Enumerated implemented-tool set, test output, route-source inspection, parity matrix.
- **Stop:** Any decision is open; a required feature test is absent; duplicate business logic, missing route/option, blocked placeholder, lost compatibility name, or noncanonical result exists. Return to the owning task or amend the plan; do not edit tests/production here.
- **Verified outcome:** PR50.16.2 may start.

#### PR50.16.2 — VERIFY: author installed-artifact acceptance probes

- **Task ID and binary outcome:** PR50.16.2; two acceptance tests prove wheel membership plus isolated installed CLI/MCP parity, or the task stops without changing package configuration.
- **Start goal:** Create the installed-artifact contract separately from evidence-file mutation. This is verification of existing package discovery, not a GREEN card and not authority to repair packaging.
- **Prerequisites:** PR50.16.1 green; all dependency decisions reflected in pyproject.toml and uv.lock.
- **Documentation impact:** None.
- **Dependency impact:** Verify only; no dependency addition or lock change.
- **Allowed writes:** Create tests/test_phase50_packaging.py; create ephemeral `.rush/phase50-dist`, `.rush/phase50-wheel-venv`, and `.rush/phase50-runtime-requirements.txt` during commands.
- **Allowed reads:** pyproject.toml; uv.lock; tests/test_phase50_packaging.py; built wheel ZIP; installed CLI/MCP outputs; PR50.16.1 evidence.
- **Prohibited:** Evidence-file, production, package-configuration, dependency, lock, version, or public-documentation edits; publishing/upload; testing docs as wheel package data; source-checkout imports during installed probes.
- **Actions:**
  1. Inspect only the package-discovery tables in pyproject.toml. From the implementation worktree run `Remove-Item Env:VIRTUAL_ENV -ErrorAction SilentlyContinue`; `Remove-Item Env:PYTHONPATH -ErrorAction SilentlyContinue`; `$phase50Worktree = (Resolve-Path .).Path`; `$phase50Dist = [System.IO.Path]::GetFullPath((Join-Path $phase50Worktree '.rush/phase50-dist'))`; `if (-not $phase50Dist.StartsWith($phase50Worktree + [System.IO.Path]::DirectorySeparatorChar, [System.StringComparison]::OrdinalIgnoreCase)) { throw "phase50-dist escaped worktree" }`; `Remove-Item -LiteralPath $phase50Dist -Recurse -Force -ErrorAction SilentlyContinue`; `uv build --out-dir $phase50Dist`; `$phase50Wheels = @(Get-ChildItem -LiteralPath $phase50Dist -Filter 'rush-*.whl' -File)`; `if ($phase50Wheels.Count -ne 1) { throw "expected exactly one Rush wheel" }`; `$phase50Wheel = $phase50Wheels[0].FullName`; `uv export --frozen --no-dev --no-emit-project --format requirements-txt --output-file .rush/phase50-runtime-requirements.txt`; `uv venv --clear .rush/phase50-wheel-venv`; `uv pip install --python .rush/phase50-wheel-venv/Scripts/python.exe --offline -r .rush/phase50-runtime-requirements.txt`; `uv pip install --python .rush/phase50-wheel-venv/Scripts/python.exe --offline --no-deps $phase50Wheel`. Stop on cache/network resolution failure; do not fall back to online resolution or source installation.
  2. Make this exact change in only tests/test_phase50_packaging.py: add `test_phase50_modules_are_present_in_built_wheel`, opening `RUSH_PHASE50_WHEEL` as a ZIP and asserting every PR50.16.1-implemented `rush/tools/*.py` module plus Rush package metadata is present; add `test_phase50_installed_cli_help_and_mcp_catalog_match_source_contract`, invoking only `RUSH_PHASE50_PYTHON`, removing the repository root from cwd/PYTHONPATH, asserting imported `rush.__file__` is under `.rush/phase50-wheel-venv`, obtaining CLI command names from the installed executable, starting the installed `rush mcp serve` through public MCP `stdio_client`/`ClientSession`, and comparing `list_tools()` with the fourteen-row disposition and sole deprecated `rush_attest_generate` alias. Do not inspect FastMCP private managers.
  3. Run `$env:RUSH_PHASE50_WHEEL = $phase50Wheel`; `$env:RUSH_PHASE50_PYTHON = (Resolve-Path .rush/phase50-wheel-venv/Scripts/python.exe).Path`; `.venv/Scripts/python.exe -m pytest tests/test_phase50_packaging.py::test_phase50_modules_are_present_in_built_wheel tests/test_phase50_packaging.py::test_phase50_installed_cli_help_and_mcp_catalog_match_source_contract -q`; `.venv/Scripts/python.exe -m pytest tests/test_phase50_packaging.py -q`; `.venv/Scripts/ruff.exe check tests/test_phase50_packaging.py`; `.venv/Scripts/ruff.exe format --check tests/test_phase50_packaging.py`; `git status --short`. Both tests must pass against the unchanged package configuration; a failure is amendment evidence, not an implementation RED.
- **Evidence:** Two named acceptance-test results, wheel member comparison, isolated interpreter path, public installed CLI/MCP lists, and one-file test diff.
- **Stop:** A module/route is absent, source checkout leaks through cwd/PYTHONPATH, a private FastMCP API is required, dependency install requires unapproved network resolution, or package configuration would need to change.
- **Verified outcome:** PR50.16.3 may independently reproduce and record installed-artifact evidence; no release action is authorized.

#### PR50.16.3 — EVIDENCE: independently reproduce and record installed-artifact behavior

- **Task ID and binary outcome:** PR50.16.3; an independently rebuilt wheel passes the unchanged PR50.16.2 acceptance tests and its identity/results are appended to the evidence file, or Phase 50 remains incomplete.
- **Start goal:** Keep final artifact evidence separate from test authoring and prohibit implementation repair inside the evidence task.
- **Prerequisites:** PR50.16.2 passes; tests/test_phase50_packaging.py unchanged after its recorded result.
- **Documentation impact:** Append only `Wheel evidence / PR50.16.3` to docs/developer/phase-50-implementation-evidence.md.
- **Dependency impact:** Verify only; no manifest or lock mutation.
- **Allowed writes:** docs/developer/phase-50-implementation-evidence.md; regenerate ephemeral `.rush/phase50-dist`, `.rush/phase50-wheel-venv`, and `.rush/phase50-runtime-requirements.txt`.
- **Allowed reads:** pyproject.toml; uv.lock; unchanged tests/test_phase50_packaging.py; built wheel ZIP; installed CLI/MCP outputs; PR50.16.1–PR50.16.2 evidence.
- **Prohibited:** Test, production, package-configuration, dependency, lock, version, or public-documentation edits; online fallback; source installation; publication/upload.
- **Actions:**
  1. From the same implementation revision run `Remove-Item Env:VIRTUAL_ENV -ErrorAction SilentlyContinue`; `Remove-Item Env:PYTHONPATH -ErrorAction SilentlyContinue`; `$phase50Worktree = (Resolve-Path .).Path`; `$phase50Dist = [System.IO.Path]::GetFullPath((Join-Path $phase50Worktree '.rush/phase50-dist'))`; `if (-not $phase50Dist.StartsWith($phase50Worktree + [System.IO.Path]::DirectorySeparatorChar, [System.StringComparison]::OrdinalIgnoreCase)) { throw "phase50-dist escaped worktree" }`; `Remove-Item -LiteralPath $phase50Dist -Recurse -Force -ErrorAction SilentlyContinue`; `uv build --out-dir $phase50Dist`; `$phase50Wheels = @(Get-ChildItem -LiteralPath $phase50Dist -Filter 'rush-*.whl' -File)`; `if ($phase50Wheels.Count -ne 1) { throw "expected exactly one Rush wheel" }`; `$phase50Wheel = $phase50Wheels[0].FullName`; `uv export --frozen --no-dev --no-emit-project --format requirements-txt --output-file .rush/phase50-runtime-requirements.txt`; `uv venv --clear .rush/phase50-wheel-venv`; `uv pip install --python .rush/phase50-wheel-venv/Scripts/python.exe --offline -r .rush/phase50-runtime-requirements.txt`; `uv pip install --python .rush/phase50-wheel-venv/Scripts/python.exe --offline --no-deps $phase50Wheel`.
  2. Run `$env:RUSH_PHASE50_WHEEL = $phase50Wheel`; `$env:RUSH_PHASE50_PYTHON = (Resolve-Path .rush/phase50-wheel-venv/Scripts/python.exe).Path`; `.venv/Scripts/python.exe -m pytest tests/test_phase50_packaging.py -q`; `.rush/phase50-wheel-venv/Scripts/rush.exe --version`; `.rush/phase50-wheel-venv/Scripts/rush.exe --help`; `Get-FileHash -Algorithm SHA256 -LiteralPath $phase50Wheel`; `git status --short`. Capture the exact wheel filename, SHA-256, ZIP-member assertion, isolated interpreter/import path, CLI commands, MCP names, test exits, and dirty paths.
  3. Make this exact change in only docs/developer/phase-50-implementation-evidence.md: append the captured values and literal command/exit ledger beneath `Wheel evidence / PR50.16.3`; state that no source checkout path, online dependency resolution, package-config edit, or release action was used.
- **Evidence:** Independent wheel filename/SHA-256, ZIP-member assertion, isolated import path, public CLI/MCP lists, commands/exits, and evidence-only diff.
- **Stop:** Any command/test fails; test bytes changed after PR50.16.2; source checkout leaks; package/dependency configuration differs; an online fallback or implementation correction is requested.
- **Verified outcome:** The final verification gate may start; no release action is authorized.

## Final verification and delivery gate

### PR50.17 — HANDOFF: run the exact phase gate and freeze evidence

- **Task ID and binary outcome:** PR50.17; every approved Phase 50 disposition, repository-quality gate, documentation correction, and installed-artifact probe passes at one recorded revision, or Phase 50 remains incomplete.
- **Start goal:** Produce one reproducible implementation-completion record without committing, tagging, publishing, or calling the phase released.
- **Prerequisites:** PR50.16.3; every decision D50-04 and D50-07 through D50-18 fully resolved; every task required by the selected dispositions complete; no omitted feature test.
- **Documentation impact:** Finalize docs/developer/phase-50-implementation-evidence.md only.
- **Dependency impact:** Verify pyproject.toml/uv.lock consistency; change neither.
- **Allowed writes:** docs/developer/phase-50-implementation-evidence.md; ignored ephemeral .rush/phase50-dist, .rush/phase50-wheel-venv, and .rush/phase50-runtime-requirements.txt may be regenerated.
- **Allowed reads:** All task-owned changed files; git diff/status; test/lint/format/build outputs; decision evidence.
- **Prohibited:** Production/test/doc/dependency corrections; commits, branches, merges, tags, pushes, release/version/changelog changes, uploads, publication, deployment, hooks, history edits.
- **Actions:**
  1. Inspect git diff --name-only and mechanically map every changed path to exactly one completed task. Inspect git diff --check and git status --short --branch. Stop on any unowned path, blocked-feature implementation, or unresolved merge marker.
  2. Make this exact change in only the evidence file: add the final revision, implemented-tool enumeration, blocked/deferred enumeration, path-to-task ownership table, dependency/lock disposition, documentation claim-search results, wheel SHA-256, and every command/exit below. Do not edit implementation to make a gate pass.
  3. Run these literal PowerShell commands in order: `Remove-Item Env:VIRTUAL_ENV -ErrorAction SilentlyContinue`; `Remove-Item Env:PYTHONPATH -ErrorAction SilentlyContinue`; `.venv/Scripts/python.exe --version`; `.venv/Scripts/python.exe -m pytest tests/test_tool_common.py tests/test_prompt_eval.py tests/test_error_catalog.py tests/test_provenance_ai.py tests/test_attest.py tests/test_license_matrix.py tests/test_iam_audit.py tests/test_mem_profile.py tests/test_cold_start.py tests/test_media_opt.py tests/test_offline_review.py tests/test_tui_diff.py tests/test_benchmark.py tests/test_dead_asset.py tests/test_pr_synthesize.py tests/test_phase50_slsa_attestation.py -q`; `.venv/Scripts/python.exe -m pytest tests/test_catalog.py tests/test_config.py tests/test_cli_registry.py tests/test_mcp.py -q`; `.venv/Scripts/python.exe -m pytest tests/ --ignore=tests/test_phase50_packaging.py -q`; `.venv/Scripts/ruff.exe check src tests scripts`; `.venv/Scripts/ruff.exe format --check src tests scripts`; `uv lock --check`; `$phase50Worktree = (Resolve-Path .).Path`; `$phase50Dist = [System.IO.Path]::GetFullPath((Join-Path $phase50Worktree '.rush/phase50-dist'))`; `if (-not $phase50Dist.StartsWith($phase50Worktree + [System.IO.Path]::DirectorySeparatorChar, [System.StringComparison]::OrdinalIgnoreCase)) { throw "phase50-dist escaped worktree" }`; `Remove-Item -LiteralPath $phase50Dist -Recurse -Force -ErrorAction SilentlyContinue`; `uv build --out-dir $phase50Dist`; `$phase50Wheels = @(Get-ChildItem -LiteralPath $phase50Dist -Filter 'rush-*.whl' -File)`; `if ($phase50Wheels.Count -ne 1) { throw "expected exactly one Rush wheel" }`; `$phase50Wheel = $phase50Wheels[0].FullName`; `uv export --frozen --no-dev --no-emit-project --format requirements-txt --output-file .rush/phase50-runtime-requirements.txt`; `uv venv --clear .rush/phase50-wheel-venv`; `uv pip install --python .rush/phase50-wheel-venv/Scripts/python.exe --offline -r .rush/phase50-runtime-requirements.txt`; `uv pip install --python .rush/phase50-wheel-venv/Scripts/python.exe --offline --no-deps $phase50Wheel`; `$env:RUSH_PHASE50_WHEEL = $phase50Wheel`; `$env:RUSH_PHASE50_PYTHON = (Resolve-Path .rush/phase50-wheel-venv/Scripts/python.exe).Path`; `.venv/Scripts/python.exe -m pytest tests/test_phase50_packaging.py -q`; `.rush/phase50-wheel-venv/Scripts/rush.exe --version`; `.rush/phase50-wheel-venv/Scripts/rush.exe --help`; `Get-FileHash -Algorithm SHA256 -LiteralPath $phase50Wheel`; `git diff --check`; `git diff --name-only`; `git status --short --branch`.
- **Evidence:** One timestamped command ledger at one revision; exact omissions tied to blockers; changed-path ownership; wheel identity; no-release statement.
- **Stop:** Any command fails; any skip/XFAIL/XPASS replaces an ordinary required assertion; any blocked feature is presented as implemented; any unowned path appears; any lifecycle action is requested.
- **Verified outcome:** Phase 50 implementation evidence is complete only for every approved requirement disposition; the phase remains `Blocked` or `Incomplete` if any decision/task/gate is open. Release execution remains separate and unauthorized.

## Exit checklist and successor evidence

This checklist summarizes evidence produced by tasks; it does not create work.

- [ ] PR50.0.1 records an accepted non-main baseline and every initial failure/path classification.
- [ ] D50-04, D50-07, D50-08, and D50-10–D50-18 are fully resolved with exact values and successor owners; an explicitly blocked decision prevents PR50.16/17 and Phase 50 completion.
- [ ] PR50.1 proves undeclared config keys are rejected, declared values are preserved, and all permissioned artifact/store effects use the shared contained atomic-output helper proven by tests/test_tool_common.py.
- [ ] Every implemented feature has its named ordinary RED evidence, unchanged contract assertions, focused GREEN output, parity output, exact DOCS search, and task-owned changed paths.
- [ ] PR50.5 evidence shows an actual artifact subject, Statement v1, provenance v1, unsigned_draft, and no stronger assurance.
- [ ] PR50.6/7/15 evidence contains no invented license, IAM, reviewer, risk, quality, or provenance conclusion.
- [ ] PR50.10/14 evidence proves denied/no-write behavior and contained explicit writes; PR50.14 deletion additionally proves manifest, hash, rescan, and uncertainty guards.
- [ ] PR50.16.1 enumerates registry/CLI/MCP/config/alias parity for the implemented tool set and proves transports contain no Phase 50 business implementation.
- [ ] PR50.16.2 adds unchanged installed-artifact acceptance probes; PR50.16.3 independently records wheel identity and isolated installed CLI/MCP/module parity without source-tree leakage.
- [ ] PR50.17 records every exact gate at one revision, all changed paths have one task owner, and no commit/tag/publish/release action occurred.
- [ ] Successor handoff states that the repository-remediation provenance phase may consume only the unsigned draft and may not claim signature, SLSA level, reproducibility, completeness, or trusted builder evidence.
