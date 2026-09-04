# Phase 56 implementation plan — user-owned content-addressed plugin trust

## 1. Purpose and status

- **Operation:** Create the implementation plan for remediation Phase 5.
- **Planning status:** Implementation-ready after §4 admission passes.
- **Implementation status:** Not authorized.
- **Authority:** governing roadmap R-003 and locked plugin decisions.
- **Predecessors:** accepted Phase 53 sanitizer, Phase 54 plugin/admin result adapter, Phase 55 AtomicFile/PhysicalRoot/VerifierRecord.
- **Successor:** Phase 58 consumes final plugin output/persistence evidence.
- **Security boundary:** Plugins remain trusted user code with ambient filesystem/network authority; this phase provides immutable authorization and environment hardening, not OS/container sandboxing.
- **Protected:** roadmap, dependency manifests, non-plugin public operations, release state.
- **Amendment rule:** Any closure input, secret transport, platform behavior, runtime, dependency, or path outside a card requires amendment.
- **Lifecycle boundary:** No commit, push, merge, tag, publish, release, hooks, history rewrite, live secret, or live network.

## 2. Authority, evidence, and decisions

Authority order: user → `AGENTS.md` → roadmap → Phases 53-55 contracts → current plugin source/CLI/MCP/tests.

Current evidence: legacy path/repository grants can authorize mutable code; `trust.py` and `trust_store.py` split authority; execution can inherit environment and mutable paths; legacy loader/`allow_untrusted` paths can bypass hardened executor.

Closed decisions: one user-owned ledger outside repository; repository receipt is non-authorizing; approval binds complete secret-free closure and trusted runtime; snapshot contains copied/materialized bytes, never hardlinks/mutable sources; literal secrets forbidden in argv/config/resources/environment/ledger/snapshot/log/result; only protected descriptor, protected stdin protocol, or approved OS credential provider may deliver referenced secrets; unsupported launch identity/channel/platform denies before spawn.

Open decisions: None. Platform-specific support is determined by Phase 55 capability evidence; unsupported is a defined denial outcome.

## 3. Goals, outcomes, exclusions, and invariants

Outcomes: explicit grant/revoke/reapprove ledger; complete content-addressed closure snapshot; protected secret channels; non-substitutable verified-snapshot launch; no legacy public bypass; sanitized ToolResultV1-compatible plugin output.

Exclusions: sandbox claim, arbitrary environment forwarding, dependency addition, repository-owned authority, live plugin/network/credentials.

Invariant: approved bytes or no child; every observed artifact is secret-free; mutation after approval requires explicit reapproval.

## 4. Admission and predecessor gate

Require accepted Phase 53-55 APIs/platform matrices and Phase 51 plugin operation record. Inspect `trust.py`, `trust_store.py`, `executor.py`, `loader.py`, CLI `plugin run`, MCP admin routes, and callers. Record platform capability and overlapping edits. P56.0.1 freezes legacy/bypass/closure inputs before RED tasks.

## 5. Requirement-ownership ledger

| Requirement | Tasks | Closure |
|---|---|---|
| User-owned ledger/reapproval | P56.1.1-P56.1.2 | cloned receipt denied; grant/revoke/reapprove tests |
| Complete closure snapshot | P56.2.1-P56.2.2 | transitive mutation matrix |
| Protected secret channels | P56.3.1-P56.3.2 | same-user argv/environment observation |
| Non-substitutable launch | P56.4.1-P56.4.2 | synchronized replacement matrix |
| Remove bypass/validate output | P56.5.1-P56.5.2 | production-route/call-path tests |
| Docs/release handoff | P56.6.1 | exact docs and evidence |

## 6. Shared contracts and handoff

Ledger record: schema version, repository identity, closure digest, snapshot identity, trusted runtime physical identity, secret-free argv/config, allowed environment names, secret-reference names/transports, platform binding, grant metadata, verifier-only authority.

Closure covers executable, interpreter/runtime bytes, dependencies/resources, import roots, script directory, `PYTHONPATH` policy, dynamic/generated code policy, command/configuration, environment names, secret references/transports, platform.

