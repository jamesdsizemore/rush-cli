# Checking project files

Source code is only part of a repository. Rush has focused, non-rewriting checks for common project files:

```bash
rush markdown .
rush yaml .
rush sql .
rush templates .
rush containerfile .
rush iac .
rush actions .
rush ci .
```

- **Markdown** uses contained markdownlint, Lychee, Vale, Alex, and No-Jargon for prose hygiene and link integrity.
- **YAML** uses Spectral rules and Zally for API schemas with remote `$ref` blocking.
- **SQL** uses SQLFluff, Atlas (migration safety), and Squawk (PostgreSQL lock analysis).
- **Templates** uses djLint and HTML-Validate for W3C HTML validation.
- **Containerfiles** uses Hadolint and Dockle for CIS Docker benchmarks.
- **IaC** targets Terraform and Kubernetes through TFLint, Checkov, Kubeconform, Terrascan, Kube-score, Conftest, Polaris, and KubeLinter.
- **Actions** checks GitHub workflow YAML with Actionlint while disabling external shellcheck/pyflakes integrations.
- **CI** inspects local workflow files and checks OpenSSF Scorecard supply chain posture.

A missing helper yields `skipped`. Install only the checks your repository adopts. Exact engine boundaries are in the [Engine directory](../reference/engine-directory.md).
