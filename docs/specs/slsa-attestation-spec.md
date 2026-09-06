# Specification: SLSA v1.0 Provenance Draft Cryptographic Build Attestation

## 1. Overview
`SLSAAttestationGenerator` (`src/rush/tools/attest.py`) creates in-toto JSON provenance statements detailing git commit digests, builder metadata, and artifact SHA256 hashes to guarantee complete supply chain integrity.

## 2. CLI & FastMCP Reference
* `rush attest [--out <FILE>]`
* `rush_attest_generate(artifact_path="")`

## Remediation & Honest Provenance (R-013)
Local executions produce unsigned provenance drafts with `assurance: "unsigned_draft"`. Artifact digests are computed directly from files in `dist/` or target files, avoiding fraudulent Level 3 claims.
### Truthful Provenance & In-Toto Specification (Phase 59)
Defines Statement v1 and SLSA Provenance v1 predicate schemas, unsigned draft semantics, strict duplicate-key rejection, and optional DSSE Ed25519 verification policy.
