# Error Catalog (`rush error-catalog`)

## Overview
`rush error-catalog` is a deterministic security and quality tool that extracts raised and thrown exceptions from Python and TypeScript/JavaScript source code. It synthesizes a structured [RFC 7807 Problem Details](https://datatracker.ietf.org/doc/html/rfc7807) error catalog and provides permission-gated Markdown documentation exports.

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
5. **Guarded Markdown Export**: Generates Markdown documentation tables. Writing export files requires explicit `--allow-artifact-write` permission and enforces path containment within the project root.

## CLI Usage

### Basic Scan
```bash
rush error-catalog src/
```

### JSON Wire Format
```bash
rush error-catalog src/ --json
```

### Exporting Documentation Catalog
```bash
rush error-catalog src/ --export-path docs/errors.md --allow-artifact-write
```

## FastMCP Usage
```json
{
  "name": "rush_error_catalog",
  "arguments": {
    "path": "src/",
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
