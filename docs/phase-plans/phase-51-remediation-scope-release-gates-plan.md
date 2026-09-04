# Phase 51 implementation plan — remediation scope, operation inventory, and release probes

## 1. Purpose and status

- **Operation:** Create the implementation plan for remediation Phase 0.
- **Planning status:** Implementation-ready after §4 admission passes.
- **Implementation status:** Not authorized by this plan.
- **Authority:** `docs/developer/repository-remediation-plan.md`.
- **Predecessor:** Accepted and merged Phase 50 (Phases 50a, 50b, 50c complete; 49 catalog tools, 963 tests passing on main).
- **Successors:** Phases 52-60.
- **Protected:** the governing roadmap and its adversarial review.
- **Amendment rule:** Add a literal path, dependency, contract, or public operation to this plan and the Phase 51 ownership record before changing it.
- **Lifecycle boundary:** No commit, push, merge, tag, publish, release, hook installation, or history rewrite.

Phase 51 creates auditable coverage, public-operation, artifact-probe, engine-policy, and cross-phase ownership records. It does not remediate R-001 through R-016 and does not commit intentionally failing or XFAIL tests for later phases.

## 2. Authority, evidence, and decisions

### 2.1 Authority order

1. Current user instructions, including no implementation and no plan validators.
2. Repository `AGENTS.md`.
3. Governing roadmap.
4. Current source, tests, dependency manifests, workflows, and shipping docs as evidence.
5. Historical Phase 41-50 plans as numbering/lifecycle convention only.

### 2.2 Current-state evidence

| Area | Exact evidence | Consequence |
|---|---|---|
| Packaging | `pyproject.toml`, `src/rush/`, current `src.rush` imports | Probe installed wheel and sdist separately from an external CWD. |
| Routes | `src/rush/cli.py` (129 commands across leaves and groups), `src/rush/mcp.py` (73 FastMCP tools), `src/rush/catalog.py` (52 `TOOL_SPECS`) | Assign every advertised route one operation ID, contract class, canonical implementation, and safe probe. |
| Engines | `src/rush/tools/common.py`, `tests/test_static_tools.py`, CI | Separate fixed-PATH deterministic tests from provisioned conformance. |
| Findings | Roadmap R-001 through R-016 | Assign one owner phase and one future ordinary RED/GREEN pair per contract. |

### 2.3 Closed decisions

- Retain wheel and sdist, cache, and trusted-user-code plugins.
- Plugins receive immutable authorization, not an OS-sandbox claim.
- Unsupported plugin launch fails before spawn.
- Lock acquisition remains public and uses caller-generated capability.
- R-015 is post-release but required for remediation-program completion.
- Phase 51 records later contract gaps; each owning phase writes its ordinary RED test immediately before its GREEN task. Skip, XFAIL, XPASS, and permanently red committed suites are prohibited evidence.

### 2.4 Open decisions

None. An unclassifiable route/path is a plan-amendment stop, not coding-agent discretion.

## 3. Goals, outcomes, exclusions, and invariants

### 3.1 Outcomes

1. Every first-party path has one deterministic class or explicit exclusion.
2. Every Click leaf and advertised MCP operation has one reconciled record and non-live probe.
3. Wheel and sdist are independently installed and probed outside the checkout on Windows/POSIX.
4. Every engine family has one support category and evidence policy.
5. Every remediation contract has one later owning phase, literal test IDs/files, target seam, and release effect.

### 3.2 Exclusions

No production remediation, dependency change, live network/credential/plugin probe, governing-roadmap edit, or release action.

### 3.3 Inherited invariants

Python 3.12 with `uv`; stdio MCP stdout is JSON-RPC only; CLI/MCP use `src/rush/tools/`; missing engines return structured `skipped`; `research/` remains local/untracked.

## 4. Admission and predecessor gate

