"""Unreferenced asset and dead media pruner tool (PR50.14).

Identifies images, fonts, and media assets unreferenced in repository source code,
generates deterministic audit manifests, and performs guarded pruning with SHA-256
validation and artifact-write permission gating.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, ClassVar

from .base import Finding, ToolFn, ToolResult
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
        for asset in all_assets:
            rel = str(asset.relative_to(self.project_root)).replace("\\", "/")
            if asset.name not in all_text and rel not in all_text:
                unreferenced.append(rel)

        return {
            "total_assets": len(all_assets),
            "dead_assets_count": len(unreferenced),
            "dead_assets": sorted(unreferenced),
        }

    def _is_ignored(self, p: Path) -> bool:
        return any(ignored in p.parts for ignored in self.IGNORED_DIRS)


class DeadAssetTool(ToolFn):
    """Scan and prune unreferenced static media, fonts, and assets."""

    name = "dead-asset"

    @property
    def mcp_description(self) -> str:
        return (
            "Scan unreferenced assets at <path>; generate manifest; "
            "prune requires --allow-artifact-write and SHA-256 validation."
        )

    def __call__(
        self,
        path: Path,
        *,
        prune: bool = False,
        export_manifest: Path | str | None = None,
        allow_artifact_write: bool = False,
    ) -> ToolResult:
        from ..permissions import ExecutionPermissions

        permissions = ExecutionPermissions(artifact_write=allow_artifact_write)
        return self.run(
            path,
            prune=prune,
            export_manifest=export_manifest,
            permissions=permissions,
        )

    def generate_manifest(self, project_root: Path) -> list[dict[str, Any]]:
        """Generate deterministic audit manifest with SHA-256 digests for all assets."""
        scanner = DeadAssetScanner(project_root=project_root)
        scan_res = scanner.scan_dead_assets()
        dead_set = set(scan_res["dead_assets"])

        manifest: list[dict[str, Any]] = []
        for ext in scanner.ASSET_EXTS:
            for p in sorted(project_root.rglob(f"*{ext}")):
                if p.is_file() and not scanner._is_ignored(p):
                    rel = str(p.relative_to(project_root)).replace("\\", "/")
                    size = p.stat().st_size
                    h = hashlib.sha256()
                    h.update(p.read_bytes())
                    sha256 = h.hexdigest()
                    manifest.append(
                        {
                            "path": rel,
                            "size_bytes": size,
                            "sha256": sha256,
                            "status": "unreferenced"
                            if rel in dead_set
                            else "referenced",
                        }
                    )
        return manifest

    def prune_candidates(
        self,
        project_root: Path,
        candidates: list[dict[str, Any]],
        permissions: Any,
    ) -> tuple[int, int]:
        """Prune unreferenced asset candidates after validating SHA-256 and containment."""
        if not getattr(permissions, "artifact_write", False):
            return 0, 0

        pruned_count = 0
        bytes_freed = 0
        root_resolved = project_root.resolve()

        for item in candidates:
            if item.get("status") != "unreferenced":
                continue
            rel_path = item["path"]
            file_path = (project_root / rel_path).resolve()

            # Containment check
            if not file_path.is_relative_to(root_resolved):
                continue
            if not file_path.is_file():
                continue

            # SHA-256 validation before deletion (tamper protection)
            h = hashlib.sha256()
            h.update(file_path.read_bytes())
            current_sha = h.hexdigest()
            if current_sha != item.get("sha256"):
                continue

            # Safe to delete
            size = file_path.stat().st_size
            try:
                file_path.unlink()
                pruned_count += 1
                bytes_freed += size
            except OSError:
                continue

        return pruned_count, bytes_freed

    def run(
        self,
        path: Path,
        *,
        config: Any = None,
        permissions: Any = None,
        prune: bool = False,
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
        dead_assets = scan_res["dead_assets"]
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
        # Export manifest if requested
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

        # Handle Prune
        bytes_freed = 0
        pruned_count = 0
        if prune:
            if not perms.artifact_write:
                return ToolResult(
                    tool=self.name,
                    engine="dead-asset-scanner",
                    engine_version="1.0.0",
                    status="skipped",
                    duration_ms=elapsed_ms(start),
                    summary=(
                        "dead-asset: pruning unreferenced assets requires "
                        "explicit --allow-artifact-write permission."
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
            pruned_count, bytes_freed = self.prune_candidates(root, manifest, perms)

        if prune and perms.artifact_write:
            status = "ok"
            summary = (
                f"dead-asset: successfully pruned {pruned_count} unreferenced assets "
                f"({bytes_freed} bytes freed) across {total_assets} total assets."
            )
        elif dead_count > 0:
            status = "warn"
            summary = (
                f"dead-asset: found {dead_count} unreferenced assets "
                f"({potential_savings_bytes} bytes potential savings) out of "
                f"{total_assets} total assets."
            )
        else:
            status = "ok"
            summary = f"dead-asset: clean - all {total_assets} assets are referenced in source code."

        return ToolResult(
            tool=self.name,
            engine="dead-asset-scanner",
            engine_version="1.0.0",
            status=status,
            duration_ms=elapsed_ms(start),
            summary=summary,
            findings=findings if not (prune and perms.artifact_write) else [],
            raw=scan_res,
            artifacts=artifacts if artifacts else None,
            metadata={
                "total_assets": total_assets,
                "dead_assets_count": dead_count,
                "dead_assets": dead_assets,
                "potential_savings_bytes": potential_savings_bytes,
                "bytes_freed": bytes_freed,
                "pruned": bool(prune and perms.artifact_write),
                "execution": build_execution_metadata(
                    mode="executed",
                    requested=perms,
                    granted=perms,
                    producer="dead-asset",
                ),
            },
        )
