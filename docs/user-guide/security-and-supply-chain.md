# Security & Supply Chain Protection

## Provider-continuation boundary

Provider continuation is an explicit local process invocation with no shell, no package installation, no profile mutation, and no retained provider output. Permission is per invocation. `9router_cli` uses a fixed local Codex bridge, child-process-only `RUSH_9ROUTER_API_KEY`, and no model argument; unsupported router routes are skipped rather than guessed or redirected.

Security shouldn't be an afterthought that only happens once a year during an external audit. In high-velocity development, security checks need to happen continuously as code is written.

Rush provides defense-in-depth across code privacy, secret detection, dependency vulnerabilities, and open-source license compliance.

Session handoff uses the same posture: explicit cache-write permission, local redacted receipts, and no provider credential persistence. A failure reference exposes a fingerprint and redacted error or a tombstone, never a patch body.

---

## 1. Catching Leaked Secrets & API Keys (`rush secrets`)

Accidentally committing an AWS secret access key, Stripe token, or database password to a public repository can lead to immediate compromise.

```bash
rush secrets .
```

### What Rush Checks:
- High-entropy API tokens (OpenAI, GitHub, AWS, Stripe, Anthropic).
- Hardcoded passwords and private certificates (`.pem`, `.key`).
- Unredacted credentials in staged git changes.

### Automatic Output Redaction:
Whenever Rush encounters a secret in any log, finding, or terminal output, it automatically redacts the sensitive value as `[REDACTED]` to prevent secondary exposure in log collectors or AI prompt transcripts.

---

## 2. Auditing Vulnerable Dependencies (`rush security`)

Most modern applications rely on hundreds of third-party open-source packages. When a known vulnerability (CVE) is discovered in a package you use, you need to know immediately.

```bash
rush security .
```

### What Rush Invokes:
- **Python**: Coordinates `pip-audit` to check packages against the PyPA advisory database.
- **Node.js**: Coordinates `npm audit` to check `package-lock.json`.
- **Containers**: Coordinates `Trivy` and `Grype` to scan base container images.
- **Static Security (SAST)**: Coordinates `Semgrep` and `Bearer` to find SQL injection, Cross-Site Scripting (XSS), and unauthenticated API endpoints.

---

## 3. Generating Software Bills of Materials & License Checks (`rush sbom`)

When shipping software to enterprise customers or open-source communities, you often need to prove which libraries you use and ensure you aren't accidentally violating restrictive copyleft licenses (like AGPL in proprietary commercial software).

```bash
# Generate a CycloneDX SBOM
rush sbom . -o bom.json --allow-artifact-write
```

Rush coordinates `cdxgen` and `ScanCode` to audit dependencies, scan license terms, and generate standard CycloneDX and SPDX documents.

---

## 4. Evaluating AI & LLM Safety (`rush ai-eval`)

If your project builds with LLM prompts, agent workflows, or RAG systems, you need to test against prompt injection and jailbreaks:

```bash
rush ai-eval .
```

Rush coordinates `Promptfoo`, `Garak`, and `DeepEval` to test that your AI system follows safety policies and refuses malicious prompts.

---

## Next Steps

- Learn about monorepos and advanced checks in [Advanced Checks & Monorepos](advanced-checks.md).
- Discover solutions to common issues in [Troubleshooting Guide](troubleshooting.md).

## 5. Polyglot Error Cataloging (`rush error-catalog`)
Extracts and documents exception pathways across Python, TypeScript, and Rust without leaking sensitive runtime details:
```bash
rush error-catalog src/ --export-docs docs/errors.md --allow-artifact-write
```

## 6. Copyleft Dependency Risk Matrix (`rush license-matrix`)
Audits dependencies across `pyproject.toml`, `package.json`, and `Cargo.toml` against an allowlist of permissive SPDX licenses:
```bash
rush license-matrix . --allowed-licenses "MIT,Apache-2.0,BSD-3-Clause"
```

## 7. Cloud IAM Policy Synthesis & Terraform Wildcards (`rush iam-audit`)
Statically extracts multi-cloud SDK operations and verifies that Terraform configurations do not contain dangerous wildcard actions (`*`):
```bash
rush iam-audit . --export-path policy.json --allow-artifact-write
```

## Phantom Package Defense (Phase 43)
`rush hallu-guard` validates all import statements in your project against Python's standard library and installed distribution metadata, blocking supply-chain risks from unvetted AI hallucinations.

## 8. AI Code Provenance & Attribution (`rush provenance-ai`)
Audit Git commit history for AI generation trailers and track code survival:
```bash
rush provenance-ai .
```

## 9. Honest Build Provenance Drafts (`rush attest`)
Generate an in-toto Statement v1 binding real distribution artifact digests from `dist/`:
```bash
rush attest . --export-path artifacts/provenance.json --allow-artifact-write
```

### Running Custom Plugins Securely (Phase 56)
When using community plugins or scripts from git repositories, Rush requires explicit trust authorization before execution. Run `rush trust plugin <name>` to approve the plugin closure.

## Secure AI Review and Network Boundaries (Phase 57)

Rush protects your code and credentials during AI reviews:
- Only approved HTTPS origins receive requests.
- Redirects to untrusted hosts are immediately blocked.
- Results are marked as AI-generated only when authentic model responses are received.
