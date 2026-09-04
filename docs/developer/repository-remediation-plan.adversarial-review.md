# Adversarial Review of the Repository Remediation Plan

## Review objective and scope

Sol reviewed `docs/developer/repository-remediation-plan.md` as an execution plan, not as an implementation request. The review tests whether the plan's findings, evidence, severity, remediations, phase ordering, delivery slices, release gates, verification baseline, and definition of done are accurate, complete, executable, and resistant to false assurance.

No Rush remediation is implemented by this review. The only files that may change are the remediation plan and this review artifact.

## First-round freeze

The plan text was read in full and frozen before delegation.

- Frozen plan SHA-256: `E30A02400494F50C6005616C3527B5635973B06DDDCA64D5948D36AD3D770A50`
- Frozen plan length: 391 lines
- Freeze rule: all first-round attackers and cross-examiners review this exact plan; no plan edit is authorized until Sol adjudicates the first round and issues fix orders.

## Sol claim ledger

Each ID identifies a proposition that must survive repository evidence and an executable closure path. Compound prose is split where its truth, cause, consequence, remedy, or proof can fail independently.

### Framing and review-coverage claims

| Claim ID | Plan location | Material claim |
|---|---|---|
| CL-META-001 | Lines 3-6 | The plan is proposed, dated 2026-08-27, covers the entire first-party repository across the listed domains, and no remediation code has been applied by the review. |
| CL-META-002 | Lines 10-12 | R-001, R-002, R-003, and R-004 are release blockers and no release should occur before Phase 0 gates pass. |
| CL-META-003 | Lines 10-12 | Executable contracts and security boundaries must precede consistency and maintainability work; early hotspot refactoring increases risk. |
| CL-COV-001 | Line 16 | The review used graph traversal, exhaustive searches over exactly 384 first-party Python files, targeted source/call-path inspection, clean-wheel execution, type checking, linting, and repeated full-suite runs. |
| CL-COV-002 | Line 16 | Excluding local untracked `research/` from product findings is complete and defensible. |
| CL-COV-003 | Lines 18-36 | The coverage table accurately maps every reviewed surface to R-001 through R-015 and correctly concludes that patch/sandbox and the broad bundle/sync/governance group contain no additional release blocker. |
| CL-COV-004 | Lines 30 and 301-313 | Patch/sandbox defects are correctly scoped as Phase 5 hardening rather than a separately registered finding. |

### Finding R-001 claims

| Claim ID | Plan location | Material claim |
|---|---|---|
| CL-R001-E1 | Lines 44-46 | The script/package configuration is as cited; exactly 26 production imports use `src.rush`; the examples and test import-path lines are accurate. |
| CL-R001-E2 | Lines 47-48 | A clean wheel fails on `rush --help` through the stated import path, and mypy aborts solely as described because of dual module identities. |
| CL-R001-I | Line 50 | The distributable is unusable despite source-tree tests. |
| CL-R001-C | Line 52 | Missing installed-artifact testing plus the test import path are the sufficient root cause. |
| CL-R001-F | Lines 240-252 | Rewriting namespaces, tightening test imports, centralizing version metadata, stale-literal testing, and clean-wheel runs on Windows/POSIX fully close R-001 and the coupled R-012 work. |
| CL-R001-P | Lines 232, 238, 248, 252, 363-365, 375 | The proposed installed-artifact and mypy gates cannot pass while the wheel/namespace defect remains. |

### Finding R-002 claims

| Claim ID | Plan location | Material claim |
|---|---|---|
| CL-R002-E1 | Lines 58-60 | Shared subprocess capture reaches `_SECRET_ASSIGNMENT`; Authorization/Bearer and quoted-JSON probes leak; the existing subprocess test starts with already-redacted fixture text. |
| CL-R002-I | Line 62 | Engine output can expose credentials through every named CLI, MCP, log, cache, finding, summary, and error surface. |
| CL-R002-C | Line 64 | The narrow regex is the operative global boundary and the existing `SecretRedactor` is a suitable replacement foundation. |
| CL-R002-F | Lines 254-266 | One recursive sanitizer, pre-storage sanitation, final serialization defense, corrected exception formatting, and fallback logging close both disclosure and dropped-diagnostic paths. |
| CL-R002-P | Lines 233, 238, 266, 368 | Recursive random-sentinel tests across all named outputs and cache rows cannot pass while a material secret path remains. |

### Finding R-003 claims

| Claim ID | Plan location | Material claim |
|---|---|---|
| CL-R003-E1 | Lines 70-73 | The CLI checks path trust and invokes the legacy loader; path trust is not content/command-bound; legacy execution inherits the environment; hardened trust/executor/environment code exists but is bypassed. |
| CL-R003-I | Line 75 | An approved path can later execute mutated code/config with user credentials. |
| CL-R003-C | Line 77 | Two plugin execution systems exist and the hardened route is not the production CLI route. |
| CL-R003-F | Lines 268-281 | Single-route migration plus repository/command/path/content binding, immediate revalidation, sanitized environment, result validation, and trust receipts close all material plugin trust paths. |
| CL-R003-P | Lines 281 and 369 | Mutation invalidation, credential-denial, malformed-output, and single-executor tests cannot pass while a bypass remains. |

### Finding R-004 claims

| Claim ID | Plan location | Material claim |
|---|---|---|
| CL-R004-E1 | Lines 83-86 | MCP registers exactly 38 canonical catalog tools and exactly 25 manual extras; the extras use incompatible types/direct implementations; tests hard-code the split and schema-check only catalog tools. |
| CL-R004-I | Line 88 | The split prevents enforceable transport parity and creates permission/redaction/schema divergence. |
| CL-R004-C | Line 90 | Accumulation outside `TOOL_SPECS`/`ALL_TOOLS` is the sufficient root cause. |
| CL-R004-F | Lines 283-297 | A typed context, uniform signature, migration/removal of all 25 operations, canonical result validation, shared scope/cache, and explicit LLM skip semantics close R-004 and its coupled findings. |
| CL-R004-P | Lines 234, 238, 297, 365-367 | Enumeration, installed stdio, equality, configuration mapping, and runtime schema gates cover every public route and cannot greenlight a split surface. |

### Finding R-005 claims

| Claim ID | Plan location | Material claim |
|---|---|---|
| CL-R005-E1 | Lines 96-99 | The generic CLI exposes all named flags; staged/changed/since results are discarded except for empty checks; `no_cache`/`all_workspaces` are unused; `ResultCache` has no production callers. |
| CL-R005-I | Line 101 | Requested scope can be broadened, workspace behavior is misleading, and advertised caching is absent. |
| CL-R005-C | Line 103 | Transport flags preceded a defined execution-scope/cache contract. |
| CL-R005-F | Lines 287-293 | The typed invocation context and explicit target-set/shared-workspace/cache decision fully specify scope and cache semantics across transports. |
| CL-R005-P | Lines 297 and 370 | Integration tests proving unrelated files are excluded are sufficient for staged/changed/since/workspace behavior, and the plan adequately gates cache behavior. |

### Finding R-006 claims

| Claim ID | Plan location | Material claim |
|---|---|---|
| CL-R006-E1 | Lines 109-110 | `_run_tool` catches every internal `TypeError` and retries without permissions, including after partial work. |
| CL-R006-I | Line 112 | This hides defects, disables permission-aware behavior, and can duplicate side effects. |
| CL-R006-C | Line 114 | Runtime exception handling is being used as interface negotiation. |
| CL-R006-F | Lines 287-288 | A typed context or mechanically uniform signature plus registration-time inspection eliminates retry ambiguity without breaking legacy tools. |
| CL-R006-P | Line 297 | Absence of the retry plus integration/contract tests proves the defect cannot recur. |

### Finding R-007 claims

| Claim ID | Plan location | Material claim |
|---|---|---|
| CL-R007-E1 | Lines 120-123 | CLI network options do not reliably reach `ReviewTool`; provider summarization runs without network permission; both providers return canned success text; tests encode the behavior. |
| CL-R007-I | Line 125 | Heuristic/canned text is misrepresented as actual model analysis. |
| CL-R007-C | Line 127 | Permission denial is modeled as provider success. |
| CL-R007-F | Line 293 | Denial-as-`skipped` and evidence of an actual request before `review_kind=llm` fully repair provider/permission semantics. |
| CL-R007-P | Lines 297 and 371 | Network-disabled skip tests and network-enabled mock-endpoint tests prove both negative and positive paths. |

