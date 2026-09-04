# Phase 57 implementation plan — invocation, physical scope, public operations, cache, and provider egress

## 1. Purpose and status

- **Operation:** Create the implementation plan for remediation Phase 6.
- **Planning status:** Implementation-ready after §4 admission passes.
- **Implementation status:** Not authorized.
- **Authority:** governing roadmap R-004 through R-007.
- **Predecessors:** accepted Phase 51 operation manifest, Phase 52 artifact identity, Phase 53 sanitizer, Phase 54 adapters, Phase 55 PhysicalRoot.
- **Successor:** Phase 58 completes eligible output migration.
- **Protected:** roadmap, dependencies/lockfile, plugin/lock/persistence/patch internals.
- **Amendment rule:** Any transport exception, context field, cache identity, public route disposition, provider origin, or path outside a card requires amendment.
- **Lifecycle boundary:** No commit, push, merge, tag, publish, release, hooks, history rewrite, live provider, or live credential.

## 2. Authority, evidence, and decisions

Authority order: user → `AGENTS.md` → roadmap → Phases 51-55 contracts → current CLI/MCP/catalog/cache/provider/test evidence.

Current evidence: CLI/MCP construct divergent inputs; scoped selections can widen through paths/ignored host inputs; execution retries on `TypeError`; public routes can bypass canonical implementations; cache is admin-only and lacks invocation identity; provider errors/redirects can be mislabeled as LLM output.

Closed decisions: one immutable `InvocationContext`; MCP accepts declared request values, never mutable config; physical target states are `present|deleted|renamed`; signature adaptation happens once at registration; only manifest-declared pure operations cache; missing identity is bypass, never default salt; `--no-cache` bypasses both read/write; LLM label requires schema-valid non-empty completion from approved effective HTTPS origin.

Open decisions: None. Any semantic transport exception must be added to the operation manifest first.

## 3. Goals, outcomes, exclusions, and invariants

Outcomes: equivalent CLI/MCP contexts; contained immutable targets; one execution per request; every retained route reaches its declared implementation/adapter; cache keys bind all behavior identities and cache values remain sanitized/valid; provider outcome/origin truth.

Exclusions: plugin execution, lock/persistence/patch migration, dependency changes, live egress.

Invariant: no transport silently changes semantics, scope, permissions, cache identity, operation contract, or provider origin.

## 4. Admission and predecessor gate

Require accepted predecessor artifacts and installed wheel/sdist identities. Reconcile every retained operation and inspect resolver/executor/cache/provider call paths. Record overlapping edits. P57.0.1 must assign every context input, target selector, callable signature, cache identity, and provider branch before RED tasks.

## 5. Requirement-ownership ledger

| Requirement | Tasks | Closure |
|---|---|---|
| Immutable equivalent contexts | P57.1.1-P57.1.2 | CLI/MCP context matrix |
| Physical scope and ignored inputs | P57.2.1-P57.2.2 | Windows/POSIX trap matrix |
| Registration signature/one execution | P57.3.1-P57.3.2 | side-effect TypeError tests |
| Public-operation dispositions | P57.4.1-P57.4.2 | installed manifest probes |
| Cache key/eligibility | P57.5.1-P57.5.2 | identity mutation matrix |
| Cache read/write result boundary | P57.5.3-P57.5.4 | no-cache/malformed/sentinel matrix |
| Provider outcome/effective origin | P57.6.1-P57.6.2 | fake redirect/proxy/error matrix |
| Docs/handoff | P57.7.1 | named docs and Phase 58 inventory |

## 6. Shared contracts and handoff

`InvocationContext` contains canonical repository/workspace root, transport, operation ID/kind, physical targets and selection provenance/state/capability, effective configuration digest, permissions, ordered arguments, declared ignored-input identities, cache policy, installed artifact/build identity, tool/normalizer behavior revisions, and controlled environment/config roots.

`CacheDecision` is `eligible|bypass` with a stable reason. `build_cache_key` accepts a complete immutable context plus target content/state identities and returns no key when any required identity is absent. Cache integration sanitizes and validates ToolResultV1 before set and after get.

Provider outcomes are `completed|skipped|error`; `review_kind=llm` only after approved effective-origin completion.

## 7. Contract-test inventory

