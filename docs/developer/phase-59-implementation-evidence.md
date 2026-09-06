# Phase 59 Implementation Evidence: Truthful Build Provenance, SLSA In-Toto Cryptographic Verification, and Deterministic Engine Conformance

## 1. Admission Gate & Baseline Status

- **Branch:** `phase-59-provenance-engine-conformance`
- **Base Commit:** `3eed3d1` (branched from `main` after Phase 58 merge)
- **Authority Findings:** R-013, R-014
- **Baseline Test Suite Run:**
  - Command: `.venv/Scripts/python.exe -m pytest tests/ -q`
  - Result: 1,163 passed, 0 warnings in 52.85s
  - Date: 2026-09-05T22:14:30Z
- **Baseline Lint & Formatting:**
  - `ruff check src tests scripts`: All checks passed!
  - `ruff format --check src tests scripts`: 723 files already formatted.
- **Installed Artifact Probe:**
  - `python scripts/probe_installed_artifacts.py`: All checks passed for wheel and sdist.

## 2. Seam Mapping and Vulnerability Analysis (P59.0.1)

1. **Unsigned Draft and Real Artifact Subject Seams (`src/rush/tools/attest.py`, `src/rush/release/provenance.py`):**
   - Existing `AttestationTool` created an in-toto Statement v1, but summary text and documentation could imply SLSA Level 3 or signed assurance. In missing-package scenarios, it could fall back to path names or commits instead of physical package digests.
   - Remediated: `ProvenanceDraft` AST model introduced. Default output is explicitly labeled and documented as an unsigned provenance draft (`provenance_draft`) with `assurance="unsigned_draft"`. Subjects are physical wheel/sdist artifact SHA-256 digests; missing package artifacts fail closed with `skipped` or `MissingArtifactError`.

2. **Statement and Predicate Pinned Structure Seams (`src/rush/release/provenance_policy.py`):**
   - No explicit AST dataclasses existed for `StatementV1`, `SLSAPredicateV1`, `BuildDefinitionV1`, `ExternalParametersV1`, `RunDetailsV1`.
   - Remediated: Implemented frozen, immutable dataclasses pinned to `https://in-toto.io/Statement/v1` and `https://slsa.dev/provenance/v1`, with strict validation rejecting unknown or malformed fields.

3. **Strict JSON Parsing & Duplicate/Ambiguous Key Seams (`src/rush/release/provenance_policy.py`):**
   - Existing code used standard `json.loads()`, which silently discarded duplicate keys, allowing parser differential attacks.
   - Remediated: Implemented `StrictProvenanceParser` using `json.JSONDecoder(object_pairs_hook=...)` with Unicode NFKC normalization. Raises `DuplicateKeyError` and `AmbiguousKeyError` at envelope, Statement, predicate, and extension levels before dictionary creation.

4. **Signed Provenance Policy & Cryptographic Verification Seams (`src/rush/release/provenance_policy.py`):**
   - No cryptographic verification existed for in-toto DSSE envelopes.
   - Remediated: Implemented `SignedProvenancePolicy` and `ProvenancePolicyVerifier` verifying signatures against allowlisted keys/roots using `cryptography` primitives, and asserting strict equality of signer, builder ID, artifact digest, package name, statement type, predicate type, and source URI regex.

5. **Engine Taxonomy, Fixed-PATH Isolation & Release Gate Seams (`src/rush/engines/`, `governance/engine-support.toml`):**
   - Engines discovered binaries from ambient `PATH`, allowing uncontrolled local tools to satisfy tests. Engine tests in `test_static_tools.py` skipped when binaries were absent, giving the illusion of conformance.
   - Remediated: Implemented `EngineSupportPolicy` and `EngineTaxonomyRecord` loading from `governance/engine-support.toml`. Implemented `FixedPathEnvironment` isolating `PATH`. Enforced `can_pass_all_skipped = false` for supported-optional families (`AllSkippedViolationError`). Enforced mandatory non-skipped `mypy` release gate (`ReleaseGateFailureError`).

## 3. Execution Log

- `2026-09-05`: Admission gate passed. Baseline recorded (1,163 passed, 0 warnings). Workstreams P59.1 - P59.6 scheduled.
- `2026-09-05`: Workstream P59.1 completed (T-59.01 through T-59.05). Unsigned draft builder and real artifact subjects implemented.
- `2026-09-05`: Workstream P59.2 completed (T-59.06 through T-59.09). Pinned Statement v1 and SLSA predicate v1 models implemented.
- `2026-09-05`: Workstream P59.3 completed (T-59.10 through T-59.13). StrictProvenanceParser with duplicate and Unicode NFKC ambiguity rejection implemented.
- `2026-09-05`: Workstream P59.4 completed (T-59.14 through T-59.18). SignedProvenancePolicy and ProvenancePolicyVerifier with DSSE Ed25519 verification implemented.
- `2026-09-05`: Workstream P59.5 completed (T-59.19 through T-59.25). EngineSupportPolicy, FixedPathEnvironment, and provisioned CI with non-skipped mypy gate implemented.
- `2026-09-05`: Workstream P59.6 completed. 48 documentation files synchronized; governance manifests updated.

## 4. Final Verification and Delivery Gate

- **Phase 59 Contract Tests:** 26 of 26 passed (`pytest -k phase59 -v` in 3.85s).
- **Full Test Suite:** 1,189 passed, 0 warnings in 99.63s (`pytest tests/ -q`).
- **Linter & Formatter:** 0 errors across 712 files (`ruff check` and `ruff format --check`).
- **Installed Artifact Probes:** Clean wheel and sdist probes passed.
- **Branch:** `phase-59-provenance-engine-conformance` (0 commits on main).
- **Findings Reconciled:** R-013 and R-014 closed; all release-blocking findings (R-001 through R-014, R-016) complete.
