"""Plugin Loader and Subprocess Executor.

Architecture §8, Phase 28.
Enforces Control 6: Repository Trust Gating before launching external scripts.
"""

from __future__ import annotations

import shlex
import tomllib
from dataclasses import dataclass
from pathlib import Path

from rush.logging import get_logger, log_subsystem
from rush.plugins.validator import validate_plugin_output
from rush.tools.base import ToolResult
from rush.tools.common import run_subprocess

logger = get_logger("plugins.loader")


@dataclass(frozen=True)
class PluginSpec:
    """Specification for an external trust-gated plugin."""

    name: str
    executable_path: Path
    command: list[str]
    description: str = ""
    file_extensions: tuple[str, ...] = ()
    timeout_seconds: float = 30.0


@dataclass(frozen=True)
class CustomPlugin:
    """Represents a discovered user-defined or agent-generated plugin."""

    name: str
    command: list[str]
    description: str = ""
    file_extensions: tuple[str, ...] = ()



def discover_plugins(root: Path) -> list[CustomPlugin]:
    """Discover plugins defined in rush.toml under [plugins.<name>]."""
    cfg_file = (root if root.is_dir() else root.parent) / "rush.toml"
    plugins: list[CustomPlugin] = []

    if not cfg_file.is_file():
        return plugins

    try:
        data = tomllib.loads(cfg_file.read_text(encoding="utf-8"))
        plugins_table = data.get("plugins", {})
        for name, p_data in plugins_table.items():
            if isinstance(p_data, dict):
                cmd_raw = p_data.get("command", "")
                cmd = (
                    shlex.split(cmd_raw) if isinstance(cmd_raw, str) else list(cmd_raw)
                )
                desc = p_data.get("description", f"Custom plugin: {name}")
                exts = tuple(p_data.get("file_extensions", []))
                plugins.append(
                    CustomPlugin(
                        name=name,
                        command=cmd,
                        description=desc,
                        file_extensions=exts,
                    )
                )
    except Exception as exc:  # noqa: BLE001
        log_subsystem(
            "plugin", "ERROR", f"Failed to parse plugins in {cfg_file}: {exc}"
        )

    return plugins


def execute_plugin(
    plugin: CustomPlugin,
    target_path: Path,
    is_trusted: bool,
    cwd: Path | None = None,
    extra_args: list[str] | None = None,
) -> ToolResult:
    """Execute custom plugin subprocess after verifying repository trust."""
    if not is_trusted:
        log_subsystem(
            "plugin",
            "TRUST_GATE",
            f"Blocked untrusted plugin '{plugin.name}'. Run 'rush trust' to enable.",
        )
        return ToolResult(
            tool=plugin.name,
            status="skipped",
            duration_ms=0,
            summary=f"plugin: trust required to execute '{plugin.name}'. Run 'rush trust' to authorize.",
            findings=[],
        )

    exec_cmd = list(plugin.command) + [str(target_path)] + (extra_args or [])
    log_subsystem(
        "plugin", "INFO", f"Executing custom plugin '{plugin.name}': {exec_cmd}"
    )

    proc = run_subprocess(
        exec_cmd,
        cwd=cwd or (target_path if target_path.is_dir() else target_path.parent),
    )

    if proc.returncode != 0 and not proc.stdout.strip():
        return ToolResult(
            tool=plugin.name,
            status="error",
            duration_ms=0,
            summary=f"plugin: '{plugin.name}' exited with code {proc.returncode}. Error: {proc.stderr.strip()}",
            findings=[],
        )

    return validate_plugin_output(proc.stdout, plugin_name=plugin.name)


class PluginLoader:
    """Discovers and manages external plugins from rush.toml."""

    def __init__(self, repo_root: Path) -> None:
        self.repo_root = repo_root.resolve()

    def discover_plugins(self) -> list[CustomPlugin]:
        return discover_plugins(self.repo_root)