| Contract | RED | GREEN | Exact ordinary tests |
|---|---|---|---|
| Context | P57.1.1 | P57.1.2 | `test_cli_and_mcp_resolve_equivalent_context`; `test_mcp_request_never_receives_mutable_config` |
| Scope | P57.2.1 | P57.2.2 | `test_target_states_and_selection_provenance_are_immutable`; `test_link_junction_and_swap_cannot_widen_scope`; `test_undeclared_host_input_refuses` |
| Signature | P57.3.1 | P57.3.2 | `test_internal_typeerror_after_side_effect_executes_once`; `test_unsupported_signature_fails_registration`; `test_cli_mcp_signature_error_is_equivalent` |
| Operations | P57.4.1 | P57.4.2 | `test_every_retained_operation_reaches_manifest_implementation`; `test_only_tool_pairs_require_semantic_parity`; `test_unprobed_route_is_not_advertised` |
| Cache identity | P57.5.1 | P57.5.2 | `test_cache_key_binds_every_context_and_target_identity`; `test_missing_identity_returns_bypass_without_key`; `test_artifact_behavior_config_permission_target_mutation_misses` |
| Cache execution | P57.5.3 | P57.5.4 | `test_no_cache_performs_no_read_or_write`; `test_cache_set_requires_sanitized_valid_tool_result`; `test_cache_get_resanitizes_and_revalidates`; `test_only_manifest_pure_operation_uses_cache` |
| Provider | P57.6.1 | P57.6.2 | `test_denied_redirected_failed_or_empty_work_is_not_llm`; `test_cross_origin_redirect_receives_no_authorization_or_prompt`; `test_approved_effective_origin_completion_is_llm` |

## 8. File, dependency, and documentation governance

New: `src/rush/invocation/__init__.py`, `src/rush/invocation/models.py`, `src/rush/invocation/resolver.py`, `src/rush/invocation/targets.py`, `src/rush/invocation/executor.py`, `src/rush/invocation/cache_policy.py`, `tests/test_phase57_invocation_context.py`, `tests/test_phase57_physical_scope.py`, `tests/test_phase57_public_operations.py`, `tests/test_phase57_cache_policy.py`, `tests/test_phase57_provider_egress.py`.

Existing task-owned: `src/rush/cli.py`, `src/rush/mcp.py`, `src/rush/catalog.py`, `src/rush/cache.py`, `src/rush/config.py`, `src/rush/permissions.py`, `src/rush/tools/__init__.py`, `src/rush/tools/base.py`, `src/rush/tools/common.py`, `src/rush/tools/review.py`, `src/rush/providers/__init__.py`, `src/rush/providers/base.py`, `src/rush/providers/openai.py`, `src/rush/providers/anthropic.py`, `src/rush/providers/registry.py`, `src/rush/contracts/operations.py`, `src/rush/contracts/results.py`, `src/rush/io/physical_paths.py`, `governance/public-operations.toml`, `governance/remediation-contracts.toml`, `tests/test_cli.py`, `tests/test_cli_registry.py`, `tests/test_mcp.py`, `tests/test_cache.py`, `tests/test_permissions.py`, `tests/test_review.py`, `tests/test_executed_modes.py`.

Docs owned only by P57.7.1: `docs/CLI_REFERENCE.md`, `docs/MCP_REFERENCE.md`, `docs/CONFIGURATION.md`, `docs/CONFIG_SCHEMA.md`, `docs/TOOL_CATALOG.md`, `docs/SCOPE.md`, `docs/ENVIRONMENT_VARIABLES.md`, `docs/PRIVACY.md`, `docs/SECURITY.md`, `docs/reference/configuration-reference.md`, `docs/safety/permissions.md`.

All other writes prohibited. Dependency changes: None. Required existing dependencies/contracts: Phase 52 artifact identity, Phase 53 sanitizer, Phase 54 output adapters, Phase 55 physical containment, and the existing provider HTTP/runtime stack.

## 9. Ordered workstreams and atomic task cards

### P57.0 — Admission

#### P57.0.1 — EVIDENCE: map request-to-execution identities and branches

