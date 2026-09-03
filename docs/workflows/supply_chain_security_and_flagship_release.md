# Workflow: Supply Chain Security & Flagship Release

This workflow coordinates pre-release security auditing, error cataloging, dependency compliance, and build attestation.

## 1. Cataloging Application Exceptions (Phase 50a)
Extract and verify all error pathways and synthesize RFC 7807 problem details:
```bash
rush error-catalog src/ --export-docs docs/errors.md --allow-artifact-write
```

## 2. Auditing Open-Source Dependency Licenses (Phase 50a)
Audit all dependencies across manifests (`pyproject.toml`, `package.json`, `Cargo.toml`) for copyleft contamination risks:
```bash
rush license-matrix . --allowed-licenses "MIT,Apache-2.0,BSD-3-Clause,BSD-2-Clause,ISC"
```

## 3. Auditing Cloud IAM Permissions & Terraform (Phase 50a)
Statically analyze cloud SDK calls and detect wildcard actions in Terraform configurations:
```bash
rush iam-audit . --output reports/iam-policy.json --allow-artifact-write
```

## 4. Pruning Dead Assets & Verifying Hashes (Phase 50b)
Identify and remove unreferenced media or font files:
```bash
rush dead-asset . --operation audit
```

## 5. Generating Cryptographic Build Attestation (Phase 50c)
Produce in-toto Statement v1 / SLSA Provenance v1 unsigned drafts with SHA-256 digests for release artifacts:
```bash
rush attest . --target-artifact dist/app-0.1.0-py3-none-any.whl --export-path dist/app-0.1.0.intoto.json --allow-artifact-write
```

## 6. Synthesizing PR Release Cards (Phase 50b)
Synthesize structured pull request release markdown cards from Git diff and test evidence:
```bash
rush pr-synthesize . --base-ref main --export-card reports/release-card.md --allow-artifact-write
```
