# Unreferenced Asset & Dead Media Pruner (`rush dead-asset`)

## Overview
`rush dead-asset` scans the repository for static images, media, and font files that are not referenced in application source code, stylesheets, templates, or documentation. It generates cryptographic SHA-256 audit manifests and executes guarded pruning with explicit `--allow-artifact-write` permission gating.

## Classification
- **Category**: `quality`
- **Maturity**: `real_adapter`
- **Tool Name**: `dead-asset`
- **FastMCP Tool**: `rush_dead_asset`

## Capabilities
1. **Multi-Format Asset Discovery**: Scans for static assets including `.png`, `.jpg`, `.jpeg`, `.svg`, `.gif`, `.webp`, `.ttf`, `.woff`, `.woff2`, `.ico`, `.bmp`, `.mp4`, `.webm`, excluding `.git`, `.venv`, `.rush`, `node_modules`, `dist`, and `build`.
2. **Comprehensive Source Cross-Referencing**: Searches across Python, TypeScript, JavaScript, HTML, CSS, SCSS, Markdown, JSON, YAML, and XML files to detect asset references by filename or relative path.
3. **Deterministic Audit Manifest**: Computes SHA-256 digests and file sizes for every asset, tagging each as `referenced` or `unreferenced`.
4. **Guarded Pruning**:
   - Requires explicit `--allow-artifact-write` permission.
   - Re-validates the SHA-256 digest of each candidate immediately prior to deletion to protect against concurrent modifications or replacement attacks.
   - Enforces workspace containment to prevent deletion outside the repository root.

## CLI Usage

### Audit Scan (Read-Only)
```bash
rush dead-asset .
```

### JSON Wire Format
```bash
rush dead-asset . --json
```

### Exporting Manifest
```bash
rush dead-asset . --export-manifest .rush/asset-manifest.json --allow-artifact-write
```

### Guarded Prune
```bash
rush dead-asset . --prune --allow-artifact-write
```

## FastMCP Usage
```json
{
  "name": "rush_dead_asset",
  "arguments": {
    "path": ".",
    "prune": false,
    "allow_artifact_write": false
  }
}
```

## Canonical Result Schema
```json
{
  "tool": "dead-asset",
  "engine": "dead-asset-scanner",
  "engine_version": "1.0.0",
  "status": "warn",
  "duration_ms": 25,
  "summary": "dead-asset: found 2 unreferenced assets out of 10 total assets.",
  "findings": [
    {
      "path": "static/img/old_banner.png",
      "line": 1,
      "column": 1,
      "rule": "dead-asset",
      "rule_id": "WARN_UNREFERENCED_ASSET",
      "severity": "warn",
      "message": "Unreferenced asset: static/img/old_banner.png (45210 bytes)",
      "fingerprint": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
    }
  ],
  "raw": {
    "total_assets": 10,
    "dead_assets_count": 2,
    "dead_assets": [
      "static/img/old_banner.png",
      "static/fonts/legacy.woff"
    ]
  },
  "metadata": {
    "total_assets": 10,
    "dead_assets_count": 2,
    "dead_assets": [
      "static/img/old_banner.png",
      "static/fonts/legacy.woff"
    ],
    "bytes_freed": 0,
    "pruned": false
  }
}
```