### Finding R-008 claims

| Claim ID | Plan location | Material claim |
|---|---|---|
| CL-R008-E1 | Lines 133-135 | Structured logging passes `exc_info` to the wrong formatter API, swallows the resulting error, emits no event in a runtime probe, and lacks exception-path tests. |
| CL-R008-I | Line 137 | Critical diagnostics disappear, including MCP failures where stderr is the only allowed diagnostics channel. |
| CL-R008-C | Line 139 | Wrong formatter use plus broad drop-on-failure behavior fully explains the loss. |
| CL-R008-F | Lines 261-262 | Correct exception formatting and a minimal redacted stderr fallback close the diagnostic loss without violating stdio. |
| CL-R008-P | Line 266 | Exactly one valid NDJSON stderr record and clean stdout objectively prove closure, including formatter-failure behavior. |

### Finding R-009 claims

| Claim ID | Plan location | Material claim |
|---|---|---|
| CL-R009-E1 | Lines 145-148 | Lock acquisition/release use the cited racy check/write and read/unlink sequences; daemon duplicates them; tests are only sequential. |
| CL-R009-I | Line 150 | Multiple agents can concurrently believe they own the same protected file. |
| CL-R009-C | Line 152 | Metadata-file existence was mistaken for an atomic ownership primitive. |
| CL-R009-F | Lines 303-305 | Atomic acquisition, opaque ownership, lease metadata, token-checked release, renewal-safe stale recovery, and deduplication fully specify a cross-process lock. |
| CL-R009-P | Lines 313 and 372 | Multiprocess one-winner and stale-owner tests are reproducible and cover all relevant contention/renewal paths. |

### Finding R-010 claims

| Claim ID | Plan location | Material claim |
|---|---|---|
| CL-R010-E1 | Lines 158-160 | All four named stores use unlocked non-atomic read/modify/write; readers collapse decode/I/O failure to empty state; containment relies on callers. |
| CL-R010-I | Line 162 | Concurrency, interruption, or one corrupt record can erase continuity/invariant data. |
| CL-R010-C | Line 164 | Independent optimistic JSON persistence is the common root cause. |
| CL-R010-F | Lines 306-309 | A shared versioned atomic store, corruption preservation, class-boundary containment, and patch hardening fully close persistence and related patch risks. |
| CL-R010-P | Lines 313 and 372 | Kill-during-write, corruption-retention, traversal/symlink, lock, and crash tests are sufficiently portable and deterministic. |

### Finding R-011 claims

| Claim ID | Plan location | Material claim |
|---|---|---|
| CL-R011-E1 | Lines 170-172 | Canonical finding severity is exactly `info|warn|error`; exactly 46 production findings use `fail`; flaky uses `warning`; exporters/dashboard/tests preserve aliases. |
| CL-R011-I | Line 174 | Drift defeats static validation and causes inconsistent downstream mappings. |
| CL-R011-C | Line 176 | Lack of runtime validation at engine boundaries is the root cause. |
| CL-R011-F | Lines 319-321 | The recommended finding/status vocabularies, runtime normalizer validation, and enum-derived exporter mappings close all schema drift. |
| CL-R011-P | Lines 328 and 367 | Every normalizer is exercised, every public result is validated, and undeclared literals are exhaustively prohibited. |

### Finding R-012 claims

| Claim ID | Plan location | Material claim |
|---|---|---|
| CL-R012-E1 | Lines 182-183 | Public version is 0.3.0 while every named consumer/template still embeds 0.2.0. |
| CL-R012-I | Line 185 | Generated artifacts and network identity can report a stale version. |
| CL-R012-C | Line 187 | Copied literals rather than package metadata are the complete cause. |
| CL-R012-F | Lines 246-247 | Metadata derivation with a development fallback and a stale-literal test cover all runtime, generated, TypeScript, TUI, and release-template cases. |
| CL-R012-P | Line 252 | No stale first-party release literal remaining is an executable, appropriately scoped exit criterion. |

### Finding R-013 claims

| Claim ID | Plan location | Material claim |
|---|---|---|
| CL-R013-E1 | Lines 193-196 | The tool claims SLSA Level 3 while generating unsigned local JSON, asserts unobserved reproducibility/completeness, substitutes a commit-string hash for an artifact digest, and MCP repeats the assurance claim. |
| CL-R013-I | Line 198 | Consumers can mistake self-asserted metadata for verified provenance. |
| CL-R013-C | Line 200 | Statement shape is being conflated with attained assurance. |
| CL-R013-F | Lines 322-324 | Renaming to unsigned draft unless controlled signed attestation exists, requiring evidence/artifact digest/current predicate, and removing Level 3 wording fully correct assurance. |
| CL-R013-P | Lines 328 and 376 | Provenance tests prohibit every unsupported assurance/reproducibility/completeness claim and distinguish signed from unsigned output. |

### Finding R-014 claims

| Claim ID | Plan location | Material claim |
|---|---|---|
| CL-R014-E1 | Lines 206-207 | The exact first/isolated/second pytest outcomes occurred and the knip discovery result depended on ambient state or timing rather than a source change. |
| CL-R014-I | Line 209 | Default CI signal depends on machine PATH/timing. |
| CL-R014-C | Line 211 | Deterministic contracts and installed-engine conformance are mixed. |
| CL-R014-F | Line 235 | Splitting deterministic and optional conformance suites and recording executable/version fully closes ambient-engine nondeterminism. |
| CL-R014-P | Lines 373, 380-382 | Structured skips plus the proposed suite split are reproducible and cannot conceal a broken available engine. |

### Finding R-015 claims

| Claim ID | Plan location | Material claim |
|---|---|---|
| CL-R015-E1 | Lines 217-220 | The stated health scores, change-hotspot order, named complexity/nesting values, and two-candidate dead-code result are current and produced by defensible measurements. |
| CL-R015-I | Line 222 | Central-path correctness fixes are materially expensive and regression-prone because of these hotspots. |
| CL-R015-C | Line 224 | Transport, policy, orchestration, and domain logic concentration is the root cause. |
| CL-R015-F | Lines 330-340 | The four decomposition instructions plus evidence-based deletion are appropriately delayed and complete enough to execute without product changes. |
| CL-R015-P | Lines 340 and 391 | An agreed complexity threshold, unchanged green behavior gates, and completion of all R-015 refactors form a measurable and proportionate release definition. |

### Phase, ordering, and delivery claims

| Claim ID | Plan location | Material claim |
|---|---|---|
| CL-P0-001 | Lines 228-238 | Phase 0 can be implemented before behavior changes and its five gates expose every listed release blocker on unfixed code. |
| CL-P0-002 | Line 238 | Phase 0 exit criteria accurately say the gates reproduce R-001 through R-004/R-011 and exclude source-tree leakage; the notation and coverage are unambiguous. |
| CL-P1-001 | Lines 240-252 | Phase 1's namespace and version work is internally complete, correctly coupled, and needs only the stated primary files. |
| CL-P2-001 | Lines 254-266 | Phase 2 orders sanitation and diagnostics safely and names all required implementation/test surfaces. |
| CL-P3-001 | Lines 268-281 | Phase 3's trust model has complete approval identity, invalidation, environment, output, audit, migration, and test semantics. |
| CL-P4-001 | Lines 283-297 | Phase 4 can safely unify 25 legacy operations, contexts, results, scopes, cache, and provider semantics without unstated product decisions or files. |
| CL-P5-001 | Lines 299-313 | Phase 5's lock, store, containment, and patch work is coherent, portable, correctly grouped, and sufficiently sequenced. |
| CL-P6-001 | Lines 315-328 | Phase 6's recommended result/severity and provenance contracts are compatible with all consumers and current standards. |
| CL-P7-001 | Lines 330-340 | Phase 7 begins only after behavior is pinned, defines a threshold elsewhere or explicitly requires one, and contains no behavior changes. |
| CL-ORDER-001 | Lines 228-340 | The phase sequence expresses every prerequisite; no later phase must precede an earlier phase for tests, migrations, schemas, or compatibility. |
| CL-SLICE-001 | Lines 342-357 | Delivery slices are small, independently reviewable/reversible, and their `Depends on` edges are complete. |
| CL-SLICE-002 | Lines 348-357 | Slice 1 can include all four failing-gate groups with no prerequisites; slices 2-10 can fit their stated contents without unnamed cross-slice edits. |
| CL-SLICE-003 | Lines 351-356 | Plugin depends only on redaction; invocation context depends only on namespace/redaction; MCP consolidation depends only on context; scope/cache/LLM depends only on context/MCP; severity/provenance depends only on MCP. |
| CL-SLICE-004 | Line 357 | Complexity refactors safely depend on all correctness slices and need no independent product decision or migration. |

