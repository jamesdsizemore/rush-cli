"""Plugin Loader and Subprocess Executor.

Architecture §8, Phase 28.
Enforces Control 6: Repository Trust Gating before launching external scripts.
"""

from __future__ import annotations

import shlex
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from rush.contracts.results import ToolResultV1
from rush.logging import get_logger, log_subsystem

if TYPE_CHECKING:
    from rush.plugins.closure import PluginClosureManifest

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
    closure: PluginClosureManifest | None = None
    secret_refs: tuple[str, ...] = ()
    channel_type: str = "stdin"


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
    plugin: CustomPlugin | PluginSpec,
    target_path: Path,
    is_trusted: bool = False,
    cwd: Path | None = None,
    extra_args: list[str] | None = None,
) -> ToolResultV1:
    """Execute custom plugin subprocess (deprecated: delegates to HardenedPluginExecutor)."""
    import warnings

    warnings.warn(
        "execute_plugin is deprecated; use HardenedPluginExecutor.execute() instead.",
        DeprecationWarning,
        stacklevel=2,
    )
    from rush.plugins.closure import build_plugin_closure
    from rush.plugins.executor import HardenedPluginExecutor
    from rush.plugins.snapshot_store import PluginSnapshotStore
    from rush.plugins.trust_store import PluginTrustStore

    repo_root = cwd or (target_path if target_path.is_dir() else target_path.parent)
    trust_store = PluginTrustStore(repo_root=repo_root)
    snapshot_store = PluginSnapshotStore()
    executor = HardenedPluginExecutor(
        repo_root=repo_root,
        trust_store=trust_store,
        snapshot_store=snapshot_store,
    )

    if isinstance(plugin, PluginSpec):
        spec = plugin
    else:
        exec_path = (
            Path(plugin.command[1])
            if len(plugin.command) > 1 and not plugin.command[1].startswith("-")
            else Path(plugin.command[0])
        )
        if not exec_path.is_absolute():
            exec_path = (repo_root / exec_path).resolve()
        spec = PluginSpec(
            name=plugin.name,
            executable_path=exec_path,
            command=list(plugin.command),
            description=plugin.description,
            file_extensions=plugin.file_extensions,
        )

    if not is_trusted:
        return executor._fail_untrusted(spec)

    # If is_trusted, ensure snapshot and trust are registered
    if not trust_store.load_trust_store().get(spec.name):
        plugin_root = (
            spec.executable_path.parent if spec.executable_path.is_file() else repo_root
        )
        closure = build_plugin_closure(
            plugin_root=plugin_root,
            entrypoint=spec.executable_path,
            config={"name": spec.name, "command": spec.command},
            plugin_name=spec.name,
        )
        snap_dir = snapshot_store.materialize_snapshot(
            closure=closure, plugin_root=plugin_root
        )
        trust_store.grant_trust(spec.name, closure.closure_digest, snap_dir)
        spec = PluginSpec(
            name=spec.name,
            executable_path=spec.executable_path,
            command=spec.command,
            description=spec.description,
            file_extensions=spec.file_extensions,
            closure=closure,
        )

    paths = [target_path] if target_path.is_file() else []
    return executor.execute(spec, paths=paths)


class PluginLoader:
    """Discovers and manages external plugins from rush.toml."""

    def __init__(self, repo_root: Path) -> None:
        self.repo_root = repo_root.resolve()

    def discover_plugins(self) -> list[CustomPlugin]:
        return discover_plugins(self.repo_root)
