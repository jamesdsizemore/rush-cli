"""Hardened plugin executor with environment sanitization and subprocess isolation."""

from __future__ import annotations

import json
import time
from pathlib import Path

from rush.plugins.loader import PluginSpec
from rush.plugins.sandboxed_env import SandboxedEnvironment
from rush.plugins.trust_store import PluginTrustStore
from rush.tools.base import Finding, ToolResult
from rush.tools.common import run_subprocess


class HardenedPluginExecutor:
    """Executes trust-gated plugins under bounded subprocess isolation."""

    def __init__(self, repo_root: Path) -> None:
        self.repo_root = repo_root.resolve()
        self.trust_store = PluginTrustStore(self.repo_root)

    def execute(
        self,
        plugin: PluginSpec,
        paths: list[Path],
        allow_untrusted: bool = False,
    ) -> ToolResult:
        if not allow_untrusted and not self.trust_store.is_trusted(
            plugin.name, plugin.executable_path
        ):
            finding: Finding = {
                "path": str(plugin.executable_path),
                "line": 1,
                "column": 1,
                "rule": "untrusted-plugin-execution-blocked",
                "severity": "warn",
                "message": "Plugin blocked by zero-trust security gate.",
            }
            return {
                "tool": "plugin",
                "engine": plugin.name,
                "engine_version": None,
                "status": "skipped",
                "duration_ms": 0,
                "summary": f"Plugin '{plugin.name}' is untrusted. Run 'rush trust grant {plugin.name}' to authorize.",
                "findings": [finding],
            }

        start_time = time.perf_counter()
        target_args = [str(p) for p in paths]
        full_command = [*plugin.command, *target_args]
        sanitized_env = SandboxedEnvironment.get_sanitized_env()

        proc = run_subprocess(
            full_command,
            cwd=self.repo_root,
            env=sanitized_env,
            timeout=plugin.timeout_seconds,
        )
        duration_ms = int((time.perf_counter() - start_time) * 1000)
        code = proc.returncode
        stdout = proc.stdout

        try:
            data = json.loads(stdout)
            findings: list[Finding] = data.get("findings", [])
            status = data.get("status", "ok" if code == 0 else "fail")
            if status not in ("ok", "warn", "fail", "error", "skipped"):
                status = "ok" if code == 0 else "fail"
            return {
                "tool": "plugin",
                "engine": plugin.name,
                "engine_version": data.get("engine_version", "1.0"),
                "status": status,
                "duration_ms": duration_ms,
                "summary": data.get("summary", f"Plugin {plugin.name} finished."),
                "findings": findings,
            }
        except (json.JSONDecodeError, KeyError, TypeError, ValueError):
            return {
                "tool": "plugin",
                "engine": plugin.name,
                "engine_version": "1.0",
                "status": "ok" if code == 0 else "fail",
                "duration_ms": duration_ms,
                "summary": f"Plugin {plugin.name} exited with code {code}.",
                "findings": [],
            }
