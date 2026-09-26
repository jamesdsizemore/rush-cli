# Phase 70 adversarial plan review

Status: **WITHDRAWN — incomplete user-scope coverage.** The historical READY verdict below was invalidated by omitted UX/TUI outcomes. Preserve the technical findings as history, not current approval. Current scope correction and review: [ux-reconciliation.md](ux-reconciliation.md). No implementation or acceptance is claimed by this historical receipt.

Date: 2026-09-23.

## Subject and scope

- Plan: [phase-70-agent-adoption-and-usability-plan.md](../../docs/phase-plans/phase-70-agent-adoption-and-usability-plan.md).
- Final plan SHA-256: `5017d33081e90b0abac08e9c0417b2d0cccd88f4a6a713e44bb51a4df7b82212`.
- Original plan SHA-256: `c05eaec114aac07dfe647118ddebe355f12ebe18ae66a987eb7596e321b6da15`; exact preserved copy: [original-plan.md](original-plan.md).
- Repository HEAD: `ddc064117e971b48e29100004052e876e456faf2`, branch `phase/69-dashboard-tui-contract-remediation`.
- Review changes: named plan, this receipt, and original snapshot only. No application code, tests, user configuration, actual host installation, hook activation, database cleanup, release version, or commit changed.

Existing modified AGENTS.md (7 additions/7 deletions), untracked named plan, and untracked src/rush/tools/.rush/ were present at entry. AGENTS.md and stray state were preserved. The original plan was untracked, so ordinary git diff does not show its changes; explicit subject reads/hashes and original snapshot provide that comparison.

User authorized resolving seven product decisions and using current official Claude Code/Cursor/Codex documentation. All 25 tasks and four workstreams remain; no host, engine, memory, setup, safety, recovery, or acceptance requirement was removed. Review applied the adversarial-plan-review skill and repository task-block template. No implementation authorization was inferred.

## Review organization and frozen passes

| Reviewer | Model / effort | Bounded ownership and independent coverage |
|---|---|---|
| adoption_audit | GPT-6 Astra / high | Original W1/native MCP integration; rotated W3/W4 and dependencies; final W3/W4 plus corrected W1 consent/schema/hook boundaries. |
| results_audit | GPT-6 Astra / high | Original W2 invocation, engine/result contracts, permissions and recovery; follow-up security-input and retrieval source verification. |
| memory_setup_audit | GPT-6 Sol / high | Original W3/W4 memory/setup/status; actual writer trace; rotated W2; final W2 correction attack. |
| Parent orchestrator | Current parent model | Decisions, exact plan edits, W1 and whole-document consistency, cross-task dependencies, source/official-source reconciliation, scope and final artifact verification. |

Reviewers remained read-only. Parent was sole plan writer. A request for another results_audit turn encountered an agent-thread limit; rotation continued through the existing other two reviewers and parent, without representing the unavailable turn as completed.

Original audit established defects against original hash. Pass B independently re-derived adjacent lanes on `fce85acda441ecf49804b2e914141f52606bda1d63203b648513963f0a0b3c74`. Correction attack C used `3cf1f65a35216640a366987768ad945ba26fb234120a124247f1278cab7ce612`; additional defects were integrated. That verdict was explicitly invalidated when bytes changed. The intermediate `e039550696bc949b30ca12eb670c585d2927f5e0c801065bfee9d6615c2df36a` received no readiness claim.

Both active final reviewers rechecked unchanged `5017d33081e90b0abac08e9c0417b2d0cccd88f4a6a713e44bb51a4df7b82212` after reading corrections and returned READY for their lanes. Parent final review found no remaining plan blocker. Original results review, rotated result review, rotated memory/onboarding review, W1 review and parent integration review together cover the whole subject; no narrow lane is presented as whole-product acceptance.

## Complete task coverage and finding closure

Each row covers task logic, dependencies, concrete files, actual runtime boundaries, adversarial/failure cases, test-first checks and completion semantics. “Closed” means repaired specification verified on final hash, not fixed production code.

