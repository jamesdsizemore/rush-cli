# Phase 59 implementation plan — truthful provenance and deterministic engine conformance

## 1. Purpose and status

- **Operation:** Create the implementation plan for remediation Phase 8.
- **Planning status:** Implementation-ready after §4 admission passes.
- **Implementation status:** Not authorized.
- **Authority:** governing roadmap R-013 and R-014.
- **Predecessors:** accepted Phase 52 artifact/version identity, Phase 53 sanitizer, Phase 54 result adapters, Phase 58 release-critical boundary evidence, and Phase 51 engine policy.
- **Release relationship:** This phase produces final release-readiness evidence for R-001-R-014 and R-016; R-015 remains Phase 60 non-release work.
- **Protected:** roadmap, dependencies/lockfile, historical Phase 50 plan evidence.
- **Amendment rule:** Any schema/type/build/source/signer/engine policy, dependency, fixture provenance, or path outside a card requires amendment.
- **Lifecycle boundary:** No live keys, signing, publishing, release, commit, push, merge, tag, hooks, or history rewrite.

## 2. Authority, evidence, and decisions

Authority order: user → `AGENTS.md` → roadmap → accepted Phase 51/52/53/54/58 artifacts → current attest/provenance/engine/CI evidence.

Current evidence: local output can claim unsupported attestation/provenance assurance; subject identity can use commit instead of artifact; parsing can accept duplicate/ambiguous keys; signer/builder/source/type policy is incomplete; ambient PATH and all-skipped tests can masquerade as engine conformance.

Closed decisions: default output is explicitly unsigned provenance draft; subject is actual artifact digest plus package identity; in-toto Statement v1 and SLSA provenance v1 predicate; duplicate/normalization ambiguity rejects before schema/signature policy; optional signed mode requires exact allowlisted signer, trusted root, builder, subject/package/type/buildType/parameters/source; fixed-PATH deterministic suite plus provisioned success/failure/malformed jobs.

Open decisions: None. No new dependency; use existing `cryptography`, `ruamel.yaml`, and stdlib duplicate-detecting JSON parsing.

## 3. Goals, outcomes, exclusions, and invariants

Outcomes: evidence-only unsigned draft; pinned structure; strict parsing; exact optional signed policy using synthetic fixtures; deterministic engine taxonomy/conformance; complete release-readiness handoff.

Exclusions: live signing/key authority, provider publication, dependency changes, R-015.

Invariants: missing evidence returns skipped/error, never fabricated claims; ambiguous provenance never reaches policy; supported engine family cannot pass all-skipped.

## 4. Admission and predecessor gate

Require accepted predecessor records and green installed artifact/public-operation/fault matrices. Reconcile current shipping provenance/engine claims through Phase 51 coverage. Inventory engine families and CI provisioning. Stop on overlapping edits. P59.0.1 freezes every subject/claim/parser/policy/engine branch before RED tasks.

## 5. Requirement-ownership ledger

| Requirement | Tasks | Closure |
|---|---|---|
| Unsigned draft/artifact subject | P59.1.1-P59.1.2 | wheel/sdist draft matrix |
| Statement/predicate structure | P59.2.1-P59.2.2 | exact schema fixtures |
| Duplicate/ambiguity rejection | P59.3.1-P59.3.2 | raw/decoded/nested parser matrix |
| Optional signed policy | P59.4.1-P59.4.2 | signer/builder/source mismatch matrix |
| Engine conformance | P59.5.1-P59.5.2 | fixed-PATH/provisioned CI matrix |
| Docs/release handoff | P59.6.1 | coverage-scoped claims and release record |

## 6. Shared contracts and handoff

Unsigned draft contains actual Phase 52 artifact subjects and collected metadata only; it never claims signature, verified builder, reproducibility, completeness, or SLSA level.

Strict parser preserves object pairs and rejects duplicate or normalized-equivalent policy keys in raw envelope, decoded Statement, predicate, builder, external parameters, and extensions before ordinary mappings.

Signed policy requires exact allowlists/trusted root and equality of signer, builder ID, artifact/package subject, statement/predicate type, buildType, external parameters, and source constraints.