- **Task ID and binary outcome:** P57.0.1; every input/selector/signature/route/cache identity/provider branch maps to one task.
- **Start goal:** Freeze exact execution scope.
- **Prerequisites:** §4.
- **Documentation impact:** None.
- **Dependency impact:** None.
- **Allowed writes:** R-004-R-007 admission fields in `governance/remediation-contracts.toml`.
- **Allowed reads:** `src/rush/cli.py`, `src/rush/mcp.py`, `src/rush/catalog.py`, `src/rush/cache.py`, `src/rush/config.py`, `src/rush/permissions.py`, `src/rush/tools/__init__.py`, `src/rush/tools/base.py`, `src/rush/tools/common.py`, `src/rush/tools/review.py`, `src/rush/providers/__init__.py`, `src/rush/providers/base.py`, `src/rush/providers/openai.py`, `src/rush/providers/anthropic.py`, `src/rush/providers/registry.py`, `src/rush/contracts/operations.py`, `src/rush/contracts/results.py`, `src/rush/io/physical_paths.py`, `governance/public-operations.toml`, `governance/remediation-contracts.toml`, `tests/test_cli.py`, `tests/test_cli_registry.py`, `tests/test_mcp.py`, `tests/test_cache.py`, `tests/test_permissions.py`, `tests/test_review.py`, `tests/test_executed_modes.py`.
- **Prohibited:** source/tests/docs/dependencies/live egress.
- **Actions:** 1. Inspect public call paths and callers. 2. Record exact fields, symbols, current divergence, task owner, and ignored inputs. 3. Reconcile every manifest route/cache/provider branch and reparse TOML.
- **Evidence:** identity/branch/call-path table.
- **Stop:** any retained route or behavior identity is unowned.
- **Verified outcome:** P57.1.1-P57.6.1 may start.

### P57.1 — Invocation context

#### P57.1.1 — RED: define equivalent immutable CLI/MCP contexts

- **Task ID and binary outcome:** P57.1.1; two table-driven tests fail on current divergence/mutability.
- **Start goal:** Pin every §6 context field across transports.
- **Prerequisites:** P57.0.1.
- **Documentation impact:** None.
- **Dependency impact:** None.
- **Allowed writes:** create `tests/test_phase57_invocation_context.py`.
- **Allowed reads:** `src/rush/cli.py`, `src/rush/mcp.py`, `src/rush/config.py`, `src/rush/permissions.py`, contracts/manifests.
- **Prohibited:** production/docs/skip/XFAIL.
- **Actions:** 1. Arrange non-default config, permissions, roots, relative/absolute paths, workspace, staged/changed/since/aggregation for CLI and MCP. 2. Add exactly two §7 context tests against planned `resolve_invocation(request, transport)`. 3. Run focused file with permissions tests and record behavior failures.
- **Evidence:** input/expected-context matrix and red output.
- **Stop:** transport exception is not manifest-declared.
- **Verified outcome:** P57.1.2 may create models/resolver.

#### P57.1.2 — GREEN: resolve one immutable context before execution

- **Task ID and binary outcome:** P57.1.2; eligible CLI/MCP requests produce equal immutable contexts.
- **Start goal:** Satisfy P57.1.1 only.
- **Prerequisites:** recorded P57.1.1 RED.
- **Documentation impact:** None.
- **Dependency impact:** None.
- **Allowed writes:** create `src/rush/invocation/__init__.py`, `src/rush/invocation/models.py`, `src/rush/invocation/resolver.py`; modify `src/rush/cli.py`, `src/rush/mcp.py`, `src/rush/config.py`, `src/rush/permissions.py`, `tests/test_phase57_invocation_context.py`.
- **Allowed reads:** P57.1.1 evidence and operation manifest.
- **Prohibited:** target resolution/execution/cache/provider behavior/docs.
- **Actions:** 1. Authorize immutable models and resolver plus adapter request construction. 2. Resolve all §6 non-target fields once; MCP copies declared request values and never receives mutable config. 3. Run focused, permissions, CLI, and MCP tests.
- **Evidence:** green context matrix.
- **Stop:** hidden transport branch is required.
- **Verified outcome:** P57.2.1/P57.3.1/P57.5.1 may consume context.

### P57.2 — Physical scope

#### P57.2.1 — RED: define target states, containment, and ignored-input refusal

