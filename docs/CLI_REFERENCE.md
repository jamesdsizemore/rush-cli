# CLI reference

Use `rush --help` and `rush COMMAND --help` as the generated source of truth. Global options are `--version`, `--log-level debug|info|warn|error`, and `--help`. `RUSH_LOG_LEVEL` sets the log-level default.

## Which command should I run?

```text
Need a quick maintainability pass? -> review
Need source style/correctness?      -> lint / format --check / typecheck
Need confidence from tests?        -> test, then evidence/advanced checks
Need dependency/secret evidence?   -> security / secrets / sbom
Need project-file checks?          -> markdown / yaml / sql / templates / containerfile / iac / actions
Need workflow inspection?          -> commit-msg / ci / release
```

## Common syntax and options

Every catalog path command takes `PATH` and `--json`. `review` also takes `--llm`, `--use-graft`, and repeatable `--changed-file`; `format` also takes `--check`.

```bash
rush COMMAND PATH [--json]
rush review PATH [--llm] [--use-graft] [--changed-file RELATIVE_PATH]... [--json]
rush format PATH [--check] [--json]
rush mcp serve
```

`PATH` must exist. Human output is the default; `--json` returns the canonical result. Most commands do not modify files. The exception is `format` without `--check`, which can invoke formatter write modes; use version control and inspect the diff.

## Core code-quality commands

| Command | Purpose / when | Optional helpers | Results and modification |
|---|---|---|---|
| `review PATH` | Deterministic Python heuristics before review or after edits. | Optional local Graft with `--use-graft`; `--llm` is a no-call stub; repeat `--changed-file` for target-contained scope only. | `ok`/`warn`; read-only; no Git-diff inference. |
| `lint PATH` | Source linting. | Ruff, ESLint; best-effort language adapters. | May `fail` on findings; read-only. |
| `format PATH --check` | Verify formatter conformance. | Ruff format, Prettier. | Check-only with `--check`; omit only when you intentionally allow formatting. |
| `test PATH` | Run applicable project tests. | pytest, Vitest. | `fail` on test failures; test code may have project-defined side effects. |
| `security PATH` | Dependency vulnerability checks. | pip-audit, npm audit, OSV integration where routed. | Read-only normalization; scanner behavior depends on installed tool. |
| `typecheck PATH` | Static type checks. | mypy, TypeScript `tsc`. | Read-only; missing helper skips. |
| `dead PATH` | Find unused code. | Vulture, Knip. | Advisory/read-only. |
| `complexity PATH` | Complexity/duplication evidence. | Radon, jscpd. | Metrics/findings; read-only. |
| `slop PATH` | Deterministic code-noise signals. | sloppylint plus JS/TS fallback. | Advisory; no authorship inference. |

## Project-file and infrastructure commands

| Command | Checks | Optional helper | Modification |
|---|---|---|---|
| `markdown` | Markdown rules | markdownlint-cli | none |
| `yaml` | YAML/OpenAPI under owned rules; remote references blocked | Spectral | none |
| `sql` | SQL lint | SQLFluff | none |
| `templates` | HTML/Jinja templates | djLint | none |
| `containerfile` | Dockerfile/Containerfile | Hadolint | none |
| `iac` | Terraform lint/policy | TFLint, Checkov | none |
| `actions` | GitHub Actions YAML | Actionlint | none |

## Supply-chain commands

| Command | Purpose | Notes |
|---|---|---|
| `secrets PATH` | Scan for secret-like material with Gitleaks. | Values are redacted from normalized findings; rotate real exposed credentials. |
| `sbom PATH` | Generate a CycloneDX SBOM through cdxgen. | Catalog-only maturity. CLI does not expose internal output/overwrite controls; verify before adoption. |

## Capabilities and planning

`rush capabilities PATH --json` reads local project markers, allowed `rush.toml` tables, known local report filenames, and `PATH`; it does not execute, install, or version-probe an engine. States distinguish configured, installed, applicable, missing, and blocked. `rush plan PATH --profile default|nonbrowser --json` expands that inventory deterministically with report/engine prerequisites; browser-runtime capabilities remain absent from `nonbrowser`.

## Test-confidence and advanced commands

`coverage`, `pbt`, `flaky`, `contract`, `snapshot`, `mutation`, `fuzz`, and `load` are local report importers: pass the report file as `PATH`. They never launch an engine, contact a target, repeat tests, or write/accept a baseline. `visual` and `e2e` remain skipped until the browser-evidence phase. `semantic-drift` remains experimental and requires browser plus slow consent.

Do not invent undocumented CLI options. See [Permissions](safety/permissions.md) and [MCP tool reference](reference/mcp-tool-reference.md).

## Workflow commands

| Command | Current behavior |
|---|---|
| `commit-msg PATH` | The underlying implementation validates a supplied Conventional Commit message, but the generated CLI exposes no `--message`; ordinary CLI use therefore evaluates the empty default and is not a complete user surface. Never rewrites history. |
| `ci PATH` | Inspects local workflow files. Does not contact a remote CI provider or read credentials. |
| `release PATH` | Creates a dry-run inventory/plan. Generated CLI exposes no publish flags; no tag, release, or upload is created. |

## MCP

`rush mcp serve` starts a local stdio server and blocks until stdin closes. It opens no HTTP port. See [MCP overview](integrations/mcp-overview.md).

## Result and exit behavior

`ok` and `skipped` exit 0; `warn` and `fail` exit 1; `error` exits 2. A mandatory check that skips must be rejected by inspecting JSON, because exit code 0 alone is intentionally non-fatal. See [Result reference](reference/result-reference.md).
