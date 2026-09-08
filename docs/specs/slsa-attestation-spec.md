# Specification: SLSA v1.0 Provenance Draft Cryptographic Build Attestation

## 1. Overview
`AttestationTool` and the compatibility `SLSAAttestationGenerator` (`src/rush/tools/attest.py`) create in-toto JSON provenance statements containing source, builder and artifact digests. A local unsigned statement does not guarantee supply-chain integrity or establish a SLSA assurance level.

## 2. CLI & FastMCP Reference
* `rush attest PATH --artifact-path ARTIFACT --out OUTPUT --allow-artifact-write`
* `rush_attest_generate(artifact_path="")`

## Remediation & Honest Provenance (R-013)
Local executions produce unsigned provenance drafts with `assurance: "unsigned_draft"`. Artifact digests are computed directly from files in `dist/` or target files, avoiding fraudulent Level 3 claims.
### Truthful Provenance & In-Toto Specification (Phase 59)
Defines Statement v1 and SLSA Provenance v1 predicate schemas, unsigned draft semantics, strict duplicate-key rejection, and optional DSSE Ed25519 verification policy.
