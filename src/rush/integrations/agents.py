"""Agent discovery, connection planning, and Phase 63 memory activation.

Phase 65 P65-05 (F35). Discovers locally installed MCP-capable coding agents
(Claude Desktop, Claude Code, Cursor, Windsurf, Zed, Codex CLI), plans and
applies a Rush MCP server registration into each agent's own config file
without disturbing any other setting, probes whether the registration is
actually live, and activates scoped memory observation/read-back for a
connected agent.

Format-preserving edits: JSON/JSONC configs and Codex's TOML config are
edited as a targeted text splice over only the "rush" server entry's own
byte range. A hand-rolled comment/string-aware scanner (`_find_top_level_key`
/ `_skip_value`) locates that exact byte range so every other key, value,
and comment elsewhere in the file is copied through untouched -- there is no
full parse+re-serialize round trip, which would silently reformat the file
and (for Zed's JSONC) drop every comment. Backups are written next to the
original before any write; writes themselves go through the repo's existing
`atomic_write_bytes` (temp file + `os.replace`).

Registration always launches the *installed* Rush executable by absolute
path (`resolve_rush_binary`); a path inside this repository's own checkout
or a `.venv` is refused, per plan constraint "never author's checkout or
project-local uv dependency".

Memory activation reuses the existing `CASMapTransaction` (compare-and-swap
JSON map, already used by `preference_store.py`/`invariant_graph.py`) rather
than the heavier `TypedArtifactStore` SQL schema -- `MemoryFamily`/
`MemorySubject` are closed `Literal`s owned by `memory/store.py`, which is
outside this task's allowed files, so no new subject/family is introduced.
Project scope is a plain project-root argument (isolates naturally, one CAS
file per project just like `preferences.json`); user scope is a CAS file
under `default_data_root() / "user"`. Session and agent are dimensions of
the CAS map's own entry key, never separate storage.
"""

from __future__ import annotations

import difflib
import errno
import hashlib
import json
import os
import platform
import re
import shlex
import shutil
import stat
import subprocess
import tempfile
import time
import tomllib
from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager, suppress
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal, overload

from rush.memory.transactions import CASMapTransaction, StoreError
from rush.setup.provision import default_data_root

ConfigFormat = Literal["json", "jsonc", "toml"]
AgentDiscoveryStatus = Literal[
    "not_detected", "detected", "registered", "misconfigured", "malformed", "read_only"
]


class AgentConnectionError(Exception):
    """Base error for every agent-connection operation."""


class UnknownAgentError(AgentConnectionError):
    """Raised for an agent_id that is neither a known adapter nor overridden."""


class ReadOnlyConfigError(AgentConnectionError):
    """Raised when a config-edit registration targets a read-only file."""


class MalformedConfigError(AgentConnectionError):
    """Raised when a config file's structure cannot be safely edited."""


# --- Path candidates (os_name, home) -> ordered list of Path, first existing wins ---


def _claude_desktop_paths(os_name: str, home: Path) -> list[Path]:
    if os_name == "Darwin":
        return [
            home
            / "Library"
            / "Application Support"
            / "Claude"
            / "claude_desktop_config.json"
        ]
    if os_name == "Windows":
        return [home / "AppData" / "Roaming" / "Claude" / "claude_desktop_config.json"]
    return [home / ".config" / "Claude" / "claude_desktop_config.json"]


def _claude_code_paths(_os_name: str, home: Path) -> list[Path]:
    return [home / ".claude.json"]


def _cursor_paths(_os_name: str, home: Path) -> list[Path]:
    return [home / ".cursor" / "mcp.json"]


def _windsurf_paths(_os_name: str, home: Path) -> list[Path]:
    return [home / ".codeium" / "windsurf" / "mcp_config.json"]


def _zed_paths(os_name: str, home: Path) -> list[Path]:
    if os_name == "Windows":
        return [home / "AppData" / "Roaming" / "Zed" / "settings.json"]
    return [home / ".config" / "zed" / "settings.json"]


def _codex_paths(_os_name: str, home: Path) -> list[Path]:
    return [home / ".codex" / "config.toml"]


@dataclass(frozen=True)
class AgentAdapter:
    """Deterministic detection/config schema for one supported local agent."""

    agent_id: str
    display_name: str
    config_format: ConfigFormat
    servers_key: tuple[str, ...]
    restart_required: bool
    config_paths: Any  # Callable[[str, Path], list[Path]]
    native_binary: str | None = None


ADAPTERS: dict[str, AgentAdapter] = {
    "claude-desktop": AgentAdapter(
        "claude-desktop",
        "Claude Desktop",
        "json",
        ("mcpServers",),
        True,
        _claude_desktop_paths,
    ),
    "claude-code": AgentAdapter(
        "claude-code",
        "Claude Code",
        "json",
        ("mcpServers",),
        False,
        _claude_code_paths,
        "claude",
    ),
    "cursor": AgentAdapter(
        "cursor", "Cursor", "json", ("mcpServers",), True, _cursor_paths
    ),
    "windsurf": AgentAdapter(
        "windsurf", "Windsurf", "json", ("mcpServers",), True, _windsurf_paths
    ),
    "zed": AgentAdapter("zed", "Zed", "jsonc", ("context_servers",), True, _zed_paths),
    "codex": AgentAdapter(
        "codex", "Codex CLI", "toml", ("mcp_servers",), False, _codex_paths
    ),
}


# Phase 70 T4 (D1): new registrations request the core profile explicitly; a
# pre-T4 entry (`mcp serve`, no profile) is the full server.
MCP_PROFILES = ("core", "full")
LEGACY_SERVE_ARGS: tuple[str, ...] = ("mcp", "serve")
CORE_SERVE_ARGS: tuple[str, ...] = ("mcp", "serve", "--profile", "core")
RegistrationProfile = Literal["legacy_full", "core", "full", "unrecognized"]


def build_stdio_entry(
    rush_binary: str, *, args: tuple[str, ...] = CORE_SERVE_ARGS
) -> dict[str, Any]:
    """Generic stdio MCP server spec shared by every adapter."""
    return {"command": rush_binary, "args": list(args)}


def classify_registration_profile(entry: Any) -> RegistrationProfile:
    """Which server profile an existing `rush` entry's args launch."""
    args = entry.get("args") if isinstance(entry, dict) else None
    if (
        not isinstance(args, list)
        or not all(isinstance(arg, str) for arg in args)
        or args[:2] != list(LEGACY_SERVE_ARGS)
        # a restricted memory-session receiver is no profile at all
        or any(arg.split("=", 1)[0] == "--memory-session" for arg in args)
    ):
        return "unrecognized"
    profiles: list[str | None] = []
    for index, arg in enumerate(args):
        if arg == "--profile":
            profiles.append(args[index + 1] if index + 1 < len(args) else None)
        elif arg.startswith("--profile="):
            profiles.append(arg.split("=", 1)[1])
    if not profiles:
        return "legacy_full"
    if len(profiles) == 1 and profiles[0] in MCP_PROFILES:
        return "core" if profiles[0] == "core" else "full"
    return "unrecognized"


def profile_serve_args(current_args: Any, profile: str) -> list[str]:
    """`current_args` with only its profile changed to `profile`.

    Args of a recognized `mcp serve` entry keep every other flag (e.g. a T26
    `--project`/`--session` binding); anything else becomes the plain
    `mcp serve --profile PROFILE`."""
    if profile not in MCP_PROFILES:
        raise ValueError(
            f"unknown MCP profile {profile!r}; valid profiles: {', '.join(MCP_PROFILES)}"
        )
    kept: list[str] = list(LEGACY_SERVE_ARGS)
    if classify_registration_profile({"args": current_args}) != "unrecognized":
        rest = list(current_args[2:])
        while rest:
            arg = rest.pop(0)
            if arg == "--profile":
                rest = rest[1:]
            elif not arg.startswith("--profile="):
                kept.append(arg)
    return [*kept, "--profile", profile]


def resolve_rush_binary(explicit: str | None = None) -> str:
    """Return an absolute path to an *installed* rush executable.

    Refuses a path inside this repository's own checkout or inside any
    `.venv` (a project-local uv virtualenv) -- registration must always
    launch the globally installed binary, never the developer's own
    working copy.
    """
    candidate = explicit or shutil.which("rush")
    if not candidate:
        raise AgentConnectionError(
            "no installed 'rush' executable found on PATH; pass rush_binary explicitly"
        )
    resolved = Path(candidate).resolve()
    if not resolved.is_absolute():
        raise AgentConnectionError(f"resolved rush binary is not absolute: {resolved}")
    repo_root = Path(__file__).resolve().parents[3]
    if (
        ".venv" in resolved.parts
        or resolved == repo_root
        or repo_root in resolved.parents
    ):
        raise AgentConnectionError(
            f"refusing to register a project-local rush binary: {resolved}"
        )
    return str(resolved)


# --- Comment/string-aware JSON-like scanner (shared by JSON and JSONC) -----------


def _skip_ws_and_comments(text: str, i: int) -> int:
    n = len(text)
    while i < n:
        ch = text[i]
        if ch in " \t\r\n":
            i += 1
        elif ch == "/" and i + 1 < n and text[i + 1] == "/":
            j = text.find("\n", i)
            i = n if j == -1 else j + 1
        elif ch == "/" and i + 1 < n and text[i + 1] == "*":
            j = text.find("*/", i + 2)
            if j == -1:
                raise MalformedConfigError("unterminated block comment")
            i = j + 2
        else:
            break
    return i


def _skip_string(text: str, i: int) -> int:
    n = len(text)
    if i >= n or text[i] != '"':
        raise MalformedConfigError(f"expected string at position {i}")
    i += 1
    while i < n:
        ch = text[i]
        if ch == "\\":
            i += 2
            continue
        if ch == '"':
            return i + 1
        i += 1
    raise MalformedConfigError("unterminated string")


def _skip_value(text: str, i: int) -> int:
    n = len(text)
    i = _skip_ws_and_comments(text, i)
    if i >= n:
        raise MalformedConfigError("unexpected end of document")
    ch = text[i]
    if ch == '"':
        return _skip_string(text, i)
    if ch in "{[":
        depth = 1
        i += 1
        while i < n and depth > 0:
            i = _skip_ws_and_comments(text, i)
            if i >= n:
                raise MalformedConfigError("unterminated object/array")
            c = text[i]
            if c == '"':
                i = _skip_string(text, i)
                continue
            if c in "{[":
                depth += 1
                i += 1
                continue
            if c in "}]":
                depth -= 1
                i += 1
                continue
            i += 1
        if depth != 0:
            raise MalformedConfigError("unbalanced braces/brackets")
        return i
    j = i
    while j < n and text[j] not in ",}] \t\r\n/":
        j += 1
    if j == i:
        raise MalformedConfigError(f"unrecognized value at position {i}")
    return j


def _find_top_level_key(
    text: str, body_start: int, body_end: int, key: str
) -> tuple[int, int, int, int] | None:
    """Find `key` among the entries of the object body `text[body_start:body_end]`.

    Returns (key_start, key_end, value_start, value_end) for the first
    match at this exact nesting depth, or None if absent.
    """
    i = body_start
    while i < body_end:
        i = _skip_ws_and_comments(text, i)
        if i >= body_end:
            break
        if text[i] == ",":
            i += 1
            continue
        key_start = i
        key_end = _skip_string(text, i)
        candidate = json.loads(text[key_start:key_end])
        i = _skip_ws_and_comments(text, key_end)
        if i >= body_end or text[i] != ":":
            raise MalformedConfigError(f"expected ':' after key {candidate!r}")
        i += 1
        i = _skip_ws_and_comments(text, i)
        value_start = i
        value_end = _skip_value(text, i)
        if candidate == key:
            return key_start, key_end, value_start, value_end
        i = _skip_ws_and_comments(text, value_end)
    return None


def _insert_key(
    text: str, body_start: int, body_end: int, key: str, value_text: str
) -> tuple[str, int, int]:
    has_content = _skip_ws_and_comments(text, body_start) < body_end
    prefix = ",\n  " if has_content else "\n  "
    insertion = f'{prefix}"{key}": {value_text}\n'
    new_text = text[:body_end] + insertion + text[body_end:]
    return new_text, body_start, body_end + len(insertion)


def _root_object_body(text: str) -> tuple[int, int]:
    start = _skip_ws_and_comments(text, 0)
    if start >= len(text) or text[start] != "{":
        raise MalformedConfigError("expected a JSON object at document root")
    root_end = _skip_value(text, start)
    return start + 1, root_end - 1


def _get_json_like_entry(
    text: str, servers_key: tuple[str, ...]
) -> dict[str, Any] | None:
    cur_start, cur_end = _root_object_body(text)
    for key in (*servers_key, "rush"):
        found = _find_top_level_key(text, cur_start, cur_end, key)
        if found is None:
            return None
        _, _, value_start, value_end = found
        if key == "rush":
            return json.loads(text[value_start:value_end])
        if text[value_start] != "{":
            raise MalformedConfigError(f"expected object at {key!r}")
        cur_start, cur_end = value_start + 1, value_end - 1
    return None


def _upsert_json_like(
    text: str, servers_key: tuple[str, ...], entry: dict[str, Any]
) -> str:
    cur_start, cur_end = _root_object_body(text)
    for key in servers_key:
        found = _find_top_level_key(text, cur_start, cur_end, key)
        if found is None:
            text, cur_start, cur_end = _insert_key(text, cur_start, cur_end, key, "{}")
            found = _find_top_level_key(text, cur_start, cur_end, key)
        _, _, value_start, value_end = found  # type: ignore[misc]
        if text[value_start] != "{":
            raise MalformedConfigError(f"expected object at {key!r}")
        cur_start, cur_end = value_start + 1, value_end - 1

    rush_json = json.dumps(entry, indent=2)
    found = _find_top_level_key(text, cur_start, cur_end, "rush")
    if found is not None:
        _, _, value_start, value_end = found
        return text[:value_start] + rush_json + text[value_end:]
    text, _, _ = _insert_key(text, cur_start, cur_end, "rush", rush_json)
    return text


# --- Minimal TOML block splice (Codex config.toml) --------------------------------


def _toml_value(value: Any) -> str:
    if isinstance(value, str):
        return json.dumps(value)
    if isinstance(value, list):
        return "[" + ", ".join(_toml_value(item) for item in value) + "]"
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def _render_toml_table(header: str, entry: dict[str, Any]) -> str:
    lines = [header + "\n"]
    for key, value in entry.items():
        lines.append(f"{key} = {_toml_value(value)}\n")
    return "".join(lines)


def _upsert_toml_table(
    text: str, table_path: tuple[str, ...], entry: dict[str, Any]
) -> str:
    header = "[" + ".".join(table_path) + "]"
    lines = text.splitlines(keepends=True)
    start_idx: int | None = None
    end_idx = len(lines)
    for idx, line in enumerate(lines):
        if start_idx is None and line.strip() == header:
            start_idx = idx
            continue
        if start_idx is not None and idx > start_idx and line.lstrip().startswith("["):
            end_idx = idx
            break
    block = _render_toml_table(header, entry)
    if start_idx is None:
        prefix = "".join(lines)
        if prefix and not prefix.endswith("\n"):
            prefix += "\n"
        if prefix:
            prefix += "\n"
        return prefix + block
    return "".join(lines[:start_idx]) + block + "".join(lines[end_idx:])


def _get_toml_entry(text: str, table_path: tuple[str, ...]) -> dict[str, Any] | None:
    try:
        data: Any = tomllib.loads(text)
    except tomllib.TOMLDecodeError as exc:
        raise MalformedConfigError(str(exc)) from exc
    node = data
    for key in table_path:
        if not isinstance(node, dict) or key not in node:
            return None
        node = node[key]
    return node if isinstance(node, dict) else None


def _read_rush_entry(text: str, adapter: AgentAdapter) -> dict[str, Any] | None:
    if adapter.config_format == "toml":
        return _get_toml_entry(text, (*adapter.servers_key, "rush"))
    return _get_json_like_entry(text, adapter.servers_key)


def _default_document(adapter: AgentAdapter) -> str:
    return "" if adapter.config_format == "toml" else "{\n}\n"


# --- Discovery ----------------------------------------------------------------------


