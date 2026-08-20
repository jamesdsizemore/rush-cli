"""Check Terraform infrastructure as code with bounded local engines."""

from __future__ import annotations

from pathlib import Path

from .common import run_engine
from .content import ContentTool
from .routing import aggregate_results, collect_files


class IacTool(ContentTool):
    name = "iac"
    engine_name = "tflint"
    engine_names = ("tflint", "checkov")
    extensions = ("tf",)

    @property
    def mcp_description(self) -> str:
        return "Check Terraform without rewriting; missing local engines return status='skipped'."

    def run(self, path: Path, *, config=None):
        """Run the declared local Terraform engines in stable adapter order."""
        del config
        from ..engines import ENGINES

        files = collect_files(path, self.extensions)
        if not files:
            return super().run(path)
        args = [str(file) for file in files]
        results = [
            run_engine(ENGINES[engine_name], path, args, tool_name=self.name)
            for engine_name in self.engine_names
        ]
        return aggregate_results(self.name, results)
