# Tool catalog

The catalog contains 32 user-visible tools. **Maturity matters:** a listed tool can be a real adapter, feasibility-gated route, importer/guarded placeholder, catalog-only contract, or experimental browser runtime.

| Tool | Category | Maturity | Engines / behavior |
|---|---|---|---|
| `review` | quality | real adapter | deterministic local heuristics; optional explicit Graft; LLM no-call stub |
| `lint` | quality | feasibility gated | Ruff, ESLint, best-effort language routes |
| `format` | quality | feasibility gated | Ruff format, Prettier; `--check` is safe mode |
| `test` | test | feasibility gated | pytest, Vitest, language routes |
| `security` | security | real adapter | pip-audit, npm audit, OSV routing |
| `typecheck` | quality | feasibility gated | mypy, tsc |
| `dead` | quality | feasibility gated | Vulture, Knip |
| `complexity` | quality | feasibility gated | Radon, jscpd |
| `slop` | quality | feasibility gated | sloppylint, deterministic JS/TS fallback |
| `markdown` | quality | real adapter | markdownlint-cli with contained config |
| `actions` | quality | real adapter | Actionlint with external child integrations disabled |
| `yaml` | quality | real adapter | Spectral with owned rules and remote-ref block |
| `sql` | quality | real adapter | SQLFluff |
| `templates` | quality | feasibility gated | djLint |
| `containerfile` | quality | real adapter | Hadolint |
| `iac` | security | real adapter | TFLint then contained Checkov |
| `secrets` | security | real adapter | Gitleaks with normalized redaction |
| `sbom` | security | catalog only | cdxgen implementation exists; incomplete CLI controls |
| `coverage` | test | importer | coverage.py JSON, LCOV, or Cobertura report; never runs tests |
| `pbt` | test | importer | seeded local property-test JSON report; never executes tests |
| `flaky` | test | importer | local JUnit duplicate-case evidence; never repeats tests |
| `contract` | test | importer | local Pact summary; never contacts provider or broker |
| `snapshot` | test | importer | local comparison report; never accepts or writes a baseline |
| `visual` | test | guarded placeholder | no visual baseline acceptance by default |
| `mutation` | test | importer | local mutation summary; never runs a mutation engine |
| `e2e` | test | guarded placeholder | requires browser consent; CLI flag absent |
| `fuzz` | test | importer | local seeded fuzz summary; never builds or runs a fuzzer |
| `load` | test | importer | local load summary; never contacts a target |
| `semantic-drift` | test | browser runtime | experimental; browser + slow consent; CLI flags absent |
| `commit-msg` | workflow | feasibility gated | local Conventional Commit validation; CLI message option absent |
| `ci` | workflow | real adapter | local workflow inspection only |
| `release` | workflow | real adapter | dry-run local artifact inventory; publication unavailable |

Generated help is authoritative for options. See [CLI reference](reference/cli-reference.md), [Engine directory](reference/engine-directory.md), and [Permissions](safety/permissions.md).