### Release-gate claims

| Claim ID | Plan location | Material claim |
|---|---|---|
| CL-GATE-001 | Lines 361-365 | A clean off-checkout wheel install plus console help and real stdio initialize/list is sufficient installed-artifact startup evidence on supported platforms. |
| CL-GATE-002 | Line 366 | A tested one-to-one mapping among CLI, catalog, implementation registry, configuration keys, and MCP is both intended and possible for every public capability. |
| CL-GATE-003 | Line 367 | Runtime validation of every public `ToolResult` covers success, failure, skipped, malformed engine, plugin, and legacy routes. |
| CL-GATE-004 | Line 368 | Absence of a sentinel corpus from nested output, stderr, exports, and cache rows covers all pre-storage, serialization, exception, truncation, binary/text, and failure paths. |
| CL-GATE-005 | Line 369 | Executable/config mutation and denied-credential tests cover plugin identity, symlink, command, environment, TOCTOU, and trust-store invalidation. |
| CL-GATE-006 | Line 370 | Scope tests cover staged, changed, since, workspace, all-workspaces, zero-match, deleted/renamed, and transport parity semantics. |
| CL-GATE-007 | Line 371 | Disabled skip plus enabled mock endpoint proves truthful provider invocation and permission propagation without live-network nondeterminism. |
| CL-GATE-008 | Line 372 | Multiprocess lock and crash tests cover ownership, stale renewal, atomic replace, corruption retention, and supported-platform durability. |
| CL-GATE-009 | Line 373 | Deterministic and conformance suites distinguish unavailable-engine skips from defects in an available/misconfigured engine. |
| CL-GATE-010 | Lines 374-375 | Ruff and mypy gates use complete, reproducible scopes and compatible configurations. |
| CL-GATE-011 | Line 376 | Provenance tests track the selected current standard and prohibit all unsupported assurance, subject, reproducibility, completeness, signing, and builder claims. |
| CL-GATE-012 | Lines 359-376 | The mandatory gate set detects every R-001 through R-014 defect and cannot pass while any critical defect remains. |

### Verification-baseline and definition-of-done claims

| Claim ID | Plan location | Material claim |
|---|---|---|
| CL-BASE-001 | Lines 380-382 | The two full-suite counts, isolated seven-test result, one warning, exact knip test, and warning characterization are accurate and reproducible enough to serve as baseline evidence. |
| CL-BASE-002 | Lines 383-385 | Standard Ruff passed; exactly 623 files were formatted; the strict audit produced exactly 33 individually reviewed findings and every material one appears in the plan. |
| CL-BASE-003 | Lines 386-387 | Mypy and clean-wheel failures occurred exactly as stated and establish the claimed causes rather than merely correlating with them. |
| CL-DONE-001 | Lines 389-391 | Closing R-001 through R-014 with regression tests, passing all gates from the built artifact, and completing R-015 refactors is necessary and sufficient for remediation. |
| CL-DONE-002 | Line 391 | Requiring every R-015 refactor for repository remediation/release readiness is proportionate and consistent with R-015's medium severity and the plan's no-behavior refactor policy. |
| CL-DONE-003 | Line 391 | The definition of done cannot be satisfied by a green source-tree suite and contains all required platform, artifact, security, migration, documentation, rollback, and product-decision conditions. |

## Terra assignments

All attackers were read-only, received the frozen hash, and were required to ground findings in exact repository evidence.

| Terra | Mission | First-round status |
|---|---|---|
| Terra 1 | Finding falsifier: R-001 through R-015 truth, evidence, causes, impacts, omissions, and baseline | Complete; T1-001 through T1-004 |
| Terra 2 | Remediation breaker: bypasses, incomplete fixes, and tests that can pass while defects survive | Complete; T2-001 through T2-013 |
| Terra 3 | Execution-plan saboteur: prerequisites, migrations, ordering, slices, and literal-agent executability | Complete; T3-001 through T3-007 |
| Terra 4 | Security and trust attacker: redaction, plugin authority, credentials, persistence, and false assurance | Complete; T4-001 through T4-004 |
| Terra 5 | Contract and transport attacker: CLI/MCP/config parity, results, scopes, cache, and installed behavior | Complete; T5-001 through T5-005 |
| Terra 6 | Release-gate and scope attacker: artifacts, gates, Phase 0, patch safety, optional engines, and done | Complete; T6-001 through T6-006 |

## First-round attack findings

This is the normalized first-round record. “Correction/gate” is the minimum remedy requested by the attacker, not yet Sol's adjudication.

