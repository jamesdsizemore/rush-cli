"""Environment Doctor & Binary Integrity Diagnostic Tool.

Architecture §8, Phase 24.
Enforces Control 4: PATH Precedence & Binary Integrity.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from rush.config import RushConfig
from rush.discovery.stack import DetectedStack, detect_project_stacks
from rush.logging import get_logger, log_subsystem
from rush.permissions import ExecutionPermissions
from rush.runtime import binaries as binaries_mod
from rush.runtime.binaries import (
    ManifestVerificationError,
    read_manifest,
    resolve_binary,
    resolve_project_binary,
    verify_manifest,
)
from rush.setup.engine_packages import UnknownEngineError, resolve_engine_package
from rush.setup.provision import setup_action_command
from rush.tools.base import Finding, ToolFn, ToolName, ToolResult, ToolStatus

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


# --- T15: actionable engine readiness inventory ------------------------------
#
# Design: .scratch/phase-70-design-gate/W2-T9-T17.md, "## T15". Cross detected
# stacks (rush.discovery.stack) with the engine package registry
# (rush.setup.engine_packages) into one per-engine readiness entry, resolved
# through the same T11 resolver dispatch uses (`resolve_binary` with
# `engine_id=`/`project_root=`), never `resolve_binary_secure` above.


@dataclass(frozen=True)
class _EngineResolution:
    """Result of resolving one engine's binary for the T15 inventory."""

    executable: str | None
    source: str | None  # "manifest" | "rush_runtime" | "path" | None
    shadowed: bool


def _resolve_engine(engine_id: str, binary: str, root: Path) -> _EngineResolution:
    """Resolve `engine_id` the same way dispatch does, flagging cwd shadowing.

    `root` must already be resolved. A binary that resolves to a file living
    directly in `root` is never trusted as installed -- S15.3/§3 -- it is
    surfaced as a `binary-shadowing` finding instead, and it is never probed.
    """
    manifest_path = resolve_project_binary(engine_id, root)
    if manifest_path is not None:
        return _EngineResolution(manifest_path, "manifest", False)

    resolved = resolve_binary(binary, engine_id=engine_id, project_root=root)
    if resolved is None:
        return _EngineResolution(None, None, False)

    resolved_path = Path(resolved).resolve()
    if resolved_path.parent == root:
        return _EngineResolution(None, None, True)

    scripts = binaries_mod._venv_scripts_dir()
    source = (
        "rush_runtime"
        if scripts is not None and resolved_path.parent == scripts.resolve()
        else "path"
    )
    return _EngineResolution(resolved, source, False)


