"""Unit tests for DeadAssetTool and DeadAssetScanner (PR50.14)."""

from __future__ import annotations

import json
from pathlib import Path

from rush.permissions import ExecutionPermissions
from rush.tools.dead_asset import DeadAssetScanner, DeadAssetTool


def test_dead_asset_scans_and_identifies_unreferenced_assets(tmp_path: Path) -> None:
    assets_dir = tmp_path / "static" / "images"
    assets_dir.mkdir(parents=True)

    used_img = assets_dir / "logo_active.png"
    used_img.write_bytes(b"active logo data")

    dead_img = assets_dir / "old_banner.jpg"
    dead_img.write_bytes(b"old banner data")

    dead_font = assets_dir / "custom_font.woff2"
    dead_font.write_bytes(b"font data")

    src_file = tmp_path / "index.html"
    src_file.write_text('<img src="/static/images/logo_active.png">', encoding="utf-8")

    tool = DeadAssetTool()
    res = tool.run(tmp_path)

    assert res["tool"] == "dead-asset"
    assert res["status"] == "warn"
    assert res["raw"] is not None

    raw = res["raw"]
    assert raw["total_assets"] == 3
    assert raw["dead_assets_count"] == 2
    dead_paths = raw["dead_assets"]
    assert any("old_banner.jpg" in p for p in dead_paths)
    assert any("custom_font.woff2" in p for p in dead_paths)
    assert not any("logo_active.png" in p for p in dead_paths)
    # Verify read-only guarantee: dead assets are never deleted
    assert dead_img.exists()
    assert dead_font.exists()


def test_dead_asset_export_manifest_requires_artifact_write_permission(
    tmp_path: Path,
) -> None:
    assets_dir = tmp_path / "assets"
    assets_dir.mkdir(parents=True)
    dead_img = assets_dir / "unused.png"
    dead_img.write_bytes(b"unused data")

    tool = DeadAssetTool()
    manifest_path = tmp_path / "manifest.json"

    # Export without permission
    denied = tool.run(
        tmp_path,
        export_manifest=manifest_path,
        permissions=ExecutionPermissions(artifact_write=False),
    )
    assert denied["status"] == "skipped"
    assert not manifest_path.exists()
    assert "--allow-artifact-write" in denied["summary"]

    # Export with permission
    granted = tool.run(
        tmp_path,
        export_manifest=manifest_path,
        permissions=ExecutionPermissions(artifact_write=True),
    )
    assert granted["status"] == "warn"
    assert manifest_path.exists()
    written_data = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert len(written_data) == 1
    assert written_data[0]["path"] == "assets/unused.png"
    assert written_data[0]["status"] == "unreferenced"
    # Verify strictly read-only: target asset is NOT deleted
    assert dead_img.exists()


def test_dead_asset_strictly_read_only_and_path_traversal_check(tmp_path: Path) -> None:
    assets_dir = tmp_path / "assets"
    assets_dir.mkdir(parents=True)
    dead_img = assets_dir / "changed.png"
    dead_img.write_bytes(b"initial")

    tool = DeadAssetTool()
    # Path traversal rejection
    res = tool.run(
        tmp_path,
        export_manifest="../outside.json",
        permissions=ExecutionPermissions(artifact_write=True),
    )
    assert res["status"] == "error"
    assert "escapes target root" in res["summary"]
    assert dead_img.exists()


def test_dead_asset_scanner_backward_compatibility(tmp_path: Path) -> None:
    assets_dir = tmp_path / "assets"
    assets_dir.mkdir(parents=True)
    (assets_dir / "logo_used.png").write_bytes(b"used")
    (assets_dir / "dead_icon.svg").write_bytes(b"dead")

    src_file = tmp_path / "index.html"
    src_file.write_text('<img src="assets/logo_used.png">', encoding="utf-8")

    scanner = DeadAssetScanner(project_root=tmp_path)
    res = scanner.scan_dead_assets()

    assert res["total_assets"] == 2
    assert res["dead_assets_count"] == 1
    assert any("dead_icon.svg" in a for a in res["dead_assets"])


def test_dead_asset_canonical_schema_and_call(tmp_path: Path) -> None:
    assets_dir = tmp_path / "assets"
    assets_dir.mkdir(parents=True)
    (assets_dir / "logo.png").write_bytes(b"data")
    src = tmp_path / "index.html"
    src.write_text('<img src="assets/logo.png">', encoding="utf-8")

    tool = DeadAssetTool()
    res = tool(tmp_path)

    assert res["tool"] == "dead-asset"
    assert res["status"] == "ok"
    assert isinstance(res["duration_ms"], int)
    assert isinstance(res["findings"], list)
    assert res["raw"]["dead_assets_count"] == 0


def test_dead_asset_reports_potential_savings_bytes(tmp_path: Path) -> None:
    assets_dir = tmp_path / "assets"
    assets_dir.mkdir(parents=True)
    dead_file = assets_dir / "unused_bg.png"
    dead_file.write_bytes(b"A" * 1024)

    tool = DeadAssetTool()
    res = tool.run(tmp_path)

    assert res["status"] == "warn"
    assert res["raw"]["potential_savings_bytes"] == 1024
    assert res["metadata"]["potential_savings_bytes"] == 1024
    assert "1.0 KB potential savings" in res["summary"]