## 7. Contract-test inventory

| Contract | RED | GREEN | Exact ordinary tests |
|---|---|---|---|
| Draft/subject | P59.1.1 | P59.1.2 | `test_default_output_is_explicit_unsigned_draft`; `test_subject_is_actual_artifact_and_package_identity`; `test_missing_evidence_never_fabricates_claim` |
| Structure | P59.2.1 | P59.2.2 | `test_statement_and_predicate_types_are_exact`; `test_build_type_parameters_source_subject_and_extensions_are_pinned` |
| Strict parse | P59.3.1 | P59.3.2 | `test_duplicate_keys_at_every_raw_decoded_nested_level_reject`; `test_unicode_and_escaped_key_ambiguity_rejects_before_policy` |
| Signed policy | P59.4.1 | P59.4.2 | `test_valid_synthetic_signed_envelope_passes_exact_policy`; `test_each_signer_builder_root_subject_type_parameter_source_mismatch_rejects` |
| Engines | P59.5.1 | P59.5.2 | `test_every_engine_has_one_taxonomy_entry`; `test_supported_family_has_success_failure_and_malformed_jobs`; `test_supported_family_all_skipped_fails`; `test_fixed_path_ignores_ambient_tools`; `test_release_gate_mypy_is_provisioned_and_non_skipped` |

## 8. File, dependency, and documentation governance

New: `src/rush/release/provenance_policy.py`, `src/rush/engines/support_policy.py`, `tests/test_phase59_provenance_draft.py`, `tests/test_phase59_provenance_structure.py`, `tests/test_phase59_provenance_parser.py`, `tests/test_phase59_provenance_policy.py`, `tests/test_phase59_engine_conformance.py`, `tests/fixtures/remediation/provenance/unsigned-draft.json`, `tests/fixtures/remediation/provenance/signed-valid-envelope.json`, `tests/fixtures/remediation/provenance/signed-invalid-envelopes.json`.

Existing task-owned: `src/rush/tools/attest.py`, `src/rush/release/provenance.py`, `src/rush/release/__init__.py`, `src/rush/engines/__init__.py`, `src/rush/cli.py`, `src/rush/mcp.py`, `src/rush/contracts/operations.py`, `src/rush/contracts/results.py`, `src/rush/safety/redactor.py`, `governance/engine-support.toml`, `governance/public-operations.toml`, `governance/remediation-contracts.toml`, `.github/workflows/ci.yml`, `.github/workflows/release.yml`, `tests/test_phase50_slsa_attestation.py`, `tests/test_supply_chain_tools.py`, `tests/test_static_tools.py`, `tests/test_capabilities.py`, `tests/conftest.py`.

Docs owned only by P59.6.1: `README.md`, `docs/ENGINES.md`, `docs/ENGINE_COMPATIBILITY.md`, `docs/DISTRIBUTION.md`, `docs/RELEASE.md`, `docs/SECURITY.md`, `docs/TOOL_CATALOG.md`, `docs/reference/engine-directory.md`, `docs/reference/result-reference.md`, `docs/developer/ci-and-packaging.md`, `docs/maintainers/release-playbook.md`, `docs/maintainers/versioning-and-compatibility.md`.

All other writes prohibited. Python project dependency changes: None. Required existing dependencies/contracts: `cryptography==50.0.0`, `ruamel.yaml==0.19.1`, Python 3.12 duplicate-preserving JSON parsing, Phase 52 artifact identity, and every external engine/version classified in `governance/engine-support.toml`. CI provisioning pins those external versions without adding them as Rush runtime dependencies; mypy remains an explicit release-gate engine and cannot be satisfied by an unavailable/all-skipped result.

## 9. Ordered workstreams and atomic task cards

### P59.0 — Admission

#### P59.0.1 — EVIDENCE: map current claims, parse/policy seams, and engine jobs

