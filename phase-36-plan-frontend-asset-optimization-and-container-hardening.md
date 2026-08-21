# Phase 36 Implementation Plan: Modern Frontend, Asset Optimization & Container Hardening

> **Phase:** 36 of 40  
> **Milestone:** Frontend Assets, Containers & Production Hardening  
> **Status:** Ready for Implementation  
> **Target Version:** Rush v0.8.0  
> **ADR References:** [ADR-0024: Hardened Subprocess Git Invocations](docs/adr/0024-hardened-subprocess-git-invocations.md)  
> **Pinned Dependencies:** `mcp==1.28.1`, Python 3.12 Standard Library (`struct`, `zlib`, `xml.etree.ElementTree`)  
> **Discovered External Engines:** `hadolint` (Dockerfile linter), `svgo` (SVG optimizer)

---

## 1. Objective & Scope

Frontend and full-stack web applications frequently suffer from bloated multimedia assets (uncompressed PNGs/JPEGs), insecure SVGs with embedded XSS payloads (`<script>`, `onload=`), unoptimized Dockerfile layer ordering that destroys caching, and raw binary assets committed directly into Git without Git LFS pointers.

Phase 36 provides production-grade asset and container hardening:
1. **Multimedia Asset & Web Performance Auditor (`rush asset-audit`)**: Pure Python header parser (`struct`, `zlib`) extracting image dimensions, color depths, and compression ratios to flag unoptimized assets exceeding performance budgets.
2. **SVG Security Sanitizer & XSS Guard (`rush svg-sanitize`)**: XML AST sanitizer stripping malicious JavaScript, external entity injections (XXE), and untrusted remote URI references.
3. **Dockerfile Layer Cache & Security Linter (`rush docker-lean`)**: Hardens Dockerfiles by ensuring non-root user execution, combining `RUN` instructions to minimize layers, and discovering `hadolint`.
4. **Git LFS Pointer & Large Binary Enforcer (`rush git-lfs-audit`)**: Scans repository blobs and commits to ensure files over 5 MB use Git LFS pointers and `.gitattributes` rules.

---

## 2. Token Reduction & Optimization Strategy (`rtk`, `graft`, `context-mode`)

- **`rtk` (Asset Summary Metrics)**: Instead of emitting raw binary dumps or verbose XML ASTs, `rush asset-audit` emits compact summary metrics (e.g. `logo.png: 4.2 MB -> convert to WebP / saves 85%`).
- **`graft` (Dockerfile AST Extraction)**: Parses Dockerfile directives into structured AST instructions (`FROM`, `RUN`, `COPY`, `USER`) to identify caching anti-patterns.
- **`context-mode` (Sanitization Diffs)**: `rush svg-sanitize` displays only the removed unsafe XML attributes/tags in compact diff format.

---

## 3. File Rosters

### Target Implementation Files
- `src/rush/tools/asset_audit.py` (New: Pure Python binary header image inspector)
- `src/rush/tools/svg_sanitize.py` (New: XML AST security sanitizer and XSS scrubber)
- `src/rush/tools/docker_lean.py` (New: Dockerfile layer optimizer and `hadolint` wrapper)
- `src/rush/git/lfs_audit.py` (New: Large file and `.gitattributes` enforcer)
- `src/rush/cli.py` (Modified: Register `rush asset-audit`, `rush svg-sanitize`, `rush docker-lean`, `rush git-lfs-audit`)
- `src/rush/mcp_server.py` (Modified: FastMCP endpoints)
- `src/rush/catalog.py` (Modified: Tool specs)

### Test & Fixture Files
- `tests/test_asset_audit.py` (New: Image header dimension extraction for PNG, JPEG, WebP, GIF)
- `tests/test_svg_sanitize.py` (New: XSS injection vectors, `<script>` removal, XXE stripping)
- `tests/test_docker_lean.py` (New: Non-root user checks, multi-stage build optimization)
- `tests/test_git_lfs_audit.py` (New: Large file detection and missing `.gitattributes` rules)
- `tests/fixtures/assets/malicious.svg` (New: Synthetic malicious SVG fixture)
- `tests/fixtures/docker/Dockerfile.bad` (New: Unoptimized Dockerfile fixture)