| Task | Defect or ambiguity resolved; final acceptance anchor | State |
|---|---|---|
| T1 | Install chain lacked agent usage guidance. Canonical packaged skill, real core/full examples, trigger/permission/result semantics and arbitrary-cwd installed-resource checks. Contributor skills remain distinct. | Closed |
| T2 | Generic plugin assumption replaced with all three native manifest/install/trust routes, wheel/sdist/frozen assets, upgrade/duplicate-registration recovery. Auto-loaded hook assets remain inert until host/project opt-in. Actual host acceptance required. | Closed |
| T3 | Missing independent guidance consent/disconnect, destructive replacement and rollback races. Exact diff/digest, scoped owned resources, shared references, CAS compensation, concurrent-edit preservation and failed native installation fixtures. | Closed |
| T4 | Stale 53-tool premise and missing status/check. Current 79-name baseline retained; explicit seven-name core for new registrations, legacy full default, real shared new tools, restricted receiver cannot widen. | Closed |
| T5 | False universal path/skipped/engine guarantees. Descriptions and initialization follow actual scope, grants, partial steps, external-provider limits and executable examples. | Closed |
| T6 | Opaque request dictionaries and inadequate memory schemas. Strict operation models drive tools/list and runtime validation; legacy/named compatibility, missing/null distinction, exact operation inventory, permission/version coercion tests, select whitelist correction and restricted-server isolation. Actual installed FastMCP API respected. | Closed |
| T7 | Unproven model-visible hook channel and unsafe payload assumptions. Native context fields, validated root/files, project fallback for unstructured edits, inert-until-consented execution, no recursive checks, deadline/cancellation/redaction, three real-host faulty-edit receipts. | Closed |
| T8 | Double relative-path rebasing and inconsistent caller roots. Server-start anchor, suite/scan propagation, immutable original input fields in InvocationContext, normalized cache/staging identity and all caller fixtures. | Closed |
| T9 | Invalid target mistaken for no findings; Click eager rejection bypassed canonical results. Catalog and handwritten quality routes reach shared validation; exact error/skipped/ok and exit mapping; unrelated lexical validation preserved. | Closed |
| T10 | Non-writing lint probe could not prove state placement; historical stray-state origin unproved. Actual session/journal/flight/cache paths tested; read-only constructors separated; exact no-write recovery inventory and future owner-approved cleanup, no speculative deletion. | Closed |
| T11 | Project dependencies conflated with executable trust and cwd. Explicit project/isolated selection, verified engine precedence, interpreter identity/build grants, labeled fallback, cache invalidation and platform tests; CLI/MCP field plumbing assigned. | Closed |
| T12 | Single-file scope/config/import semantics undefined, especially native TS. Concrete owning-config resolution and scoped native tsc strategy, ambient/global inputs, references, rootDir/typeRoots, contained buildinfo, actual consumed files and permission preflight. No dependency-error suppression or pre-7-only API assumption. | Closed |
| T13 | Historical 16/8 duplication not reproduced; naive dedup could erase defects. Exact producer/path/column/message/severity identity and controlled decoder/aggregation fixtures; no unsupported causal claim. | Closed |
| T14 | pyproject recognition mistaken for complete dependency auditing. Native supported uv/requirements routes, OSV version/offline DB contract, explicitly granted isolated pip-audit project resolution, exact inventory provenance and unresolved-input disclosure. | Closed |
| T15 | Hardcoded doctor inventory returned ok when all engines missing. Stack/package recommendations plus actual secure resolver, exact dispositions/actions, integrity errors and shared status readiness. | Closed |
| T16 | Unknown strict-schema fields, discarded engine metadata and unrecoverable output. Sanctioned metadata locations; full child preservation; immutable redacted CCR recovery, read-only retrieval, whole-wire budget for every variable field, strict cursors, service-frame compatibility and explicit no-cache/compact preflight conflict. | Closed |
| T17 | Run-all promise omitted test and failed to account for callers/permissions. Six real shared steps, skipped/not_run distinction, once-only execution, direct TestTool tuple-permission normalization, import-cycle avoidance, existing CLI flags and dashboard/TUI/watch/initial-check propagation. | Closed |
| T18 | Bookkeeping and external-write trust conflated; migrated sources omitted. Exact four-source read-time predicate, unchanged trust/restore/handoff, common UI counts and T20 ownership of public flag. | Closed |
| T19 | Existing review citations mistaken for complete attribution; actual producer receipts dropped. Committed observation/cache row revisions retained, result-cache versus typed-artifact cache distinguished, historical receipts separated, current true consumption only, denial/failed-write absence. | Closed |
| T20 | Bare memory absent; read-only constructor, authorship and pagination unclear. 20-row local-admin metadata overview, source/owner without invented author, atomic generation/count/page snapshot, project/filter-bound continuation and no-write storage reads. | Closed |
| T21 | Summary could imply learning without observed use or rewrite history. Real unioned read/write receipts, neutral text, exact run/attempt persistence, no extra recall and absent-if-unused behavior. | Closed |
| T22 | Four empty tables assumed one defect. Explicit relation, embedding and acknowledged handoff triggers; behavior-success helper has test callers only. Source-grounded findings and characterization, no fabricated production reachability or speculative learning wiring. | Closed |
| T23 | Bare/virgin resolution, cumulative totals, UUID chronology and active-state claims incorrect. Explicit/session/cwd selection, distinct registry failures, read-only ledger access, separate current/published pairs, per-run attempt generation versus cross-run timestamps, ambiguous/corrupt chronology and existing-lock-only observation. No nonexistent admission scan_generation. | Closed |
| T24 | Legacy interactive install bypassed grants; placeholder destinations and latest resolution invalidated preview; rollback could erase concurrent edits. Existing ProvisionPlan extended with resolved identity/concrete destination/hash; resolution-only grant, explicit reviewed payload apply, all grants before key creation, valid config byte reuse and owned CAS rollback. | Closed |
| T25 | Huge help with obsolete count; category route and noncatalog mapping undefined. Exact everyday set, help CATEGORY/help-all, finite remaining map and alias inheritance, registry parity, real first-use walkthrough and tied documentation/catalog reconciliation. | Closed |

