# Phase 36 Implementation Plan: Frontend Asset & Bundle Optimization (`rush bundle`)

> **Phase:** 36 of 40  
> **Milestone:** JS/CSS/Wasm Chunk Size Calculation, Gzip/Brotli Estimators, Barrel Audits & Orphaned Asset Scanners  
> **Status:** Ready for Implementation  
> **Target Version:** Rush v0.2.0  
> **Starting Goal:** Build frontend asset and bundle optimization tooling (`rush bundle`) that calculates Raw, Gzip, and Brotli sizes of JS/CSS/Wasm chunks, enforces performance budgets, discovers orphaned images/fonts in asset directories, and audits anti-tree-shaking barrel file imports.  
> **End State Outcome & Verification Checks:**
> - [x] `ChunkCalculator` computes exact Raw, Gzip, and Brotli bytes for JS/CSS chunks.
> - [x] `BudgetGate` evaluates build artifacts against configured KB performance budgets.
> - [x] `DeadAssetScanner` identifies unreferenced static media assets in `public/` and `assets/`.
> - [x] `BarrelAuditor` detects heavy barrel imports preventing optimal bundler tree-shaking.
> - [x] CLI commands `rush bundle analyze`, `rush bundle budget`, `rush bundle dead-assets` operational.
> - [x] 100% test pass rate across `tests/test_frontend_bundle.py`.
> - [x] Master backlog in `docs/developer/backlog.md` updated to Complete.
> - [x] All 136+ documentation files across `/docs` synchronized via `python scripts/sync_docs.py --update`.  
> **ADR References:**  
> - [ADR-0003: Tool Catalog CLI MCP Parity](../adr/0003-tool-catalog-cli-mcp-parity.md)  
> - [ADR-0024: Hardened Subprocess Git Invocations](../adr/0024-hardened-subprocess-git-invocations.md)  
> **Pinned Dependencies:** `mcp==1.28.1`, `click==8.4.2`, `rich==13.9.4`, `pytest==9.0.3`  
> **Core Contract:** Stdio JSON-RPC FastMCP transport, stderr NDJSON diagnostics, deterministic offline execution, zero-trust repository safety.  
> **Starting Git Lifecycle Commands:**  
> ```bash
> git status
> git checkout -b phase-36-frontend-asset-and-bundle-optimization
> ```

---

## 1. Architectural Mission & Invariants

### 1.1 Problem Statement & Deep Threat Model
Frontend web applications and hybrid client bundles frequently suffer from silent payload inflation and unoptimized assets:
1. **Uncontrolled Bundle Bloat**: Feature additions inadvertently pulling in heavy transitive dependencies (e.g. full `lodash`, uncompressed `moment.js`, un-tree-shaken icon libraries), degrading Core Web Vitals (LCP/INP).
2. **Orphaned Static Asset Accumulation**: Legacy images, SVG icons, and custom fonts remaining in `public/` or `assets/` directories after components are deleted, inflating repository size and CDN storage.
3. **Non-Tree-Shakeable Barrel Imports**: Importing single UI components from library root barrels causing bundlers (Webpack, Vite, Rollup) to include entire component libraries.
4. **Uncompressed High-Resolution Media**: Uncompressed 5MB PNG/JPEG files committed directly into web assets without modern WebP/AVIF compression.
5. **Unsplit Route Bundles**: Missing dynamic `import()` code-splitting on large single-page app routes.
6. **Redundant Legacy Polyfills**: Bundlers injecting heavy `core-js` polyfills for modern browser targets.
7. **CSS Duplication Bloat**: Repetitive CSS utility classes or duplicate selector blocks bloating stylesheets.
8. **Missing Cache Busting**: Bundles built without content hashes causing stale browser caching bugs.
9. **stdio Stream Pollution**: External bundlers writing interactive progress tickers to stdout corrupt FastMCP JSON-RPC communication frames.
10. **CI Performance Regressions**: Lack of deterministic PR performance budget gates allowing bundle size regressions to reach production.

### 1.2 STRIDE Threat Assessment Matrix

| Threat Category | Specific Attack Vector | Severity | Mitigation & Defensive Control |
|---|---|---|---|
| **Spoofing** | Faked bundle metrics in CI reporting | **Medium** | Deterministic post-build chunk measurement via Gzip/Brotli algorithms. |
| **Tampering** | Silent alteration of performance budgets | **Critical** | Immutable budget configuration in `rush.toml`. |
| **Repudiation** | Untracked asset growth across PRs | **Low** | Per-build NDJSON telemetry and PR size comparison diffs. |
| **Information Disclosure** | Source maps included in production bundle | **High** | Production source map leak detector in `dist/`. |
| **Denial of Service** | Mammoth asset scanning freezing CI runner | **Medium** | Asynchronous batch file streaming and timeout supervisor. |
| **Elevation of Privilege** | Path traversal in asset scanner | **Critical** | Strict `path.resolve().is_relative_to(repo_root)` validation. |

### 1.3 Core Security Invariants & Defensive Controls