Before P51.0.1, record `git status --short --branch`, `git rev-parse HEAD`, `.venv/Scripts/python.exe --version`, the current tracked/untracked state of the roadmap, and verify predecessor test baseline (>= 956 passing tests, 963 in full environment). Read `pyproject.toml`, both workflows, CLI/MCP registration, and the phase index using Graft/CodeGraph first where indexed. Stop on wrong Python, failing predecessor tests, missing authority, unresolved decision, or overlapping user edits to a task-owned path.

## 5. Requirement-ownership ledger

| Requirement | Tasks | Closure |
|---|---|---|
| RM-P0-01 coverage boundary | P51.1.1-P51.1.2 | `governance/first-party-coverage.toml` |
| RM-P0-02 operation inventory/probes | P51.2.1-P51.2.2 | `governance/public-operations.toml` |
| RM-P0-03 artifact isolation/matrix | P51.3.1-P51.3.2 | wheel/sdist probe results and CI jobs |
| RM-P0-04 engine taxonomy | P51.4.1-P51.4.2 | `governance/engine-support.toml` |
| RM-P0-05 finding/test ownership | P51.5.1 | `governance/remediation-contracts.toml` |
| RM-P0-06 baseline/docs/handoff | P51.0.1, P51.6.1 | Phase record and named docs |

R-001 through R-016 are owned only by Phases 52-60.

## 6. Shared contracts and handoff

- **Coverage record:** revision, generator version, normalized path, class, inclusion rule, exclusion reason; sorted byte-stably.
- **Operation record:** ID, kind (`tool|admin|service|deprecated`), canonical implementation, CLI/MCP names, input/output contract owner, effect class, compatibility, safe probe.
- **Engine record:** family, `mandatory|supported-optional|best-effort`, executable/version evidence, fixture matrix, provisioned job, permitted skip.
- **Remediation record:** finding, owner phase, RED task, GREEN task, literal test file/function, deterministic control, target symbol/seam, predecessor, docs owner, release effect.

## 7. Contract-test inventory

| Contract | RED | GREEN | Exact ordinary tests | Deterministic control |
|---|---|---|---|---|
| Coverage | P51.1.1 | P51.1.2 | `test_manifest_covers_every_first_party_path_once`; `test_manifest_is_byte_stable`; `test_manifest_rejects_unclassified_tracked_path` | synthetic repository tree |
| Operations | P51.2.1 | P51.2.2 | `test_every_click_leaf_and_advertised_mcp_route_has_one_operation`; `test_every_advertised_transport_has_a_non_live_probe` | fake effect/service probes |
| Artifacts | P51.3.1 | P51.3.2 | `test_wheel_and_sdist_are_probed_independently`; `test_external_cwd_rejects_checkout_origin`; `test_broken_import_control_is_detected` | fake runner and broken package |
| Engines | P51.4.1 | P51.4.2 | `test_every_engine_family_has_one_support_class`; `test_supported_family_cannot_pass_all_skipped`; `test_fixed_path_ignores_ambient_tools` | fixed PATH and fake results |

Each RED card writes tests only and records the intended assertion failure. Its immediately dependent GREEN card changes only named implementation seams and makes the same tests pass.

## 8. File, dependency, and documentation governance

### 8.1 Phase inventory

New implementation/evidence files: `src/rush/governance/coverage_manifest.py`, `src/rush/governance/public_operations.py`, `scripts/build_remediation_manifests.py`, `scripts/probe_installed_artifacts.py`, `governance/remediation-phase-51.toml`, `governance/first-party-coverage.toml`, `governance/public-operations.toml`, `governance/engine-support.toml`, `governance/remediation-contracts.toml`, `tests/test_phase51_coverage_manifest.py`, `tests/test_phase51_public_operations.py`, `tests/test_phase51_artifact_probes.py`, `tests/test_phase51_engine_policy.py`.

Existing implementation/workflow file: `src/rush/governance/__init__.py`, `.github/workflows/ci.yml`, `.github/workflows/release.yml`.

