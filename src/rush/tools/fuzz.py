"""Fuzz tool supporting both local imported fuzz reports and bounded local execution."""

from __future__ import annotations

import importlib.metadata
import importlib.util
import json
import re
import shutil
import subprocess
import sys
import uuid
from collections.abc import Mapping
from pathlib import Path

from ..io.atomic_file import AtomicFile, AtomicWriteError
from ..safety.redactor import sanitize_value
from .base import ToolFn, ToolResult
from .common import (
    elapsed_ms,
    error_result,
    now_ms,
    run_subprocess,
    skipped_result,
)


def atheris_available() -> bool:
    return importlib.util.find_spec("atheris") is not None


class FuzzTool(ToolFn):
    """Import a local fuzz report or execute a bounded local fuzzer under --allow-slow."""

    name = "fuzz"

    @property
    def mcp_description(self) -> str:
        return (
            "Import a local fuzz report or execute local fuzz tests under --allow-slow."
        )

    def __call__(
        self,
        path: Path,
        *,
        report_path: Path | None = None,
        harness: str | None = None,
        corpus: str | None = None,
        seed: int | None = None,
        max_runs: int | None = None,
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
            ("harness", harness),
            ("corpus", corpus),
            ("seed", seed),
            ("max_runs", max_runs),
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
                    "fuzz-report",
                    f"refusing fuzz report outside target: {effective_report}",
                    duration_ms=elapsed_ms(start),
                )
            if not report.is_file():
                result = skipped_result(
                    self.name, "fuzz-report", "fuzz report is absent"
                )
                result["duration_ms"] = elapsed_ms(start)
                return result
            try:
                payload = json.loads(report.read_text(encoding="utf-8"))
                metrics = {name: int(payload[name]) for name in ("crashes", "timeouts")}
                seed = int(payload["seed"])
                if any(value < 0 for value in metrics.values()):
                    raise ValueError("negative metric")
            except (json.JSONDecodeError, KeyError, TypeError, ValueError):
                return error_result(
                    self.name,
                    "fuzz-report",
                    "fuzz report is malformed or unsupported",
                    duration_ms=elapsed_ms(start),
                )
            failures = metrics["crashes"] + metrics["timeouts"]
            return ToolResult(
                tool=self.name,
                engine="fuzz-report",
                engine_version=None,
                status="fail" if failures else "ok",
                duration_ms=elapsed_ms(start),
                summary=f"fuzz: {failures} crash(es) or timeout(s) in imported report",
                findings=[],
                raw=None,
                metrics=dict(metrics),
                artifacts=[str(effective_report)],
                metadata={
                    "evidence_source": "imported-local-report",
                    "report_format": "fuzz-json",
                    "seed": seed,
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
                f"fuzz: execution requires permission: {', '.join(missing_perms)}",
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
                    getattr(config, "tools", {}).get("fuzz") if config else None
                )
                config_options = getattr(tool_config, "options", {})
            resolved_options = resolve_tool_options("fuzz", config_options, options)
        except (RushConfigError, TypeError, ValueError, KeyError) as exc:
            return error_result(
                self.name,
                "atheris",
                f"fuzz: invalid options: {exc}",
                duration_ms=elapsed_ms(start),
            )

        harness = resolved_options.get("harness")
        corpus = resolved_options.get("corpus")
        seed = resolved_options.get("seed", 0)
        max_runs = resolved_options.get("max_runs", 1000)
        timeout_seconds = resolved_options.get("timeout_seconds", 60)
        if not isinstance(harness, (str, Path)) or not str(harness):
            return skipped_result(
                self.name,
                "atheris",
                "fuzz: harness is required",
                duration_ms=elapsed_ms(start),
                metadata={"requires_input": "harness"},
            )
        if not isinstance(corpus, (str, Path)) or not str(corpus):
            return skipped_result(
                self.name,
                "atheris",
                "fuzz: corpus is required",
                duration_ms=elapsed_ms(start),
                metadata={"requires_input": "corpus"},
            )
        if (
            any(
                isinstance(value, bool) or not isinstance(value, int) or value < 0
                for value in (seed, max_runs)
            )
            or max_runs == 0
        ):
            return error_result(
                self.name,
                "atheris",
                "fuzz: seed must be nonnegative and max_runs must be positive integers",
                duration_ms=elapsed_ms(start),
            )
        if (
            isinstance(timeout_seconds, bool)
            or not isinstance(timeout_seconds, int)
            or timeout_seconds <= 0
        ):
            return error_result(
                self.name,
                "atheris",
                "fuzz: timeout_seconds must be a positive integer",
                duration_ms=elapsed_ms(start),
            )

        root = path.resolve()
        if not root.is_dir():
            return error_result(
                self.name,
                "atheris",
                "fuzz: target project directory is absent",
                duration_ms=elapsed_ms(start),
            )

        def validate_relative(
            value: str | Path, *, directory: bool
        ) -> tuple[str, Path]:
            relative = Path(value)
            if (
                relative.is_absolute()
                or str(value).startswith("-")
                or ".." in relative.parts
            ):
                raise ValueError("workload paths must be relative contained paths")
            resolved = (root / relative).resolve(strict=True)
            if not resolved.is_relative_to(root):
                raise ValueError("workload path escapes project")
            if directory and not resolved.is_dir():
                raise ValueError("corpus must be a directory")
            if not directory and not resolved.is_file():
                raise ValueError("harness must be a file")
            if not directory and resolved.suffix != ".py":
                raise ValueError("harness must be a Python file")
            for child in resolved.rglob("*") if resolved.is_dir() else (resolved,):
                if child.is_symlink() and not child.resolve().is_relative_to(root):
                    raise ValueError("workload symlink escapes project")
            return relative.as_posix(), resolved

        try:
            harness_rel, harness_source = validate_relative(harness, directory=False)
            corpus_rel, corpus_source = validate_relative(corpus, directory=True)
        except (OSError, ValueError) as exc:
            return error_result(
                self.name,
                "atheris",
                f"fuzz: invalid workload input: {exc}",
                duration_ms=elapsed_ms(start),
            )

        if not atheris_available():
            return skipped_result(
                self.name,
                "atheris",
                "fuzz: atheris module not available",
                duration_ms=elapsed_ms(start),
                metadata={
                    "execution": build_execution_metadata(
                        "executed",
                        requested=required_perms,
                        granted=permissions,
                        producer="atheris",
                    )
                },
            )

        from ..io.physical_paths import ContainmentError, PhysicalRoot

        metadata = {
            "evidence_source": "executed-workload",
            "seed": seed,
            "max_runs": max_runs,
            "timeout_seconds": timeout_seconds,
            "execution": build_execution_metadata(
                "executed",
                requested=required_perms,
                granted=permissions,
                producer="atheris",
            ),
        }
        try:
            physical = PhysicalRoot(root)
            run_rel = Path(".rush/runs") / f"fuzz-{uuid.uuid4().hex}"
            run_root = physical.open_contained(run_rel, purpose="write")
            run_root.mkdir(parents=True)
            run_physical = PhysicalRoot(run_root)
            harness_dest = run_root / harness_rel
            harness_dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(harness_source, harness_dest)
            corpus_dest = run_root / corpus_rel
            shutil.copytree(
                corpus_source,
                corpus_dest,
                symlinks=False,
                dirs_exist_ok=True,
                ignore=shutil.ignore_patterns(".rush"),
            )
            crash_dir = run_root / "crashes"
            crash_dir.mkdir()
            argv = [
                sys.executable,
                harness_rel,
                corpus_rel,
                f"-seed={seed}",
                f"-runs={max_runs}",
                f"-max_total_time={timeout_seconds}",
                "-print_final_stats=1",
                f"-artifact_prefix={crash_dir}/",
            ]
            metadata["execution"]["argv"] = argv
            proc = run_subprocess(argv, cwd=run_root, timeout=timeout_seconds)
        except subprocess.TimeoutExpired:
            return error_result(
                self.name,
                "atheris",
                "fuzz: workload timed out",
                duration_ms=elapsed_ms(start),
                terminal_reason="timeout",
                metadata=metadata,
            )
        except (ContainmentError, OSError, ValueError) as exc:
            return error_result(
                self.name,
                "atheris",
                f"fuzz: workload failed: {exc}",
                duration_ms=elapsed_ms(start),
            )

        counters = re.findall(
            r"^stat::number_of_executed_units:\s*(\d+)\s*$",
            proc.stderr or "",
            re.MULTILINE,
        )
        iterations = int(counters[-1]) if counters else 0
        crash_files = []
        try:
            from .ship.cleaner import CleanupRegistryError, register_owned_artifact

            physical.open_contained(run_rel, purpose="read")
            crash_dir = run_physical.open_contained("crashes", purpose="read")
            for candidate in sorted(crash_dir.rglob("*")):
                candidate = run_physical.open_contained(
                    candidate.relative_to(run_root), purpose="read"
                )
                if candidate.is_file():
                    crash_files.append(candidate)
                elif not candidate.is_dir():
                    raise ValueError("reproducer must be an ordinary file")
            for crash in crash_files:
                register_owned_artifact(root, crash, "atheris", permissions=permissions)
            report = AtomicFile(run_physical).write_json(
                "fuzz-report.json",
                sanitize_value(
                    {
                        "metrics": {
                            "crashes": len(crash_files),
                            "timeouts": 0,
                            "iterations": iterations,
                        }
                    }
                ),
            )
            register_owned_artifact(root, report, "atheris", permissions=permissions)
        except (
            CleanupRegistryError,
            ContainmentError,
            AtomicWriteError,
            OSError,
            ValueError,
        ) as exc:
            return error_result(
                self.name,
                "atheris",
                str(
                    sanitize_value(f"fuzz: failed to register reproducer: {exc}").value
                ),
                duration_ms=elapsed_ms(start),
            )
        metrics = {"crashes": len(crash_files), "timeouts": 0, "iterations": iterations}
        if proc.returncode != 0 and not crash_files:
            return error_result(
                self.name,
                "atheris",
                f"fuzz: process failed with exit {proc.returncode}",
                duration_ms=elapsed_ms(start),
                metadata=metadata,
            )
        if iterations == 0:
            metadata["incomplete"] = True
            return skipped_result(
                self.name,
                "atheris",
                "fuzz: workload completed zero iterations",
                duration_ms=elapsed_ms(start),
                metadata=metadata,
            )
        try:
            version = importlib.metadata.version("atheris")
        except importlib.metadata.PackageNotFoundError:
            version = None
        return sanitize_value(
            ToolResult(
                tool=self.name,
                engine="atheris",
                engine_version=version,
                status="fail" if crash_files else "ok",
                duration_ms=elapsed_ms(start),
                summary=f"fuzz: {iterations} iteration(s), {len(crash_files)} crash(es)",
                findings=[],
                raw=proc.stderr,
                metrics=dict(metrics),
                artifacts=[*(str(p) for p in crash_files), str(report)],
                metadata=metadata,
            )
        ).value
