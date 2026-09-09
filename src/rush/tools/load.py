"""Load testing tool supporting both local imported reports and execution."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import stat
import subprocess
import uuid
from collections.abc import Mapping
from pathlib import Path
from urllib.parse import urlparse

from ..safety.redactor import sanitize_value
from .base import ToolFn, ToolResult
from .common import (
    elapsed_ms,
    engine_on_path,
    error_result,
    now_ms,
    run_subprocess,
    skipped_result,
)


class LoadTool(ToolFn):
    """Import a local load report or execute load traffic under --allow-network."""

    name = "load"

    @property
    def mcp_description(self) -> str:
        return (
            "Import a local load report or execute load traffic under --allow-network."
        )

    def __call__(
        self,
        path: Path,
        *,
        report_path: Path | None = None,
        script: str | Path | None = None,
        target_url: str | None = None,
        vus: int | None = None,
        duration_seconds: int | None = None,
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
        return self.run(
            path,
            report_path=report_path,
            permissions=permissions,
            script=script,
            target_url=target_url,
            vus=vus,
            duration_seconds=duration_seconds,
            timeout_seconds=timeout_seconds,
            **options,
        )

    def run(
        self,
        path: Path,
        *,
        report_path: Path | None = None,
        script: str | Path | None = None,
        target_url: str | None = None,
        vus: int | None = None,
        duration_seconds: int | None = None,
        timeout_seconds: int | None = None,
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
                    "load-report",
                    f"refusing load report outside target: {effective_report}",
                    duration_ms=elapsed_ms(start),
                )
            if not report.is_file():
                result = skipped_result(
                    self.name, "load-report", "load report is absent"
                )
                result["duration_ms"] = elapsed_ms(start)
                return result
            try:
                payload = json.loads(report.read_text(encoding="utf-8"))
                metrics = {
                    name: int(payload[name])
                    for name in (
                        "failed_requests",
                        "total_requests",
                        "duration_seconds",
                    )
                }
                if any(value < 0 for value in metrics.values()):
                    raise ValueError("negative metric")
            except (json.JSONDecodeError, KeyError, TypeError, ValueError):
                return error_result(
                    self.name,
                    "load-report",
                    "load report is malformed or unsupported",
                    duration_ms=elapsed_ms(start),
                )
            return ToolResult(
                tool=self.name,
                engine="load-report",
                engine_version=None,
                status="fail" if metrics["failed_requests"] else "ok",
                duration_ms=elapsed_ms(start),
                summary=f"load: {metrics['failed_requests']} failed request(s) in imported report",
                findings=[],
                raw=None,
                metrics=dict(metrics),
                artifacts=[str(effective_report)],
                metadata={
                    "evidence_source": "imported-local-report",
                    "report_format": "load-json",
                    "target_contacted": False,
                    "execution": build_execution_metadata(
                        "imported",
                        granted=permissions,
                        report_path=str(effective_report),
                    ),
                },
            )

        # 2. Executed mode
        required_perms = ExecutionPermissions(
            network=True, slow=True, artifact_write=True
        )
        is_satisfied, missing_perms = check_permissions(required_perms, permissions)
        if not is_satisfied:
            return skipped_result(
                self.name,
                None,
                f"load: execution requires permission: {', '.join(missing_perms)}",
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
                    getattr(config, "tools", {}).get("load") if config else None
                )
                config_options = getattr(tool_config, "options", {})
            invocation_options = dict(options)
            for name, value in {
                "script": script,
                "target_url": target_url,
                "vus": vus,
                "duration_seconds": duration_seconds,
                "timeout_seconds": timeout_seconds,
            }.items():
                if value is not None:
                    invocation_options[name] = value
            resolved_options = resolve_tool_options(
                "load", config_options, invocation_options
            )
        except (RushConfigError, TypeError, ValueError, KeyError) as exc:
            return error_result(
                self.name,
                "k6",
                sanitize_value(f"load: invalid options: {exc}").value,
                duration_ms=elapsed_ms(start),
            )

        script = resolved_options.get("script")
        target_url = resolved_options.get("target_url")
        vus = resolved_options.get("vus", 1)
        duration_seconds = resolved_options.get("duration_seconds", 10)
        timeout_seconds = resolved_options.get("timeout_seconds", 60)
        if not isinstance(script, (str, Path)) or not str(script):
            return skipped_result(
                self.name,
                "k6",
                "load: script is required",
                duration_ms=elapsed_ms(start),
                metadata={"requires_input": "script"},
            )
        if not target_url:
            return skipped_result(
                self.name,
                "k6",
                "load: target_url is required",
                duration_ms=elapsed_ms(start),
                metadata={"requires_input": "target_url"},
            )
        try:
            parsed_url = urlparse(target_url)
            if parsed_url.scheme not in {"http", "https"} or not parsed_url.hostname:
                raise ValueError("invalid HTTP(S) URL")
            _ = parsed_url.port
        except ValueError:
            return error_result(
                self.name,
                "k6",
                "load: target_url must be an explicit HTTP(S) URL",
                duration_ms=elapsed_ms(start),
            )
        if any(
            isinstance(value, bool) or not isinstance(value, int) or value <= 0
            for value in (vus, duration_seconds, timeout_seconds)
        ):
            return error_result(
                self.name,
                "k6",
                "load: limits must be positive integers",
                duration_ms=elapsed_ms(start),
            )
        if duration_seconds > timeout_seconds:
            return error_result(
                self.name,
                "k6",
                "load: duration_seconds cannot exceed timeout_seconds",
                duration_ms=elapsed_ms(start),
            )
        root = path.resolve()
        if not root.is_dir():
            return error_result(
                self.name,
                "k6",
                "load: target project directory is absent",
                duration_ms=elapsed_ms(start),
            )
        try:
            relative = Path(script)
            if (
                relative.is_absolute()
                or str(script).startswith("-")
                or ".." in relative.parts
            ):
                raise ValueError("script must be a relative contained path")
            source = (root / relative).resolve(strict=True)
            if (
                not source.is_relative_to(root)
                or not source.is_file()
                or source.suffix != ".js"
            ):
                raise ValueError("script must be a contained JavaScript file")
            if any(
                child.is_symlink() and not child.resolve().is_relative_to(root)
                for child in (source,)
            ):
                raise ValueError("script symlink escapes project")
        except (OSError, ValueError) as exc:
            return error_result(
                self.name,
                "k6",
                sanitize_value(f"load: invalid script: {exc}").value,
                duration_ms=elapsed_ms(start),
            )

        if not engine_on_path("k6"):
            return skipped_result(
                self.name,
                "k6",
                "load: k6 engine not available on PATH",
                duration_ms=elapsed_ms(start),
                metadata={
                    "execution": build_execution_metadata(
                        "executed",
                        requested=required_perms,
                        granted=permissions,
                        producer="k6",
                    )
                },
            )

        from ..io.physical_paths import ContainmentError, PhysicalRoot

        try:
            physical = PhysicalRoot(root)
            run_rel = Path(".rush/runs") / f"load-{uuid.uuid4().hex}"
            run_root = physical.open_contained(run_rel, purpose="write")
            run_root.mkdir(parents=True)
            script_dest = run_root / relative
            script_dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, script_dest)
            report = run_root / "k6-summary.json"
            env = os.environ.copy()
            env["K6_NO_USAGE_REPORT"] = "true"
            env["RUSH_TARGET_URL"] = str(target_url)
            version_proc = run_subprocess(
                ["k6", "version"], cwd=run_root, timeout=timeout_seconds, env=env
            )
            if version_proc.returncode != 0:
                raise RuntimeError("k6 version command failed")
            version = next(
                (
                    token.lstrip("v")
                    for token in version_proc.stdout.split()
                    if token.lstrip("v")[0:1].isdigit()
                ),
                None,
            )
            if not version:
                raise RuntimeError("k6 version output unavailable")
            argv = [
                "k6",
                "run",
                "--vus",
                str(vus),
                "--duration",
                f"{duration_seconds}s",
                "--summary-export",
                str(report),
                str(relative),
            ]
            proc = run_subprocess(argv, cwd=run_root, timeout=timeout_seconds, env=env)
        except subprocess.TimeoutExpired:
            return error_result(
                self.name,
                "k6",
                "load: workload timed out",
                duration_ms=elapsed_ms(start),
                terminal_reason="timeout",
                metadata={
                    "seed": None,
                    "vus": vus,
                    "duration_seconds": duration_seconds,
                    "timeout_seconds": timeout_seconds,
                    "execution": build_execution_metadata(
                        "executed",
                        requested=required_perms,
                        granted=permissions,
                        producer="k6",
                    ),
                },
            )
        except (ContainmentError, OSError, ValueError, RuntimeError) as exc:
            return error_result(
                self.name,
                "k6",
                sanitize_value(f"load: workload failed: {exc}").value,
                duration_ms=elapsed_ms(start),
            )
        try:
            report = physical.open_contained(
                run_rel / "k6-summary.json", purpose="read"
            )
            expected = report.lstat()
            if not stat.S_ISREG(expected.st_mode):
                raise ValueError("summary is not an ordinary file")
            with report.open("rb") as handle:
                opened = os.fstat(handle.fileno())
                if (opened.st_dev, opened.st_ino) != (expected.st_dev, expected.st_ino):
                    raise ValueError("summary identity changed")
                report_bytes = handle.read()
            report_sha256 = hashlib.sha256(report_bytes).hexdigest()
            payload = json.loads(report_bytes)
            metrics_payload = payload["metrics"]
            total_requests = metrics_payload["http_reqs"]["count"]
            # k6 legacy export counts true http_req_failed samples as passes.
            failed_requests = metrics_payload["http_req_failed"]["passes"]
            successful_requests = metrics_payload["http_req_failed"]["fails"]
            if (
                any(
                    type(value) is not int or value < 0
                    for value in (total_requests, failed_requests, successful_requests)
                )
                or failed_requests + successful_requests != total_requests
            ):
                raise ValueError("invalid request counts")
            threshold_failed = False
            for metric in metrics_payload.values():
                if not isinstance(metric, dict):
                    raise TypeError("invalid metric")
                thresholds = metric.get("thresholds", {})
                if not isinstance(thresholds, dict) or any(
                    type(value) is not bool for value in thresholds.values()
                ):
                    raise ValueError("invalid thresholds")
                threshold_failed |= any(thresholds.values())
        except (
            ContainmentError,
            OSError,
            json.JSONDecodeError,
            KeyError,
            TypeError,
            ValueError,
        ) as exc:
            return error_result(
                self.name,
                "k6",
                sanitize_value(f"load: malformed k6 summary: {exc}").value,
                duration_ms=elapsed_ms(start),
            )
        try:
            from .ship.cleaner import register_owned_artifact

            entry = register_owned_artifact(root, report, "k6", permissions=permissions)
            if (entry["sha256"], entry["device"], entry["inode"]) != (
                report_sha256,
                opened.st_dev,
                opened.st_ino,
            ):
                raise ValueError("summary changed during registration")
        except (OSError, ValueError, PermissionError) as exc:
            return error_result(
                self.name,
                "k6",
                sanitize_value(f"load: failed to register report: {exc}").value,
                duration_ms=elapsed_ms(start),
            )
        metrics = {"total_requests": total_requests, "failed_requests": failed_requests}
        metadata = sanitize_value(
            {
                "evidence_source": "executed-workload",
                "target_contacted": total_requests > 0,
                "threshold_failed": threshold_failed,
                "report_sha256": report_sha256,
                "raw_artifact_sha256": report_sha256,
                "execution": build_execution_metadata(
                    "executed",
                    requested=required_perms,
                    granted=permissions,
                    producer="k6",
                    producer_version=version,
                    report_path=str(report),
                    extra={"target_url": str(target_url)},
                ),
            }
        ).value
        if proc.returncode not in (0, 99):
            return error_result(
                self.name,
                "k6",
                f"load: process failed with exit {proc.returncode}",
                duration_ms=elapsed_ms(start),
                metadata=metadata,
            )
        if total_requests == 0:
            return skipped_result(
                self.name,
                "k6",
                "load: incomplete workload; no HTTP requests",
                duration_ms=elapsed_ms(start),
                metadata=metadata,
            )
        return ToolResult(
            tool=self.name,
            engine="k6",
            engine_version=version,
            status="fail" if threshold_failed or proc.returncode == 99 else "ok",
            duration_ms=elapsed_ms(start),
            summary=f"load: {failed_requests} failed of {total_requests} requests",
            findings=[],
            raw=sanitize_value(payload).value,
            metrics=dict(metrics),
            artifacts=[str(report)],
            metadata=metadata,
        )
