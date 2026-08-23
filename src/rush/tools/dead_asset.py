"""Unreferenced asset and dead media pruner."""

from pathlib import Path
from typing import Any, ClassVar


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
    }

    def __init__(self, project_root: Path | None = None):
        self.project_root = project_root or Path.cwd()

    def scan_dead_assets(self) -> dict[str, Any]:
        all_assets: set[Path] = set()
        for ext in self.ASSET_EXTS:
            for p in self.project_root.glob(f"**/*{ext}"):
                if (
                    ".git" not in str(p)
                    and ".venv" not in str(p)
                    and ".rush" not in str(p)
                ):
                    all_assets.add(p)

        all_text = ""
        for src_file in self.project_root.glob("**/*"):
            if (
                src_file.is_file()
                and src_file.suffix
                in (".py", ".md", ".html", ".css", ".ts", ".js", ".json")
                and ".git" not in str(src_file)
                and ".venv" not in str(src_file)
                and ".rush" not in str(src_file)
            ):
                try:
                    all_text += " " + src_file.read_text(
                        encoding="utf-8", errors="ignore"
                    )
                except Exception:  # noqa: BLE001, S110
                    pass

        unreferenced: list[str] = []
        for asset in all_assets:
            if asset.name not in all_text:
                unreferenced.append(str(asset.relative_to(self.project_root)))

        return {
            "total_assets": len(all_assets),
            "dead_assets_count": len(unreferenced),
            "dead_assets": sorted(unreferenced),
        }
