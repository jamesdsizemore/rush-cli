# Rush Context Intelligence & Ship-Readiness Phase Implementation Plans

This directory contains the 10 self-contained, TDD-driven, version-aware implementation plans corresponding to the roadmap defined in [docs/rush-token-innovation-enhancement-report-plan.md](../rush-token-innovation-enhancement-report-plan.md).

Each plan is fully executable without needing to read external documents and includes exact file boundaries, TDD task lists, failure/error codes, worktree procedures, and validation checklists.

---

## Master Phase Sequencing & Index

| Phase ID | File Link | Focus Area | Key Features & Commands | Prereqs | Deliverables / Artifacts |
|---|---|---|---|---|---|
| **Phase 41** (PHASE-41) | [phase-41-foundations-bpe-distillers-base-ship-plan.md](./phase-41-foundations-bpe-distillers-base-ship-plan.md) | Foundations, BPE & Distillers | T01, T02, M01, M02, M03, S01, S02, S05 (
ush ship clean/env/docs) | Baseline | src/rush/token_economy/router.py, src/rush/token_economy/distillers/, src/rush/memory/ |
| **Phase 42** (PHASE-42) | [phase-42-toon-ast-skeletons-ship-gate-plan.md](./phase-42-toon-ast-skeletons-ship-gate-plan.md) | TOON, AST Skeletons & Ship Gate | T03, T04, M04, S03, S04, S06, S07 (
ush ship gate, --format toon) | Phase 01 | src/rush/token_economy/toon/, src/rush/token_economy/ast_skeletonizer.py, src/rush/tools/ship/cockpit.py |
| **Phase 43** (PHASE-43) | [phase-43-ccr-grounding-mistake-memory-plan.md](./phase-43-ccr-grounding-mistake-memory-plan.md) | CCR Reversibility & Mistake Memory | T05, T06, I02, M05, M06, M07 (
ush context retrieve, 
ush hallu-guard) | Phase 02 | src/rush/token_economy/ccr_store.py, src/rush/codegraph/grounding_verifier.py, src/rush/memory/mistake_miner.py |
| **Phase 44** (PHASE-44) | [phase-44-context-pack-prompt-cache-alignment-plan.md](./phase-44-context-pack-prompt-cache-alignment-plan.md) | Graph Context Packing & KV Cache | T07, T08, I01 (
ush context pack, TokenTamer, Cache Aligner) | Phase 03 | src/rush/codegraph/context_packer.py, src/rush/token_economy/stale_sweeper.py, src/rush/token_economy/cache_aligner.py |
| **Phase 45** (PHASE-45) | [phase-45-gain-tui-telemetry-terse-persona-plan.md](./phase-45-gain-tui-telemetry-terse-persona-plan.md) | Context Gain TUI & Telemetry | T09, T10 (
ush context gain, 
ush context persona, Telemetry Ledger) | Phase 04 | src/rush/token_economy/telemetry.py, src/rush/token_economy/tui_gain.py, src/rush/token_economy/output_shaper.py |
| **Phase 46** (PHASE-46) | [phase-46-blast-radius-architecture-guard-plan.md](./phase-46-blast-radius-architecture-guard-plan.md) | Blast Radius & Architecture Guard | I03, I04 (
ush blast-radius, 
ush arch-guard, [architecture.layers]) | Phase 05 | src/rush/tools/blast_radius.py, src/rush/tools/arch_guard.py |
| **Phase 47** (PHASE-47) | [phase-47-test-heal-api-diff-plan.md](./phase-47-test-heal-api-diff-plan.md) | Flaky Test Healer & API Differ | I05, I06 (
ush test-heal, 
ush api-diff, GitSandbox Worktrees) | Phase 06 | src/rush/core/git_sandbox.py, src/rush/tools/test_heal.py, src/rush/tools/api_diff.py |
| **Phase 48** (PHASE-48) | [phase-48-db-drift-simplify-strictify-plan.md](./phase-48-db-drift-simplify-strictify-plan.md) | DB Schema Drift & Decomposer | I07, I08, I09 (
ush db-drift, 
ush simplify, 
ush strictify) | Phase 07 | src/rush/tools/db_drift.py, src/rush/tools/simplify.py, src/rush/tools/strictify.py |
| **Phase 49** (PHASE-49) | [phase-49-traceability-flight-recorder-swarm-merge-plan.md](./phase-49-traceability-flight-recorder-swarm-merge-plan.md) | Multi-Agent Mesh & Swarm Merge | I10, I11, I12, I23, I25 (
ush trace, 
ush flight-recorder, 
ush swarm-merge, Mesh Daemon) | Phase 08 | src/rush/tools/trace.py, src/rush/tools/flight_recorder.py, src/rush/tools/swarm_merge.py, src/rush/mcp_mesh/ |
| **Phase 50** (PHASE-50) | [phase-50-slsa-attestation-security-suite-flagship-plan.md](./phase-50-slsa-attestation-security-suite-flagship-plan.md) | SLSA Attestation & Security Suite | I13–I22, I24, I26–I28 (
ush attest, 
ush license-matrix, 
ush iam-audit, 
ush pr-synthesize) | Phase 09 | Complete security, compliance, offline ONNX review runtime, and v0.3.0 Flagship Release |

---

## Architectural Guardrails
1. **Hybrid Dual-Engine Graph Foundation**: Every phase honors [ADR-0048](../adr/0048-hybrid-dual-engine-architecture-graft-and-codegraph.md), querying **Graft** for whole-repo macroscopic reachability and **CodeGraph** for in-process microscopic AST property trees with zero feature degradation.
2. **Strict File Boundaries**: Every phase explicitly isolates modified files, newly created files, and read-only subsystems.
3. **Red-Green-Refactor TDD**: Every implementation task begins with a failing unit/contract test before touching production code.
4. **Mandatory Documentation Synchronization**: Every phase concludes with scripts/sync_docs.py --update and scripts/sync_docs.py --check across all documentation files.
