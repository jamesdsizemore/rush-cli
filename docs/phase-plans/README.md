# Rush Phase Implementation Plans

This directory is the numbered, self-contained, TDD-driven implementation-plan cycle for Rush.

- Phases 41-50 implement the roadmap in [`docs/rush-token-innovation-enhancement-report-plan.md`](../rush-token-innovation-enhancement-report-plan.md).
- Phases 51-60 continue the cycle with the correctness and security program governed by [`docs/developer/repository-remediation-plan.md`](../developer/repository-remediation-plan.md).
- Phases 61-63 continue memory development: typed-artifact foundations, integration into existing tools, then expanded memory capabilities and vibecoder workflows. Phase 63 is planned; its implementation is not claimed complete.
- Phases 64-66 continue with runtime correctness, one-command installation and complete project/agent workflows, then the required interactive TUI and per-project local web application. All three are planned, not implemented. The [whole-application review](../reports/phase-64-66-application-review.md) is their finding and coverage ledger.

Each phase plan defines its authority, prerequisites, outcomes, exact writes, tests, dependencies, documentation work, stop conditions, verification, and successor handoff. A plan does not authorize implementation lifecycle actions such as committing, merging, publishing, or releasing.

**Historical remediation-plan status:** Phases 51 through 60 and findings R-001 through R-016 were recorded completed in their original evidence. Those records are not a current whole-product readiness verdict. The Phase 64–66 review at `997b56e` identifies additional defects and missing user routes; its findings remain open until implementation evidence closes them.

## Master phase sequencing and index