- **Task ID and binary outcome:** P59.0.1; every current claim/parser/policy/engine family/job maps to one task.
- **Start goal:** Freeze exact release-evidence scope.
- **Prerequisites:** §4.
- **Documentation impact:** None.
- **Dependency impact:** None.
- **Allowed writes:** R-013/R-014 admission fields in `governance/remediation-contracts.toml`.
- **Allowed reads:** `src/rush/tools/attest.py`, `src/rush/release/provenance.py`, `src/rush/release/__init__.py`, `src/rush/engines/__init__.py`, `src/rush/cli.py`, `src/rush/mcp.py`, `src/rush/contracts/operations.py`, `src/rush/contracts/results.py`, `src/rush/safety/redactor.py`, `governance/engine-support.toml`, `governance/public-operations.toml`, `governance/remediation-contracts.toml`, `.github/workflows/ci.yml`, `.github/workflows/release.yml`, `tests/test_phase50_slsa_attestation.py`, `tests/test_supply_chain_tools.py`, `tests/test_static_tools.py`, `tests/test_capabilities.py`, `tests/conftest.py`, `docs/ENGINES.md`, `docs/ENGINE_COMPATIBILITY.md`, `docs/DISTRIBUTION.md`, `docs/RELEASE.md`, `docs/SECURITY.md`.
- **Prohibited:** source/tests/docs/workflows/dependencies/live signing.
- **Actions:** 1. Inspect attest/provenance consumers, claim hits, parse flow, policy, engine taxonomy/jobs. 2. Record exact symbols/claims/families/current defects/task owners. 3. Reconcile coverage and engine manifests; reparse TOML.
- **Evidence:** claim/parser/policy/engine table.
- **Stop:** unowned shipping claim or engine family.
- **Verified outcome:** P59.1.1-P59.5.1 may start.

### P59.1 — Unsigned draft

#### P59.1.1 — RED: define honest default output and subjects

- **Task ID and binary outcome:** P59.1.1; three tests fail on current naming/subject/claims.
- **Start goal:** Pin explicit unsigned draft and actual artifact identity.
- **Prerequisites:** P59.0.1 and Phase 52 artifact evidence.
- **Documentation impact:** None.
- **Dependency impact:** None.
- **Allowed writes:** create `tests/test_phase59_provenance_draft.py`, create `tests/fixtures/remediation/provenance/unsigned-draft.json`.
- **Allowed reads:** attest/provenance source, artifact identities, existing Phase 50 tests.
- **Prohibited:** production/docs/live keys/XFAIL.
- **Actions:** 1. Arrange wheel/sdist identities and missing-evidence case. 2. Add exactly three §7 draft tests and forbid uncollected signature/builder/reproducibility/completeness/level claims. 3. Run focused with Phase 50 tests and record failures.
- **Evidence:** red matrix and expected fixture.
- **Stop:** artifact identity is missing; expected outcome is skipped/error.
- **Verified outcome:** P59.1.2 may edit draft builders/routes.

#### P59.1.2 — GREEN: build sanitized evidence-only unsigned drafts

- **Task ID and binary outcome:** P59.1.2; default output/subject tests pass for wheel/sdist/missing evidence.
- **Start goal:** Satisfy P59.1.1 only.
- **Prerequisites:** recorded P59.1.1 RED.
- **Documentation impact:** None.
- **Dependency impact:** None.
- **Allowed writes:** `src/rush/tools/attest.py`, `src/rush/release/provenance.py`, `src/rush/release/__init__.py`, `src/rush/cli.py`, `src/rush/mcp.py`, `src/rush/contracts/operations.py`, `results.py`, `src/rush/safety/redactor.py`, `governance/public-operations.toml`, `tests/test_phase59_provenance_draft.py`, `tests/test_phase50_slsa_attestation.py`, unsigned fixture.
- **Allowed reads:** P59.1.1 evidence and Phase 52 identities.
- **Prohibited:** signed verification/parser policy/docs/dependencies.
- **Actions:** 1. Reinspect public names/builders. 2. Build only sanitized unsigned draft from actual artifact/package evidence; update route descriptions/compatibility; missing evidence skips/errors. 3. Run focused, Phase 50, operation reconciliation tests.
- **Evidence:** green artifact matrix and claim scan.
- **Stop:** any unsupported assurance remains in default output.
- **Verified outcome:** P59.2.1 may pin structure.

### P59.2 — Statement structure

#### P59.2.1 — RED: define exact Statement/predicate fields

