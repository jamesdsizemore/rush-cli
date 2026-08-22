# Specification: SLSA Level 3 Cryptographic Build Attestation

## 1. Overview
`SLSAAttestationGenerator` (`src/rush/tools/attest.py`) creates in-toto JSON provenance statements detailing git commit digests, builder metadata, and artifact SHA256 hashes to guarantee complete supply chain integrity.

## 2. CLI & FastMCP Reference
* `rush attest [--out <FILE>]`
* `rush_attest_generate(artifact_path="")`
