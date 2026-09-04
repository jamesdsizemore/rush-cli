# Phase 54 implementation plan — ToolResultV1 schema kernel and operation adapters

## 1. Purpose and status

- **Operation:** Create the implementation plan for remediation Phase 3.
- **Planning status:** Implementation-ready after §4 admission passes.
- **Implementation status:** Not authorized.
- **Authority:** governing roadmap R-011 schema-definition requirements.
- **Predecessor:** accepted Phase 53 sanitizer and JSON-safe value contract.
- **Successors:** Phase 56 consumes the plugin adapter; Phase 57 migrates public tools; Phase 58 completes eligible runtime migration.
- **Boundary:** Define and prove the kernel/adapters only; do not claim runtime migration.
- **Protected:** roadmap, CLI/MCP registrations, plugin execution, persistence/patch writers, `pyproject.toml`, `uv.lock`.
- **Amendment rule:** Add any new schema field, vocabulary, compatibility mapping, adapter class, or write path before implementation.
- **Lifecycle boundary:** No commit, push, merge, tag, publish, release, hooks, or history rewrite.

## 2. Authority, evidence, and decisions

Authority order: user → `AGENTS.md` → roadmap → Phase 51 operation/contract records → Phase 53 sanitizer contract → current `src/rush/tools/base.py` and producer/exporter evidence.

Current evidence: base results use `info|warn|error` while producers/exporters also emit `fail|warning`; malformed results can remain raw dictionaries/prose; public operations require different contract classes.

Closed decisions: tool statuses are exactly `ok|warn|fail|error|skipped`; finding severities are exactly `info|warning|error`; legacy `warn→warning`, `fail→error`; unknown values return one structured validation error; unknown top-level keys reject; extensions live under one namespaced JSON-safe object; service protocol messages are not ToolResultV1.

Open decisions: None. An unclassified operation returns to Phase 51 for amendment.

## 3. Goals, outcomes, exclusions, and invariants

Outcomes: immutable versioned ToolResultV1/FindingV1; deterministic serializer; exact legacy mappings; canonical structured validation errors; explicit tool/admin/service adapter registry.

Exclusions: CLI/MCP/plugin/persistence/patch migration, public command changes, new dependency.

Invariant: Phase 53 sanitization precedes validation/serialization; malformed eligible values never fall back to raw prose/dict.

## 4. Admission and predecessor gate

Require accepted Phase 53 sanitizer API/error evidence and current Phase 51 operation manifest. Inventory current ToolResult/Finding constructors and contract classes. Record overlapping edits and stop on any task-owned path conflict. P54.0.1 records the exact baseline before RED tasks.

## 5. Requirement-ownership ledger

| Requirement | Tasks | Closure |
|---|---|---|
| ToolResultV1/FindingV1 exact schema | P54.1.1-P54.1.2 | schema tests/fixtures |
| Legacy mappings and canonical error | P54.2.1-P54.2.2 | mapping matrix |
| Operation-class adapter interfaces | P54.3.1-P54.3.2 | tool/admin/service fixtures |
| Kernel-only documentation/handoff | P54.4.1 | docs and unclosed migration IDs |

## 6. Shared contracts and handoff

`ToolResultV1` requires `schema_version, tool, engine, engine_version, status, duration_ms, summary, findings`. `FindingV1` owns canonical path/location/rule/severity/message. Extensions are JSON-safe and namespaced. `adapt_legacy_finding` and `adapt_legacy_tool_result` are the only compatibility paths. Operation registry maps each Phase 51 operation ID to one target contract ID and adapter.

## 7. Contract-test inventory

| Contract | RED | GREEN | Exact ordinary tests |
|---|---|---|---|
| V1 schema | P54.1.1 | P54.1.2 | `test_tool_result_v1_requires_exact_fields_and_vocabularies`; `test_finding_v1_rejects_unknown_severity`; `test_extensions_are_namespaced_json_safe`; `test_serializer_is_deterministic` |
| Legacy/error mapping | P54.2.1 | P54.2.2 | `test_legacy_warn_maps_only_to_warning`; `test_legacy_fail_maps_only_to_error`; `test_unknown_legacy_value_returns_canonical_validation_error` |
| Operation adapters | P54.3.1 | P54.3.2 | `test_tool_operation_targets_tool_result_v1`; `test_admin_operation_uses_named_contract`; `test_service_liveness_is_not_wrapped_as_tool_result`; `test_every_manifest_operation_has_one_adapter` |

