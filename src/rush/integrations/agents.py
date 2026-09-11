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

import json
import os
import platform
import shutil
import subprocess
import time
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from rush.memory.transactions import CASMapTransaction
from rush.runtime.filesystem import atomic_write_bytes
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


def build_stdio_entry(
    rush_binary: str, *, args: tuple[str, ...] = ("mcp", "serve")
) -> dict[str, Any]:
    """Generic stdio MCP server spec shared by every adapter."""
    return {"command": rush_binary, "args": list(args)}


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

    def to_dict(self) -> dict[str, Any]:
        return {
            "agent_id": self.agent_id,
            "display_name": self.display_name,
            "detected": self.detected,
            "config_path": str(self.config_path) if self.config_path else None,
            "status": self.status,
            "restart_required": self.restart_required,
            "error": self.error,
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


@dataclass(frozen=True)
class AgentApplyResult:
    agent_id: str
    ok: bool
    method: Literal["native", "config-edit"]
    config_path: Path | None
    backup_path: Path | None
    restart_required: bool
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "agent_id": self.agent_id,
            "ok": self.ok,
            "method": self.method,
            "config_path": str(self.config_path) if self.config_path else None,
            "backup_path": str(self.backup_path) if self.backup_path else None,
            "restart_required": self.restart_required,
            "error": self.error,
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
) -> RegistrationStep:
    """Plan how to register Rush with one agent, never writing anything yet."""
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
        command = (
            adapter.native_binary,
            "mcp",
            "add",
            "rush",
            "--scope",
            "user",
            "--",
            rush_binary,
            "mcp",
            "serve",
        )
        return RegistrationStep(
            agent_id,
            "native",
            resolved_path,
            None,
            command,
            None,
            adapter.restart_required,
        )

    existing_text = (
        resolved_path.read_text(encoding="utf-8")
        if resolved_path.exists()
        else _default_document(adapter)
    )
    if resolved_path.exists() and not os.access(resolved_path, os.W_OK):
        raise ReadOnlyConfigError(f"{agent_id}: config is read-only: {resolved_path}")

    entry = build_stdio_entry(rush_binary)
    if adapter.config_format == "toml":
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
    )


def apply_agent_registration(step: RegistrationStep) -> AgentApplyResult:
    """Apply a previously built plan. Never raises -- failures come back as `ok=False`."""
    if step.method == "native":
        assert step.native_command is not None
        remove_command = step.native_command[:2] + ("remove", "rush", "--scope", "user")
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
    try:
        step.config_path.parent.mkdir(parents=True, exist_ok=True)
        if step.config_path.exists() and step.backup_path is not None:
            shutil.copy2(step.config_path, step.backup_path)
        atomic_write_bytes(
            step.config_path.parent,
            step.config_path.name,
            step.new_text.encode("utf-8"),
        )
    except OSError as exc:
        return AgentApplyResult(
            step.agent_id,
            False,
            step.method,
            step.config_path,
            step.backup_path,
            step.restart_required,
            error=str(exc),
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


__all__ = [
    "ADAPTERS",
    "AgentAdapter",
    "AgentApplyResult",
    "AgentConnectionError",
    "AgentStatus",
    "MalformedConfigError",
    "ReadOnlyConfigError",
    "RegistrationStep",
    "UnknownAgentError",
    "acknowledge_agent_connection",
    "agent_memory_store_path",
    "agent_readiness",
    "apply_agent_registration",
    "build_stdio_entry",
    "discover_agents",
    "initialize_agent_memory",
    "plan_agent_registration",
    "probe_agent_connection",
    "read_agent_memory_state",
    "record_tool_observation",
    "resolve_rush_binary",
]