- **Task ID and binary outcome:** P57.2.1; three tests fail on current widening/identity behavior.
- **Start goal:** Pin empty/present/deleted/renamed, selectors, links/swaps, outside sentinel, generated/config inputs.
- **Prerequisites:** P57.1.2 and Phase 55.
- **Documentation impact:** None.
- **Dependency impact:** None.
- **Allowed writes:** create `tests/test_phase57_physical_scope.py`.
- **Allowed reads:** current selector/tool launch paths and PhysicalRoot.
- **Prohibited:** production/docs/XFAIL.
- **Actions:** 1. Arrange Windows/POSIX target trap matrix and immutable allowlist spy. 2. Add exactly three §7 scope tests through invocation resolver/executor boundary. 3. Run focused file and record failures.
- **Evidence:** trap matrix, outside digest, red output.
- **Stop:** selector semantics are absent from operation manifest.
- **Verified outcome:** P57.2.2 may create targets module.

#### P57.2.2 — GREEN: bind and revalidate physical target allowlists

- **Task ID and binary outcome:** P57.2.2; scope cannot widen/escape and undeclared ignored inputs refuse.
- **Start goal:** Satisfy P57.2.1 only.
- **Prerequisites:** recorded P57.2.1 RED.
- **Documentation impact:** None.
- **Dependency impact:** None.
- **Allowed writes:** create `src/rush/invocation/targets.py`; modify `src/rush/invocation/models.py`, `resolver.py`, `src/rush/io/physical_paths.py`, `src/rush/tools/common.py`, `tests/test_phase57_physical_scope.py`.
- **Allowed reads:** P57.2.1 evidence and operation selector contracts.
- **Prohibited:** broad fallback/cache/provider/docs.
- **Actions:** 1. Reinspect every selector/trap. 2. Create physical target entries with provenance/state/capability, bind declared ignored identities, revalidate before launch, pass immutable allowlist. 3. Run focused on Windows/POSIX and existing executed-mode tests.
- **Evidence:** green traps and unchanged outside digest.
- **Stop:** target cannot be represented; refuse rather than use original broad path.
- **Verified outcome:** execution/cache can consume stable targets.

### P57.3 — One execution

#### P57.3.1 — RED: expose runtime TypeError retry

- **Task ID and binary outcome:** P57.3.1; three tests fail because internal TypeError can execute twice.
- **Start goal:** Pin registration-time adaptation and canonical errors.
- **Prerequisites:** P57.1.2.
- **Documentation impact:** None.
- **Dependency impact:** None.
- **Allowed writes:** create `tests/test_phase57_public_operations.py`.
- **Allowed reads:** registries, CLI/MCP executors, existing registry tests.
- **Prohibited:** production/public dispositions/docs/XFAIL.
- **Actions:** 1. Arrange supported signatures, unsupported signature, side-effect counter then internal TypeError. 2. Add exactly three §7 signature tests through registered CLI/MCP operations. 3. Run focused plus registry tests and record counter/error failures.
- **Evidence:** red outputs and counter values.
- **Stop:** test bypasses registration.
- **Verified outcome:** P57.3.2 may create executor/adaptation.

#### P57.3.2 — GREEN: adapt signatures once and execute once

- **Task ID and binary outcome:** P57.3.2; supported operations execute once; unsupported signatures fail registration.
- **Start goal:** Satisfy P57.3.1 only.
- **Prerequisites:** recorded P57.3.1 RED.
- **Documentation impact:** None.
- **Dependency impact:** None.
- **Allowed writes:** create `src/rush/invocation/executor.py`; modify `src/rush/catalog.py`, `src/rush/tools/__init__.py`, `src/rush/cli.py`, `src/rush/mcp.py`, `tests/test_phase57_public_operations.py`, `tests/test_cli_registry.py`.
- **Allowed reads:** P57.3.1 evidence and contracts.
- **Prohibited:** public disposition/cache/provider/docs.
- **Actions:** 1. Reinspect registration/call sites. 2. Inspect/adapt supported callable signatures at registration, store adapter, remove runtime TypeError retry, map canonical error. 3. Run focused, registry, CLI, MCP tests and assert side-effect count one.
- **Evidence:** green signature matrix.
- **Stop:** support requires runtime exception guessing.
- **Verified outcome:** P57.4.1 may test all routes.

### P57.4 — Public operations

#### P57.4.1 — RED: execute every retained manifest disposition

