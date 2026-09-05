# Phase 59 Implementation Plan: Truthful Build Provenance, SLSA In-Toto Cryptographic Verification, and Deterministic Engine Conformance

## 1. Purpose and Status

- **Operation:** Comprehensive implementation plan for Phase 59 remediation.
- **Planning Status:** Implementation-ready; deeply reviewed against repo codebase and active development.
- **Implementation Status:** Authorized for strict TDD execution.
- **Authority:** Governing Roadmap findings R-013, R-014, and R-016/R-011 integration (`governance/remediation-contracts.toml`).
- **Predecessors:** Accepted Phase 51 operation manifest and engine taxonomy, Phase 52 package artifact identity, Phase 53 sanitizer (`rush.safety.redactor`), Phase 54 result schema kernel (`rush.contracts.results.ToolResultV1`), Phase 55 physical containment and verifier primitives (`rush.io.PhysicalRoot`, `rush.io.AtomicFile`, `rush.io.VerifierRecord`), Phase 56 user-owned plugin trust, Phase 57 invocation context and cryptographic cache, and Phase 58 capability locks, CAS persistence, and fail-closed patch verification.
- **Release Relationship:** Phase 59 produces final release-readiness evidence closing all release-blocking findings (R-001 through R-014, and R-016). R-015 (maintainability hotspots) remains explicitly deferred to Phase 60 (non-release-blocker).
- **Security Boundary:**
  1. Default output is strictly an unsigned draft (`provenance_draft` / `assurance: "unsigned_draft"`). It strictly forbids claiming SLSA levels (e.g. SLSA Level 3), signatures, verified builder, completeness, or reproducibility without cryptographic verification.
  2. Provenance subjects must be actual built artifact SHA-256 digests (wheel/sdist) and package identities; git commits or workspace tree hashes are strictly forbidden as primary subjects.
  3. Strict JSON parsing: preserves object pairs and rejects duplicate keys, escaped/Unicode equivalent key collisions, and ambiguous dictionary structures at every level (envelope, statement, predicate, buildDefinition, externalParameters, runDetails) before ordinary mapping conversion or policy evaluation.
  4. Optional cryptographic verification policy: `SignedProvenancePolicy` requires exact equality of signer identity, trusted root, builder ID, artifact digest, package name, statement type, predicate type, buildType, externalParameters, and source repository URI. Uses synthetic cryptographic test fixtures (committed public keys/certificates, never live operational secrets).
  5. Deterministic engine environment isolation: engine test suites execute in an isolated environment (`FixedPathEnvironment`) to prevent ambient developer binaries on PATH from masking dependency gaps or polluting conformance evidence.
  6. Non-permissive engine conformance: supported-optional and mandatory engine families cannot pass when all tests are skipped (`can_pass_all_skipped = false`).
  7. Release-gate engine enforcement: `mypy` is an explicit release gate; running `mypy --version` and `mypy src/rush` must be provisioned and non-skipped; unavailable, skipped, or nonzero exit code blocks release handoff.
- **Protected Boundaries:** Roadmap requirements, dependency lockfile, engine taxonomy, and release versioning.
- **Zero-Downscope Invariant:** This plan is the immutable contract. Stubs returning `"unknown"`, `"deferred"`, or permissive test assertions (`assert status in (...)`) are strictly prohibited. Every covered failure mode must fail closed.
- **Lifecycle Boundary:** No commit, push, merge, tag, publish, release, hooks, history rewrite, live secrets, or live network calls without explicit user instructions.

---

## 2. Authority, Predecessor Artifacts, and Concrete Evidence

Authority order: User instructions → `AGENTS.md` → Roadmap (`governance/remediation-contracts.toml`) → Phases 51-58 contracts → Current attest/provenance/engine source and test suites.

### 2.1 Concrete Codebase Audit & Semantic Drift Identification

An exhaustive audit of the existing codebase against findings R-013 and R-014 identified five critical vulnerabilities and architectural drifts:

1. **Drift 1: Unsigned Draft Claiming Unsupported SLSA Assurance (R-013)**:
   - *Existing Code:* In `src/rush/tools/attest.py`, `AttestationTool` generates an in-toto Statement v1 with `predicateType="https://slsa.dev/provenance/v1"`. While it includes `"assurance": "unsigned_draft"` in metadata, documentation, summary text, and legacy callers refer to this output as "SLSA Provenance v1 attestation" or imply SLSA Level 3 compliance. Furthermore, if `artifact_path` is not provided and no built packages exist in `dist/`, it attempts to fall back to path name or skips without structured typed draft models.
   - *Vulnerability:* Misleading consumers into believing an unsigned, unverified local draft represents a signed cryptographic SLSA Level 3 attestation.
   - *Remediation (R-013):* Introduce `ProvenanceDraft` AST model. Default output must be explicitly labeled and documented as an unsigned provenance draft (`provenance_draft`). Default output must never claim SLSA Level 1/2/3, verified builder, cryptographic signature, completeness, or reproducibility.

2. **Drift 2: Subject Identity Using Commits Instead of Built Artifacts (R-013)**:
   - *Existing Code:* In `src/rush/tools/attest.py`, lines 133-138 resolve git commit hash from `git rev-parse HEAD`. In some legacy invocations or fallback cases, commits were used directly as the subject identity rather than the binary package digest.
   - *Vulnerability:* Attesting a git commit hash does not guarantee that the distributed wheel or sdist binary matches that source commit, violating SLSA artifact binding requirements.
   - *Remediation (R-013):* Attestation subjects MUST be the actual physical package artifacts (e.g. `rush-0.3.0-py3-none-any.whl`, `rush-0.3.0.tar.gz`) verified via SHA-256 digest from Phase 52 distribution evidence. If no built distribution artifact is provided or discovered, the tool fails closed with `skipped` status or `MissingArtifactError`; it never fabricates an attestation over raw source trees or commit hashes.

3. **Drift 3: Ambiguous JSON Parser & Permissive Decoding (R-013)**:
   - *Existing Code:* `json.loads()` is used across provenance and report loaders. Standard `json.loads` in Python silently overwrites earlier duplicate keys (e.g. `{"builder": {"id": "evil"}, "builder": {"id": "good"}}` parses cleanly to `"good"`). Escaped characters or Unicode representations (`\u0062uilder`) can also bypass basic string matching before downstream evaluation.
   - *Vulnerability:* Parser differential attacks where an attacker crafts an envelope with duplicate keys that verifiers parse one way and downstream policy engines parse another, bypassing signer or builder validation.
   - *Remediation (R-013):* Implement `StrictProvenanceParser` in `src/rush/release/provenance_policy.py` using `json.JSONDecoder(object_pairs_hook=...)`. It preserves object key-value pairs during parsing, normalizes Unicode representations (NFKC), and raises `DuplicateKeyError` or `AmbiguousKeyError` immediately if any duplicate or collision key is detected at any level (raw envelope, Statement, predicate, buildDefinition, externalParameters, runDetails) BEFORE converting to mapping or evaluating policy. Zero ambiguous inputs ever reach policy verification.