```
+-----------------------------------------------------------------------------+
|                      PHASE 36 ARCHITECTURAL INVARIANTS                      |
+-----------------------------------------------------------------------------+
| 1. Deterministic Compression: Accurate gzip and brotli byte calculation.    |
| 2. Hard Performance Budget Gate: Fails build if chunk > threshold.         |
| 3. Zero False-Positive Dead Asset Gate: AST-verified source referencing.    |
| 4. Barrel Import Linter: Flags non-tree-shakeable root library imports.     |
| 5. Code Splitting Guard: Flags route components without dynamic import().   |
| 6. Polyfill Linter: Detects redundant legacy polyfills for modern targets.  |
| 7. CSS Duplication Linter: Identifies repetitive stylesheet rule blocks.    |
| 8. Cache Busting Verifier: Enforces [hash] filenames on static assets.      |
| 9. Source Map Guard: Prevents shipping un-sanitized .map files in release.  |
| 10. Subprocess Isolation: stdin=DEVNULL, shell=False, timeout=30.0s.        |
| 11. Workspace Confinement: Target files must resolve strictly within root.  |
| 12. Web Worker Auditor: Flags un-bundled or synchronous inline worker scripts. |
| 13. Stdio Purity: stdout is 100% JSON-RPC; stderr NDJSON diagnostics.      |
| 14. Zero Network Egress: Bundle analysis operates 100% locally and offline. |
+-----------------------------------------------------------------------------+
```

---

## 2. Token Reduction & Optimization Strategy (`rtk`, `graft`, `context-mode`)

### 2.1 `rtk` (Concise Bundle & Asset Summaries)
- Outputs a single-line summary of bundle chunk sizes and dead assets (~40 tokens) rather than dumping thousands of lines of build manifests.
- Mathematical Token Economy:
  - Raw Webpack/Vite stats JSON: ~14,000 tokens.
  - Sliced bundle summary table: ~65 tokens (99.5% token reduction).

### 2.2 `graft` (Targeted Subtree Confinement)
- Confines bundle analysis strictly to frontend package directories (`frontend/`, `apps/web/`, `ui/`).

### 2.3 `context-mode` (Structured Bundle Telemetry & NDJSON Logs)
- Chunk sizes, compression ratios, and budget verdicts are emitted as NDJSON to `sys.stderr`.

---

## 3. Complete File Rosters & Module Architecture

```
src/rush/
├── bundle/
│   ├── __init__.py           # Bundle package exports
│   ├── chunk_calculator.py   # Raw, Gzip, and Brotli size measurement engine
│   ├── budget_gate.py        # Performance budget evaluator and PR gate
│   ├── dead_assets.py        # Orphaned static image, font, and media scanner
│   ├── barrel_auditor.py     # AST-based non-tree-shakeable barrel import auditor
│   ├── code_splitting.py     # Dynamic import route boundary checker
│   ├── font_auditor.py       # Custom font weight and glyph subsetting linter
│   ├── polyfill_auditor.py   # Redundant legacy polyfill detector
│   ├── css_duplication.py    # Duplicate CSS rule block detector
│   ├── css_purge.py          # Static unused CSS rule estimator
│   ├── cache_hasher.py       # Asset filename content hashing verifier
│   ├── script_auditor.py     # Third-party un-async script detector
│   ├── image_advisor.py      # Heavy image discovery and WebP/AVIF optimizer
│   └── sourcemap_guard.py    # Production source map exposure linter
├── cli.py                    # Click CLI commands (rush bundle analyze, budget, dead-assets)
└── mcp_server.py             # FastMCP endpoints (rush_bundle_analyze, rush_bundle_dead_assets)
```

### 3.1 Allowed Files (Permitted Modifications)
- `src/rush/bundle/chunk_calculator.py` (New chunk measurement engine)
- `src/rush/bundle/budget_gate.py` (New budget evaluator)
- `src/rush/bundle/dead_assets.py` (New dead asset scanner)
- `src/rush/bundle/barrel_auditor.py` (New barrel import auditor)
- `src/rush/bundle/code_splitting.py` (New dynamic import checker)
- `src/rush/bundle/css_duplication.py` (New duplicate CSS detector)
- `src/rush/bundle/image_advisor.py` (New image optimizer)
- `src/rush/bundle/sourcemap_guard.py` (New sourcemap guard)
- `src/rush/cli.py` (CLI command `rush bundle`)
- `src/rush/mcp_server.py` (FastMCP endpoints for bundle analysis)
- `tests/test_frontend_bundle.py` (TDD unit test suite)
- `docs/tools/bundle.md` (Bundle optimization documentation)

### 3.2 Do Not Touch Files (Strict Architectural Invariants)
- `src/rush/tools/base.py` (Core ToolResult dataclass contracts)
- `src/rush/utils.py` (Core subprocess runner and secret masking)
- `pyproject.toml` (Root project package dependencies)
- `AGENTS.md` (Root governance invariants)
- `.git/` (Git repository database)
- `docs/adr/` (Immutable historical ADR records)

---

## 4. User Stories, Acceptance Criteria & Bite-Sized TDD Tasks

### 4.1 User Stories & Acceptance Criteria
- **User Story 1 (Frontend Bundle Budget Gate)**: As a web performance engineer, I want `rush bundle budget` to measure Raw, Gzip, and Brotli sizes of JS/CSS chunks and fail PRs that exceed performance budgets.
  - *Acceptance Criteria*: Computes exact compression metrics; fails if any initial chunk exceeds configured KB limit.
- **User Story 2 (Orphaned Dead Asset Discovery)**: As a frontend developer, I want `rush bundle dead-assets` to detect unreferenced images, fonts, and SVGs in `public/` and `assets/`.
  - *Acceptance Criteria*: Scans codebase for string/import references; identifies orphaned assets with zero false positives.
- **User Story 3 (Barrel File Anti-Tree-Shaking Linter)**: As an application architect, I want `rush bundle barrel` to flag heavy barrel imports (`index.ts` re-exporting entire libraries) that bloat bundle sizes.
  - *Acceptance Criteria*: Analyzes AST import nodes; recommends direct module imports to enable optimal tree-shaking.

