# Checking code

## Python

Install only the helpers you require:

```bash
uv add --dev ruff pytest pip-audit mypy vulture radon
rush review .
rush lint .
rush format . --check
rush typecheck .
rush dead .
rush complexity .
rush test .
rush security .
```

Rush detects Python through `pyproject.toml`, `setup.py`, and Python file extensions. `review` itself examines Python files with local heuristics.

## JavaScript and TypeScript

```bash
npm install --save-dev eslint prettier vitest typescript knip jscpd
rush lint .
rush format . --check
rush typecheck .
rush dead .
rush complexity .
rush test .
rush security .
```

Rush detects a JavaScript/TypeScript project through `package.json` and relevant extensions. The repository's engine configuration still matters; for example, ESLint may skip when its configuration is absent.

## Mixed repositories

Run the same command at the repository root. Applicable engines run in stable order and Rush aggregates findings. One missing engine can coexist with another engine's result; use JSON provenance on findings when you need to identify the producer.

## Other ecosystems

Rush recognizes markers for Go, Rust, Ruby, JVM, Swift, PHP, .NET, Elixir, Dart, Scala, and Nix. Current support is best-effort and check-only. Consult [Compatibility](../reference/compatibility.md) and do not assume every language's preferred tool is implemented.
