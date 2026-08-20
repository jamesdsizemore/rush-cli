"""Release planning with an explicit no-publication default."""

from __future__ import annotations

from pathlib import Path

from .base import ToolFn, ToolResult
from .common import elapsed_ms, now_ms, skipped_result


class ReleaseTool(ToolFn):
    name = "release"

    @property
    def mcp_description(self) -> str:
        return (
            "Create a dry-run release plan; publishing requires explicit confirmation."
        )

    def __call__(self, path: Path) -> ToolResult:
        return self.run(path)

    def run(
        self, path: Path, *, publish: bool = False, confirm: bool = False, config=None
    ) -> ToolResult:
        start = now_ms()
        if publish and not confirm:
            result = skipped_result(
                self.name, None, "publication requires explicit confirmation"
            )
        elif publish:
            result = skipped_result(
                self.name,
                None,
                "publication execution is intentionally unavailable in this local tool",
            )
        else:
            artifacts = _local_dist_artifacts(path)
            from .common import engine_on_path

            findings = []
            if engine_on_path("cejel"):
                from ..engines import ENGINES
                from .common import run_engine

                cejel_res = run_engine(ENGINES["cejel"], path, [], tool_name=self.name)
                findings.extend(cejel_res.get("findings", []))

            status = "fail" if findings else "ok"
            result = ToolResult(
                tool=self.name,
                engine="builtin+cejel" if engine_on_path("cejel") else "builtin",
                engine_version=None,
                status=status,
                duration_ms=0,
                summary=(
                    "release dry-run plan; no tag, release, or upload was created; "
                    f"{len(artifacts)} local artifact(s) found"
                ),
                findings=findings,
                raw=None,
                artifacts=artifacts,
                metadata={
                    "dry_run": True,
                    "publish": False,
                    "artifact_count": len(artifacts),
                    "artifact_source": "local-dist",
                },
            )
        result["duration_ms"] = elapsed_ms(start)
        return result


def _local_dist_artifacts(path: Path) -> list[str]:
    """List local built artifacts without creating, hashing, or uploading them."""
    root = path if path.is_dir() else path.parent
    dist = root / "dist"
    if not dist.is_dir():
        return []
    return [
        str(candidate) for candidate in sorted(dist.iterdir()) if candidate.is_file()
    ]
