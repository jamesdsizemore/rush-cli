# Your first ten minutes with Rush

This walkthrough proves that Rush is installed, runs a safe local review, and can return machine-readable output.

## 1. Confirm the command

From a Rush checkout:

```bash
uv run rush --help
```

You should see `review`, `lint`, `format`, `test`, `security`, focused checks, and `mcp`. The list is generated from the implementation, so use it as the current command inventory.

## 2. Review a small target

```bash
uv run rush review src
```

`review` reads Python files and applies deterministic heuristics for large files, TODO density, missing docstrings, naming, and configured scaffold markers. It does not rewrite the files.

A clean result is `ok`. Advisory findings produce `warn`. Read the file, line, rule, severity, and message; then decide whether the finding needs a code change or a documented exception.

## 3. Ask for JSON

```bash
uv run rush review src --json
```

The object contains `tool`, `engine`, `engine_version`, `status`, `duration_ms`, `summary`, `findings`, and `raw`; some tools add `metrics`, `artifacts`, or `metadata`. See [Result reference](../reference/result-reference.md).

## 4. Try an optional-engine command

```bash
uv run rush lint src --json
```

If Ruff is available and Python files apply, Rush runs it. If the engine is absent, expect `status: "skipped"`. That is a useful explanation, not an automatic project failure.

## What to do next

- Build a before-PR routine with [Everyday workflow](../user-guide/everyday-workflow.md).
- Configure a project only after the defaults are understood: [Configuration cookbook](../reference/configuration-cookbook.md).
- Connect an assistant with [MCP client setup](../integrations/mcp-client-setup.md).
