"""AI, LLM, and agentic safety evaluation tool."""

from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from .base import ToolFn, ToolResult
from .common import (
    elapsed_ms,
    engine_on_path,
    error_result,
    now_ms,
    run_engine,
    skipped_result,
)


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
        from ..io.physical_paths import ContainmentError, PhysicalRoot
        from ..permissions import (
            ExecutionPermissions,
            build_execution_metadata,
            check_permissions,
        )
        from ..safety.redactor import sanitize_value

        start = now_ms()
        perms = permissions or ExecutionPermissions()
        required = ExecutionPermissions(network=True, slow=True, artifact_write=True)
        if isinstance(config, dict) and any(
            key in config
            for key in ("pre_build", "pre_build_command", "pre_build_commands")
        ):
            return error_result(
                self.name,
                "ai-eval",
                "pre-build commands are unsupported for ai-eval",
                duration_ms=elapsed_ms(start),
            )
        granted, missing = check_permissions(required, perms)
        if not granted:
            res = skipped_result(
                self.name,
                "ai-eval",
                f"requires permission: {', '.join(missing)}",
                duration_ms=elapsed_ms(start),
            )
            res["metadata"] = {
                "execution": build_execution_metadata(
                    mode="executed",
                    requested=required,
                    granted=perms,
                    producer="ai-eval",
                )
            }
            return res

        engine_name = next(
            (
                cand
                for cand in ("promptfoo", "garak", "deepeval", "guardrails")
                if cand in ENGINES and engine_on_path(ENGINES[cand].binary)
            ),
            None,
        )

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
                    requested=required,
                    granted=perms,
                    producer="ai-eval",
                )
            }
            return res

        try:
            physical = PhysicalRoot(path if path.is_dir() else path.parent)
            path = (
                physical.root_path
                if path.is_dir()
                else physical.open_contained(path.name, purpose="read")
            )
            report_dir = physical.open_contained(
                f".rush/runs/ai-eval-{uuid4().hex}", purpose="write"
            )
            report_dir.mkdir(parents=True)
        except (ContainmentError, OSError) as exc:
            return error_result(
                self.name,
                engine_name,
                str(sanitize_value(str(exc)).value),
                duration_ms=elapsed_ms(start),
            )
        engine = ENGINES[engine_name]
        config_path = (
            path
            if path.is_file()
            else next(
                (
                    candidate
                    for candidate in (
                        path / "promptfooconfig.yaml",
                        path / "promptfooconfig.yml",
                        path / "promptfooconfig.json",
                    )
                    if candidate.is_file()
                ),
                None,
            )
        )
        engine_args = (
            ["--config", str(config_path)]
            if engine_name == "promptfoo" and config_path is not None
            else []
        )
        engine_res = run_engine(
            engine,
            path,
            engine_args,
            tool_name=self.name,
            cwd=report_dir,
            permissions=perms,
            required_permissions=required,
        )
        engine_res = sanitize_value(engine_res).value
        execution = engine_res.setdefault("metadata", {}).setdefault(
            "execution",
            build_execution_metadata(
                mode="executed",
                requested=required,
                granted=perms,
                producer=engine_name,
            ),
        )
        execution["report_path"] = str(report_dir)
        return engine_res