- **Task ID and binary outcome:** P57.4.1; operation tests fail on bypass/unprobed/incorrect parity behavior.
- **Start goal:** Pin canonical implementations and contract classes.
- **Prerequisites:** P57.2.2, P57.3.2, Phase 54 registry.
- **Documentation impact:** None.
- **Dependency impact:** None.
- **Allowed writes:** `tests/test_phase57_public_operations.py`, `tests/test_cli.py`, `tests/test_mcp.py`.
- **Allowed reads:** public-operation manifest, transport registrations, installed probe harness.
- **Prohibited:** production/manifest/docs/XFAIL.
- **Actions:** 1. Arrange one probe per retained operation ID and transport. 2. Add exactly three §7 operation tests plus `test_admin_and_service_keep_named_contracts`. 3. Run focused files and record failures.
- **Evidence:** operation/transport red matrix.
- **Stop:** route lacks Phase 51 disposition.
- **Verified outcome:** P57.4.2 may change registrations/manifest.

#### P57.4.2 — GREEN: route retained operations through declared implementations

- **Task ID and binary outcome:** P57.4.2; every advertised route passes its contract-correct probe.
- **Start goal:** Satisfy P57.4.1 only.
- **Prerequisites:** recorded P57.4.1 RED.
- **Documentation impact:** None.
- **Dependency impact:** None.
- **Allowed writes:** `src/rush/cli.py`, `src/rush/mcp.py`, `src/rush/catalog.py`, `src/rush/contracts/operations.py`, `src/rush/contracts/results.py`, `governance/public-operations.toml`, `tests/test_phase57_public_operations.py`, `tests/test_cli.py`, `tests/test_mcp.py`.
- **Allowed reads:** P57.4.1 evidence and canonical tools.
- **Prohibited:** tool logic duplication, forcing admin/service to ToolResult, cache/provider/docs.
- **Actions:** 1. Reinspect each failing route. 2. Point retained routes at canonical implementation/adapter, emit declared deprecation, remove only explicitly deprecated/unprobed advertising. 3. Run focused, Phase 51 reconciliation, and installed wheel/sdist probes.
- **Evidence:** green operation matrix.
- **Stop:** route behavior/class must change beyond manifest.
- **Verified outcome:** public operation contract is closed.

### P57.5 — Cache identity and execution

#### P57.5.1 — RED: define pure-operation eligibility and complete cache keys

- **Task ID and binary outcome:** P57.5.1; three tests fail because no complete key policy exists.
- **Start goal:** Pin eligibility and every exact identity independently of cache I/O.
- **Prerequisites:** P57.1.2 and P57.2.2.
- **Documentation impact:** None.
- **Dependency impact:** None.
- **Allowed writes:** create `tests/test_phase57_cache_policy.py`.
- **Allowed reads:** invocation models, `src/rush/cache.py`, operation manifest, Phase 52 artifact identity.
- **Prohibited:** cache read/write integration, production/docs/XFAIL.
- **Actions:** 1. Arrange a complete context then independently mutate operation ID, ordered args, config digest, permissions, roots, environment/config identities, artifact/build, tool revision, normalizer revision, target path/state/content/capability, ignored inputs. 2. Add exactly three §7 cache-identity tests against planned `decide_cache`/`build_cache_key`; non-pure and any missing identity must return `bypass` and no key. 3. Run focused file and record absent-policy failures.
- **Evidence:** field-by-field mutation matrix and red output.
- **Stop:** any behavior identity lacks a canonical representation.
- **Verified outcome:** P57.5.2 may create policy/key functions only.

#### P57.5.2 — GREEN: create deterministic cache eligibility and key policy

- **Task ID and binary outcome:** P57.5.2; every identity mutation misses and incomplete/non-pure contexts yield no key.
- **Start goal:** Satisfy P57.5.1 without cache I/O.
- **Prerequisites:** recorded P57.5.1 RED.
- **Documentation impact:** None.
- **Dependency impact:** None.
- **Allowed writes:** create `src/rush/invocation/cache_policy.py`; modify `src/rush/invocation/models.py`; modify `tests/test_phase57_cache_policy.py` only to retain/strengthen assertions.
- **Allowed reads:** P57.5.1 evidence and manifest purity fields.
- **Prohibited:** `src/rush/cache.py`, executor, serializers, docs.
- **Actions:** 1. Reinspect every mutation. 2. Implement `CacheDecision`, completeness checks, canonical key payload, digest; return bypass reason/no key for non-pure, no-cache, or missing identity. 3. Run focused file and invocation-context tests.
- **Evidence:** green mutation matrix and deterministic key bytes.
- **Stop:** default/fallback salt replaces a missing identity.
- **Verified outcome:** P57.5.3 may test cache I/O integration.

