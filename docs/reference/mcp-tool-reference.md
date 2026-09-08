# MCP tool reference

## `rush_continuity` provider resume

The `provider_resume` operation accepts a checkpoint name and supported provider ID and returns the canonical continuity `ToolResult`. It has CLI/MCP parity for permission, bounded projection, states, and output suppression. It executes fixed-loopback OmniRoute after permission and semantic response validation and `9router_cli` through a fixed-local Codex bridge with a process-only key and no model argument; Z.AI is deferred.

## `rush_continuity`

Arguments: project `path`; `operation` (`save`, `list`, `restore`); optional checkpoint `name`, `files`, and `allow_cache_write`. The result is canonical JSON, with denied writes and absent checkpoints represented by `status: "skipped"`.

`rush mcp serve` registers each catalog tool as `rush_<name>` using the same Python tool objects as the CLI. Tool names include hyphens where the command does, for example `rush_semantic-drift` and `rush_ai-eval`.

## Common result

Every tool returns canonical `ToolResultV1` data (`schema_version: "1.0.0"`) documented in [Result reference](result-reference.md), featuring canonical finding severities (`info`, `warning`, `error`). Service operations (such as stdio protocol initializations) remain unwrapped JSON-RPC protocol frames. A missing optional engine is a structured `skipped` result, not an installation request.

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
rush_get_patch, rush_apply_fix, rush_session_context, rush_memory,
rush_guard, rush_token, rush_sync, rush_hygiene, rush_codegraph,
rush_bundle, rush_hotspots, rush_governance, rush_hook, rush_score,
rush_error_catalog, rush_license_matrix, rush_iam_audit
```

## AI Agent Remediation & Safety Tools (Phases 29–40)

- `rush_get_patch`: Returns unified diff for a finding.
- `rush_apply_fix`: Safely applies validated unified diffs with path containment and protected file shielding (Control 7).
- `rush_session_context`: Retrieves multi-turn evaluation history framed in `<rush_session_memory>` XML tags.
- `rush_memory` (Phase 61): `MemoryTool`'s `ask`/`write`/`promote`/`list`/`recall`/`maintain` operations over the unified `TypedArtifactStore`; returns `ToolResultV1` with `status="skipped"` for denied/absent cases, matching the `rush_session_context` precedent — same registration path (`ALL_TOOLS`/`TOOL_SPECS`), not a different shape.
- `rush_guard`: Validates shell command safety and confines path traversal.
- `rush_token`: Fast BPE token counting and AST outline compression.
- `rush_codegraph`: Explores polyglot Code Property Graph and extracts verbatim symbol slices.
- `rush_score`: Computes 6-pillar composite quality scores and generates SARIF/SVG artifacts.


## Polyglot Quality & Security Tools (Phase 50a)

- `rush_error_catalog`: Statically extracts exceptions across Python AST, TypeScript, and Rust, mapping to RFC 7807 problem details.
- `rush_license_matrix`: Audits dependencies across `pyproject.toml`, `package.json`, and `Cargo.toml` for copyleft risk.
- `rush_iam_audit`: Parses multi-cloud SDK calls (AWS/GCP/Azure) and Terraform wildcard permissions to synthesize minimal IAM policies.

## Protocol guarantees

- stdio only; no HTTP/SSE listener.
- stdout is JSON-RPC only.
- NDJSON diagnostics go to stderr.
- engine subprocess stdin is detached (`stdin=DEVNULL`) so it cannot consume MCP frames.
- the client-provided process environment must preserve required Windows/runtime variables.

See [MCP client setup](../integrations/mcp-client-setup.md) and [MCP development](../developer/mcp-development.md).

### `rush_provenance_ai`
Audits AI code attribution via Git trailers and shallow history check at `<path>`.

### `rush_dead_asset`
Scans unreferenced assets at `<path>`, calculates space savings, and generates manifests.

### `rush_pr_synthesize`
Synthesizes semantic PR markdown card with risk tiering and CODEOWNERS routing.

### `rush_attest`
Generates in-toto Statement v1 SLSA provenance draft at `<path>`.

### `rush_mem_profile`
Performs static resource lifecycle audit and dynamic memory sampling.

### `rush_cold_start`
Performs static import analysis and dynamic `-X importtime` audit.

### `rush_offline_review`
Runs air-gapped local ONNX review model at `<path>`.

### `rush_benchmark`
Compares performance samples against baseline thresholds at `<path>`.
