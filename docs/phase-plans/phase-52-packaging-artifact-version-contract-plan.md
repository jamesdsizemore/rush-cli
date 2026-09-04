# Phase 52 implementation plan — package identity, installed artifacts, and version authority

## 1. Purpose and status

- **Operation:** Create the implementation plan for remediation Phase 1.
- **Planning status:** Complete.
- **Implementation status:** Complete (P52.0-P52.5).
- **Authority:** `docs/developer/repository-remediation-plan.md`, R-001 and R-012.
- **Predecessor:** Accepted Phase 51 coverage, operation, and artifact-probe evidence (revision `0dc2c11`, baseline 975 passing tests, `governance/remediation-phase-51.toml`).
- **Parallelism:** May run beside Phase 53; Phases 57 and 59 consume its handoff.
- **Protected:** governing roadmap, adversarial review, Phase 51 manifests except task-owned evidence fields.
- **Amendment rule:** A newly found `src.rush` import or Rush-version consumer must be added as a literal task write before editing.
- **Lifecycle boundary:** No commit, push, merge, tag, publish, release, hooks, or history rewrite.

## 2. Authority, evidence, and decisions

### 2.1 Authority order

User instructions → repository `AGENTS.md` → governing roadmap → accepted Phase 51 artifacts → current package/tests/docs evidence.

### 2.2 Current-state evidence

- `pyproject.toml` packages `src/rush` but test configuration exposes `.` and `src` via `pythonpath = [".", "src"]`.
- Phase 51 coverage evidence identifies 74 first-party `src.rush` imports across 15 production files (24 imports) and 14 test files (50 imports).
- Version literals/consumers exist in `src/rush/__init__.py`, CLI/user-agent, scaffolder, providers, SARIF, TypeScript generator, PR synthesis, and TUI seams.
- Phase 51 installed probes reproduce the current artifact startup/origin failure (`ModuleNotFoundError: No module named 'src'`).

### 2.3 Closed decisions

- Canonical import namespace is `rush`; no top-level `src` package, alias, shim, or `sys.path` workaround.
- Public Rush version comes from `importlib.metadata.version("rush-cli")`; only `PackageNotFoundError` permits an explicit development fallback.
- Wheel and sdist must pass independently from an empty external CWD on Windows and POSIX.
- No dependency addition or lockfile change.

### 2.4 Open decisions

None. A packaging change beyond the exact `pyproject.toml` package-data/package-selection seam blocks for amendment.

## 3. Goals, outcomes, exclusions, and invariants

Outcomes: zero first-party `src.rush` imports; one module identity in local/installed tests; one metadata-derived version; independent installed wheel/sdist operation probes.

Exclusions: provenance semantics (Phase 59), new dependencies, editable-install evidence, unrelated import refactors, historical external-version fixtures.

Inherited invariants: Phase 51 safe probes and checkout-origin negative control remain unchanged; CLI/MCP names and behavior do not change.

## 4. Admission and predecessor gate

Require Phase 51 accepted evidence: exact revision, coverage manifest, public-operation manifest, and artifact harness results. Re-run the current harness once and record its R-001 failure. Record `git status --short`; stop on overlapping edits to any §8 path. Do not start source work until P52.0.1 passes.

## 5. Requirement-ownership ledger

| Requirement | Tasks | Closure |
|---|---|---|
| R-001 canonical namespace | P52.1.1-P52.2.2 | no `src.rush`, one collection/import identity |
| R-001 installed wheel/sdist | P52.4.1-P52.4.2 | external-CWD artifact matrix |
| R-012 metadata version | P52.3.1-P52.3.2 | runtime/generated consumer matrix |
| Shipping documentation and handoff | P52.5.1 | exact docs and Phase 57/59 evidence |

## 6. Shared contracts and handoff

- `rush` is the only runtime/import namespace.
- `rush.__version__` is metadata-derived; the source-checkout fallback is a named non-release value.
- Artifact evidence records artifact family, digest, install environment, CWD, scrubbed variables, imported origins, version, and per-operation result.
- Phase 57 receives installed build identity; Phase 59 receives artifact digests/package/version identity.

## 7. Contract-test inventory

