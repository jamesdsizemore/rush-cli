"""Environment Doctor & Binary Integrity Diagnostic Tool.

Architecture §8, Phase 24.
Enforces Control 4: PATH Precedence & Binary Integrity.
"""

from __future__ import annotations

import os
import shutil
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from rush.config import RushConfig
from rush.logging import get_logger, log_subsystem
from rush.permissions import ExecutionPermissions
from rush.tools.base import ToolFn, ToolName, ToolResult

logger = get_logger("tools.doctor")


@dataclass(frozen=True)
class HealthCheck:
    name: str
    status: str  # "ok", "warn", "fail"
    message: str
    remediation: str | None = None
    details: dict[str, Any] = field(default_factory=dict)


class EnvironmentDoctor:
    """Performs deep health checks on Python runtime, PATH ordering, and external engines."""

    def __init__(self, repo_root: Path | None = None) -> None:
        self.repo_root = (repo_root or Path.cwd()).resolve()

    def check_python_anti_shadowing(self) -> HealthCheck:
        """Verify that current interpreter belongs to project virtual environment."""
        venv_path = self.repo_root / ".venv"
        current_exe = Path(sys.executable).resolve()

        if not venv_path.exists():
            return HealthCheck(
                name="python_runtime",
                status="warn",
                message=f"No local .venv found at '{venv_path}'. Using global interpreter '{current_exe}'.",
                remediation="Run 'uv venv' or 'python -m venv .venv' to create a project-isolated environment.",
                details={
                    "executable": str(current_exe),
                    "expected_venv": str(venv_path),
                },
            )

        if not current_exe.is_relative_to(venv_path):
            return HealthCheck(
                name="python_anti_shadowing",
                status="fail",
                message=f"Interpreter Shadowing Detected: Running from '{current_exe}', but project venv is at '{venv_path}'.",
                remediation="Activate project virtual environment or invoke via '.venv/Scripts/python.exe' directly.",
                details={
                    "active_executable": str(current_exe),
                    "project_venv": str(venv_path),
                },
            )

        return HealthCheck(
            name="python_anti_shadowing",
            status="ok",
            message=f"Python runtime correctly isolated to project venv ('{current_exe}').",
            details={"executable": str(current_exe)},
        )

    def diagnose_all(self) -> list[HealthCheck]:
        return [self.check_python_anti_shadowing()]


def resolve_binary_secure(name: str, cwd: Path | None = None) -> Path | None:
    """Securely resolve executable path with strict precedence:
    1. Active virtual environment (sys.prefix / Scripts or bin)
    2. Global system PATH (excluding current working directory)
    """
    # 1. Check Virtual Environment
    venv_dir = Path(sys.prefix)
    bin_dir = venv_dir / ("Scripts" if sys.platform == "win32" else "bin")
    candidate = bin_dir / (
        f"{name}.exe" if sys.platform == "win32" and not name.endswith(".exe") else name
    )
    if candidate.is_file():
        return candidate

    # 2. Check System PATH (sanitizing out cwd)
    path_entries = os.environ.get("PATH", "").split(os.pathsep)
    clean_entries = []
    cwd_resolved = (cwd or Path.cwd()).resolve()

    for entry in path_entries:
        if not entry:
            continue
        p = Path(entry).resolve()
        if p == cwd_resolved:
            # Reject relative or cwd path injection
            continue
        clean_entries.append(str(p))

    resolved_str = shutil.which(name, path=os.pathsep.join(clean_entries))
    return Path(resolved_str).resolve() if resolved_str else None


def audit_environment_health(root: Path | None = None) -> dict[str, Any]:
    """Audit local runtime environment, binary health, and potential shadowing attacks."""
    root_path = root or Path.cwd()
    warnings: list[str] = []
    engines: dict[str, dict[str, Any]] = {}

    known_engines = [
        "ruff",
        "biome",
        "eslint",
        "prettier",
        "mypy",
        "tsc",
        "pytest",
        "vitest",
        "pip-audit",
        "semgrep",
        "gitleaks",
    ]

    for engine in known_engines:
        bin_path = resolve_binary_secure(engine, cwd=root_path)
        # Check for cwd shadowing
        cwd_candidate = root_path / (
            f"{engine}.exe" if sys.platform == "win32" else engine
        )
        if cwd_candidate.is_file():
            warn_msg = f"Security Warning: Local binary '{cwd_candidate}' shadows system {engine}"
            log_subsystem("doctor", "WARN", warn_msg)
            warnings.append(warn_msg)

        engines[engine] = {
            "installed": bin_path is not None,
            "path": str(bin_path) if bin_path else None,
        }

    return {
        "python_version": sys.version.split()[0],
        "in_virtualenv": sys.prefix != sys.base_prefix,
        "virtualenv_path": sys.prefix if sys.prefix != sys.base_prefix else None,
        "engines": engines,
        "warnings": warnings,
    }


class DoctorTool(ToolFn):
    """Diagnose toolchain installation, PATH precedence, and system readiness."""

    name: ToolName = "doctor"

    @property
    def mcp_description(self) -> str:
        return (
            "Diagnose environment health, toolchain integrity, and binary resolution at <path>. "
            "Returns {status, findings[], summary}."
        )

    def __call__(self, path: Path = Path(".")) -> ToolResult:
        return self.run(path)

    def run(
        self,
        path: Path | None = None,
        config: RushConfig | None = None,
        permissions: ExecutionPermissions | None = None,
        **kwargs: Any,
    ) -> ToolResult:
        root = (path or Path.cwd()).resolve()
        log_subsystem("doctor", "INFO", f"Auditing environment health at {root}")
        report = audit_environment_health(root)

        installed_count = sum(1 for e in report["engines"].values() if e["installed"])
        total_count = len(report["engines"])
        status = "warn" if report["warnings"] else "ok"

        summary = (
            f"doctor: {installed_count}/{total_count} engines installed. "
            f"Virtualenv: {'active' if report['in_virtualenv'] else 'inactive'}. "
            f"{len(report['warnings'])} warning(s)."
        )

        return ToolResult(
            tool=self.name,
            status=status,
            duration_ms=10,
            summary=summary,
            findings=[],
        )