4. **Drift 4: Ambient PATH Pollution & All-Skipped Conformance Illusion (R-014)**:
   - *Existing Code:* In `src/rush/engines/` and `src/rush/tools/common.py:resolve_binary()`, engine lookup inspects `shutil.which(binary)` against the host environment's ambient `PATH`. In `tests/test_static_tools.py`, tests mark `pytest.skip` if a binary is absent.
   - *Vulnerability:* If run on a developer machine with local tools installed, tests pass using unpinned, uncontrolled host binaries. If run in an empty CI environment, all tests skip, and the test suite passes with 0 failures, giving the illusion that engines conform when zero actual checks ran.
   - *Remediation (R-014):* Implement `src/rush/engines/support_policy.py` and `FixedPathEnvironment`. Engine tests must run in an isolated environment with a strictly controlled, fixed PATH. In accordance with `governance/engine-support.toml`, supported-optional engine families cannot pass when all tests are skipped (`can_pass_all_skipped = false`). Provisioned CI jobs in `.github/workflows/ci.yml` must explicitly provision external binaries at pinned versions and test clean, finding, and malformed fixtures.

5. **Drift 5: Release-Gate Engine (mypy) Verification Gap (R-014)**:
   - *Existing Code:* `mypy` is classified as `supported-optional` in `governance/engine-support.toml`, and in `tests/test_static_tools.py` it can be skipped if absent.
   - *Vulnerability:* Rush can claim release readiness without verifying type safety across the codebase.
   - *Remediation (R-014):* In `governance/engine-support.toml` and `support_policy.py`, `mypy` is designated as an explicit release-gate engine. For pre-release and release verification, `mypy --version` and `mypy src/rush` must be executed and non-skipped. Any failure, absence, or skip of `mypy` immediately fails closed with `ReleaseGateFailureError` and aborts release readiness.

---

## 3. Goals, Non-Goals, Operational Exclusions, and Security Boundaries

### 3.1 Primary Goals

1. Implement `ProvenanceDraft` builder in `src/rush/tools/attest.py` and `src/rush/release/provenance.py` producing truthful unsigned drafts with real artifact digests (R-013).
2. Implement pinned in-toto Statement v1 and SLSA Provenance v1 predicate schemas with strict field definitions (R-013).
3. Implement `StrictProvenanceParser` rejecting duplicate and ambiguous keys at all raw, decoded, and nested levels (R-013).
4. Implement `SignedProvenancePolicy` and `ProvenancePolicyVerifier` in `src/rush/release/provenance_policy.py` verifying in-toto envelopes against allowlisted signers, builders, digests, and sources using synthetic test fixtures (R-013).
5. Implement `EngineTaxonomyRecord` and `EngineSupportPolicy` in `src/rush/engines/support_policy.py` enforcing `governance/engine-support.toml` rules (R-014).
6. Implement `FixedPathEnvironment` test harness isolating engine discovery from ambient host tools (R-014).
7. Provision separate success, failure, and malformed CI jobs for supported engine families, and enforce non-skipped `mypy` release gate (R-014).
8. Synchronize all 48 identified documentation files across `/docs` and all subfolders.

### 3.2 Non-Goals and Operational Exclusions

1. **No Live Signing Keys or Private Operational Secrets:** Verification tests use synthetic, committed public keys and certificates generated for testing; no live corporate or production signing authority is used.
2. **No Dependency Additions:** 100% pure standard library plus existing project dependencies (`cryptography==50.0.0`, `ruamel.yaml==0.19.1`).
3. **No Live Package Publishing or Registry Upload:** Phase 59 produces verified artifacts and attestation drafts locally; network publication is strictly prohibited.
4. **R-015 Explicitly Excluded:** Maintainability hotspots and modularity refactoring belong to Phase 60 (non-release-blocker).

---

## 4. Admission Gate and Predecessor Verification

The following criteria must be verified prior to initiating Phase 59 development:
1. `governance/remediation-phase-58.toml` is present with status `completed` (all 26 Phase 58 contract tests passed).
2. Clean test baseline of 1,163 passed tests, 0 warnings.
3. Installed package artifacts (`scripts/probe_installed_artifacts.py`) pass on wheel and sdist.
4. Phase 51 public operations manifest (`governance/public-operations.toml`) is present with 146 operations mapped.
5. Phase 51 engine taxonomy (`governance/engine-support.toml`) is present with 19 engine families classified.
6. Execution of P59.0.1 maps every attest, provenance, engine taxonomy, and CI seam before RED tasks begin.

---

## 5. Requirement-Ownership Ledger (R-013, R-014)

| Requirement ID | Finding Summary | Workstreams | Specific Contract Outcomes |
|---|---|---|---|
| **R-013** | Build provenance claims SLSA Level 3 without cryptographic attestation | P59.1, P59.2, P59.3, P59.4 | Truthful unsigned draft output by default; real artifact SHA-256 digest subjects; pinned Statement v1 / SLSA predicate v1; strict duplicate/ambiguity JSON parser; optional signed verification policy using synthetic crypto fixtures. |
| **R-014** | Engine adapters lack deterministic environment discovery and capability verification | P59.5 | Single-source engine taxonomy loader; fixed-PATH deterministic test suite; prohibition of all-skipped for supported families; provisioned CI jobs for clean/finding/malformed; non-skipped `mypy` release gate. |
| **Handoff** | Release readiness verification and documentation synchronization | P59.6 | Complete `/docs` synchronization (48 files across 4 groups); closure of R-001 through R-014 and R-016 in `governance/remediation-contracts.toml`; generation of `governance/remediation-phase-59.toml`. |

---

## 6. Shared Architecture, State Invariants, and Data Structures

### 6.1 Provenance Models & Statement Schemas (`src/rush/release/provenance_policy.py`)

```python
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

IN_TOTO_STATEMENT_TYPE = "https://in-toto.io/Statement/v1"
SLSA_PREDICATE_TYPE_V1 = "https://slsa.dev/provenance/v1"
RUSH_BUILD_TYPE_DRAFT_V1 = "https://rush-cli.org/build/draft/v1"
RUSH_BUILDER_ID_V1 = "https://rush-cli.org/builder/v1"

@dataclass(frozen=True)
class SubjectV1:
    name: str
    digest: dict[str, str]  # Must include "sha256": hex_digest

@dataclass(frozen=True)
class ExternalParametersV1:
    source_uri: str
    commit: str
    entry_point: str

@dataclass(frozen=True)
class InternalParametersV1:
    builder_id: str

@dataclass(frozen=True)
class BuildDefinitionV1:
    build_type: str
    external_parameters: ExternalParametersV1
    internal_parameters: InternalParametersV1

@dataclass(frozen=True)
class BuilderDetailsV1:
    id: str

@dataclass(frozen=True)
class RunMetadataV1:
    invocation_id: str
    started_on: str
    finished_on: str
    assurance: Literal["unsigned_draft", "cryptographically_verified"]

@dataclass(frozen=True)
class RunDetailsV1:
    builder: BuilderDetailsV1
    metadata: RunMetadataV1

@dataclass(frozen=True)
class SLSAPredicateV1:
    build_definition: BuildDefinitionV1
    run_details: RunDetailsV1

@dataclass(frozen=True)
class StatementV1:
    type: str  # Must equal IN_TOTO_STATEMENT_TYPE
    subject: tuple[SubjectV1, ...]
    predicate_type: str  # Must equal SLSA_PREDICATE_TYPE_V1
    predicate: SLSAPredicateV1

@dataclass(frozen=True)
class ProvenanceDraft:
    statement: StatementV1
    assurance: Literal["unsigned_draft"] = "unsigned_draft"
    is_signed: bool = False

    def to_dict(self) -> dict[str, Any]:
        ...
```