Docs owned only by P51.6.1: `docs/DISTRIBUTION.md`, `docs/ENGINES.md`, `docs/CLI_REFERENCE.md`, `docs/MCP_REFERENCE.md`, `docs/developer/ci-and-packaging.md`, `docs/developer/testing-guide.md`, `docs/maintainers/release-playbook.md`.

All other writes are prohibited. Phase-level inventory is not task-level permission.

### 8.2 Dependencies

None. Use stdlib, existing pytest/Ruff, existing build backend, and `uv build`. `pyproject.toml` and `uv.lock` are protected.

## 9. Ordered workstreams and atomic task cards

### P51.0 — Admission

#### P51.0.1 — EVIDENCE: record the Phase 51 baseline

- **Task ID and binary outcome:** P51.0.1; one parseable record contains revision, worktree, toolchain, authorities, decisions, and Phase 52-60 edges.
- **Start goal:** Establish admissible evidence without implementation.
- **Prerequisites:** §4.
- **Documentation impact:** None; governance evidence only.
- **Dependency impact:** None.
- **Allowed writes:** create `governance/remediation-phase-51.toml`.
- **Allowed reads:** §2 authorities, Git state, interpreter, manifests/workflows.
- **Prohibited:** every other write and any remediation-success claim.
- **Actions:** 1. Inspect and record exact evidence. 2. Create only the TOML record with `status = "admitted"`. 3. Parse it with Python `tomllib` and compare status to the admission snapshot.
- **Evidence:** parsed record, revision, Python version, changed paths.
- **Stop:** missing/contradictory authority or overlapping output edit.
- **Verified outcome:** P51.1.1, P51.2.1, P51.3.1, and P51.4.1 may start.

### P51.1 — First-party coverage

#### P51.1.1 — RED: define deterministic coverage

- **Task ID and binary outcome:** P51.1.1; three named tests fail only because the API is absent.
- **Start goal:** Pin single classification, unknown-path refusal, and byte stability.
- **Prerequisites:** P51.0.1.
- **Documentation impact:** None; behavior absent.
- **Dependency impact:** None.
- **Allowed writes:** create `tests/test_phase51_coverage_manifest.py`.
- **Allowed reads:** repository tree, ignore rules, `pyproject.toml`, governance conventions.
- **Prohibited:** source, manifest, docs, workflows, skip/XFAIL.
- **Actions:** 1. Arrange a synthetic tree covering source/tests/scripts/docs/templates/workflows/metadata/research/unknown. 2. Add exactly the three §7 coverage tests against planned `build_manifest(root, revision)`. 3. Run `.venv/Scripts/python.exe -m pytest tests/test_phase51_coverage_manifest.py -q` and record the intended absent-API/assertion failure.
- **Evidence:** test IDs, fixture, exact red output.
- **Stop:** collection/fixture failure or missing policy choice.
- **Verified outcome:** P51.1.2 may change only its named implementation.

#### P51.1.2 — GREEN: generate the coverage manifest

- **Task ID and binary outcome:** P51.1.2; coverage tests pass and repeat output is byte-identical.
- **Start goal:** Satisfy P51.1.1 only.
- **Prerequisites:** recorded P51.1.1 RED.
- **Documentation impact:** None; P51.6.1 owns docs.
- **Dependency impact:** None.
- **Allowed writes:** create `src/rush/governance/coverage_manifest.py`, create `scripts/build_remediation_manifests.py`, create `governance/first-party-coverage.toml`, modify `src/rush/governance/__init__.py`, and modify `tests/test_phase51_coverage_manifest.py` only to retain or strengthen its original assertions.
- **Allowed reads:** P51.1.1 evidence and repository paths.
- **Prohibited:** operations/engines/runtime/workflows/docs/dependencies.
- **Actions:** 1. Reinspect red assertions and authorize `CoverageRecord`, `classify_path`, `build_manifest`, `render_toml`. 2. Implement only those symbols and generate sorted explicit records; unknown tracked paths raise. 3. Run the focused file, generate twice and compare digests, then run `tests/test_cli_registry.py`.
- **Evidence:** green output, equal digests, zero unclassified paths.
- **Stop:** new classification choice or unlisted write.
- **Verified outcome:** later phases may use the coverage manifest.