Launch sequence: parse/validate manifest → resolve user ledger → open immutable snapshot/runtime through PhysicalRoot → reverify closure/runtime/ledger → negotiate protected channels → spawn handle-bound approved bytes; any unsupported/mismatch returns admin denial and creates no child.

## 7. Contract-test inventory

| Contract | RED | GREEN | Exact ordinary tests |
|---|---|---|---|
| Ledger lifecycle | P56.1.1 | P56.1.2 | `test_repository_receipt_never_authorizes`; `test_cloned_repository_receipt_is_denied`; `test_legacy_grant_requires_explicit_reapproval`; `test_revoke_invalidates_launch` |
| Closure snapshot | P56.2.1 | P56.2.2 | `test_closure_digest_covers_every_code_and_behavior_input`; `test_snapshot_contains_copied_bytes_not_links`; `test_post_approval_mutation_uses_snapshot_or_denies` |
| Secret channels | P56.3.1 | P56.3.2 | `test_literal_secret_is_rejected_from_argv_config_resource_and_environment`; `test_declared_protected_channel_is_not_visible_in_child_argv_or_environment`; `test_unsupported_channel_denies_before_spawn` |
| Launch identity | P56.4.1 | P56.4.2 | `test_snapshot_runtime_dependency_and_link_replacement_yields_approved_bytes_or_no_child`; `test_failed_verification_creates_no_child` |
| Public route/output | P56.5.1 | P56.5.2 | `test_plugin_run_cannot_reach_legacy_loader_execute_path`; `test_allow_untrusted_is_not_public`; `test_plugin_output_uses_admin_result_adapter_and_sanitizer` |

## 8. File, dependency, and documentation governance

New: `src/rush/plugins/closure.py`, `src/rush/plugins/snapshot_store.py`, `src/rush/plugins/secret_channels.py`, `tests/test_phase56_plugin_closure.py`, `tests/test_phase56_plugin_secret_channels.py`, `tests/test_phase56_plugin_launch_identity.py`.

Existing task-owned: `src/rush/plugins/__init__.py`, `src/rush/plugins/executor.py`, `src/rush/plugins/hash_verifier.py`, `src/rush/plugins/loader.py`, `src/rush/plugins/manifest_schema.py`, `src/rush/plugins/sandboxed_env.py`, `src/rush/plugins/trust.py`, `src/rush/plugins/trust_store.py`, `src/rush/plugins/validator.py`, `src/rush/cli.py`, `src/rush/mcp.py`, `src/rush/contracts/operations.py`, `src/rush/contracts/results.py`, `src/rush/io/atomic_file.py`, `src/rush/io/physical_paths.py`, `src/rush/io/verifier_record.py`, `src/rush/safety/redactor.py`, `governance/public-operations.toml`, `governance/remediation-contracts.toml`, `tests/test_plugin_trust.py`, `tests/test_plugins.py`, `tests/test_mcp.py`.

Docs owned only by P56.6.1: `docs/SECURITY.md`, `docs/PRIVACY.md`, `docs/CONFIGURATION.md`, `docs/CLI_REFERENCE.md`, `docs/MCP_REFERENCE.md`, `docs/TOOL_CATALOG.md`, `docs/agentic-rush/plugins-and-agent-skills.md`, `docs/safety/permissions.md`, `docs/safety/security-model.md`, `docs/developer/tool-development.md`.

Repository `.rush/trust.json` is read-only legacy evidence and never authority. All other writes prohibited. Dependency changes: None. Required existing dependencies/contracts: `cryptography==50.0.0`, Phase 53 sanitizer, Phase 54 output adapters, and Phase 55 containment/verifier primitives.

## 9. Ordered workstreams and atomic task cards

### P56.0 — Admission

#### P56.0.1 — EVIDENCE: record authority paths, closure inputs, and spawn call paths

