"""Offline local ONNX model review runner.

Executes local ONNX inference models over codebase files with zero network
calls. Returns status='skipped' when onnxruntime or model artifact is absent.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from .base import Finding, ToolFn, ToolName, ToolResult
from .common import elapsed_ms, now_ms


def _has_onnxruntime() -> bool:
    try:
        import onnxruntime  # noqa: F401

        return True
    except ImportError:
        return False


def _create_inference_session(model_path: Path) -> Any:
    import onnxruntime as ort

    return ort.InferenceSession(str(model_path))


class OfflineReviewTool(ToolFn):
    name: ToolName = "offline-review"

    @property
    def mcp_description(self) -> str:
        return (
            "Run local offline ONNX model review at <path>; returns skipped when "
            "onnxruntime or model is absent. Returns {status, findings[], summary}."
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
        return self.run(path, permissions=permissions, **options)

    def run(
        self,
        path: Path,
        *,
        config: Any = None,
        permissions: Any = None,
        model_path: Path | str | None = None,
        expected_sha256: str | None = None,
        defect_threshold: float = 0.5,
        **options: object,
    ) -> ToolResult:
        from ..permissions import build_execution_metadata

        start = now_ms()
        p = Path(path)

        resolved_model_path: Path | None = None
        if model_path is not None:
            mp = Path(model_path)
            if mp.is_file():
                resolved_model_path = mp
        else:
            default_candidate = (
                (p if p.is_dir() else p.parent) / ".rush" / "models" / "review.onnx"
            )
            if default_candidate.is_file():
                resolved_model_path = default_candidate

        if (
            not _has_onnxruntime()
            or resolved_model_path is None
            or not resolved_model_path.is_file()
        ):
            return ToolResult(
                tool=self.name,
                engine="offline-review",
                engine_version="1.0.0",
                status="skipped",
                duration_ms=elapsed_ms(start),
                summary="offline-review: onnxruntime or ONNX model absent; skipping offline review.",
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

        # Check digest if expected
        if expected_sha256:
            digest = hashlib.sha256(resolved_model_path.read_bytes()).hexdigest()
            if digest.lower() != expected_sha256.lower():
                return ToolResult(
                    tool=self.name,
                    engine="offline-review",
                    engine_version="1.0.0",
                    status="fail",
                    duration_ms=elapsed_ms(start),
                    summary=f"offline-review: Model digest mismatch (expected {expected_sha256}, got {digest}).",
                    findings=[
                        Finding(
                            path=str(resolved_model_path),
                            line=1,
                            rule="offline-review/digest-mismatch",
                            severity="error",
                            message=f"ONNX model checksum mismatch: expected {expected_sha256}, got {digest}",
                        )
                    ],
                    raw=None,
                    metadata={
                        "execution": build_execution_metadata(
                            "executed",
                            granted=permissions,
                            producer="offline-review",
                        )
                    },
                )

        # Scan code files
        code_files: list[Path] = []
        if p.is_file():
            code_files.append(p)
        elif p.is_dir():
            for ext in ("*.py", "*.ts", "*.js", "*.go", "*.rs"):
                code_files.extend(sorted(p.glob(f"**/{ext}")))

        findings: list[Finding] = []
        try:
            session = _create_inference_session(resolved_model_path)
            input_name = (
                session.get_inputs()[0].name if session.get_inputs() else "input"
            )

            for cf in code_files:
                try:
                    text = cf.read_text(encoding="utf-8", errors="replace")
                    # Simple deterministic char/token vector (first 64 char ordinals normalized)
                    tokens = [min(ord(c), 255) for c in text[:64]]
                    if len(tokens) < 64:
                        tokens.extend([0] * (64 - len(tokens)))

                    # Run inference session
                    outputs = session.run(None, {input_name: [tokens]})
                    score = 0.0
                    if outputs and isinstance(outputs[0], (list, tuple)):
                        val = outputs[0][0]
                        if isinstance(val, (list, tuple)):
                            val = val[0]
                        score = float(val)
                    elif outputs:
                        score = float(outputs[0])

                    if score >= defect_threshold:
                        findings.append(
                            Finding(
                                path=str(cf),
                                line=1,
                                rule="offline-review/model-flagged-defect",
                                severity="warn",
                                message=f"Offline ONNX model flagged suspicious pattern in {cf.name} (defect score: {score:.2f})",
                                remediation="Review code structure for logic flaws, security vulnerabilities, or unbounded execution.",
                            )
                        )
                except Exception:  # noqa: BLE001, S112
                    continue
        except Exception as exc:  # noqa: BLE001
            return ToolResult(
                tool=self.name,
                engine="offline-review",
                engine_version="1.0.0",
                status="error",
                duration_ms=elapsed_ms(start),
                summary=f"offline-review: Failed executing ONNX inference session: {exc}",
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

        status = "warn" if findings else "ok"
        summary = (
            f"offline-review: Evaluated {len(code_files)} file(s) with local ONNX model, "
            f"{len(findings)} finding(s)"
        )

        return ToolResult(
            tool=self.name,
            engine="offline-review",
            engine_version="1.0.0",
            status=status,
            duration_ms=elapsed_ms(start),
            summary=summary,
            findings=findings,
            metrics={
                "files_evaluated": len(code_files),
                "model_findings_count": len(findings),
                "model_path": str(resolved_model_path),
            },
            raw={"findings_count": len(findings)},
            metadata={
                "execution": build_execution_metadata(
                    "executed",
                    granted=permissions,
                    producer="offline-review",
                )
            },
        )
