"""aislop adapter for AI-generated code anti-pattern detection."""

from __future__ import annotations

import importlib.util
import json
import os
import re
import shutil
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import Path

from ..permissions import ExecutionPermissions, build_execution_metadata
from ..tools.base import Finding, ToolResult, ToolStatus
from ..tools.common import resolve_binary, run_subprocess, skipped_result
from .base import Engine, EngineResult, env_kwargs, ownership_kwargs

# aislop runs its npm package through `npx`, which downloads it on a cold npm
# cache. The calling tool's grants are ambient here (context-local, like
# `cancel_scope`); without `download`, npm runs offline.
_GRANTS: ContextVar[ExecutionPermissions | None] = ContextVar(
    "rush_aislop_grants", default=None
)
_REQUIRED = ExecutionPermissions(download=True)
AISLOP_NO_TELEMETRY_ENV = {"AISLOP_NO_TELEMETRY": "1", "DO_NOT_TRACK": "1"}


def _granted() -> ExecutionPermissions:
    return _GRANTS.get() or ExecutionPermissions()


_VERSION_RE = re.compile(r"""^__version__\s*=\s*["']([^"']+)["']""", re.MULTILINE)
NO_NODE_STDERR = "aislop for Python requires Node.js tooling on PATH."


def _launcher_package_init(binary: str) -> Path | None:
    """`aislop_py/__init__.py` of the install `binary` (aislop's Python
    launcher) belongs to, else of Rush's own interpreter."""
    real = Path(os.path.realpath(binary))
    # A venv or `uv tool` env (the POSIX uv shim symlinks into it), then Rush's
    # provisioned `uv tool install` layout (UV_TOOL_DIR=<bin dir>/tools).
    # ponytail: fixed layouts; a Windows shim copied outside its env (plain
    # `uv tool install`) falls back to Rush's interpreter, read the uv receipt
    # if that ever pins a different version.
    for env in (real.parent.parent, real.parent / "tools" / "aislop"):
        for init in (
            *sorted(env.glob("lib/python*/site-packages/aislop_py/__init__.py")),
            env / "Lib" / "site-packages" / "aislop_py" / "__init__.py",
        ):
            if init.is_file():
                return init
    spec = importlib.util.find_spec("aislop_py")
    return Path(spec.origin) if spec is not None and spec.origin else None


def _pinned_version(binary: str) -> str | None:
    """The npm version aislop's launcher pins (its `aislop_py.__version__`)."""
    init = _launcher_package_init(binary)
    if init is None:
        return None
    try:
        match = _VERSION_RE.search(init.read_text(encoding="utf-8"))
    except OSError:
        return None
    return match.group(1) if match else None


def npm_package(binary: str) -> str | None:
    """The npm package aislop runs: `AISLOP_NPM_PACKAGE`, else the version
    the launcher at `binary` pins."""
    package = os.environ.get("AISLOP_NPM_PACKAGE")
    if package:
        return package
    version = _pinned_version(binary)
    return f"aislop@{version}" if version else None


def npm_command(
    package: str,
    args: list[str],
    which: Callable[[str], str | None] | None = None,
) -> list[str] | None:
    """aislop_py/cli.py's npm argv, without its os.execve(): execve cannot run
    Windows' npx.cmd, so the launcher crashes there."""
    find = which or shutil.which
    npx = find("npx")
    if npx:
        return [npx, "--yes", "--package", package, "aislop", *args]
    npm = find("npm")
    if npm:
        return [npm, "exec", "--yes", "--package", package, "--", "aislop", *args]
    return None


def _install_channel(binary: str) -> str:
    """aislop_py/cli.py's install-channel detection, for the launcher path."""
    existing = os.environ.get("AISLOP_INSTALL_CHANNEL", "").strip().lower()
    if existing:
        return existing
    if "pipx" in str(Path(binary).resolve()).lower() or os.environ.get("PIPX_HOME"):
        return "pipx"
    return "pip"


@contextmanager
def aislop_grants(permissions: ExecutionPermissions) -> Iterator[None]:
    """Make the calling tool's grants decide whether aislop may download."""
    token = _GRANTS.set(permissions)
    try:
        yield
    finally:
        _GRANTS.reset(token)


