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
   - Existing `AttestationTool` creates an in-toto Statement v1 with `predicateType="https://slsa.dev/provenance/v1"`, but summary and descriptions can imply SLSA Level 3 or signed assurance. In missing-package scenarios, it may fall back to path names or commits instead of physical package digests.
   - Seam identified: Must define `ProvenanceDraft` AST model. Default output must be explicitly labeled and documented as an unsigned provenance draft (`provenance_draft`) with `assurance="unsigned_draft"`. Subjects MUST be physical wheel/sdist artifact SHA-256 digests; missing package artifacts fail closed with `skipped` or `MissingArtifactError`.

2. **Statement and Predicate Pinned Structure Seams (`src/rush/release/provenance_policy.py`):**
   - No explicit AST dataclasses exist for `StatementV1`, `SLSAPredicateV1`, `BuildDefinitionV1`, `ExternalParametersV1`, `RunDetailsV1`.
   - Seam identified: Must implement frozen, immutable dataclasses pinned to `https://in-toto.io/Statement/v1` and `https://slsa.dev/provenance/v1`, with strict validation rejecting unknown or malformed fields.

3. **Strict JSON Parsing & Duplicate/Ambiguous Key Seams (`src/rush/release/provenance_policy.py`):**
   - Existing code uses standard `json.loads()`, which silently discards duplicate keys, allowing parser differential attacks.
   - Seam identified: Implement `StrictProvenanceParser` using `json.JSONDecoder(object_pairs_hook=...)` with Unicode NFKC normalization. Raises `DuplicateKeyError` and `AmbiguousKeyError` at envelope, Statement, predicate, and extension levels before dictionary creation.

4. **Signed Provenance Policy & Cryptographic Verification Seams (`src/rush/release/provenance_policy.py`):**
   - No cryptographic verification exists for in-toto DSSE envelopes.
   - Seam identified: Implement `SignedProvenancePolicy` and `ProvenancePolicyVerifier` verifying signatures against allowlisted keys/roots using `cryptography` primitives, and asserting strict equality of signer, builder ID, artifact digest, package name, statement type, predicate type, and source URI regex.

5. **Engine Taxonomy, Fixed-PATH Isolation & Release Gate Seams (`src/rush/engines/`, `governance/engine-support.toml`):**
   - Engines discover binaries from ambient `PATH`, allowing uncontrolled local tools to satisfy tests. Engine tests in `test_static_tools.py` skip when binaries are absent, giving the illusion of conformance.
   - Seam identified: Implement `EngineSupportPolicy` and `EngineTaxonomyRecord` loading from `governance/engine-support.toml`. Implement `FixedPathEnvironment` isolating `PATH`. Enforce `can_pass_all_skipped = false` for supported-optional families (`AllSkippedViolationError`). Enforce mandatory non-skipped `mypy` release gate (`ReleaseGateFailureError`).

## 3. Execution Log

- `2026-09-05`: Admission gate passed. Baseline recorded (1,163 passed, 0 warnings). Workstreams P59.1 - P59.6 scheduled.