def _probe_version(executable: str) -> tuple[str | None, str]:
    """Run `executable --version`, timeout 10s. Never raises to the caller."""
    try:
        proc = subprocess.run(
            [executable, "--version"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None, "probe_failed"
    output = (proc.stdout or proc.stderr or "").strip()
    return (output or None), "probed"


def _build_engine_entry(
    engine_id: str, stack_language: str, root: Path, *, probe: bool
) -> tuple[dict[str, Any], bool]:
    """Return (entry, shadowed). `shadowed` is never a public entry key --
    S15.2 pins the entry's exact key set -- callers that need it (DoctorTool)
    carry it alongside the entry instead."""
    try:
        package = resolve_engine_package(engine_id)
    except UnknownEngineError:
        # R15.1: a recommended engine without ENGINE_PACKAGES metadata (e.g.
        # bandit, clippy, gofmt) is unsupported/informational, never required.
        return {
            "engine": engine_id,
            "stack": stack_language,
            "required": False,
            "disposition": "unsupported",
            "executable": None,
            "source": None,
            "version": None,
            "probe_state": "not_probed",
            "action": "",
        }, False

    resolution = _resolve_engine(engine_id, package.binary, root)
    if resolution.executable is None:
        disposition = "missing"
        version: str | None = None
        probe_state = "not_probed"
    else:
        disposition = "installed"
        if probe:
            version, probe_state = _probe_version(resolution.executable)
        else:
            version, probe_state = None, "not_probed"

    action = "" if disposition == "installed" else setup_action_command(root, [package])

    entry = {
        "engine": engine_id,
        "stack": stack_language,
        "required": True,
        "disposition": disposition,
        "executable": resolution.executable,
        "source": resolution.source,
        "version": version,
        "probe_state": probe_state,
        "action": action,
    }
    return entry, resolution.shadowed


def _build_inventory_with_shadow_map(
    root: Path, *, probe: bool
) -> tuple[list[dict[str, Any]], dict[str, bool], list[DetectedStack]]:
    """Shared implementation for `build_engine_inventory` and `DoctorTool.run`.

    Returns the public entries, a private engine-id -> shadowed map (never
    exposed on the entry dict), and the detected stacks -- so a single caller
    (DoctorTool.run) never re-detects stacks or re-resolves an engine it
    already resolved here.
    """
    resolved_root = root.resolve()
    stacks = detect_project_stacks(resolved_root)
    entries: list[dict[str, Any]] = []
    shadow_map: dict[str, bool] = {}
    seen: set[str] = set()
    for stack in stacks:
        for engine_id in stack.suggested_engines:
            if engine_id in seen:
                continue
            seen.add(engine_id)
            entry, shadowed = _build_engine_entry(
                engine_id, stack.language, resolved_root, probe=probe
            )
            entries.append(entry)
            shadow_map[engine_id] = shadowed
    return entries, shadow_map, stacks


def build_engine_inventory(root: Path, *, probe: bool) -> list[dict[str, Any]]:
    """Cross detected stacks x ENGINE_PACKAGES into one readiness entry each.

    S15.1-S15.6: one entry per suggested engine of every detected stack, in
    `{engine, stack, required, disposition, executable, source, version,
    probe_state, action}` shape. `probe=False` never executes any binary
    (T23's status contract, R15.2); `probe=True` runs a `--version` probe on
    installed, non-shadowed engines only.
    """
    entries, _shadow_map, _stacks = _build_inventory_with_shadow_map(root, probe=probe)
    return entries


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
        log_subsystem("doctor", "INFO", f"Auditing engine readiness at {root}")

        entries, shadow_map, stacks = _build_inventory_with_shadow_map(root, probe=True)
        findings: list[Finding] = []

        for stack in stacks:
            stack_entries = [e for e in entries if e["stack"] == stack.language]
            if stack_entries and all(
                e["disposition"] == "unsupported" for e in stack_entries
            ):
                findings.append(
                    {
                        "rule": "no_supported_engine_for_stack",
                        "message": (
                            f"No Rush-supported engine for stack '{stack.language}'; "
                            f"suggested engines ({', '.join(stack.suggested_engines)}) "
                            "have no installable package."
                        ),
                    }
                )

        for entry in entries:
            engine_id = entry["engine"]
            if entry["disposition"] == "unsupported":
                findings.append(
                    {
                        "rule": "engine-unsupported",
                        "message": f"{engine_id}: no Rush-managed package; install manually if needed.",
                    }
                )
                continue
            if entry["disposition"] == "missing":
                if shadow_map.get(engine_id):
                    findings.append(
                        {
                            "rule": "binary-shadowing",
                            "message": (
                                f"{engine_id}: a binary inside the project root shadows the "
                                f"trusted resolution and is never trusted or probed. {entry['action']}"
                            ).strip(),
                        }
                    )
                else:
                    findings.append(
                        {
                            "rule": "engine-missing",
                            "message": f"{engine_id} is not installed. {entry['action']}".strip(),
                        }
                    )

        # R15.3: doctor calls manifest verification explicitly -- the resolver
        # silently falls back to PATH on any tampered/scope-mismatched
        # manifest, so a tampered manifest that still resolves via PATH is
        # otherwise invisible.
        integrity_failed = False
        toolchains_path = root / ".rush" / "toolchains.json"
        if toolchains_path.is_file():
            try:
                selection = json.loads(toolchains_path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                selection = {}
            if isinstance(selection, dict):
                for engine_id, sel in selection.items():
                    manifest_path = (
                        sel.get("manifest") if isinstance(sel, dict) else None
                    )
                    if not isinstance(manifest_path, str):
                        continue
                    manifest = read_manifest(Path(manifest_path))
                    if manifest is None:
                        continue
                    try:
                        verify_manifest(manifest, project_root=root)
                    except ManifestVerificationError as exc:
                        integrity_failed = True
                        findings.append(
                            {
                                "rule": "engine-integrity",
                                "message": (
                                    f"{engine_id}: manifest verification failed "
                                    f"({exc.code})."
                                ),
                            }
                        )

        status: ToolStatus
        if integrity_failed:
            status = "error"
        elif any(
            f["rule"]
            in {"engine-missing", "no_supported_engine_for_stack", "binary-shadowing"}
            for f in findings
        ):
            status = "warn"
        else:
            status = "ok"

        installed = sum(1 for e in entries if e["disposition"] == "installed")
        total_required = sum(1 for e in entries if e["required"])
        summary = (
            f"doctor: {installed}/{total_required} required engine(s) installed, "
            f"{len(findings)} finding(s)."
        )

        return ToolResult(
            tool=self.name,
            status=status,
            duration_ms=10,
            summary=summary,
            findings=findings,
        )