| Contract | RED | GREEN | Exact tests |
|---|---|---|---|
| No `src.rush` imports | P52.1.1 | P52.1.2 | `tests/test_phase52_package_identity.py::test_first_party_python_contains_no_src_rush_import`; `::test_broken_src_rush_import_fails_in_isolated_install` |
| Test/import isolation | P52.2.1 | P52.2.2 | `::test_pytest_configuration_does_not_expose_repository_root_as_src_package`; `::test_installed_collection_uses_one_rush_origin` |
| Version authority | P52.3.1 | P52.3.2 | `tests/test_phase52_version_contract.py::test_public_version_comes_from_distribution_metadata`; `::test_development_fallback_is_explicit`; `::test_every_runtime_consumer_uses_public_version` |
| Artifact parity | P52.4.1 | P52.4.2 | `tests/test_phase52_installed_artifacts.py::test_wheel_and_sdist_pass_every_safe_probe`; `::test_artifact_imports_never_resolve_to_checkout_or_src` |

Every RED test is ordinary, deterministic, and immediately consumed by its GREEN task.

## 8. File, dependency, and documentation governance

### 8.1 Import-write inventory

Production (15 files, 24 imports): `src/rush/codegraph/context_packer.py`, `src/rush/core/git_sandbox.py`, `src/rush/memory/mistake_miner.py`, `src/rush/token_economy/distillers/__init__.py`, `src/rush/token_economy/distillers/cargo_distiller.py`, `src/rush/token_economy/distillers/pytest_distiller.py`, `src/rush/token_economy/distillers/ruff_distiller.py`, `src/rush/token_economy/distillers/vitest_distiller.py`, `src/rush/token_economy/toon/__init__.py`, `src/rush/token_economy/tui_gain.py`, `src/rush/tools/api_diff.py`, `src/rush/tools/hallu_guard.py`, `src/rush/tools/ship/cockpit.py`, `src/rush/tools/simulate_ci.py`, `src/rush/tools/test_heal.py`.

Tests (14 files, 50 imports): `tests/test_cli_registry.py`, `tests/test_phase41_memory_ship.py`, `tests/test_phase41_router_distillers.py`, `tests/test_phase42_ship_cockpit.py`, `tests/test_phase42_toon_skeleton.py`, `tests/test_phase43_ccr_grounding.py`, `tests/test_phase43_mistake_memory.py`, `tests/test_phase44_context_pack_cache.py`, `tests/test_phase45_telemetry_gain.py`, `tests/test_phase46_blast_radius_arch.py`, `tests/test_phase47_heal_apidiff.py`, `tests/test_phase48_db_simplify_strict.py`, `tests/test_phase49_trace_swarm_recorder.py`, `tests/test_phase50_slsa_attestation.py`.

### 8.2 Version/artifact inventory

`src/rush/__init__.py`, `src/rush/cli.py`, `src/rush/governance/scaffolder.py`, `src/rush/providers/anthropic.py`, `src/rush/providers/openai.py`, `src/rush/sarif.py`, `src/rush/score/sarif_export.py`, `src/rush/sync/ts_generator.py`, `src/rush/tools/pr_synthesize.py`, `src/rush/tui.py`, `pyproject.toml`, `.github/workflows/ci.yml`, `.github/workflows/release.yml`, `scripts/probe_installed_artifacts.py`, `tests/test_phase52_package_identity.py`, `tests/test_phase52_version_contract.py`, `tests/test_phase52_installed_artifacts.py`.

### 8.3 Documentation

Only P52.5.1 may edit `README.md`, `CHANGELOG.md`, `docs/DISTRIBUTION.md`, `docs/VERSIONING.md`, `docs/COMPATIBILITY.md`, `docs/RELEASE.md`, `docs/developer/ci-and-packaging.md`, `docs/maintainers/release-playbook.md`, and `docs/maintainers/versioning-and-compatibility.md`.

All other writes are prohibited. No dependency change; `uv.lock` is protected.

## 9. Ordered workstreams and atomic task cards

### P52.0 — Admission

#### P52.0.1 — EVIDENCE: record exact package/version seams

