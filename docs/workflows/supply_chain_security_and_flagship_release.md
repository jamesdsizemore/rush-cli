# Workflow: Supply Chain Security & Flagship Release

This workflow coordinates pre-release security auditing, error cataloging, dependency compliance, and build attestation.

## 1. Cataloging Application Exceptions (Phase 50a)
Extract and verify all error pathways and synthesize RFC 7807 problem details:
```bash
rush error-catalog src/ --json
```

## 2. Auditing Open-Source Dependency Licenses (Phase 50a)
Audit all dependencies across manifests (`pyproject.toml`, `package.json`, `Cargo.toml`) for copyleft contamination risks:
```bash
rush license-matrix . --json
```

## 3. Auditing Cloud IAM Permissions & Terraform (Phase 50a)
Statically analyze cloud SDK calls and detect wildcard actions in Terraform configurations:
```bash
rush iam-audit . --output reports/iam-policy.json --allow-artifact-write
```

## 3a. AI Code Attribution & Provenance (Phase 50b)
Audit commit history trailers and track code attribution before release:
```bash
rush provenance-ai .
```

## 4. Scanning Dead Assets & Calculating Savings (Phase 50b)
Identify and remove unreferenced media or font files:
```bash
rush dead-asset . --json
```

## 5. Generating Cryptographic Build Attestation (Phase 50c)
Produce in-toto Statement v1 / SLSA Provenance v1 unsigned drafts with SHA-256 digests for release artifacts:
```bash
rush attest . --artifact-path dist/app-0.1.0-py3-none-any.whl --out dist/app-0.1.0.intoto.json --allow-artifact-write
```

## 5a. Performance Baseline & Regression Check (Phase 50c)
Compare execution samples against recorded baselines in `.rush/baselines.json`:
```bash
rush benchmark check .
```

## 6. Synthesizing PR Release Cards (Phase 50b)
Synthesize structured pull request release markdown cards from Git diff and test evidence:
```bash
rush pr-synthesize . --json
```
### Flagship Release & Provenance Workflow (Phase 59)
End-to-end workflow executing package build, checksum manifest, unsigned draft attestation, and mandatory mypy release gate.