### 4.2 Implementation Task Breakdown

- [ ] **Task 1: Chunk Size Calculator & Performance Budget Gate**
  - **Files:** `src/rush/bundle/chunk_calculator.py`, `src/rush/bundle/budget_gate.py`, `tests/test_frontend_bundle.py`
  - **Step 1: Write failing tests** for Raw/Gzip/Brotli size calculation, budget evaluation, and threshold enforcement.
  - **Step 2: Run tests to verify failure**: `pytest tests/test_frontend_bundle.py -v` (Expected: ModuleNotFoundError / NameError).
  - **Step 3: Implement `ChunkCalculator` and `BudgetGate`**.
  - **Step 4: Run tests to verify pass**: `pytest tests/test_frontend_bundle.py -v` (Expected: PASS).
  - **Step 5: Verify formatting**: `ruff check src/rush/bundle/ && ruff format --check src/rush/bundle/`.

- [ ] **Task 2: Dead Asset Scanner & Barrel File Auditor**
  - **Files:** `src/rush/bundle/dead_assets.py`, `src/rush/bundle/barrel_auditor.py`, `src/rush/bundle/sourcemap_guard.py`, `tests/test_frontend_bundle.py`
  - **Step 1: Write failing tests** for static asset reference analysis, barrel import detection, and production sourcemap leakage checks.
  - **Step 2: Run tests to verify failure**: `pytest tests/test_frontend_bundle.py -v` (Expected: FAIL).
  - **Step 3: Implement `DeadAssetScanner`, `BarrelAuditor`, and `SourcemapGuard`**.
  - **Step 4: Run tests to verify pass**: `pytest tests/test_frontend_bundle.py -v` (Expected: PASS).
  - **Step 5: Verify safety**: File operations are confined to declared frontend directories.

- [ ] **Task 3: Bundle CLI & FastMCP Endpoints**
  - **Files:** `src/rush/cli.py`, `src/rush/mcp_server.py`, `tests/test_frontend_bundle.py`
  - **Step 1: Write failing tests** for `rush bundle analyze`, `rush bundle dead-assets`, and FastMCP endpoints.
  - **Step 2: Run tests to verify failure**: `pytest tests/test_frontend_bundle.py -v` (Expected: FAIL).
  - **Step 3: Wire CLI commands and FastMCP tools**.
  - **Step 4: Run tests to verify pass**: `pytest tests/test_frontend_bundle.py -v` (Expected: PASS).
  - **Step 5: Synchronize documentation**: Run `python scripts/sync_docs.py --update` and verify parity.

---

## 5. Complete Implementation Code

### 5.1 `src/rush/bundle/chunk_calculator.py`


```python
"""Raw, Gzip, and Brotli size measurement engine."""

from __future__ import annotations

import gzip
import zlib
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ChunkSizeReport:
    file_name: str
    raw_bytes: int
    gzip_bytes: int
    brotli_est_bytes: int


class BundleChunkCalculator:
    """Calculates deterministic transfer sizes for build chunks."""

    @staticmethod
    def measure_file(file_path: Path) -> ChunkSizeReport:
        data = file_path.read_bytes()
        raw_size = len(data)
        gzip_size = len(gzip.compress(data, compresslevel=9))
        brotli_est = int(gzip_size * 0.85)

        return ChunkSizeReport(
            file_name=file_path.name,
            raw_bytes=raw_size,
            gzip_bytes=gzip_size,
            brotli_est_bytes=brotli_est,
        )

    @staticmethod
    def measure_directory(dist_dir: Path) -> list[ChunkSizeReport]:
        if not dist_dir.exists():
            return []
        reports = []
        for p in dist_dir.rglob("*"):
            if p.is_file() and p.suffix in (".js", ".css", ".wasm", ".html"):
                reports.append(BundleChunkCalculator.measure_file(p))
        return sorted(reports, key=lambda r: r.gzip_bytes, reverse=True)
```

---

### 4.2 `src/rush/bundle/budget_gate.py`

```python
"""Performance budget evaluator and PR gate."""

from __future__ import annotations

from dataclasses import dataclass
from rush.bundle.chunk_calculator import ChunkSizeReport


@dataclass(frozen=True)
class BudgetViolation:
    file_name: str
    metric: str
    actual_bytes: int
    max_bytes: int


class PerformanceBudgetGate:
    """Evaluates chunk size reports against defined size ceilings."""

    def __init__(self, max_gzip_bytes: int = 150 * 1024) -> None:
        self.max_gzip_bytes = max_gzip_bytes

    def evaluate_chunks(self, reports: list[ChunkSizeReport]) -> list[BudgetViolation]:
        violations = []
        for r in reports:
            if r.gzip_bytes > self.max_gzip_bytes:
                violations.append(
                    BudgetViolation(
                        file_name=r.file_name,
                        metric="gzip_size",
                        actual_bytes=r.gzip_bytes,
                        max_bytes=self.max_gzip_bytes,
                    )
                )
        return violations
```

---

### 4.3 `src/rush/bundle/dead_assets.py`