- **Task ID and binary outcome:** P52.0.1; one Phase 52 evidence entry lists every current import/version hit and the exact Phase 51 artifact failure.
- **Start goal:** Close scope before tests.
- **Prerequisites:** §4.
- **Documentation impact:** None.
- **Dependency impact:** None.
- **Allowed writes:** create `governance/remediation-phase-52.toml`.
- **Allowed reads:** `governance/first-party-coverage.toml`, `governance/public-operations.toml`, `governance/remediation-phase-51.toml`, `pyproject.toml`, `scripts/probe_installed_artifacts.py`, every literal production/test path in the P52.1.1 allowed-read list, every literal version path in the P52.3.1 allowed-read list, `.github/workflows/ci.yml`, `.github/workflows/release.yml`, and the nine documentation paths owned by P52.5.1.
- **Prohibited:** source/tests/docs/workflows/dependencies.
- **Actions:** 1. Inspect every manifest-scoped hit and artifact result. 2. Record path, symbol/line, category, owning task, and current failure. 3. Reconcile record count with coverage search and reparse TOML.
- **Evidence:** exact hit inventory and artifact command/result.
- **Stop:** a hit lacks literal write ownership.
- **Verified outcome:** P52.1.1-P52.4.1 may start.

### P52.1 — Canonical imports

#### P52.1.1 — RED: prove dual namespace remains

- **Task ID and binary outcome:** P52.1.1; two ordinary tests fail on current `src.rush` usage.
- **Start goal:** Pin manifest scan and isolated negative control.
- **Prerequisites:** P52.0.1.
- **Documentation impact:** None.
- **Dependency impact:** None.
- **Allowed writes:** create `tests/test_phase52_package_identity.py`.
- **Allowed reads:** `governance/first-party-coverage.toml`, `scripts/probe_installed_artifacts.py`, `src/rush/codegraph/context_packer.py`, `src/rush/core/git_sandbox.py`, `src/rush/memory/mistake_miner.py`, `src/rush/token_economy/distillers/__init__.py`, `src/rush/token_economy/distillers/cargo_distiller.py`, `src/rush/token_economy/distillers/pytest_distiller.py`, `src/rush/token_economy/distillers/ruff_distiller.py`, `src/rush/token_economy/distillers/vitest_distiller.py`, `src/rush/token_economy/toon/__init__.py`, `src/rush/token_economy/tui_gain.py`, `src/rush/tools/api_diff.py`, `src/rush/tools/hallu_guard.py`, `src/rush/tools/ship/cockpit.py`, `src/rush/tools/simulate_ci.py`, `src/rush/tools/test_heal.py`, `tests/test_cli_registry.py`, `tests/test_phase41_memory_ship.py`, `tests/test_phase41_router_distillers.py`, `tests/test_phase42_ship_cockpit.py`, `tests/test_phase42_toon_skeleton.py`, `tests/test_phase43_ccr_grounding.py`, `tests/test_phase43_mistake_memory.py`, `tests/test_phase44_context_pack_cache.py`, `tests/test_phase45_telemetry_gain.py`, `tests/test_phase46_blast_radius_arch.py`, `tests/test_phase47_heal_apidiff.py`, `tests/test_phase48_db_simplify_strict.py`, `tests/test_phase49_trace_swarm_recorder.py`, `tests/test_phase50_slsa_attestation.py`.
- **Prohibited:** production/import/config/docs/workflow changes, skip/XFAIL.
- **Actions:** 1. Arrange manifest-scoped AST scan and broken isolated import fixture. 2. Add the two §7 tests; Act through the Phase 51 harness for the negative case. 3. Run the focused file and record assertion failures, not collection failure.
- **Evidence:** test IDs and red output.
- **Stop:** scan includes third-party/generated historical content outside manifest policy.
- **Verified outcome:** P52.1.2 may edit only the literal import-hit paths named on its card.

#### P52.1.2 — GREEN: replace every first-party `src.rush` import

