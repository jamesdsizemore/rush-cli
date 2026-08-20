"""SBOM generation with protected output paths."""

from __future__ import annotations

from pathlib import Path

from .base import ToolFn, ToolResult
from .common import elapsed_ms, error_result, now_ms, run_engine


class SbomTool(ToolFn):
    name = "sbom"

    @property
    def mcp_description(self) -> str:
        return "Generate an SBOM only to a safe explicit output path; missing cdxgen returns status='skipped'."

    def __call__(
        self,
        path: Path,
        *,
        output_path: Path | None = None,
        overwrite: bool = False,
        allow_network: bool = False,
        allow_download: bool = False,
        allow_cache_write: bool = False,
        allow_build: bool = False,
        allow_slow: bool = False,
        allow_artifact_write: bool = False,
        allow_browser: bool = False,
    ) -> ToolResult:
        from ..permissions import ExecutionPermissions

        permissions = ExecutionPermissions(
            network=allow_network,
            download=allow_download,
            cache_write=allow_cache_write,
            build=allow_build,
            slow=allow_slow,
            artifact_write=allow_artifact_write,
            browser=allow_browser,
        )
        return self.run(
            path,
            output_path=output_path,
            overwrite=overwrite,
            permissions=permissions,
        )

    def run(
        self,
        path: Path,
        *,
        output_path: Path | None = None,
        overwrite: bool = False,
        config=None,
        permissions=None,
    ) -> ToolResult:
        from ..engines import ENGINES
        from ..permissions import ExecutionPermissions, build_execution_metadata

        start = now_ms()
        required_perms = ExecutionPermissions(artifact_write=True)
        target_dir = path if path.is_dir() else path.parent
        output = output_path or target_dir / "rush-sbom.json"

        try:
            output.resolve().relative_to(target_dir.resolve())
        except ValueError:
            return error_result(
                self.name,
                "cdxgen",
                f"refusing SBOM output outside target: {output}",
                duration_ms=elapsed_ms(start),
            )
        if output.exists() and not overwrite:
            return error_result(
                self.name,
                "cdxgen",
                f"refusing to overwrite existing SBOM: {output}",
                duration_ms=elapsed_ms(start),
            )

        result = run_engine(
            ENGINES["cdxgen"],
            path,
            ["--output", str(output)],
            tool_name=self.name,
            permissions=permissions,
            required_permissions=required_perms,
        )
        result["artifacts"] = [str(output)] if result["status"] != "skipped" else []
        result["duration_ms"] = elapsed_ms(start)
        if "metadata" not in result or result["metadata"] is None:
            result["metadata"] = {}
        result["metadata"]["execution"] = build_execution_metadata(
            "artifact",
            requested=required_perms,
            granted=permissions,
            producer="cdxgen",
            producer_version=result.get("engine_version"),
            declared_artifact=str(output),
        )
        return result
