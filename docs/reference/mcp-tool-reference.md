# MCP tool reference

## `rush_continuity` provider resume

The `provider_resume` operation accepts a checkpoint name and supported provider ID and returns the canonical continuity `ToolResult`. It has CLI/MCP parity for permission, bounded projection, states, and output suppression. It executes fixed-loopback OmniRoute after permission and semantic response validation and `9router_cli` through a fixed-local Codex bridge with a process-only key and no model argument; Z.AI is deferred.

## `rush_continuity`

Arguments: project `path`; `operation` (`save`, `list`, `restore`); optional checkpoint `name`, `files`, and `allow_cache_write`. The result is canonical JSON, with denied writes and absent checkpoints represented by `status: "skipped"`.

`uv run rush mcp serve` registers each catalog tool through the shared invocation executor. Catalog hyphens become underscores in MCP names, for example `rush_semantic_drift` and `rush_ai_eval`.

## Common result

Catalog tools return canonical `ToolResultV1` data (`schema_version: "1.0.0"`) documented in [Result reference](result-reference.md). Service operations remain JSON-RPC protocol frames. Some legacy custom MCP tools still return specialized strings or dictionaries; MCP discovery and each tool's generated schema are authoritative. A missing optional engine in a catalog tool is a structured `skipped` result.

## Inputs

Catalog wrappers commonly accept `path`, permission flags, and tool-specific options. Defaults are false for permission flags. Inspect the generated MCP schema before invocation; not every tool accepts every field.

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

## Current tool names

At baseline `997b56e`, live `build_server().list_tools()` returns 74 registered tools. Use MCP discovery for the exact current names and input schemas. Fixed copied lists are not completeness evidence because catalog registration and named custom registration can change independently.

## AI Agent Remediation & Safety Tools (Phases 29–40)

- `rush_get_patch`: Returns unified diff for a finding.
- `rush_apply_fix`: Applies validated unified diffs through the current patch path. Invocation-owned restoration remains required by [P64-04](../phase-plans/phase-64-runtime-correctness-and-safe-execution-plan.md#p64-04--real-isolated-patch-application-f05-f2425-f43); do not treat current broad cleanup as safe promotion evidence.
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
