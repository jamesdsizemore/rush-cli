"""rush.toml discovery + parsing.

Architecture §8.

Discovery rule:
    start = path (file or directory passed to tool)
    loop:
        candidate = start / "rush.toml"
        if candidate.exists(): return parse(candidate)
        if start has ".git" (file or directory): stop  → no config
        if start.parent == start: stop  → filesystem root, no config
        start = start.parent

Override order (last wins):
    1. Hardcoded defaults (in the dataclasses below)
    2. rush.toml values
    3. CLI flags
"""

from __future__ import annotations

import tomllib
import types
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .catalog import ToolOptionSpec, ToolOptionValue


class RushConfigError(Exception):
    """Raised when rush.toml is malformed."""


@dataclass
class ProjectConfig:
    src: list[str] = field(default_factory=lambda: ["src"])
    test: list[str] = field(default_factory=lambda: ["tests"])
    exclude: list[str] = field(
        default_factory=lambda: ["**/.venv/**", "**/node_modules/**"]
    )


@dataclass
class ToolConfig:
    engine_args: list[str] = field(default_factory=list)
    check: bool = False
    options: Mapping[str, ToolOptionValue] = field(default_factory=dict)


@dataclass
class ReviewConfig:
    max_file_lines: int = 400
    fail_on: list[str] = field(default_factory=list)
    use_graft: bool = False
    scaffold_markers: list[str] = field(default_factory=list)
    source_policy_exclude: list[str] = field(default_factory=list)


@dataclass
class CacheConfig:
    enabled: bool = True
    dir: str = ".rush"
    max_size_mb: int = 100


@dataclass
class RushConfig:
    project: ProjectConfig = field(default_factory=ProjectConfig)
    tools: dict[str, ToolConfig] = field(default_factory=dict)
    review: ReviewConfig = field(default_factory=ReviewConfig)
    cache: CacheConfig = field(default_factory=CacheConfig)
    log_level: str = "warn"
    # Path of the rush.toml we loaded from, or None if defaults-only.
    source: Path | None = None


def _has_git_marker(p: Path) -> bool:
    """True if `p` is the git root (contains .git) or a child of one we crossed."""
    cur = p
    while True:
        if (cur / ".git").exists():
            return True
        if cur.parent == cur:
            return False
        cur = cur.parent


def discover_config(start: Path) -> Path | None:
    """Walk up from `start` looking for rush.toml. Stop at git root or filesystem root.

    Returns the path to rush.toml, or None if not found.
    """
    cur = start if start.is_dir() else start.parent
    while True:
        candidate = cur / "rush.toml"
        if candidate.is_file():
            return candidate
        # Stop at git root (config shouldn't escape the repo)
        if (cur / ".git").exists():
            return None
        if cur.parent == cur:
            return None
        cur = cur.parent