### 6.2 Strict JSON Parser & Duplicate Rejection (`src/rush/release/provenance_policy.py`)

```python
class ProvenanceError(Exception):
    """Base exception for provenance and attestation failures."""
    pass

class DuplicateKeyError(ProvenanceError):
    """Raised when JSON input contains duplicate keys at any nesting level."""
    def __init__(self, key: str, path: str):
        super().__init__(f"Duplicate key detected in provenance JSON: '{key}' at path '{path}'")
        self.key = key
        self.path = path

class AmbiguousKeyError(ProvenanceError):
    """Raised when keys collide under Unicode normalization (NFKC) or escape representation."""
    def __init__(self, key1: str, key2: str, path: str):
        super().__init__(f"Ambiguous key collision detected: '{key1}' vs '{key2}' at path '{path}'")
        self.key1 = key1
        self.key2 = key2
        self.path = path

class StrictProvenanceParser:
    """Strict JSON parser that rejects duplicate and ambiguous keys at all nesting levels."""

    @staticmethod
    def parse(raw_json: str | bytes) -> dict[str, Any]:
        """Parses JSON text/bytes, enforcing key uniqueness and Unicode normalization.

        Preserves object pairs during decoding and verifies that no key is repeated
        or normalizes to an existing key at the same scope.
        """
        ...
```

### 6.3 Signed Provenance Policy & Verifier (`src/rush/release/provenance_policy.py`)

```python
class UntrustedSignerError(ProvenanceError):
    """Raised when envelope signer is not present in trusted allowlist."""
    pass

class SubjectMismatchError(ProvenanceError):
    """Raised when artifact subject digest or package identity does not match policy."""
    pass

class BuilderMismatchError(ProvenanceError):
    """Raised when builder ID or buildType does not match policy."""
    pass

@dataclass(frozen=True)
class SignedProvenancePolicy:
    trusted_roots: tuple[str, ...]  # Base64 or PEM encoded trusted root certs/keys
    allowed_signers: tuple[str, ...]  # Allowlisted signer identities (key IDs or subjects)
    allowed_builders: tuple[str, ...]  # Allowlisted builder URIs
    expected_build_type: str = RUSH_BUILD_TYPE_DRAFT_V1
    source_uri_pattern: str = "^https://github.com/rush-cli/rush.*$"
    allow_unsigned: bool = False

@dataclass(frozen=True)
class ProvenanceVerificationResult:
    is_valid: bool
    signer_id: str | None
    builder_id: str
    subject_digest: str
    statement: StatementV1
    summary: str
    warnings: tuple[str, ...] = ()

class ProvenancePolicyVerifier:
    """Verifies in-toto Statement v1 DSSE envelopes against SignedProvenancePolicy."""

    def __init__(self, policy: SignedProvenancePolicy) -> None:
        self.policy = policy

    def verify(
        self,
        raw_envelope: str | bytes,
        expected_artifact_path: Path | None = None,
    ) -> ProvenanceVerificationResult:
        """Parses envelope with StrictProvenanceParser, checks signature, and evaluates policy."""
        ...
```

### 6.4 Engine Taxonomy & Support Policy (`src/rush/engines/support_policy.py`)

```python
class EngineConformanceError(Exception):
    """Base exception for engine conformance and taxonomy errors."""
    pass

class AllSkippedViolationError(EngineConformanceError):
    """Raised when a supported engine family passes with all skipped tests."""
    pass

class AmbientPathPollutionError(EngineConformanceError):
    """Raised when an unprovisioned ambient tool on PATH leaks into engine discovery."""
    pass

class ReleaseGateFailureError(EngineConformanceError):
    """Raised when a mandatory release gate engine (e.g. mypy) fails or is skipped."""
    pass

SupportClass = Literal["mandatory", "supported-optional", "best-effort"]

@dataclass(frozen=True)
class EngineTaxonomyRecord:
    family: str
    support_class: SupportClass
    executable: str
    version_command: str
    can_pass_all_skipped: bool
    permitted_skip_reason: str
    clean_fixture: str
    finding_fixture: str
    malformed_fixture: str | None = None

class EngineSupportPolicy:
    """Loads and enforces engine taxonomy rules from governance/engine-support.toml."""

    @classmethod
    def load(cls, manifest_path: Path | None = None) -> "EngineSupportPolicy":
        ...

    def get_family(self, family_name: str) -> EngineTaxonomyRecord:
        ...

    def validate_execution_result(
        self,
        family_name: str,
        results: list[dict[str, Any]],
    ) -> None:
        """Asserts that supported-optional families never succeed with all-skipped results."""
        ...

    def verify_release_gate(self, engine_name: str = "mypy") -> bool:
        """Executes release-gate command; raises ReleaseGateFailureError if unavailable or skipped."""
        ...
```

### 6.5 State Invariants

1. **Default Unsigned Draft Invariant:** Default output of `rush attest` and `AttestationTool` is strictly an unsigned draft (`provenance_draft` with `assurance: "unsigned_draft"`). Default output must never claim SLSA levels (e.g. SLSA Level 3), signatures, verified builder, completeness, or reproducibility without cryptographic verification.
2. **Artifact Subject Digest Invariant:** Attestation subjects must be actual physical package artifacts (wheel/sdist) resolved from `dist/` or explicit artifact path with computed SHA-256 digests; git commits or workspace trees are strictly forbidden as primary subjects. Missing distribution artifacts fail closed with `skipped` status or `MissingArtifactError`.
3. **Strict JSON Key Uniqueness Invariant:** Provenance parsing strictly forbids duplicate keys or Unicode-equivalent key collisions at any level (envelope, Statement, predicate, parameters). Any collision raises `DuplicateKeyError` or `AmbiguousKeyError` before dictionary creation.
4. **Cryptographic Equality Invariant:** Optional signed provenance verification requires strict equality of signer identity, trusted root, builder ID, artifact digest, package name, statement type, predicate type, buildType, externalParameters, and source repository URI against `SignedProvenancePolicy`. Empty allowlists fail closed.
5. **Fixed-PATH Isolation Invariant:** Engine tests execute within `FixedPathEnvironment` isolating `PATH` from ambient developer host binaries. Uncontrolled local binaries cannot satisfy engine contracts.
6. **No-All-Skipped Invariant:** A supported-optional or mandatory engine family cannot pass when all tests are skipped (`can_pass_all_skipped = false`). An all-skipped suite raises `AllSkippedViolationError`.
7. **Release-Gate Mypy Non-Skipped Invariant:** `mypy` is an explicit release gate; running `mypy --version` and `mypy src/rush` must be provisioned and non-skipped. Any skip, missing binary, or nonzero exit code blocks release handoff with `ReleaseGateFailureError`.