| ID | Sev. | Claim/section attacked | Attack, exact evidence, and failure narrative | Minimum correction/gate | Blocks; new |
|---|---|---|---|---|---|
| T1-001 | P2 | CL-COV-001 | The claimed exhaustive 384-file population conflicts with 250 `src`, 232 `tests`, and 15 `scripts` Python files (497 non-`research` files); the stated whole-repository coverage has no manifest or exclusions. | Generate an in-scope manifest with reviewed/excluded status or narrow the coverage claim. | Yes; yes |
| T1-002 | P3 | CL-R005-E1 | “No production callers” is false: `cli.py:752-769` constructs `ResultCache` for public `cache stats/clean`; only execution-path key/get/set integration is absent. | Correct the evidence and classify/admin-test retained cache commands. | No; no |
| T1-003 | P2 | CL-R010-E1/C | `CheckpointJournal` writes one record without read-modify-write, unlike the other three stores; its risks are torn same-name overwrite and containment, not shared-document lost update. | Split shared-document transaction tests from journal per-record durability/containment tests. | No; no |
| T1-004 | P1 | CL-GATE-002, CL-R004-F/P | Raw CLI/catalog/MCP equality is impossible: CLI-only `capabilities`, `plan`, `cache stats/clean`, and other controls are outside 38 `ALL_TOOLS`; 25 manual MCP tools form another surface. | Classify every public operation; require one-to-one parity only for canonical tool operations. | Yes; yes |
| T2-001 | P1 | CL-R001-F, CL-GATE-001 | An external venv run from repository CWD can still resolve checkout `src.rush`; clearing only `PYTHONPATH` does not prove installed origin. | Run all artifact probes off-checkout and assert module origins/site-packages-only `sys.path`. | Yes; yes |
| T2-002 | P1 | CL-R002-F/P, CL-GATE-004 | `attest.py:23-30,59-85` publishes Git remote URLs; current redactors do not remove URL userinfo, so `https://user:secret@host` can leak through provenance. | Sanitize userinfo, sensitive query/fragment, and encoded variants; add Git-remote sentinel tests. | Yes; yes |
| T2-003 | P0 | CL-R003-F/P | `executor.py:29-31` trusts `executable_path` but `:51-60` launches independent `command`; PATH resolution and validate-to-spawn swaps can execute an unapproved object. | Make the exact verified absolute executable the launched object; reject divergence/PATH/symlink swaps and test synchronized races. | Yes; yes |
| T2-004 | P1 | CL-R003-F/P | Environment filtering cannot prove a plugin lacks credentials while it runs as the user and can read home/cloud configs or credential helpers. | Either narrow the assurance to inherited environment or require a genuine filesystem/home/network isolation boundary and test it. | Yes; yes |
| T2-005 | P1 | CL-R004-F, CL-GATE-002/003 | Migrating only manual MCP wrappers leaves standalone CLI routes such as `rush attest` directly invoking implementations and bypassing canonical results/redaction. | Inventory every CLI/MCP operation and map each retained capability to one implementation/result boundary. | Yes; yes |
| T2-006 | P2 | CL-R005-F/P | Result-only scope tests can pass while a tool re-expands the root and reads unrelated files. | Put an immutable target allowlist in the context; observe engine argv/file access with trap files. | Yes; yes |
| T2-007 | P2 | CL-R006-F/P | Source absence of the current retry is not behavioral proof; a compatibility adapter could reinvoke after an internal `TypeError`. | Centralize registration-time compatibility and test one side effect/one invocation through CLI and MCP. | Yes; yes |
| T2-008 | P1 | CL-R007-F/P | Providers return success-shaped `LLMResponse` on HTTP/transport/parse failure; evidence of an attempted request can still be mislabeled `review_kind=llm`. | Use discriminated skipped/error/executed outcomes; only a validated completion is LLM analysis; test the full failure matrix. | Yes; yes |
| T2-009 | P1 | CL-R009-F/P | An opaque lock token is unusable through current bool acquire/release plus caller-chosen `agent_id`; wire migration and token secrecy are unspecified. | Return an unguessable capability, require it for release/renewal, deprecate the old API, and test live MCP stale/reused IDs. | Yes; yes |
| T2-010 | P1 | CL-R010-F/P | Atomic replacement alone permits lost updates when two processes read, mutate, and replace separately. | Hold a transactional lock or CAS across read/validate/mutate/durable replace; barrier-test every mutator. | Yes; yes |
| T2-011 | P2 | CL-R013-F/P | A “signed” label can bless arbitrary local self-signing; trusted builder identity and independent verification are absent. | Keep local output unsigned or define trusted-builder verification with negative signer/subject/predicate tests. | Yes; yes |
| T2-012 | P2 | CL-R014-F/P | Optional conformance can be entirely skipped, leaving available-but-broken supported engines untested. | Define support policy and a pinned available/unavailable/malformed engine CI matrix. | Yes; yes |
| T2-013 | P3 | CL-R015-F/P | “Agreed complexity threshold” has no metric, value, baseline, or exemptions, so superficial refactors can pass. | Pin metric/tool/version, targets, threshold, baseline, characterization tests, and expiring exemptions. | No; yes |
| T3-001 | P1 | CL-P4-001, CL-GATE-002 | “Migrate or remove” gives no disposition/compatibility policy for 25 public legacy MCP operations with heterogeneous inputs and effects. | Create a 25-row retain/migrate/deprecate manifest with schemas, aliases, permissions, adapters, and removal policy. | Yes; yes |
| T3-002 | P1 | CL-R005-F, CL-GATE-006 | A single `Path` API cannot express deleted/renamed targets, multi-workspace aggregation, or operation-specific requests without widening scope. | Define ordered target entries/states, selection provenance, workspace/aggregation behavior, and per-tool scope capability. | Yes; yes |
| T3-003 | P1 | CL-P3-001 | Legacy user-owned repository grants and repo-local hardened hash records have incompatible identities and no migration/grant flow. | Choose one user-owned authority, version records, resolve `PluginSpec`, add grant/revoke UX, and require reapproval or explicit upgrade. | Yes; yes |
| T3-004 | P1 | CL-P3-001, CL-P6-001 | Phase 3 requires canonical plugin validation before Phase 6 decides the severity vocabulary and validator. | Create a schema-kernel decision/implementation slice before plugin/MCP migration. | Yes; yes |
| T3-005 | P2 | CL-R005-F, CL-GATE-004 | Phase 2 claims cache sanitation before Phase 4 decides whether cache exists in execution; the early gate can pass without a row. | Make retain/defer a Phase 0 decision; test a real execution row if retained or remove public cache claims if deferred. | Yes; yes |
| T3-006 | P1 | CL-P5-001, CL-GATE-008 | Stores return dict/None/bool and public callers conflate corrupt with missing; Phase 5 has no typed outcome or dependency on canonical result migration. | Define absent/corrupt/invalid/I-O outcomes, map them to canonical results, and order public adaptation before store migration. | Yes; yes |
| T3-007 | P3 | CL-P7-001, CL-DONE-001 | Mandatory R-015 work has no objective metric/gate and can block forever or finish arbitrarily. | Pin a deterministic metric/baseline or separate R-015 from release readiness. | No; yes |
| T4-001 | P0 | CL-R003-F/P | The current hardened store is `<repo>/.rush/trust.json`; a malicious checkout can commit a matching plugin/hash and self-authorize. | Make only a user-owned, non-repository, link-safe ledger authoritative; repo receipts are evidence only. | Yes; yes |
| T4-002 | P1 | CL-R003-F/P | Verified path and launched command diverge; `allow_untrusted=True` is a public bypass; subprocess re-resolves argv and Windows batch commands via `cmd.exe`. | Remove bypass, launch only an immutable approved absolute spec, and reject command/PATH/symlink mismatches. | Yes; yes |
| T4-003 | P1 | CL-R002-F/P, CL-P2-001 | `SecretRedactor.redact_value` preserves mapping keys; checkpoints and other persistence are outside the stated cache/output gate. | Redact every serializable string position with collision policy and scan all stores/temp/backup artifacts. | Yes; yes |
| T4-004 | P2 | CL-R007-F/P | `LLMResponse` cannot represent skipped/error/executed; current mocks assert content, not truthful execution evidence or sanitized failure state. | Add typed provider outcome/evidence and negative transport/redirect/malformed tests. | Yes; yes |
| T5-001 | P2 | CL-R004-F/P, CL-GATE-002 | Public control operations such as `mcp serve` and `cache stats` make raw surface equality nonsensical. | Add versioned PublicOperation kinds and manifest-driven parity/no-unclassified-route tests. | Yes; yes |
| T5-002 | P1 | CL-R004/R005/R007-F | CLI resolves config and calls `run`; MCP registers `__call__` without config. Same schema can hide different config/root/permission/scope behavior. | Define one server-side invocation resolver and assert semantic CLI/stdio parity with non-default config. | Yes; yes |
| T5-003 | P1 | CL-R005-F/P | `ResultCache.compute_cache_key` hashes a directory as empty after swallowed read failure; two repositories can collide if cache is integrated naively. | Define target-set/root/config/engine/args/permission/schema identity and cacheable outcomes; add cross-directory tests. | Yes; yes |
| T5-004 | P1 | CL-R004-P, CL-GATE-001 | Installed MCP initialize/list does not execute lazy imports; most advertised tools are never called in the checkout test. | Give every advertised tool a safe installed-wheel contract probe and invoke all off-checkout. | Yes; yes |
| T5-005 | P2 | CL-R011-F/P, CL-GATE-003 | `ToolResult` and `Finding` are `total=False`; no runtime/versioned JSON contract requires fields, JSON-safe extensions, or canonical errors. | Define runtime `ToolResultV1`/`FindingV1` plus schema version, errors, enums, extensions, and uniform serialization. | Yes; yes |
| T6-001 | P0 | CL-R001-P, CL-GATE-001 | Same checkout-CWD/module-origin bypass as T2-001, demonstrated with repository-root resolution of `src.rush`. | External empty CWD, scrub paths, `python -I`/origin assertions for CLI/import/MCP. | Yes; yes |
| T6-002 | P1 | CL-COV-004, CL-DONE-001 | Public `rush patch test` says “Apply and verify” but calls only parser/apply/syntax; `PatchVerifier` has no caller, sandbox failure creates an empty dir, cleanup lacks containment, and no gate/DoD closes it. | Register a patch-safety finding; fail closed; invoke verifier; ensure rollback, managed cleanup, unique temp files, containment, and mandatory gate/DoD. | Yes; yes |
| T6-003 | P1 | CL-GATE-001, CL-DONE-003 | Only wheels are built/installed; an sdist can be broken while every gate passes. | Build/install wheel and sdist independently on Windows/POSIX with the same off-checkout probes. | Yes; yes |
| T6-004 | P2 | CL-P0-001/002 | Phase 0 has no production plugin child-environment/approval fixture, so it cannot reproduce R-003 before migration. | Add a Phase 0 production-route plugin attack fixture that observes child environment and mutation invalidation. | Yes; no |
| T6-005 | P2 | CL-R014-P, CL-GATE-009 | All optional conformance jobs may skip; no available-engine result is required. | Pin a representative engine matrix with unavailable, success, and malformed/failure outcomes. | No; yes |
| T6-006 | P2 | CL-R015-P, CL-DONE-001/002 | Undefined R-015 completion is mandatory for release even though it is medium maintainability work with no complexity gate. | Separate release readiness from program completion or pin the metric/threshold/baseline. | Yes; yes |

