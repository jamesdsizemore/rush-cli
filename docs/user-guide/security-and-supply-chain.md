# Security and supply chain

Rush separates three jobs so their evidence is clear.

## Dependency and SAST security

```bash
rush security . --json --export-html artifacts/security.html
```

Rush routes dependency scanning to pip-audit, npm audit, OSV-Scanner, Trivy, and Grype. Static analysis and privacy scanning run via Semgrep, Bearer, and Horusec. Agent hook security and prompt injection audits route to **Medusa**. Web standards and accessibility audits route to Pa11y, OWASP ZAP, Deadfinder, and A11yWatch. Container layer benchmarks run via Dockle.

## Secret scanning

```bash
rush secrets . --json
```

Rush scans for secrets and sensitive keys via Gitleaks, TruffleHog, Secretlint, detect-secrets, and Safe-Env. Secret values are redacted as `[REDACTED]` from normalized messages. Rotate real exposed credentials immediately.

## AI and LLM Evaluation

```bash
rush ai-eval . --json
```

Evaluates LLM prompts, jailbreaks, agent workflows, and safety guardrails using Promptfoo, Garak, DeepEval, and NeMo Guardrails.

## CodeQL evidence & SARIF Export

```bash
rush codeql path/to/codeql.sarif --json
rush security . --export-sarif artifacts/security.sarif
```

Imports existing CodeQL SARIF 2.1.0 reports for offline normalization, or runs the local CodeQL CLI under `--allow-build`. Supports direct SARIF 2.1.0 generation via `--export-sarif`.

## Software bill of materials (SBOM) & Offline Trust Attestation

```bash
rush sbom . --json
rush release . --json
```

Generates SBOM and audits license copyleft risk using cdxgen, ScanCode, GUAC, and pip-licenses. Verifies offline cryptographic quality and security certificates via **Cejel** and automated semantic releases. Overwriting existing artifacts requires `--allow-artifact-write`. See [Safety](../safety/safety-overview.md).
