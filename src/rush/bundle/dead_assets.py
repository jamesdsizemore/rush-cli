"""Orphaned static image, font, and media scanner."""

from __future__ import annotations

from pathlib import Path

ASSET_EXTENSIONS = {
    ".png",
    ".jpg",
    ".jpeg",
    ".svg",
    ".webp",
    ".avif",
    ".woff",
    ".woff2",
    ".ttf",
}


class OrphanedAssetScanner:
    """Discovers static assets in public/ or assets/ directories not referenced in source code."""

    def __init__(self, repo_root: Path) -> None:
        self.repo_root = repo_root.resolve()

    def find_all_assets(self) -> list[Path]:
        assets = []
        for p in self.repo_root.rglob("*"):
            if (
                p.is_file()
                and p.suffix.lower() in ASSET_EXTENSIONS
                and ".venv" not in p.parts
                and "node_modules" not in p.parts
            ):
                assets.append(p)
        return assets

    def find_orphaned_assets(self) -> list[Path]:
        all_assets = self.find_all_assets()
        if not all_assets:
            return []

        source_text = []
        for p in self.repo_root.rglob("*"):
            if p.is_file() and p.suffix in (
                ".tsx",
                ".ts",
                ".jsx",
                ".js",
                ".vue",
                ".html",
                ".css",
                ".scss",
            ):
                source_text.append(p.read_text(encoding="utf-8", errors="replace"))

        combined_sources = "\n".join(source_text)
        orphaned = []

        for asset in all_assets:
            name = asset.name
            if name not in combined_sources:
                orphaned.append(asset)

        return orphaned