## Cross-examination results

### Cross-examination docket

Duplicates are consolidated, but every source finding remains linked. All P0/P1 dockets and disputed P2 dockets require a challenger who did not author the linked attack.

| Docket | Source findings | Issue to challenge | Required disposition |
|---|---|---|---|
| XD-01 | T1-001 | Repository-wide coverage count/manifest | P2 disputed: sustain, narrow, disprove, or require uncertainty |
| XD-02 | T1-004, T2-005, T3-001, T5-001 | Public-operation classification and 25-operation compatibility manifest | P1 challenge |
| XD-03 | T2-001, T6-001 | Off-checkout artifact CWD/module-origin proof | P0/P1 challenge |
| XD-04 | T2-002, T4-003 | URL-userinfo, mapping-key, and all-persistence redaction coverage | P1 challenge |
| XD-05 | T4-001 | Repository-controlled plugin store can self-authorize | P0 challenge |
| XD-06 | T2-003, T4-002 | Approved object versus launched command, bypass flag, and TOCTOU/PATH behavior | P0/P1 challenge |
| XD-07 | T2-004 | Plugin filesystem/network authority versus environment-only assurance | P1 challenge |
| XD-08 | T3-003 | Plugin trust-store migration/grant/reapproval | P1 challenge |
| XD-09 | T3-004, T5-005 | Schema-kernel ordering and executable `ToolResultV1` contract | P1/P2 challenge |
| XD-10 | T5-002 | One invocation resolver and semantic CLI/MCP parity | P1 challenge |
| XD-11 | T2-006, T3-002 | Exact target-set model, deleted/renamed, aggregation, access enforcement | P1/P2 challenge |
| XD-12 | T3-005, T5-003 | Cache product decision and collision-safe execution identity | P1/P2 challenge |
| XD-13 | T2-007 | One-invocation behavioral proof for internal `TypeError` | P2 disputed challenge |
| XD-14 | T2-008, T4-004 | Discriminated provider outcome and truthful LLM labeling | P1/P2 challenge |
| XD-15 | T2-009 | Lock capability wire contract and legacy migration | P1 challenge |
| XD-16 | T1-003, T2-010, T3-006 | Transactional stores, distinct journal semantics, and typed public errors | P1/P2 challenge |
| XD-17 | T2-011 | Signed provenance versus controlled trusted builder; current predicate selection | P2 disputed challenge |
| XD-18 | T2-012, T6-005 | Supported-engine policy and pinned conformance matrix | P2 disputed challenge |
| XD-19 | T2-013, T3-007, T6-006 | Complexity metric and release-readiness versus program-completion DoD | P2/P3 disputed challenge |
| XD-20 | T5-004 | Installed invocation probe for every advertised MCP tool | P1 challenge |
| XD-21 | T6-002 | New patch-safety finding, public verifier path, rollback/containment gate | P1 challenge |
| XD-22 | T6-003 | Wheel plus sdist artifact matrix | P1 challenge |
| XD-23 | T6-004 | Phase 0 must reproduce plugin trust/environment failure | P2 disputed challenge |
| XD-24 | T1-002 | Correct cache evidence and retain/admin classification | P3; no mandatory cross-examination |

### Challenger results

| Docket | Challenger | Result | Strongest attempted disproof and surviving boundary |
|---|---|---|---|
| XD-01 | Terra 4 | Narrowed | `384` might describe a subset, but whole-repository/exhaustive wording has no manifest. Require an auditable population or narrow the claim. |
| XD-02 | Terra 4 | Sustained | Control-plane exceptions may be intentional, but they are undocumented; raw surface equality is not a contract. |
| XD-03 | Terra 4 | Sustained | An external venv and empty `PYTHONPATH` do not prevent repository-CWD imports. External CWD and origin assertions are required. |
| XD-04 | Terra 5 | Narrowed | Some checkpoints redact values, but URL userinfo, mapping keys, preference storage, and unlisted persistence paths remain demonstrably exposed. |
| XD-05 | Terra 5 | Narrowed | Repo self-authorization is not on the current legacy CLI path, but Phase 3 would introduce it by adopting the existing executor/store unchanged. |
| XD-06 | Terra 5 | Narrowed | `allow_untrusted` has no current public caller, but approved-path/launched-command divergence, re-resolution, and replacement remain real. |
| XD-07 | Terra 5 | Sustained | Fixed environment-key removal proves only inherited-environment filtering, not filesystem, credential-helper, or network isolation. |
| XD-08 | Terra 4 | Sustained | Legacy home-path grants and repo-local hash records have incompatible authority; no migration/reapproval rule exists. |
| XD-09 | Terra 4 | Sustained | Plugin and transport validators are ordered before the canonical runtime schema and vocabulary are defined. |
| XD-10 | Terra 4 | Sustained | CLI loads config into `run`; MCP registers `__call__`. Schema equality cannot prove equivalent effective execution. |
| XD-11 | Terra 6 | Narrowed | Not every tool needs universal rename/delete objects, but every scoped tool needs a declared capability and enforced target allowlist with observed non-access. |
| XD-12 | Terra 4 | Narrowed | Raw cache persistence can be tested early, but retained execution caching still needs a complete collision-safe identity and an early retain/remove decision. |
| XD-13 | Terra 4 | Sustained | “No retry source pattern” does not prove one invocation after an internal `TypeError`; an observable side-effect test is required. |
| XD-14 | Terra 5 | Narrowed | The defect is the review-provider contract, not every provider subsystem. Review still needs completed/skipped/error outcomes and truthful labeling. |
| XD-15 | Terra 5 | Narrowed | An opaque token is required only if lock operations remain public; the plan must explicitly retain/migrate or remove them. |
| XD-16 | Terra 6 | Narrowed | Journal files do not share the map-store lost-update race; they need per-record atomicity/containment, while shared maps need transactions and public corrupt-vs-missing outcomes. |
| XD-17 | Terra 5 | Narrowed | A trusted builder is unnecessary if Rush ships only an unsigned draft; any optional signed mode needs trusted identity and independent verification. |
| XD-18 | Terra 1 | Narrowed | Ruff is implicitly exercised today, but no support taxonomy or pinned conformance matrix covers the broader advertised engine surface. |
| XD-19 | Terra 5 | Narrowed | Whether R-015 blocks release is a product choice, but its current completion condition is objectively undefined. |
| XD-20 | Terra 6 | Narrowed | Blanket live calls are unsafe; every advertised operation still needs a classified hermetic installed-artifact probe that reaches lazy imports. |
| XD-21 | Terra 1 | Narrowed | Phase 5 mentions several patch risks, but it does not prove the public command invokes verification, fails closed, rolls back, or confines cleanup. |
| XD-22 | Terra 1 | Sustained | `uv build` creates artifacts, but neither CI nor the plan installs/tests an sdist. Test it or explicitly prohibit publishing it. |
| XD-23 | Terra 1 | Sustained | Existing plugin tests exercise components directly, not the production CLI path, child environment, or post-approval mutation. |
| XD-24 | Sol | Narrowed without mandatory challenge | The evidence must say cache-management commands are production callers while execution key/get/set integration is absent. |

## Sol adjudications

Sol accepts every challenger narrowing above and sustains the surviving defect. No docket is dismissed. A narrowing removes unsupported breadth; it does not make the surviving issue optional.

