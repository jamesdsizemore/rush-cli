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

- **Markdown** uses a contained markdownlint configuration and does not discover custom rules.
- **YAML** uses package-owned Spectral rules and blocks remote `$ref` input before execution.
- **SQL** can use SQLFluff when installed.
- **Templates** can use djLint when installed.
- **Containerfiles** use Hadolint when installed.
- **IaC** currently targets Terraform through TFLint and a contained Checkov invocation.
- **Actions** checks GitHub workflow YAML with Actionlint while disabling external shellcheck/pyflakes integrations.
- **CI** inspects local workflow files only; it does not contact GitHub or use credentials.

A missing helper yields `skipped`. Install only the checks your repository adopts. Exact engine boundaries are in the [Engine directory](../reference/engine-directory.md).
