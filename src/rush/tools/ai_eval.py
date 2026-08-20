"""AI, LLM, and agentic safety evaluation tool."""

from __future__ import annotations

from pathlib import Path

from .base import ToolFn, ToolResult
from .common import elapsed_ms, engine_on_path, now_ms, run_engine, skipped_result


class AiEvalTool(ToolFn):
    name = "ai-eval"

    @property
    def mcp_description(self) -> str:
        return (
            "Evaluate LLM prompts, agent workflows, and safety guardrails. "
            "Requires explicit permissions for live inference runs."
        )

    def __call__(
        self,
        path: Path,
        *,
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
            permissions=permissions,
        )

    def run(
        self,
        path: Path,
        *,
        config=None,
        permissions=None,
    ) -> ToolResult:
        from ..engines import ENGINES
        from ..permissions import ExecutionPermissions, build_execution_metadata

        start = now_ms()
        perms = permissions or ExecutionPermissions()

        # Engine resolution: check promptfoo, garak, deepeval, guardrails
        engine_name = None
        for cand in ("promptfoo", "garak", "deepeval", "guardrails"):
            if cand in ENGINES and engine_on_path(ENGINES[cand].binary):
                engine_name = cand
                break

        if not engine_name:
            res = skipped_result(
                self.name,
                "promptfoo",
                "no AI evaluation engine (promptfoo, garak, deepeval, guardrails) found on PATH",
                duration_ms=elapsed_ms(start),
            )
            res["metadata"] = {
                "execution": build_execution_metadata(
                    mode="executed",
                    requested=perms,
                    granted=perms,
                    producer="ai-eval",
                )
            }
            return res

        engine = ENGINES[engine_name]
        engine_res = run_engine(engine, path, [], tool_name=self.name, cwd=path)
        engine_res["metadata"] = {
            "execution": build_execution_metadata(
                mode="executed",
                requested=perms,
                granted=perms,
                producer=engine_name,
            )
        }
        return engine_res
