# Engine directory

An **engine** is an optional helper executable Rush knows how to call. Rush does not install engines. Applicability is based on file extensions and project markers; an absent engine produces `skipped` with an install hint.

Python install commands work on Windows, macOS, and Linux inside an appropriate Python environment. npm commands are cross-platform when Node/npm is installed. For standalone binaries, use the upstream project's release instructions for your platform; Rush's catalog intentionally says `install ...` rather than inventing an unverified package-manager command.

## Python and JavaScript/TypeScript

| Engine | What / who | Commands | Catalog install hint | Applicability and recovery |
|---|---|---|---|---|
| Ruff (`ruff`) | Python lint and format | `lint`, `format` | `pip install ruff` | `.py/.pyi`, `pyproject.toml`; verify `ruff --version`. |
| ESLint (`eslint`) | JS/TS lint | `lint` | `npm install -g eslint` | JS/TS extensions, `package.json`; project config may be required. Prefer project-local install when team versions matter. |
| Prettier (`prettier`) | JS/TS/data formatting | `format` | `npm install -g prettier` | JS/TS/JSON/YAML/Markdown and `package.json`; verify project configuration. |
| pytest (`pytest`) | Python tests | `test` | `pip install pytest` | Python project marker; install project test dependencies too. |
| Vitest (`vitest`) | JS/TS tests | `test` | `npm install -D vitest` | JS/TS and `package.json`; verify `npx vitest --version`. |
| pip-audit (`pip-audit`) | Python dependency advisories | `security` | `pip install pip-audit` | `pyproject.toml`/`requirements.txt`; lock/install metadata must be usable. |
| npm audit (`npm-audit`, binary `npm`) | npm dependency advisories | `security` | ships with npm | `package.json`; requires npm and appropriate lock/dependency metadata. |
| mypy (`mypy`) | Python types | `typecheck` | `pip install mypy` | Python files/project; project plugins/types may be needed. |
| TypeScript (`tsc`) | JS/TS types | `typecheck` | `npm install -D typescript` | JS/TS and `package.json`; normally needs `tsconfig.json`. |
| Vulture (`vulture`) | Python dead code | `dead` | `pip install vulture` | Python files/project; treat findings as candidates. |
| Knip (`knip`) | JS/TS unused files/exports/deps | `dead` | `npm install -D knip` | JS/TS project; configure framework entry points to reduce false positives. |
| Radon (`radon`) | Python complexity metrics | `complexity` | `pip install radon` | Python files; metrics are evidence, not an automatic design verdict. |
| jscpd (`jscpd`) | JS/TS duplication | `complexity` | `npm install -D jscpd` | JS/TS project; generated trees are excluded by Rush collectors. |
| sloppylint (`sloppylint`) | Python code-noise heuristics | `slop` | `pip install sloppylint` | Python files; JS/TS may use a built-in fallback. Do not infer authorship. |

## Content and infrastructure

| Engine | What / who | Command | Catalog install hint | Applicability and recovery |
|---|---|---|---|---|
| markdownlint-cli (`markdownlint`) | Markdown rules | `markdown` | `npm install -D markdownlint-cli` | `.md/.mdx`; Rush uses owned contained config rather than custom rules. |
| Actionlint (`actionlint`) | GitHub Actions workflows | `actions` | `install actionlint` | `.github/workflows`; download an upstream release for Windows/macOS/Linux and verify `actionlint -version`. |
| Spectral (`spectral`) | YAML/OpenAPI rules | `yaml` | `npm install -D @stoplight/spectral-cli` | `.yml/.yaml`; remote `$ref` is rejected. |
| SQLFluff (`sqlfluff`) | SQL lint | `sql` | `pip install sqlfluff` | `.sql`; dialect/config requirements can cause engine errors. |
| djLint (`djlint`) | HTML/Jinja templates | `templates` | `pip install djlint` | `.html/.jinja/.j2`; feasibility-gated maturity. |
| Hadolint (`hadolint`) | Dockerfile lint | `containerfile` | `install hadolint` | Dockerfile/Containerfile; use an official platform binary/package and verify `hadolint --version`. |
| TFLint (`tflint`) | Terraform lint | `iac` | `install tflint` | `.tf`/`.terraform`; use official install for your OS. Rush avoids implicit plugin setup. |
| Checkov (`checkov`) | Terraform policy checks | `iac` | `pip install checkov` | `.tf`; Rush uses local Terraform-only JSON mode with downloads/external modules disabled and an allowlisted environment. |

## Supply chain and workflow

| Engine | What / who | Command | Catalog install hint | Applicability and recovery |
|---|---|---|---|---|
| OSV-Scanner (`osv-scanner`) | Multi-ecosystem advisories | `security` | `install osv-scanner` | Known lockfiles (`poetry.lock`, `package-lock.json`, `Cargo.lock`, `go.sum`, etc.); use official platform distribution. |
| Gitleaks (`gitleaks`) | Secret patterns | `secrets` | `install gitleaks` | Repository-wide; use official release/package. Normalized messages redact values. |
| cdxgen (`cdxgen`) | CycloneDX SBOM | `sbom` | `npm install -g @cyclonedx/cdxgen` | Catalog-only surface; verify safe artifact behavior before adoption. |
| Commitlint (`commitlint`) | Conventional Commit messages | `commit-msg` | `npm install -D @commitlint/cli` | Optional workflow helper; generated CLI currently lacks message input. |
| semantic-drift (`semantic-drift`) | Experimental UI intent checks | `semantic-drift` | configure a local .NET or Playwright target | Browser runtime candidate; requires explicit browser and slow consent and is not runnable through current CLI options. |

## Missing-engine experience

```json
{"tool":"typecheck","engine":"mypy","status":"skipped","summary":"mypy executable not found", ...}
```

Install only if that check is part of your project policy. Then launch Rush from the same environment and verify the binary directly. Desktop MCP clients often have a different `PATH` from an interactive shell; use absolute paths or environment configuration when needed.