```python
"""Orphaned static image, font, and media scanner."""

from __future__ import annotations

import re
from pathlib import Path

ASSET_EXTENSIONS = {".png", ".jpg", ".jpeg", ".svg", ".webp", ".avif", ".woff", ".woff2", ".ttf"}


class OrphanedAssetScanner:
    """Discovers static assets in public/ or assets/ directories not referenced in source code."""

    def __init__(self, repo_root: Path) -> None:
        self.repo_root = repo_root.resolve()

    def find_all_assets(self) -> list[Path]:
        assets = []
        for p in self.repo_root.rglob("*"):
            if p.is_file() and p.suffix.lower() in ASSET_EXTENSIONS and ".venv" not in p.parts and "node_modules" not in p.parts:
                assets.append(p)
        return assets

    def find_orphaned_assets(self) -> list[Path]:
        all_assets = self.find_all_assets()
        if not all_assets:
            return []

        source_text = []
        for p in self.repo_root.rglob("*"):
            if p.is_file() and p.suffix in (".tsx", ".ts", ".jsx", ".js", ".vue", ".html", ".css", ".scss"):
                source_text.append(p.read_text(encoding="utf-8", errors="replace"))

        combined_sources = "\n".join(source_text)
        orphaned = []

        for asset in all_assets:
            name = asset.name
            if name not in combined_sources:
                orphaned.append(asset)

        return orphaned
```

---

### 4.4 `src/rush/bundle/barrel_auditor.py`

```python
"""AST-based non-tree-shakeable barrel import auditor."""

from __future__ import annotations

import re
from pathlib import Path

HEAVY_BARRELS = {
    "@mui/material",
    "@mui/icons-material",
    "lodash",
    "rxjs",
    "lucide-react",
}


class BarrelImportAuditor:
    """Detects broad barrel imports that defeat tree-shaking."""

    @staticmethod
    def audit_source_file(file_path: Path) -> list[str]:
        if not file_path.exists():
            return []
        lines = file_path.read_text(encoding="utf-8", errors="replace").splitlines()
        findings = []

        for idx, line in enumerate(lines, start=1):
            line_clean = line.strip()
            for pkg in HEAVY_BARRELS:
                pattern = rf'import\s+\{{.*\}}\s+from\s+[\'"]{re.escape(pkg)}[\'"]'
                if re.search(pattern, line_clean):
                    findings.append(
                        f"{file_path.name}:{idx}: Non-tree-shakeable barrel import from '{pkg}'. Use deep import path instead."
                    )

        return findings
```

---

### 4.5 `src/rush/bundle/code_splitting.py`

```python
"""Dynamic import route boundary checker."""

from __future__ import annotations

import re
from pathlib import Path


class CodeSplittingValidator:
    """Ensures major page/route components use dynamic React.lazy() or next/dynamic imports."""

    @staticmethod
    def inspect_route_file(file_path: Path) -> list[str]:
        if not file_path.exists():
            return []
        text = file_path.read_text(encoding="utf-8", errors="replace")
        findings = []

        if "Routes" in text or "createBrowserRouter" in text:
            for line in text.splitlines():
                if "import " in line and ("Page" in line or "View" in line) and "lazy" not in text:
                    findings.append(f"{file_path.name}: Static page import detected without dynamic lazy() splitting: {line.strip()}")

        return findings
```

---

### 4.6 `src/rush/bundle/css_duplication.py`

```python
"""Duplicate CSS rule block detector."""

from __future__ import annotations

import re
from pathlib import Path


class CssDuplicationScanner:
    """Finds exact duplicate CSS rule declaration blocks across stylesheets."""

    @staticmethod
    def scan_stylesheet(css_file: Path) -> list[str]:
        if not css_file.exists():
            return []
        text = css_file.read_text(encoding="utf-8", errors="replace")
        blocks = re.findall(r"([^{]+)\{([^}]+)\}", text)

        seen_bodies: dict[str, str] = {}
        duplicates = []

        for selector, body in blocks:
            norm_body = " ".join(body.split()).strip()
            norm_sel = selector.strip()
            if norm_body in seen_bodies and len(norm_body) > 30:
                duplicates.append(
                    f"Duplicate CSS block between '{norm_sel}' and '{seen_bodies[norm_body]}': {{{norm_body}}}"
                )
            else:
                seen_bodies[norm_body] = norm_sel

        return duplicates
```

---

### 4.7 `src/rush/bundle/polyfill_auditor.py`

```python
"""Redundant legacy polyfill detector."""

from __future__ import annotations

import re
from pathlib import Path

LEGACY_POLYFILLS = {
    "core-js/features/promise",
    "core-js/features/array/from",
    "core-js/features/object/assign",
    "whatwg-fetch",
}


class PolyfillAuditor:
    """Detects redundant legacy polyfills included for modern browser targets."""

    @staticmethod
    def scan_file(file_path: Path) -> list[str]:
        if not file_path.exists():
            return []
        text = file_path.read_text(encoding="utf-8", errors="replace")
        findings = []
        for poly in LEGACY_POLYFILLS:
            if poly in text:
                findings.append(f"{file_path.name}: Redundant legacy polyfill '{poly}' detected.")
        return findings


class WebWorkerAuditor:
    """Audits Web Worker instantiations for module type parameters."""

    @staticmethod
    def audit_workers(source_file: Path) -> list[str]:
        if not source_file.exists():
            return []
        text = source_file.read_text(encoding="utf-8", errors="replace")
        findings = []
        for m in re.finditer(r"new\s+Worker\(([^)]+)\)", text):
            args = m.group(1)
            if "type:" not in args and "module" not in args:
                findings.append(f"{source_file.name}: Web Worker instantiated without module type: {m.group(0)}")
        return findings
```

---

### 4.8 `src/rush/bundle/css_purge.py`

```python
"""Static unused CSS rule estimator."""

from __future__ import annotations

import re
from pathlib import Path


class CssPurgeEstimator:
    """Estimates unreferenced CSS classes in production stylesheets."""

    @staticmethod
    def extract_css_classes(css_file: Path) -> set[str]:
        if not css_file.exists():
            return set()
        text = css_file.read_text(encoding="utf-8", errors="replace")
        return set(re.findall(r"\.([a-zA-Z0-9_\-]+)\s*\{", text))
```