---

## 7. Contract Test Inventory (T-59.01 to T-59.25)

| Test ID | Test File | Test Function | Target Contract & Non-Permissive Assertion |
|---|---|---|---|
| **T-59.01** | `tests/test_phase59_provenance_draft.py` | `test_default_output_is_explicit_unsigned_draft` | Asserts `AttestationTool.run()` default output contains `assurance="unsigned_draft"`, `is_signed=False`, and summary contains "draft". Asserts output contains zero claims of SLSA Level 3, verified builder, or signature. |
| **T-59.02** | `tests/test_phase59_provenance_draft.py` | `test_subject_is_actual_artifact_and_package_identity` | Provides real built wheel/sdist in `dist/`; asserts statement `subject` contains artifact filename and real SHA-256 digest. Asserts commit hash is not used as subject name or digest. |
| **T-59.03** | `tests/test_phase59_provenance_draft.py` | `test_missing_evidence_never_fabricates_claim` | Runs `AttestationTool` in clean repo with zero built artifacts in `dist/`; asserts result status is `skipped` with summary indicating no package artifacts found, and no statement is fabricated. |
| **T-59.04** | `tests/test_phase59_provenance_draft.py` | `test_draft_envelope_conforms_to_sanitizer_contract` | Verifies generated draft statement passes through `rush.safety.redactor.sanitize_value` with zero unredacted secrets or path leaks. |
| **T-59.05** | `tests/test_phase59_provenance.py` | `test_slsa_provenance_cryptographic_verification` | **R-013 Governance Test:** Asserts provenance attestation requires actual cryptographic signature and fails closed on unsigned or fabricated claims. |
| **T-59.06** | `tests/test_phase59_provenance_structure.py` | `test_statement_and_predicate_types_are_exact` | Validates Statement v1 schema: `_type` strictly equals `"https://in-toto.io/Statement/v1"` and `predicateType` strictly equals `"https://slsa.dev/provenance/v1"`. Any divergence raises `SchemaMismatchError`. |
| **T-59.07** | `tests/test_phase59_provenance_structure.py` | `test_build_type_parameters_source_subject_and_extensions_are_pinned` | Asserts `buildDefinition` contains exact pinned `buildType`, `externalParameters` (sourceUri, commit, entryPoint), `internalParameters` (builderId), and `runDetails`. |
| **T-59.08** | `tests/test_phase59_provenance_structure.py` | `test_unknown_or_malformed_fields_fail_validation` | Injects unknown top-level or predicate fields; asserts schema validator rejects with descriptive error. |
| **T-59.09** | `tests/test_phase59_provenance_structure.py` | `test_provenance_draft_dataclass_is_frozen_and_serializable` | Asserts `StatementV1`, `SLSAPredicateV1`, and `ProvenanceDraft` are immutable frozen dataclasses that serialize to valid JSON. |
| **T-59.10** | `tests/test_phase59_provenance_parser.py` | `test_duplicate_keys_at_raw_envelope_level_reject` | Injects duplicate `"payload"` or `"signatures"` key in raw DSSE JSON; asserts `StrictProvenanceParser.parse()` raises `DuplicateKeyError`. |
| **T-59.11** | `tests/test_phase59_provenance_parser.py` | `test_duplicate_keys_at_decoded_statement_and_predicate_level_reject` | Injects duplicate `"predicate"` or `"buildDefinition"` key in decoded statement JSON; asserts parser raises `DuplicateKeyError`. |
| **T-59.12** | `tests/test_phase59_provenance_parser.py` | `test_unicode_and_escaped_key_ambiguity_rejects_before_policy` | Injects colliding keys under Unicode normalization (e.g. `\u0062uilder` vs `builder`); asserts parser raises `AmbiguousKeyError`. Zero calls to downstream policy. |
| **T-59.13** | `tests/test_phase59_provenance_parser.py` | `test_malformed_or_truncated_json_rejects_cleanly` | Injects truncated or syntactically invalid JSON; asserts parser raises `ProvenanceError` fail-closed. |
| **T-59.14** | `tests/test_phase59_provenance_policy.py` | `test_valid_synthetic_signed_envelope_passes_exact_policy` | Signs valid Statement v1 using synthetic Ed25519/ECDSA test key; asserts `ProvenancePolicyVerifier.verify()` returns `is_valid=True` with correct signer and builder IDs. |
| **T-59.15** | `tests/test_phase59_provenance_policy.py` | `test_each_signer_builder_root_subject_type_parameter_source_mismatch_rejects` | Individually mutates: (a) signer key, (b) trusted root, (c) builder ID, (d) subject digest, (e) statement type, (f) predicate type, (g) source URI; asserts each mutation fails verification fail-closed. |
| **T-59.16** | `tests/test_phase59_provenance_policy.py` | `test_empty_allowlist_fails_closed` | Instantiates `SignedProvenancePolicy` with empty `allowed_signers` or `trusted_roots`; asserts all envelopes are rejected with `UntrustedSignerError`. |
| **T-59.17** | `tests/test_phase59_provenance_policy.py` | `test_tampered_payload_or_signature_fails_verification` | Mutates a single byte in payload or signature; asserts `cryptography` verification raises signature error and verifier returns `is_valid=False`. |
| **T-59.18** | `tests/test_phase59_provenance_policy.py` | `test_synthetic_fixtures_contain_zero_live_keys` | Scans test fixtures asserting all keys and certificates contain explicit `"TEST_ONLY"` or `"SYNTHETIC"` markers and zero production secrets. |
| **T-59.19** | `tests/test_phase59_engine_conformance.py` | `test_every_engine_has_one_taxonomy_entry` | Loads `governance/engine-support.toml`; asserts all 19 engine families have a valid entry with support_class, executable, version_command, and fixtures. |
| **T-59.20** | `tests/test_phase59_engine_conformance.py` | `test_supported_family_has_success_failure_and_malformed_jobs` | Asserts every `supported-optional` family has declared clean, finding, and malformed fixture paths that resolve to actual tests/files. |
| **T-59.21** | `tests/test_phase59_engine_conformance.py` | `test_supported_family_all_skipped_fails` | Simulates test suite where a supported-optional engine returns `skipped` for all test cases; asserts `EngineSupportPolicy.validate_execution_result()` raises `AllSkippedViolationError`. |
| **T-59.22** | `tests/test_phase59_engine_conformance.py` | `test_fixed_path_ignores_ambient_tools` | Runs engine discovery inside `FixedPathEnvironment(empty_dir)`; asserts discovery returns `None` even if tool is installed on the developer's host machine. |
| **T-59.23** | `tests/test_phase59_engine_conformance.py` | `test_release_gate_mypy_is_provisioned_and_non_skipped` | Executes `EngineSupportPolicy.verify_release_gate("mypy")`; asserts that mypy executes `mypy --version` and `mypy src/rush`, and that missing/skipped mypy raises `ReleaseGateFailureError`. |
| **T-59.24** | `tests/test_phase59_engines.py` | `test_engine_discovery_and_capability_matrix` | **R-014 Governance Test:** Verifies deterministic engine discovery against the complete capability and taxonomy matrix. |
| **T-59.25** | `tests/test_phase59_engine_conformance.py` | `test_remediation_phase59_manifest_integrity` | Verifies `governance/remediation-phase-59.toml` registers all 25 contract tests and closes R-013 and R-014. |

