"""Unit tests for DeadAssetTool and DeadAssetScanner (PR50.14)."""

from __future__ import annotations

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
    assert res["status"] in ("ok", "warn")
    assert res["raw"] is not None

    raw = res["raw"]
    assert raw["total_assets"] == 3
    assert raw["dead_assets_count"] == 2
    dead_paths = raw["dead_assets"]
    assert any("old_banner.jpg" in p for p in dead_paths)
    assert any("custom_font.woff2" in p for p in dead_paths)
    assert not any("logo_active.png" in p for p in dead_paths)


def test_dead_asset_pruning_requires_artifact_write_permission(tmp_path: Path) -> None:
    assets_dir = tmp_path / "assets"
    assets_dir.mkdir(parents=True)
    dead_img = assets_dir / "unused.png"
    dead_img.write_bytes(b"unused data")

    tool = DeadAssetTool()

    # Prune without permission
    denied = tool.run(
        tmp_path,
        prune=True,
        permissions=ExecutionPermissions(artifact_write=False),
    )
    assert denied["status"] in ("skipped", "warn")
    assert dead_img.exists()
    assert "--allow-artifact-write" in denied["summary"]

    # Prune with permission
    granted = tool.run(
        tmp_path,
        prune=True,
        permissions=ExecutionPermissions(artifact_write=True),
    )
    assert granted["status"] == "ok"
    assert not dead_img.exists()
    assert granted["metadata"]["bytes_freed"] == len(b"unused data")


def test_dead_asset_prune_validates_sha256_before_deletion(tmp_path: Path) -> None:
    assets_dir = tmp_path / "assets"
    assets_dir.mkdir(parents=True)
    dead_img = assets_dir / "changed_concurrently.png"
    dead_img.write_bytes(b"initial")

    tool = DeadAssetTool()
    manifest = tool.generate_manifest(tmp_path)
    item = next(i for i in manifest if "changed_concurrently.png" in i["path"])

    # Tamper with file before prune
    dead_img.write_bytes(b"tampered content")

    # Pruning with stale manifest candidate should fail validation or protect the file
    pruned_count, _freed_bytes = tool.prune_candidates(
        tmp_path,
        candidates=[item],
        permissions=ExecutionPermissions(artifact_write=True),
    )
    assert pruned_count == 0
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
    tool = DeadAssetTool()
    res = tool(tmp_path)

    assert res["tool"] == "dead-asset"
    assert res["status"] in ("ok", "warn", "skipped")
    assert isinstance(res["duration_ms"], int)
    assert isinstance(res["findings"], list)


def test_dead_asset_reports_potential_savings_bytes(tmp_path: Path) -> None:
    assets_dir = tmp_path / "assets"
    assets_dir.mkdir(parents=True)
    dead_file = assets_dir / "unused_bg.png"
    dead_file.write_bytes(b"A" * 1234)

    tool = DeadAssetTool()
    res = tool.run(tmp_path)

    assert res["status"] == "warn"
    assert res["raw"]["potential_savings_bytes"] == 1234
    assert res["metadata"]["potential_savings_bytes"] == 1234
    assert "1234 bytes potential savings" in res["summary"]
