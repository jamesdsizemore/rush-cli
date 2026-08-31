# Media Optimization & Security Tool (`rush media-opt`)

## Overview
`rush media-opt` audits repository media files for security vulnerabilities (SVG active script and event handler injection), layout stability (CLS missing image dimensions in HTML/templates), and raster compression optimization per D50-15.

## Usage

### CLI
```bash
rush media-opt [PATH] [--sanitize] [--optimize] [--allow-artifact-write] [--json]
```

### MCP
- **Tool Name:** `rush_media_opt`
- **Parameters:**
  - `path` (str): Target directory or media file.
  - `sanitize` (bool, optional): Strip active script and event handler tags from SVGs.
  - `optimize` (bool, optional): Compress PNG/WebP raster images via Pillow.
  - `allow_artifact_write` (bool): Required when `sanitize=True` or `optimize=True` writes changes.

## Capabilities
1. **SVG Security**: Detects `<script>`, inline event handlers (`onload`, `onclick`), and `javascript:` URIs. Strips malicious tags when run with `--sanitize` and `--allow-artifact-write`.
2. **CLS Layout Audit**: Identifies `<img>` elements missing explicit `width` and `height` attributes or aspect ratios in HTML/JSX/Vue/Svelte templates.
3. **Pillow Optimization**: Re-encodes raster images with lossless/optimized compression when output is smaller.

## Output Schema
Emits canonical `ToolResult`:
```json
{
  "tool": "media-opt",
  "engine": "media-opt",
  "engine_version": "1.0.0",
  "status": "ok",
  "duration_ms": 22,
  "summary": "media-opt: Audited 15 media/markup file(s), 0 finding(s)",
  "findings": [],
  "metrics": {
    "svg_files_count": 5,
    "markup_files_count": 6,
    "image_files_count": 4,
    "findings_count": 0,
    "sanitized_svg_count": 0
  }
}
```

## Security & Permissions
- Read-only audit by default.
- Modifying SVGs (`--sanitize`) or raster images (`--optimize`) requires explicit `--allow-artifact-write` permission.