def load_config(start: Path | None = None) -> RushConfig:
    """Load rush.toml from `start` (or cwd if None), applying defaults.

    Never raises on missing config — returns defaults. Raises RushConfigError
    only when rush.toml exists but is malformed.
    """
    if start is None:
        start = Path.cwd()
    cfg_path = discover_config(start)
    if cfg_path is None:
        return RushConfig()
    try:
        raw = tomllib.loads(cfg_path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as e:
        raise RushConfigError(f"malformed rush.toml at {cfg_path}: {e}") from e

    return _parse(raw, cfg_path)


def _parse(raw: dict, source: Path) -> RushConfig:
    from .catalog import TOOL_SPECS

    project_raw = raw.get("project", {}) or {}
    project = ProjectConfig(
        src=list(project_raw.get("src", ["src"])),
        test=list(project_raw.get("test", ["tests"])),
        exclude=list(project_raw.get("exclude", ["**/.venv/**", "**/node_modules/**"])),
    )

    tools: dict[str, ToolConfig] = {}
    for tool_name, tr in (raw.get("tools", {}) or {}).items():
        if tool_name not in TOOL_SPECS:
            raise RushConfigError(f"unknown tool in {source}: {tool_name}")
        spec = TOOL_SPECS[tool_name]
        if spec.maturity in {
            "guarded_placeholder",
            "browser_runtime",
        }:
            raise RushConfigError(
                f"tool {tool_name} does not accept tool configuration; "
                "it is not a configurable local adapter"
            )
        tr = tr or {}
        declared_options: dict[str, ToolOptionSpec] = {
            opt.name: opt for opt in getattr(spec, "option_specs", ())
        }
        reserved_keys = {"engine_args", "check"}
        for key in tr:
            if key not in reserved_keys and key not in declared_options:
                raise RushConfigError(
                    f"unknown option '{key}' for tool '{tool_name}' in {source}"
                )

        parsed_options: dict[str, ToolOptionValue] = {}
        for opt_name, opt_spec in declared_options.items():
            if opt_name in tr:
                val = tr[opt_name]
                if opt_spec.value_type is bool:
                    if not isinstance(val, bool):
                        raise RushConfigError(
                            f"option '{opt_name}' for tool '{tool_name}' must be bool, got {type(val).__name__}"
                        )
                elif opt_spec.value_type is int:
                    if not isinstance(val, int) or isinstance(val, bool):
                        raise RushConfigError(
                            f"option '{opt_name}' for tool '{tool_name}' must be int, got {type(val).__name__}"
                        )
                elif opt_spec.value_type is float:
                    if not isinstance(val, (int, float)) or isinstance(val, bool):
                        raise RushConfigError(
                            f"option '{opt_name}' for tool '{tool_name}' must be float, got {type(val).__name__}"
                        )
                    val = float(val)
                elif opt_spec.value_type is str:
                    if not isinstance(val, str):
                        raise RushConfigError(
                            f"option '{opt_name}' for tool '{tool_name}' must be str, got {type(val).__name__}"
                        )
                elif opt_spec.value_type is tuple:
                    if isinstance(val, list):
                        if not all(isinstance(x, str) for x in val):
                            raise RushConfigError(
                                f"option '{opt_name}' for tool '{tool_name}' must be list of strings"
                            )
                        val = tuple(val)
                    elif isinstance(val, tuple):
                        if not all(isinstance(x, str) for x in val):
                            raise RushConfigError(
                                f"option '{opt_name}' for tool '{tool_name}' must be tuple of strings"
                            )
                    else:
                        raise RushConfigError(
                            f"option '{opt_name}' for tool '{tool_name}' must be list/tuple of strings, got {type(val).__name__}"
                        )

                if opt_spec.choices:
                    if opt_spec.value_type is tuple:
                        for item in val:
                            if item not in opt_spec.choices:
                                raise RushConfigError(
                                    f"option '{opt_name}' item '{item}' for tool '{tool_name}' not in allowed choices {opt_spec.choices}"
                                )
                    else:
                        if val not in opt_spec.choices:
                            raise RushConfigError(
                                f"option '{opt_name}' value '{val}' for tool '{tool_name}' not in allowed choices {opt_spec.choices}"
                            )

                if opt_spec.minimum is not None and val < opt_spec.minimum:
                    raise RushConfigError(
                        f"option '{opt_name}' value {val} for tool '{tool_name}' is less than minimum {opt_spec.minimum}"
                    )
                if opt_spec.maximum is not None and val > opt_spec.maximum:
                    raise RushConfigError(
                        f"option '{opt_name}' value {val} for tool '{tool_name}' is greater than maximum {opt_spec.maximum}"
                    )

                if opt_spec.path_kind in ("file", "directory"):
                    path_str = str(val)
                    p = Path(path_str)
                    if (
                        p.is_absolute()
                        or path_str.startswith(("/", "\\"))
                        or bool(p.drive)
                        or ".." in p.parts
                    ):
                        raise RushConfigError(
                            f"option '{opt_name}' path '{path_str}' for tool '{tool_name}' must be a relative, non-parent-traversing path"
                        )

                parsed_options[opt_name] = val
            elif opt_spec.required:
                raise RushConfigError(
                    f"required option '{opt_name}' for tool '{tool_name}' is missing in {source}"
                )
            elif opt_spec.default is not None:
                parsed_options[opt_name] = opt_spec.default

        tools[tool_name] = ToolConfig(
            engine_args=list(tr.get("engine_args", [])),
            check=bool(tr.get("check", False)),
            options=types.MappingProxyType(parsed_options),
        )

    review_raw = raw.get("review", {}) or {}
    review = ReviewConfig(
        max_file_lines=int(review_raw.get("max_file_lines", 400)),
        fail_on=list(review_raw.get("fail_on", [])),
        use_graft=bool(review_raw.get("use_graft", False)),
        scaffold_markers=list(review_raw.get("scaffold_markers", [])),
        source_policy_exclude=list(review_raw.get("source_policy_exclude", [])),
    )

    cache_raw = raw.get("cache", {}) or {}
    cache = CacheConfig(
        enabled=bool(cache_raw.get("enabled", True)),
        dir=str(cache_raw.get("dir", ".rush")),
        max_size_mb=int(cache_raw.get("max_size_mb", 100)),
    )

    return RushConfig(
        project=project,
        tools=tools,
        review=review,
        cache=cache,
        log_level=str(raw.get("log_level", "warn")),
        source=source,
    )


def resolve_tool_options(
    tool_name: str,
    config_options: Mapping[str, Any] | None = None,
    invocation_options: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Resolve tool options with precedence: default -> config -> invocation."""
    from .catalog import TOOL_SPECS

    spec = TOOL_SPECS.get(tool_name) or TOOL_SPECS.get(tool_name.replace("_", "-"))
    if not spec:
        return {}

    declared_options = {opt.name: opt for opt in getattr(spec, "option_specs", ())}
    resolved: dict[str, Any] = {}
    for name, opt in declared_options.items():
        resolved[name] = opt.default

    if config_options:
        for name, val in config_options.items():
            if name not in declared_options:
                raise RushConfigError(f"unknown option '{name}' for tool '{tool_name}'")
            opt = declared_options[name]
            if opt.value_type is float:
                try:
                    resolved[name] = float(val)
                except (ValueError, TypeError):
                    raise RushConfigError(
                        f"option '{name}' for tool '{tool_name}' must be float"
                    )
            elif opt.value_type is int and not isinstance(val, bool):
                try:
                    resolved[name] = int(val)
                except (ValueError, TypeError):
                    raise RushConfigError(
                        f"option '{name}' for tool '{tool_name}' must be int"
                    )
            elif opt.value_type is bool:
                resolved[name] = (
                    str(val).lower() in ("true", "1", "yes")
                    if isinstance(val, str)
                    else bool(val)
                )
            else:
                resolved[name] = val

    if invocation_options:
        for name, val in invocation_options.items():
            if name not in declared_options:
                raise RushConfigError(f"unknown option '{name}' for tool '{tool_name}'")
            opt = declared_options[name]
            if opt.value_type is float:
                try:
                    resolved[name] = float(val)
                except (ValueError, TypeError):
                    raise RushConfigError(
                        f"option '{name}' for tool '{tool_name}' must be float"
                    )
            elif opt.value_type is int and not isinstance(val, bool):
                try:
                    resolved[name] = int(val)
                except (ValueError, TypeError):
                    raise RushConfigError(
                        f"option '{name}' for tool '{tool_name}' must be int"
                    )
            elif opt.value_type is bool:
                resolved[name] = (
                    str(val).lower() in ("true", "1", "yes")
                    if isinstance(val, str)
                    else bool(val)
                )
            else:
                resolved[name] = val

    return resolved


def resolve_memory_record(cfg: Mapping[str, Any] | None) -> bool:
    """Resolve the single opt-in `[tools.memory] record` observation flag. Default `False`.

    MC05 (Phase 63) adds only this key; MC14 adds the remaining `tools.memory`
    configuration keys later. Accepts either a snapshotted `RushConfig`-shaped
    mapping (`tools.memory.options.record`, produced by `_parse()`/invocation
    config snapshotting) or a flat test mapping (`tools.memory.record`).
    """
    if not isinstance(cfg, Mapping):
        return False
    tools = cfg.get("tools")
    if not isinstance(tools, Mapping):
        return False
    memory_cfg = tools.get("memory")
    if not isinstance(memory_cfg, Mapping):
        return False
    options = memory_cfg.get("options")
    if isinstance(options, Mapping) and "record" in options:
        return bool(options["record"])
    return bool(memory_cfg.get("record", False))