- **Task ID and binary outcome:** P52.1.2; manifest scan is zero and imported symbols remain identical.
- **Start goal:** Satisfy P52.1.1 only.
- **Prerequisites:** recorded P52.1.1 RED.
- **Documentation impact:** None.
- **Dependency impact:** None.
- **Allowed writes:** `src/rush/codegraph/context_packer.py`, `src/rush/core/git_sandbox.py`, `src/rush/memory/mistake_miner.py`, `src/rush/token_economy/distillers/__init__.py`, `src/rush/token_economy/distillers/cargo_distiller.py`, `src/rush/token_economy/distillers/pytest_distiller.py`, `src/rush/token_economy/distillers/ruff_distiller.py`, `src/rush/token_economy/distillers/vitest_distiller.py`, `src/rush/token_economy/toon/__init__.py`, `src/rush/token_economy/tui_gain.py`, `src/rush/tools/api_diff.py`, `src/rush/tools/hallu_guard.py`, `src/rush/tools/ship/cockpit.py`, `src/rush/tools/simulate_ci.py`, `src/rush/tools/test_heal.py`, `tests/test_cli_registry.py`, `tests/test_phase41_memory_ship.py`, `tests/test_phase41_router_distillers.py`, `tests/test_phase42_ship_cockpit.py`, `tests/test_phase42_toon_skeleton.py`, `tests/test_phase43_ccr_grounding.py`, `tests/test_phase43_mistake_memory.py`, `tests/test_phase44_context_pack_cache.py`, `tests/test_phase45_telemetry_gain.py`, `tests/test_phase46_blast_radius_arch.py`, `tests/test_phase47_heal_apidiff.py`, `tests/test_phase48_db_simplify_strict.py`, `tests/test_phase49_trace_swarm_recorder.py`, `tests/test_phase50_slsa_attestation.py`, and `tests/test_phase52_package_identity.py`.
- **Allowed reads:** P52.1.1 evidence and imported symbol definitions.
- **Prohibited:** behavior/refactor/sys.path/alias/package config/docs/workflows.
- **Actions:** 1. Reinspect each hit and target symbol. 2. Replace only `src.rush` with canonical `rush` or established relative import; preserve names/aliases. 3. Run focused tests, then all specifically changed historical phase test files.
- **Evidence:** zero-hit scan and green affected suites.
- **Stop:** import cycle or symbol mismatch; amend with exact resolution rather than adding a shim.
- **Verified outcome:** P52.2.1 may test collection isolation.

### P52.2 — Collection identity

#### P52.2.1 — RED: prove pytest exposes the repository root

- **Task ID and binary outcome:** P52.2.1; two tests fail on current pythonpath/origin behavior.
- **Start goal:** Pin one local/installed module identity.
- **Prerequisites:** P52.1.2.
- **Documentation impact:** None.
- **Dependency impact:** None.
- **Allowed writes:** `tests/test_phase52_package_identity.py`.
- **Allowed reads:** `pyproject.toml`, pytest collection config, installed harness.
- **Prohibited:** config/source/docs/workflows/skip/XFAIL.
- **Actions:** 1. Arrange scrubbed `VIRTUAL_ENV`/`PYTHONPATH` collection and installed-origin capture. 2. Add the two collection tests from §7 and assert no importable top-level `src`. 3. Run focused tests and record current assertion failure.
- **Evidence:** red output and observed origins.
- **Stop:** failure comes from P52.1 regressions or missing environment.
- **Verified outcome:** P52.2.2 may edit only pytest/package selection config.

#### P52.2.2 — GREEN: remove root-assisted package leakage

- **Task ID and binary outcome:** P52.2.2; scrubbed local and installed collection use only `rush`.
- **Start goal:** Satisfy P52.2.1 without compatibility shims.
- **Prerequisites:** recorded P52.2.1 RED.
- **Documentation impact:** None.
- **Dependency impact:** None.
- **Allowed writes:** `pyproject.toml`, `tests/test_phase52_package_identity.py`.
- **Allowed reads:** pytest/hatch configuration and P52.2.1 evidence.
- **Prohibited:** dependency/tool version changes, `uv.lock`, source aliases, docs/workflows.
- **Actions:** 1. Reinspect exact `pythonpath` and wheel package keys. 2. Remove only root exposure and retain source-layout configuration needed for canonical local imports. 3. Run focused tests, `.venv/Scripts/python.exe -m pytest tests/ -q` with variables cleared, and Phase 51 origin negative control.
- **Evidence:** green collection and one origin per module.
- **Stop:** config change alters dependency or build backend.
- **Verified outcome:** P52.4.1 may rely on canonical collection.

### P52.3 — Version authority

#### P52.3.1 — RED: define metadata-derived version consumers