| Docket | Sol decision | Mandatory disposition |
|---|---|---|
| XD-01 | Requires explicit uncertainty | Remove the unsupported exact/exhaustive claim unless Phase 0 produces an auditable manifest. |
| XD-02 | Sustained | Add a public-operation/legacy-disposition manifest and scoped parity rule. |
| XD-03 | Sustained | Strengthen installed-artifact isolation and origin proof. |
| XD-04 | Narrowed and sustained | Expand redaction to precise URL, key, persistence, and temporary-artifact boundaries. |
| XD-05 | Narrowed and sustained | Prevent the planned migration from making repo-controlled authorization authoritative. |
| XD-06 | Narrowed and sustained | Bind approval to the exact launch identity and remove/private bypasses. |
| XD-07 | Sustained | Choose and accurately describe environment-only filtering versus an actual OS sandbox. |
| XD-08 | Sustained | Define one user-owned authority and explicit legacy reapproval/migration. |
| XD-09 | Sustained | Move the runtime schema kernel before plugin and transport migration. |
| XD-10 | Sustained | Define one effective invocation resolver and semantic parity evidence. |
| XD-11 | Narrowed and sustained | Specify per-tool target capabilities and enforce/observe the exact allowlist. |
| XD-12 | Narrowed and sustained | Make the cache product decision early and fully specify identity if retained. |
| XD-13 | Sustained | Add a one-side-effect/one-invocation `TypeError` regression. |
| XD-14 | Narrowed and sustained | Add typed review-provider outcomes and a failure matrix. |
| XD-15 | Narrowed and sustained | Decide public lock disposition; migrate retained operations to capability tokens. |
| XD-16 | Narrowed and sustained | Split shared-map transactions from journal atomic records; expose corrupt state truthfully. |
| XD-17 | Narrowed and sustained | Default to unsigned draft; gate any signed mode on trusted independent verification and a pinned current format. |
| XD-18 | Narrowed and sustained | Publish an engine-support taxonomy and provisioned conformance matrix. |
| XD-19 | Narrowed and sustained | Separate release readiness from R-015 or define a complete metric contract; the revised plan must choose explicitly. |
| XD-20 | Narrowed and sustained | Probe every retained advertised operation hermetically from installed artifacts. |
| XD-21 | Narrowed and sustained | Register and gate the public patch-safety defect. |
| XD-22 | Sustained | Test sdist parity or explicitly prevent sdist publication. |
| XD-23 | Sustained | Reproduce R-003 through the production CLI in Phase 0. |
| XD-24 | Narrowed and sustained | Correct R-005 evidence and retain/admin classification. |

## Terra fix orders

Every order below is mandatory. An order changes the remediation plan, never Rush code.

| Fix order | Linked docket/findings | Exact plan correction | Required replacement behavior, sequence, gate, and closure |
|---|---|---|---|
| FO-001 | XD-01 / T1-001 | Review scope, coverage, Phase 0, baseline | Remove the unsupported “all 384” assertion. Phase 0 must generate a deterministic first-party file manifest covering `src`, `tests`, `scripts`, packaging/release/CI and classify exclusions such as local untracked `research/`. Closure: every repository-wide conclusion is scoped to that manifest. |
| FO-002 | XD-02 / T1-004, T2-005, T3-001, T5-001 | Phase 0, R-004, Phase 4, slices, parity gate | Before migration, create a versioned public-operation manifest. For all 25 legacy MCP operations and every Click leaf, record kind, retain/migrate/deprecate/remove, canonical implementation, CLI/MCP names and aliases, input schema, config policy, effect/permission class, result adapter, compatibility notice, and safe probe. Require one-to-one parity only for `kind=tool`; prohibit unclassified public routes. |
| FO-003 | XD-03 / T2-001, T6-001 | R-001, Phase 0/1, artifact gates, DoD | Run wheel/sdist CLI, import, and MCP probes from a new empty directory outside the checkout with scrubbed `PYTHONPATH`, no editable install, and isolated import probes. Assert loaded `rush.*` origins are in the installed environment and checkout `src` is absent. Include a deliberately broken `src.rush` negative control. |
| FO-004 | XD-04 / T2-002, T4-003 | R-002, Phase 2/5/6, redaction gate | Define the sanitizer over every serializable string position, including user-controlled mapping keys with collision handling, exception text, identifiers, URL userinfo/query/fragment and percent-encoding. Apply before every output and write: findings, summary/raw, logs, MCP/CLI, exports, cache, checkpoints, preferences, invariant/failure/merkle stores, trust receipts, provenance, temp/backup files. Gate all positions and aborted-write artifacts with fresh sentinels. |
| FO-005 | XD-05 / T4-001 | R-003, Phase 3, plugin gate | Make a user-owned, non-repository, link/junction-safe ledger the sole authorizing state. Repository receipts are non-authorizing evidence. Closure: a cloned repo with a matching plugin and `.rush/trust.json` remains denied until an explicit user grant. |
| FO-006 | XD-06 / T2-003, T4-002 | R-003, Phase 3, plugin gate | Remove/private `allow_untrusted`; define an immutable approved launch spec; require the verified absolute executable (or explicitly modeled interpreter plus script) to be exactly what is launched without PATH/cwd re-resolution. Reject command/path mismatch, PATH shadowing, symlink/batch indirection, and synchronized validate-to-spawn replacement before child start. State any platform residual uncertainty rather than claiming impossible race elimination. |
| FO-007 | XD-07 / T2-004 | R-003 impact, Phase 0 decision, Phase 3/gate | Explicitly choose: (A) environment-only hardening, documenting that approved plugins remain trusted user-code with ambient filesystem/network authority, or (B) a real OS/container sandbox with isolated home/config, mounts/ACLs, helpers and network. Until B exists, replace broad “credentials never reach plugin” claims with exact inherited-environment guarantees and adversarial tests. |
| FO-008 | XD-08 / T3-003 | R-003, Phase 3/5, slice dependencies | Select one user-owned versioned trust-store authority and grant/revoke UX. Legacy repo-path grants must not silently authorize the new command identity; require explicit reapproval or a user-confirmed upgrade that records all new binding fields. Make trust-receipt atomic persistence a prerequisite or part of the same slice. |
| FO-009 | XD-09 / T3-004, T5-005 | R-011, phases and slices, result gate | Insert a schema-kernel slice before plugins/MCP/cache. Define runtime `ToolResultV1`/`FindingV1`: schema version, required envelope/finding fields, exact status/severity enums, canonical structured errors, JSON-safe recursive values, extension namespace and serializer. Every producer/boundary must use the same validator; malformed input becomes a canonical error. |
| FO-010 | XD-10 / T5-002 | R-004/R-005/R-007, Phase 4, parity gate | Define one internal `resolve_invocation(request, transport)` and `execute(context)` path that contains/canonicalizes target, determines repository/workspace root, loads effective config, derives explicit permissions, resolves target set and cache policy. MCP must not accept a mutable config object. Gate semantic CLI/stdio equality with non-default config, permissions, roots, relative/absolute paths and workspace selection. |
| FO-011 | XD-11 / T2-006, T3-002 | R-005, Phase 4, scope gate | Define ordered target entries, selection provenance and per-tool capabilities for present/deleted/renamed/directory/aggregate/repository-wide work. Scoped tools receive an immutable allowlist and never widen silently; declared repository-wide exceptions use a distinct contract. Observe engine argv/filesystem access with traps, including empty, rename/delete and workspace aggregation cases. |
| FO-012 | XD-12 / T3-005, T5-003 | R-005, Phase 0 decision, Phase 2/4, cache gate | Decide in Phase 0 whether execution caching is retained. If deferred, remove `--no-cache` and public execution-cache claims while classifying admin commands. If retained, key only pure validated results by schema, canonical root/workspace, ordered target identities/content/state, config digest, engines/versions, behavior args and permissions; define cacheable statuses and bypass read/write semantics. Test cross-directory and target mutation collisions through the real path. |
| FO-013 | XD-13 / T2-007 | R-006, Phase 4/gate | Centralize registration-time signature adaptation. Through CLI and MCP, an instrumented tool that performs one side effect then raises internal `TypeError` must execute once and return one canonical error; unsupported signatures fail registration. |
| FO-014 | XD-14 / T2-008, T4-004 | R-007, Phase 4/gate | Give review providers discriminated `completed|skipped|error` outcomes with sanitized request/completion evidence. Only a schema-valid non-empty successful completion may set `review_kind=llm`. Gate no-key, denied network, redirect, DNS/timeout, HTTP error, malformed/empty response and success for both providers; never persist credentials in evidence. |
| FO-015 | XD-15 / T2-009 | R-009, public-operation manifest, Phase 4/5/gate | Decide retain/remove for lock MCP operations. If retained, acquisition returns a holder-only unguessable capability; release/renew require it; inspect/logs never expose it; deprecate bool/agent-ID authority. Gate reused IDs, guessed/stale tokens, renewal, crash/stale recovery and live MCP behavior. |
| FO-016 | XD-16 / T1-003, T2-010, T3-006 | R-010, Phase 5/gate | Correct R-010 evidence. Shared-map stores require lock/CAS across read-validate-mutate-fsync/replace with barrier tests. Checkpoint records require class-level containment, atomic per-record replace, corrupt retention and explicit same-name policy. Public operations distinguish absent (`skipped`) from corrupt/invalid/I-O (`error`) and lists report retained corruption. |
| FO-017 | XD-17 / T2-011 plus Sol primary-source check | R-013, Phase 6, provenance gate | Make local output an unsigned provenance draft by default. Pin the implementation to a selected supported in-toto/SLSA schema and cite primary specs; as of review, SLSA v1.2 uses predicate `https://slsa.dev/provenance/v1` and in-toto Statement v1, while current code emits v0.2/v0.1. Require an actual artifact digest. Any signed mode needs trusted signer-builder roots, envelope and subject/predicate verification; reject self-signed/unknown/mutated cases. |
| FO-018 | XD-18 / T2-012, T6-005 | R-014, Phase 0, engine gate | Publish engine support classes: mandatory, supported optional, best-effort. Keep deterministic tests on fixed PATH; provision pinned success/failure/malformed jobs for every supported family, record resolved executable/version, and permit unavailable skip only where policy allows. All-skipped conformance cannot satisfy the supported matrix. |
| FO-019 | XD-19 / T2-013, T3-007, T6-006 | R-015, Phase 7, slice 10, gates, DoD | Choose explicitly: R-015 is a non-release program after correctness release, or it remains release-gating with pinned metric/tool/version, named symbols, numeric threshold, baseline, characterization tests and expiring exemptions. The revised plan must distinguish “release ready” from “remediation program complete”; no future undefined agreement may decide completion. |
| FO-020 | XD-20 / T5-004 | Phase 0/4 and installed MCP gates | Generate installed probes from live `tools/list`. Pure tools use fixtures; engine-backed tools exercise fixture and missing-engine paths; write/network/destructive tools use dry-run or injected fakes; operations without a safe probe are not advertised. Every probe must reach lazy imports off-checkout and return a validated result, intentional skip/error, and clean stdout. |
| FO-021 | XD-21 / T6-002 | Add R-016; coverage, Phase 0/patch phase, slices, release gates, DoD | Register “public patch test can report verification without tests and has fail-open sandbox/cleanup/rollback risks” as R-016. Require `PatchVerifier` after successful apply or remove the verification claim; fail closed on worktree creation/verifier unavailability; keep checkout unchanged; confine cleanup to manager-owned resolved paths; unique temp files; rollback/direct-apply sandbox-only policy; containment/symlink/concurrency tests. R-016 is release-blocking while the command is public. |
| FO-022 | XD-22 / T6-003 | R-001, Phase 0/1, artifact matrix/gate/DoD | Because `uv build` produces wheel and sdist for publication, independently install/test both on Windows and POSIX with FO-003 probes. Alternative only if release policy explicitly disables/prevents sdist publication. |
| FO-023 | XD-23 / T6-004 | Phase 0, R-003, slice 1 | Add a failing pre-change production-route `CliRunner` plugin fixture. Establish legacy trust, run `rush plugin run`, have the child report a sentinel inherited variable, mutate config/command/executable after approval, and prove the unfixed bypass. Preserve this fixture through migration with inverted safe expectations. |
| FO-024 | XD-24 / T1-002 | R-005 evidence and cache disposition | Replace “no production callers” with “cache-management commands construct `ResultCache`, but generic execution has no production `compute_cache_key`/`get`/`set` path.” Preserve/admin-test `cache stats/clean` or disposition them in FO-002; do not erase their public contract accidentally. |

