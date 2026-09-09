"""Mutation tool supporting both local imported mutation reports and execution."""

from __future__ import annotations

import json
import os
import shutil
import uuid
from collections.abc import Mapping
from pathlib import Path

from .base import ToolFn, ToolResult
from .common import (
    elapsed_ms,
    engine_on_path,
    error_result,
    now_ms,
    run_subprocess,
    skipped_result,
)


class MutationTool(ToolFn):
    """Import a local mutation report or run mutation testing under explicit permissions."""

    name = "mutation"

    @property
    def mcp_description(self) -> str:
        return (
            "Import a local mutation report or run mutation testing under --allow-slow."
        )

    def __call__(
        self,
        path: Path,
        *,
        report_path: Path | None = None,
        source_paths: list[str] | None = None,
        test_paths: list[str] | None = None,
        timeout_seconds: int | None = None,
        allow_network: bool = False,
        allow_download: bool = False,
        allow_cache_write: bool = False,
        allow_build: bool = False,
        allow_slow: bool = False,
        allow_artifact_write: bool = False,
        allow_browser: bool = False,
        **options: object,
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
        for name, value in (
            ("source_paths", source_paths),
            ("test_paths", test_paths),
            ("timeout_seconds", timeout_seconds),
        ):
            if value is not None:
                options[name] = value
        return self.run(
            path, report_path=report_path, permissions=permissions, **options
        )

    def run(
        self,
        path: Path,
        *,
        report_path: Path | None = None,
        config=None,
        permissions=None,
        **options: object,
    ) -> ToolResult:
        from ..permissions import (
            ExecutionPermissions,
            build_execution_metadata,
            check_permissions,
        )

        start = now_ms()

        # 1. Imported mode
        if report_path is not None or path.is_file():
            effective_report = report_path or path
            root = path.resolve() if path.is_dir() else path.parent.resolve()
            report = effective_report.resolve()
            try:
                report.relative_to(root)
            except ValueError:
                return error_result(
                    self.name,
                    "mutation-report",
                    f"refusing mutation report outside target: {effective_report}",
                    duration_ms=elapsed_ms(start),
                )
            if not report.is_file():
                result = skipped_result(
                    self.name, "mutation-report", "mutation report is absent"
                )
                result["duration_ms"] = elapsed_ms(start)
                return result
            try:
                payload = json.loads(report.read_text(encoding="utf-8"))
                metrics = {
                    name: int(payload[name])
                    for name in ("killed", "survived", "timeout")
                }
                if any(value < 0 for value in metrics.values()):
                    raise ValueError("negative metric")
            except (json.JSONDecodeError, KeyError, TypeError, ValueError):
                return error_result(
                    self.name,
                    "mutation-report",
                    "mutation report is malformed or unsupported",
                    duration_ms=elapsed_ms(start),
                )
            escaped = metrics["survived"] + metrics["timeout"]
            return ToolResult(
                tool=self.name,
                engine="mutation-report",
                engine_version=None,
                status="fail" if escaped else "ok",
                duration_ms=elapsed_ms(start),
                summary=f"mutation: {escaped} mutant(s) survived or timed out",
                findings=[],
                raw=None,
                metrics=metrics,
                artifacts=[str(effective_report)],
                metadata={
                    "evidence_source": "imported-local-report",
                    "report_format": "mutation-json",
                    "execution": build_execution_metadata(
                        "imported",
                        granted=permissions,
                        report_path=str(effective_report),
                    ),
                },
            )

        # 2. Executed mode
        required_perms = ExecutionPermissions(
            build=True, slow=True, artifact_write=True
        )
        is_satisfied, missing_perms = check_permissions(required_perms, permissions)
        if not is_satisfied:
            return skipped_result(
                self.name,
                None,
                f"mutation: execution requires permission: {', '.join(missing_perms)}",
                duration_ms=elapsed_ms(start),
                metadata={
                    "execution": build_execution_metadata(
                        "executed",
                        requested=required_perms,
                        granted=permissions,
                    )
                },
            )

        try:
            from ..config import RushConfigError, load_config, resolve_tool_options

            if config is None:
                config = load_config(path)
            if isinstance(config, Mapping):
                config_options = config.get("options", config)
            else:
                tool_config = (
                    getattr(config, "tools", {}).get("mutation") if config else None
                )
                config_options = getattr(tool_config, "options", {})
            resolved_options = resolve_tool_options("mutation", config_options, options)
        except (RushConfigError, TypeError, ValueError, KeyError) as exc:
            return error_result(
                self.name,
                "mutmut",
                f"mutation: invalid options: {exc}",
                duration_ms=elapsed_ms(start),
            )
        source_paths = resolved_options.get("source_paths")
        test_paths = resolved_options.get("test_paths")
        timeout_seconds = resolved_options.get("timeout_seconds", 300)
        if not isinstance(source_paths, (list, tuple)) or not source_paths:
            return skipped_result(
                self.name,
                "mutmut",
                "mutation: source_paths is required",
                duration_ms=elapsed_ms(start),
                metadata={
                    "requires_input": "source_paths",
                    "execution": build_execution_metadata(
                        "executed", requested=required_perms, granted=permissions
                    ),
                },
            )
        if not isinstance(test_paths, (list, tuple)) or not test_paths:
            return skipped_result(
                self.name,
                "mutmut",
                "mutation: test_paths is required",
                duration_ms=elapsed_ms(start),
                metadata={
                    "requires_input": "test_paths",
                    "execution": build_execution_metadata(
                        "executed", requested=required_perms, granted=permissions
                    ),
                },
            )
        if (
            isinstance(timeout_seconds, bool)
            or not isinstance(timeout_seconds, int)
            or timeout_seconds <= 0
        ):
            return error_result(
                self.name,
                "mutmut",
                "mutation: timeout_seconds must be a positive integer",
                duration_ms=elapsed_ms(start),
            )

        root = path.resolve()
        if not root.is_dir():
            return error_result(
                self.name,
                "mutmut",
                "mutation: target project directory is absent",
                duration_ms=elapsed_ms(start),
            )

        def validate_inputs(values: list | tuple) -> list[tuple[str, Path]]:
            validated = []
            for value in values:
                if (
                    not isinstance(value, (str, Path))
                    or not str(value)
                    or Path(value).is_absolute()
                ):
                    raise ValueError("workload paths must be relative contained paths")
                relative = Path(value)
                if ".." in relative.parts or str(value).startswith("-"):
                    raise ValueError("workload paths must be relative contained paths")
                candidate = root / relative
                resolved = candidate.resolve(strict=True)
                resolved.relative_to(root)
                if not resolved.is_file() and not resolved.is_dir():
                    raise ValueError(
                        f"workload path is not a file or directory: {value}"
                    )
                if resolved.is_dir():
                    for child in resolved.rglob("*"):
                        if child.is_symlink() and not child.resolve().is_relative_to(
                            root
                        ):
                            raise ValueError(
                                f"workload path symlink escapes project: {value}"
                            )
                validated.append((relative.as_posix(), resolved))
            return validated

        try:
            sources = validate_inputs(source_paths)
            tests = validate_inputs(test_paths)
        except (OSError, ValueError) as exc:
            return error_result(
                self.name,
                "mutmut",
                f"mutation: invalid workload input: {exc}",
                duration_ms=elapsed_ms(start),
            )

        if not engine_on_path("mutmut"):
            return skipped_result(
                self.name,
                "mutmut",
                "mutation: mutmut engine not available on PATH",
                duration_ms=elapsed_ms(start),
                metadata={
                    "execution": build_execution_metadata(
                        "executed",
                        requested=required_perms,
                        granted=permissions,
                        producer="mutmut",
                    )
                },
            )

        if os.name == "nt":
            return skipped_result(
                self.name,
                "mutmut",
                "mutation: mutmut is unsupported on native Windows; run on Linux CI",
                duration_ms=elapsed_ms(start),
                metadata={"unsupported_platform": "native-windows"},
            )
        from ..io.physical_paths import ContainmentError, PhysicalRoot

        try:
            physical = PhysicalRoot(root)
            run_relative = Path(".rush/runs") / f"mutation-{uuid.uuid4().hex}"
            run_root = physical.open_contained(run_relative, purpose="write")
            run_root.mkdir(parents=True)
        except (ContainmentError, OSError, ValueError) as exc:
            return error_result(
                self.name,
                "mutmut",
                f"mutation: cannot create isolated run root: {exc}",
                duration_ms=elapsed_ms(start),
            )
        try:
            for relative, source in [*sources, *tests]:
                destination = run_root / relative
                destination.parent.mkdir(parents=True, exist_ok=True)
                if source.is_dir():
                    shutil.copytree(
                        source,
                        destination,
                        symlinks=False,
                        dirs_exist_ok=True,
                        ignore=shutil.ignore_patterns(".rush"),
                    )
                else:
                    shutil.copy2(source, destination)
            (run_root / "pyproject.toml").write_text(
                "[tool.mutmut]\n"
                f"source_paths = {json.dumps([relative for relative, _ in sources])}\n"
                f"pytest_add_cli_args_test_selection = {json.dumps([relative for relative, _ in tests])}\n",
                encoding="utf-8",
            )
            version_proc = run_subprocess(
                ["mutmut", "--version"], cwd=run_root, timeout=timeout_seconds
            )
            if version_proc.returncode != 0:
                raise RuntimeError("mutmut version command failed")
            version = next(
                (
                    token.lstrip("v")
                    for token in version_proc.stdout.split()
                    if any(char.isdigit() for char in token)
                ),
                None,
            )
            if not version:
                raise RuntimeError("mutmut version output is unavailable")
            workload_proc = run_subprocess(
                ["mutmut", "run"], cwd=run_root, timeout=timeout_seconds
            )
            if workload_proc.returncode != 0:
                raise RuntimeError(
                    f"mutmut run failed with exit {workload_proc.returncode}"
                )
            export_proc = run_subprocess(
                ["mutmut", "export-cicd-stats"], cwd=run_root, timeout=timeout_seconds
            )
            if export_proc.returncode != 0:
                raise RuntimeError(
                    f"mutmut export-cicd-stats failed with exit {export_proc.returncode}"
                )
            report = run_root / "mutants" / "mutmut-cicd-stats.json"
            from .ship.cleaner import register_owned_artifact

            register_owned_artifact(root, report, "mutmut", permissions=permissions)
            payload = json.loads(report.read_text(encoding="utf-8"))
            interrupted = payload.get("check_was_interrupted_by_user", 0)
            if not isinstance(interrupted, (bool, int)) or interrupted < 0:
                raise ValueError(
                    "mutation report contains an invalid interruption count"
                )
            if interrupted:
                return error_result(
                    self.name,
                    "mutmut",
                    "mutation workload interrupted by user",
                    duration_ms=elapsed_ms(start),
                    terminal_reason="cancelled",
                    metadata={"artifacts": [str(report)]},
                )
            names = (
                "total",
                "killed",
                "survived",
                "timeout",
                "no_tests",
                "skipped",
                "suspicious",
                "segfault",
            )
            values = {name: payload[name] for name in names}
            if any(
                isinstance(value, bool) or not isinstance(value, int) or value < 0
                for value in values.values()
            ):
                raise ValueError("mutation report contains invalid counts")
            metrics = {
                "generated": values["total"],
                "killed": values["killed"],
                "survived": values["survived"],
                "timeout": values["timeout"],
                "untested": values["no_tests"] + values["skipped"],
                "incompetent": values["suspicious"] + values["segfault"],
            }
            if metrics["generated"] != sum(
                metrics[name]
                for name in ("killed", "survived", "timeout", "untested", "incompetent")
            ):
                raise ValueError(
                    "mutation report counts do not conserve generated mutants"
                )
            escaped = metrics["survived"] + metrics["timeout"] + metrics["untested"]
            status = (
                "skipped"
                if metrics["generated"] == 0
                else ("fail" if escaped else "ok")
            )
            return ToolResult(
                tool=self.name,
                engine="mutmut",
                engine_version=version,
                status=status,
                duration_ms=elapsed_ms(start),
                summary=f"mutation: {metrics['generated']} generated, {escaped} escaped",
                findings=[],
                raw=payload,
                metrics=metrics,
                artifacts=[str(report)],
                metadata={
                    "evidence_source": "executed-workload",
                    "incomplete": metrics["generated"] == 0,
                    "source_paths": [relative for relative, _ in sources],
                    "test_paths": [relative for relative, _ in tests],
                    "execution": build_execution_metadata(
                        "executed",
                        requested=required_perms,
                        granted=permissions,
                        producer="mutmut",
                        producer_version=version,
                        report_path=str(report),
                    ),
                },
            )
        except Exception as exc:  # noqa: BLE001
            return error_result(
                self.name,
                "mutmut",
                f"mutation: workload failed: {exc}",
                duration_ms=elapsed_ms(start),
            )