## 8. File, dependency, and documentation governance

New: `src/rush/contracts/__init__.py`, `src/rush/contracts/results.py`, `src/rush/contracts/operations.py`, `tests/test_phase54_result_schema.py`, `tests/test_phase54_operation_adapters.py`, `tests/fixtures/remediation/tool_result_v1_valid.json`, `tests/fixtures/remediation/tool_result_v1_invalid.json`.

Existing task-owned: `src/rush/tools/base.py`, `src/rush/tools/common.py`, `src/rush/tools/__init__.py`, `governance/public-operations.toml`, `governance/remediation-contracts.toml`, `tests/test_base.py`.

Docs owned only by P54.4.1: `docs/JSON_SCHEMA.md`, `docs/API_REFERENCE.md`, `docs/CLI_REFERENCE.md`, `docs/MCP_REFERENCE.md`, `docs/reference/result-reference.md`, `docs/developer/tool-development.md`.

All other writes prohibited. Dependency changes: None. Required existing dependencies/contracts: Python 3.12 typing/dataclasses and the Phase 53 sanitizer. Pydantic is prohibited.

## 9. Ordered workstreams and atomic task cards

### P54.0 — Admission

#### P54.0.1 — EVIDENCE: record schema producers and operation classes

- **Task ID and binary outcome:** P54.0.1; every current constructor/vocabulary and manifest operation class maps to one later task.
- **Start goal:** Freeze kernel scope.
- **Prerequisites:** §4.
- **Documentation impact:** None.
- **Dependency impact:** None.
- **Allowed writes:** R-011 kernel evidence fields in `governance/remediation-contracts.toml`.
- **Allowed reads:** `src/rush/tools/base.py`, `src/rush/tools/common.py`, `src/rush/tools/__init__.py`, `governance/public-operations.toml`, existing base/MCP/plugin tests.
- **Prohibited:** source/tests/docs/dependencies or migration claims.
- **Actions:** 1. Inspect constructors/callers/vocabularies and operation classes. 2. Record exact symbols, current values, task owner, and deferred migration phase. 3. Reconcile every operation and reparse TOML.
- **Evidence:** producer/vocabulary/operation table.
- **Stop:** unclassified operation or conflicting vocabulary decision.
- **Verified outcome:** P54.1.1-P54.3.1 may start.

### P54.1 — Schema types

#### P54.1.1 — RED: define exact V1 types and deterministic serialization

- **Task ID and binary outcome:** P54.1.1; four tests fail only because V1 types are absent.
- **Start goal:** Pin required fields, vocabularies, extension boundary, deterministic bytes.
- **Prerequisites:** P54.0.1.
- **Documentation impact:** None.
- **Dependency impact:** None.
- **Allowed writes:** create `tests/test_phase54_result_schema.py`, create `tests/fixtures/remediation/tool_result_v1_valid.json`, create `tests/fixtures/remediation/tool_result_v1_invalid.json`.
- **Allowed reads:** `src/rush/tools/base.py`, Phase 53 sanitizer API, current JSON schema docs as evidence.
- **Prohibited:** production/docs/migration/skip/XFAIL.
- **Actions:** 1. Arrange valid/invalid sanitized JSON fixtures. 2. Add exactly four §7 schema tests against planned `ToolResultV1`, `FindingV1`, and `serialize_tool_result`. 3. Run focused file and record absent-API/assertion failures only.
- **Evidence:** fixtures, test IDs, red output.
- **Stop:** a field/vocabulary is not fixed by §6.
- **Verified outcome:** P54.1.2 may create result contracts.

#### P54.1.2 — GREEN: implement V1 validation and serialization

