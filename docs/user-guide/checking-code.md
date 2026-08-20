# Checking code

## Python

Install only the helpers you require:

```bash
uv add --dev ruff pytest pip-audit mypy vulture radon refurb fawltydeps flake8-bugbear tach pyrefly aislop
rush tdd .
rush review .
rush lint .
rush format . --check
rush typecheck .
rush dead .
rush complexity .
rush slop .
rush test .
rush security .
```

Rush detects Python through `pyproject.toml`, `setup.py`, and Python file extensions. `review` itself examines Python files with local heuristics. `typecheck` supports both `mypy` and high-speed `pyrefly`. `complexity` evaluates both cyclomatic metrics (`radon`) and modular architectural boundaries (`tach`).

## JavaScript and TypeScript

```bash
npm install --save-dev eslint prettier vitest typescript knip jscpd @biomejs/biome ts-prune stylelint
rush lint .
rush format . --check
rush typecheck .
rush dead .
rush complexity .
rush test .
rush security .
```

Rush detects a JavaScript/TypeScript project through `package.json` and relevant extensions. The repository's engine configuration still matters; for example, ESLint may skip when its configuration is absent.

## Polyglot & Multi-Language Quality

For polyglot repositories, Rush routes structural and AST checks across languages:
- **AST Pattern Matching**: `globstar`, `ast-grep`, and `comby` run syntactic AST pattern matching across 20+ languages.
- **AI Anti-Slop**: `aislop` scans 10 languages for AI boilerplate, stub routines, and repetitive comments.
- **Continuous Architecture & Token Metrics**: `sentrux` and `clines` evaluate codebase decay, cyclomatic spikes, and LLM context costs.
- **Polyglot Linting**: `megalinter` orchestrates linters across polyglot trees.
- **Modernization**: `refurb` (Python idioms), `biome` (JS/TS), `depcruise` (module architecture), `scaphandre` (energy profiling).

## Other ecosystems

Rush recognizes markers for Go, Rust, Ruby, JVM, Swift, PHP, .NET, Elixir, Dart, Scala, and Nix. Consult [Compatibility](../reference/compatibility.md) and [Engine Directory](../reference/engine-directory.md) for full engine rosters.