- **Task ID and binary outcome:** P56.0.1; every current grant/execute/spawn path and closure input maps to one task.
- **Start goal:** Freeze plugin security scope.
- **Prerequisites:** §4.
- **Documentation impact:** None.
- **Dependency impact:** None.
- **Allowed writes:** R-003 admission fields in `governance/remediation-contracts.toml`.
- **Allowed reads:** `src/rush/plugins/__init__.py`, `src/rush/plugins/executor.py`, `src/rush/plugins/hash_verifier.py`, `src/rush/plugins/loader.py`, `src/rush/plugins/manifest_schema.py`, `src/rush/plugins/sandboxed_env.py`, `src/rush/plugins/trust.py`, `src/rush/plugins/trust_store.py`, `src/rush/plugins/validator.py`, `src/rush/cli.py`, `src/rush/mcp.py`, `src/rush/contracts/operations.py`, `src/rush/contracts/results.py`, `src/rush/io/atomic_file.py`, `src/rush/io/physical_paths.py`, `src/rush/io/verifier_record.py`, `src/rush/safety/redactor.py`, `governance/public-operations.toml`, `governance/remediation-contracts.toml`, `tests/test_plugin_trust.py`, `tests/test_plugins.py`, `tests/test_mcp.py`.
- **Prohibited:** source/tests/docs/dependencies/live plugin.
- **Actions:** 1. Inspect grants, loaders, executor, spawn, env, manifest, secret flow, physical paths. 2. Record exact symbols, closure inputs, bypasses, platform capabilities, task owners. 3. Reconcile every public call path and reparse TOML.
- **Evidence:** call-path/closure/bypass table.
- **Stop:** an execution route or behavior input lacks ownership.
- **Verified outcome:** P56.1.1-P56.5.1 may start.

### P56.1 — Ledger lifecycle

#### P56.1.1 — RED: define user-owned authorization and explicit reapproval

- **Task ID and binary outcome:** P56.1.1; four tests fail on current grant authority.
- **Start goal:** Pin ledger-only authorization, cloned receipt denial, reapproval, revoke.
- **Prerequisites:** P56.0.1.
- **Documentation impact:** None.
- **Dependency impact:** None.
- **Allowed writes:** `tests/test_plugin_trust.py`.
- **Allowed reads:** `src/rush/plugins/trust.py`, `src/rush/plugins/trust_store.py`, `src/rush/cli.py`, `src/rush/mcp.py`, `src/rush/io/atomic_file.py`, `src/rush/io/physical_paths.py`, `src/rush/io/verifier_record.py`, `governance/public-operations.toml`.
- **Prohibited:** production/repository receipt writes/docs/XFAIL/live plugin.
- **Actions:** 1. Arrange injected user-data root, repository clone, legacy grant, grant/revoke generations. 2. Add exactly four §7 ledger tests through public admin routes. 3. Run `.venv/Scripts/python.exe -m pytest tests/test_plugin_trust.py -q` and record behavior failures.
- **Evidence:** red output and injected paths.
- **Stop:** test relies on actual user home or repository authority.
- **Verified outcome:** P56.1.2 may edit trust authority.

#### P56.1.2 — GREEN: consolidate authority into one atomic user ledger

- **Task ID and binary outcome:** P56.1.2; only user ledger authorizes and lifecycle tests pass.
- **Start goal:** Satisfy P56.1.1 only.
- **Prerequisites:** recorded P56.1.1 RED.
- **Documentation impact:** None.
- **Dependency impact:** None.
- **Allowed writes:** `src/rush/plugins/trust.py`, `src/rush/plugins/trust_store.py`, `src/rush/plugins/__init__.py`, `src/rush/cli.py`, `src/rush/mcp.py`, `src/rush/io/atomic_file.py`, `src/rush/io/verifier_record.py`, `tests/test_plugin_trust.py`.
- **Allowed reads:** P56.1.1 evidence and Phase 54/55 contracts.
- **Prohibited:** closure snapshot/spawn/secret channels, repository authority, docs.
- **Actions:** 1. Reinspect authority callers. 2. Make `PluginTrustStore` the sole authorizer using AtomicFile and VerifierRecord; repository receipts become sanitized non-authorizing evidence; legacy grant requires explicit new grant. 3. Run focused trust and MCP admin tests.
- **Evidence:** green lifecycle and ledger-location/content inspection.
- **Stop:** migration silently authorizes legacy/path state.
- **Verified outcome:** P56.2.1/P56.4.1 may consume ledger identity.

### P56.2 — Closure snapshots