- **Task ID and binary outcome:** P54.1.2; schema tests pass with exact deterministic output.
- **Start goal:** Satisfy P54.1.1 only.
- **Prerequisites:** recorded P54.1.1 RED.
- **Documentation impact:** None.
- **Dependency impact:** None.
- **Allowed writes:** create `src/rush/contracts/__init__.py`, create `src/rush/contracts/results.py`, modify `tests/test_phase54_result_schema.py` only to retain/strengthen assertions, modify the two V1 fixture files only for canonical expected bytes.
- **Allowed reads:** P54.1.1 evidence and sanitizer contract.
- **Prohibited:** legacy adapters, operations registry, tools/base, docs/dependencies.
- **Actions:** 1. Authorize only V1 types, validators, structured error type, serializer. 2. Implement exact required keys/vocabularies/namespaced extensions and deterministic JSON-safe output. 3. Run focused tests and Phase 53 sanitizer tests.
- **Evidence:** green output and canonical fixture bytes.
- **Stop:** permissive unknown keys or raw fallback.
- **Verified outcome:** P54.2.1 and P54.3.1 may consume V1 types.

### P54.2 — Legacy mapping

#### P54.2.1 — RED: define deterministic legacy conversion

- **Task ID and binary outcome:** P54.2.1; three tests fail on absent/incorrect mappings.
- **Start goal:** Pin only legacy severity/result conversion and error shape.
- **Prerequisites:** P54.1.2.
- **Documentation impact:** None.
- **Dependency impact:** None.
- **Allowed writes:** `tests/test_phase54_result_schema.py`, `tests/test_base.py`.
- **Allowed reads:** `src/rush/tools/base.py`, `src/rush/tools/common.py`, V1 API.
- **Prohibited:** production/operation registry/runtime migration/XFAIL.
- **Actions:** 1. Arrange legacy warn/fail/unknown/nested cases. 2. Add exactly three §7 mapping tests and assert no silent unknown coercion. 3. Run both test files and record contract failures.
- **Evidence:** mapping matrix and red output.
- **Stop:** test authorizes a new vocabulary.
- **Verified outcome:** P54.2.2 may edit mapping symbols.

#### P54.2.2 — GREEN: centralize legacy mappings and helpers

- **Task ID and binary outcome:** P54.2.2; legacy mappings and canonical errors pass through one path.
- **Start goal:** Satisfy P54.2.1 only.
- **Prerequisites:** recorded P54.2.1 RED.
- **Documentation impact:** None.
- **Dependency impact:** None.
- **Allowed writes:** `src/rush/contracts/results.py`, `src/rush/tools/base.py`, `src/rush/tools/common.py`, `src/rush/tools/__init__.py`, `tests/test_phase54_result_schema.py`, `tests/test_base.py`.
- **Allowed reads:** P54.2.1 evidence and current helper callers.
- **Prohibited:** producer-wide migration, CLI/MCP/plugin/persistence changes, docs.
- **Actions:** 1. Reinspect `normalize_findings`, `error_result`, `skipped_result` callers. 2. Implement only `adapt_legacy_finding`/`adapt_legacy_tool_result` and route those helpers through them while retaining compatibility imports. 3. Run focused files and existing base/tool tests.
- **Evidence:** green mapping matrix.
- **Stop:** a caller needs behavior migration owned by Phase 57/58.
- **Verified outcome:** mapping contract is ready for later migrations.

### P54.3 — Operation adapters

#### P54.3.1 — RED: define contract-class adapter behavior

- **Task ID and binary outcome:** P54.3.1; four tests fail on absent registry/reconciliation.
- **Start goal:** Pin tool/admin/service distinctions.
- **Prerequisites:** P54.0.1 and P54.1.2.
- **Documentation impact:** None.
- **Dependency impact:** None.
- **Allowed writes:** create `tests/test_phase54_operation_adapters.py`.
- **Allowed reads:** `governance/public-operations.toml`, V1 API, `tests/test_mcp.py`, `tests/test_plugins.py`.
- **Prohibited:** registrations/runtime implementation/manifest edits/XFAIL.
- **Actions:** 1. Arrange valid/malformed tool, named admin, and service liveness fixtures. 2. Add exactly four §7 adapter tests and assert stdio initialize/list remain protocol messages. 3. Run focused file and record absent-registry failures.
- **Evidence:** fixture matrix and red output.
- **Stop:** an operation has no Phase 51 class/contract ID.
- **Verified outcome:** P54.3.2 may create adapter registry.