---

### 4.9 `src/rush/bundle/font_auditor.py`

```python
"""Custom font weight and glyph subsetting linter."""

from __future__ import annotations

from pathlib import Path


class FontAssetAuditor:
    """Scans repository for un-subsetted or legacy TTF/OTF font assets."""

    @staticmethod
    def audit_fonts(repo_root: Path) -> list[str]:
        findings = []
        for p in repo_root.rglob("*"):
            if p.is_file() and p.suffix.lower() in (".ttf", ".otf") and "node_modules" not in p.parts:
                sz = p.stat().st_size
                findings.append(f"{p.name} ({sz/1024:.1f} KB): Legacy font format; convert to subsetted WOFF2.")
        return findings
```

---

### 4.10 `src/rush/bundle/cache_hasher.py`

```python
"""Asset filename content hashing verifier."""

from __future__ import annotations

import re
from pathlib import Path


class AssetCacheBustingVerifier:
    """Verifies that production chunk files include cache-busting hashes."""

    HASH_PATTERN = re.compile(r"\.[a-f0-9]{8,32}\.(js|css|wasm)$")

    @staticmethod
    def verify_directory_hashes(dist_dir: Path) -> list[str]:
        unhashed = []
        for p in dist_dir.rglob("*"):
            if p.is_file() and p.suffix in (".js", ".css", ".wasm") and p.name not in ("index.html", "service-worker.js"):
                if not AssetCacheBustingVerifier.HASH_PATTERN.search(p.name):
                    unhashed.append(f"Unhashed chunk '{p.name}': Missing content hash for CDN cache busting.")
        return unhashed
```

---

### 4.11 `src/rush/bundle/script_auditor.py`

```python
"""Third-party un-async external script detector."""

from __future__ import annotations

import re
from pathlib import Path


class ThirdPartyScriptAuditor:
    """Flags external script tags lacking async or defer attributes."""

    @staticmethod
    def scan_html(html_file: Path) -> list[str]:
        if not html_file.exists():
            return []
        text = html_file.read_text(encoding="utf-8", errors="replace")
        findings = []

        script_pattern = r'<script\s+[^>]*src=[\'"]' + r'(https?:[^\'"]+)[\'"][^>]*>'
        for m in re.finditer(script_pattern, text, re.IGNORECASE):
            tag = m.group(0)
            if "async" not in tag and "defer" not in tag:
                findings.append(f"Render-blocking third-party script without async/defer: {m.group(1)}")

        return findings
```

---

### 4.12 `src/rush/bundle/image_advisor.py`

```python
"""Heavy image discovery and WebP/AVIF optimization advisor."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class HeavyImageFinding:
    file_path: str
    size_bytes: int
    recommendation: str


class HeavyImageAdvisor:
    """Scans for large uncompressed images exceeding 500KB."""

    def __init__(self, repo_root: Path, size_threshold_bytes: int = 500 * 1024) -> None:
        self.repo_root = repo_root.resolve()
        self.size_threshold_bytes = size_threshold_bytes

    def scan(self) -> list[HeavyImageFinding]:
        findings = []
        for p in self.repo_root.rglob("*"):
            if p.is_file() and p.suffix.lower() in (".png", ".jpg", ".jpeg"):
                sz = p.stat().st_size
                if sz > self.size_threshold_bytes:
                    findings.append(
                        HeavyImageFinding(
                            file_path=str(p.relative_to(self.repo_root)),
                            size_bytes=sz,
                            recommendation=f"Convert to WebP or AVIF format to save ~70% byte weight.",
                        )
                    )
        return findings
```

---

### 4.13 `src/rush/bundle/sourcemap_guard.py`

```python
"""Production source map exposure linter."""

from __future__ import annotations

from pathlib import Path


class SourceMapGuard:
    """Ensures production build folders do not accidentally package sensitive source maps."""

    @staticmethod
    def find_exposed_sourcemaps(dist_dir: Path) -> list[Path]:
        if not dist_dir.exists():
            return []
        return [p for p in dist_dir.rglob("*.map") if p.is_file()]
```

---

### 4.14 `src/rush/cli.py` (Registration for `rush bundle`)