### P51.2 — Public operations

#### P51.2.1 — RED: define route reconciliation and safe probes

- **Task ID and binary outcome:** P51.2.1; two named tests fail on the absent operation API.
- **Start goal:** Pin one route record and non-live probe per advertised transport.
- **Prerequisites:** P51.0.1.
- **Documentation impact:** None.
- **Dependency impact:** None.
- **Allowed writes:** create `tests/test_phase51_public_operations.py`.
- **Allowed reads:** CLI, MCP, tool registry, `tests/test_cli_registry.py`, `tests/test_mcp.py`.
- **Prohibited:** source/manifest/docs/workflows/live effects/skip/XFAIL.
- **Actions:** 1. Inspect registration and arrange pure, engine, effectful, admin, and service fakes. 2. Add exactly the two §7 tests plus `test_operation_ids_and_transport_names_are_unique` and `test_tool_pairs_share_one_canonical_implementation`. 3. Run the focused file and record intended absent-API failure.
- **Evidence:** test IDs, fakes, exact red output.
- **Stop:** a route cannot be classified or safely probed under §6.
- **Verified outcome:** P51.2.2 may implement the inventory.

#### P51.2.2 — GREEN: create the operation manifest

- **Task ID and binary outcome:** P51.2.2; all retained routes reconcile once and have safe probes.
- **Start goal:** Satisfy P51.2.1 only.
- **Prerequisites:** recorded P51.2.1 RED.
- **Documentation impact:** None.
- **Dependency impact:** None.
- **Allowed writes:** create `src/rush/governance/public_operations.py`, create `governance/public-operations.toml`, modify `src/rush/governance/__init__.py`, modify `scripts/build_remediation_manifests.py`, and modify `tests/test_phase51_public_operations.py` only to retain or strengthen its original assertions.
- **Allowed reads:** registration and P51.2.1 evidence.
- **Prohibited:** CLI/MCP behavior, artifact harness, workflows, docs, dependencies.
- **Actions:** 1. Authorize only `OperationKind`, `TransportProbe`, `PublicOperation`, enumeration and reconciliation symbols. 2. Implement and render records; reject duplicate/unowned routes. 3. Run focused tests, then `tests/test_cli_registry.py tests/test_mcp.py`.
- **Evidence:** green output, counts, zero duplicates/unprobed routes.
- **Stop:** inventory requires a behavior/public-route change.
- **Verified outcome:** P51.3.1 may consume the manifest.

### P51.3 — Installed artifacts

#### P51.3.1 — RED: define artifact isolation

- **Task ID and binary outcome:** P51.3.1; three named tests fail because the harness is absent.
- **Start goal:** Pin wheel/sdist separation, scrubbed external CWD, origin checks, and negative control.
- **Prerequisites:** P51.0.1 and P51.2.2.
- **Documentation impact:** None.
- **Dependency impact:** None; `uv build` is the existing tool.
- **Allowed writes:** create `tests/test_phase51_artifact_probes.py`.
- **Allowed reads:** `pyproject.toml`, operation manifest, packaging tests/workflows.
- **Prohibited:** packaging/source/scripts/workflows/docs/dependencies/editable installs.
- **Actions:** 1. Arrange fake runner and deliberately broken checkout-origin package. 2. Add exactly the three §7 tests plus `test_probe_scrubs_pythonpath_and_editable_state`. 3. Run the focused file and record missing-harness failure.
- **Evidence:** red output and negative-control proof.
- **Stop:** test can pass from checkout or needs downloads/live effects.
- **Verified outcome:** P51.3.2 may create the harness.

