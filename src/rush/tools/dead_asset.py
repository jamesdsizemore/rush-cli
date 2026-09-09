"""Unreferenced asset and dead media detection tool (Strictly Read-Only).

Identifies images, fonts, and media assets unreferenced in repository source code,
generates deterministic audit manifests, and calculates potential disk savings without
modifying or deleting any repository files.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, ClassVar

from .base import Finding, ToolFn, ToolResult, ToolStatus
from .common import elapsed_ms, now_ms, skipped_result


class DeadAssetScanner:
    """Identifies images, fonts, and assets in the repository that are unreferenced in source code."""

    ASSET_EXTS: ClassVar[set[str]] = {
        ".png",
        ".jpg",
        ".jpeg",
        ".svg",
        ".gif",
        ".webp",
        ".ttf",
        ".woff",
        ".woff2",
        ".ico",
        ".bmp",
        ".tiff",
        ".mp4",
        ".webm",
    }

    IGNORED_DIRS: ClassVar[set[str]] = {
        ".git",
        ".venv",
        ".rush",
        "node_modules",
        "dist",
        "build",
        "__pycache__",
        ".pytest_cache",
        ".mypy_cache",
        ".ruff_cache",
    }

    SOURCE_EXTS: ClassVar[set[str]] = {
        ".py",
        ".md",
        ".html",
        ".css",
        ".scss",
        ".sass",
        ".less",
        ".ts",
        ".tsx",
        ".js",
        ".jsx",
        ".json",
        ".yaml",
        ".yml",
        ".toml",
        ".rst",
        ".xml",
    }

    def __init__(self, project_root: Path | None = None):
        self.project_root = (project_root or Path.cwd()).resolve()

    def scan_dead_assets(self) -> dict[str, Any]:
        all_assets: set[Path] = set()
        for ext in self.ASSET_EXTS:
            for p in self.project_root.rglob(f"*{ext}"):
                if p.is_file() and not self._is_ignored(p):
                    all_assets.add(p)

        all_text = ""
        for src_file in self.project_root.rglob("*"):
            if (
                src_file.is_file()
                and src_file.suffix.lower() in self.SOURCE_EXTS
                and not self._is_ignored(src_file)
            ):
                try:
                    all_text += " " + src_file.read_text(
                        encoding="utf-8", errors="ignore"
                    )
                except Exception:  # noqa: BLE001, S110
                    pass

        unreferenced: list[str] = []
        for asset in sorted(all_assets):
            rel = str(asset.relative_to(self.project_root)).replace("\\", "/")
            if asset.name not in all_text and rel not in all_text:
                unreferenced.append(rel)

        return {
            "total_assets": len(all_assets),
            "dead_assets_count": len(unreferenced),
            "dead_assets": unreferenced,
        }

    def _is_ignored(self, path: Path) -> bool:
        for part in path.parts:
            if part in self.IGNORED_DIRS:
                return True
        return False


class DeadAssetTool(ToolFn):
    """Audit unreferenced image, font, and media assets in the repository (Strictly Read-Only)."""

    name = "dead-asset"

    @property
    def mcp_description(self) -> str:
        return (
            "Detect unreferenced images, fonts, and media assets under <path> (strictly read-only). "
            "Returns {status, findings[], summary}; export manifest requires --allow-artifact-write."
        )

    def __call__(
        self,
        path: Path,
        *,
        export_manifest: Path | str | None = None,
        allow_artifact_write: bool = False,
    ) -> ToolResult:
        from ..permissions import ExecutionPermissions

        permissions = ExecutionPermissions(artifact_write=allow_artifact_write)
        return self.run(
            path,
            export_manifest=export_manifest,
            permissions=permissions,
        )

    def generate_manifest(self, root: Path) -> list[dict[str, Any]]:
        manifest: list[dict[str, Any]] = []
        scanner = DeadAssetScanner(project_root=root)
        scan_res = scanner.scan_dead_assets()
        dead_set = set(scan_res["dead_assets"])

        for ext in scanner.ASSET_EXTS:
            for p in root.rglob(f"*{ext}"):
                if p.is_file() and not scanner._is_ignored(p):
                    rel = str(p.relative_to(root)).replace("\\", "/")
                    data = p.read_bytes()
                    manifest.append(
                        {
                            "path": rel,
                            "sha256": hashlib.sha256(data).hexdigest(),
                            "size_bytes": len(data),
                            "status": "unreferenced" if rel in dead_set else "active",
                        }
                    )
        manifest.sort(key=lambda x: x["path"])
        return manifest

    def run(
        self,
        path: Path,
        *,
        config: Any = None,
        permissions: Any = None,
        export_manifest: Path | str | None = None,
    ) -> ToolResult:
        from ..permissions import ExecutionPermissions, build_execution_metadata

        start = now_ms()
        perms = permissions or ExecutionPermissions()
        root = path.resolve() if path.is_dir() else path.parent.resolve()

        scanner = DeadAssetScanner(project_root=root)
        scan_res = scanner.scan_dead_assets()
        manifest = self.generate_manifest(root)

        total_assets = scan_res["total_assets"]
        dead_count = scan_res["dead_assets_count"]
        potential_savings_bytes = sum(
            item["size_bytes"] for item in manifest if item["status"] == "unreferenced"
        )
        scan_res["potential_savings_bytes"] = potential_savings_bytes

        if total_assets == 0:
            res = skipped_result(
                self.name,
                "dead-asset-scanner",
                f"dead-asset: no media or font assets found under '{path}'",
                duration_ms=elapsed_ms(start),
            )
            res["metadata"] = {
                "execution": build_execution_metadata(
                    mode="executed",
                    requested=perms,
                    granted=perms,
                    producer="dead-asset",
                )
            }
            return res

        findings: list[Finding] = []
        for item in manifest:
            if item["status"] == "unreferenced":
                findings.append(
                    Finding(
                        path=item["path"],
                        line=1,
                        column=1,
                        rule="dead-asset",
                        rule_id="WARN_UNREFERENCED_ASSET",
                        severity="warn",
                        message=f"Unreferenced asset: {item['path']} ({item['size_bytes']} bytes)",
                        fingerprint=item["sha256"],
                    )
                )

        artifacts: list[str] = []
        if export_manifest is not None:
            exp = Path(export_manifest)
            if not exp.is_absolute():
                exp = (root / exp).resolve()
            else:
                exp = exp.resolve()

            if not exp.is_relative_to(root):
                return ToolResult(
                    tool=self.name,
                    engine="dead-asset-scanner",
                    engine_version="1.0.0",
                    status="error",
                    duration_ms=elapsed_ms(start),
                    summary=f"dead-asset: export path '{export_manifest}' escapes target root '{root}'",
                    findings=[],
                    raw=None,
                    metadata={
                        "execution": build_execution_metadata(
                            mode="executed",
                            requested=perms,
                            granted=perms,
                            producer="dead-asset",
                        )
                    },
                )

            if not perms.artifact_write:
                return ToolResult(
                    tool=self.name,
                    engine="dead-asset-scanner",
                    engine_version="1.0.0",
                    status="skipped",
                    duration_ms=elapsed_ms(start),
                    summary=(
                        f"dead-asset: writing manifest to '{export_manifest}' "
                        "requires explicit --allow-artifact-write permission."
                    ),
                    findings=findings,
                    raw=scan_res,
                    metadata={
                        "execution": build_execution_metadata(
                            mode="executed",
                            requested=perms,
                            granted=perms,
                            producer="dead-asset",
                        )
                    },
                )

            from rush.safety.redactor import sanitize_value

            clean_manifest = sanitize_value(manifest).value
            exp.parent.mkdir(parents=True, exist_ok=True)
            exp.write_text(json.dumps(clean_manifest, indent=2), encoding="utf-8")
            artifacts.append(str(exp))

        status: ToolStatus = "warn" if dead_count > 0 else "ok"
        savings_kb = round(potential_savings_bytes / 1024, 1)

        summary = (
            f"dead-asset: scanned {total_assets} assets, found {dead_count} unreferenced "
            f"({savings_kb} KB potential savings). Strictly read-only analysis."
        )

        return ToolResult(
            tool=self.name,
            engine="dead-asset-scanner",
            engine_version="1.0.0",
            status=status,
            duration_ms=elapsed_ms(start),
            summary=summary,
            findings=findings,
            metrics={
                "total_assets": total_assets,
                "dead_assets_count": dead_count,
                "potential_savings_bytes": potential_savings_bytes,
            },
            raw=scan_res,
            artifacts=artifacts if artifacts else None,
            metadata={
                "manifest": manifest,
                "potential_savings_bytes": potential_savings_bytes,
                "execution": build_execution_metadata(
                    mode="executed",
                    requested=perms,
                    granted=perms,
                    producer="dead-asset",
                ),
            },
        )


__all__ = ["DeadAssetScanner", "DeadAssetTool"]
