"""Contract tool supporting both local imported Pact reports and local execution."""

from __future__ import annotations

import hashlib
import json
import os
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


class ContractTool(ToolFn):
    """Import a local Pact report or run local contract tests without network."""

    name = "contract"

    @property
    def mcp_description(self) -> str:
        return "Import a local Pact report or run local contract verifications under --allow-slow."

    def __call__(
        self,
        path: Path,
        *,
        report_path: Path | None = None,
        pact_files: list[str] | tuple[str, ...] | None = None,
        provider_url: str | None = None,
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
            pact_files=pact_files,
            provider_url=provider_url,
            timeout_seconds=timeout_seconds,
            permissions=permissions,
            **options,
        )

    def run(
        self,
        path: Path,
        *,
        report_path: Path | None = None,
        pact_files: list[str] | tuple[str, ...] | None = None,
        provider_url: str | None = None,
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
                    "pact-report",
                    f"refusing contract report outside target: {effective_report}",
                    duration_ms=elapsed_ms(start),
                )
            if not report.is_file():
                result = skipped_result(
                    self.name, "pact-report", "contract report is absent"
                )
                result["duration_ms"] = elapsed_ms(start)
                return result
            try:
                payload = json.loads(report.read_text(encoding="utf-8"))
                summary = payload["summary"]
                errors = int(summary["errors"])
                warnings = int(summary.get("warnings", 0))
                if errors < 0 or warnings < 0:
                    raise ValueError("negative counts")
            except (json.JSONDecodeError, KeyError, TypeError, ValueError):
                return error_result(
                    self.name,
                    "pact-report",
                    "contract report is malformed or unsupported",
                    duration_ms=elapsed_ms(start),
                )

            status = "fail" if errors else "warn" if warnings else "ok"
            return ToolResult(
                tool=self.name,
                engine="pact-report",
                engine_version=None,
                status=status,
                duration_ms=elapsed_ms(start),
                summary=f"contract: {errors} error(s), {warnings} warning(s) in imported report",
                findings=[],
                raw=None,
                metrics={"errors": errors, "warnings": warnings},
                artifacts=[str(effective_report)],
                metadata={
                    "evidence_source": "imported-local-report",
                    "report_format": "pact",
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
                f"contract: execution requires permission: {', '.join(missing_perms)}",
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
                    getattr(config, "tools", {}).get("contract") if config else None
                )
                config_options = getattr(tool_config, "options", {})
            invocation_options = dict(options)
            for name, value in {
                "pact_files": pact_files,
                "provider_url": provider_url,
                "timeout_seconds": timeout_seconds,
            }.items():
                if value is not None:
                    invocation_options[name] = value
            resolved_options = resolve_tool_options(
                "contract", config_options, invocation_options
            )
        except (RushConfigError, TypeError, ValueError, KeyError) as exc:
            return error_result(
                self.name,
                "pact-provider-verifier",
                sanitize_value(f"contract: invalid options: {exc}").value,
                duration_ms=elapsed_ms(start),
            )

        pact_files = resolved_options.get("pact_files")
        provider_url = resolved_options.get("provider_url")
        timeout_seconds = resolved_options.get("timeout_seconds", 60)
        if not pact_files:
            return skipped_result(
                self.name,
                "pact-provider-verifier",
                "contract: pact_files is required",
                duration_ms=elapsed_ms(start),
                metadata={"requires_input": "pact_files"},
            )
        if not isinstance(pact_files, (list, tuple)) or any(
            not isinstance(item, str) or not item for item in pact_files
        ):
            return error_result(
                self.name,
                "pact-provider-verifier",
                "contract: pact_files must be a nonempty path list",
                duration_ms=elapsed_ms(start),
            )
        if not provider_url:
            return skipped_result(
                self.name,
                "pact-provider-verifier",
                "contract: provider_url is required",
                duration_ms=elapsed_ms(start),
                metadata={"requires_input": "provider_url"},
            )
        try:
            if not isinstance(provider_url, str):
                raise TypeError("invalid HTTP(S) URL")
            parsed_url = urlparse(provider_url)
            if parsed_url.scheme not in {"http", "https"} or not parsed_url.hostname:
                raise ValueError("invalid HTTP(S) URL")
            _ = parsed_url.port
        except (TypeError, ValueError):
            return error_result(
                self.name,
                "pact-provider-verifier",
                "contract: provider_url must be an explicit HTTP(S) URL",
                duration_ms=elapsed_ms(start),
            )
        if (
            isinstance(timeout_seconds, bool)
            or not isinstance(timeout_seconds, int)
            or timeout_seconds <= 0
        ):
            return error_result(
                self.name,
                "pact-provider-verifier",
                "contract: timeout_seconds must be a positive integer",
                duration_ms=elapsed_ms(start),
            )

        root = path.resolve()
        if not root.is_dir():
            return error_result(
                self.name,
                "pact-provider-verifier",
                "contract: target project directory is absent",
                duration_ms=elapsed_ms(start),
            )

        from ..io.physical_paths import ContainmentError, PhysicalRoot

        try:
            physical = PhysicalRoot(root)
            snapshots: list[tuple[Path, bytes, list[str]]] = []
            seen: set[str] = set()
            for item in pact_files:
                relative = Path(item)
                normalized = relative.as_posix()
                if (
                    relative.is_absolute()
                    or item.startswith("-")
                    or ".." in relative.parts
                    or normalized in seen
                ):
                    raise ValueError(
                        "pact path must be unique, relative, and contained"
                    )
                seen.add(normalized)
                source = physical.open_contained(relative, purpose="read")
                expected = source.lstat()
                if not stat.S_ISREG(expected.st_mode):
                    raise ValueError("pact must be an ordinary file")
                with source.open("rb") as handle:
                    opened = os.fstat(handle.fileno())
                    if (opened.st_dev, opened.st_ino) != (
                        expected.st_dev,
                        expected.st_ino,
                    ):
                        raise ValueError("pact identity changed")
                    content = handle.read()
                pact_payload = json.loads(content)
                interactions = pact_payload["interactions"]
                if not isinstance(interactions, list):
                    raise TypeError("pact interactions must be a list")
                descriptions: list[str] = []
                for interaction in interactions:
                    if not isinstance(interaction, dict) or not isinstance(
                        interaction.get("description"), str
                    ):
                        raise TypeError("pact interaction description is invalid")
                    descriptions.append(interaction["description"])
                snapshots.append((relative, content, descriptions))
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
                "pact-provider-verifier",
                sanitize_value(f"contract: invalid pact input: {exc}").value,
                duration_ms=elapsed_ms(start),
            )

        if not engine_on_path("pact-provider-verifier"):
            return skipped_result(
                self.name,
                "pact-provider-verifier",
                "contract: pact-provider-verifier engine not available on PATH",
                duration_ms=elapsed_ms(start),
                metadata={
                    "execution": build_execution_metadata(
                        "executed",
                        requested=required_perms,
                        granted=permissions,
                        producer="pact-provider-verifier",
                    )
                },
            )

        try:
            run_rel = Path(".rush/runs") / f"contract-{uuid.uuid4().hex}"
            run_root = physical.open_contained(run_rel, purpose="write")
            run_root.mkdir(parents=True)
            copied: list[tuple[Path, list[str]]] = []
            for relative, content, descriptions in snapshots:
                destination = physical.open_contained(
                    run_rel / relative, purpose="write"
                )
                destination.parent.mkdir(parents=True, exist_ok=True)
                with destination.open("xb") as handle:
                    handle.write(content)
                copied.append((relative, descriptions))

            env = os.environ.copy()
            for name in (
                "PACT_BROKER_BASE_URL",
                "PACT_BROKER_USERNAME",
                "PACT_BROKER_PASSWORD",
                "PACT_BROKER_TOKEN",
                "PACT_BROKER_PUBLISH_VERIFICATION_RESULTS",
                "PACT_PROJECT_PACT_HELPER",
                "PACT_DESCRIPTION",
                "PACT_PROVIDER_STATE",
            ):
                env.pop(name, None)
            version_proc = run_subprocess(
                ["pact-provider-verifier", "version"],
                cwd=run_root,
                timeout=timeout_seconds,
                env=env,
            )
            if version_proc.returncode != 0:
                raise RuntimeError("version command failed")
            version = next(
                (
                    token.lstrip("v")
                    for token in version_proc.stdout.split()
                    if token.lstrip("v")[0:1].isdigit()
                ),
                None,
            )
            if not version:
                raise RuntimeError("version output unavailable")
        except subprocess.TimeoutExpired:
            return error_result(
                self.name,
                "pact-provider-verifier",
                "contract: verifier timed out",
                duration_ms=elapsed_ms(start),
                terminal_reason="timeout",
                metadata={
                    "timeout_seconds": timeout_seconds,
                    "execution": build_execution_metadata(
                        "executed",
                        requested=required_perms,
                        granted=permissions,
                        producer="pact-provider-verifier",
                    ),
                },
            )
        except (ContainmentError, OSError, RuntimeError) as exc:
            return error_result(
                self.name,
                "pact-provider-verifier",
                sanitize_value(f"contract: setup failed: {exc}").value,
                duration_ms=elapsed_ms(start),
            )

        reports: list[Path] = []
        report_hashes: dict[str, str] = {}
        grouped: dict[tuple[str, int], dict[str, object]] = {}
        example_total = 0
        try:
            from .ship.cleaner import register_owned_artifact

            for index, (relative, descriptions) in enumerate(copied):
                report_rel = run_rel / f"pact-report-{index:03d}.json"
                report = physical.open_contained(report_rel, purpose="write")
                argv = [
                    "pact-provider-verifier",
                    relative.as_posix(),
                    "--provider-base-url",
                    provider_url,
                    "--format",
                    "json",
                    "--log-dir",
                    str(run_root),
                ]
                with report.open("xb") as output:
                    proc = subprocess.run(
                        argv,
                        cwd=run_root,
                        timeout=timeout_seconds,
                        env=env,
                        stdout=output,
                        stderr=subprocess.PIPE,
                        check=False,
                    )
                report = physical.open_contained(report_rel, purpose="read")
                expected = report.lstat()
                if not stat.S_ISREG(expected.st_mode):
                    raise ValueError("verifier report is not an ordinary file")
                with report.open("rb") as handle:
                    opened = os.fstat(handle.fileno())
                    if (opened.st_dev, opened.st_ino) != (
                        expected.st_dev,
                        expected.st_ino,
                    ):
                        raise ValueError("verifier report identity changed")
                    report_bytes = handle.read()
                report_sha256 = hashlib.sha256(report_bytes).hexdigest()
                entry = register_owned_artifact(
                    root, report, "pact-provider-verifier", permissions=permissions
                )
                if (entry["sha256"], entry["device"], entry["inode"]) != (
                    report_sha256,
                    opened.st_dev,
                    opened.st_ino,
                ):
                    raise ValueError("verifier report changed during registration")
                reports.append(report)
                report_hashes[str(report)] = report_sha256

                payload = json.loads(report_bytes)
                examples = payload["examples"]
                summary = payload["summary"]
                if not isinstance(examples, list) or not isinstance(summary, dict):
                    raise TypeError("invalid verifier report shape")
                counts = {
                    name: summary[name]
                    for name in (
                        "example_count",
                        "failure_count",
                        "pending_count",
                        "errors_outside_of_examples_count",
                    )
                }
                if any(
                    type(value) is not int or value < 0 for value in counts.values()
                ):
                    raise ValueError("invalid verifier summary counts")
                failed_examples = 0
                pending_examples = 0
                for example in examples:
                    if not isinstance(example, dict):
                        raise TypeError("invalid verifier example")
                    pact_url = example["pact_url"]
                    interaction_index = example["interaction_index"]
                    description = example["description"]
                    full_description = example["full_description"]
                    status = example["status"]
                    mismatches = example["mismatches"]
                    if (
                        not isinstance(pact_url, str)
                        or Path(pact_url).as_posix() != relative.as_posix()
                        or type(interaction_index) is not int
                        or not 0 <= interaction_index < len(descriptions)
                        or not isinstance(description, str)
                        or not isinstance(full_description, str)
                        or status not in {"passed", "failed", "pending"}
                        or not isinstance(mismatches, list)
                    ):
                        raise ValueError("invalid verifier example fields")
                    failed_examples += int(status == "failed")
                    pending_examples += int(status == "pending")
                    key = (relative.as_posix(), interaction_index)
                    interaction = grouped.setdefault(
                        key,
                        {
                            "name": descriptions[interaction_index],
                            "status": "passed",
                            "mismatches": [],
                        },
                    )
                    if status == "failed":
                        interaction["status"] = "failed"
                    elif status == "pending" and interaction["status"] == "passed":
                        interaction["status"] = "pending"
                    interaction["mismatches"].extend(mismatches)
                if (
                    counts["example_count"] != len(examples)
                    or counts["failure_count"] != failed_examples
                    or counts["pending_count"] != pending_examples
                ):
                    raise ValueError("verifier summary does not match examples")
                if counts["errors_outside_of_examples_count"] > 0:
                    raise RuntimeError("verifier reported errors outside examples")
                if proc.returncode not in (0, 1) or (
                    proc.returncode == 1 and failed_examples == 0
                ):
                    raise RuntimeError(
                        f"verifier process failed with exit {proc.returncode}"
                    )
                example_total += len(examples)
            if grouped and len(grouped) != sum(len(names) for _, names in copied):
                raise ValueError("verifier omitted input interactions")
        except subprocess.TimeoutExpired:
            return error_result(
                self.name,
                "pact-provider-verifier",
                "contract: verifier timed out",
                duration_ms=elapsed_ms(start),
                terminal_reason="timeout",
                metadata={
                    "timeout_seconds": timeout_seconds,
                    "execution": build_execution_metadata(
                        "executed",
                        requested=required_perms,
                        granted=permissions,
                        producer="pact-provider-verifier",
                        producer_version=version,
                    ),
                },
            )
        except (
            ContainmentError,
            OSError,
            json.JSONDecodeError,
            KeyError,
            TypeError,
            ValueError,
            RuntimeError,
        ) as exc:
            result = error_result(
                self.name,
                "pact-provider-verifier",
                sanitize_value(f"contract: verifier failed: {exc}").value,
                duration_ms=elapsed_ms(start),
            )
            if reports:
                result["artifacts"] = sanitize_value(
                    [str(item) for item in reports]
                ).value
            return result

        interactions = [grouped[key] for key in sorted(grouped)]
        passed = sum(item["status"] == "passed" for item in interactions)
        failed = sum(item["status"] == "failed" for item in interactions)
        pending = sum(item["status"] == "pending" for item in interactions)
        metrics = {
            "total_interactions": len(interactions),
            "passed_interactions": passed,
            "failed_interactions": failed,
            "pending_interactions": pending,
            "examples": example_total,
        }
        metadata = sanitize_value(
            {
                "evidence_source": "executed-workload",
                "report_sha256": report_hashes,
                "raw_artifact_sha256": report_hashes,
                "timeout_seconds": timeout_seconds,
                "incomplete": pending > 0,
                "execution": build_execution_metadata(
                    "executed",
                    requested=required_perms,
                    granted=permissions,
                    producer="pact-provider-verifier",
                    producer_version=version,
                    extra={"provider_url": provider_url},
                ),
            }
        ).value
        if not interactions:
            metadata["incomplete"] = True
            return skipped_result(
                self.name,
                "pact-provider-verifier",
                "contract: incomplete workload; no interactions",
                duration_ms=elapsed_ms(start),
                metadata=metadata,
            )
        status = "fail" if failed else "warn" if pending else "ok"
        return ToolResult(
            tool=self.name,
            engine="pact-provider-verifier",
            engine_version=version,
            status=status,
            duration_ms=elapsed_ms(start),
            summary=(
                f"contract: {passed} passed, {failed} failed, {pending} pending interaction(s)"
            ),
            findings=[],
            raw=sanitize_value({"interactions": interactions}).value,
            metrics=metrics,
            artifacts=sanitize_value([str(item) for item in reports]).value,
            metadata=metadata,
        )