#### P56.2.1 — RED: define complete secret-free closure identity

- **Task ID and binary outcome:** P56.2.1; mutation/snapshot tests fail on incomplete closure.
- **Start goal:** Pin all behavior inputs and immutable materialization.
- **Prerequisites:** P56.1.2.
- **Documentation impact:** None.
- **Dependency impact:** None.
- **Allowed writes:** create `tests/test_phase56_plugin_closure.py`.
- **Allowed reads:** manifest/loader/hash/executor/sandbox code and Phase 55 physical API.
- **Prohibited:** production/docs/real plugin/secret/XFAIL.
- **Actions:** 1. Arrange executable, command/config, dependency/resource, import root, dynamic/generated code, interpreter, PYTHONPATH, script dir, symlink, junction, hardlink mutations. 2. Add exactly three §7 closure tests and assert snapshot bytes contain no literal secret. 3. Run focused file and record failures.
- **Evidence:** mutation matrix and red output.
- **Stop:** behavior source cannot be enumerated under §6.
- **Verified outcome:** P56.2.2 may create closure/snapshot modules.

#### P56.2.2 — GREEN: discover, digest, and materialize immutable closure

- **Task ID and binary outcome:** P56.2.2; every covered mutation changes digest/source only while approved snapshot remains immutable or denies.
- **Start goal:** Satisfy P56.2.1 only.
- **Prerequisites:** recorded P56.2.1 RED.
- **Documentation impact:** None.
- **Dependency impact:** None.
- **Allowed writes:** create `src/rush/plugins/closure.py`, create `src/rush/plugins/snapshot_store.py`, modify `src/rush/plugins/manifest_schema.py`, `hash_verifier.py`, `validator.py`, `trust_store.py`, `src/rush/io/atomic_file.py`, `src/rush/io/physical_paths.py`, `tests/test_phase56_plugin_closure.py`.
- **Allowed reads:** P56.2.1 evidence and predecessor APIs.
- **Prohibited:** secret delivery/spawn/legacy route/docs/dependencies.
- **Actions:** 1. Reinspect each mutation input. 2. Implement closure enumeration/digest and copied-byte snapshot under contained user root; reject links/unbounded dynamic inputs and secret-bearing bytes. 3. Run focused closure, trust, and Phase 55 containment/atomic tests.
- **Evidence:** green matrix, closure manifest, snapshot physical identities.
- **Stop:** hardlink/mutable/unbounded source can enter snapshot.
- **Verified outcome:** P56.4.1 may target snapshot launch.

### P56.3 — Protected secrets

#### P56.3.1 — RED: define allowed child secret channels

- **Task ID and binary outcome:** P56.3.1; secret-channel tests fail on current argv/env behavior.
- **Start goal:** Pin literal rejection, protected delivery, same-user invisibility, unsupported denial.
- **Prerequisites:** P56.0.1.
- **Documentation impact:** None.
- **Dependency impact:** None.
- **Allowed writes:** create `tests/test_phase56_plugin_secret_channels.py`.
- **Allowed reads:** sandbox/env/executor/manifest code and platform capability evidence.
- **Prohibited:** production/live secrets/network/XFAIL.
- **Actions:** 1. Arrange runtime sentinels, child argv/env observer, descriptor, stdin protocol, fake credential provider, unsupported platform. 2. Add exactly three §7 secret tests plus unknown-reference denial. 3. Run focused file and record contract failures.
- **Evidence:** red output and observer captures.
- **Stop:** fixture exposes sentinel outside protected channel.
- **Verified outcome:** P56.3.2 may create secret channel negotiation.

#### P56.3.2 — GREEN: resolve references only into protected channels