- **Task ID and binary outcome:** P59.2.1; structure tests fail on absent/inexact schema.
- **Start goal:** Pin types, buildType, parameters, source, subject, extensions.
- **Prerequisites:** P59.1.2.
- **Documentation impact:** None.
- **Dependency impact:** None.
- **Allowed writes:** create `tests/test_phase59_provenance_structure.py`.
- **Allowed reads:** roadmap schema decisions, draft builder, current schemas/tests.
- **Prohibited:** production/parser/signature/docs/XFAIL.
- **Actions:** 1. Arrange exact valid/field-mismatch drafts. 2. Add exactly two §7 structure tests. 3. Run focused file and record failures.
- **Evidence:** expected structure and red output.
- **Stop:** a field is not fixed by roadmap.
- **Verified outcome:** P59.2.2 may create policy constants/schema builder.

#### P59.2.2 — GREEN: pin one current provenance structure

- **Task ID and binary outcome:** P59.2.2; draft structure passes exact schema tests.
- **Start goal:** Satisfy P59.2.1 only.
- **Prerequisites:** recorded P59.2.1 RED.
- **Documentation impact:** None.
- **Dependency impact:** None.
- **Allowed writes:** create `src/rush/release/provenance_policy.py`; modify `src/rush/release/provenance.py`, `tests/test_phase59_provenance_structure.py`, unsigned fixture.
- **Allowed reads:** P59.2.1 evidence and result/sanitizer contracts.
- **Prohibited:** parser/signature/engine/docs.
- **Actions:** 1. Authorize exact constants/schema construction. 2. Implement Statement v1/predicate v1 structure and validation. 3. Run structure/draft/result-schema tests.
- **Evidence:** green exact-field matrix.
- **Stop:** permissive unknown policy-relevant extension.
- **Verified outcome:** P59.3.1/P59.4.1 may consume structure.

### P59.3 — Strict parsing

#### P59.3.1 — RED: expose duplicate and normalized-key ambiguity

- **Task ID and binary outcome:** P59.3.1; parser tests fail because ambiguous inputs can reach policy.
- **Start goal:** Pin raw/decoded/nested/escaped/Unicode/extension rejection before policy.
- **Prerequisites:** P59.2.2.
- **Documentation impact:** None.
- **Dependency impact:** None.
- **Allowed writes:** create `tests/test_phase59_provenance_parser.py`, create `tests/fixtures/remediation/provenance/signed-invalid-envelopes.json`.
- **Allowed reads:** current parse flow and structure policy.
- **Prohibited:** production/signature/docs/XFAIL.
- **Actions:** 1. Arrange duplicates at envelope/Statement/predicate/builder/parameters/extensions and instrument policy call count. 2. Add exactly two §7 parser tests plus malformed cases; policy count must remain zero. 3. Run focused file and record failures.
- **Evidence:** ambiguity matrix and red output.
- **Stop:** fixture parser discards pairs before system under test.
- **Verified outcome:** P59.3.2 may implement strict parser.

#### P59.3.2 — GREEN: reject ambiguity before ordinary mappings and policy

- **Task ID and binary outcome:** P59.3.2; every ambiguous/malformed input rejects with zero policy calls.
- **Start goal:** Satisfy P59.3.1 only.
- **Prerequisites:** recorded P59.3.1 RED.
- **Documentation impact:** None.
- **Dependency impact:** None.
- **Allowed writes:** `src/rush/release/provenance_policy.py`, `src/rush/release/provenance.py`, `tests/test_phase59_provenance_parser.py`, invalid fixture.
- **Allowed reads:** P59.3.1 evidence.
- **Prohibited:** signature acceptance/engine/docs/dependencies.
- **Actions:** 1. Reinspect parse entry points. 2. Preserve object pairs, apply explicit key normalization/duplicate rejection at every level, construct mappings only after pass. 3. Run parser/structure/draft tests.
- **Evidence:** green ambiguity matrix and zero policy calls.
- **Stop:** permissive parse occurs first.
- **Verified outcome:** P59.4.1 may test signed policy.

### P59.4 — Optional signed policy

#### P59.4.1 — RED: define exact synthetic signed acceptance