@dataclass(frozen=True)
class AgentStatus:
    agent_id: str
    display_name: str
    detected: bool
    config_path: Path | None
    status: AgentDiscoveryStatus
    restart_required: bool
    error: str | None = None
    # T4: the profile an existing `rush` entry launches; None without one.
    profile: RegistrationProfile | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "agent_id": self.agent_id,
            "display_name": self.display_name,
            "detected": self.detected,
            "config_path": str(self.config_path) if self.config_path else None,
            "status": self.status,
            "restart_required": self.restart_required,
            "error": self.error,
            "profile": self.profile,
        }


def _discover_one(
    adapter: AgentAdapter, *, home: Path, os_name: str, rush_binary: str | None
) -> AgentStatus:
    candidates = adapter.config_paths(os_name, home)
    config_path = next((path for path in candidates if path.exists()), None)
    if config_path is None:
        return AgentStatus(
            adapter.agent_id,
            adapter.display_name,
            False,
            None,
            "not_detected",
            adapter.restart_required,
        )

    try:
        text = config_path.read_text(encoding="utf-8")
        rush_entry = _read_rush_entry(text, adapter)
    except Exception as exc:  # noqa: BLE001 - any structural failure isolates to this agent
        return AgentStatus(
            adapter.agent_id,
            adapter.display_name,
            True,
            config_path,
            "malformed",
            adapter.restart_required,
            error=str(exc),
        )

    writable = os.access(config_path, os.W_OK)
    if rush_entry is None:
        status: AgentDiscoveryStatus = "detected" if writable else "read_only"
        return AgentStatus(
            adapter.agent_id,
            adapter.display_name,
            True,
            config_path,
            status,
            adapter.restart_required,
        )

    command = rush_entry.get("command") if isinstance(rush_entry, dict) else None
    if rush_binary and command != rush_binary:
        status = "misconfigured"
    else:
        status = "registered"
    return AgentStatus(
        adapter.agent_id,
        adapter.display_name,
        True,
        config_path,
        status,
        adapter.restart_required,
        profile=classify_registration_profile(rush_entry),
    )


def discover_agents(
    *,
    home: Path | None = None,
    os_name: str | None = None,
    rush_binary: str | None = None,
) -> list[AgentStatus]:
    """Detect every known local agent and its current Rush registration state.

    A failure isolating to one adapter (malformed config, unreadable file)
    never affects any other adapter's reported status.
    """
    home = home or Path.home()
    os_name = os_name or platform.system()
    return [
        _discover_one(adapter, home=home, os_name=os_name, rush_binary=rush_binary)
        for adapter in ADAPTERS.values()
    ]


# --- Registration plan / apply / probe ----------------------------------------------


@dataclass(frozen=True)
class RegistrationStep:
    agent_id: str
    method: Literal["native", "config-edit"]
    config_path: Path | None
    backup_path: Path | None
    native_command: tuple[str, ...] | None
    new_text: str | None
    restart_required: bool
    # sha256 of the config file's bytes when the plan was built; None means
    # the file was absent. Apply re-checks it immediately before replacing.
    # For a project-bound Claude Code (`scope="local"`) step it is the digest
    # of the project's current `rush` entry instead: Claude rewrites
    # `~/.claude.json` constantly, so only the entry itself is comparable.
    expected_sha256: str | None = None
    # Phase 70 T26: project-bound registration (`plan_project_registration`).
    scope: Literal["user", "local"] = "user"
    project_root: Path | None = None
    entry: dict[str, Any] | None = None
    current_entry: dict[str, Any] | None = None
    diff: str = ""
    requires_consent: bool = False
    unchanged: bool = False
    # Phase 70 T4: the profile an explicit `agent connect --profile` migration
    # moves this entry to. For a native step `expected_sha256` is then the
    # digest of the current user-scope `rush` entry, re-checked before removal.
    migration_profile: str | None = None


@dataclass(frozen=True)
class AgentApplyResult:
    agent_id: str
    ok: bool
    method: Literal["native", "config-edit"]
    config_path: Path | None
    backup_path: Path | None
    restart_required: bool
    error: str | None = None
    # T4: the target changed after the plan was built; nothing was written.
    conflict: bool = False
    # T4: a native re-add and the restore of the captured entry both failed;
    # the captured entry JSON the user must restore by hand.
    recovery_required: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "agent_id": self.agent_id,
            "ok": self.ok,
            "method": self.method,
            "config_path": str(self.config_path) if self.config_path else None,
            "backup_path": str(self.backup_path) if self.backup_path else None,
            "restart_required": self.restart_required,
            "error": self.error,
            "conflict": self.conflict,
            "recovery_required": self.recovery_required,
        }


def _resolve_adapter(
    agent_id: str,
    *,
    config_path: Path | None,
    config_format: ConfigFormat | None,
    servers_key: tuple[str, ...] | None,
) -> AgentAdapter:
    known = ADAPTERS.get(agent_id)
    if known is not None:
        return known
    if config_path is None or config_format is None or servers_key is None:
        raise UnknownAgentError(
            f"unknown agent {agent_id!r}: pass config_path, config_format, and "
            "servers_key to register a generic stdio client"
        )
    fixed_path = config_path
    return AgentAdapter(
        agent_id,
        agent_id,
        config_format,
        servers_key,
        True,
        lambda _os, _home, _p=fixed_path: [_p],
    )


def plan_agent_registration(
    agent_id: str,
    *,
    rush_binary: str,
    home: Path | None = None,
    os_name: str | None = None,
    config_path: Path | None = None,
    config_format: ConfigFormat | None = None,
    servers_key: tuple[str, ...] | None = None,
    profile: str | None = None,
) -> RegistrationStep:
    """Plan how to register Rush with one agent, never writing anything yet.

    Phase 70 T4: a new entry launches `mcp serve --profile core`. An existing
    `rush` entry keeps its args exactly (only a stale command path is
    repaired; an entry already launching `rush_binary` is left untouched).
    Only an explicit `profile` -- the previewed migration of `agent connect
    --profile` -- changes an existing entry's profile, and then nothing else
    in its args.
    """
    home = home or Path.home()
    os_name = os_name or platform.system()
    adapter = _resolve_adapter(
        agent_id,
        config_path=config_path,
        config_format=config_format,
        servers_key=servers_key,
    )

    candidates = adapter.config_paths(os_name, home)
    resolved_path = config_path or next(
        (p for p in candidates if p.exists()), candidates[0]
    )

    if adapter.native_binary and shutil.which(adapter.native_binary):
        current = _capture_native_entry(resolved_path)
        entry = _planned_entry(current, rush_binary, profile)
        return RegistrationStep(
            agent_id,
            "native",
            resolved_path,
            None,
            (adapter.native_binary, "mcp", "add", "rush", "--scope", "user", "--")
            + (entry["command"], *entry["args"]),
            None,
            adapter.restart_required,
            _entry_digest(current) if current is not None else None,
            entry=entry,
            current_entry=current,
            migration_profile=profile,
        )

    existing_bytes = resolved_path.read_bytes() if resolved_path.exists() else None
    existing_text = (
        existing_bytes.decode("utf-8")
        if existing_bytes is not None
        else _default_document(adapter)
    )
    if resolved_path.exists() and not os.access(resolved_path, os.W_OK):
        raise ReadOnlyConfigError(f"{agent_id}: config is read-only: {resolved_path}")

    current = _read_rush_entry(existing_text, adapter)
    current = current if isinstance(current, dict) else None
    entry = _planned_entry(current, rush_binary, profile)
    unchanged = current is not None and same_server_entry(current, entry)
    if unchanged:
        new_text = existing_text
    elif adapter.config_format == "toml":
        new_text = _upsert_toml_table(
            existing_text, (*adapter.servers_key, "rush"), entry
        )
    else:
        new_text = _upsert_json_like(existing_text, adapter.servers_key, entry)

    backup_path = resolved_path.with_name(
        resolved_path.name + f".rush-backup-{int(time.time())}"
    )
    return RegistrationStep(
        agent_id,
        "config-edit",
        resolved_path,
        backup_path,
        None,
        new_text,
        adapter.restart_required,
        _sha256(existing_bytes) if existing_bytes is not None else None,
        entry=entry,
        current_entry=current,
        unchanged=unchanged,
        migration_profile=profile,
    )


def _planned_entry(
    current: dict[str, Any] | None, rush_binary: str, profile: str | None
) -> dict[str, Any]:
    """The `{command, args}` entry a registration writes (see `plan_agent_registration`)."""
    if current is None:
        if profile is None:
            return build_stdio_entry(rush_binary)
        return build_stdio_entry(
            rush_binary, args=tuple(profile_serve_args(LEGACY_SERVE_ARGS, profile))
        )
    if profile is not None:
        return build_stdio_entry(
            rush_binary, args=tuple(profile_serve_args(current.get("args"), profile))
        )
    args = current.get("args")
    if not isinstance(args, list) or not all(isinstance(arg, str) for arg in args):
        # ponytail: unusable args were always replaced by the full server's.
        args = list(LEGACY_SERVE_ARGS)
    return build_stdio_entry(rush_binary, args=tuple(args))


def registration_preview(step: RegistrationStep) -> dict[str, Any]:
    """What an `agent connect --profile` migration will change, shown before consent."""
    current = step.current_entry
    return {
        "agent_id": step.agent_id,
        "method": step.method,
        "config_path": str(step.config_path) if step.config_path else None,
        "current_profile": (
            classify_registration_profile(current) if current is not None else None
        ),
        "current_command": current.get("command") if current is not None else None,
        "current_args": current.get("args") if current is not None else None,
        "new_command": step.entry["command"] if step.entry else None,
        "new_args": step.entry["args"] if step.entry else None,
        "profile": step.migration_profile,
        "current_sha256": step.expected_sha256,
        "unchanged": step.unchanged,
    }


def _capture_native_entry(config_path: Path | None) -> dict[str, Any] | None:
    """The host's current `rush` entry, read before a native remove/add."""
    if config_path is None or not config_path.is_file():
        return None
    try:
        entry = _get_json_like_entry(
            config_path.read_text(encoding="utf-8"), ("mcpServers",)
        )
    except (OSError, ValueError, MalformedConfigError):
        return None
    return entry if isinstance(entry, dict) else None


def apply_agent_registration(step: RegistrationStep) -> AgentApplyResult:
    """Apply a previously built plan. Never raises -- failures come back as `ok=False`.

    Native replacement captures the existing `rush` entry first and restores
    it via `mcp add-json` when the new `mcp add` fails, so a prior working
    registration survives. Config-edit writes are compare-and-swap against
    the plan's recorded digest and preserve the file's mode.
    """
    if step.method == "native":
        assert step.native_command is not None
        remove_command = step.native_command[:2] + ("remove", "rush", "--scope", "user")
        captured = _capture_native_entry(step.config_path)
        if step.migration_profile is not None and step.expected_sha256 != (
            _entry_digest(captured) if captured is not None else None
        ):
            return AgentApplyResult(
                step.agent_id,
                False,
                step.method,
                step.config_path,
                None,
                step.restart_required,
                error=f"{step.config_path}: changed_since_preview",
                conflict=True,
            )
        try:
            subprocess.run(
                remove_command, capture_output=True, text=True, timeout=30, check=False
            )
            proc = subprocess.run(
                step.native_command,
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )
            if proc.returncode != 0 and captured is not None:
                restore_error = _restore_native_entry(step.native_command[:2], captured)
                if restore_error is not None:
                    return AgentApplyResult(
                        step.agent_id,
                        False,
                        step.method,
                        step.config_path,
                        None,
                        step.restart_required,
                        error=(
                            f"{proc.stderr.strip() or f'exit {proc.returncode}'}; "
                            f"recovery_required: {restore_error}"
                        ),
                        recovery_required=restore_error,
                    )
        except (OSError, subprocess.SubprocessError) as exc:
            return AgentApplyResult(
                step.agent_id,
                False,
                step.method,
                step.config_path,
                None,
                step.restart_required,
                error=str(exc),
            )
        ok = proc.returncode == 0
        error = None if ok else (proc.stderr.strip() or f"exit {proc.returncode}")
        return AgentApplyResult(
            step.agent_id,
            ok,
            step.method,
            step.config_path,
            None,
            step.restart_required,
            error=error,
        )

    assert step.config_path is not None and step.new_text is not None
    if step.unchanged:
        # T4: the entry already launches this binary; its bytes stay as they are.
        return AgentApplyResult(
            step.agent_id,
            True,
            step.method,
            step.config_path,
            None,
            step.restart_required,
        )
    try:
        step.config_path.parent.mkdir(parents=True, exist_ok=True)
        if step.config_path.exists() and step.backup_path is not None:
            shutil.copy2(step.config_path, step.backup_path)
        cas_replace_file(
            step.config_path,
            step.new_text.encode("utf-8"),
            expected_sha256=step.expected_sha256,
            new_file_mode=0o600,  # host configs can later hold credentials
        )
    except (OSError, AgentConnectionError) as exc:
        return AgentApplyResult(
            step.agent_id,
            False,
            step.method,
            step.config_path,
            step.backup_path,
            step.restart_required,
            error=str(exc),
            conflict=isinstance(exc, CASConflictError),
        )
    return AgentApplyResult(
        step.agent_id,
        True,
        step.method,
        step.config_path,
        step.backup_path,
        step.restart_required,
        error=None,
    )


def probe_agent_connection(
    agent_id: str,
    *,
    home: Path | None = None,
    os_name: str | None = None,
    rush_binary: str | None = None,
) -> AgentStatus:
    """Re-read an agent's config off disk and report its real current state."""
    adapter = ADAPTERS.get(agent_id)
    if adapter is None:
        raise UnknownAgentError(f"unknown agent: {agent_id!r}")
    return _discover_one(
        adapter,
        home=home or Path.home(),
        os_name=os_name or platform.system(),
        rush_binary=rush_binary,
    )


# --- Phase 63 memory activation: user/project/session/agent scope ------------------


def _readiness_transaction(
    *, project_root: Path | None, data_root: Path | None
) -> CASMapTransaction:
    root = (
        Path(project_root).resolve()
        if project_root
        else (data_root or default_data_root()) / "user"
    )
    store_file = root / ".rush" / "agent_memory.json"
    return CASMapTransaction(file_path=store_file, root_path=root)


def agent_memory_store_path(
    *, project_root: Path | None = None, data_root: Path | None = None
) -> Path:
    """The exact CAS-backed file a given (project|user) scope's memory lives at."""
    root = (
        Path(project_root).resolve()
        if project_root
        else (data_root or default_data_root()) / "user"
    )
    return root / ".rush" / "agent_memory.json"


def _entry_key(session_id: str, agent_id: str) -> str:
    return f"{session_id}::{agent_id}"


def initialize_agent_memory(
    agent_id: str,
    session_id: str,
    *,
    project_root: Path | None = None,
    data_root: Path | None = None,
    consent: bool = False,
) -> dict[str, Any]:
    """Create (or reset) the observation/readiness entry for one scope.

    Scope is (user-or-project, session_id, agent_id) -- project scope is the
    project's own root (a distinct CAS file per project, same isolation
    `preferences.json` already relies on); user scope is a single CAS file
    under the durable OS-user data root. `consent` gates whether
    `record_tool_observation` is later allowed to store anything.
    """
    tx = _readiness_transaction(project_root=project_root, data_root=data_root)
    key = _entry_key(session_id, agent_id)

    def mutator(current: dict[str, Any]) -> dict[str, Any]:
        entries = dict(current.get("entries") or {})
        entries[key] = {
            "agent_id": agent_id,
            "session_id": session_id,
            "scope": "project" if project_root is not None else "user",
            "consent": consent,
            "connected": False,
            "acknowledged_at": None,
            "last_observation": None,
            "updated_at": time.time(),
        }
        return {"schema_version": 1, "entries": entries}

    snapshot = tx.update(mutator)
    return snapshot.data["entries"][key]


def read_agent_memory_state(
    agent_id: str,
    session_id: str,
    *,
    project_root: Path | None = None,
    data_root: Path | None = None,
) -> dict[str, Any] | None:
    tx = _readiness_transaction(project_root=project_root, data_root=data_root)
    entries = tx.read(allow_missing=True).data.get("entries") or {}
    return entries.get(_entry_key(session_id, agent_id))