| Phase | Plan | Focus | Prerequisites | Exit artifact |
|---|---|---|---|---|
| 41 | [Foundations, BPE, distillers, base ship](./phase-41-foundations-bpe-distillers-base-ship-plan.md) | Token/memory/ship foundations | Baseline | Foundation tools and contracts |
| 42 | [TOON, AST skeletons, ship gate](./phase-42-toon-ast-skeletons-ship-gate-plan.md) | Serialization, skeletons, ship gate | Phase 41 | TOON and ship-gate surfaces |
| 43 | [CCR, grounding, mistake memory](./phase-43-ccr-grounding-mistake-memory-plan.md) | Reversibility and grounded memory | Phase 42 | CCR/grounding/memory contracts |
| 44 | [Context pack and prompt-cache alignment](./phase-44-context-pack-prompt-cache-alignment-plan.md) | Context packing and cache alignment | Phase 43 | Context and cache tools |
| 45 | [Gain TUI, telemetry, terse persona](./phase-45-gain-tui-telemetry-terse-persona-plan.md) | Telemetry and output shaping | Phase 44 | Gain and telemetry surfaces |
| 46 | [Blast radius and architecture guard](./phase-46-blast-radius-architecture-guard-plan.md) | Architecture analysis | Phase 45 | Blast-radius and guard tools |
| 47 | [Test healing and API diff](./phase-47-test-heal-api-diff-plan.md) | Test/API change analysis | Phase 46 | Test-heal and API-diff tools |
| 48 | [DB drift, simplify, strictify](./phase-48-db-drift-simplify-strictify-plan.md) | Drift and decomposition | Phase 47 | DB/type/complexity tools |
| 49 | [Traceability, recorder, swarm merge](./phase-49-traceability-flight-recorder-swarm-merge-plan.md) | Trace and coordination | Phase 48 | Trace/mesh/merge tools |
| 50a | [Polyglot quality catalog](./phase-50a-polyglot-quality-catalog-plan.md) | Error catalog, license matrix, IAM audit | Phase 49 | Static quality tools (41 catalog tools) |
| 50b | [Attribution, PR evidence, workspace hygiene](./phase-50b-attribution-pr-evidence-plan.md) | AI attribution, dead asset, PR synthesis | Phase 50a | Evidence & hygiene tools (44 catalog tools) |
| 50c | [Performance profiling & honest provenance](./phase-50c-performance-profiling-provenance-plan.md) | Profiling, cold start, benchmark, attest | Phase 50b | Phase 41-50 cycle completion (49 catalog tools) |
| 51 | [Remediation scope and release gates](./phase-51-remediation-scope-release-gates-plan.md) | Coverage/operation/engine manifests and release-gate ownership | Phase 50c complete | Auditable remediation baseline |
| 52 | [Packaging, artifacts, and version](./phase-52-packaging-artifact-version-contract-plan.md) | R-001 and R-012 | Phase 51 | One installed namespace/version source |
| 53 | [Sanitization and diagnostics](./phase-53-sanitization-diagnostics-write-boundaries-plan.md) | R-002 and R-008 | Phase 51 | Secret-safe output/write boundary |
| 54 | [ToolResult schema kernel](./phase-54-tool-result-schema-kernel-plan.md) | R-011 schema foundation | Phase 53 | ToolResultV1/FindingV1 adapters |
| 55 | [AtomicFile and containment](./phase-55-atomic-file-physical-containment-plan.md) | Shared persistence prerequisite | Phase 53 | Fail-closed atomic writer/verifier |
| 56 | [Content-addressed plugin trust](./phase-56-content-addressed-plugin-trust-plan.md) | R-003 | Phases 53-55 | Approved immutable bytes or no child |
| 57 | [Invocation, scope, cache, and egress](./phase-57-invocation-scope-operations-cache-egress-plan.md) | R-004 through R-007 | Phases 52-54 | Semantic parity and truthful egress |
| 58 | [Locks, persistence, and patch verification](./phase-58-lock-persistence-patch-fail-closed-plan.md) | R-009-R-011 and R-016 | Phases 53-57 | Fail-closed state and output migration |
| 59 | [Provenance and engine conformance](./phase-59-provenance-engine-conformance-plan.md) | R-013 and R-014 | Phases 52-54 | Truthful provenance/engine evidence |
| 60 | [Maintainability hotspot reduction](./phase-60-maintainability-hotspot-reduction-plan.md) | R-015 non-release program | Release-ready Phases 52-59 | Completed: Remediation-program completion (all 26 tests passed) |
| 61 | [Cross-LLM memory typed-artifact schema, trust tiers, transport dispatcher](./phase-61-cross-llm-memory-typed-artifact-schema-plan.md) | Roadmap phase — unified `TypedArtifactStore`, 4-tier trust taxonomy, ADR-0049 | Phase 60 | Completed: unified memory store, `MemoryTool`, all 39 tests passed (not an `R-xxx` finding) |
| 62 | [Cross-LLM memory integration layer](./phase-62-memory-integration-layer-plan.md) | Roadmap phase — wires `TypedArtifactStore` into cache, review, maintenance, handoff, attribution, and API-diff staleness; per-type expiry; decision-record schema | Phase 61 | Completed: 6 subsystems integrated, per-type expiry, `DecisionRecordFields`, all 26 tests passed (not an `R-xxx` finding) |
| 63 | [Memory capabilities and vibecoder integrations](./phase-63-memory-capabilities-vibecoder-plan.md) | Roadmap continuation — bounded recall, connected evidence, verified repair/intent/recipe workflows, receiver read-back and comparative benchmarks | Developed Phases 61/62; current inherited baseline verified by MC00 | Planned: 20 requirements, 16 workstreams and 80 tasks; MC15 owns reviewed implementation and benchmark handoff |
| 64 | [Runtime correctness and safe execution](./phase-64-runtime-correctness-and-safe-execution-plan.md) | Recursive documentation coverage; safe fixes/patches, real engines, correct analytics and executable gates | Reviewed developed baseline; repairs precede dependent Phase 63 work | Planned: P64-00–20; reviewed runtime evidence |
| 65 | [Project provisioning, scans and agent workflow](./phase-65-project-provisioning-scan-and-agent-workflow-plan.md) | One-command cross-platform installation, all detected agent integrations, managed toolchains, full scan, aggregate, handoff, verified rescan and scoped evidence | Phases 64 and 63 | Planned: P65-01–10; installed end-to-end evidence |
| 66 | [Interactive TUI and local web application](./phase-66-interactive-tui-and-local-web-plan.md) | Interactive project map; neon TUI/dashboard with integrated motion; per-repo overview, results, memory, tokens, Git and all outputs | Phase 65 shared workflows | Planned development: P66-01–07; actual terminal/browser acceptance |