- **Task ID and binary outcome:** P59.4.1; valid/mismatch tests fail on absent/incomplete policy.
- **Start goal:** Pin signer/root/builder/subject/type/buildType/parameters/source.
- **Prerequisites:** P59.3.2.
- **Documentation impact:** None.
- **Dependency impact:** None.
- **Allowed writes:** create `tests/test_phase59_provenance_policy.py`, create `tests/fixtures/remediation/provenance/signed-valid-envelope.json`, modify invalid fixture.
- **Allowed reads:** existing cryptography usage and strict parser.
- **Prohibited:** production/live key/signing/docs/XFAIL.
- **Actions:** 1. Arrange committed synthetic keys/envelopes containing no secret authority and one mismatch per policy field. 2. Add exactly two §7 signed tests plus empty allowlist/malformed signature cases. 3. Run focused file and record failures.
- **Evidence:** mismatch matrix and red output.
- **Stop:** fixture uses live/private operational key.
- **Verified outcome:** P59.4.2 may implement optional verifier.

#### P59.4.2 — GREEN: enforce exact signed verification policy

- **Task ID and binary outcome:** P59.4.2; only exact valid synthetic envelope passes.
- **Start goal:** Satisfy P59.4.1 only.
- **Prerequisites:** recorded P59.4.1 RED.
- **Documentation impact:** None.
- **Dependency impact:** None.
- **Allowed writes:** `src/rush/release/provenance_policy.py`, `src/rush/release/provenance.py`, `tests/test_phase59_provenance_policy.py`, valid/invalid fixtures, `tests/test_supply_chain_tools.py`.
- **Allowed reads:** P59.4.1 evidence and existing cryptography.
- **Prohibited:** live key generation/signing/release/docs/dependencies.
- **Actions:** 1. Reinspect each mismatch. 2. Verify root/envelope/signature then exact allowlists/equalities after strict parse; empty allowlist denies. 3. Run policy/parser/structure/supply-chain tests.
- **Evidence:** green mismatch matrix.
- **Stop:** any policy field is inferred/defaulted.
- **Verified outcome:** R-013 implementation contract closes.

### P59.5 — Engine conformance

#### P59.5.1 — RED: define fixed-PATH and provisioned evidence

- **Task ID and binary outcome:** P59.5.1; five engine tests fail on incomplete jobs, ambient/all-skipped behavior, or absent mypy release evidence.
- **Start goal:** Pin every Phase 51 family and support class.
- **Prerequisites:** P59.0.1 and Phase 51 engine policy.
- **Documentation impact:** None.
- **Dependency impact:** None.
- **Allowed writes:** create `tests/test_phase59_engine_conformance.py`, modify `tests/conftest.py`.
- **Allowed reads:** `governance/engine-support.toml`, engines/tools, static tests, workflows.
- **Prohibited:** production/CI/docs/dependencies/ambient tools/XFAIL.
- **Actions:** 1. Arrange fixed PATH and success/failure/malformed/missing result fixtures per family. 2. Add exactly five §7 engine tests, including mandatory provisioned non-skipped mypy release evidence and resolved executable/version assertions. 3. Run focused/static tests and record failures.
- **Evidence:** family/job red matrix.
- **Stop:** taxonomy entry is incomplete.
- **Verified outcome:** P59.5.2 may implement policy/CI.

#### P59.5.2 — GREEN: enforce deterministic and provisioned engine matrices

- **Task ID and binary outcome:** P59.5.2; deterministic tests ignore ambient tools and every supported family has non-skipped provisioned evidence.
- **Start goal:** Satisfy P59.5.1 only.
- **Prerequisites:** recorded P59.5.1 RED.
- **Documentation impact:** None.
- **Dependency impact:** None.
- **Allowed writes:** create `src/rush/engines/support_policy.py`; modify `src/rush/engines/__init__.py`, `governance/engine-support.toml`, `.github/workflows/ci.yml`, `.github/workflows/release.yml`, `tests/test_phase59_engine_conformance.py`, `tests/test_static_tools.py`, `tests/conftest.py`.
- **Allowed reads:** P59.5.1 evidence and existing adapter/version resolution.
- **Prohibited:** bundled engines/dependencies/docs/fabricated job results.
- **Actions:** 1. Reinspect every family/job. 2. Implement taxonomy loader/enforcement; fixed-PATH deterministic job; separate pinned provisioned success/failure/malformed jobs; archive executable/version evidence; fail all-skipped supported. 3. Run focused/static locally and inspect CI matrix diff.
- **Evidence:** green deterministic matrix and provisioned job definitions/results.
- **Stop:** supported family cannot be provisioned at pinned version.
- **Verified outcome:** R-014 implementation contract closes.

