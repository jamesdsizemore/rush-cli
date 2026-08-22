# MCP tool reference

`rush mcp serve` registers each catalog tool as `rush_<name>` using the same Python tool objects as the CLI. Tool names include hyphens where the command does, for example `rush_semantic-drift` and `rush_ai-eval`.

## Common result

Every tool returns canonical ToolResult data documented in [Result reference](reference/result-reference.md). A missing optional engine is a structured `skipped` result, not an installation request.

## Inputs

Most tools accept:

```json
{
  "path": "/absolute/path/to/project",
  "allow_network": false,
  "allow_download": false,
  "allow_cache_write": false,
  "allow_build": false,
  "allow_slow": false,
  "allow_artifact_write": false,
  "allow_browser": false
}
```

Special callable options include:

- `rush_review`: `path`, `use_llm=false`, `use_graft=false`, `changed_files=[]`.
- `rush_format`: `path`, check-mode options.
- `rush_commit-msg`: `path`, `message=""`.
- `rush_sbom`: `path`, `output=null`, `overwrite=false`.
- `rush_snapshot`: `path`, `accept=false`, `report_path=null`.
- `rush_ai-eval`: `path`, standard permissions.

## Complete tool names

```text
rush_review, rush_lint, rush_format, rush_test, rush_security,
rush_typecheck, rush_dead, rush_complexity, rush_slop,
rush_markdown, rush_actions, rush_yaml, rush_sql, rush_templates,
rush_containerfile, rush_iac, rush_secrets, rush_sbom,
rush_coverage, rush_pbt, rush_flaky, rush_contract, rush_snapshot,
rush_visual, rush_mutation, rush_e2e, rush_fuzz, rush_load,
rush_semantic-drift, rush_commit-msg, rush_ci, rush_release,
rush_codeql, rush_ai-eval, rush_tdd, rush_fix, rush_doctor,
rush_guard, rush_token, rush_sync, rush_hygiene, rush_codegraph,
rush_bundle, rush_hotspots, rush_governance, rush_hook, rush_score
```

## Protocol guarantees


- stdio only; no HTTP/SSE listener.
- stdout is JSON-RPC only.
- NDJSON diagnostics go to stderr.
- engine subprocess stdin is detached (`stdin=DEVNULL`) so it cannot consume MCP frames.
- the client-provided process environment must preserve required Windows/runtime variables.

See [MCP client setup](integrations/mcp-client-setup.md) and [MCP development](developer/mcp-development.md).

## Phase 41–43 FastMCP Tool Additions

* **`rush_session_save(name, files)`**: Save developer context snapshot to `.rush/sessions/`.
* **`rush_ship_clean(dry_run=False)`**: Clean scratch directories and build caches before release.
* **`rush_ship_env()`**: Audit codebase environment variable usage against `.env.example`.
* **`rush_ship_gate()`**: Run 7-vector pre-flight release readiness cockpit.
* **`rush_token_outline(path, focus_symbol="")`**: Generate token-efficient AST skeleton outline of a code file.
* **`rush_context_retrieve(chunk_hash)`**: Retrieve uncompressed content from CCR chunk store by hash.
* **`rush_hallu_guard(path="")`**: Audit code imports against installed packages and stdlib.
* **`rush_context_mistakes_check()`**: Check git revert history for past mistakes and anti-patterns.

* **`rush_context_pack(path, symbol="", budget=4000)`**: Pack graph-pruned context outline under a strict token budget.

* **`rush_context_gain_stats()`**: Return real-time token economy savings, compression ratios, and dollar metrics as JSON.

* **`rush_blast_radius(path, depth=5)`**: Calculate downstream transitive blast radius for a changed file.
* **`rush_arch_guard()`**: Validate codebase against clean architecture layer boundaries.

* **`rush_test_heal(target, runs=5)`**: Diagnose flaky test race conditions in isolated sandbox and propose fixes.
* **`rush_api_diff(base="main")`**: Detect breaking public API contract changes against base Git ref.