## Remediation-cycle continuity

1. `docs/developer/repository-remediation-plan.md` remains the cross-phase authority for findings, locked decisions, release gates, and completion definitions.
2. Remediation Phase 0 maps to repository Phase 51; remediation Phases 1-9 map one-to-one to repository Phases 52-60.
3. A phase starts only after its prerequisite evidence exists. Parallel execution is allowed only where prerequisites permit it.
4. Each requirement, write path, test, documentation change, dependency decision, and handoff has one owning phase. A newly discovered write requires an approved plan amendment.
5. Release readiness required Phases 52-59 and every Phase 51 release gate. Phase 60 (maintainability hotspot reduction) is now completed, achieving 100% remediation-program completion.
6. The governing remediation roadmap and adversarial-review artifact are protected planning evidence, not implementation scratch files.

### Remediation finding ownership

| Finding or prerequisite | Owning phase |
|---|---|
| Scope, operation, engine, and failing-gate manifests | Phase 51 (Completed) |
| R-001, R-012 | Phase 52 (Completed) |
| R-002, R-008 | Phase 53 (Completed) |
| R-011 schema kernel | Phase 54 (Completed) |
| Shared AtomicFile/containment/verifier prerequisite | Phase 55 (Completed) |
| R-003 | Phase 56 (Completed) |
| R-004 through R-007 | Phase 57 (Completed) |
| R-009, R-010, R-016, and R-011 runtime migration | Phase 58 (Completed) |
| R-013, R-014 | Phase 59 (Completed) |
| R-015 | Phase 60 (Completed) |

## Memory-cycle continuity

[Phase 63](phase-63-memory-capabilities-vibecoder-plan.md) extends Phase 61's typed-memory foundation and Phase 62's integrations. Its MC00–MC15 identifiers denote workstreams within Phase 63; MC00.1–MC15.5 denote individual tasks. They are not additional phases. The plan's continuation table maps predecessor contracts to their owning Phase 63 workstreams.

Existing Phase 61/62 evidence remains a record of its original revision. Phase 63 starts from the developed source and checks its inherited baseline before dependent changes. Its [benchmark strategy](../reports/memory-capabilities-benchmark-strategy.md) combines established public workloads with Rush-specific behavioral scenarios. Planning status does not imply implementation or measured improvement.

## Product-continuation execution order

The execution DAG is **Phase 64 → Phase 63 → Phase 65 → Phase 66**. Phase numbers record continuation planning order; newly found unsafe baseline behavior must be repaired before the already-planned memory expansion consumes it. Phase 63's MC00–MC15 and 80 tasks keep their existing identities. Phase 65 composes that memory work with provisioning, complete scanning and agent remediation. Phase 66 supplies both full interfaces without duplicating backend behavior.

Each packet's exact task IDs, files, RED fixtures, expected results and completion gates are in its owning plan. P65-10 is the final install integration packet and executes after P65-05; artifact production P65-01 closes independently. No plan's existence, structural review or historical test count proves product implementation or readiness.

Phase 65 separates global installation for the OS user account from selecting, adding, configuring or creating projects, including choosing a project later. P64-00 implements recursive documentation validation and corrects current references throughout `docs/`; subsequent packets update their documented behavior alongside working code. Phase 66 implements the interactive project-map opening view, neon blue/pink/purple palette and integrated motion through named source changes and behavioral tests; P66-02 owns the map renderer and its transitions.

## Architectural guardrails

1. **Repository navigation:** Follow repository instructions for Graft and CodeGraph before broad source inspection.
2. **Strict write ownership:** Every phase distinguishes new files, existing authorized writes, protected files, and read-only discovery.
3. **Genuine TDD:** Behavior changes begin with a named failing contract test whose failure proves the missing contract, followed by the smallest production change and broader regression gate.
4. **Documentation synchronization:** Each phase names exact documentation files and required content. Do not rely on an undocumented or nonexistent bulk synchronization command.
5. **Installed evidence:** Source-tree green tests never substitute for the installed wheel/sdist, transport, engine, security, and release gates owned by the remediation cycle.