---

## 8. File, Dependency, and Documentation Governance

### 8.1 File Write Inventory

#### New Files
1. `src/rush/release/provenance_policy.py`: Models (`StatementV1`, `SLSAPredicateV1`, `ProvenanceDraft`), `StrictProvenanceParser`, `SignedProvenancePolicy`, `ProvenancePolicyVerifier`, typed exceptions.
2. `src/rush/engines/support_policy.py`: Models (`EngineTaxonomyRecord`), `EngineSupportPolicy`, `FixedPathEnvironment`, typed engine exceptions.
3. `tests/test_phase59_provenance_draft.py`: Contract tests T-59.01 through T-59.04.
4. `tests/test_phase59_provenance.py`: R-013 governance bridge test (T-59.05).
5. `tests/test_phase59_provenance_structure.py`: Contract tests T-59.06 through T-59.09.
6. `tests/test_phase59_provenance_parser.py`: Contract tests T-59.10 through T-59.13.
7. `tests/test_phase59_provenance_policy.py`: Contract tests T-59.14 through T-59.18.
8. `tests/test_phase59_engine_conformance.py`: Contract tests T-59.19 through T-59.23, T-59.25.
9. `tests/test_phase59_engines.py`: R-014 governance bridge test (T-59.24).
10. `tests/fixtures/remediation/provenance/unsigned-draft.json`: Expected unsigned draft statement fixture.
11. `tests/fixtures/remediation/provenance/signed-valid-envelope.json`: Valid synthetic signed in-toto DSSE envelope.
12. `tests/fixtures/remediation/provenance/signed-invalid-envelopes.json`: Collection of invalid envelopes (duplicate keys, mismatched signers, tampered payloads).
13. `governance/remediation-phase-59.toml`: Phase 59 completion manifest.
14. `docs/developer/phase-59-implementation-evidence.md`: Evidence and execution logs.

#### Modified Files
1. `src/rush/tools/attest.py`: Migrate to `ProvenanceDraft`, real artifact digest subjects, strict schema validation, fail-closed handling on missing artifacts.
2. `src/rush/release/provenance.py`: Integrate checksum manifests with `ProvenanceDraft` builder.
3. `src/rush/release/__init__.py`: Export provenance models and verifier.
4. `src/rush/engines/__init__.py`: Connect engine registry to `EngineSupportPolicy`.
5. `src/rush/cli.py`: Wire `rush attest` options (`--output`, `--verify`, `--builder-id`) through `ProvenancePolicyVerifier` and adapters.
6. `src/rush/mcp.py`: Update `tool.attest` registration with truthful unsigned draft schema and metadata.
7. `src/rush/contracts/operations.py`: Reconcile provenance and engine operation signatures.
8. `governance/engine-support.toml`: Reconcile engine taxonomy entries and release-gate specifications.
9. `governance/public-operations.toml`: Reconcile `tool.attest` schema and options.
10. `governance/remediation-contracts.toml`: Mark R-013 and R-014 completed.
11. `.github/workflows/ci.yml`: Add provisioned engine test jobs (clean/finding/malformed) and mandatory non-skipped mypy step.
12. `.github/workflows/release.yml`: Add pre-release non-skipped mypy verification gate and checksums manifest generation.
13. `tests/test_phase50_slsa_attestation.py`: Align existing tests with truthful unsigned draft output.
14. `tests/test_supply_chain_tools.py`: Align supply-chain test fixtures.
15. `tests/test_static_tools.py`: Align static engine contracts with `FixedPathEnvironment`.
16. `tests/conftest.py`: Add `fixed_path_env` and synthetic crypto key fixtures.

---

### 8.2 Comprehensive `/docs` Synchronization Inventory (48 Files across 4 Groups)

#### Group 1: Core Specifications & Public Contracts (15 files)
1. `docs/ARCHITECTURE.md`: Document truthful provenance architecture, in-toto Statement v1 + SLSA Provenance v1 predicate, strict JSON parser, signed verification policy, and engine taxonomy with fixed-PATH isolation.
2. `docs/SECURITY.md`: Supply chain security, SLSA in-toto provenance verification, DSSE envelope verification, strict JSON parser against parser differentials.
3. `docs/SAFETY.md`: Truthful build claims, prohibition of fabricated SLSA Level 3 claims, engine fallback safety.
4. `docs/PRIVACY.md`: Scrubbing of local paths and credentials from provenance statements and attestation drafts.
5. `docs/API_REFERENCE.md`: Public APIs for `rush.release.provenance`, `rush.release.provenance_policy`, `rush.engines.support_policy`.
6. `docs/CLI_REFERENCE.md`: `rush attest` options (`--output`, `--builder-id`, `--verify`), `rush engines` command, exit codes.
7. `docs/MCP.md`: FastMCP tools for provenance attestation (`tool.attest`), engine discovery tools.
8. `docs/MCP_REFERENCE.md`: Tool definitions for `tool.attest` (unsigned draft schema, input parameters, ToolResultV1 metadata).
9. `docs/CONFIGURATION.md`: Configuration for provenance generation, builder ID, engine timeouts, and support classes.
10. `docs/CONFIG_SCHEMA.md`: Schema for `[release.provenance]` and `[engines]` sections in `rush.toml`.
11. `docs/GLOSSARY.md`: Glossary entries for `in-toto Statement`, `SLSA Provenance`, `DSSE Envelope`, `Unsigned Draft`, `Engine Support Policy`, `Fixed-PATH Isolation`.
12. `docs/TOOL_CATALOG.md`: Catalog entries for `tool.attest`, engine discovery, and supply-chain tools.
13. `docs/JSON_SCHEMA.md`: Schemas for in-toto Statement v1, SLSA Provenance v1 predicate, and engine support records.
14. `docs/SEMANTIC_DRIFT.md`: Resolution of R-013 (SLSA Level 3 claims without attestation) and R-014 (ambient engine discovery & all-skipped tests).
15. `docs/SCOPE.md`: Physical scope of build artifacts and provenance export under `PhysicalRoot`.