- **Task ID and binary outcome:** P52.3.1; named tests fail on copied literals/current fallback.
- **Start goal:** Pin source/editable/artifact version and every runtime/generated consumer.
- **Prerequisites:** P52.0.1.
- **Documentation impact:** None.
- **Dependency impact:** None.
- **Allowed writes:** create `tests/test_phase52_version_contract.py`.
- **Allowed reads:** `src/rush/__init__.py`, `src/rush/cli.py`, `src/rush/governance/scaffolder.py`, `src/rush/providers/anthropic.py`, `src/rush/providers/openai.py`, `src/rush/sarif.py`, `src/rush/score/sarif_export.py`, `src/rush/sync/ts_generator.py`, `src/rush/tools/attest.py`, `src/rush/tools/pr_synthesize.py`, `src/rush/tui.py`, `pyproject.toml`, `tests/test_packaging_and_versioning.py`, and `tests/test_skeleton.py`.
- **Prohibited:** production/docs/config/workflows/fixtures representing external versions/XFAIL.
- **Actions:** 1. Arrange patched `importlib.metadata.version` and `PackageNotFoundError` plus consumer table. 2. Add the three §7 tests and explicit assertions for CLI user agent, providers, SARIF, scaffolder, TS header, TUI, attest, PR synthesis. 3. Run focused tests and record contract assertion failures.
- **Evidence:** consumer table and red output.
- **Stop:** a candidate is a historical/external-tool version rather than Rush.
- **Verified outcome:** P52.3.2 may edit exact consumers.

#### P52.3.2 — GREEN: route all Rush version consumers through metadata

- **Task ID and binary outcome:** P52.3.2; all version tests pass with one source.
- **Start goal:** Satisfy P52.3.1 only.
- **Prerequisites:** recorded P52.3.1 RED.
- **Documentation impact:** None; P52.5.1 owns docs.
- **Dependency impact:** None.
- **Allowed writes:** `src/rush/__init__.py`, `src/rush/cli.py`, `src/rush/governance/scaffolder.py`, `src/rush/providers/anthropic.py`, `src/rush/providers/openai.py`, `src/rush/sarif.py`, `src/rush/score/sarif_export.py`, `src/rush/sync/ts_generator.py`, `src/rush/tools/attest.py`, `src/rush/tools/pr_synthesize.py`, `src/rush/tui.py`, and `tests/test_phase52_version_contract.py`.
- **Allowed reads:** P52.3.1 evidence and current consumer constructors.
- **Prohibited:** unrelated generated text, provenance semantics, docs/package config/dependencies.
- **Actions:** 1. Reinspect exact consumer symbols. 2. Implement `rush.__version__` via metadata, catch only `PackageNotFoundError`, use explicit development fallback, and replace copied Rush literals at listed consumers. 3. Run focused tests, `tests/test_packaging_and_versioning.py`, and `tests/test_skeleton.py`.
- **Evidence:** green consumer matrix and zero unowned literals.
- **Stop:** consumer requires a new compatibility/version policy.
- **Verified outcome:** P52.4.1 receives stable version identity.

### P52.4 — Artifact parity

#### P52.4.1 — RED: define complete installed-artifact success

- **Task ID and binary outcome:** P52.4.1; artifact tests fail on current wheel/sdist startup/probe behavior.
- **Start goal:** Convert Phase 51 evidence into ordinary Phase 52 contract tests.
- **Prerequisites:** P52.2.2 and P52.3.2.
- **Documentation impact:** None.
- **Dependency impact:** None.
- **Allowed writes:** create `tests/test_phase52_installed_artifacts.py`.
- **Allowed reads:** Phase 51 harness/results, operation manifest, `pyproject.toml`, workflows.
- **Prohibited:** packaging/script/workflow/source/docs changes, editable installs, XFAIL.
- **Actions:** 1. Arrange fake harness result fixtures and one bounded real local probe. 2. Add the two §7 tests plus `test_artifact_version_matches_distribution_metadata` and `test_windows_and_posix_jobs_cover_both_artifacts`. 3. Run focused tests and record current artifact assertion failure.
- **Evidence:** artifact-specific red output.
- **Stop:** test passes using checkout, one artifact, or one platform only.
- **Verified outcome:** P52.4.2 may change packaging/harness/workflows.

#### P52.4.2 — GREEN: make wheel and sdist probes pass