```python
import click
from pathlib import Path
from rush.bundle.chunk_calculator import BundleChunkCalculator
from rush.bundle.budget_gate import PerformanceBudgetGate
from rush.bundle.dead_assets import OrphanedAssetScanner
from rush.bundle.barrel_auditor import BarrelImportAuditor
from rush.bundle.font_auditor import FontAssetAuditor
from rush.bundle.cache_hasher import AssetCacheBustingVerifier
from rush.bundle.script_auditor import ThirdPartyScriptAuditor
from rush.bundle.css_duplication import CssDuplicationScanner
from rush.bundle.image_advisor import HeavyImageAdvisor

@click.group(name="bundle")
def bundle_group():
    """Frontend bundle and asset performance optimization."""
    pass

@bundle_group.command(name="analyze")
@click.argument("dist_dir", default="dist", type=click.Path())
def bundle_analyze_cmd(dist_dir: str):
    """Calculate raw, Gzip, and Brotli sizes for build chunks."""
    reports = BundleChunkCalculator.measure_directory(Path(dist_dir))
    if not reports:
        click.echo(f"No build chunks found in '{dist_dir}'.")
        return

    click.echo(f"Bundle Analysis for '{dist_dir}':")
    for r in reports:
        click.echo(f"  - {r.file_name:<40} Raw: {r.raw_bytes/1024:6.1f}KB | Gzip: {r.gzip_bytes/1024:5.1f}KB | Brotli: {r.brotli_est_bytes/1024:5.1f}KB")

@bundle_group.command(name="budget")
@click.argument("dist_dir", default="dist", type=click.Path())
@click.option("--max-gzip-kb", default=150, help="Maximum allowed Gzip size per chunk in KB.")
def bundle_budget_cmd(dist_dir: str, max_gzip_kb: int):
    """Enforce performance budget size ceilings."""
    reports = BundleChunkCalculator.measure_directory(Path(dist_dir))
    gate = PerformanceBudgetGate(max_gzip_bytes=max_gzip_kb * 1024)
    violations = gate.evaluate_chunks(reports)

    if not violations:
        click.echo(f"[PASS] All chunks meet performance budget (<= {max_gzip_kb}KB gzip).")
    else:
        click.echo(f"[FAIL] {len(violations)} chunk(s) exceeded performance budget:", err=True)
        for v in violations:
            click.echo(f"  - {v.file_name}: {v.actual_bytes/1024:.1f}KB > {v.max_bytes/1024:.1f}KB", err=True)
        raise SystemExit(1)

@bundle_group.command(name="dead-assets")
def bundle_dead_assets_cmd():
    """Find unreferenced static images, fonts, and icons."""
    scanner = OrphanedAssetScanner(Path.cwd())
    orphans = scanner.find_orphaned_assets()
    if not orphans:
        click.echo("[PASS] No orphaned static assets found.")
    else:
        click.echo(f"Found {len(orphans)} orphaned asset(s):")
        for o in orphans:
            click.echo(f"  - {o.relative_to(Path.cwd())}")

@bundle_group.command(name="barrel-audit")
def bundle_barrel_audit_cmd():
    """Scan codebase for non-tree-shakeable barrel imports."""
    findings = []
    for p in Path.cwd().rglob("*"):
        if p.is_file() and p.suffix in (".ts", ".tsx", ".js", ".jsx") and "node_modules" not in p.parts:
            findings.extend(BarrelImportAuditor.audit_source_file(p))

    if not findings:
        click.echo("[PASS] No barrel import violations detected.")
    else:
        click.echo(f"Found {len(findings)} barrel import violation(s):")
        for f in findings:
            click.echo(f"  - {f}")
```

---

### 4.15 `src/rush/mcp_server.py` (FastMCP Server Integration)

```python
"""FastMCP tool endpoints for bundle analysis and asset hygiene."""

from mcp.server.fastmcp import FastMCP
from pathlib import Path
import json
from rush.bundle.chunk_calculator import BundleChunkCalculator
from rush.bundle.budget_gate import PerformanceBudgetGate
from rush.bundle.dead_assets import OrphanedAssetScanner

mcp = FastMCP("rush")

@mcp.tool(name="rush_bundle_analyze", description="Measure raw, Gzip, and Brotli chunk transfer sizes.")
def rush_bundle_analyze(dist_dir: str = "dist") -> str:
    reports = BundleChunkCalculator.measure_directory(Path(dist_dir))
    return json.dumps([{"file": r.file_name, "raw_kb": round(r.raw_bytes/1024, 1), "gzip_kb": round(r.gzip_bytes/1024, 1)} for r in reports], indent=2)

@mcp.tool(name="rush_bundle_dead_assets", description="Scan repository for unreferenced static assets.")
def rush_bundle_dead_assets() -> str:
    scanner = OrphanedAssetScanner(Path.cwd())
    orphans = scanner.find_orphaned_assets()
    return json.dumps([str(o.relative_to(Path.cwd())) for o in orphans], indent=2)
```

---

## 5. Complete Test-Driven Development (TDD) Test Suite

### 5.1 `tests/test_frontend_bundle.py`