### P59.6 — Documentation and release handoff

#### P59.6.1 — VERIFY/DOCS/HANDOFF: close release readiness truthfully

- **Task ID and binary outcome:** P59.6.1; shipping docs contain no unsupported current assurance and release handoff records all required gates.
- **Start goal:** Publish only proven draft/signed/engine behavior.
- **Prerequisites:** P59.1.2-P59.5.2 and accepted R-001-R-012/R-016 evidence.
- **Documentation impact:** all twelve §8 docs.
- **Dependency impact:** None.
- **Allowed writes:** `README.md`, `docs/ENGINES.md`, `docs/ENGINE_COMPATIBILITY.md`, `docs/DISTRIBUTION.md`, `docs/RELEASE.md`, `docs/SECURITY.md`, `docs/TOOL_CATALOG.md`, `docs/reference/engine-directory.md`, `docs/reference/result-reference.md`, `docs/developer/ci-and-packaging.md`, `docs/maintainers/release-playbook.md`, `docs/maintainers/versioning-and-compatibility.md`, and R-013/R-014/release evidence fields in `governance/remediation-contracts.toml`.
- **Allowed reads:** passing tests, installed artifacts, provisioned CI, Phase 51 coverage, prior gate records.
- **Prohibited:** source/tests/dependencies/live signing/release, rewriting historical plans.
- **Actions:** 1. Map every current assurance/engine claim to evidence and identify historical exemptions. 2. Update named docs; record unsigned/signed limits, subject/parser/policy, taxonomy, R-001-R-014/R-016 results, artifact identities, explicit R-015 exclusion. 3. Run §10 and compare changed paths to tasks.
- **Evidence:** coverage-scoped claim scan, docs diff, full release handoff.
- **Stop:** any required gate lacks passing evidence or claim exceeds it.
- **Verified outcome:** release readiness is evidence-backed; Phase 60 may begin separately.

## 10. Final verification and delivery gate

```text
$env:VIRTUAL_ENV=$null
$env:PYTHONPATH=$null
.venv/Scripts/python.exe -m pytest tests/test_phase59_provenance_draft.py tests/test_phase59_provenance_structure.py tests/test_phase59_provenance_parser.py tests/test_phase59_provenance_policy.py tests/test_phase59_engine_conformance.py -q
.venv/Scripts/python.exe -m pytest tests/ -q
.venv/Scripts/ruff.exe check src tests scripts
.venv/Scripts/ruff.exe format --check src tests scripts
.venv/Scripts/python.exe scripts/probe_installed_artifacts.py
git diff --check
git diff --name-only
git status --short --branch
```

The provisioned Phase 59 engine job also runs the exact mypy executable/version pinned in `governance/engine-support.toml` as `mypy --version` followed by `mypy src/rush`; either command unavailable, skipped, or nonzero blocks the release handoff.

## 11. Exit checklist and successor evidence

- [ ] Ordinary RED precedes GREEN; no skip/XFAIL/XPASS.
- [ ] Default output is unsigned draft with actual artifact/package subjects only.
- [ ] Exact structure is pinned; ambiguity rejects before policy.
- [ ] Optional signed mode accepts only exact synthetic policy match.
- [ ] Fixed-PATH tests ignore ambient tools and supported jobs cannot pass all-skipped.
- [ ] Shipping claims are coverage-scoped and evidence-backed.
- [ ] R-001-R-014/R-016 release handoff is complete; R-015 explicitly remains Phase 60.
- [ ] No dependency/live key/signing/release action.
- [ ] Every changed path belongs to one task.
