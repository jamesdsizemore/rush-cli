# Error Catalog (`rush error-catalog`)

## Overview
`rush error-catalog` is a deterministic security and quality tool that extracts raised and thrown exceptions from Python, TypeScript/JavaScript, and Rust source code. It synthesizes a structured [RFC 7807 Problem Details](https://datatracker.ietf.org/doc/html/rfc7807) error catalog. MCP exposes permission-gated Markdown export; current CLI does not expose an export flag despite stale command help prose.

**Status: planned correction — implementation [Phase 64, P64-18](../phase-plans/phase-64-runtime-correctness-and-safe-execution-plan.md#p64-18--source-aware-error-catalog-and-scope-aware-complexity-f22-f23).** Current TypeScript/JavaScript line regex can count commented throws and miss multiline throws. Treat those results as incomplete until packet acceptance passes.

## Classification
- **Category**: `security`
- **Maturity**: `real_adapter`
- **Tool Name**: `error-catalog`
- **FastMCP Tool**: `rush_error_catalog`

## Capabilities
1. **Python AST Parsing**: Traverses Python AST to inspect all `ast.Raise` nodes, extracting exception classes (e.g. `ValueError`, `NotFoundError`, `PermissionError`), constant string arguments, line numbers, and file paths.
2. **TypeScript/JavaScript Extraction**: Scans `.ts`, `.tsx`, `.js`, and `.jsx` files for `throw new <ErrorClass>(...)` and literal error throw constructs.
3. **Rust Error Extraction**: Scans `.rs` files for `enum <Name>Error`, `struct <Name>Error`, `Err(<Name>::...)`, and `panic!(...)` declarations.
4. **Deterministic RFC 7807 Mapping**: Maps each unique error definition to an RFC 7807 problem detail object:
   - `code`: Normalized screaming-snake identifier (e.g. `ERR_NOT_FOUND`, `ERR_VALIDATION`).
   - `status`: Inferred HTTP status code (e.g. 404 for NotFound, 403 for Forbidden/Permission, 422 for Validation/Value, 500 default).
   - `title`: Short human-readable title derived from the error class.
   - `type`: Canonical URI reference `https://rush-cli.org/errors/<slug>`.
   - `detail`: Default message or observed exception detail.
   - `occurrences`: Array of file locations and line numbers where the error is raised.
5. **Guarded Markdown Export**: MCP `export_path` generates Markdown documentation tables with `allow_artifact_write=true` and project-root containment. Current CLI has no `--export-path` or `--export-docs` option.

## CLI Usage

### Basic Scan
```bash
uv run rush error-catalog src/
```

### JSON Wire Format
```bash
uv run rush error-catalog src/ --json
```

### Exporting documentation catalog

Use MCP `export_path` with `allow_artifact_write=true`. No current CLI export spelling exists.

## FastMCP Usage
```json
{
  "name": "rush_error_catalog",
  "arguments": {
    "path": "src/",
    "export_path": null,
    "allow_artifact_write": false
  }
}
```

## Canonical Result Schema
```json
{
  "tool": "error-catalog",
  "engine": "error-catalog",
  "engine_version": "1.0.0",
  "status": "ok",
  "duration_ms": 12,
  "summary": "error-catalog: cataloged 4 unique RFC 7807 error types (12 occurrences across 8 files)",
  "findings": [
    {
      "path": "src/api/auth.py",
      "line": 45,
      "column": 1,
      "rule": "error-catalog",
      "rule_id": "ERR_UNAUTHORIZED",
      "severity": "info",
      "message": "UnauthorizedError: Invalid token provided"
    }
  ],
  "raw": {
    "catalog": [
      {
        "code": "ERR_UNAUTHORIZED",
        "class_name": "UnauthorizedError",
        "status": 401,
        "title": "UnauthorizedError",
        "type": "https://rush-cli.org/errors/err-unauthorized",
        "detail": "Invalid token provided",
        "occurrences": [
          {
            "path": "src/api/auth.py",
            "line": 45,
            "message": "Invalid token provided"
          }
        ]
      }
    ],
    "total_unique_errors": 1,
    "total_occurrences": 1
  }
}
```
