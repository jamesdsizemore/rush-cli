"""Offline local LLM review runner (PR50.11 / I24).

Discovers external local LLM engines (ollama, llama-cli) on PATH for air-gapped
code review with zero network egress. Returns status='skipped' when no local runner is found.
"""

from __future__ import annotations

import json
import re
import shutil
from pathlib import Path
from typing import Any

from .base import Finding, ToolFn, ToolName, ToolResult
from .common import elapsed_ms, now_ms, run_subprocess


def _is_ollama_ready() -> bool:
    """Checks if local Ollama daemon is actively listening on localhost:11434."""
    import socket

    try:
        with socket.create_connection(("127.0.0.1", 11434), timeout=0.2):
            return True
    except OSError:
        return False


def discover_local_runner(
    custom_path: str | Path | None = None,
    check_active: bool = True,
) -> dict[str, Any] | None:
    """Discovers external local LLM execution engine on PATH or custom path.

    Returns a dict with 'type' and 'path', or None if no runner is discovered.
    """
    if custom_path:
        cp = Path(custom_path)
        if cp.is_file():
            binary_name = cp.name.lower()
            runner_type = "llama-cli" if "llama" in binary_name else "ollama"
            return {"type": runner_type, "path": str(cp.resolve())}
        return {
            "type": "ollama" if "ollama" in str(custom_path).lower() else "llama-cli",
            "path": str(custom_path),
        }

    ollama_path = shutil.which("ollama")
    if ollama_path and (not check_active or _is_ollama_ready()):
        return {"type": "ollama", "path": ollama_path}

    llama_path = shutil.which("llama-cli") or shutil.which("llama")
    if llama_path:
        return {"type": "llama-cli", "path": llama_path}

    return None


def parse_review_findings(raw_output: str, base_dir: Path) -> list[Finding]:
    """Parses text or JSON output from a local LLM runner into canonical Findings."""
    findings: list[Finding] = []
    if not raw_output or not raw_output.strip():
        return findings

    # Attempt JSON parse first if model emitted JSON
    trimmed = raw_output.strip()
    if trimmed.startswith("[") and trimmed.endswith("]"):
        try:
            parsed = json.loads(trimmed)
            if isinstance(parsed, list):
                for item in parsed:
                    if isinstance(item, dict) and "message" in item:
                        findings.append(
                            Finding(
                                path=item.get("path", "source"),
                                line=int(item.get("line", 1)),
                                column=int(item.get("column", 1)),
                                rule=item.get("rule", "offline-review/detected-issue"),
                                severity=item.get("severity", "warn"),
                                message=str(item.get("message")),
                                remediation=item.get("remediation"),
                            )
                        )
                if findings:
                    return findings
        except json.JSONDecodeError:
            pass

    # Regex parse for line-oriented findings like:
    # path/to/file.py:12: [WARN] Description of flaw
    pattern = re.compile(
        r"^(?P<path>[^:\n]+):(?P<line>\d+)(?::(?P<col>\d+))?:\s*(?:\[(?P<sev>ERROR|WARN|INFO)\])?\s*(?P<msg>.+)$",
        re.MULTILINE,
    )
    for match in pattern.finditer(raw_output):
        f_path = match.group("path").strip()
        line_num = int(match.group("line"))
        col_num = int(match.group("col") or 1)
        sev_raw = (match.group("sev") or "WARN").lower()
        severity = "error" if sev_raw == "error" else "warn"
        message = match.group("msg").strip()

        findings.append(
            Finding(
                path=f_path,
                line=line_num,
                column=col_num,
                rule="offline-review/detected-issue",
                severity=severity,
                message=message,
            )
        )

    return findings


