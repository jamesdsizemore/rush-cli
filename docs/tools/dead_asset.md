# Unreferenced Asset & Dead Media Scanner (`rush dead-asset`)

## Overview
`rush dead-asset` scans the repository for static images, media, and font files that are not referenced in application source code, stylesheets, templates, or documentation. It calculates potential disk space savings, generates deterministic SHA-256 audit manifests, and enforces a strictly read-only guarantee (zero file deletions or mutations).

## Classification
- **Category**: `quality`
- **Maturity**: `real_adapter`
- **Tool Name**: `dead-asset`
- **FastMCP Tool**: `rush_dead_asset`

## Capabilities
1. **Potential Disk Space Savings**: Calculates the aggregate size in bytes of all unreferenced assets, reporting potential savings in summary, raw metrics, and metadata.
2. **Multi-Format Asset Discovery**: Scans for static assets including `.png`, `.jpg`, `.jpeg`, `.svg`, `.gif`, `.webp`, `.ttf`, `.woff`, `.woff2`, `.ico`, `.bmp`, `.tiff`, `.mp4`, `.webm`, excluding `.git`, `.venv`, `.rush`, `node_modules`, `dist`, and `build`.
3. **Comprehensive Source Cross-Referencing**: Searches across Python, TypeScript, JavaScript, HTML, CSS, SCSS, Markdown, JSON, YAML, and XML files to detect asset references by filename or relative path.
4. **Deterministic Audit Manifest**: Computes SHA-256 digests and file sizes for every asset, tagging each as `referenced` or `unreferenced`.
5. **Contained Manifest Export**: MCP `export_manifest` requires explicit `allow_artifact_write=true` and enforces workspace containment. Current CLI has no `--export-manifest` option.
6. **Strictly Read-Only Invariant**: Does not modify, unlink, or delete any files in the repository.

## CLI Usage

### Audit Scan (Read-Only)
```bash
uv run rush dead-asset .
```

### JSON Wire Format
```bash
uv run rush dead-asset . --json
```

### Exporting a manifest

Current CLI exposes no manifest-export flag. Use MCP `export_manifest` with `allow_artifact_write=true` after reviewing the contained destination.

## FastMCP Usage
```json
{
  "name": "rush_dead_asset",
  "arguments": {
    "path": ".",
    "export_manifest": ".rush/asset-manifest.json",
    "allow_artifact_write": true
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
  "summary": "dead-asset: scanned 10 assets, found 2 unreferenced (45.2 KB potential savings). Strictly read-only analysis.",
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
  "metrics": {
    "total_assets": 10,
    "dead_assets_count": 2,
    "potential_savings_bytes": 46234
  },
  "raw": {
    "total_assets": 10,
    "dead_assets_count": 2,
    "dead_assets": [
      "static/img/old_banner.png",
      "static/fonts/legacy.woff"
    ],
    "potential_savings_bytes": 46234
  },
  "metadata": {
    "manifest": [],
    "potential_savings_bytes": 46234,
    "execution": {}
  }
}
```