Important correction evidence includes `cli_support/rendering.py:107-116` and `invocation/resolver.py:140-167` for rebasing; `invocation/models.py:32-55` for missing original inputs; `invocation/executor.py:195-196,439-473` for permission tuple/cache/observation behavior; `cache.py:129-149` versus `token_economy/memory_cache_gate.py:50-53,122-172` for distinct caches; `workflows/project_run.py:1259-1342` for attempt generations and headers; `dashboard/state.py:506,1219-1241,1440` for mutating construction and published/admission data; and `setup/provision.py:138,390-480,721-860` for resolved identities and grant ordering. These are current-checkout source pointers; they are not assertions that implementation has changed.

## Whole-plan and material-surface coverage

| Coverage | Result |
|---|---|
| Sections 1–3: authority, E1–E18, D1–D7, shared/host contracts | All 18 observations reconciled against current source or explicitly retained as historical/unproved; seven owner-authorized decisions resolved with explicit compatibility and consent. Official host sources linked in plan. |
| Sections 4–6: sequence, R01–R08 and T1–T25 | All eight requirements and 25 distinct tasks present. Topological order moves status before core registration, results before attribution, causal findings before speculative wiring, packaging before hook activation. Shared-file serial ownership explicit. |
| Sections 7–8: checks, file writes, recovery and risks | Runnable G0–G7, packet-specific RED/GREEN fixtures, finite existing/new paths, native host/platform/artifact acceptance, denial and partial failure, corruption, ownership, cache conflict and concurrency covered. |
| Section 9: development alignment and readiness | Current Phase 69 ownership/results preserved. Historical UI defects and ignored sample prototype are not current production proof. Shared consumers remain in scope while UI redesign does not enter plan. Plan readiness separated from implementation/ratification/release. |
| Semantic and failure lanes | Compatibility, no-work versus clean, false memory contribution, retrieval loss, provider/engine trust, side-effect consent, stale/concurrent state, destructive rollback, hidden constructor writes, schema bypass, default-profile migration and misleading active/latest claims explicitly attacked. |

Selection criteria were actual native support, current repository reuse, backwards compatibility, precise authorization, recoverable output and directly testable behavior. Resolutions preserve legacy full MCP while choosing explicit core onboarding; preserve opt-in side effects rather than silently editing user files; prefer authorized project dependencies while retaining engine trust; choose run-all with honest partial execution; and filter bookkeeping without migrating/deleting it. Native tsc CLI was selected over a pre-7 compiler-API helper after current official API documentation and local TypeScript version evidence showed the compatibility problem.

## Verification evidence and limits

Executed during review:
- Repository root/branch/HEAD/status/diff checks before edits and final scope checks; Python `3.12.12`.
- Graft-first source/caller investigations, narrowed source reads and isolated probes recorded in §2 of plan: CLI relative-target double rebase; standard MCP behavior; actual MCP/CLI inventories; controlled Ruff duplicate comparison; Python dependency-dispatch skip; all-engines-missing doctor status; actual schema/metadata and writer paths.
- Current official host contract verification; primary OSV/pip-audit and TypeScript documentation/source verification. Links and verification date retained in plan.
- Mechanical final subject check: 25 tasks, 25 distinct IDs, 18 evidence rows, seven decision rows, eight requirement rows, nine sections, required task packet fields, valid fence balance and no trailing whitespace. Literal file-map check covered 136 paths; absent paths were explicitly new deliverables or the `src/bad.py` reproduction fixture, not phantom existing files.
- Original snapshot hash exactly matches original plan. Final plan hash matched both reviewers and final no-drift check. Git whitespace check passed; explicit plan whitespace check covers its untracked status.

Not executed: Phase 70 implementation tests, complete application regression suite, native host installations/hooks, real platform matrix, release builds, stray-state cleanup, or production acceptance. New named tests are required future RED/GREEN work, not evidence of current behavior. Characterization probes are not substitutes for those gates.

### Pre-existing document-gate failure

`rtk proxy env -u PYTHONPATH uv run --python 3.12 --extra dev python scripts/sync_docs.py --check` failed on baseline before plan repair. Output included unrelated missing document coverage receipts, the already-untracked Phase 70 plan receipt, and these ten runtime-parameter omissions:

- CLI `rush memory maintain`: owner_id, owner_kind.
- MCP `rush_continuity`: project_id, run_id, session_id.
- MCP `rush_memory`: agent_id, invocation_id, project_id, run_id, session_id.

No global document-gate PASS is claimed. Broad unrelated coverage regeneration would exceed this plan-only review. T25/§8.1 assign touched documentation/contracts reconciliation through existing helpers, preserving unrelated entries; G7 still requires the real checker to pass before implementation completion. Unrelated baseline debt remains a separately visible repository acceptance dependency, not permission to waive G7. It does not prevent beginning the resolved implementation sequence.

## Final disposition

No open plan-review finding remains on the recorded final hash. All original scope retained and strengthened with concrete contracts, files, dependencies, failure behavior and test-first acceptance. The plan is ready for a subsequent implementation instruction.

This review authorizes neither implementation nor side effects. No commit was made. Any later plan edit invalidates this exact-hash verdict and requires review of changed contracts and affected dependencies.
