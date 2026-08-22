# Security & Supply Chain Protection

Security shouldn't be an afterthought that only happens once a year during an external audit. In high-velocity development, security checks need to happen continuously as code is written.

Rush provides defense-in-depth across code privacy, secret detection, dependency vulnerabilities, and open-source license compliance.

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

## Phantom Package Defense (Phase 43)
`rush hallu-guard` validates all import statements in your project against Python's standard library and installed distribution metadata, blocking supply-chain risks from unvetted AI hallucinations.