class OfflineReviewTool(ToolFn):
    """Air-gapped code review using local LLM engines discovered from PATH."""

    name: ToolName = "offline-review"

    @property
    def mcp_description(self) -> str:
        return (
            "Run air-gapped code review using external local LLM (ollama/llama-cli) on PATH; "
            "returns skipped if no local runner is found. Returns {status, findings[], summary}."
        )

    def __call__(
        self,
        path: Path,
        *,
        runner_path: str | Path | None = None,
        model: str = "codellama",
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
            runner_path=runner_path,
            model=model,
            permissions=permissions,
            **options,
        )

    def run(
        self,
        path: Path,
        *,
        config: Any = None,
        permissions: Any = None,
        runner_path: str | Path | None = None,
        model: str = "codellama",
        **options: object,
    ) -> ToolResult:
        from ..permissions import build_execution_metadata

        start = now_ms()
        p = Path(path).resolve()
        target_dir = p if p.is_dir() else p.parent

        runner = discover_local_runner(runner_path)
        if runner is None:
            return ToolResult(
                tool=self.name,
                engine="offline-runner",
                engine_version="1.0.0",
                status="skipped",
                duration_ms=elapsed_ms(start),
                summary=(
                    "offline-review: No external local LLM runner (ollama or llama-cli) found on PATH. "
                    "Install ollama (https://ollama.com) or llama.cpp for local air-gapped review."
                ),
                findings=[],
                raw=None,
                metadata={
                    "execution": build_execution_metadata(
                        "executed",
                        granted=permissions,
                        producer="offline-review",
                    )
                },
            )

        # Collect code files for review
        code_files: list[Path] = []
        if p.is_file():
            code_files.append(p)
        elif p.is_dir():
            for ext in ("*.py", "*.ts", "*.js", "*.go", "*.rs"):
                for cf in sorted(p.rglob(ext)):
                    # Avoid hidden and vendor dirs
                    if not any(part.startswith(".") for part in cf.parts):
                        code_files.append(cf)
                        if len(code_files) >= 20:
                            break
                if len(code_files) >= 20:
                    break

        if not code_files:
            return ToolResult(
                tool=self.name,
                engine="offline-runner",
                engine_version="1.0.0",
                status="skipped",
                duration_ms=elapsed_ms(start),
                summary=f"offline-review: No code files found at '{path}'.",
                findings=[],
                raw=None,
                metadata={
                    "runner": runner,
                    "execution": build_execution_metadata(
                        "executed",
                        granted=permissions,
                        producer="offline-review",
                    ),
                },
            )

        # Build prompt for local model
        code_snippets: list[str] = []
        for cf in code_files:
            rel = str(cf.relative_to(target_dir)).replace("\\", "/")
            try:
                snippet = cf.read_text(encoding="utf-8", errors="replace")[:1000]
                code_snippets.append(f"--- File: {rel} ---\n{snippet}")
            except Exception:  # noqa: BLE001, S112
                continue

        prompt = (
            "Review the following code for potential security bugs or syntax errors. "
            "Output findings in the format: file:line: [WARN] message\n\n"
            + "\n".join(code_snippets)
        )

        findings: list[Finding] = []
        runner_bin = runner["path"]
        runner_type = runner["type"]

        if runner_type == "ollama":
            cmd = [runner_bin, "run", model, prompt]
        else:
            model_file = options.get("model_path")
            if not model_file:
                candidates = (
                    list((target_dir / ".rush" / "models").glob("*.gguf"))
                    if (target_dir / ".rush" / "models").is_dir()
                    else []
                )
                if candidates:
                    model_file = str(candidates[0])
            if (
                not model_file
                and not options.get("mock")
                and "mock" not in str(runner_bin).lower()
            ):
                return ToolResult(
                    tool=self.name,
                    engine="offline-runner",
                    engine_version="1.0.0",
                    status="skipped",
                    duration_ms=elapsed_ms(start),
                    summary="offline-review: llama-cli discovered, but no local GGUF model file provided via --model-path or in .rush/models/.",
                    findings=[],
                    raw=None,
                    metadata={
                        "runner": runner,
                        "execution": build_execution_metadata(
                            "executed",
                            granted=permissions,
                            producer="offline-review",
                        ),
                    },
                )
            cmd = (
                [runner_bin, "-m", str(model_file), "-p", prompt]
                if model_file
                else [runner_bin, "-p", prompt]
            )

        try:
            res = run_subprocess(cmd, cwd=target_dir)
            if res.returncode != 0:
                return ToolResult(
                    tool=self.name,
                    engine="offline-runner",
                    engine_version="1.0.0",
                    status="error",
                    duration_ms=elapsed_ms(start),
                    summary=f"offline-review: Runner execution failed with exit code {res.returncode}: {res.stderr[:200]}",
                    findings=[],
                    raw={"stderr": res.stderr},
                    metadata={
                        "runner": runner,
                        "execution": build_execution_metadata(
                            "executed",
                            granted=permissions,
                            producer="offline-review",
                        ),
                    },
                )
            findings = parse_review_findings(res.stdout, target_dir)
        except Exception as exc:  # noqa: BLE001
            return ToolResult(
                tool=self.name,
                engine="offline-runner",
                engine_version="1.0.0",
                status="error",
                duration_ms=elapsed_ms(start),
                summary=f"offline-review: Error invoking runner: {exc}",
                findings=[],
                raw=None,
                metadata={
                    "runner": runner,
                    "execution": build_execution_metadata(
                        "executed",
                        granted=permissions,
                        producer="offline-review",
                    ),
                },
            )

        has_errors = any(f.get("severity") == "error" for f in findings)
        status = "fail" if has_errors else ("warn" if findings else "ok")
        summary = (
            f"offline-review: Evaluated {len(code_files)} file(s) via {runner['type']} ({model}), "
            f"found {len(findings)} issue(s)."
        )

        return ToolResult(
            tool=self.name,
            engine="offline-runner",
            engine_version="1.0.0",
            status=status,
            duration_ms=elapsed_ms(start),
            summary=summary,
            findings=findings,
            metrics={
                "files_evaluated": len(code_files),
                "issues_found": len(findings),
            },
            raw={"raw_output": res.stdout[:1000] if "res" in locals() else ""},
            metadata={
                "runner": runner,
                "model": model,
                "execution": build_execution_metadata(
                    "executed",
                    granted=permissions,
                    producer="offline-review",
                ),
            },
        )


__all__ = ["OfflineReviewTool", "discover_local_runner", "parse_review_findings"]