---

## 4. Test-Driven Development (TDD) Workflow & Test Suite Design

### 4.1 RED Phase (Author Tests First)

```python
# tests/test_svg_sanitize.py
def test_svg_sanitizer_removes_malicious_script_tags():
    unsafe_svg = '<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script><circle cx="50" cy="50" r="40"/></svg>'
    sanitized, removed_elements = sanitize_svg_content(unsafe_svg)
    assert "<script>" not in sanitized
    assert "<circle" in sanitized
    assert len(removed_elements) == 1

# tests/test_docker_lean.py
def test_docker_lean_flags_missing_user_directive():
    dockerfile_content = """
FROM node:20-alpine
WORKDIR /app
COPY . .
RUN npm install
CMD ["node", "server.js"]
"""
    findings = analyze_dockerfile(dockerfile_content)
    assert any(f.rule_id == "missing_non_root_user" for f in findings)
    assert any(f.rule_id == "unpinned_base_image" for f in findings)
```

### 4.2 GREEN Phase (Implementation)
Implement `src/rush/tools/asset_audit.py`, `src/rush/tools/svg_sanitize.py`, `src/rush/tools/docker_lean.py`, and `src/rush/git/lfs_audit.py`.

### 4.3 REFACTOR Phase
Ensure image header parsing handles truncated files without raising unhandled exceptions, returning structured error findings instead.

---

## 5. Structured Error Logging & Diagnostics Contract

Emit structured NDJSON to `sys.stderr`:

```json
{"timestamp": "2026-08-21T07:40:00Z", "phase": 36, "tool": "rush_svg_sanitize", "event": "xss_removed", "file": "public/icon.svg", "tag": "script"}
{"timestamp": "2026-08-21T07:40:01Z", "phase": 36, "tool": "rush_docker_lean", "event": "layer_warning", "file": "Dockerfile", "rule": "missing_non_root_user"}
{"timestamp": "2026-08-21T07:40:02Z", "phase": 36, "tool": "rush_git_lfs_audit", "event": "large_file_untracked_lfs", "file": "models/weights.bin", "size_bytes": 104857600}
```

---

## 6. Step-by-Step Task Specifications

### Task 36.1: Multimedia Asset Inspector (`src/rush/tools/asset_audit.py`)
```python
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
from rush.tools.base import ToolResult, Finding

@dataclass(frozen=True)
class AssetMetadata:
    path: str
    format: str
    size_bytes: int
    width: int | None
    height: int | None
    suggested_action: str | None

def audit_multimedia_assets(target_dir: Path, max_size_kb: int = 500) -> ToolResult:
    """Scan image assets and flag unoptimized binaries exceeding budget."""
    ...
```

### Task 36.2: XML AST SVG Sanitizer (`src/rush/tools/svg_sanitize.py`)
Parse SVGs with `xml.etree.ElementTree`, remove active elements (`<script>`, `<foreignObject>`), strip event handlers (`onload`, `onclick`), and enforce clean XML output.

### Task 36.3: Dockerfile Layer Optimizer (`src/rush/tools/docker_lean.py`)
Lint Dockerfile instructions for caching efficiency, non-root user execution, and pinned base image digests. Discover `hadolint` if available.

### Task 36.4: Git LFS Pointer Enforcer (`src/rush/git/lfs_audit.py`)
Scan repository files exceeding size threshold (default 5 MB) to verify Git LFS pointer format and `.gitattributes` tracking.

### Task 36.5: CLI & FastMCP Registrations
Register all 4 tools in CLI and FastMCP server.

---

## 7. Semantic Drift Review & Verification Gate

1. **Pure Python Fallback**: Asset header parsing must function 100% offline without Pillow or external C libraries.
2. **Safe XML Parser**: Prevent XML bomb / Billion Laughs attacks with depth-limited XML tree traversal.
3. **Doc Parity**: Synchronize and verify `/docs`.