#### Group 2: Developer, Engine & Maintainer Guides (15 files)
16. `docs/ENGINES.md`: Engine taxonomy (mandatory, supported-optional, best-effort), discovery mechanism, fixed-PATH isolation, no-all-skipped rule.
17. `docs/ENGINE_COMPATIBILITY.md`: Engine compatibility matrix across platforms, pinned versions, permitted skip reasons.
18. `docs/developer/architecture.md`: Section on provenance pipeline, strict parser, policy verifier, and engine support architecture.
19. `docs/developer/source-tree.md`: Add `src/rush/release/provenance_policy.py`, `src/rush/engines/support_policy.py`.
20. `docs/developer/testing-guide.md`: Section on Phase 59 contract test suites (`tests/test_phase59_*.py`), fixed-PATH testing, synthetic key fixtures.
21. `docs/developer/debugging-guide.md`: Troubleshooting duplicate key rejections, untrusted signer errors, and missing engine failures.
22. `docs/developer/tool-development.md`: Writing tools that generate truthful provenance and conform to engine taxonomy.
23. `docs/developer/backlog.md`: Mark Phase 59 Complete and record release blocker closure (R-001 through R-014, R-016).
24. `docs/developer/issues.md`: Resolution of ISS-059-01 (Untruthful SLSA Level 3 Claims) and ISS-059-02 (Ambient Engine Discovery & All-Skipped Illusion).
25. `docs/developer/ci-and-packaging.md`: Hardened CI workflow, provisioned engine test matrix, isolated artifact probes.
26. `docs/developer/phase-59-implementation-evidence.md`: Baseline evidence, contract test execution logs, and probe results.
27. `docs/maintainers/release-playbook.md`: Comprehensive release playbook with mandatory non-skipped `mypy` gate, checksum generation, and provenance verification.
28. `docs/maintainers/versioning-and-compatibility.md`: Pinned engine versions, taxonomy support classes, and provenance schema versioning.
29. `docs/maintainers/incident-and-security.md`: Handling supply chain compromises, invalid signatures, and compromised builder keys.
30. `docs/maintainers/adr/002-external-engine-discovery.md`: Align ADR with deterministic taxonomy and fixed-PATH isolation.

#### Group 3: Reference, Tools & User Guides (12 files)
31. `docs/DISTRIBUTION.md`: Package distribution verification, wheel and sdist SHA-256 manifests, provenance drafts.
32. `docs/RELEASE.md`: Pre-release verification gates, non-skipped mypy gate, SLSA attestation draft export, checksums manifest.
33. `docs/reference/engine-directory.md`: Complete directory of 19 engine families, support classes, executables, and version commands.
34. `docs/reference/result-reference.md`: Output shape reference for `tool.attest` returning `ToolResultV1` with draft metadata.
35. `docs/reference/cli-reference.md`: Reference for `rush attest` command line arguments and behavior.
36. `docs/reference/environment-variables.md`: Reference for `RUSH_BUILDER_ID`, `RUSH_PROVENANCE_KEY`, `RUSH_ENGINE_PATH`.
37. `docs/specs/slsa-attestation-spec.md`: Complete specification for in-toto Statement v1, SLSA Provenance v1 predicate, unsigned draft, and signed policy.
38. `docs/tools/attest.md`: User documentation for `rush attest` tool, unsigned draft default, real artifact digest requirement.
39. `docs/tools/pr_synthesize.md`: Integration of PR synthesizer with build provenance drafts.
40. `docs/user-guide/security-and-supply-chain.md`: User guide for build provenance, SLSA drafts, and engine quality checks.
41. `docs/user-guide/advanced-checks.md`: Advanced options for provenance verification and engine selection.
42. `docs/workflows/supply_chain_security_and_flagship_release.md`: End-to-end workflow for supply chain verification and flagship release.

#### Group 4: Governance, Evidence & Release Tracking (6 files)
43. `governance/remediation-phase-59.toml`: Phase 59 completion manifest.
44. `governance/remediation-contracts.toml`: Mark R-013 and R-014 completed.
45. `governance/engine-support.toml`: Reconcile engine taxonomy entries and release-gate specifications.
46. `README.md`: Update test badge (1,163 to 1,188 passed), release readiness statement, engine taxonomy summary.
47. `CHANGELOG.md`: Log Phase 59 additions under `[0.3.0]`.
48. `docs/adr/006-bounded-ci.md`: Align ADR with provisioned engine success/failure/malformed CI jobs.

---

### 8.3 Dependency Constraints

- Zero new third-party dependencies introduced.
- Strict reliance on Python 3.12 standard library (`hashlib`, `json`, `pathlib`, `dataclasses`, `time`, `shutil`, `subprocess`, `re`, `unicodedata`) plus existing project dependencies `cryptography==50.0.0` and `ruamel.yaml==0.19.1`.

---

## 9. Ordered Workstreams and Atomic Task Cards

### P59.0 — Admission Gate & Baseline Evidence

#### P59.0.1 — EVIDENCE: Map Current Claims, Parse/Policy Seams, and Engine Jobs
- **Task ID:** P59.0.1
- **Binary Outcome:** Baseline evidence recorded in `docs/developer/phase-59-implementation-evidence.md`; full test suite passes (1,163 passed, 0 warnings); all attest/provenance/engine seams mapped.
- **Prerequisites:** Admission gate §4 passed.
- **Allowed Writes:** `docs/developer/phase-59-implementation-evidence.md`, R-013/R-014 admission fields in `governance/remediation-contracts.toml`.
- **Actions:**
  1. Run `.venv/Scripts/python.exe -m pytest tests/ -q` and record 1,163 passing tests.
  2. Inspect `AttestationTool`, `ArtifactProvenanceVerifier`, `ENGINES`, `engine-support.toml`, and `.github/workflows/ci.yml`.
  3. Map call paths and divergence points to tasks P59.1 through P59.5.

---

### P59.1 — Unsigned Draft & Real Artifact Subject Identity

#### P59.1.1 — RED: Define Honest Default Output and Artifact Subject Contract Tests
- **Task ID:** P59.1.1
- **Binary Outcome:** Create `tests/test_phase59_provenance_draft.py` and `tests/test_phase59_provenance.py` containing contract tests T-59.01, T-59.02, T-59.03, T-59.04, T-59.05; create `tests/fixtures/remediation/provenance/unsigned-draft.json`; tests fail (RED).
- **Prerequisites:** P59.0.1.
- **Allowed Writes:** `tests/test_phase59_provenance_draft.py`, `tests/test_phase59_provenance.py`, `tests/fixtures/remediation/provenance/unsigned-draft.json`.
- **Actions:**
  1. Author T-59.01 (`test_default_output_is_explicit_unsigned_draft`).
  2. Author T-59.02 (`test_subject_is_actual_artifact_and_package_identity`).
  3. Author T-59.03 (`test_missing_evidence_never_fabricates_claim`).
  4. Author T-59.04 (`test_draft_envelope_conforms_to_sanitizer_contract`).
  5. Author T-59.05 (`test_slsa_provenance_cryptographic_verification`).
  6. Run `pytest tests/test_phase59_provenance_draft.py tests/test_phase59_provenance.py -q` and confirm failures.