#### P57.5.3 — RED: define cache read/write and result boundaries

- **Task ID and binary outcome:** P57.5.3; four tests fail because execution is not integrated safely.
- **Start goal:** Pin no-cache zero calls, pure-only use, pre-set sanitation/validation, post-get sanitation/validation.
- **Prerequisites:** P57.5.2 and Phase 53/54 contracts.
- **Documentation impact:** None.
- **Dependency impact:** None.
- **Allowed writes:** `tests/test_cache.py`, `tests/test_phase57_cache_policy.py`, `tests/test_phase57_invocation_context.py`.
- **Allowed reads:** `src/rush/cache.py`, invocation executor/policy, sanitizer/results.
- **Prohibited:** production/docs/XFAIL.
- **Actions:** 1. Arrange cache spy, pure/non-pure operations, no-cache context, malformed/secret-bearing cached values, valid ToolResultV1. 2. Add exactly four §7 cache-execution tests through `execute(context)`; assert read/write call counts and canonical error/miss behavior. 3. Run focused cache files and record failures.
- **Evidence:** call counts, sentinel scan, red output.
- **Stop:** test bypasses executor or weakens ToolResult validation.
- **Verified outcome:** P57.5.4 may integrate cache I/O.

#### P57.5.4 — GREEN: integrate cache around one execution boundary

- **Task ID and binary outcome:** P57.5.4; only eligible pure execution uses safe cache and `--no-cache` performs zero I/O.
- **Start goal:** Satisfy P57.5.3 only.
- **Prerequisites:** recorded P57.5.3 RED.
- **Documentation impact:** None.
- **Dependency impact:** None.
- **Allowed writes:** `src/rush/invocation/executor.py`, `src/rush/invocation/cache_policy.py`, `src/rush/cache.py`, `src/rush/cli.py`, `src/rush/mcp.py`, `tests/test_cache.py`, `tests/test_phase57_cache_policy.py`, `tests/test_phase57_invocation_context.py`.
- **Allowed reads:** P57.5.3 evidence, sanitizer/results adapters, operation manifest.
- **Prohibited:** cache admin semantics, provider logic, docs.
- **Actions:** 1. Reinspect executor before/after operation call. 2. Call policy once; on eligible key validate/sanitize after get and before return, execute once on miss, sanitize/validate before set; bypass does neither read nor write. 3. Run cache/context/public-operation tests and installed pure-operation probes.
- **Evidence:** green call-count/result matrix and no sentinels.
- **Stop:** malformed hit can return raw or absent identity still reads/writes.
- **Verified outcome:** R-006 cache portion closes without ambiguity.

### P57.6 — Provider truth

#### P57.6.1 — RED: define outcome and effective-origin labeling

- **Task ID and binary outcome:** P57.6.1; provider tests fail on redirect/origin/outcome labeling.
- **Start goal:** Pin missing key, denied network, HTTP/HTTPS, redirect, DNS/timeout, HTTP error, malformed/empty, approved/unapproved proxy, success.
- **Prerequisites:** P57.1.2 and Phase 53/54.
- **Documentation impact:** None.
- **Dependency impact:** None.
- **Allowed writes:** create `tests/test_phase57_provider_egress.py`, modify `tests/test_review.py`.
- **Allowed reads:** providers, review tool, permissions/config.
- **Prohibited:** production/live network/credentials/docs/XFAIL.
- **Actions:** 1. Arrange fake transport/DNS/proxy/redirect with authorization/prompt receiver spies. 2. Add exactly three §7 provider tests and full branch parameterization. 3. Run focused provider/review files and record failures.
- **Evidence:** branch matrix, receiver calls, red output.
- **Stop:** fixture uses real network or cannot expose effective origin.
- **Verified outcome:** P57.6.2 may edit provider/review seams.

#### P57.6.2 — GREEN: label LLM only after approved-origin completion

