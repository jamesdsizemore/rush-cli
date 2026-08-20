# Rush user guide

Rush checks a project with relevant quality tools already available in your environment and reports one consistent result. This guide is the complete beginner manual; focused chapters live under [`user-guide/`](user-guide/index.md).

## Welcome to Rush

Use Rush before a pull request, after an AI-assisted coding session, while introducing CI, or while cleaning up an unfamiliar repository. It helps answer: Is the code obviously unfinished? Does it lint and format? Do tests pass? Are dependency or secret findings present? Are project files and workflows healthy?

Rush is not a replacement for specialized tools. It is the safe front door to them.

## Before you begin

Install Python 3.12 and uv, then follow [Installation](getting-started/installation.md). Optional checkers are installed separately. Missing helpers produce `skipped`; Rush never installs them for you.

## Your first Rush check

```bash
uv run rush review .
```

`review` is local and deterministic. A line such as `review: 2 heuristic finding(s)` means two rules matched. Use the path and line to inspect the source. `info` is context; `warn` deserves review; `error` represents a strong finding or execution problem depending on status.

## The everyday workflow

After finishing a feature:

```bash
rush review .
rush lint .
rush format . --check
rush test .
rush security .
```

- `review`: catches maintainability signals without modifying code. Good: `ok`; `warn`: inspect advisory findings.
- `lint`: runs applicable linters. Good: `ok`; `fail`: fix reported rules; `skipped`: install the named engine only if needed.
- `format --check`: asks whether files match formatter rules without rewriting. Good: `ok`; failure means run and review your project's formatter.
- `test`: runs applicable test engines. Good: `ok`; `fail`: inspect failed test findings/output.
- `security`: checks supported dependency manifests. Good: `ok`; `fail`: evaluate and remediate reported advisories.

See [Everyday workflow](user-guide/everyday-workflow.md) for the full story.

## Understanding results

- `ok`: the command completed and found no blocking issue.
- `warn`: completed with advisory findings.
- `fail`: completed and found a failed check.
- `error`: Rush or an engine could not complete correctly.
- `skipped`: nothing applicable, required evidence absent, permission absent, or an optional engine missing.

A missing engine is not the same as a passing check. Decide whether your policy requires that engine. See [Understanding results](user-guide/understanding-results.md).

## Use Rush for common jobs

- Python, JS/TS, mixed repositories: [Checking code](user-guide/checking-code.md)
- Markdown, YAML, SQL, Dockerfiles, Actions: [Checking project files](user-guide/checking-project-files.md)
- Dependencies, secrets, SBOM: [Security and supply chain](user-guide/security-and-supply-chain.md)
- Tests and evidence: [Testing confidence](user-guide/testing-confidence.md)

## Optional advanced checks

Advanced checks are permission-sensitive. Rush supports dual modes across test confidence and quality verification:
1. **Imported Mode**: Pass existing local report files (`coverage`, `mutation`, `fuzz`, `load`, `contract`, `snapshot`, `codeql`) for instant offline normalization.
2. **Executed Mode**: Run native test engines under explicit permission flags (`--allow-slow`, `--allow-network`, `--allow-build`, `--allow-browser`, `--allow-artifact-write`).

See [Advanced checks](user-guide/advanced-checks.md) and [Permissions](safety/permissions.md).

## Use Rush with an AI coding assistant

MCP lets a compatible assistant ask the local Rush process to inspect your project. Configure `rush mcp serve` as a stdio command, then ask: “Review the files I changed,” “Run relevant tests,” or “Tell me which checker is missing.” See [Working with AI agents](user-guide/working-with-ai-agents.md).

## Configure Rush for my project

A `rush.toml` file stores a small set of project settings. Rush finds the nearest file while walking upward from the target and stops at the Git root. Current fields are documented in [Configuration reference](reference/configuration-reference.md). Only `review.max_file_lines`, `review.use_graft`, and direct lint engine arguments have verified consumers; other parsed fields are forward-facing and should not be presented as enforced policy.

## When something goes wrong

Use [Troubleshooting](user-guide/troubleshooting.md) for symptom → reason → exact fix, and [FAQ](user-guide/faq.md) for common decisions.