def read_agent_memory_state_strict(
    *, project_root: Path | None = None, data_root: Path | None = None
) -> dict[str, Any] | None:
    """T23 (X5): one scope's readiness `entries` read with a plain JSON load,
    never `CASMapTransaction` (whose constructor creates directories). `{}`
    when the file is absent; `None` when it is unreadable or not the CAS
    `{version, data: {entries}}` shape."""
    path = agent_memory_store_path(project_root=project_root, data_root=data_root)
    try:
        payload = json.loads(path.read_bytes())
    except FileNotFoundError:
        return {}
    except (OSError, ValueError):
        return None
    data = payload.get("data") if isinstance(payload, dict) else None
    entries = data.get("entries", {}) if isinstance(data, dict) else None
    return entries if isinstance(entries, dict) else None


def record_tool_observation(
    agent_id: str,
    session_id: str,
    observation: dict[str, Any],
    *,
    project_root: Path | None = None,
    data_root: Path | None = None,
) -> dict[str, Any]:
    """Persist one real tool-observation payload. Requires prior explicit consent."""
    tx = _readiness_transaction(project_root=project_root, data_root=data_root)
    key = _entry_key(session_id, agent_id)

    def mutator(current: dict[str, Any]) -> dict[str, Any]:
        entries = dict(current.get("entries") or {})
        entry = entries.get(key)
        if entry is None:
            raise AgentConnectionError(
                f"no memory scope initialized for {agent_id!r}/{session_id!r}"
            )
        if not entry.get("consent"):
            raise AgentConnectionError(
                f"consent required before capturing observation for {agent_id!r}"
            )
        entries[key] = {
            **entry,
            "last_observation": observation,
            "updated_at": time.time(),
        }
        return {"schema_version": 1, "entries": entries}

    snapshot = tx.update(mutator)
    return snapshot.data["entries"][key]


def acknowledge_agent_connection(
    agent_id: str,
    session_id: str,
    *,
    project_root: Path | None = None,
    data_root: Path | None = None,
) -> dict[str, Any]:
    """Flip an initialized scope to connected. This is the only path to `connected=True`."""
    tx = _readiness_transaction(project_root=project_root, data_root=data_root)
    key = _entry_key(session_id, agent_id)

    def mutator(current: dict[str, Any]) -> dict[str, Any]:
        entries = dict(current.get("entries") or {})
        entry = entries.get(key)
        if entry is None:
            raise AgentConnectionError(
                f"no memory scope initialized for {agent_id!r}/{session_id!r}"
            )
        entries[key] = {**entry, "connected": True, "acknowledged_at": time.time()}
        return {"schema_version": 1, "entries": entries}

    snapshot = tx.update(mutator)
    return snapshot.data["entries"][key]


def agent_readiness(
    *,
    home: Path | None = None,
    os_name: str | None = None,
    rush_binary: str | None = None,
) -> dict[str, Any]:
    """One callable readiness summary. P65-10 consumes this directly -- it never

    needs to touch CLI parsing to learn "is agent X installed/configured".
    """
    statuses = discover_agents(home=home, os_name=os_name, rush_binary=rush_binary)
    return {
        "agents": [status.to_dict() for status in statuses],
        "any_connected": any(status.status == "registered" for status in statuses),
    }


# --- Phase 70 T3: CAS writer, ownership ledger, instruction blocks, disconnect ----
#
# Every write to a user-owned file (project CLAUDE.md/AGENTS.md, host configs)
# goes through `cas_replace_file`: temp file in the same directory, the
# original mode copied onto it (new files 0644), fsync, then a digest
# re-check immediately before `os.replace`. The shared `atomic_write_bytes`
# is not used here because it leaves every replaced file at mode 0600 and
# rejects symlinked targets (design brief X10). The same primitive is the
# compare-and-swap T4's registration migration reuses.
#
# The ownership ledger `<data_root>/agents/owned.json` is a `CASMapTransaction`
# map whose `data` is keyed by entry id. Every read-modify-write of it, and every component
# write it records, happens under the O_EXCL lock `<data_root>/agents/
# agents.lock` (same pattern as the project registry lock).


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class CASConflictError(AgentConnectionError):
    """A compare-and-swap precondition failed; the target was not written."""

    def __init__(
        self,
        path: Path,
        expected: str | None,
        actual: str | None,
        reason: str = "changed_since_preview",
    ) -> None:
        super().__init__(f"{path}: {reason} (expected {expected}, actual {actual})")
        self.path = path
        self.expected = expected
        self.actual = actual
        self.reason = reason


class LedgerBusyError(AgentConnectionError):
    """Another Rush process holds the agents ownership-ledger lock."""


class LedgerCorruptError(AgentConnectionError):
    """The ownership ledger exists but is not a JSON object of entry objects."""


def _read_regular(path: Path) -> bytes | None:
    """Bytes of a regular file, None when absent. Never follows a final symlink."""
    try:
        fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    except FileNotFoundError:
        return None
    except OSError as exc:
        if exc.errno == errno.ELOOP:
            raise CASConflictError(path, None, None, reason="symlink") from exc
        raise
    with os.fdopen(fd, "rb") as handle:
        if not stat.S_ISREG(os.fstat(handle.fileno()).st_mode):
            raise CASConflictError(path, None, None, reason="not_a_regular_file")
        return handle.read()


def _digest_or_none(data: bytes | None) -> str | None:
    return None if data is None else _sha256(data)


def cas_replace_file(
    path: Path,
    data: bytes,
    *,
    expected_sha256: str | None,
    new_file_mode: int = 0o644,
) -> str:
    """Replace `path` with `data` only while its digest still equals `expected_sha256`.

    `expected_sha256=None` means the file must still be absent. The existing
    file's permission bits are preserved; a new file gets `new_file_mode`.
    Returns the written digest. Raises `CASConflictError` without writing.
    """
    try:
        mode = stat.S_IMODE(os.lstat(path).st_mode)
    except FileNotFoundError:
        mode = new_file_mode
    fd, tmp_name = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.rush-")
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(tmp_path, mode)
        actual = _digest_or_none(_read_regular(path))
        if actual != expected_sha256:
            raise CASConflictError(path, expected_sha256, actual)
        os.replace(tmp_path, path)
    except BaseException:
        tmp_path.unlink(missing_ok=True)
        raise
    return _sha256(data)


def cas_unlink(path: Path, *, expected_sha256: str) -> None:
    """Delete `path` only while its digest still equals `expected_sha256`."""
    actual = _digest_or_none(_read_regular(path))
    if actual != expected_sha256:
        raise CASConflictError(path, expected_sha256, actual)
    path.unlink()


def owned_path_digest(path: Path) -> str | None:
    """Digest of a Rush-owned file or directory tree; None when absent.

    A directory digest covers every entry's relative path plus its file
    digest (or symlink target), so any added, removed or changed entry
    changes it. A top-level symlink is never treated as owned content.
    """
    try:
        st = os.lstat(path)
    except FileNotFoundError:
        return None
    if stat.S_ISREG(st.st_mode):
        return _digest_or_none(_read_regular(path))
    if not stat.S_ISDIR(st.st_mode):
        raise CASConflictError(path, None, None, reason="not_a_regular_file")
    tree = hashlib.sha256()
    for dirpath, dirnames, filenames in os.walk(path):
        dirnames.sort()
        base = Path(dirpath)
        for name in sorted(dirnames + filenames):
            child = base / name
            rel = child.relative_to(path).as_posix()
            if child.is_symlink():
                tree.update(f"{rel}\0symlink:{os.readlink(child)}\n".encode())
            elif child.is_dir():
                tree.update(f"{rel}/\n".encode())
            else:
                tree.update(
                    f"{rel}\0{_digest_or_none(_read_regular(child))}\n".encode()
                )
    return tree.hexdigest()


class WriteJournal:
    """In-memory record of one transaction's own writes, undone in reverse on failure.

    An undo restores captured original bytes only while the component's
    current digest still equals the digest this transaction wrote; a
    concurrently changed component is left as is and reported as
    `recovery_required{component, path, expected, actual}`.
    """

    def __init__(self) -> None:
        self._undo: list[Callable[[], dict[str, Any] | None]] = []

    def record_file(
        self, component: str, path: Path, original: bytes | None, written_sha256: str
    ) -> None:
        def undo() -> dict[str, Any] | None:
            try:
                if original is None:
                    cas_unlink(path, expected_sha256=written_sha256)
                else:
                    cas_replace_file(path, original, expected_sha256=written_sha256)
            except CASConflictError as exc:
                return {
                    "component": component,
                    "path": str(path),
                    "expected": written_sha256,
                    "actual": exc.actual,
                }
            except OSError as exc:
                return {
                    "component": component,
                    "path": str(path),
                    "expected": written_sha256,
                    "actual": None,
                    "error": str(exc),
                }
            return None

        self._undo.append(undo)

    def record_undo(self, undo: Callable[[], dict[str, Any] | None]) -> None:
        self._undo.append(undo)

    def rollback(self) -> list[dict[str, Any]]:
        recovery: list[dict[str, Any]] = []
        while self._undo:
            outcome = self._undo.pop()()
            if outcome is not None:
                recovery.append(outcome)
        return recovery


def _entry_digest(entry: Any) -> str:
    return _sha256(
        json.dumps(entry, sort_keys=True, separators=(",", ":")).encode("utf-8")
    )


def read_registration_entry(
    agent_id: str, *, home: Path | None = None, os_name: str | None = None
) -> tuple[Path, dict[str, Any] | None]:
    """The adapter config path registration targets and its current `rush` entry."""
    adapter = ADAPTERS.get(agent_id)
    if adapter is None:
        raise UnknownAgentError(f"unknown agent: {agent_id!r}")
    candidates = adapter.config_paths(os_name or platform.system(), home or Path.home())
    config_path = next((p for p in candidates if p.exists()), candidates[0])
    raw = _read_regular(config_path)
    if raw is None:
        return config_path, None
    entry = _read_rush_entry(raw.decode("utf-8"), adapter)
    return config_path, entry if isinstance(entry, dict) else None


