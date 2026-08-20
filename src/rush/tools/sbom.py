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

    def __call__(self, path: Path) -> ToolResult:
        return self.run(path)

    def run(
        self,
        path: Path,
        *,
        output_path: Path | None = None,
        overwrite: bool = False,
        config=None,
    ) -> ToolResult:
        start = now_ms()
        output = output_path or path / "rush-sbom.json"
        try:
            output.resolve().relative_to(path.resolve())
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
        from ..engines import ENGINES

        result = run_engine(
            ENGINES["cdxgen"], path, ["--output", str(output)], tool_name=self.name
        )
        result["artifacts"] = [str(output)] if result["status"] != "skipped" else []
        result["duration_ms"] = elapsed_ms(start)
        return result