#### P51.3.2 — GREEN: probe wheel and sdist independently

- **Task ID and binary outcome:** P51.3.2; harness detects the broken control and emits separate artifact results on both CI platforms.
- **Start goal:** Satisfy P51.3.1 without fixing packaging.
- **Prerequisites:** recorded P51.3.1 RED.
- **Documentation impact:** None.
- **Dependency impact:** None.
- **Allowed writes:** create `scripts/probe_installed_artifacts.py`, modify `.github/workflows/ci.yml`, modify `.github/workflows/release.yml`, and modify `tests/test_phase51_artifact_probes.py` only to retain or strengthen its original assertions.
- **Allowed reads:** `pyproject.toml`, operation manifest, workflow conventions.
- **Prohibited:** `pyproject.toml`, `uv.lock`, runtime behavior, live probes.
- **Actions:** 1. Reinspect the runner contract and workflow jobs. 2. Implement `uv build`, separate fresh installs, empty external CWD, cleared `PYTHONPATH`, installed-origin assertions, and manifest probe dispatch; add Windows/POSIX jobs. 3. Run focused tests, local harness, and Ruff on scripts/tests; inspect workflow diff.
- **Evidence:** artifact-specific results, origins, negative-control rejection.
- **Stop:** checkout import, live effect, or dependency change.
- **Verified outcome:** Phase 52 receives reproducible R-001 evidence.

### P51.4 — Engine taxonomy

#### P51.4.1 — RED: define engine support policy

- **Task ID and binary outcome:** P51.4.1; three named tests fail because policy records are absent.
- **Start goal:** Pin one class per family and prevent ambient/all-skipped conformance.
- **Prerequisites:** P51.0.1.
- **Documentation impact:** None.
- **Dependency impact:** None.
- **Allowed writes:** create `tests/test_phase51_engine_policy.py`.
- **Allowed reads:** tool adapters, common runner, static-tool tests, workflows.
- **Prohibited:** source/manifest/CI/docs/dependencies/XFAIL.
- **Actions:** 1. Inventory families and arrange fixed PATH plus success/failure/malformed/missing fakes. 2. Add exactly the three §7 tests plus `test_supported_family_has_success_failure_and_malformed_evidence`. 3. Run the focused file and record missing-policy failure.
- **Evidence:** family inventory and red output.
- **Stop:** roadmap cannot determine a family’s class.
- **Verified outcome:** P51.4.2 may write the taxonomy.

#### P51.4.2 — GREEN: publish engine policy

- **Task ID and binary outcome:** P51.4.2; every family has one complete record and tests pass.
- **Start goal:** Satisfy P51.4.1 without adapter changes.
- **Prerequisites:** recorded P51.4.1 RED.
- **Documentation impact:** None.
- **Dependency impact:** None.
- **Allowed writes:** create `governance/engine-support.toml`, modify `scripts/build_remediation_manifests.py`, and modify `tests/test_phase51_engine_policy.py` only to retain or strengthen its original assertions.
- **Allowed reads:** adapters, tests, P51.4.1 inventory.
- **Prohibited:** adapter/CI/docs/dependency changes or fabricated conformance.
- **Actions:** 1. Reinspect every family. 2. Write class, executable, version source, fixtures, provisioned job, skip policy; reject omission/duplicate. 3. Run focused and `tests/test_static_tools.py` with fixed PATH.
- **Evidence:** green output and full family table.
- **Stop:** supported family lacks provisionable version or malformed case.
- **Verified outcome:** Phase 59 receives exact engine policy.

### P51.5 — Cross-phase ownership

#### P51.5.1 — EVIDENCE: assign every finding to one later RED/GREEN pair