- **Task ID and binary outcome:** P57.6.2; only approved effective-origin valid non-empty completion is `llm`.
- **Start goal:** Satisfy P57.6.1 only.
- **Prerequisites:** recorded P57.6.1 RED.
- **Documentation impact:** None.
- **Dependency impact:** None.
- **Allowed writes:** `src/rush/tools/review.py`, `src/rush/providers/__init__.py`, `src/rush/providers/base.py`, `src/rush/providers/openai.py`, `src/rush/providers/anthropic.py`, `src/rush/providers/registry.py`, `src/rush/config.py`, `src/rush/permissions.py`, `tests/test_phase57_provider_egress.py`, `tests/test_review.py`.
- **Allowed reads:** P57.6.1 evidence and sanitizer/result contracts.
- **Prohibited:** live network/credential, new provider/dependency, docs.
- **Actions:** 1. Reinspect each branch and label assignment. 2. Implement exact outcomes, approved effective HTTPS origin/proxy policy, cross-origin redirect refusal before forwarding authorization/prompt, schema-valid non-empty completion gate. 3. Run focused provider/review/security tests.
- **Evidence:** green branch matrix and zero unauthorized receiver calls.
- **Stop:** effective origin cannot be proven.
- **Verified outcome:** R-007 closes.

### P57.7 — Documentation and handoff

#### P57.7.1 — VERIFY/DOCS/HANDOFF: close R-004 through R-007

- **Task ID and binary outcome:** P57.7.1; named docs and Phase 58 inventory cite passing installed evidence.
- **Start goal:** Document only proven contexts/scope/operations/cache/provider behavior.
- **Prerequisites:** P57.1.2-P57.6.2.
- **Documentation impact:** all eleven §8 docs.
- **Dependency impact:** None.
- **Allowed writes:** `docs/CLI_REFERENCE.md`, `docs/MCP_REFERENCE.md`, `docs/CONFIGURATION.md`, `docs/CONFIG_SCHEMA.md`, `docs/TOOL_CATALOG.md`, `docs/SCOPE.md`, `docs/ENVIRONMENT_VARIABLES.md`, `docs/PRIVACY.md`, `docs/SECURITY.md`, `docs/reference/configuration-reference.md`, `docs/safety/permissions.md`, and R-004-R-007 evidence fields in `governance/remediation-contracts.toml`.
- **Allowed reads:** passing tests, manifests, installed probe results.
- **Prohibited:** source/tests/dependencies or unproven transport/cache/provider claims.
- **Actions:** 1. Map each claim to exact tests. 2. Update named docs and record Phase 58 eligible-output inventory/handoff. 3. Run §10 and compare changed paths to tasks.
- **Evidence:** docs diff, installed probes, handoff.
- **Stop:** unowned path or source-tree-only proof.
- **Verified outcome:** R-004-R-007 close and Phase 58 may consume contracts.

## 10. Final verification and delivery gate

```text
$env:VIRTUAL_ENV=$null
$env:PYTHONPATH=$null
.venv/Scripts/python.exe -m pytest tests/test_phase57_invocation_context.py tests/test_phase57_physical_scope.py tests/test_phase57_public_operations.py tests/test_phase57_cache_policy.py tests/test_phase57_provider_egress.py tests/test_cache.py tests/test_review.py -q
.venv/Scripts/python.exe -m pytest tests/ -q
.venv/Scripts/ruff.exe check src tests scripts
.venv/Scripts/ruff.exe format --check src tests scripts
.venv/Scripts/python.exe scripts/probe_installed_artifacts.py
git diff --check
git diff --name-only
git status --short --branch
```

## 11. Exit checklist and successor evidence

- [ ] Ordinary RED precedes every GREEN; no skip/XFAIL/XPASS.
- [ ] Installed CLI/MCP resolve equivalent immutable contexts.
- [ ] Target traps cannot widen/escape; internal TypeError executes once.
- [ ] Every retained route passes its own contract-correct installed probe.
- [ ] Cache identity mutations miss; absent identity/no-cache/non-pure performs no I/O.
- [ ] Cache get/set values are sanitized and ToolResultV1-valid.
- [ ] Only approved-origin completed output is labeled LLM.
- [ ] No dependency/live egress/protected subsystem change.
- [ ] Every changed path belongs to one task.
