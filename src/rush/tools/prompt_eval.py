"""Prompt evaluation tool for recorded golden task runs.

Evaluates deterministic recorded-run evaluation matrices (sequence match,
patch match, token/cost totals, pass rates, baseline deltas).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .base import Finding, ToolFn, ToolName, ToolResult, ToolStatus
from .common import elapsed_ms, now_ms


class PromptEvalTool(ToolFn):
    name: ToolName = "prompt-eval"

    @property
    def mcp_description(self) -> str:
        return (
            "Evaluate recorded prompt runs against golden task criteria at <path>. "
            "Returns {status, findings[], summary}."
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
        golden_path: Path | str | None = None,
        pass_rate_threshold: float = 1.0,
        max_cost_threshold: float | None = None,
        max_tokens_threshold: int | None = None,
        records: list[dict[str, Any]] | None = None,
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
            permissions=permissions,
            golden_path=golden_path,
            pass_rate_threshold=pass_rate_threshold,
            max_cost_threshold=max_cost_threshold,
            max_tokens_threshold=max_tokens_threshold,
            records=records,
            **options,
        )

    def _load_records(
        self, path: Path, records_arg: list[dict[str, Any]] | None
    ) -> list[dict[str, Any]]:
        if records_arg is not None:
            return records_arg

        p = Path(path)
        if not p.exists():
            return []

        loaded: list[dict[str, Any]] = []
        if p.is_file():
            if p.suffix in (".json", ".jsonl"):
                try:
                    text = p.read_text(encoding="utf-8").strip()
                    if p.suffix == ".jsonl" or (text.startswith("{") and "\n{" in text):
                        for line in text.splitlines():
                            line = line.strip()
                            if line:
                                loaded.append(json.loads(line))
                    else:
                        data = json.loads(text)
                        if isinstance(data, list):
                            loaded.extend(data)
                        elif isinstance(data, dict):
                            if "runs" in data and isinstance(data["runs"], list):
                                loaded.extend(data["runs"])
                            elif "records" in data and isinstance(
                                data["records"], list
                            ):
                                loaded.extend(data["records"])
                            else:
                                loaded.append(data)
                except Exception:  # noqa: BLE001, S110
                    pass
        elif p.is_dir():
            for child in sorted(p.glob("**/*.json")):
                try:
                    data = json.loads(child.read_text(encoding="utf-8"))
                    if isinstance(data, list):
                        loaded.extend(data)
                    elif isinstance(data, dict):
                        loaded.append(data)
                except Exception:  # noqa: BLE001, S112
                    continue

        return loaded

    def run(
        self,
        path: Path,
        *,
        config: Any = None,
        permissions: Any = None,
        golden_path: Path | str | None = None,
        pass_rate_threshold: float = 1.0,
        max_cost_threshold: float | None = None,
        max_tokens_threshold: int | None = None,
        records: list[dict[str, Any]] | None = None,
        **options: object,
    ) -> ToolResult:
        from ..permissions import build_execution_metadata

        start = now_ms()
        raw_records = self._load_records(Path(path), records)

        if not raw_records:
            return ToolResult(
                tool=self.name,
                engine="prompt-eval",
                engine_version="1.0.0",
                status="skipped",
                duration_ms=elapsed_ms(start),
                summary=f"prompt-eval: No recorded golden runs found at {path}.",
                findings=[],
                raw=None,
                metadata={
                    "execution": build_execution_metadata(
                        "executed",
                        granted=permissions,
                        producer="prompt-eval",
                    )
                },
            )

        findings: list[Finding] = []
        total_runs = len(raw_records)
        passed_runs = 0
        total_tokens = 0
        total_cost = 0.0

        for idx, rec in enumerate(raw_records, 1):
            task_id = str(rec.get("task_id") or rec.get("id") or f"task-{idx}")
            run_failed = False

            # Sequence match
            actual_seq = rec.get("sequence") or []
            expected_seq = rec.get("expected_sequence")
            if expected_seq is not None and actual_seq != expected_seq:
                findings.append(
                    Finding(
                        path=str(path),
                        line=idx,
                        rule="prompt-eval/sequence-mismatch",
                        severity="error",
                        message=f"Task '{task_id}' sequence mismatch: expected {expected_seq}, got {actual_seq}",
                        remediation="Align prompt or tool execution trajectory with golden sequence.",
                    )
                )
                run_failed = True

            # Patch match
            actual_patch = rec.get("patch") or rec.get("diff")
            expected_patch = rec.get("expected_patch") or rec.get("golden_patch")
            if expected_patch is not None and (
                actual_patch is None or actual_patch.strip() != expected_patch.strip()
            ):
                findings.append(
                    Finding(
                        path=str(path),
                        line=idx,
                        rule="prompt-eval/patch-mismatch",
                        severity="error",
                        message=f"Task '{task_id}' patch mismatch against expected golden patch.",
                        remediation="Verify code generation and diff output matches golden task assertion.",
                    )
                )
                run_failed = True

            # Assertions / explicit outcome
            passed_field = rec.get("passed")
            if passed_field is False:
                run_failed = True
                findings.append(
                    Finding(
                        path=str(path),
                        line=idx,
                        rule="prompt-eval/task-failed",
                        severity="error",
                        message=f"Task '{task_id}' marked as failed in evaluation record.",
                    )
                )
            elif rec.get("outcome") in ("fail", "error"):
                run_failed = True
                findings.append(
                    Finding(
                        path=str(path),
                        line=idx,
                        rule="prompt-eval/task-failed",
                        severity="error",
                        message=f"Task '{task_id}' outcome was {rec.get('outcome')}.",
                    )
                )

            # Tokens & Cost aggregation
            tokens_data = rec.get("tokens") or rec.get("token_usage")
            if isinstance(tokens_data, dict):
                total_tokens += int(tokens_data.get("total_tokens") or 0)
            elif isinstance(tokens_data, int):
                total_tokens += tokens_data

            cost_data = rec.get("cost")
            if isinstance(cost_data, (int, float)):
                total_cost += float(cost_data)

            if not run_failed:
                passed_runs += 1

        pass_rate = (passed_runs / total_runs) if total_runs > 0 else 0.0

        if max_tokens_threshold is not None and total_tokens > max_tokens_threshold:
            findings.append(
                Finding(
                    path=str(path),
                    line=1,
                    rule="prompt-eval/token-budget-exceeded",
                    severity="warn",
                    message=f"Total tokens ({total_tokens}) exceeded budget ({max_tokens_threshold}).",
                )
            )

        if max_cost_threshold is not None and total_cost > max_cost_threshold:
            findings.append(
                Finding(
                    path=str(path),
                    line=1,
                    rule="prompt-eval/cost-budget-exceeded",
                    severity="warn",
                    message=f"Total cost (${total_cost:.4f}) exceeded budget (${max_cost_threshold:.4f}).",
                )
            )

        has_errors = any(f.get("severity") in ("error", "fail") for f in findings)
        if has_errors or pass_rate < pass_rate_threshold:
            status: ToolStatus = "fail"
        elif findings:
            status = "warn"
        else:
            status = "ok"

        summary = (
            f"prompt-eval: {passed_runs}/{total_runs} golden task(s) passed "
            f"({pass_rate * 100:.1f}%), {total_tokens} tokens, ${total_cost:.4f}"
        )

        return ToolResult(
            tool=self.name,
            engine="prompt-eval",
            engine_version="1.0.0",
            status=status,
            duration_ms=elapsed_ms(start),
            summary=summary,
            findings=findings,
            metrics={
                "total_runs": total_runs,
                "passed_runs": passed_runs,
                "failed_runs": total_runs - passed_runs,
                "pass_rate": pass_rate,
                "total_tokens": total_tokens,
                "total_cost": round(total_cost, 6),
            },
            raw={
                "total_runs": total_runs,
                "passed_runs": passed_runs,
                "pass_rate": pass_rate,
            },
            metadata={
                "execution": build_execution_metadata(
                    "executed",
                    granted=permissions,
                    producer="prompt-eval",
                )
            },
        )