def registration_undo(
    step: RegistrationStep,
    *,
    original_bytes: bytes | None,
    captured_entry: dict[str, Any] | None,
) -> Callable[[], dict[str, Any] | None]:
    """Undo for a successful `apply_agent_registration(step)` inside a transaction."""
    if step.method == "config-edit":
        assert step.config_path is not None and step.new_text is not None
        journal = WriteJournal()
        journal.record_file(
            "mcp_entry",
            step.config_path,
            original_bytes,
            _sha256(step.new_text.encode("utf-8")),
        )

        def undo_edit() -> dict[str, Any] | None:
            recovery = journal.rollback()
            return recovery[0] if recovery else None

        return undo_edit

    assert step.native_command is not None
    prefix = step.native_command[:2]
    written = _capture_native_entry(step.config_path)

    def undo_native() -> dict[str, Any] | None:
        current = _capture_native_entry(step.config_path)
        if written is None or current is None or current != written:
            return {
                "component": "mcp_entry",
                "path": str(step.config_path),
                "expected": _entry_digest(written) if written is not None else None,
                "actual": _entry_digest(current) if current is not None else None,
            }
        try:
            subprocess.run(
                (*prefix, "remove", "rush", "--scope", "user"),
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            return {
                "component": "mcp_entry",
                "path": str(step.config_path),
                "expected": _entry_digest(written),
                "actual": _entry_digest(current),
                "error": str(exc),
            }
        if captured_entry is None:
            return None
        error = _restore_native_entry(prefix, captured_entry)
        if error is None:
            return None
        return {
            "component": "mcp_entry",
            "path": str(step.config_path),
            "expected": _entry_digest(captured_entry),
            "actual": None,
            "error": error,
        }

    return undo_native


def _restore_native_entry(
    prefix: tuple[str, ...], captured: dict[str, Any]
) -> str | None:
    """Re-add a captured native `rush` entry; an error string when that fails too."""
    captured_json = json.dumps(captured)
    try:
        proc = subprocess.run(
            (*prefix, "add-json", "rush", captured_json, "--scope", "user"),
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return f"{exc}; captured entry: {captured_json}"
    if proc.returncode != 0:
        return (
            f"{proc.stderr.strip() or f'exit {proc.returncode}'}; "
            f"captured entry: {captured_json}"
        )
    return None


# --- Ownership ledger ------------------------------------------------------------

LedgerKind = Literal[
    "mcp_entry",
    "instruction_block",
    "file_resource",
    "native_plugin",
    "hook_activation",
]
_FILE_KINDS = frozenset({"file_resource", "native_plugin", "hook_activation"})
_LEDGER_LOCK_TIMEOUT = 10.0
_LEDGER_LOCK_STALE_SECONDS = 60.0
_LEDGER_LOCK_POLL_SECONDS = 0.02


def ownership_ledger_path(data_root: Path | None = None) -> Path:
    return (data_root or default_data_root()) / "agents" / "owned.json"


@contextmanager
def _ledger_lock(data_root: Path) -> Iterator[None]:
    """Mutual exclusion over the ledger and the writes it records (O_EXCL lock file)."""
    agents_dir = data_root / "agents"
    agents_dir.mkdir(parents=True, exist_ok=True)
    lock_path = agents_dir / "agents.lock"
    start = time.monotonic()
    fd: int | None = None
    while fd is None:
        try:
            fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError:
            with suppress(OSError):
                if time.time() - lock_path.stat().st_mtime > _LEDGER_LOCK_STALE_SECONDS:
                    lock_path.unlink(missing_ok=True)
                    continue
            if time.monotonic() - start >= _LEDGER_LOCK_TIMEOUT:
                raise LedgerBusyError(
                    f"timed out after {_LEDGER_LOCK_TIMEOUT}s waiting for {lock_path}"
                ) from None
            time.sleep(_LEDGER_LOCK_POLL_SECONDS)
    try:
        yield
    finally:
        os.close(fd)
        with suppress(OSError):
            lock_path.unlink()


def _ledger_transaction(data_root: Path) -> CASMapTransaction:
    """The ledger's CAS map: `{schema_version, version, data: {entry_id: row}}`.

    Only built on the write path (the caller already holds the ledger lock,
    which created `<data_root>/agents`), because construction creates the
    root directory (design brief X5).
    """
    return CASMapTransaction(
        file_path=ownership_ledger_path(data_root), root_path=data_root / "agents"
    )


def _load_ledger(data_root: Path) -> tuple[dict[str, dict[str, Any]], int]:
    """Entries keyed by id, plus the CAS version the later save must match."""
    try:
        snapshot = _ledger_transaction(data_root).read(allow_missing=True)
    except StoreError as exc:
        raise LedgerCorruptError(f"ownership ledger is unreadable: {exc}") from exc
    entries = snapshot.data
    if not all(isinstance(value, dict) for value in entries.values()):
        raise LedgerCorruptError(
            f"ownership ledger data is not an object of entries: "
            f"{ownership_ledger_path(data_root)}"
        )
    return entries, snapshot.version


def _save_ledger(
    data_root: Path, entries: dict[str, dict[str, Any]], expected_version: int
) -> None:
    try:
        _ledger_transaction(data_root).write(entries, expected_version)
    except StoreError as exc:
        raise AgentConnectionError(f"ownership ledger write failed: {exc}") from exc


def _ledger_entry(
    entry_id: str,
    kind: LedgerKind,
    host: str,
    project_root: Path | None,
    path: str,
    written_sha256: str,
    original_sha256: str | None,
) -> dict[str, Any]:
    from rush import __version__

    return {
        "id": entry_id,
        "kind": kind,
        "host": host,
        "project_root": str(project_root) if project_root is not None else None,
        "path": path,
        "written_sha256": written_sha256,
        "original_sha256": original_sha256,
        "rush_version": __version__,
        "created_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }


def _same_project(entry: dict[str, Any], project_root: Path | None) -> bool:
    recorded = entry.get("project_root")
    if project_root is None:
        return recorded is None
    return isinstance(recorded, str) and Path(recorded).resolve() == project_root


def _entry_physical_path(entry: dict[str, Any]) -> Path:
    """Where a ledger entry's component lives.

    Absolute paths are host-global components (MCP config, shared package).
    A relative path is project-relative and must stay inside that root.
    """
    raw = entry.get("path")
    if not isinstance(raw, str) or not raw:
        raise ValueError("ledger entry has no path")
    path = Path(raw)
    if path.is_absolute():
        return path
    recorded_root = entry.get("project_root")
    if not isinstance(recorded_root, str) or not recorded_root:
        raise ValueError(f"relative ledger path without a project root: {raw}")
    root = Path(recorded_root).resolve()
    candidate = root / path
    parent = candidate.parent.resolve()
    if not parent.is_relative_to(root):
        raise ValueError(f"ledger path escapes its project root: {raw}")
    return parent / candidate.name


def _record_registration_locked(
    agent_id: str,
    root: Path | None,
    ledger: dict[str, dict[str, Any]],
    *,
    home: Path | None,
    os_name: str | None,
    original_entry: dict[str, Any] | None,
) -> dict[str, Any] | None:
    """Add the MCP-entry row Rush just wrote to an in-memory ledger.

    One row per project (or user scope) that connected this host, all over
    the same physical entry, so disconnect removes the entry only when no
    other row still references it. The caller holds the ledger lock.
    """
    if agent_id not in ADAPTERS:
        return None
    config_path, entry = read_registration_entry(agent_id, home=home, os_name=os_name)
    if entry is None:
        return None
    written = _entry_digest(entry)
    entry_id = f"{agent_id}:mcp_entry:{config_path}:{root if root else 'user'}"
    siblings = [
        row
        for row in ledger.values()
        if row.get("kind") == "mcp_entry"
        and row.get("host") == agent_id
        and row.get("path") == str(config_path)
    ]
    original = (
        siblings[0].get("original_sha256")
        if siblings
        else (_entry_digest(original_entry) if original_entry is not None else None)
    )
    for sibling in siblings:
        sibling["written_sha256"] = written
    row = _ledger_entry(
        entry_id, "mcp_entry", agent_id, root, str(config_path), written, original
    )
    ledger[entry_id] = row
    return row


# --- Project instruction blocks -----------------------------------------------------

INSTRUCTION_TARGETS: dict[str, str] = {"claude-code": "CLAUDE.md", "codex": "AGENTS.md"}
# ponytail: kept short so the whole interactive preview (path, diff, prompt)
INSTRUCTION_BODY: tuple[str, ...] = (
    "## Rush",
    "",
    (
        "This project is connected to Rush, a local code-quality toolbelt, "
        "through the `rush` MCP server."
    ),
    "",
    (
        "- Check code you change with Rush tools such as `rush_lint`, "
        "`rush_test`, `rush_security` and `rush_review`."
    ),
    (
        "- Each tool returns `{status, findings, summary}`. `status: skipped` "
        "means no work was performed (the engine is missing, there were no "
        "supported targets, or a permission was denied), not that the code passed."
    ),
    (
        "- Rush manages this block. Remove it with "
        "`rush agent disconnect <agent> --project <path>` instead of editing it."
    ),
)
_BEGIN_TOKEN = "<!-- rush:begin"
_END_TOKEN = "<!-- rush:end"
_END_LINE = "<!-- rush:end -->"
_BEGIN_RE = re.compile(
    r"<!-- rush:begin v=1 hosts=([a-z0-9-]+(?:,[a-z0-9-]+)*) sha256=([0-9a-f]+) -->"
)
_BOM = b"\xef\xbb\xbf"
_LINE_RE = re.compile(r"[^\n]*\n|[^\n]+")


class _MarkerConflict(Exception):
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


@dataclass(frozen=True)
class _Line:
    start: int
    end: int
    content: str


@dataclass(frozen=True)
class _Block:
    begin: _Line
    end: _Line
    hosts: tuple[str, ...]
    marker_digest: str
    body_digest: str


@dataclass(frozen=True)
class _Document:
    bom: bool
    text: str
    newline: str
    lines: tuple[_Line, ...]

    def encode(self, text: str) -> bytes:
        return (_BOM if self.bom else b"") + text.encode("utf-8")


def _decode_document(raw: bytes | None) -> _Document:
    """Split without normalizing: every unrelated byte is copied through by offset."""
    data = raw or b""
    bom = data.startswith(_BOM)
    text = (data[len(_BOM) :] if bom else data).decode("utf-8")
    lines: list[_Line] = []
    for match in _LINE_RE.finditer(text):
        content = match.group()
        content = content.removesuffix("\n").removesuffix("\r")
        lines.append(_Line(match.start(), match.end(), content))
    newline = "\r\n" if "\r\n" in text else "\n"
    return _Document(bom, text, newline, tuple(lines))


def _body_digest(lines: Any) -> str:
    return _sha256("".join(f"{line}\n" for line in lines).encode("utf-8"))


def _parse_block(doc: _Document) -> _Block | None:
    """Zero or one well-formed begin/end pair, in order; anything else conflicts."""
    begins = sum(line.content.count(_BEGIN_TOKEN) for line in doc.lines)
    ends = sum(line.content.count(_END_TOKEN) for line in doc.lines)
    if begins == 0 and ends == 0:
        return None
    if begins != 1 or ends != 1:
        raise _MarkerConflict("corrupt_markers")
    begin_idx = next(
        (i for i, line in enumerate(doc.lines) if _BEGIN_RE.fullmatch(line.content)),
        None,
    )
    end_idx = next(
        (i for i, line in enumerate(doc.lines) if line.content == _END_LINE), None
    )
    if begin_idx is None or end_idx is None or end_idx <= begin_idx:
        raise _MarkerConflict("corrupt_markers")
    match = _BEGIN_RE.fullmatch(doc.lines[begin_idx].content)
    assert match is not None
    return _Block(
        doc.lines[begin_idx],
        doc.lines[end_idx],
        tuple(match.group(1).split(",")),
        match.group(2),
        _body_digest(line.content for line in doc.lines[begin_idx + 1 : end_idx]),
    )


def _begin_line(hosts: tuple[str, ...], body_digest: str) -> str:
    return f"{_BEGIN_TOKEN} v=1 hosts={','.join(hosts)} sha256={body_digest} -->"


def _render_block(hosts: tuple[str, ...], newline: str) -> str:
    lines = [_begin_line(hosts, _body_digest(INSTRUCTION_BODY)), *INSTRUCTION_BODY]
    return newline.join([*lines, _END_LINE]) + newline


def _append_block(text: str, block: str, newline: str) -> str:
    """Block at end of file, separated from existing content by one blank line."""
    if not text:
        return block
    prefix = text if text.endswith("\n") else text + newline
    if not prefix.endswith(("\n\n", "\n\r\n")):
        prefix += newline
    return prefix + block


def _without_block(doc: _Document, block: _Block, original_sha256: str | None) -> str:
    """Text with the block and its blank separator removed.

    When the rest of the file is untouched this reproduces the pre-Rush
    bytes exactly (checked against the recorded original digest).
    """
    before, after = doc.text[: block.begin.start], doc.text[block.end.end :]
    stripped = before
    if before.endswith(("\r\n\r\n", "\n\r\n")):
        stripped = before[:-2]
    elif before.endswith("\n\n"):
        stripped = before[:-1]
    candidates = [stripped + after, before + after]
    if not after and stripped.endswith(doc.newline):
        candidates.append(stripped[: -len(doc.newline)])
    if original_sha256 is not None:
        for candidate in candidates:
            if _sha256(doc.encode(candidate)) == original_sha256:
                return candidate
    return candidates[0]


@dataclass(frozen=True)
class AgentInstructionPlan:
    """Preview of one host's Rush instruction block in its project instruction file."""

    agent_id: str
    target_path: Path
    diff: str
    hosts: tuple[str, ...]
    existing_sha256: str | None
    conflict: str | None
    project_root: Path
    data_root: Path
    relative_path: str
    new_bytes: bytes | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "agent_id": self.agent_id,
            "target_path": str(self.target_path),
            "diff": self.diff,
            "hosts": list(self.hosts),
            "existing_sha256": self.existing_sha256,
            "conflict": self.conflict,
            "changed": self.new_bytes is not None,
        }


@dataclass(frozen=True)
class AgentInstructionApplyResult:
    status: Literal["applied", "unchanged", "declined", "conflict"]
    target_path: Path
    conflict: str | None = None
    recovery: tuple[dict[str, Any], ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "target_path": str(self.target_path),
            "conflict": self.conflict,
            "recovery": list(self.recovery),
        }


@overload
def plan_agent_instructions(
    agent_id: str,
    *,
    project_root: Path,
    data_root: Path | None = None,
    rush_binary: None = None,
) -> AgentInstructionPlan: ...


@overload
def plan_agent_instructions(
    agent_id: str,
    *,
    project_root: Path,
    data_root: Path | None = None,
    rush_binary: str,
    home: Path | None = None,
    project_id: str | None = None,
    session_id: str | None = None,
    which: Callable[[str], str | None] = shutil.which,
) -> RegistrationStep: ...


def plan_agent_instructions(
    agent_id: str,
    *,
    project_root: Path,
    data_root: Path | None = None,
    rush_binary: str | None = None,
    home: Path | None = None,
    project_id: str | None = None,
    session_id: str | None = None,
    which: Callable[[str], str | None] = shutil.which,
) -> AgentInstructionPlan | RegistrationStep:
    """Plan the Rush instruction block for `agent_id` in `project_root`. Never writes.

    Claude Code uses `CLAUDE.md`, Codex `AGENTS.md`. A symlinked instruction
    file is followed only to a regular file inside the canonical project
    root; the block then lives in that physical file, shared by every host
    whose file resolves there (`hosts=` is the union).

    With `rush_binary` (Phase 70 T26) this plans the host's project-bound
    MCP registration instead -- the server entry that launches `rush_binary`
    bound to this project and session (`plan_project_registration`).
    """
    if rush_binary is not None:
        return plan_project_registration(
            agent_id,
            rush_binary=rush_binary,
            project_root=project_root,
            project_id=project_id,
            session_id=session_id,
            home=home,
            which=which,
        )
    name = INSTRUCTION_TARGETS.get(agent_id)
    if name is None:
        raise UnknownAgentError(
            f"no project instruction file is defined for agent {agent_id!r}"
        )
    root = Path(project_root).resolve()
    resolved_data_root = data_root or default_data_root()
    link = root / name

    def conflict(
        target: Path, reason: str, digest: str | None = None
    ) -> AgentInstructionPlan:
        return AgentInstructionPlan(
            agent_id,
            target,
            "",
            (agent_id,),
            digest,
            reason,
            root,
            resolved_data_root,
            name,
        )

    if not root.is_dir():
        return conflict(link, "project_root_missing")
    target = link
    if link.is_symlink():
        target = link.resolve()
        if target == root or not target.is_relative_to(root):
            return conflict(link, "symlink_outside_root")
        if not target.exists():
            return conflict(link, "dangling_symlink")
    try:
        raw = _read_regular(target)
    except CASConflictError as exc:
        return conflict(target, exc.reason)
    digest = _digest_or_none(raw)
    try:
        doc = _decode_document(raw)
    except UnicodeDecodeError:
        return conflict(target, "not_utf8", digest)
    try:
        block = _parse_block(doc)
    except _MarkerConflict as exc:
        return conflict(target, exc.reason, digest)

    if block is None:
        hosts: tuple[str, ...] = (agent_id,)
        new_text = _append_block(
            doc.text, _render_block(hosts, doc.newline), doc.newline
        )
    else:
        if block.body_digest != block.marker_digest:
            return conflict(target, "user_edited_block", digest)
        hosts = tuple(sorted({*block.hosts, agent_id}))
        new_text = (
            doc.text[: block.begin.start]
            + _render_block(hosts, doc.newline)
            + doc.text[block.end.end :]
        )

    relative = target.relative_to(root).as_posix()
    if new_text == doc.text:
        return AgentInstructionPlan(
            agent_id,
            target,
            "",
            hosts,
            digest,
            None,
            root,
            resolved_data_root,
            relative,
        )
    diff = "".join(
        difflib.unified_diff(
            doc.text.splitlines(keepends=True),
            new_text.splitlines(keepends=True),
            fromfile=str(target),
            tofile=str(target),
            n=0,
        )
    )
    return AgentInstructionPlan(
        agent_id,
        target,
        diff,
        hosts,
        digest,
        None,
        root,
        resolved_data_root,
        relative,
        doc.encode(new_text),
    )


@overload
def apply_agent_instructions(
    plan: AgentInstructionPlan, *, consent: bool
) -> AgentInstructionApplyResult: ...


@overload
def apply_agent_instructions(
    plan: RegistrationStep,
    *,
    consent: bool | None = None,
    data_root: Path | None = None,
    project_root: Path | None = None,
    runner: HostRunner | None = None,
    writer: Callable[..., Any] | None = None,
) -> AgentApplyResult: ...


def apply_agent_instructions(
    plan: AgentInstructionPlan | RegistrationStep,
    *,
    consent: bool | None = None,
    data_root: Path | None = None,
    project_root: Path | None = None,
    runner: HostRunner | None = None,
    writer: Callable[..., Any] | None = None,
) -> AgentInstructionApplyResult | AgentApplyResult:
    """Apply a previewed block only with consent and only if the file is unchanged.

    The whole-file digest recorded at preview is re-checked immediately
    before `os.replace`; any difference is a conflict with no write.

    A project-bound registration step (T26) goes to
    `apply_project_registration`; `project_root`, when given, must be the
    root the step was planned for.
    """
    if isinstance(plan, RegistrationStep):
        if (
            project_root is not None
            and plan.project_root != Path(project_root).resolve()
        ):
            return _registration_result(plan, False, "project_root_mismatch")
        return apply_project_registration(
            plan,
            consent=consent,
            data_root=data_root,
            runner=runner,
            writer=writer,
        )
    target = plan.target_path
    if plan.conflict is not None:
        return AgentInstructionApplyResult("conflict", target, plan.conflict)
    if not consent:
        return AgentInstructionApplyResult("declined", target)
    try:
        with _ledger_lock(plan.data_root):
            ledger, ledger_digest = _load_ledger(plan.data_root)
            before = json.dumps(ledger, sort_keys=True)
            journal = WriteJournal()
            result = _apply_instructions_locked(plan, ledger, journal)
            if json.dumps(ledger, sort_keys=True) != before:
                try:
                    _save_ledger(plan.data_root, ledger, ledger_digest)
                except (OSError, AgentConnectionError):
                    recovery = journal.rollback()
                    if recovery:
                        return AgentInstructionApplyResult(
                            "conflict", target, "recovery_required", tuple(recovery)
                        )
                    raise
    except LedgerBusyError:
        return AgentInstructionApplyResult("conflict", target, "ledger_busy")
    return result


def _apply_instructions_locked(
    plan: AgentInstructionPlan,
    ledger: dict[str, dict[str, Any]],
    journal: WriteJournal,
) -> AgentInstructionApplyResult:
    """Write a consented plan and add its row to an in-memory ledger.

    The caller holds the ledger lock and saves the ledger. A digest mismatch
    is a `conflict` result with no write; an I/O failure propagates so the
    caller's transaction can roll back.
    """
    target = plan.target_path
    entry_id = f"{plan.agent_id}:instruction_block:{target}"
    siblings = [
        row
        for eid, row in ledger.items()
        if eid != entry_id
        and row.get("kind") == "instruction_block"
        and _same_project(row, plan.project_root)
        and row.get("path") == plan.relative_path
    ]
    try:
        current = _read_regular(target)
    except CASConflictError as exc:
        return AgentInstructionApplyResult("conflict", target, exc.reason)
    if _digest_or_none(current) != plan.existing_sha256:
        return AgentInstructionApplyResult("conflict", target, "changed_since_preview")
    if plan.new_bytes is None:
        if entry_id not in ledger and current is not None:
            ledger[entry_id] = _ledger_entry(
                entry_id,
                "instruction_block",
                plan.agent_id,
                plan.project_root,
                plan.relative_path,
                _sha256(current),
                siblings[0].get("original_sha256") if siblings else None,
            )
        return AgentInstructionApplyResult("unchanged", target)

    original = (
        siblings[0].get("original_sha256")
        if siblings
        else ledger.get(entry_id, {}).get("original_sha256", plan.existing_sha256)
    )
    try:
        written = cas_replace_file(
            target, plan.new_bytes, expected_sha256=plan.existing_sha256
        )
    except CASConflictError as exc:
        return AgentInstructionApplyResult("conflict", target, exc.reason)
    journal.record_file("instruction_block", target, current, written)
    for row in siblings:
        row["written_sha256"] = written
    ledger[entry_id] = _ledger_entry(
        entry_id,
        "instruction_block",
        plan.agent_id,
        plan.project_root,
        plan.relative_path,
        written,
        original,
    )
    return AgentInstructionApplyResult("applied", target)


GuidanceConsent = bool | Callable[[AgentInstructionPlan], bool]
# T4: consent to a previewed profile migration (the preview dict is passed).
ProfileConsent = bool | Callable[[dict[str, Any]], bool]


def reconcile_agent_instructions(
    agent_id: str,
    *,
    project_root: Path | None,
    data_root: Path | None = None,
    consent: GuidanceConsent = False,
) -> dict[str, Any]:
    """Preview and (only with consent) apply one host's instruction block.

    `consent` is either an explicit grant (`True` applies, `False` leaves the
    block `pending`) or an interactive prompt that sees the preview first
    (a refusal is `declined`). Nothing is asked when there is nothing to
    change or the plan already conflicts.
    """
    plan, report = _preview_guidance(
        agent_id, project_root=project_root, data_root=data_root, consent=consent
    )
    if plan is None:
        return report
    result = apply_agent_instructions(plan, consent=True)
    return {
        **report,
        "state": result.status,
        "conflict": result.conflict,
        "recovery": list(result.recovery),
    }


def _preview_guidance(
    agent_id: str,
    *,
    project_root: Path | None,
    data_root: Path | None,
    consent: GuidanceConsent,
) -> tuple[AgentInstructionPlan | None, dict[str, Any]]:
    """The preview report, plus the plan only when it should now be applied."""
    base: dict[str, Any] = {
        "target_path": None,
        "diff": "",
        "hosts": [],
        "conflict": None,
        "recovery": [],
    }
    if agent_id not in INSTRUCTION_TARGETS:
        return None, {**base, "state": "unsupported"}
    if project_root is None:
        return None, {**base, "state": "pending", "reason": "project_required"}
    plan = plan_agent_instructions(
        agent_id, project_root=project_root, data_root=data_root
    )
    report = {**base, **plan.to_dict()}
    report.pop("agent_id", None)
    if plan.conflict is not None:
        return None, {**report, "state": "conflict"}
    if plan.new_bytes is None:
        return None, {**report, "state": "unchanged"}
    if callable(consent):
        granted, refused = consent(plan), "declined"
    else:
        granted, refused = consent, "pending"
    if not granted:
        return None, {**report, "state": refused}
    return plan, {**report, "state": "pending"}


# --- Owned resources and the connect transaction ------------------------------------


@dataclass(frozen=True)
class OwnedResource:
    """A Rush-owned file (skill, hook script, plugin file) a connection writes.

    `path` is project-relative, or absolute for a host-global resource.
    """

    kind: Literal["file_resource", "native_plugin", "hook_activation"]
    path: str
    content: bytes


class AgentTransactionError(AgentConnectionError):
    """A connect step failed; earlier writes were undone where still Rush's own."""

    def __init__(self, message: str, recovery: list[dict[str, Any]]) -> None:
        super().__init__(message)
        self.recovery = recovery


def _physical_or_none(row: dict[str, Any]) -> Path | None:
    try:
        return _entry_physical_path(row)
    except ValueError:
        return None


def _apply_resource_locked(
    agent_id: str,
    resource: OwnedResource,
    root: Path | None,
    ledger: dict[str, dict[str, Any]],
    journal: WriteJournal,
) -> dict[str, Any]:
    """Write one owned resource and add its ledger row (caller holds the lock).

    An existing file is replaced only when it is byte-identical to a digest
    Rush recorded for it; anything else is a `not_owned` conflict, untouched.
    """
    if not Path(resource.path).is_absolute() and root is None:
        raise ValueError(f"project-relative resource needs a project: {resource.path}")
    target = _entry_physical_path(
        {"path": resource.path, "project_root": str(root) if root else None}
    )
    report: dict[str, Any] = {"kind": resource.kind, "path": resource.path}
    missing: list[Path] = []
    parent = target.parent
    while not parent.exists():
        missing.append(parent)
        parent = parent.parent
    for directory in reversed(missing):
        directory.mkdir()
    if missing:

        def remove_created_dirs() -> dict[str, Any] | None:
            for directory in missing:  # deepest first
                with suppress(OSError):
                    directory.rmdir()
            return None

        journal.record_undo(remove_created_dirs)

    try:
        current = _read_regular(target)
    except CASConflictError as exc:
        return {**report, "state": "conflict", "conflict": exc.reason}
    current_digest = _digest_or_none(current)
    new_digest = _sha256(resource.content)
    siblings = [
        row
        for row in ledger.values()
        if row.get("kind") == resource.kind and _physical_or_none(row) == target
    ]
    owned = {row.get("written_sha256") for row in siblings}
    if (
        current is not None
        and current_digest != new_digest
        and current_digest not in owned
    ):
        return {
            **report,
            "state": "conflict",
            "conflict": "not_owned",
            "actual": current_digest,
        }
    state = "unchanged"
    if current_digest != new_digest:
        try:
            cas_replace_file(target, resource.content, expected_sha256=current_digest)
        except CASConflictError as exc:
            return {
                **report,
                "state": "conflict",
                "conflict": exc.reason,
                "actual": exc.actual,
            }
        journal.record_file(resource.kind, target, current, new_digest)
        state = "applied"
    for row in siblings:
        row["written_sha256"] = new_digest
    entry_id = f"{agent_id}:{resource.kind}:{target}:{root if root else 'user'}"
    ledger[entry_id] = _ledger_entry(
        entry_id,
        resource.kind,
        agent_id,
        root,
        resource.path,
        new_digest,
        siblings[0].get("original_sha256") if siblings else None,
    )
    return {**report, "state": state}


def connect_agent(
    agent_id: str,
    *,
    session_id: str,
    rush_binary: str | None,
    consent: bool = False,
    acknowledge: bool = False,
    guidance_consent: GuidanceConsent = False,
    project_root: Path | None = None,
    home: Path | None = None,
    data_root: Path | None = None,
    resources: Sequence[OwnedResource] = (),
    profile: str | None = None,
    profile_consent: ProfileConsent = False,
) -> dict[str, Any]:
    """Registration, memory, instruction block and resources as one transaction.

    Phase 70 T4: with `profile`, this is an explicit migration of the host's
    `rush` entry to that server profile. Its preview (config path, current
    and new args, current digest) is built first and passed to
    `profile_consent` (or `profile_consent` is the answer itself); without
    consent nothing at all is written and `{"migration": preview}` returns
    with state `pending`/`declined`. The write re-checks the previewed digest.

    The guidance preview and any consent prompt happen first, before the
    ledger lock is taken or anything is written. Then, under the lock, every
    component write is journaled and the ledger is saved once at the end. A
    failure at any step undoes the earlier writes in reverse -- restoring
    the captured original bytes (or the prior native registration) only
    while the component is still exactly what this transaction wrote -- and
    leaves the ledger untouched. A component changed concurrently is kept
    and reported in `AgentTransactionError.recovery` as
    `{component, path, expected, actual}`.

    The host and project checks run before the binary is resolved, so their
    outcome never depends on where rush itself is installed.
    """
    _resolve_adapter(agent_id, config_path=None, config_format=None, servers_key=None)
    if project_root is not None and not Path(project_root).is_dir():
        raise AgentConnectionError(f"project root not found: {project_root}")
    binary = resolve_rush_binary(rush_binary)
    step = plan_agent_registration(
        agent_id, rush_binary=binary, home=home, profile=profile
    )
    migration, refused = _migration_consent(step, profile_consent)
    if refused is not None:
        return {"migration": {**(migration or {}), "state": refused}}
    prior_entry: dict[str, Any] | None = None
    if agent_id in ADAPTERS:
        try:
            _, prior_entry = read_registration_entry(agent_id, home=home)
        except (AgentConnectionError, ValueError, OSError):
            prior_entry = None  # unreadable config: nothing to capture
    original_bytes: bytes | None = None
    if step.method == "config-edit" and step.config_path is not None:
        with suppress(CASConflictError):
            original_bytes = _read_regular(step.config_path)

    root = Path(project_root).resolve() if project_root is not None else None
    resolved_data_root = data_root or default_data_root()
    guidance_plan, guidance = _preview_guidance(
        agent_id,
        project_root=project_root,
        data_root=resolved_data_root,
        consent=guidance_consent,
    )

    journal = WriteJournal()
    with _ledger_lock(resolved_data_root):
        ledger, ledger_digest = _load_ledger(resolved_data_root)
        before = json.dumps(ledger, sort_keys=True)
        try:
            applied = apply_agent_registration(step)
            if applied.ok:
                journal.record_undo(
                    registration_undo(
                        step, original_bytes=original_bytes, captured_entry=prior_entry
                    )
                )
            memory_entry = initialize_agent_memory(
                agent_id,
                session_id,
                project_root=project_root,
                data_root=data_root,
                consent=consent,
            )
            if applied.ok and acknowledge:
                memory_entry = acknowledge_agent_connection(
                    agent_id, session_id, project_root=project_root, data_root=data_root
                )
            if applied.ok:
                _record_registration_locked(
                    agent_id,
                    root,
                    ledger,
                    home=home,
                    os_name=None,
                    original_entry=prior_entry,
                )
            if guidance_plan is not None:
                result = _apply_instructions_locked(guidance_plan, ledger, journal)
                guidance = {
                    **guidance,
                    "state": result.status,
                    "conflict": result.conflict,
                }
            resource_reports = [
                _apply_resource_locked(agent_id, resource, root, ledger, journal)
                for resource in resources
            ]
            if json.dumps(ledger, sort_keys=True) != before:
                _save_ledger(resolved_data_root, ledger, ledger_digest)
        except (AgentConnectionError, StoreError, OSError, ValueError) as exc:
            recovery = journal.rollback()
            raise AgentTransactionError(
                f"agent connect failed and was rolled back: {exc}", recovery
            ) from exc

    probe = probe_agent_connection(agent_id, home=home, rush_binary=binary)
    connected: dict[str, Any] = {
        "apply": applied.to_dict(),
        "probe": probe.to_dict(),
        "memory": memory_entry,
        "guidance": guidance,
        "resources": resource_reports,
    }
    if migration is not None:
        connected["migration"] = {**migration, "state": _migration_state(applied)}
    return connected


def _migration_consent(
    step: RegistrationStep, consent: ProfileConsent
) -> tuple[dict[str, Any] | None, str | None]:
    """A migration step's preview, plus `pending`/`declined` when it must not apply."""
    if step.migration_profile is None:
        return None, None
    preview = registration_preview(step)
    if callable(consent):
        return preview, None if consent(preview) else "declined"
    return preview, None if consent else "pending"


def _migration_state(applied: AgentApplyResult) -> str:
    if applied.ok:
        return "applied"
    if applied.conflict:
        return "conflict"
    return "recovery_required" if applied.recovery_required else "failed"


# --- Disconnect ----------------------------------------------------------------------


@dataclass(frozen=True)
class AgentDisconnectResult:
    status: Literal["ok", "conflict"]
    removed: list[str]
    conflicts: list[dict[str, Any]]
    kept_shared: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "removed": list(self.removed),
            "conflicts": list(self.conflicts),
            "kept_shared": list(self.kept_shared),
        }


def _remove_toml_table(text: str, table_path: tuple[str, ...]) -> str | None:
    header = "[" + ".".join(table_path) + "]"
    lines = text.splitlines(keepends=True)
    start = next((i for i, line in enumerate(lines) if line.strip() == header), None)
    if start is None:
        return None
    end = next(
        (i for i in range(start + 1, len(lines)) if lines[i].lstrip().startswith("[")),
        len(lines),
    )
    before = lines[:start]
    if end == len(lines) and before and not before[-1].strip():
        before = before[:-1]
    return "".join(before + lines[end:])


def _remove_json_like_entry(text: str, servers_key: tuple[str, ...]) -> str | None:
    """Splice out only the `rush` key/value (and one separating comma)."""
    cur_start, cur_end = _root_object_body(text)
    for key in servers_key:
        found = _find_top_level_key(text, cur_start, cur_end, key)
        if found is None:
            return None
        _, _, value_start, value_end = found
        if text[value_start] != "{":
            raise MalformedConfigError(f"expected object at {key!r}")
        cur_start, cur_end = value_start + 1, value_end - 1
    found = _find_top_level_key(text, cur_start, cur_end, "rush")
    if found is None:
        return None
    key_start, _, _, value_end = found
    after = _skip_ws_and_comments(text, value_end)
    if after < cur_end and text[after] == ",":
        resume = after + 1
        while resume < cur_end and text[resume] in " \t\r\n":
            resume += 1
        return text[:key_start] + text[resume:]
    # Last entry: drop the comma that ends the previous value, if any.
    ws_start = key_start
    while ws_start > cur_start and text[ws_start - 1] in " \t\r\n":
        ws_start -= 1
    previous_end: int | None = None
    i = cur_start
    while i < key_start:
        i = _skip_ws_and_comments(text, i)
        if i >= key_start:
            break
        if text[i] == ",":
            i += 1
            continue
        i = _skip_string(text, i)
        i = _skip_ws_and_comments(text, i) + 1
        i = _skip_value(text, i)
        previous_end = i
    if previous_end is None:
        return text[:ws_start] + text[value_end:]
    comma = _skip_ws_and_comments(text, previous_end)
    return text[:comma] + text[comma + 1 : ws_start] + text[value_end:]


def _legacy_owned_entries(agent_id: str) -> list[dict[str, Any]]:
    """What Rush's own writers produce for a pre-ledger registration."""
    try:
        binary = resolve_rush_binary(None)
    except AgentConnectionError:
        return []
    # Pre-ledger writers always launched the full server (`mcp serve`).
    legacy = build_stdio_entry(binary, args=LEGACY_SERVE_ARGS)
    entries = [legacy]
    if agent_id == "claude-code":
        entries.append({"type": "stdio", **legacy, "env": {}})
    return entries


def _remove_registration(
    adapter: AgentAdapter, config_path: Path, raw: bytes
) -> str | None:
    """Remove the host's `rush` entry; a failure reason, or None on success."""
    if adapter.native_binary and shutil.which(adapter.native_binary):
        try:
            proc = subprocess.run(
                (adapter.native_binary, "mcp", "remove", "rush", "--scope", "user"),
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            return f"native_remove_failed: {exc}"
        return None if proc.returncode == 0 else "native_remove_failed"
    text = raw.decode("utf-8")
    if adapter.config_format == "toml":
        new_text = _remove_toml_table(text, (*adapter.servers_key, "rush"))
    else:
        new_text = _remove_json_like_entry(text, adapter.servers_key)
    if new_text is None:
        return None
    cas_replace_file(
        config_path, new_text.encode("utf-8"), expected_sha256=_sha256(raw)
    )
    return None


def _conflict_row(
    component: str,
    path: str,
    expected: str | None,
    actual: str | None,
    reason: str,
) -> dict[str, Any]:
    return {
        "component": component,
        "path": path,
        "expected": expected,
        "actual": actual,
        "reason": reason,
    }


def disconnect_agent(
    agent_id: str,
    *,
    project_root: Path | None,
    data_root: Path | None = None,
    home: Path | None = None,
    os_name: str | None = None,
) -> AgentDisconnectResult:
    """Remove only the Rush-owned, unchanged components of one host connection.

    Scope is (agent, project) -- or user scope when `project_root` is None.
    Components: the MCP entry, the instruction block (or this host's name
    in a shared block's `hosts=`), skill/hook file resources, and hook
    activation. A component whose bytes no longer match what Rush recorded
    is left untouched and reported as a conflict with its path and digests.
    A component another ledger row still references is kept. Running it
    again is a no-op `ok`.
    """
    adapter = ADAPTERS.get(agent_id)
    if adapter is None:
        raise UnknownAgentError(f"unknown agent: {agent_id!r}")
    root = Path(project_root).resolve() if project_root is not None else None
    resolved_data_root = data_root or default_data_root()
    home = home or Path.home()
    os_name = os_name or platform.system()
    removed: list[str] = []
    kept_shared: list[str] = []
    conflicts: list[dict[str, Any]] = []

    with _ledger_lock(resolved_data_root):
        ledger, ledger_digest = _load_ledger(resolved_data_root)
        mine = {
            eid: row
            for eid, row in ledger.items()
            if row.get("host") == agent_id and _same_project(row, root)
        }
        remaining = {eid: row for eid, row in ledger.items() if eid not in mine}
        had_mcp_rows = any(
            row.get("kind") == "mcp_entry" and row.get("host") == agent_id
            for row in ledger.values()
        )

        # A native plugin is uninstalled from its host before the files it
        # runs from are removed.
        for eid, row in sorted(
            mine.items(),
            key=lambda item: (item[1].get("kind") != "native_plugin", item[0]),
        ):
            kind = str(row.get("kind"))
            recorded_path = str(row.get("path"))
            try:
                outcome = _disconnect_component(
                    row, agent_id, adapter, remaining, home=home, os_name=os_name
                )
            except CASConflictError as exc:
                outcome = _conflict_row(
                    kind,
                    recorded_path,
                    row.get("written_sha256"),
                    exc.actual,
                    exc.reason,
                )
            except (ValueError, OSError, MalformedConfigError) as exc:
                outcome = _conflict_row(
                    kind, recorded_path, row.get("written_sha256"), None, str(exc)
                )
            if isinstance(outcome, dict):
                conflicts.append(outcome)
                remaining[eid] = row
            elif outcome == "removed":
                removed.append(kind)
            elif outcome == "kept_shared":
                kept_shared.append(kind)

        if not had_mcp_rows:
            try:
                legacy = _disconnect_legacy_registration(
                    agent_id, adapter, home=home, os_name=os_name
                )
            except CASConflictError as exc:
                legacy = _conflict_row(
                    "mcp_entry", str(exc.path), exc.expected, exc.actual, exc.reason
                )
            except (ValueError, OSError, MalformedConfigError) as exc:
                legacy = _conflict_row("mcp_entry", "", None, None, str(exc))
            if isinstance(legacy, dict):
                conflicts.append(legacy)
            elif legacy == "removed":
                removed.append("mcp_entry")

        if mine:
            _save_ledger(resolved_data_root, remaining, ledger_digest)

    return AgentDisconnectResult(
        "conflict" if conflicts else "ok", removed, conflicts, kept_shared
    )


def _references(remaining: dict[str, dict[str, Any]], kind: str, path: Path) -> bool:
    for row in remaining.values():
        # A Claude Code local-scope entry (T26) is its own per-project entry
        # inside the shared config file, never the user-scope entry.
        if row.get("kind") != kind or row.get("scope") == "local":
            continue
        try:
            if _entry_physical_path(row) == path:
                return True
        except ValueError:
            continue
    return False


def _disconnect_component(
    row: dict[str, Any],
    agent_id: str,
    adapter: AgentAdapter,
    remaining: dict[str, dict[str, Any]],
    *,
    home: Path,
    os_name: str,
) -> str | dict[str, Any]:
    kind = row.get("kind")
    recorded_path = str(row.get("path"))
    written = row.get("written_sha256")
    if kind == "instruction_block":
        return _disconnect_instruction_block(row, agent_id, remaining)
    if kind == "native_plugin":
        return _uninstall_native_plugin(agent_id, recorded_path)
    if kind == "hook_activation":
        # T7: one record per (host, project) in the shared activations file.
        from .agent_hooks import remove_activation

        return remove_activation(row)
    if kind in _FILE_KINDS:
        path = _entry_physical_path(row)
        if _references(remaining, str(kind), path):
            return "kept_shared"
        actual = owned_path_digest(path)
        if actual is None:
            return "absent"
        if actual != written:
            return _conflict_row(str(kind), recorded_path, written, actual, "changed")
        if path.is_dir():
            if owned_path_digest(path) != written:
                return _conflict_row(str(kind), recorded_path, written, None, "changed")
            shutil.rmtree(path)
        else:
            cas_unlink(path, expected_sha256=actual)
        return "removed"
    if kind == "mcp_entry":
        config_path = _entry_physical_path(row)
        if config_path not in adapter.config_paths(os_name, home):
            raise ValueError(
                f"ledger MCP path is not {agent_id}'s config: {config_path}"
            )
        if row.get("scope") == "local":
            return _disconnect_local_entry(row, agent_id, config_path)
        if _references(remaining, "mcp_entry", config_path):
            return "kept_shared"
        raw = _read_regular(config_path)
        if raw is None:
            return "absent"
        current = _read_rush_entry(raw.decode("utf-8"), adapter)
        if current is None:
            return "absent"
        actual = _entry_digest(current)
        if actual != written:
            return _conflict_row("mcp_entry", recorded_path, written, actual, "changed")
        failure = _remove_registration(adapter, config_path, raw)
        if failure is not None:
            return _conflict_row("mcp_entry", recorded_path, written, actual, failure)
        return "removed"
    raise ValueError(f"unknown ledger kind: {kind!r}")


def _disconnect_instruction_block(
    row: dict[str, Any], agent_id: str, remaining: dict[str, dict[str, Any]]
) -> str | dict[str, Any]:
    path = _entry_physical_path(row)
    recorded_path = str(row.get("path"))
    written = row.get("written_sha256")
    raw = _read_regular(path)
    if raw is None:
        return "absent"
    actual = _sha256(raw)
    doc = _decode_document(raw)
    try:
        block = _parse_block(doc)
    except _MarkerConflict as exc:
        return _conflict_row(
            "instruction_block", recorded_path, written, actual, exc.reason
        )
    if block is None:
        return "absent"
    unchanged_file = actual == written
    if not unchanged_file and block.body_digest != block.marker_digest:
        return _conflict_row(
            "instruction_block", recorded_path, written, actual, "user_edited_block"
        )
    if agent_id not in block.hosts:
        return "absent"
    other_hosts = tuple(host for host in block.hosts if host != agent_id)
    if other_hosts:
        begin_text = doc.text[block.begin.start : block.begin.end]
        terminator = begin_text[len(block.begin.content) :]
        new_text = (
            doc.text[: block.begin.start]
            + _begin_line(other_hosts, block.body_digest)
            + terminator
            + doc.text[block.begin.end :]
        )
    else:
        new_text = _without_block(doc, block, row.get("original_sha256"))
    if not new_text and row.get("original_sha256") is None:
        cas_unlink(path, expected_sha256=actual)
        new_digest: str | None = None
    else:
        new_digest = cas_replace_file(
            path, doc.encode(new_text), expected_sha256=actual
        )
    for other in remaining.values():
        if other.get("kind") != "instruction_block" or new_digest is None:
            continue
        with suppress(ValueError):
            if _entry_physical_path(other) == path:
                other["written_sha256"] = new_digest
    return "removed"


def _disconnect_legacy_registration(
    agent_id: str, adapter: AgentAdapter, *, home: Path, os_name: str
) -> str | dict[str, Any]:
    """A pre-ledger `rush` entry counts as owned only if it equals Rush's own output."""
    config_path, current = read_registration_entry(agent_id, home=home, os_name=os_name)
    if current is None:
        return "absent"
    actual = _entry_digest(current)
    owned = _legacy_owned_entries(agent_id)
    if current not in owned:
        return _conflict_row(
            "mcp_entry",
            str(config_path),
            _entry_digest(owned[0]) if owned else None,
            actual,
            "not_owned" if owned else "ownership_unproven",
        )
    raw = _read_regular(config_path)
    assert raw is not None
    failure = _remove_registration(adapter, config_path, raw)
    if failure is not None:
        return _conflict_row("mcp_entry", str(config_path), actual, actual, failure)
    return "removed"


# --- Native host plugin packages (Phase 70 T2) --------------------------------------

# Package host name (also its CLI binary) -> the adapter id its ledger rows use.
PLUGIN_HOSTS: dict[str, str] = {"claude": "claude-code", "codex": "codex"}
PLUGIN_MARKETPLACE = "rush-local"
PLUGIN_ID = f"rush@{PLUGIN_MARKETPLACE}"
_PLUGIN_MANIFESTS: dict[str, tuple[str, str]] = {
    "claude": (".claude-plugin", "plugin.json"),
    "codex": (".codex-plugin", "plugin.json"),
}
# One marketplace manifest serves both hosts: Codex also reads a marketplace
# root's `.claude-plugin/marketplace.json` (design brief X8, proven locally).
_MARKETPLACE_REL = Path(".claude-plugin") / "marketplace.json"
_VERSION_RE = re.compile(r"[0-9A-Za-z][0-9A-Za-z.+_-]{0,63}")
_TEMPLATE_MARK = "@RUSH_"


def _plugin_host(host: str) -> str:
    if host not in PLUGIN_HOSTS:
        raise UnknownAgentError(
            f"unknown plugin host {host!r}; expected one of {sorted(PLUGIN_HOSTS)}"
        )
    return PLUGIN_HOSTS[host]


def plugin_uninstall_commands(host: str) -> list[tuple[str, ...]]:
    """The host's own commands that uninstall the plugin and its marketplace."""
    _plugin_host(host)
    if host == "claude":
        return [
            ("claude", "plugin", "uninstall", PLUGIN_ID, "--scope", "user"),
            ("claude", "plugin", "marketplace", "remove", PLUGIN_MARKETPLACE),
        ]
    return [
        ("codex", "plugin", "remove", PLUGIN_ID),
        ("codex", "plugin", "marketplace", "remove", PLUGIN_MARKETPLACE),
    ]


def _uninstall_native_plugin(agent_id: str, recorded_path: str) -> str | dict[str, Any]:
    """Disconnect step for a `native_plugin` row: the host's own uninstall."""
    host = next(name for name, aid in PLUGIN_HOSTS.items() if aid == agent_id)
    if shutil.which(host) is None:
        return _conflict_row("native_plugin", recorded_path, None, None, "host_missing")
    for argv in plugin_uninstall_commands(host):
        try:
            proc = subprocess.run(
                argv, capture_output=True, text=True, timeout=60, check=False
            )
        except (OSError, subprocess.SubprocessError) as exc:
            return _conflict_row(
                "native_plugin",
                recorded_path,
                None,
                None,
                f"native_uninstall_failed: {exc}",
            )
        detail = (proc.stderr or proc.stdout or "").strip()
        # Both hosts report an already-removed plugin/marketplace this way
        # (claude 2.1.283: "not found"; codex 0.155.1: "is not configured
        # or installed"), so a repeated disconnect stays a no-op.
        already_gone = "not found" in detail or "not configured" in detail
        if proc.returncode != 0 and not already_gone:
            detail = detail or f"exit {proc.returncode}"
            return _conflict_row(
                "native_plugin",
                recorded_path,
                None,
                None,
                f"native_uninstall_failed: {detail}",
            )
    return "removed"


@dataclass(frozen=True)
class ManualEntryRemoval:
    """Removing a host's manual `rush` MCP entry before its plugin installs."""

    path: Path
    original: bytes
    new_bytes: bytes
    entry_sha256: str
    owned: bool
    diff: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": str(self.path),
            "entry_sha256": self.entry_sha256,
            "owned": self.owned,
            "consent_required": not self.owned,
            "diff": self.diff,
        }


def _read_ledger_rows(data_root: Path | None) -> dict[str, dict[str, Any]]:
    """Ledger rows read without creating anything (design brief X5)."""
    try:
        payload = json.loads(_read_regular(ownership_ledger_path(data_root)) or b"{}")
    except (OSError, ValueError, CASConflictError):
        return {}
    rows = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(rows, dict):
        return {}
    return {eid: row for eid, row in rows.items() if isinstance(row, dict)}


def plan_manual_entry_removal(
    agent_id: str, config_path: Path, *, data_root: Path | None = None
) -> ManualEntryRemoval | None:
    """Preview removing `agent_id`'s manual `rush` entry; None when there is none.

    The entry is Rush-owned only when the ownership ledger records exactly
    its digest at this path (T3 contract). Anything else, including an
    entry that merely looks like Rush's own output, is the user's and needs
    their consent before it is converted.
    """
    adapter = ADAPTERS.get(agent_id)
    if adapter is None:
        raise UnknownAgentError(f"unknown agent: {agent_id!r}")
    raw = _read_regular(config_path)
    if raw is None:
        return None
    text = raw.decode("utf-8")
    entry = _read_rush_entry(text, adapter)
    if entry is None:
        return None
    if adapter.config_format == "toml":
        new_text = _remove_toml_table(text, (*adapter.servers_key, "rush"))
    else:
        new_text = _remove_json_like_entry(text, adapter.servers_key)
    if new_text is None:
        return None
    diff = "".join(
        difflib.unified_diff(
            text.splitlines(keepends=True),
            new_text.splitlines(keepends=True),
            fromfile=str(config_path),
            tofile=str(config_path),
        )
    )
    digest = _entry_digest(entry)
    owned = any(
        row.get("kind") == "mcp_entry"
        and row.get("host") == agent_id
        and row.get("path") == str(config_path)
        and row.get("written_sha256") == digest
        for row in _read_ledger_rows(data_root).values()
    )
    return ManualEntryRemoval(
        config_path, raw, new_text.encode("utf-8"), digest, owned, diff
    )


def _render_template(value: Any, substitutions: dict[str, str]) -> Any:
    if isinstance(value, str):
        for token, replacement in substitutions.items():
            value = value.replace(token, replacement)
        return value
    if isinstance(value, list):
        return [_render_template(item, substitutions) for item in value]
    if isinstance(value, dict):
        return {k: _render_template(v, substitutions) for k, v in value.items()}
    return value


def _copy_rendered(src: Path, dst: Path, substitutions: dict[str, str]) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)
    if dst.suffix == ".json":
        data = json.loads(dst.read_text(encoding="utf-8"))
        rendered = _render_template(data, substitutions)
        dst.write_text(json.dumps(rendered, indent=2) + "\n", encoding="utf-8")