## Summary of plan revisions made

Exactly one Terra remediator—Terra 3—was authorized to edit the plan. Sol remained the orchestrator, adjudicator, review-artifact author, and final reviewer. No Rush source, test, configuration, CI, release, or dependency file was changed.

| Revision | SHA-256 | Purpose |
|---|---|---|
| Frozen first-round plan | `E30A02400494F50C6005616C3527B5635973B06DDDCA64D5948D36AD3D770A50` | Immutable target for the six-role first attack and cross-examination. |
| First remediation | `17E54EE1604E65860E0BCDAAD84E199F27C21C6E89B02B2A60E65E187064FFCA` | Applied FO-001 through FO-024. |
| Second remediation | `462349C27EB8980407274AD593AD7D7A84623BD06354210D0E1D472F632E16B7` | Closed the first post-remediation P0/P1 attack. |
| Third remediation | `2BD8CA6AF2F0968ADC05B0F734050F02B2D0E2102648A1F58745A00A5440F7AB` | Closed output-class, lock-channel, patch-policy, ignored-input, plugin-secret, and duplicate-JSON findings. |
| Final targeted remediation | `783C82DD101EC3A379F8710C33B513FB2CAEB265568576B94FD7D25A67314B2D` | Required protected child-secret transports and same-user observer proof. |

The final plan:

- replaces unsupported exhaustive coverage language with committed coverage and public-operation manifests;
- separates operation kinds, output contracts, and transport-specific installed probes;
- makes wheel and sdist isolation, redaction, schema, physical-target, cache, provider, engine, and provenance gates executable;
- replaces repository-controlled plugin authority with a user-owned ledger, secret-free content-addressed snapshots, protected secret references, and fail-closed non-substitutable launch;
- introduces an owned `AtomicFile` prerequisite, verifier-only lock metadata, distinct map/journal semantics, and physical containment;
- registers R-016 and binds patch success to clean target state, trusted verification policy, declared inputs, and an actually executed required command;
- separates correctness release readiness from the non-release R-015 maintainability program.