- **Task ID and binary outcome:** P52.4.2; both artifacts pass all safe probes on both platforms with installed origins.
- **Start goal:** Satisfy P52.4.1 only.
- **Prerequisites:** recorded P52.4.1 RED.
- **Documentation impact:** None.
- **Dependency impact:** None.
- **Allowed writes:** `pyproject.toml` package-selection/data keys only, `.github/workflows/ci.yml` Phase 51 artifact job only, `.github/workflows/release.yml` Phase 51 artifact job only, `scripts/probe_installed_artifacts.py`, and `tests/test_phase52_installed_artifacts.py` only to retain or strengthen its original assertions.
- **Allowed reads:** package tree, manifests, P52.4.1 evidence.
- **Prohibited:** dependencies/build backend/version constraints/`uv.lock`/runtime behavior.
- **Actions:** 1. Reinspect built archive contents and failure origins. 2. Change only packaging inclusion needed for `rush` and required package data; update harness/jobs only for passing-result assertions. 3. Run `uv build`, focused tests, full harness from external CWD, then full suite and Ruff.
- **Evidence:** wheel/sdist digests, origins, operation results, CI job matrix.
- **Stop:** fix requires top-level `src`, editable install, dependency, or runtime workaround.
- **Verified outcome:** R-001/R-012 implementation evidence is complete.

### P52.5 — Documentation and handoff

#### P52.5.1 — DOCS/HANDOFF: publish package/version truth

- **Task ID and binary outcome:** P52.5.1; named docs and handoffs cite passing artifact/version evidence.
- **Start goal:** Update shipping claims only after behavior passes.
- **Prerequisites:** P52.1.2-P52.4.2.
- **Documentation impact:** `README.md`, `CHANGELOG.md`, `docs/DISTRIBUTION.md`, `docs/VERSIONING.md`, `docs/COMPATIBILITY.md`, `docs/RELEASE.md`, `docs/developer/ci-and-packaging.md`, `docs/maintainers/release-playbook.md`, and `docs/maintainers/versioning-and-compatibility.md`; explain canonical namespace, metadata version, source fallback, artifact matrix, external-CWD rule, and release use.
- **Dependency impact:** None.
- **Allowed writes:** `README.md`, `CHANGELOG.md`, `docs/DISTRIBUTION.md`, `docs/VERSIONING.md`, `docs/COMPATIBILITY.md`, `docs/RELEASE.md`, `docs/developer/ci-and-packaging.md`, `docs/maintainers/release-playbook.md`, `docs/maintainers/versioning-and-compatibility.md`, and Phase 52 evidence fields in `governance/remediation-contracts.toml`.
- **Allowed reads:** passing tests, artifact outputs, manifest-scoped stale version hits.
- **Prohibited:** source/tests/config/workflows/dependencies/provenance claims outside version wording.
- **Actions:** 1. Map each stale shipping claim to evidence. 2. Update only named docs and record artifact/version handoffs to Phases 57/59. 3. Run §10 and compare every changed path to a task card.
- **Evidence:** docs diff, commands, artifact identities, handoff.
- **Stop:** unowned path or unsupported assurance claim.
- **Verified outcome:** Phase 52 closes R-001/R-012 and successors may consume its identities.

## 10. Final verification and delivery gate

```text
$env:VIRTUAL_ENV=$null
$env:PYTHONPATH=$null
.venv/Scripts/python.exe -m pytest tests/test_phase52_package_identity.py tests/test_phase52_version_contract.py tests/test_phase52_installed_artifacts.py -q
.venv/Scripts/python.exe -m pytest tests/ -q
.venv/Scripts/ruff.exe check src tests scripts
.venv/Scripts/ruff.exe format --check src tests scripts
uv build
.venv/Scripts/python.exe scripts/probe_installed_artifacts.py
git diff --check
git diff --name-only
git status --short --branch
```

## 11. Exit checklist and successor evidence

- [ ] Zero first-party `src.rush` imports and no top-level `src` compatibility path.
- [ ] Scrubbed local/installed collection uses one `rush` identity.
- [ ] Every Rush version consumer derives from distribution metadata.
- [ ] Wheel and sdist independently pass every safe probe on Windows/POSIX outside checkout.
- [ ] No dependency/lockfile change, editable-install evidence, skip, XFAIL, or XPASS.
- [ ] Every changed path belongs to one task.
- [ ] Phase 57 receives installed build identity; Phase 59 receives artifact/package/version evidence.