def _stage_host_root(
    host: str, assets: Path, target: Path, substitutions: dict[str, str]
) -> None:
    """Build one host's marketplace root: the marketplace manifest plus `rush/`."""
    source = assets / host
    marketplace_source = assets / "claude" / _MARKETPLACE_REL
    for dirpath, dirnames, filenames in os.walk(source):
        dirnames.sort()
        for name in sorted(filenames):
            src = Path(dirpath) / name
            if src == marketplace_source:
                continue
            _copy_rendered(
                src, target / "rush" / src.relative_to(source), substitutions
            )
    _copy_rendered(marketplace_source, target / _MARKETPLACE_REL, substitutions)


def _validate_host_root(host: str, root: Path) -> None:
    """JSON parse, no unrendered token, and closure of every manifest reference."""
    for path in sorted(root.rglob("*.json")):
        try:
            text = path.read_text(encoding="utf-8")
            json.loads(text)
        except (OSError, ValueError) as exc:
            raise AgentConnectionError(f"invalid plugin JSON {path}: {exc}") from exc
        if _TEMPLATE_MARK in text:
            raise AgentConnectionError(f"unrendered template token in {path}")
    marketplace = json.loads((root / _MARKETPLACE_REL).read_text(encoding="utf-8"))
    for plugin in marketplace.get("plugins", []):
        if not (root / str(plugin.get("source", ""))).is_dir():
            raise AgentConnectionError(f"marketplace source missing: {plugin!r}")
    plugin_dir = root / "rush"
    manifest_path = plugin_dir.joinpath(*_PLUGIN_MANIFESTS[host])
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(manifest.get("mcpServers"), str):
        raise AgentConnectionError(f"{manifest_path}: no mcpServers reference")
    for value in manifest.values():
        if (
            isinstance(value, str)
            and value.startswith("./")
            and not (plugin_dir / value).exists()
        ):
            raise AgentConnectionError(f"{manifest_path}: missing {value}")
    for required in ("skills/rush/SKILL.md", "hooks/hooks.json"):
        if not (plugin_dir / required).is_file():
            raise AgentConnectionError(f"{plugin_dir}: missing {required}")


