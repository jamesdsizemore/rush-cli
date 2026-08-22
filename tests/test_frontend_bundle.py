"""Tests for Phase 36: Frontend Asset & Bundle Optimization."""

from __future__ import annotations

from pathlib import Path

from rush.bundle.barrel_auditor import BarrelImportAuditor
from rush.bundle.budget_gate import PerformanceBudgetGate
from rush.bundle.chunk_calculator import BundleChunkCalculator
from rush.bundle.css_duplication import CssDuplicationScanner
from rush.bundle.dead_assets import OrphanedAssetScanner
from rush.bundle.polyfill_auditor import PolyfillAuditor


def test_bundle_chunk_calculator(tmp_path: Path) -> None:
    dist = tmp_path / "dist"
    dist.mkdir()
    js_file = dist / "app.main.js"
    js_file.write_text("console.log('hello bundle');\n" * 100, encoding="utf-8")

    reports = BundleChunkCalculator.measure_directory(dist)
    assert len(reports) == 1
    assert reports[0].raw_bytes > reports[0].gzip_bytes
    assert reports[0].brotli_est_bytes > 0


def test_performance_budget_gate(tmp_path: Path) -> None:
    import os

    dist = tmp_path / "dist"
    dist.mkdir()
    js_file = dist / "vendor.huge.js"
    js_file.write_bytes(os.urandom(20000))

    reports = BundleChunkCalculator.measure_directory(dist)
    gate = PerformanceBudgetGate(max_gzip_bytes=500)
    violations = gate.evaluate_chunks(reports)
    assert len(violations) == 1
    assert violations[0].file_name == "vendor.huge.js"


def test_orphaned_asset_scanner(tmp_path: Path) -> None:
    assets = tmp_path / "public"
    assets.mkdir()
    (assets / "used_logo.png").write_bytes(b"used logo")
    (assets / "unused_banner.svg").write_bytes(b"unused banner")

    src = tmp_path / "src"
    src.mkdir()
    (src / "App.tsx").write_text(
        '<img src="/public/used_logo.png" />', encoding="utf-8"
    )

    scanner = OrphanedAssetScanner(tmp_path)
    orphaned = scanner.find_orphaned_assets()
    assert len(orphaned) == 1
    assert orphaned[0].name == "unused_banner.svg"


def test_barrel_import_auditor(tmp_path: Path) -> None:
    src_file = tmp_path / "Component.tsx"
    src_file.write_text(
        'import { Button, Dialog } from "@mui/material";', encoding="utf-8"
    )

    findings = BarrelImportAuditor.audit_source_file(src_file)
    assert len(findings) == 1
    assert "Non-tree-shakeable barrel import" in findings[0]


def test_css_duplication_scanner(tmp_path: Path) -> None:
    css_file = tmp_path / "styles.css"
    dup_block = (
        "display: flex; justify-content: center; align-items: center; padding: 20px;"
    )
    css_file.write_text(
        f".header {{ {dup_block} }}\n.footer {{ {dup_block} }}", encoding="utf-8"
    )

    duplicates = CssDuplicationScanner.scan_stylesheet(css_file)
    assert len(duplicates) == 1


def test_polyfill_auditor(tmp_path: Path) -> None:
    js_file = tmp_path / "legacy.js"
    js_file.write_text('import "whatwg-fetch";\nfetch("/api");', encoding="utf-8")

    findings = PolyfillAuditor.audit_file(js_file)
    assert len(findings) == 1
    assert "whatwg-fetch" in findings[0]