- **Task ID and binary outcome:** P56.3.2; declared channel delivers value and no ordinary artifact/argv/env contains it.
- **Start goal:** Satisfy P56.3.1 only.
- **Prerequisites:** recorded P56.3.1 RED.
- **Documentation impact:** None.
- **Dependency impact:** None.
- **Allowed writes:** create `src/rush/plugins/secret_channels.py`, modify `src/rush/plugins/sandboxed_env.py`, `manifest_schema.py`, `executor.py`, `src/rush/safety/redactor.py`, `tests/test_phase56_plugin_secret_channels.py`.
- **Allowed reads:** P56.3.1 evidence and platform APIs.
- **Prohibited:** argv/env fallback, persistence, new dependency, docs.
- **Actions:** 1. Reinspect channel/platform cases. 2. Implement declared descriptor/stdin/provider negotiation, ephemeral resolution after authorization, minimal bootstrap env, unsupported denial before spawn. 3. Run focused secret, sanitizer, and plugin trust tests.
- **Evidence:** green observer matrix and sentinel scan.
- **Stop:** protected channel unavailable; deny rather than fall back.
- **Verified outcome:** P56.4.2 may negotiate channels at launch.

### P56.4 — Launch identity

#### P56.4.1 — RED: define approved-bytes-or-no-child races

- **Task ID and binary outcome:** P56.4.1; synchronized replacement tests fail on substitutable launch.
- **Start goal:** Pin snapshot/runtime/dependency/link replacement immediately before spawn.
- **Prerequisites:** P56.1.2, P56.2.2, P56.3.2.
- **Documentation impact:** None.
- **Dependency impact:** None.
- **Allowed writes:** create `tests/test_phase56_plugin_launch_identity.py`.
- **Allowed reads:** executor/loader plus ledger/closure/secret/PhysicalRoot APIs.
- **Prohibited:** production/live plugin/network/XFAIL.
- **Actions:** 1. Arrange spawn barrier and replacement cases for snapshot file, interpreter, dependency/resource, symlink, directory junction, runtime. 2. Add exactly two §7 launch tests and assert child counter remains zero on mismatch. 3. Run focused file on Windows/POSIX and record failures.
- **Evidence:** race matrix and child counters.
- **Stop:** platform fixture cannot prove launched physical identity.
- **Verified outcome:** P56.4.2 may edit hardened executor.

#### P56.4.2 — GREEN: launch only reverified immutable identities

- **Task ID and binary outcome:** P56.4.2; every race launches approved bytes or no child.
- **Start goal:** Satisfy P56.4.1 only.
- **Prerequisites:** recorded P56.4.1 RED.
- **Documentation impact:** None.
- **Dependency impact:** None.
- **Allowed writes:** `src/rush/plugins/executor.py`, `src/rush/plugins/loader.py`, `src/rush/plugins/closure.py`, `snapshot_store.py`, `secret_channels.py`, `src/rush/io/physical_paths.py`, `tests/test_phase56_plugin_launch_identity.py`.
- **Allowed reads:** P56.4.1 evidence and predecessor APIs.
- **Prohibited:** legacy public route removal/output adapter/docs/dependencies.
- **Actions:** 1. Reinspect barrier and spawn call. 2. Reverify ledger/closure/runtime/physical identities immediately before handle-bound spawn, then negotiate channel; unsupported/mismatch returns denial without child. 3. Run focused launch, closure, secret, and Phase 55 platform tests.
- **Evidence:** green races and launched identities.
- **Stop:** platform cannot bind approved bytes at spawn.
- **Verified outcome:** hardened launch contract is closed.

### P56.5 — Public route and output

#### P56.5.1 — RED: expose legacy bypass and malformed output

- **Task ID and binary outcome:** P56.5.1; public-route tests fail on legacy loader/`allow_untrusted`/raw output.
- **Start goal:** Pin one production route and Phase 54 admin adapter.
- **Prerequisites:** P56.4.2 and Phase 54 adapter.
- **Documentation impact:** None.
- **Dependency impact:** None.
- **Allowed writes:** `tests/test_plugins.py`, `tests/test_plugin_trust.py`, `tests/test_mcp.py`.
- **Allowed reads:** CLI/MCP/plugin registrations, loader/executor, contracts.
- **Prohibited:** production/docs/XFAIL/manual executor-only tests.
- **Actions:** 1. Trace public `rush plugin run` and MCP admin call paths. 2. Add exactly three §7 route/output tests through public boundaries. 3. Run focused files and record failures.
- **Evidence:** call-path spies and red output.
- **Stop:** test bypasses actual registration.
- **Verified outcome:** P56.5.2 may change public plugin route.

#### P56.5.2 — GREEN: remove public bypass and adapt output