def _plugin_version_of(row: dict[str, Any], base: Path) -> str | None:
    """The version directory a plugin ledger row lives in, or None."""
    try:
        rel = Path(str(row.get("path"))).resolve().relative_to(base.resolve())
    except ValueError:
        return None
    return rel.parts[0] if len(rel.parts) == 2 else None


def materialize_agent_plugins(
    *,
    rush_binary: str,
    rush_version: str | None = None,
    data_root: Path | None = None,
) -> dict[str, Path]:
    """Write `<data_root>/agent-plugins/<version>/{claude,codex}/` marketplace roots.

    Each root holds `.claude-plugin/marketplace.json` (marketplace
    `rush-local`) and the `rush/` plugin, with the absolute Rush executable
    substituted into its MCP file and hooks. Sources resolve through
    `importlib.resources`, never the cwd. The version directory is built in
    a stage directory, validated, then renamed into place, so a failure
    leaves no partial version. An existing version directory is kept when
    identical and replaced only while it is still exactly what Rush
    recorded. Every host root is recorded as a `file_resource` ledger row.
    """
    from importlib.resources import as_file, files

    from rush import __version__

    binary = str(rush_binary)
    if not Path(binary).is_absolute():
        raise AgentConnectionError(f"rush binary must be an absolute path: {binary}")
    version = rush_version or __version__
    if not _VERSION_RE.fullmatch(version):
        raise AgentConnectionError(f"unsafe plugin version name: {version!r}")
    resolved_data_root = data_root or default_data_root()
    base = resolved_data_root / "agent-plugins"
    final = base / version
    substitutions = {
        "@RUSH_BINARY_SH@": shlex.quote(binary),
        "@RUSH_BINARY@": binary,
        "@RUSH_VERSION@": version,
    }
    with _ledger_lock(resolved_data_root):
        base.mkdir(parents=True, exist_ok=True)
        stage = Path(tempfile.mkdtemp(prefix=f".stage-{version}-", dir=base))
        try:
            with as_file(files("rush.integrations") / "agent_assets") as assets:
                for host in PLUGIN_HOSTS:
                    _stage_host_root(host, Path(assets), stage / host, substitutions)
            for host in PLUGIN_HOSTS:
                _validate_host_root(host, stage / host)
            ledger, ledger_version = _load_ledger(resolved_data_root)
            if final.exists():
                _replace_version_dir(final, stage, ledger)
            else:
                os.rename(stage, final)
        finally:
            shutil.rmtree(stage, ignore_errors=True)
        before = json.dumps(ledger, sort_keys=True)
        roots: dict[str, Path] = {}
        for host, agent_id in PLUGIN_HOSTS.items():
            root = final / host
            roots[host] = root
            entry_id = f"{agent_id}:file_resource:{root}:user"
            digest = owned_path_digest(root)
            if digest is None:
                raise AgentConnectionError(f"materialized root vanished: {root}")
            recorded = ledger.get(entry_id)
            if recorded is None or recorded.get("written_sha256") != digest:
                ledger[entry_id] = _ledger_entry(
                    entry_id, "file_resource", agent_id, None, str(root), digest, None
                )
        if json.dumps(ledger, sort_keys=True) != before:
            _save_ledger(resolved_data_root, ledger, ledger_version)
    return roots