#### P59.1.2 — GREEN: Implement Truthful Unsigned Draft Builder
- **Task ID:** P59.1.2
- **Binary Outcome:** Update `src/rush/tools/attest.py` and `src/rush/release/provenance.py`; tests in `tests/test_phase59_provenance_draft.py` and `tests/test_phase59_provenance.py` pass (GREEN).
- **Prerequisites:** P59.1.1 RED.
- **Allowed Writes:** `src/rush/tools/attest.py`, `src/rush/release/provenance.py`, `src/rush/release/__init__.py`, `src/rush/cli.py`, `src/rush/mcp.py`, `tests/test_phase50_slsa_attestation.py`.
- **Actions:**
  1. Refactor `AttestationTool` to produce explicit `ProvenanceDraft` with `assurance="unsigned_draft"`.
  2. Require real artifact digest from `dist/` or explicit `artifact_path`; forbid commit hash subjects.
  3. Missing artifacts return `status="skipped"` with descriptive reason; never fabricate statements.
  4. Ensure sanitized output and canonical `ToolResultV1` metadata.
  5. Verify tests pass cleanly.

---

### P59.2 — Statement & Predicate Pinned Structure

#### P59.2.1 — RED: Define Exact Statement and Predicate Schema Tests
- **Task ID:** P59.2.1
- **Binary Outcome:** Create `tests/test_phase59_provenance_structure.py` containing contract tests T-59.06, T-59.07, T-59.08, T-59.09; tests fail (RED).
- **Prerequisites:** P59.1.2.
- **Allowed Writes:** `tests/test_phase59_provenance_structure.py`.
- **Actions:**
  1. Author T-59.06 (`test_statement_and_predicate_types_are_exact`).
  2. Author T-59.07 (`test_build_type_parameters_source_subject_and_extensions_are_pinned`).
  3. Author T-59.08 (`test_unknown_or_malformed_fields_fail_validation`).
  4. Author T-59.09 (`test_provenance_draft_dataclass_is_frozen_and_serializable`).
  5. Run `pytest tests/test_phase59_provenance_structure.py -q` and confirm failures.

#### P59.2.2 — GREEN: Implement Pinned Statement and Predicate Models
- **Task ID:** P59.2.2
- **Binary Outcome:** Create `src/rush/release/provenance_policy.py` with dataclass models; tests in `tests/test_phase59_provenance_structure.py` pass (GREEN).
- **Prerequisites:** P59.2.1 RED.
- **Allowed Writes:** `src/rush/release/provenance_policy.py`, `src/rush/release/provenance.py`, `src/rush/tools/attest.py`.
- **Actions:**
  1. Implement `SubjectV1`, `ExternalParametersV1`, `InternalParametersV1`, `BuildDefinitionV1`, `RunDetailsV1`, `SLSAPredicateV1`, `StatementV1`, and `ProvenanceDraft`.
  2. Implement schema validation function verifying all pinned types and fields.
  3. Ensure models are frozen, immutable, and properly serializable.
  4. Verify tests pass cleanly.

---

### P59.3 — Strict JSON Parser & Ambiguity Rejection

#### P59.3.1 — RED: Define Duplicate and Ambiguous Key Rejection Tests
- **Task ID:** P59.3.1
- **Binary Outcome:** Create `tests/test_phase59_provenance_parser.py` containing contract tests T-59.10, T-59.11, T-59.12, T-59.13; tests fail (RED).
- **Prerequisites:** P59.2.2.
- **Allowed Writes:** `tests/test_phase59_provenance_parser.py`.
- **Actions:**
  1. Author T-59.10 (`test_duplicate_keys_at_raw_envelope_level_reject`).
  2. Author T-59.11 (`test_duplicate_keys_at_decoded_statement_and_predicate_level_reject`).
  3. Author T-59.12 (`test_unicode_and_escaped_key_ambiguity_rejects_before_policy`).
  4. Author T-59.13 (`test_malformed_or_truncated_json_rejects_cleanly`).
  5. Run `pytest tests/test_phase59_provenance_parser.py -q` and confirm failures.

#### P59.3.2 — GREEN: Implement StrictProvenanceParser with Unicode Normalization
- **Task ID:** P59.3.2
- **Binary Outcome:** Implement `StrictProvenanceParser` in `src/rush/release/provenance_policy.py`; tests in `tests/test_phase59_provenance_parser.py` pass (GREEN).
- **Prerequisites:** P59.3.1 RED.
- **Allowed Writes:** `src/rush/release/provenance_policy.py`.
- **Actions:**
  1. Implement `StrictProvenanceParser.parse(raw_json)` using custom `json.JSONDecoder` with `object_pairs_hook`.
  2. Check for duplicate keys in pairs list; raise `DuplicateKeyError`.
  3. Normalize keys using `unicodedata.normalize("NFKC", k)`; detect collisions; raise `AmbiguousKeyError`.
  4. Recurse through nested structures ensuring every level is validated before dictionary conversion.
  5. Verify tests pass cleanly.

---

### P59.4 — Optional Signed Policy & Synthetic Cryptographic Verification

#### P59.4.1 — RED: Define Signed Verification Policy Contract Tests
- **Task ID:** P59.4.1
- **Binary Outcome:** Create `tests/test_phase59_provenance_policy.py` containing contract tests T-59.14, T-59.15, T-59.16, T-59.17, T-59.18; create fixtures `signed-valid-envelope.json` and `signed-invalid-envelopes.json`; tests fail (RED).
- **Prerequisites:** P59.3.2.
- **Allowed Writes:** `tests/test_phase59_provenance_policy.py`, `tests/fixtures/remediation/provenance/signed-valid-envelope.json`, `tests/fixtures/remediation/provenance/signed-invalid-envelopes.json`.
- **Actions:**
  1. Author T-59.14 (`test_valid_synthetic_signed_envelope_passes_exact_policy`).
  2. Author T-59.15 (`test_each_signer_builder_root_subject_type_parameter_source_mismatch_rejects`).
  3. Author T-59.16 (`test_empty_allowlist_fails_closed`).
  4. Author T-59.17 (`test_tampered_payload_or_signature_fails_verification`).
  5. Author T-59.18 (`test_synthetic_fixtures_contain_zero_live_keys`).
  6. Run `pytest tests/test_phase59_provenance_policy.py -q` and confirm failures.

