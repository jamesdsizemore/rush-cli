# Media Optimization & Security Tool (`rush media-opt`)

## Overview
`rush media-opt` audits repository media files for security vulnerabilities (SVG active script and event handler injection), layout stability (CLS missing image dimensions in HTML/templates), and raster compression optimization per D50-15.

**Status: planned correction — implementation [Phase 64, P64-16](../phase-plans/phase-64-runtime-correctness-and-safe-execution-plan.md#p64-16--spdx-expressions-and-decoded-svg-safety-f18-f19).** Current SVG checks can miss entity-encoded script schemes. Do not treat a clean result as proof decoded attributes are safe until packet acceptance passes.

## Usage

### CLI
```bash
uv run rush media-opt PATH [--allow-artifact-write] [--json]
```

### MCP
- **Tool Name:** `rush_media_opt`
- **Parameters:** required `path` (str), required opaque `options` object, and common permission booleans defaulting to false. Current MCP schema exposes no top-level `sanitize` or `optimize` parameter.

## Capabilities
1. **SVG Security**: Detects `<script>`, inline event handlers (`onload`, `onclick`), and `javascript:` URIs. Current CLI exposes no `--sanitize` or `--optimize` option.
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
- Artifact writes require explicit `--allow-artifact-write`; current CLI does not expose the documented sanitize/optimize selectors.