def _replace_version_dir(
    final: Path, stage: Path, ledger: dict[str, dict[str, Any]]
) -> None:
    """Swap `stage` in for an existing version dir that is still Rush's own."""
    current = {host: owned_path_digest(final / host) for host in PLUGIN_HOSTS}
    if all(current[host] == owned_path_digest(stage / host) for host in PLUGIN_HOSTS):
        return  # already identical; the caller discards the stage
    recorded = {
        str(row.get("path")): row.get("written_sha256")
        for row in ledger.values()
        if row.get("kind") == "file_resource"
    }
    for host in PLUGIN_HOSTS:
        path = final / host
        if current[host] is not None and recorded.get(str(path)) != current[host]:
            raise CASConflictError(
                path, recorded.get(str(path)), current[host], reason="not_owned"
            )
    extra = {entry.name for entry in final.iterdir()} - set(PLUGIN_HOSTS)
    if extra:
        raise CASConflictError(
            final, None, None, reason=f"unowned_entries:{sorted(extra)}"
        )
    trash = final.with_name(f".trash-{final.name}-{os.getpid()}")
    os.rename(final, trash)
    try:
        os.rename(stage, final)
    except OSError:
        os.rename(trash, final)
        raise
    shutil.rmtree(trash)


def record_native_plugin_install(
    *,
    data_root: Path,
    host: str,
    plugin_root: Path,
    removed_entry: ManualEntryRemoval | None = None,
) -> dict[str, Any]:
    """Record that `host` now runs the plugin from `plugin_root`.

    Adds a `native_plugin` ledger row (the host installation; the files
    stay owned by the materializer's `file_resource` row). When the install
    converted a manual `rush` entry -- Rush's own, or the user's after they
    consented -- the row records that entry's path and digest under
    `replaced_entry`, and the host's `mcp_entry` rows for it are dropped.
    """
    removed_entry_path = removed_entry.path if removed_entry is not None else None
    agent_id = _plugin_host(host)
    digest = owned_path_digest(plugin_root)
    if digest is None:
        raise AgentConnectionError(f"plugin root is missing: {plugin_root}")
    with _ledger_lock(data_root):
        ledger, ledger_version = _load_ledger(data_root)
        if removed_entry_path is not None:
            for eid, row in list(ledger.items()):
                if (
                    row.get("kind") == "mcp_entry"
                    and row.get("host") == agent_id
                    and row.get("path") == str(removed_entry_path)
                ):
                    del ledger[eid]
        entry_id = f"{agent_id}:native_plugin:{plugin_root}:user"
        row = _ledger_entry(
            entry_id, "native_plugin", agent_id, None, str(plugin_root), digest, None
        )
        if removed_entry is not None:
            row["replaced_entry"] = {
                "path": str(removed_entry.path),
                "sha256": removed_entry.entry_sha256,
                "owned_before": removed_entry.owned,
            }
        ledger[entry_id] = row
        _save_ledger(data_root, ledger, ledger_version)
    return row


def installed_plugin_roots(host: str, data_root: Path | None = None) -> list[Path]:
    """Plugin roots `host` is recorded as installed from (read-only, no mkdir)."""
    agent_id = _plugin_host(host)
    return [
        Path(str(row.get("path")))
        for row in _read_ledger_rows(data_root).values()
        if row.get("kind") == "native_plugin" and row.get("host") == agent_id
    ]


def finalize_agent_plugin_upgrade(
    *, host: str, confirmed_version: str, data_root: Path | None = None
) -> dict[str, Any]:
    """Retire older plugin versions once `host` reports `confirmed_version`.

    `host`'s own `native_plugin` rows for other versions are dropped. An
    older version directory is then removed only when no host is still
    recorded as installed from it and every host root in it is still
    byte-for-byte what Rush materialized; otherwise it is kept (or reported
    as a conflict), never deleted on a guess.
    """
    agent_id = _plugin_host(host)
    resolved_data_root = data_root or default_data_root()
    base = resolved_data_root / "agent-plugins"
    if (
        not _VERSION_RE.fullmatch(confirmed_version)
        or not (base / confirmed_version).is_dir()
    ):
        raise AgentConnectionError(
            f"confirmed plugin version is not materialized: {confirmed_version!r}"
        )
    removed: list[str] = []
    kept: list[str] = []
    conflicts: list[dict[str, Any]] = []
    with _ledger_lock(resolved_data_root):
        ledger, ledger_version = _load_ledger(resolved_data_root)
        before = json.dumps(ledger, sort_keys=True)
        for eid, row in list(ledger.items()):
            version = _plugin_version_of(row, base)
            if (
                row.get("kind") == "native_plugin"
                and row.get("host") == agent_id
                and version not in (None, confirmed_version)
            ):
                del ledger[eid]
        for version_dir in sorted(base.iterdir()):
            name = version_dir.name
            if (
                name == confirmed_version
                or name.startswith(".")
                or not version_dir.is_dir()
            ):
                continue
            rows = {
                eid: row
                for eid, row in ledger.items()
                if _plugin_version_of(row, base) == name
            }
            file_rows = {
                eid: row
                for eid, row in rows.items()
                if row.get("kind") == "file_resource"
            }
            if len(file_rows) != len(rows) or not file_rows:
                kept.append(name)  # a host still runs it, or Rush never recorded it
                continue
            changed = []
            for row in file_rows.values():
                actual = owned_path_digest(Path(str(row["path"])))
                if actual != row.get("written_sha256"):
                    changed.append(
                        _conflict_row(
                            "file_resource",
                            str(row["path"]),
                            row.get("written_sha256"),
                            actual,
                            "changed",
                        )
                    )
            owned_names = {Path(str(row["path"])).name for row in file_rows.values()}
            extra = {entry.name for entry in version_dir.iterdir()} - owned_names
            if extra:
                changed.append(
                    _conflict_row(
                        "file_resource",
                        str(version_dir),
                        None,
                        None,
                        f"unowned_entries:{sorted(extra)}",
                    )
                )
            if changed:
                conflicts.extend(changed)
                continue
            shutil.rmtree(version_dir)
            for eid in file_rows:
                del ledger[eid]
            removed.append(name)
        if json.dumps(ledger, sort_keys=True) != before:
            _save_ledger(resolved_data_root, ledger, ledger_version)
    return {
        "state": "conflict" if conflicts else "ok",
        "host": host,
        "confirmed_version": confirmed_version,
        "removed": removed,
        "kept": kept,
        "conflicts": conflicts,
    }


# --- Phase 70 T26: project-bound host registration, readback and probe --------------
#
# `rush setup PATH --agent HOST` binds a host's Rush server to one project: the
# entry launches the installed Rush with `mcp serve --project ID --session
# HOST:ID`. Claude Code keeps that entry in the project's local scope
# (`claude mcp add --scope local`, run with `cwd=PATH`), so each project has its
# own. Codex has one global `[mcp_servers.rush]` table, edited through the T3
# compare-and-swap writer; rebinding it from another project is a host-change
# diff that needs consent. Host readback and capability-probe argv are data
# here; the real-host lanes (G6) validate them against each installed host.

HOST_BINARIES: dict[str, str] = {"claude-code": "claude", "codex": "codex"}
PROBE_PROMPT = "Call rush_status with no arguments and return its JSON"
HOST_READBACK_ARGS: dict[str, tuple[str, ...]] = {
    "claude-code": ("mcp", "get", "rush"),
    "codex": ("mcp", "get", "rush", "--json"),
}
HOST_PROBE_ARGS: dict[str, tuple[str, ...]] = {
    "claude-code": (
        "-p",
        PROBE_PROMPT,
        "--output-format",
        "stream-json",
        "--verbose",
        "--allowedTools",
        "mcp__rush__rush_status",
    ),
    "codex": ("exec", "--json", "--skip-git-repo-check", PROBE_PROMPT),
}
HOST_LOGIN_ACTIONS: dict[str, str] = {
    "claude-code": "claude /login",
    "codex": "codex login",
}
_CLAUDE_CONNECTED_RE = re.compile(r"status:\s*(?:\S+\s+)?connected\b", re.IGNORECASE)

# Runs one host CLI command with `cwd`; returns stdout, raises `HostCommandError`.
HostRunner = Callable[[tuple[str, ...], str], str]


class HostCommandError(AgentConnectionError):
    """A host CLI command exited non-zero or could not be started."""

    def __init__(
        self, argv: Sequence[str], returncode: int | None, detail: str
    ) -> None:
        super().__init__(f"{' '.join(argv[:4])} failed ({returncode}): {detail}")
        self.argv = tuple(argv)
        self.returncode = returncode
        self.detail = detail