#### P59.4.2 — GREEN: Implement SignedProvenancePolicy and ProvenancePolicyVerifier
- **Task ID:** P59.4.2
- **Binary Outcome:** Implement `SignedProvenancePolicy` and `ProvenancePolicyVerifier` in `src/rush/release/provenance_policy.py`; tests in `tests/test_phase59_provenance_policy.py` pass (GREEN).
- **Prerequisites:** P59.4.1 RED.
- **Allowed Writes:** `src/rush/release/provenance_policy.py`, `src/rush/release/provenance.py`, `src/rush/tools/attest.py`, `src/rush/cli.py`.
- **Actions:**
  1. Implement `SignedProvenancePolicy` and `ProvenancePolicyVerifier`.
  2. Use `cryptography` primitives to verify DSSE envelope signature against allowlisted public keys/roots.
  3. Verify exact equality of signer identity, builder ID, artifact digest, package name, statement type, predicate type, and source URI regex.
  4. Ensure empty allowlist fails closed with `UntrustedSignerError`.
  5. Wire `--verify` option into `rush attest` CLI command.
  6. Verify tests pass cleanly.

---

### P59.5 — Deterministic Engine Conformance & Provisioned CI

#### P59.5.1 — RED: Define Engine Taxonomy, Fixed-PATH Isolation, and Release Gate Tests
- **Task ID:** P59.5.1
- **Binary Outcome:** Create `tests/test_phase59_engine_conformance.py` and `tests/test_phase59_engines.py` containing contract tests T-59.19, T-59.20, T-59.21, T-59.22, T-59.23, T-59.24, T-59.25; tests fail (RED).
- **Prerequisites:** P59.0.1.
- **Allowed Writes:** `tests/test_phase59_engine_conformance.py`, `tests/test_phase59_engines.py`, `tests/conftest.py`.
- **Actions:**
  1. Author T-59.19 (`test_every_engine_has_one_taxonomy_entry`).
  2. Author T-59.20 (`test_supported_family_has_success_failure_and_malformed_jobs`).
  3. Author T-59.21 (`test_supported_family_all_skipped_fails`).
  4. Author T-59.22 (`test_fixed_path_ignores_ambient_tools`).
  5. Author T-59.23 (`test_release_gate_mypy_is_provisioned_and_non_skipped`).
  6. Author T-59.24 (`test_engine_discovery_and_capability_matrix`).
  7. Author T-59.25 (`test_remediation_phase59_manifest_integrity`).
  8. Run `pytest tests/test_phase59_engine_conformance.py tests/test_phase59_engines.py -q` and confirm failures.

#### P59.5.2 — GREEN: Implement EngineSupportPolicy and Hardened CI Workflow
- **Task ID:** P59.5.2
- **Binary Outcome:** Implement `src/rush/engines/support_policy.py`; update `governance/engine-support.toml`, `.github/workflows/ci.yml`, and `.github/workflows/release.yml`; tests in `tests/test_phase59_engine_conformance.py` and `tests/test_phase59_engines.py` pass (GREEN).
- **Prerequisites:** P59.5.1 RED.
- **Allowed Writes:** `src/rush/engines/support_policy.py`, `src/rush/engines/__init__.py`, `governance/engine-support.toml`, `.github/workflows/ci.yml`, `.github/workflows/release.yml`, `tests/test_static_tools.py`.
- **Actions:**
  1. Implement `EngineSupportPolicy` and `EngineTaxonomyRecord` loading from `governance/engine-support.toml`.
  2. Implement `FixedPathEnvironment` isolating `PATH` from host environment.
  3. Enforce `can_pass_all_skipped = false` for supported-optional families; raise `AllSkippedViolationError`.
  4. Enforce `mypy` release gate verification (`mypy --version` and `mypy src/rush`); raise `ReleaseGateFailureError` on failure.
  5. Update `.github/workflows/ci.yml` with provisioned engine jobs and non-skipped mypy step.
  6. Update `.github/workflows/release.yml` with non-skipped pre-release mypy gate.
  7. Verify tests pass cleanly.

---

### P59.6 — Documentation & Release Handoff

#### P59.6.1 — VERIFY/DOCS/HANDOFF: Close Release Readiness Truthfully
- **Task ID:** P59.6.1
- **Binary Outcome:** All 48 documentation files synchronized; `governance/remediation-contracts.toml` updated; `governance/remediation-phase-59.toml` generated; all gates in §10 pass cleanly.
- **Prerequisites:** P59.1.2 through P59.5.2 GREEN.
- **Allowed Writes:** All 48 documentation files listed in §8.2, `governance/remediation-phase-59.toml`, `governance/remediation-contracts.toml`.
- **Actions:**
  1. Synchronize all 48 documentation files across the 4 groups detailed in §8.2.
  2. Update `governance/remediation-contracts.toml` marking R-013 and R-014 completed.
  3. Create `governance/remediation-phase-59.toml` recording completion of all 25 Phase 59 contract tests.
  4. Execute full verification suite (§10).
  5. Verify clean git diff and hygiene.

---

## 10. Final Verification and Delivery Gate

```text
$env:VIRTUAL_ENV=$null
$env:PYTHONPATH=$null
.venv/Scripts/python.exe -m pytest tests/test_phase59_provenance_draft.py tests/test_phase59_provenance.py tests/test_phase59_provenance_structure.py tests/test_phase59_provenance_parser.py tests/test_phase59_provenance_policy.py tests/test_phase59_engine_conformance.py tests/test_phase59_engines.py -q
.venv/Scripts/python.exe -m pytest tests/ -q
.venv/Scripts/ruff.exe check src tests scripts
.venv/Scripts/ruff.exe format --check src tests scripts
.venv/Scripts/python.exe scripts/probe_installed_artifacts.py
git diff --check
git diff --name-only
git status --short --branch
```

The provisioned Phase 59 engine job also runs the exact mypy executable/version pinned in `governance/engine-support.toml` as `mypy --version` followed by `mypy src/rush`; either command unavailable, skipped, or nonzero blocks the release handoff.

---

## 11. Exit Checklist and Successor Evidence

- [ ] Ordinary RED precedes GREEN; no skip/XFAIL/XPASS.
- [ ] Default output is explicitly an unsigned draft (`provenance_draft`) with actual artifact/package subjects only.
- [ ] No unverified claims of SLSA Level 1/2/3, verified builder, completeness, or signature in default output.
- [ ] In-toto Statement v1 and SLSA Provenance v1 predicate schemas are pinned and immutable.
- [ ] Strict JSON parser rejects duplicate keys and Unicode-equivalent collisions at all raw/decoded/nested levels before policy.
- [ ] Optional signed verification mode validates exact equality of signer, root, builder, subject, statement/predicate type, buildType, and source URI using synthetic test fixtures.
- [ ] Zero live private signing keys or production secrets in codebase or fixtures.
- [ ] Engine taxonomy is enforced via single-source `governance/engine-support.toml`.
- [ ] Supported engine families cannot pass when all tests are skipped (`can_pass_all_skipped = false`).
- [ ] Fixed-PATH isolation prevents ambient developer tools on PATH from polluting engine discovery.
- [ ] Release-gate engine (`mypy`) is provisioned and verified non-skipped.
- [ ] All 48 documentation files across `/docs` and all subfolders are synchronized.
- [ ] R-001 through R-014 and R-016 release handoff is complete; R-015 explicitly remains Phase 60.
- [ ] Full test suite passes (1,188+ passed, 0 warnings).