#### P54.3.2 — GREEN: create operation adapter registry

- **Task ID and binary outcome:** P54.3.2; every manifest entry has one correct adapter without runtime migration.
- **Start goal:** Satisfy P54.3.1 only.
- **Prerequisites:** recorded P54.3.1 RED.
- **Documentation impact:** None.
- **Dependency impact:** None.
- **Allowed writes:** create `src/rush/contracts/operations.py`, modify `src/rush/contracts/__init__.py`, modify contract-ID fields only in `governance/public-operations.toml`, modify `tests/test_phase54_operation_adapters.py` only to retain/strengthen assertions.
- **Allowed reads:** P54.3.1 evidence and public-operation manifest.
- **Prohibited:** CLI/MCP/plugin/producer changes, arbitrary ToolResult assignment, docs.
- **Actions:** 1. Reinspect each operation class. 2. Implement adapter protocols/registry and reconcile existing contract IDs; no transport calls. 3. Run focused tests, Phase 51 operation tests, and `tests/test_mcp.py`.
- **Evidence:** green adapter matrix and zero unclassified entries.
- **Stop:** fixing test requires changing an operation’s class.
- **Verified outcome:** Phases 56-58 may consume registry interfaces.

### P54.4 — Verification, docs, and handoff

#### P54.4.1 — VERIFY/DOCS/HANDOFF: close the kernel without claiming migration

- **Task ID and binary outcome:** P54.4.1; docs define V1/adapters and records retain all later migration owners.
- **Start goal:** Prove kernel isolation and publish exact contract.
- **Prerequisites:** P54.1.2, P54.2.2, P54.3.2.
- **Documentation impact:** update all six §8 docs with fields, vocabularies, mappings, structured error, operation classes, and migration ownership.
- **Dependency impact:** None.
- **Allowed writes:** `docs/JSON_SCHEMA.md`, `docs/API_REFERENCE.md`, `docs/CLI_REFERENCE.md`, `docs/MCP_REFERENCE.md`, `docs/reference/result-reference.md`, `docs/developer/tool-development.md`, and R-011 kernel evidence fields in `governance/remediation-contracts.toml`.
- **Allowed reads:** passing Phase 54 tests, manifests, Phase 56-58 ownership records.
- **Prohibited:** source/tests/registrations/dependencies or “all migrated” claims.
- **Actions:** 1. Verify every later migration ID remains assigned. 2. Update only named docs/evidence with kernel and handoff facts. 3. Run §10 and compare changed paths to task ownership.
- **Evidence:** commands, docs diff, schema/adapter handoff, unclosed IDs.
- **Stop:** a later migration is accidentally marked closed.
- **Verified outcome:** R-011 schema kernel closes; runtime migration remains Phase 58-owned.

## 10. Final verification and delivery gate

```text
$env:VIRTUAL_ENV=$null
$env:PYTHONPATH=$null
.venv/Scripts/python.exe -m pytest tests/test_phase54_result_schema.py tests/test_phase54_operation_adapters.py tests/test_base.py tests/test_phase51_public_operations.py -q
.venv/Scripts/python.exe -m pytest tests/ -q
.venv/Scripts/ruff.exe check src tests scripts
.venv/Scripts/ruff.exe format --check src tests scripts
git diff --check
git diff --name-only
git status --short --branch
```

## 11. Exit checklist and successor evidence

- [ ] Ordinary RED evidence precedes each GREEN task; no skip/XFAIL/XPASS.
- [ ] Exact status/severity vocabularies and mappings are deterministic.
- [ ] Malformed values yield one structured error, never raw fallback.
- [ ] Every operation has one correct adapter class.
- [ ] No runtime migration, dependency, or protected registration change.
- [ ] Every changed path belongs to one task.
- [ ] Phases 56-58 receive schema version, mappings, error shape, registry, and unclosed IDs.