The provenance contract was checked against [SLSA v1.2](https://slsa.dev/spec/v1.2/), [in-toto Statement v1](https://github.com/in-toto/attestation/blob/main/spec/v1/statement.md), and the [SLSA artifact-verification guidance](https://slsa.dev/spec/v1.2/verifying-artifacts).

## Second-round attack findings

The first revised hash was attacked independently by security/trust, contract/artifact, and execution/release roles. Because blockers survived, the same sole remediator revised the plan and the attackers repeated targeted attacks until closure.

| Finding(s) | Severity | Surviving attack | Sol disposition and final closure |
|---|---:|---|---|
| S2-T2-001 | P0 | An approved interpreter/script could load mutated transitive local code. | Sustained. Final lines 299-306 and 384 require a complete secret-free content-addressed runtime closure or deny the mode. |
| S2-T4-001 | P0 | Validation-to-spawn replacement could execute unapproved bytes while merely documenting residual risk. | Sustained. Lines 22, 303, 306, 384, and 408 require approved bytes or no child and disable unsupported platforms. |
| S2-T6-001 | P1 | Phase 3 required universal schema migration before later adapters existed. | Sustained. Lines 273-282 limit Phase 3 to the kernel; lines 321-334 and 392 defer eligible-boundary enforcement. |
| S2-T6-002 | P1 | Plugin trust receipts depended cyclically on an unowned later persistence primitive. | Sustained. Lines 284-293 and Slice 5 own `AtomicFile` before plugin migration. |
| S2-T6-003 | P1 | `tools/list` could not drive probes for retained Click-only/service operations. | Sustained. Lines 240-241, 315, and 379-381 make probes manifest- and transport-driven. |
| S2-T6-004 / S2-T2-004 | P1 | Patch verification could succeed after executing zero required commands. | Sustained. Lines 329-334 and 391 require a bound selected command to execute successfully. |
| S2-T2-002 | P1 | A raw lock capability could be recovered from repository metadata. | Sustained. Lines 24, 291, 325-326, and 389 use caller-generated secrets and verifier-only storage. |
| S2-T2-003 | P1 | Shared maps/locks lacked the link/junction containment required of journals. | Sustained. Lines 288-293, 327-328, 383, and 390 apply one physical-containment policy to every boundary. |
| S2-T2-005 | P1 | Patch verification used `HEAD` without binding the intended dirty/untracked target state. | Sustained. Lines 329-330 and 391 reject or bind target state, policy, and declared inputs. |
| S2-T2-006 | P1 | Signed provenance did not authorize the signer-builder/build-definition relationship. | Sustained. Lines 340-345 and 395 pin signer/build/predicate/source policy and strict parsing. |
| S2-T4-002 | P1 | Lexically allowlisted targets could escape through links/junctions. | Sustained. Lines 312-313, 319, and 386 require physical identity, revalidation, and outside-sentinel traps. |
| S2-T4-003 | P1 | Cache keys omitted Rush artifact/tool behavior identity. | Sustained. Lines 312, 316, 319, and 387 require build plus tool/normalizer revisions and cross-build misses. |
| S2-T4-004 | P1 | Provider redirects/proxies could exfiltrate prompt or credentials while still completing. | Sustained. Lines 317, 319, and 388 bind completion to an approved HTTPS origin and explicit proxy policy. |
| S2-T4-005 | P1 | The coverage manifest omitted public documentation containing assurance claims. | Sustained. Lines 29, 239, 257, and 378 include shipping documentation and manifest-scoped assurance scans. |
| S2-SOL-001..003 | P2 | Severity migration, child-environment policy, and sanitizer-versus-semantic-input behavior remained ambiguous. | Sustained. Lines 244, 266-282, 301-306, 382, and 384 choose exact mappings, default-deny forwarding, and non-mutating input handling. |

Further literal re-review found and closed these issues:

| Finding(s) | Severity | Closure |
|---|---:|---|
| S3-T4-001 | P1 | Lines 23, 245, 300-306, 382, and 384 reject literal plugin secrets and permit only named protected references. |
| S3-T6-001 | P1 | Lines 240, 279-282, 332, 379, and 392 distinguish tool, admin, and service output contracts. |
| S3-T6-002 / S3-T2-001 | P1 | Lines 24, 325-326, and 389 define caller-generated, request-only lock capabilities and transport handling. |
| S3-T6-003 | P1 | Lines 329-330 and 391 bind the verification plan/configuration to the clean base or trusted manifest. |
| S3-T2-002 | P1 | Lines 240-241, 312-313, 319, 329-330, 386, and 391 bind or reject ignored host inputs under controlled roots. |
| S3-T2-003 | P2 | Lines 342, 345, and 395 reject duplicates and ambiguous keys throughout envelope, Statement, predicate, and nested policy objects. |
| S4-T4-001 | P1 | Lines 23, 245, 300-306, 368, 382, 384, and 408 forbid argv/environment/file delivery and require protected descriptor/stdin/credential-provider transport plus same-user observation. |

Closure re-checks against hash `2BD8...F7AB` found no P0/P1 in the execution/release or contract attack, and the final targeted security check against hash `783C...14B2D` found no surviving P0/P1.

## Closure evidence for every sustained finding

These are plan-contract closures, not claims that Rush has already been remediated.

| Docket / fix order | Final plan closure evidence |
|---|---|
| XD-01 / FO-001 | Lines 12, 29-31, 239, and 378 establish manifest-scoped claims and remove the unsupported exact count. |
| XD-02 / FO-002 | Lines 240-242, 279, 315, and 379-381 classify every public operation, contract, disposition, and probe. |
| XD-03 / FO-003 | Lines 243, 255-260, and 380 require external-CWD installed-origin proof and a `src.rush` negative control for both artifacts. |
| XD-04 / FO-004 | Lines 244, 266-271, and 382 cover keys, URLs, exceptions, persistence, temporary/aborted artifacts, and semantic-input safety. |
| XD-05 / FO-005 | Lines 21, 299, and 384 make repository receipts non-authorizing and require explicit user authority. |
| XD-06 / FO-006 | Lines 299-306 and 384 bind and launch a verified snapshot/runtime identity or fail closed. |
| XD-07 / FO-007 | Lines 20, 302-304, and 384 explicitly choose environment-only hardening and deny broader sandbox claims. |
| XD-08 / FO-008 | Lines 21 and 299-301 define one user-owned authority and explicit legacy reapproval. |
| XD-09 / FO-009 | Lines 273-282, 332, and 392 place a versioned schema kernel before adapters and gate eligible boundaries afterward. |
| XD-10 / FO-010 | Lines 312-319 and 385 define one resolver/executor and semantic CLI/stdio evidence. |
| XD-11 / FO-011 | Lines 312-313, 319, and 386 define physical target capabilities, immutable allowlists, and observed containment. |
| XD-12 / FO-012 | Lines 19, 312, 316, and 387 retain caching with complete behavioral identity and read/write bypass. |
| XD-13 / FO-013 | Lines 314 and 385 require one observed side effect, one invocation, and one canonical error after internal `TypeError`. |
| XD-14 / FO-014 | Lines 317, 319, and 388 define truthful provider outcomes and the full failure/egress matrix. |
| XD-15 / FO-015 | Lines 24, 291, 325-326, and 389 retain locks with caller-held capabilities, verifier-only metadata, and live transport tests. |
| XD-16 / FO-016 | Lines 288-293, 327-328, 383, and 390 separate map transactions from journals while sharing atomic containment and truthful errors. |
| XD-17 / FO-017 | Lines 340-345 and 395 make unsigned draft the default and gate signed mode on current pinned identity/policy verification. |
| XD-18 / FO-018 | Lines 247, 343, and 393 define support classes and a non-skippable provisioned conformance matrix. |
| XD-19 / FO-019 | Lines 25, 347-357, and 408-410 make R-015 non-release while preserving measurable program completion. |
| XD-20 / FO-020 | Lines 240-241, 315, and 381 run a safe installed probe for every retained operation according to its transport. |
| XD-21 / FO-021 | Lines 221-231, 329-334, and 391 register R-016 and make target, policy, command execution, rollback, and cleanup fail closed. |
| XD-22 / FO-022 | Lines 18, 243, 258, 380, and 408 independently install and gate wheel and sdist on Windows/POSIX. |
| XD-23 / FO-023 | Lines 245 and 384 preserve the production CLI plugin fixture and invert it into the final mutation/secret gate. |
| XD-24 / FO-024 | Lines 19, 242, 316, and 387 correctly distinguish cache admin callers from absent execution integration and preserve both contracts. |

## Open issues or explicit blockers

No P0 or P1 plan defect remains after the final targeted attack.

Non-blocking follow-ups are explicit rather than hidden assumptions:

- R-015 remains a post-release program. Its metric implementation, version, baseline, numeric thresholds, and expiring exemptions must be pinned in its first PR before refactoring, as required by lines 347-357.
- Platform-specific handle/no-follow and protected-secret-channel feasibility must be demonstrated during implementation. The plan already requires the affected plugin or protected operation to fail closed where the guarantee is unavailable.
- Signed provenance remains optional and disabled by default until the complete signer-builder and verification policy exists.
- This review accepts the remediation **plan** only. Rush is not release ready until its code changes and every release gate passes on both installed artifact families.

## Final Sol decision

**Accepted with explicit non-blocking follow-ups.**

The final plan at SHA-256 `783C82DD101EC3A379F8710C33B513FB2CAEB265568576B94FD7D25A67314B2D` is accurate enough to execute, assigns prerequisites without a dependency cycle, distinguishes product decisions from evidence, and prevents the reviewed false-success paths from satisfying release readiness. The final execution/release, contract, and targeted security re-checks report no remaining P0/P1.

Acceptance is confined to the two requested documentation artifacts. It does not certify the current Rush implementation, authorize a release, or waive any gate in the plan.