def run_host_command(argv: tuple[str, ...], cwd: str) -> str:
    """Run one host CLI command in `cwd` (stdin closed); its stdout."""
    from rush.logging import redact_secrets

    try:
        proc = subprocess.run(
            list(argv),
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=600,
            check=False,
            stdin=subprocess.DEVNULL,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise HostCommandError(argv, None, str(exc)) from exc
    if proc.returncode != 0:
        tail = (proc.stderr or proc.stdout or "").strip()[-2000:]
        raise HostCommandError(argv, proc.returncode, redact_secrets(tail))
    return proc.stdout


def project_session_id(agent_id: str, project_id: str) -> str:
    """The session a project-bound server defaults to: `HOST:PROJECT_ID`."""
    return f"{HOST_BINARIES.get(agent_id, agent_id)}:{project_id}"


def project_serve_args(project_id: str, session_id: str) -> tuple[str, ...]:
    return (
        "mcp",
        "serve",
        "--project",
        project_id,
        "--session",
        session_id,
        "--profile",
        "core",
    )


def _claude_local_entry(raw: bytes | None, root: Path) -> dict[str, Any] | None:
    """Claude Code's local-scope `rush` entry for `root` in `~/.claude.json`."""
    if raw is None:
        return None
    try:
        data = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as exc:
        raise MalformedConfigError(f"Claude Code config is not JSON: {exc}") from exc
    node: Any = data.get("projects") if isinstance(data, dict) else None
    for key in (str(root), "mcpServers", "rush"):
        node = node.get(key) if isinstance(node, dict) else None
    return node if isinstance(node, dict) else None


def read_project_registration_entry(
    agent_id: str,
    *,
    project_root: Path,
    home: Path | None = None,
    os_name: str | None = None,
) -> tuple[Path, dict[str, Any] | None]:
    """The config path a project-bound registration targets and its current entry."""
    root = Path(project_root).resolve()
    if agent_id == "claude-code":
        adapter = ADAPTERS[agent_id]
        config_path = adapter.config_paths(
            os_name or platform.system(), home or Path.home()
        )[0]
        return config_path, _claude_local_entry(_read_regular(config_path), root)
    return read_registration_entry(agent_id, home=home, os_name=os_name)


def same_server_entry(current: dict[str, Any] | None, entry: dict[str, Any]) -> bool:
    """Whether a host entry already launches exactly `entry`'s command and args."""
    return (
        current is not None
        and current.get("command") == entry["command"]
        and list(current.get("args") or []) == list(entry["args"])
    )


def _entry_diff(
    path: Path, before: dict[str, Any] | None, after: dict[str, Any]
) -> str:
    def lines(entry: dict[str, Any] | None) -> list[str]:
        if entry is None:
            return []
        text = json.dumps({"rush": entry}, indent=2, sort_keys=True) + "\n"
        return text.splitlines(keepends=True)

    return _redacted(
        "".join(
            difflib.unified_diff(
                lines(before), lines(after), fromfile=str(path), tofile=str(path)
            )
        )
    )


def _redacted(text: str) -> str:
    from rush.logging import redact_secrets

    return redact_secrets(text)


def plan_project_registration(
    agent_id: str,
    *,
    rush_binary: str,
    project_root: Path,
    project_id: str | None = None,
    session_id: str | None = None,
    home: Path | None = None,
    os_name: str | None = None,
    which: Callable[[str], str | None] = shutil.which,
) -> RegistrationStep:
    """Plan one host's project-bound Rush MCP entry. Never writes or runs anything.

    `project_id` defaults to the canonical project root, which `mcp serve
    --project` also resolves once the root is registered. An existing `rush`
    entry that differs from the planned one (another project, an unbound
    entry, another binary) is a host change: the step carries its diff and
    `requires_consent=True`. An identical entry is `unchanged`.
    """
    if agent_id not in HOST_BINARIES:
        raise UnknownAgentError(
            f"project-bound registration is defined for {sorted(HOST_BINARIES)}, "
            f"not {agent_id!r}"
        )
    adapter = ADAPTERS[agent_id]
    root = Path(project_root).resolve()
    pid = project_id or str(root)
    entry = build_stdio_entry(
        rush_binary,
        args=project_serve_args(pid, session_id or project_session_id(agent_id, pid)),
    )
    config_path, current = read_project_registration_entry(
        agent_id, project_root=root, home=home, os_name=os_name
    )
    same = same_server_entry(current, entry)
    changes_existing = current is not None and not same
    if agent_id == "claude-code":
        binary = which(HOST_BINARIES[agent_id])
        if binary is None:
            raise AgentConnectionError("absent_host: `claude` is not on PATH")
        return RegistrationStep(
            agent_id,
            "native",
            config_path,
            None,
            (binary, "mcp", "add", "rush", "--scope", "local", "--")
            + (entry["command"], *entry["args"]),
            None,
            adapter.restart_required,
            _entry_digest(current) if current is not None else None,
            scope="local",
            project_root=root,
            entry=entry,
            current_entry=current,
            diff="" if same else _entry_diff(config_path, current, entry),
            requires_consent=changes_existing,
            unchanged=same,
        )
    raw = _read_regular(config_path)
    if raw is not None and not os.access(config_path, os.W_OK):
        raise ReadOnlyConfigError(f"{agent_id}: config is read-only: {config_path}")
    text = raw.decode("utf-8") if raw is not None else _default_document(adapter)
    new_text = (
        text
        if same
        else _upsert_toml_table(text, (*adapter.servers_key, "rush"), entry)
    )
    # No context lines and redacted: the diff is shown and saved in plans, and
    # a host config's neighbouring tables can hold credentials.
    diff = _redacted(
        "".join(
            difflib.unified_diff(
                text.splitlines(keepends=True),
                new_text.splitlines(keepends=True),
                fromfile=str(config_path),
                tofile=str(config_path),
                n=0,
            )
        )
    )
    return RegistrationStep(
        agent_id,
        "config-edit",
        config_path,
        None,
        None,
        new_text,
        adapter.restart_required,
        _digest_or_none(raw),
        scope="user",
        project_root=root,
        entry=entry,
        current_entry=current,
        diff=diff,
        requires_consent=changes_existing,
        unchanged=same,
    )


def _registration_result(
    step: RegistrationStep, ok: bool, error: str | None = None
) -> AgentApplyResult:
    return AgentApplyResult(
        step.agent_id,
        ok,
        step.method,
        step.config_path,
        None,
        step.restart_required,
        error=error,
    )


def _apply_config_edit(
    step: RegistrationStep, writer: Callable[..., Any], journal: WriteJournal
) -> None:
    """CAS-write a planned Codex config (parent directories undone on rollback)."""
    path = step.config_path
    if path is None or step.new_text is None:
        raise ValueError("config-edit step has no config path or text")
    current = _read_regular(path)
    actual = _digest_or_none(current)
    if actual != step.expected_sha256:
        raise CASConflictError(path, step.expected_sha256, actual)
    missing: list[Path] = []
    parent = path.parent
    while not parent.exists():
        missing.append(parent)
        parent = parent.parent
    for directory in reversed(missing):
        directory.mkdir()
    if missing:

        def remove_created_dirs() -> dict[str, Any] | None:
            for directory in missing:  # deepest first
                with suppress(OSError):
                    directory.rmdir()
            return None

        journal.record_undo(remove_created_dirs)
    data = step.new_text.encode("utf-8")
    writer(path, data, expected_sha256=step.expected_sha256, new_file_mode=0o600)
    journal.record_file("mcp_entry", path, current, _sha256(data))


def _step_entry_now(step: RegistrationStep) -> dict[str, Any] | None:
    """The `rush` entry now at the exact config path the step was planned for."""
    if step.config_path is None or step.project_root is None:
        raise ValueError("not a project registration step")
    raw = _read_regular(step.config_path)
    if step.scope == "local":
        return _claude_local_entry(raw, step.project_root)
    if raw is None:
        return None
    entry = _read_rush_entry(raw.decode("utf-8"), ADAPTERS[step.agent_id])
    return entry if isinstance(entry, dict) else None


def _apply_local_native(
    step: RegistrationStep, runner: HostRunner, journal: WriteJournal
) -> None:
    """`claude mcp add --scope local` in the project root, restoring the
    entry it replaced when the add fails."""
    assert step.native_command is not None and step.project_root is not None
    cwd = str(step.project_root)
    prefix = step.native_command[:2]
    current = _step_entry_now(step)
    actual = _entry_digest(current) if current is not None else None
    if actual != step.expected_sha256:
        raise CASConflictError(step.config_path or Path(), step.expected_sha256, actual)
    if current is not None:
        runner((*prefix, "remove", "rush", "--scope", "local"), cwd)
    try:
        runner(step.native_command, cwd)
    except HostCommandError as exc:
        if current is not None:
            restore = (*prefix, "add-json", "rush", json.dumps(current))
            try:
                runner((*restore, "--scope", "local"), cwd)
            except HostCommandError as restore_exc:
                raise HostCommandError(
                    exc.argv,
                    exc.returncode,
                    f"{exc.detail}; recovery_required: restoring the previous "
                    f"entry failed ({restore_exc.detail}); entry: {json.dumps(current)}",
                ) from exc
        raise
    written = _step_entry_now(step)

    def undo() -> dict[str, Any] | None:
        now = _step_entry_now(step)
        if now != written:
            return {
                "component": "mcp_entry",
                "path": str(step.config_path),
                "expected": _entry_digest(written) if written is not None else None,
                "actual": _entry_digest(now) if now is not None else None,
            }
        try:
            if now is not None:
                runner((*prefix, "remove", "rush", "--scope", "local"), cwd)
            if current is not None:
                runner(
                    (*prefix, "add-json", "rush", json.dumps(current))
                    + ("--scope", "local"),
                    cwd,
                )
        except HostCommandError as exc:
            return {
                "component": "mcp_entry",
                "path": str(step.config_path),
                "expected": _entry_digest(current) if current is not None else None,
                "actual": None,
                "error": exc.detail,
            }
        return None

    journal.record_undo(undo)


def _record_project_registration_locked(
    step: RegistrationStep, ledger: dict[str, dict[str, Any]]
) -> bool:
    """Record the entry the host now holds for this project; whether the ledger changed.

    A Codex entry is global, so once bound to this project the other rows
    over that same entry no longer own a binding and are dropped (their
    original digest carries over for disconnect).
    """
    assert step.project_root is not None and step.config_path is not None
    entry = _step_entry_now(step)
    if entry is None:
        return False
    config_path = step.config_path
    root = step.project_root
    entry_id = f"{step.agent_id}:mcp_entry:{config_path}:{root}"
    original = (
        _entry_digest(step.current_entry) if step.current_entry is not None else None
    )
    changed = False
    for eid, row in list(ledger.items()):
        same_entry = (
            row.get("kind") == "mcp_entry"
            and row.get("host") == step.agent_id
            and row.get("path") == str(config_path)
        )
        if not same_entry:
            continue
        if eid == entry_id:
            original = row.get("original_sha256")
        elif step.scope == "user" and row.get("scope") != "local":
            original = row.get("original_sha256")
            del ledger[eid]
            changed = True
    written = _entry_digest(entry)
    existing = ledger.get(entry_id)
    if (
        existing is not None
        and existing.get("written_sha256") == written
        and existing.get("scope") == step.scope
    ):
        return changed
    row = _ledger_entry(
        entry_id, "mcp_entry", step.agent_id, root, str(config_path), written, original
    )
    row["scope"] = step.scope
    ledger[entry_id] = row
    return True


def apply_project_registration(
    step: RegistrationStep,
    *,
    consent: bool | None = None,
    data_root: Path | None = None,
    runner: HostRunner | None = None,
    writer: Callable[..., Any] | None = None,
) -> AgentApplyResult:
    """Apply a `plan_project_registration` step. Never raises for host or I/O failures.

    A step that changes an existing `rush` entry runs only with
    `consent=True` (`False` is `declined`, `None` is `consent_required`).
    The entry (Codex: the whole config file) must still be exactly what the
    plan saw. Under the ownership-ledger lock the change is journaled, read
    back and recorded as this project's `mcp_entry` row; any failure undoes
    this call's own change while it is still Rush's and reports the rest as
    `recovery_required`.
    """
    if step.entry is None or step.project_root is None:
        return _registration_result(step, False, "not_a_project_registration")
    if step.requires_consent and consent is not True:
        return _registration_result(
            step, False, "declined" if consent is False else "consent_required"
        )
    resolved_data_root = data_root or default_data_root()
    try:
        with _ledger_lock(resolved_data_root):
            ledger, version = _load_ledger(resolved_data_root)
            journal = WriteJournal()
            try:
                if not step.unchanged and step.method == "native":
                    _apply_local_native(step, runner or run_host_command, journal)
                elif not step.unchanged:
                    _apply_config_edit(step, writer or cas_replace_file, journal)
                if _record_project_registration_locked(step, ledger):
                    _save_ledger(resolved_data_root, ledger, version)
            except (AgentConnectionError, StoreError, OSError, ValueError) as exc:
                recovery = journal.rollback()
                detail = str(exc)
                if recovery:
                    detail += f"; recovery_required: {json.dumps(recovery)}"
                return _registration_result(step, False, detail)
    except AgentConnectionError as exc:  # ledger busy or corrupt
        return _registration_result(step, False, str(exc))
    return _registration_result(step, True)


def _disconnect_local_entry(
    row: dict[str, Any], agent_id: str, config_path: Path
) -> str | dict[str, Any]:
    """Remove a project's Claude Code local-scope entry, mirroring how it was added."""
    recorded_root = row.get("project_root")
    if not isinstance(recorded_root, str) or not recorded_root:
        raise ValueError("local-scope ledger row has no project root")
    root = Path(recorded_root).resolve()
    written = row.get("written_sha256")
    current = _claude_local_entry(_read_regular(config_path), root)
    if current is None:
        return "absent"
    actual = _entry_digest(current)
    if actual != written:
        return _conflict_row("mcp_entry", str(config_path), written, actual, "changed")
    binary = shutil.which(HOST_BINARIES[agent_id])
    if binary is None:
        return _conflict_row(
            "mcp_entry",
            str(config_path),
            written,
            actual,
            f"native_remove_failed: `{HOST_BINARIES[agent_id]}` is not on PATH",
        )
    try:
        run_host_command(
            (binary, "mcp", "remove", "rush", "--scope", "local"), str(root)
        )
    except HostCommandError as exc:
        return _conflict_row(
            "mcp_entry",
            str(config_path),
            written,
            actual,
            f"native_remove_failed: {exc.detail}",
        )
    return "removed"


def host_readback_connected(agent_id: str, output: str) -> bool:
    """Whether a host's own MCP readback reports the Rush server connected.

    Only Claude Code's `mcp get` reports a live health check; Codex's
    readback shows configuration only, so it never proves a connection.
    """
    return agent_id == "claude-code" and bool(_CLAUDE_CONNECTED_RE.search(output))


def _json_documents(output: str) -> list[Any]:
    try:
        return [json.loads(output)]
    except ValueError:
        pass
    documents: list[Any] = []
    for line in output.splitlines():
        if line.strip():
            with suppress(ValueError):
                documents.append(json.loads(line))
    return documents


def _tool_result_value(value: Any) -> Any:
    """A tool result as parsed JSON when it carries a single JSON text block."""
    if isinstance(value, str):
        try:
            return json.loads(value)
        except ValueError:
            return value
    if isinstance(value, list):
        texts = [
            block.get("text")
            for block in value
            if isinstance(block, dict) and block.get("type") == "text"
        ]
        return _tool_result_value(texts[0]) if len(texts) == 1 else value
    if isinstance(value, dict) and "project" not in value:
        for key in ("structured_content", "structuredContent"):
            if isinstance(value.get(key), dict):
                return value[key]
        if "content" in value:
            return _tool_result_value(value["content"])
    return value


def _claude_blocks(document: dict[str, Any]) -> list[dict[str, Any]]:
    message = document.get("message")
    content = message.get("content") if isinstance(message, dict) else None
    return (
        [b for b in content if isinstance(b, dict)] if isinstance(content, list) else []
    )


def parse_host_tool_calls(output: str) -> list[dict[str, Any]]:
    """Every completed tool call in a host's non-interactive JSON output, as `{name, result}`.

    Reads Claude Code `--output-format stream-json` (assistant `tool_use`
    blocks joined to their `tool_result`), Codex `exec --json`
    (`mcp_tool_call` items, named `mcp__SERVER__TOOL`), and Rush's own
    normalized record `{"tool_calls": [{"name", "result"}]}`. Failed calls
    are skipped.
    """
    calls: list[dict[str, Any]] = []
    tool_names: dict[Any, Any] = {}
    for document in _json_documents(output):
        if not isinstance(document, dict):
            continue
        recorded = document.get("tool_calls")
        for call in recorded if isinstance(recorded, list) else []:
            if isinstance(call, dict) and isinstance(call.get("name"), str):
                calls.append(
                    {
                        "name": call["name"],
                        "result": _tool_result_value(call.get("result")),
                    }
                )
        item = document.get("item")
        if (
            document.get("type") == "item.completed"
            and isinstance(item, dict)
            and item.get("type") == "mcp_tool_call"
            and item.get("status", "completed") == "completed"
        ):
            calls.append(
                {
                    "name": f"mcp__{item.get('server')}__{item.get('tool')}",
                    "result": _tool_result_value(item.get("result")),
                }
            )
        for block in _claude_blocks(document):
            if block.get("type") == "tool_use":
                tool_names[block.get("id")] = block.get("name")
            elif (
                block.get("type") == "tool_result"
                and block.get("tool_use_id") in tool_names
                and not block.get("is_error")
            ):
                calls.append(
                    {
                        "name": tool_names[block["tool_use_id"]],
                        "result": _tool_result_value(block.get("content")),
                    }
                )
    return calls


def observed_status_project_ids(calls: list[dict[str, Any]]) -> list[str]:
    """Project ids reported by observed Rush `rush_status` calls (never another server's)."""
    ids: list[str] = []
    for call in calls:
        name = str(call.get("name"))
        if name != "rush_status" and name != "mcp__rush__rush_status":
            continue
        result = call.get("result")
        candidates = (result, result.get("raw") if isinstance(result, dict) else None)
        for node in candidates:
            project = node.get("project") if isinstance(node, dict) else None
            project_id = (
                project.get("project_id") if isinstance(project, dict) else None
            )
            if isinstance(project_id, str):
                ids.append(project_id)
                break
    return ids


__all__ = [
    "ADAPTERS",
    "CORE_SERVE_ARGS",
    "HOST_BINARIES",
    "HOST_LOGIN_ACTIONS",
    "HOST_PROBE_ARGS",
    "HOST_READBACK_ARGS",
    "INSTRUCTION_TARGETS",
    "LEGACY_SERVE_ARGS",
    "MCP_PROFILES",
    "PLUGIN_HOSTS",
    "PLUGIN_ID",
    "PLUGIN_MARKETPLACE",
    "AgentAdapter",
    "AgentApplyResult",
    "AgentConnectionError",
    "AgentDisconnectResult",
    "AgentInstructionApplyResult",
    "AgentInstructionPlan",
    "AgentStatus",
    "AgentTransactionError",
    "CASConflictError",
    "GuidanceConsent",
    "HostCommandError",
    "LedgerBusyError",
    "LedgerCorruptError",
    "MalformedConfigError",
    "ManualEntryRemoval",
    "OwnedResource",
    "ProfileConsent",
    "ReadOnlyConfigError",
    "RegistrationProfile",
    "RegistrationStep",
    "UnknownAgentError",
    "WriteJournal",
    "acknowledge_agent_connection",
    "agent_memory_store_path",
    "agent_readiness",
    "apply_agent_instructions",
    "apply_agent_registration",
    "apply_project_registration",
    "build_stdio_entry",
    "cas_replace_file",
    "cas_unlink",
    "classify_registration_profile",
    "connect_agent",
    "disconnect_agent",
    "discover_agents",
    "finalize_agent_plugin_upgrade",
    "host_readback_connected",
    "initialize_agent_memory",
    "installed_plugin_roots",
    "materialize_agent_plugins",
    "observed_status_project_ids",
    "owned_path_digest",
    "ownership_ledger_path",
    "parse_host_tool_calls",
    "plan_agent_instructions",
    "plan_agent_registration",
    "plan_manual_entry_removal",
    "plan_project_registration",
    "plugin_uninstall_commands",
    "probe_agent_connection",
    "profile_serve_args",
    "project_serve_args",
    "project_session_id",
    "read_agent_memory_state",
    "read_project_registration_entry",
    "read_registration_entry",
    "reconcile_agent_instructions",
    "record_native_plugin_install",
    "record_tool_observation",
    "registration_preview",
    "registration_undo",
    "resolve_rush_binary",
    "run_host_command",
    "same_server_entry",
]