- **Task ID and binary outcome:** P51.5.1; R-001 through R-016 each have one complete owner record.
- **Start goal:** Prevent omission/duplication without writing later tests.
- **Prerequisites:** P51.1.2-P51.4.2.
- **Documentation impact:** None.
- **Dependency impact:** None.
- **Allowed writes:** create `governance/remediation-contracts.toml` and modify `scripts/build_remediation_manifests.py`.
- **Allowed reads:** roadmap, Phases 52-60 plans, current seams, Phase 51 artifacts.
- **Prohibited:** source/tests/workflows/docs/dependencies/XFAIL/finding-closed claims.
- **Actions:** 1. Match every finding to exact later RED/GREEN cards. 2. Write finding, owner, test file/function, control, seam, predecessor, docs owner, release effect. 3. Reconcile against roadmap and plans; run existing manifest unit tests and confirm zero missing/duplicate owners.
- **Evidence:** complete owner table.
- **Stop:** any later plan lacks an exact RED/GREEN pair.
- **Verified outcome:** successor ownership is closed.

### P51.6 — Documentation and handoff

#### P51.6.1 — DOCS/HANDOFF: close Phase 51

- **Task ID and binary outcome:** P51.6.1; named docs and Phase record cite only passing Phase 51 evidence.
- **Start goal:** Document implemented baseline and successor entry evidence.
- **Prerequisites:** P51.1.2-P51.5.1.
- **Documentation impact:** `docs/DISTRIBUTION.md`, `docs/ENGINES.md`, `docs/CLI_REFERENCE.md`, `docs/MCP_REFERENCE.md`, `docs/developer/ci-and-packaging.md`, `docs/developer/testing-guide.md`, and `docs/maintainers/release-playbook.md`; add manifest locations, operation classes, probe isolation, engine policy, and finding ownership.
- **Dependency impact:** None.
- **Allowed writes:** `docs/DISTRIBUTION.md`, `docs/ENGINES.md`, `docs/CLI_REFERENCE.md`, `docs/MCP_REFERENCE.md`, `docs/developer/ci-and-packaging.md`, `docs/developer/testing-guide.md`, `docs/maintainers/release-playbook.md`, and the evidence section of `governance/remediation-phase-51.toml`.
- **Allowed reads:** passing artifacts/tests/workflows.
- **Prohibited:** source/tests/workflows/dependencies/roadmap or remediation-success claims.
- **Actions:** 1. Map each intended doc statement to passing evidence. 2. Update only named sections and record digests/commands/handoffs. 3. Run §10 and compare every changed path to a task card.
- **Evidence:** commands, digests, docs diff, handoff table.
- **Stop:** unowned path or claim that a later finding is fixed.
- **Verified outcome:** eligible successors may consume Phase 51 artifacts.

## 10. Final verification and delivery gate

```text
$env:VIRTUAL_ENV=$null
$env:PYTHONPATH=$null
.venv/Scripts/python.exe -m pytest tests/test_phase51_coverage_manifest.py tests/test_phase51_public_operations.py tests/test_phase51_artifact_probes.py tests/test_phase51_engine_policy.py -q
.venv/Scripts/python.exe -m pytest tests/ -q
.venv/Scripts/ruff.exe check src tests scripts
.venv/Scripts/ruff.exe format --check src tests scripts
uv build
.venv/Scripts/python.exe scripts/probe_installed_artifacts.py
git diff --check
git diff --name-only
git status --short --branch
```

No live credential, network, plugin, destructive, or release action is permitted.

## 11. Exit checklist and successor evidence

- [ ] Admission evidence is exact and parseable.
- [ ] Coverage is exhaustive, single-classified, and byte-stable.
- [ ] Every retained route reconciles once and has a safe probe.
- [ ] Wheel/sdist probes are independent and reject checkout origins.
- [ ] Engine policy is complete and cannot pass supported families all-skipped.
- [ ] Every finding maps to one later ordinary RED/GREEN pair.
- [ ] No skip, XFAIL, XPASS, permanently red suite, dependency change, or roadmap edit is closure evidence.
- [ ] Every changed path belongs to one task card.