- **Task ID and binary outcome:** P56.5.2; every public invocation reaches hardened executor and returns sanitized valid admin result.
- **Start goal:** Satisfy P56.5.1 only.
- **Prerequisites:** recorded P56.5.1 RED.
- **Documentation impact:** None.
- **Dependency impact:** None.
- **Allowed writes:** `src/rush/cli.py`, `src/rush/mcp.py`, `src/rush/plugins/loader.py`, `executor.py`, `src/rush/contracts/operations.py`, `src/rush/contracts/results.py`, `governance/public-operations.toml`, `tests/test_plugins.py`, `tests/test_plugin_trust.py`, `tests/test_mcp.py`.
- **Allowed reads:** P56.5.1 evidence and Phase 53/54 contracts.
- **Prohibited:** unrelated routes, dependency/docs/release.
- **Actions:** 1. Reinspect every public caller. 2. Route only through HardenedPluginExecutor, remove/private legacy execute and `allow_untrusted`, sanitize then validate output with named admin adapter. 3. Run focused public/plugin/MCP suites and Phase 51 operation reconciliation.
- **Evidence:** green public call paths and output fixtures.
- **Stop:** any advertised bypass remains.
- **Verified outcome:** R-003 production route is closed.

### P56.6 — Documentation and handoff

#### P56.6.1 — VERIFY/DOCS/HANDOFF: publish exact trust limitations

- **Task ID and binary outcome:** P56.6.1; named docs describe ledger/snapshot/channels/denial/non-sandbox truth and evidence passes.
- **Start goal:** Document only proven plugin behavior.
- **Prerequisites:** P56.1.2-P56.5.2.
- **Documentation impact:** all ten §8 docs.
- **Dependency impact:** None.
- **Allowed writes:** `docs/SECURITY.md`, `docs/PRIVACY.md`, `docs/CONFIGURATION.md`, `docs/CLI_REFERENCE.md`, `docs/MCP_REFERENCE.md`, `docs/TOOL_CATALOG.md`, `docs/agentic-rush/plugins-and-agent-skills.md`, `docs/safety/permissions.md`, `docs/safety/security-model.md`, `docs/developer/tool-development.md`, and R-003 evidence fields in `governance/remediation-contracts.toml`.
- **Allowed reads:** passing Phase 56/predecessor tests and manifests.
- **Prohibited:** source/tests/dependencies, sandbox/privacy guarantees, live evidence.
- **Actions:** 1. Map every claim/limitation/recovery step to tests. 2. Update named docs and record Phase 58 output/persistence handoff. 3. Run §10 and compare every changed path to task ownership.
- **Evidence:** docs diff, platform matrices, handoff.
- **Stop:** a claim implies OS isolation or insecure fallback.
- **Verified outcome:** R-003 closes and Phase 58 may consume evidence.

## 10. Final verification and delivery gate

```text
$env:VIRTUAL_ENV=$null
$env:PYTHONPATH=$null
.venv/Scripts/python.exe -m pytest tests/test_plugin_trust.py tests/test_plugins.py tests/test_phase56_plugin_closure.py tests/test_phase56_plugin_secret_channels.py tests/test_phase56_plugin_launch_identity.py tests/test_mcp.py -q
.venv/Scripts/python.exe -m pytest tests/ -q
.venv/Scripts/ruff.exe check src tests scripts
.venv/Scripts/ruff.exe format --check src tests scripts
git diff --check
git diff --name-only
git status --short --branch
```

## 11. Exit checklist and successor evidence

- [ ] Ordinary RED precedes GREEN; no skip/XFAIL/XPASS.
- [ ] Only user-owned ledger authorizes; cloned/repository/legacy state denies.
- [ ] Complete secret-free closure launches immutable snapshot bytes.
- [ ] Literal secrets never enter argv/config/resource/env/ledger/snapshot/log/result.
- [ ] Every race yields approved bytes or no child on Windows/POSIX.
- [ ] Public route has no legacy/`allow_untrusted` bypass and output uses Phase 54 adapter.
- [ ] No dependency, live plugin/network/credential, or sandbox claim.
- [ ] Every changed path belongs to one task.