class AislopEngine(Engine):
    name = "aislop"
    binary = "aislop"
    file_extensions = ("py", "js", "ts", "jsx", "tsx", "go", "rs", "java", "c", "cpp")

    def child_env(self) -> dict[str, str]:
        # aislop's npm cli.js honors both telemetry opt-outs; npm runs offline
        # unless the calling tool holds the download grant.
        env = {**os.environ, **AISLOP_NO_TELEMETRY_ENV}
        if not _granted().download:
            env["npm_config_offline"] = "true"
        return env

    def run(
        self,
        path: Path,
        args: list[str],
        cwd: Path | None = None,
        *,
        owner_instance_id: str | None = None,
        run_id: str | None = None,
    ) -> EngineResult:
        binary_path = resolve_binary(self.binary) or self.binary
        # aislop 0.16.1: `scan [options] [directory]` takes one positional, so a
        # file target scans its parent restricted to that file via --include.
        target = path.absolute()
        include: list[str] = []
        if target.is_file():
            include = ["--include", target.name]
            target = target.parent
        scan = ["scan", "--format=json", *args, *include, str(target)]

        # Run the launcher's pinned npm package directly, never the launcher.
        package = npm_package(binary_path)
        if package is None:
            return self._not_run(
                target,
                1,
                f"aislop: no aislop_py package found for {binary_path} "
                "to pin its npm version",
            )
        argv = npm_command(package, scan)
        if argv is None:
            return self._not_run(target, 127, NO_NODE_STDERR)

        env = self.child_env()
        env.setdefault("AISLOP_INSTALL_CHANNEL", _install_channel(binary_path))
        proc = run_subprocess(
            argv,
            cwd=target,
            timeout=120,
            **env_kwargs(env),
            **ownership_kwargs(owner_instance_id, run_id),
        )

        parsed = None
        findings_raw: list[dict] = []
        if proc.stdout.strip():
            try:
                parsed = json.loads(proc.stdout)
                if isinstance(parsed, list):
                    findings_raw = parsed
                elif isinstance(parsed, dict) and "diagnostics" in parsed:
                    findings_raw = parsed["diagnostics"]
                elif isinstance(parsed, dict) and "issues" in parsed:
                    findings_raw = parsed["issues"]
            except json.JSONDecodeError:
                parsed = None

        return EngineResult(
            exit_code=proc.returncode,
            stdout=proc.stdout,
            stderr=proc.stderr,
            parsed=parsed,
            findings=findings_raw,
            summary=f"aislop exit {proc.returncode}",
            duration_ms=0,
            cwd=str(target),
        )

    @staticmethod
    def _not_run(target: Path, exit_code: int, stderr: str) -> EngineResult:
        return EngineResult(
            exit_code=exit_code,
            stdout="",
            stderr=stderr,
            parsed=None,
            findings=[],
            summary=f"aislop exit {exit_code}",
            duration_ms=0,
            cwd=str(target),
        )

    def version(
        self,
        *,
        owner_instance_id: str | None = None,
        run_id: str | None = None,
    ) -> str | None:
        """The pinned npm version itself: `aislop --version` would run the
        launcher, which crashes on Windows."""
        binary_path = resolve_binary(self.binary)
        return _pinned_version(binary_path) if binary_path else None

    def normalize(self, raw: EngineResult, path: Path, tool_name: str) -> ToolResult:
        findings: list[Finding] = []
        base = Path(raw.get("cwd") or path)
        for item in raw.get("findings", []):
            sev = item.get("severity", "warning").lower()
            if "filePath" in item:
                # aislop 0.16.1 `diagnostics`: filePath is relative to the
                # scanned directory; rule is namespaced by its aislop engine.
                file = str(base / item["filePath"])
                rule = f"aislop/{item.get('engine', 'aislop')}/{item.get('rule', 'slop-pattern')}"
            else:
                file = item.get("file", str(path))
                rule = f"aislop/{item.get('rule_id', item.get('rule', 'slop-pattern'))}"
            findings.append(
                {
                    "path": file,
                    "line": item.get("line", 0),
                    "column": item.get("column", 0),
                    "rule": rule,
                    "severity": "error"
                    if sev in ("error", "fatal", "critical")
                    else "warn",
                    "message": item.get(
                        "message", "AI-generated anti-pattern detected"
                    ),
                    "fix": item.get("fix") or item.get("suggested_fix"),
                    "remediation": item.get("help")
                    or item.get("remediation")
                    or item.get("explanation"),
                }
            )

        parsed = raw.get("parsed")
        reported = isinstance(parsed, list) or (
            isinstance(parsed, dict) and ("diagnostics" in parsed or "issues" in parsed)
        )
        status: ToolStatus
        if (
            not reported
            and raw.get("exit_code") == 127
            and NO_NODE_STDERR in (raw.get("stderr") or "")
        ):
            # aislop runs its pinned npm package through npx: without
            # Node.js on PATH the engine is not installed, not broken.
            return skipped_result(
                tool_name,
                self.name,
                "npx (Node.js) not on PATH (install: Node.js; aislop runs its "
                "pinned npm package through npx)",
            )
        if (
            not reported
            and not _granted().download
            and "ENOTCACHED" in (raw.get("stderr") or "")
        ):
            # Offline npm and the package is not cached: fetching it needs
            # the download grant. Not run, never an engine error.
            return skipped_result(
                tool_name,
                self.name,
                "requires permission: --allow-download (aislop's npm package "
                "is not in the local npm cache)",
                metadata={
                    "execution": build_execution_metadata(
                        "executed",
                        requested=_REQUIRED,
                        granted=_granted(),
                        producer=self.name,
                        extra={"disposition": "not_run", "cause": "permission_denied"},
                    )
                },
            )
        if not reported:
            # aislop exits 1 whenever it reports diagnostics, so only a
            # missing/unrecognized JSON report is an engine error.
            status = "error"
            stderr = (raw.get("stderr") or "").strip()[:500]
            summary = f"aislop produced no JSON report (exit {raw.get('exit_code', 0)})"
            if stderr:
                summary += f": {stderr}"
        else:
            status = (
                "fail"
                if any(f["severity"] == "error" for f in findings)
                else ("warn" if findings else "ok")
            )
            summary = f"aislop: {len(findings)} anti-pattern finding(s)"

        return ToolResult(
            tool=tool_name,
            engine=self.name,
            engine_version=self.version(),
            status=status,
            duration_ms=raw.get("duration_ms", 0),
            summary=summary,
            findings=findings,
            raw=raw.get("parsed"),
        )