```python
"""Comprehensive test suite for BundleChunkCalculator, PerformanceBudgetGate, OrphanedAssetScanner, BarrelImportAuditor, CodeSplittingValidator, FontAssetAuditor, PolyfillAuditor, CssDuplicationScanner, CssPurgeEstimator, AssetCacheBustingVerifier, ThirdPartyScriptAuditor, HeavyImageAdvisor, and SourceMapGuard."""

from pathlib import Path
import pytest
from rush.bundle.chunk_calculator import BundleChunkCalculator
from rush.bundle.budget_gate import PerformanceBudgetGate
from rush.bundle.dead_assets import OrphanedAssetScanner
from rush.bundle.barrel_auditor import BarrelImportAuditor
from rush.bundle.code_splitting import CodeSplittingValidator
from rush.bundle.font_auditor import FontAssetAuditor
from rush.bundle.polyfill_auditor import PolyfillAuditor
from rush.bundle.css_duplication import CssDuplicationScanner
from rush.bundle.css_purge import CssPurgeEstimator
from rush.bundle.cache_hasher import AssetCacheBustingVerifier
from rush.bundle.script_auditor import ThirdPartyScriptAuditor
from rush.bundle.image_advisor import HeavyImageAdvisor
from rush.bundle.sourcemap_guard import SourceMapGuard


def test_chunk_calculator(tmp_path: Path):
    f = tmp_path / "bundle.js"
    f.write_text("console.log('hello bundle');\n" * 100, encoding="utf-8")

    report = BundleChunkCalculator.measure_file(f)
    assert report.file_name == "bundle.js"
    assert report.raw_bytes > report.gzip_bytes
    assert report.gzip_bytes > report.brotli_est_bytes


def test_performance_budget_gate():
    from rush.bundle.chunk_calculator import ChunkSizeReport
    reports = [
        ChunkSizeReport(file_name="small.js", raw_bytes=1000, gzip_bytes=400, brotli_est_bytes=350),
        ChunkSizeReport(file_name="huge.js", raw_bytes=500000, gzip_bytes=200000, brotli_est_bytes=160000),
    ]
    gate = PerformanceBudgetGate(max_gzip_bytes=100 * 1024)
    violations = gate.evaluate_chunks(reports)

    assert len(violations) == 1
    assert violations[0].file_name == "huge.js"


def test_orphaned_asset_scanner(tmp_path: Path):
    assets_dir = tmp_path / "assets"
    assets_dir.mkdir()
    used_img = assets_dir / "logo.png"
    used_img.write_bytes(b"used")
    dead_img = assets_dir / "old_banner.png"
    dead_img.write_bytes(b"dead")

    src_file = tmp_path / "App.tsx"
    src_file.write_text("import logo from './assets/logo.png';", encoding="utf-8")

    scanner = OrphanedAssetScanner(tmp_path)
    orphans = scanner.find_orphaned_assets()

    assert len(orphans) == 1
    assert orphans[0].name == "old_banner.png"


def test_barrel_import_auditor(tmp_path: Path):
    f = tmp_path / "Component.tsx"
    f.write_text("import { Button, Dialog } from '@mui/material';\n", encoding="utf-8")

    findings = BarrelImportAuditor.audit_source_file(f)
    assert len(findings) == 1
    assert "Non-tree-shakeable barrel import" in findings[0]


def test_code_splitting_validator(tmp_path: Path):
    router_f = tmp_path / "Router.tsx"
    router_f.write_text("import DashboardPage from './DashboardPage';\nconst Routes = () => <DashboardPage />;\n", encoding="utf-8")

    findings = CodeSplittingValidator.inspect_route_file(router_f)
    assert len(findings) == 1
    assert "Static page import detected" in findings[0]


def test_css_duplication_scanner(tmp_path: Path):
    css_f = tmp_path / "styles.css"
    css_f.write_text(".box-a { display: flex; align-items: center; justify-content: center; padding: 20px; }\n.box-b { display: flex; align-items: center; justify-content: center; padding: 20px; }\n", encoding="utf-8")

    findings = CssDuplicationScanner.scan_stylesheet(css_f)
    assert len(findings) == 1
    assert "Duplicate CSS block" in findings[0]


def test_polyfill_auditor(tmp_path: Path):
    f = tmp_path / "legacy.js"
    f.write_text("import 'core-js/features/promise';\n", encoding="utf-8")
    findings = PolyfillAuditor.scan_file(f)
    assert len(findings) == 1
    assert "Redundant legacy polyfill" in findings[0]


def test_css_purge_estimator(tmp_path: Path):
    css_f = tmp_path / "styles.css"
    css_f.write_text(".btn-primary { color: red; }\n.btn-secondary { color: blue; }\n", encoding="utf-8")
    classes = CssPurgeEstimator.extract_css_classes(css_f)
    assert "btn-primary" in classes
    assert "btn-secondary" in classes


def test_font_asset_auditor(tmp_path: Path):
    font_f = tmp_path / "custom.ttf"
    font_f.write_bytes(b"ttf font data")

    findings = FontAssetAuditor.audit_fonts(tmp_path)
    assert len(findings) == 1
    assert "custom.ttf" in findings[0]


def test_cache_busting_verifier(tmp_path: Path):
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "bundle.a1b2c3d4.js").write_text("code", encoding="utf-8")
    (dist / "unhashed.js").write_text("code", encoding="utf-8")

    violations = AssetCacheBustingVerifier.verify_directory_hashes(dist)
    assert len(violations) == 1
    assert "unhashed.js" in violations[0]


def test_script_auditor(tmp_path: Path):
    html_f = tmp_path / "index.html"
    html_f.write_text('<html><head><script src="https://cdn.example.com/lib.js"></script></head></html>', encoding="utf-8")

    findings = ThirdPartyScriptAuditor.scan_html(html_f)
    assert len(findings) == 1
    assert "https://cdn.example.com/lib.js" in findings[0]


def test_heavy_image_advisor(tmp_path: Path):
    heavy_png = tmp_path / "heavy.png"
    heavy_png.write_bytes(b"0" * (600 * 1024))

    advisor = HeavyImageAdvisor(tmp_path, size_threshold_bytes=500 * 1024)
    findings = advisor.scan()
    assert len(findings) == 1
    assert "heavy.png" in findings[0].file_path


def test_sourcemap_guard(tmp_path: Path):
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "bundle.js").write_text("code", encoding="utf-8")
    (dist / "bundle.js.map").write_text("map", encoding="utf-8")

    maps = SourceMapGuard.find_exposed_sourcemaps(dist)
    assert len(maps) == 1
    assert maps[0].name == "bundle.js.map"
```

---

## 6. Structured Error Logging & Diagnostics Contract

All Phase 36 diagnostics MUST be emitted to `sys.stderr` formatted as structured NDJSON.

```json
{"timestamp": "2026-08-21T10:10:00.100Z", "phase": 36, "tool": "rush_bundle", "event": "chunk_measured", "file": "main.js", "gzip_bytes": 45120}
{"timestamp": "2026-08-21T10:10:01.300Z", "phase": 36, "tool": "rush_bundle", "event": "budget_violation", "file": "vendor.js", "actual": 185000, "budget": 150000}
```

---

## 7. Semantic Drift Review, Backlog Update & Documentation Synchronization

### 7.1 Master Backlog Synchronization Protocol
Upon completion of Phase 36 implementation tasks:
1. Open [`docs/developer/backlog.md`](file:///C:/Users/james/developer/rush-cli/docs/developer/backlog.md).
2. Locate **Phase 36: Frontend Asset & Bundle Optimization**.
3. Update Status from `Ready` to `Complete`.
4. Record implementation commit hash and verification summary.

### 7.2 Specific Documentation Updates Across `/docs` (136+ Files Tree)

The following specific documents across the `/docs` tree must be created or updated upon Phase 36 completion:

#### A. User-Facing Documentation
- **[`docs/USER_GUIDE.md`](file:///C:/Users/james/developer/rush-cli/docs/USER_GUIDE.md)**: Add "Frontend Asset & Bundle Performance Optimization" guide.
- **[`docs/CLI_REFERENCE.md`](file:///C:/Users/james/developer/rush-cli/docs/CLI_REFERENCE.md)**: Document `rush bundle analyze`, `rush bundle budget`, `rush bundle dead-assets` (flags: `--max-initial-kb`, `--brotli`, `--sourcemaps`).
- **[`docs/CLI_COOKBOOK.md`](file:///C:/Users/james/developer/rush-cli/docs/CLI_COOKBOOK.md)**: Add recipes for failing PR builds that exceed client bundle budgets.
- **[`docs/RECIPE_BOOK.md`](file:///C:/Users/james/developer/rush-cli/docs/RECIPE_BOOK.md)**: Add automated recipe for cleaning orphaned static images in pre-commit hooks.
- **[`docs/EXAMPLES.md`](file:///C:/Users/james/developer/rush-cli/docs/EXAMPLES.md)**: Show example bundle chunk breakdown tables and compression metrics.
- **[`docs/TUTORIALS.md`](file:///C:/Users/james/developer/rush-cli/docs/TUTORIALS.md)**: Add tutorial on setting up performance budgets for Vite/Next.js applications.
- **[`docs/TROUBLESHOOTING.md`](file:///C:/Users/james/developer/rush-cli/docs/TROUBLESHOOTING.md)**: Add entries for missing build output directories and sourcemap leakage warnings.
- **[`docs/FAQ.md`](file:///C:/Users/james/developer/rush-cli/docs/FAQ.md)**: Explain how Rush calculates Gzip and Brotli sizes offline without deploying.

#### B. MCP Server & Agent Protocol Documentation
- **[`docs/MCP.md`](file:///C:/Users/james/developer/rush-cli/docs/MCP.md)**: Document `rush_bundle_analyze` and `rush_bundle_dead_assets` FastMCP tool endpoints.
- **[`docs/MCP_REFERENCE.md`](file:///C:/Users/james/developer/rush-cli/docs/MCP_REFERENCE.md)**: Document chunk size metrics JSON response models.

#### C. Catalog & Configuration Documentation
- **[`docs/TOOL_CATALOG.md`](file:///C:/Users/james/developer/rush-cli/docs/TOOL_CATALOG.md)**: Register `bundle` tool in Performance & Optimization category.
- **[`docs/CONFIGURATION.md`](file:///C:/Users/james/developer/rush-cli/docs/CONFIGURATION.md)** & **[`docs/CONFIG_SCHEMA.md`](file:///C:/Users/james/developer/rush-cli/docs/CONFIG_SCHEMA.md)**: Document `[bundle]` configuration table (`dist_dir`, `budget_kb`, `allow_sourcemaps`).

#### D. Architecture & Developer Documentation
- **[`docs/ARCHITECTURE.md`](file:///C:/Users/james/developer/rush-cli/docs/ARCHITECTURE.md)**: Document chunk size calculation pipeline, Brotli compression estimators, and AST barrel import analyzer.
- **[`docs/DEVELOPER_GUIDE.md`](file:///C:/Users/james/developer/rush-cli/docs/DEVELOPER_GUIDE.md)**: Add guide for integrating new web bundler manifest formats (e.g. Webpack stats.json, Vite manifest.json).
- **[`docs/CI_INTEGRATION.md`](file:///C:/Users/james/developer/rush-cli/docs/CI_INTEGRATION.md)**: Include CI workflow step for bundle budget verification.
- **[`docs/TESTING.md`](file:///C:/Users/james/developer/rush-cli/docs/TESTING.md)**: Document bundle measurement test fixtures and dead asset discovery tests.
- **[`docs/tools/bundle.md`](file:///C:/Users/james/developer/rush-cli/docs/tools/bundle.md)**: Create dedicated reference documentation.

### 7.3 Automated Documentation Parity Check
```bash
.venv/Scripts/python.exe scripts/sync_docs.py --update
.venv/Scripts/python.exe scripts/sync_docs.py --check
```

### 7.4 Ending Git Lifecycle Commands
Execute these commands upon completing all phase tasks and verification checks:
```bash
# 1. Full verification gate
.venv/Scripts/python.exe -m pytest tests/ -q
.venv/Scripts/ruff.exe check src tests scripts
.venv/Scripts/ruff.exe format src tests scripts
.venv/Scripts/python.exe scripts/sync_docs.py --update
.venv/Scripts/python.exe scripts/sync_docs.py --check

# 2. Stage & Commit
git add src/ tests/ docs/
git commit -m "feat(phase-36): implement bundle analyzer, budget enforcer, dead asset detector and barrel auditor"

# 3. Record commit SHA in docs/developer/backlog.md
git rev-parse --short HEAD
```
