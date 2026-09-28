"""Project registry: one project/discovery/readiness model (Phase 65 P65-03, F32-33).

Shared by CLI, MCP, and TUI so every interface sees the same registered
projects, the same identity rules, and the same readiness computation.

Identity: `project_id` is a durable UUID tied to a project's canonical
physical root (symlinks resolved). Two worktrees have distinct roots and get
distinct IDs; reopening the same root (directly or through a symlink alias)
returns the existing ID. A moved root requires an explicit `relink_project`
call with an identity check, never silent re-registration under a new ID.

Readiness is three independent facts, not one enum:
  - installed:  the project is registered AND its root currently exists.
  - applicable: the root currently has at least one detectable language/stack.
  - ready:      installed AND applicable AND `configure_project` has run.
A brand-new empty project is installed but neither applicable nor ready.

Frozen contract (docs/phase-plans/phase-65-project-provisioning-scan-and-
agent-workflow-plan.md §6.1, "P65-03 owns registry/envelope tests"):
  - Every registry entry carries an integer `revision`, incremented on every
    successful mutation. `relink_project`/`configure_project` (apply) take
    `expected_revision` and compare it under a real file lock; a stale value
    raises `ProjectRevisionConflictError`, a lock-acquisition timeout raises
    `ProjectBusyError`. Never silently overwrite a concurrent update.
  - `configure_project` has a preview mode (returns a canonical SHA256
    `plan_id` over the proposed settings) and an apply mode (`plan_id` +
    `expected_revision` required; a stale/wrong plan raises
    `ProjectPlanStaleError`).
  - `list_projects_page` implements the mandatory HMAC-signed cursor
    (`cursor.key` in user data, created by `ensure_cursor_key` during
    authorized global setup -- never created from this query path).
"""

from __future__ import annotations

import base64
import copy
import hashlib
import hmac
import json
import os
import re
import sqlite3
import stat
import subprocess
import threading
import time
import uuid
from collections.abc import Iterator, Mapping
from contextlib import contextmanager, suppress
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, ClassVar

from rush.config import load_config
from rush.io.physical_paths import ContainmentError, PhysicalRoot
from rush.memory.store import (
    MemoryStoreUnreadableError,
    is_internal_memory_source,
    read_sqlite_readonly,
    readonly_view_reason,
    sqlite_has_table,
)
from rush.review.collection import SKIP_DIRS
from rush.runtime.filesystem import atomic_write_bytes
from rush.setup.provision import default_data_root
from rush.token_economy.telemetry import read_summary_readonly
from rush.tools.routing import detect_project_languages

REGISTRY_FILE = "projects.json"
SESSION_SELECTION_FILE = "session_projects.json"
REGISTRY_LOCK_FILE = "projects.json.lock"
CURSOR_KEY_FILE = "cursor.key"
DESCRIPTOR_RELATIVE_PATH = ".rush/project.json"

_LOCK_STALE_SECONDS = 30.0
_LOCK_POLL_SECONDS = 0.02

_SETTINGS_KEYS = frozenset(
    {
        "exclude_tools",
        "severity",
        "concurrency",
        "timeout_seconds",
        "memory_record",
        "agent_ids",
    }
)


class ProjectError(Exception):
    """Base error for project registry operations. Defaults to INVALID_REQUEST."""

    code: ClassVar[str] = "INVALID_REQUEST"
    retryable: ClassVar[bool] = False


class ProjectNotFoundError(ProjectError):
    """Raised when a project id or path cannot be resolved to a registered project."""

    code = "PROJECT_NOT_FOUND"


class ProjectDestinationExistsError(ProjectError):
    """Raised when project creation targets an already-occupied destination."""

    code = "PROJECT_DESTINATION_EXISTS"


class ProjectRootMissingError(ProjectError):
    """Raised when a physical root required by an operation does not exist."""

    code = "PROJECT_ROOT_MISSING"


class ProjectRootConflictError(ProjectError):
    """Raised when a root/identity already belongs to a different project."""

    code = "PROJECT_ROOT_CONFLICT"


class ProjectRevisionConflictError(ProjectError):
    """Raised when `expected_revision` no longer matches the registry."""

    code = "REVISION_CONFLICT"


class ProjectBusyError(ProjectError):
    """Raised when the registry lock cannot be acquired before the timeout."""

    code = "BUSY"
    retryable = True


class ProjectPlanStaleError(ProjectError):
    """Raised when a configure `plan_id` no longer matches the given settings."""

    code = "PLAN_STALE"


class ProjectRequiredError(ProjectError):
    """Raised when no project argument and no interface-bound selection exist."""

    code = "PROJECT_REQUIRED"


class ProjectSetupRequiredError(ProjectError):
    """Raised when the cursor signing key has not been created yet."""

    code = "SETUP_REQUIRED"


class ProjectInvalidCursorError(ProjectError):
    """Raised when a pagination cursor is tampered, stale, or unverifiable."""

    code = "INVALID_CURSOR"


class ProjectInvalidRequestError(ProjectError):
    """Raised for malformed input rejected before any effect."""

    code = "INVALID_REQUEST"


class ProjectRegistryCorruptError(ProjectError):
    """Raised when a mutation would have to overwrite a corrupt or unreadable
    registry file. Carries the path and the SHA-256 of the bytes on disk; the
    file is never rewritten."""

    code = "REGISTRY_CORRUPT"

    def __init__(self, message: str, *, path: str, sha256: str | None) -> None:
        super().__init__(message)
        self.path = path
        self.sha256 = sha256


@dataclass(frozen=True)
class ProjectRecord:
    project_id: str
    root: str
    name: str
    created_at: str
    configured: bool = False
    revision: int = 1

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _canonical_root(path: Path | str) -> Path:
    """Resolve a path to its real, symlink-free canonical directory."""
    return Path(path).expanduser().resolve()


def _registry_path(data_root: Path) -> Path:
    return data_root / REGISTRY_FILE


def _canonical_json(value: Any) -> bytes:
    """Canonical JSON: sorted keys, compact separators, UTF-8 (plan §6.1)."""
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")


@contextmanager
def _registry_lock(data_root: Path, *, timeout: float = 5.0) -> Iterator[None]:
    """Real mutual exclusion over the registry file via an O_EXCL lock file.

    A lock file older than `_LOCK_STALE_SECONDS` is treated as abandoned by a
    crashed holder and reclaimed immediately, without consuming the caller's
    own timeout budget.
    """
    data_root.mkdir(parents=True, exist_ok=True)
    lock_path = data_root / REGISTRY_LOCK_FILE
    start = time.monotonic()
    fd: int | None = None
    while fd is None:
        try:
            fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError:
            try:
                if time.time() - lock_path.stat().st_mtime > _LOCK_STALE_SECONDS:
                    lock_path.unlink(missing_ok=True)
                    continue
            except OSError:
                pass
            if time.monotonic() - start >= timeout:
                raise ProjectBusyError(
                    f"timed out after {timeout}s waiting for the project registry lock"
                ) from None
            time.sleep(_LOCK_POLL_SECONDS)
    try:
        yield
    finally:
        os.close(fd)
        with suppress(OSError):
            lock_path.unlink()


def _load_registry(data_root: Path) -> dict[str, Any]:
    path = _registry_path(data_root)
    if not path.is_file():
        return {"version": 1, "projects": {}}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"version": 1, "projects": {}}
    if not isinstance(payload, dict) or not isinstance(payload.get("projects"), dict):
        return {"version": 1, "projects": {}}
    return payload


def _read_json_state(path: Path, valid: Any) -> tuple[str, Any, str | None, str | None]:
    """Read-only JSON load reporting `(state, payload, error, sha256)`.

    `state` is `missing` (no file), `unreadable` (the file exists but cannot
    be read), `corrupt` (not JSON, or not the shape `valid` accepts), or
    `ok`. Never creates a directory or file.
    """
    try:
        raw = path.read_bytes()
    except FileNotFoundError:
        return "missing", None, None, None
    except OSError as exc:
        return "unreadable", None, str(exc), None
    digest = hashlib.sha256(raw).hexdigest()
    try:
        payload = json.loads(raw)
    except ValueError as exc:
        return "corrupt", None, str(exc), digest
    if not valid(payload):
        return "corrupt", None, "unexpected JSON shape", digest
    return "ok", payload, None, digest


def _strict_result(
    key: str, path: Path, state: tuple[str, Any, str | None, str | None]
) -> dict[str, Any]:
    status, payload, error, digest = state
    return {
        "state": status,
        key: payload,
        "path": str(path),
        "error": error,
        "sha256": digest,
    }


def read_registry_strict(data_root: Path) -> dict[str, Any]:
    """Read-only registry load that tells missing, ok, corrupt and unreadable
    apart (the tolerant `_load_registry` maps all failures to empty)."""
    path = _registry_path(data_root)
    state = _read_json_state(
        path,
        lambda p: isinstance(p, dict) and isinstance(p.get("projects"), dict),
    )
    return _strict_result("registry", path, state)


@dataclass(frozen=True)
class RegistryState:
    """T23: typed `read_registry_strict` result (`missing|ok|corrupt|unreadable`)."""

    state: str
    path: str
    registry: dict[str, Any] | None
    error: str | None
    sha256: str | None


def read_registry_state(data_root: Path) -> RegistryState:
    """T23: `read_registry_strict` as a `RegistryState`; never creates `data_root`."""
    result = read_registry_strict(data_root)
    return RegistryState(
        result["state"],
        result["path"],
        result["registry"],
        result["error"],
        result["sha256"],
    )


def read_session_selections_strict(data_root: Path) -> dict[str, Any]:
    """Read-only session-selection load with the same four states."""
    path = _session_selection_path(data_root)
    state = _read_json_state(path, lambda p: isinstance(p, dict))
    return _strict_result("selections", path, state)


def read_descriptor_strict(root: Path) -> dict[str, Any]:
    """Read-only `.rush/project.json` load with the same four states."""
    path = root / DESCRIPTOR_RELATIVE_PATH
    state = _read_json_state(path, lambda p: isinstance(p, dict))
    return _strict_result("descriptor", path, state)


def _raise_if_unusable(result: dict[str, Any], what: str) -> None:
    if result["state"] in ("corrupt", "unreadable"):
        raise ProjectRegistryCorruptError(
            f"{what} at {result['path']} is {result['state']} "
            f"({result['error']}); refusing to overwrite it",
            path=result["path"],
            sha256=result["sha256"],
        )


def _load_registry_for_mutation(data_root: Path) -> dict[str, Any]:
    """Strict load used by mutations: a corrupt or unreadable registry raises
    `ProjectRegistryCorruptError` instead of being replaced by an empty one."""
    result = read_registry_strict(data_root)
    _raise_if_unusable(result, "project registry")
    registry: dict[str, Any] = result["registry"] or {"version": 1, "projects": {}}
    return registry


def _save_registry(data_root: Path, registry: dict[str, Any]) -> None:
    payload = json.dumps(registry, indent=2, sort_keys=True).encode("utf-8") + b"\n"
    atomic_write_bytes(data_root, REGISTRY_FILE, payload)


def _read_descriptor(root: Path) -> dict[str, Any] | None:
    descriptor = root / DESCRIPTOR_RELATIVE_PATH
    if not descriptor.is_file():
        return None
    try:
        payload = json.loads(descriptor.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return payload if isinstance(payload, dict) else None


def _write_project_descriptor(root: Path, record: ProjectRecord) -> None:
    """Store the project descriptor under `.rush/`. Only called from an
    explicit add/create/relink -- read-only discovery never calls this."""
    atomic_write_bytes(root, DESCRIPTOR_RELATIVE_PATH, _descriptor_bytes(record))


def _project_view(project_id: str, entry: dict[str, Any]) -> dict[str, Any]:
    root = Path(entry["root"])
    exists = root.is_dir()
    languages: list[str] = []
    if exists:
        # Config is still loaded so an invalid rush.toml fails the view
        # closed; the languages are exactly what `inspect_capabilities`
        # reports, without its per-tool engine PATH scan.
        load_config(start=root)
        languages = detect_project_languages(root)
    installed = exists
    applicable = bool(languages)
    configured = bool(entry.get("configured", False))
    return {
        "project_id": project_id,
        "root": entry["root"],
        "name": entry.get("name", root.name),
        "created_at": entry.get("created_at"),
        "revision": int(entry.get("revision", 1)),
        "configured": configured,
        "exists": exists,
        "languages": languages,
        "settings": entry.get("settings", {}),
        "readiness": {
            "installed": installed,
            "applicable": applicable,
            "ready": installed and applicable and configured,
        },
    }


def register_project(
    path: Path | str,
    *,
    name: str | None = None,
    data_root: Path | None = None,
    lock_timeout: float = 5.0,
    expect_new: bool = False,
) -> ProjectRecord:
    """Register an existing folder as a Rush project.

    Idempotent by canonical physical root: registering the same root twice
    (directly or through a symlink alias) returns the same project_id and
    never writes a duplicate registry entry. With `expect_new=True` (a
    reviewed setup that previewed "new"), an existing entry for the root
    raises `ProjectRevisionConflictError` instead. A corrupt or unreadable
    registry raises `ProjectRegistryCorruptError` and is never overwritten.
    If the descriptor write fails after the registry save, the new entry is
    removed again under the same lock before the error propagates.
    """
    data_root = data_root or default_data_root()
    root = _canonical_root(path)
    if not root.is_dir():
        raise ProjectRootMissingError(f"not a directory: {root}")

    with _registry_lock(data_root, timeout=lock_timeout):
        registry = _load_registry_for_mutation(data_root)
        projects: dict[str, Any] = registry["projects"]
        root_str = str(root)

        for project_id, entry in projects.items():
            if entry.get("root") == root_str:
                if expect_new:
                    raise ProjectRevisionConflictError(
                        f"root already registered as {project_id}"
                    )
                return ProjectRecord(
                    project_id=project_id,
                    root=entry["root"],
                    name=entry.get("name", root.name),
                    created_at=entry.get("created_at", ""),
                    configured=bool(entry.get("configured", False)),
                    revision=int(entry.get("revision", 1)),
                )

        descriptor = _read_descriptor(root)
        descriptor_id = descriptor.get("project_id") if descriptor else None
        project_id = (
            descriptor_id
            if isinstance(descriptor_id, str) and descriptor_id not in projects
            else str(uuid.uuid4())
        )

        record = ProjectRecord(
            project_id=project_id,
            root=root_str,
            name=name or root.name,
            created_at=datetime.now(UTC).isoformat(),
        )
        projects[project_id] = record.to_dict()
        _save_registry(data_root, registry)
        try:
            _write_project_descriptor(root, record)
        except Exception:
            del projects[project_id]
            _save_registry(data_root, registry)
            raise
        return record


def _descriptor_bytes(record: ProjectRecord) -> bytes:
    return (
        json.dumps(record.to_dict(), indent=2, sort_keys=True).encode("utf-8") + b"\n"
    )


def unregister_project(
    project_id: str,
    *,
    expected_revision: int,
    data_root: Path | None = None,
    lock_timeout: float = 5.0,
) -> None:
    """Compensation for a failed setup: remove one registry entry only while
    its revision still equals `expected_revision` (else
    `ProjectRevisionConflictError`, entry kept). The root's descriptor is
    removed only when its bytes still equal the descriptor that the original
    registration wrote."""
    data_root = data_root or default_data_root()
    with _registry_lock(data_root, timeout=lock_timeout):
        registry = _load_registry_for_mutation(data_root)
        entry = registry["projects"].get(project_id)
        if entry is None:
            return
        current = int(entry.get("revision", 1))
        if current != expected_revision:
            raise ProjectRevisionConflictError(
                f"expected revision {expected_revision}, registry is at {current}"
            )
        del registry["projects"][project_id]
        _save_registry(data_root, registry)
    original = ProjectRecord(
        project_id=project_id,
        root=entry["root"],
        name=entry.get("name", Path(entry["root"]).name),
        created_at=entry.get("created_at", ""),
    )
    descriptor = Path(entry["root"]) / DESCRIPTOR_RELATIVE_PATH
    with suppress(OSError):
        if descriptor.read_bytes() == _descriptor_bytes(original):
            descriptor.unlink()


def list_projects(*, data_root: Path | None = None) -> list[dict[str, Any]]:
    """Return every registered project. Empty registry returns `[]`."""
    data_root = data_root or default_data_root()
    registry = _load_registry(data_root)
    return [
        _project_view(project_id, entry)
        for project_id, entry in sorted(registry["projects"].items())
    ]


def _read_cursor_key(data_root: Path) -> bytes | None:
    path = data_root / CURSOR_KEY_FILE
    if not path.is_file():
        return None
    try:
        data = path.read_bytes()
    except OSError:
        return None
    return data if len(data) == 32 else None


def ensure_cursor_key(data_root: Path | None = None) -> bytes:
    """Create (or return) the 32-byte cursor-signing key with owner-only
    permissions. Called only during authorized global setup -- never from a
    query path (plan §6.1: "Query paths never silently create the key")."""
    data_root = data_root or default_data_root()
    existing = _read_cursor_key(data_root)
    if existing is not None:
        return existing
    key = os.urandom(32)
    path = atomic_write_bytes(data_root, CURSOR_KEY_FILE, key)
    os.chmod(path, 0o600)
    return key


def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64url_decode(data: str) -> bytes:
    padding = "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(data + padding)


def _encode_cursor(key: bytes, payload: dict[str, Any]) -> str:
    payload_bytes = _canonical_json(payload)
    signature = hmac.new(key, payload_bytes, hashlib.sha256).digest()
    return f"{_b64url_encode(payload_bytes)}.{_b64url_encode(signature)}"


def _decode_cursor(key: bytes, cursor: str) -> dict[str, Any] | None:
    if "." not in cursor:
        return None
    payload_part, _, sig_part = cursor.partition(".")
    try:
        payload_bytes = _b64url_decode(payload_part)
        signature = _b64url_decode(sig_part)
    except (ValueError, Exception):  # noqa: BLE001 - any malformed base64 rejects
        return None
    expected = hmac.new(key, payload_bytes, hashlib.sha256).digest()
    if not hmac.compare_digest(signature, expected):
        return None
    try:
        payload = json.loads(payload_bytes)
    except ValueError:
        return None
    return payload if isinstance(payload, dict) else None


def list_projects_page(
    *,
    limit: int = 50,
    cursor: str | None = None,
    data_root: Path | None = None,
) -> dict[str, Any]:
    """Paginated, HMAC-cursor-authenticated project listing (plan §6.1).

    Ordering is `(created_at, id)` ascending; pagination range is 1-200.
    Cursor authentication is mandatory: a missing signing key raises
    `ProjectSetupRequiredError` and a tampered/stale/mismatched cursor raises
    `ProjectInvalidCursorError`.
    """
    data_root = data_root or default_data_root()
    if not isinstance(limit, int) or isinstance(limit, bool) or not (1 <= limit <= 200):
        raise ProjectInvalidRequestError("limit must be an integer in 1..200")

    key = _read_cursor_key(data_root)
    if key is None:
        raise ProjectSetupRequiredError(
            "cursor signing key missing; run global setup first"
        )

    query_hash = hashlib.sha256(_canonical_json({"limit": limit})).hexdigest()

    after: tuple[str, str] | None = None
    if cursor is not None:
        payload = _decode_cursor(key, cursor)
        if (
            payload is None
            or payload.get("schema_version") != 1
            or payload.get("query_hash") != query_hash
            or payload.get("project_id") is not None
        ):
            raise ProjectInvalidCursorError(
                "cursor is stale or does not match this query"
            )
        last_created_at = payload.get("last_created_at")
        last_id = payload.get("last_id")
        if not isinstance(last_created_at, str) or not isinstance(last_id, str):
            raise ProjectInvalidCursorError("cursor payload is malformed")
        after = (last_created_at, last_id)

    registry = _load_registry(data_root)
    items = sorted(
        registry["projects"].items(),
        key=lambda pair: (pair[1].get("created_at", ""), pair[0]),
    )

    if after is not None:
        items = [
            (pid, entry)
            for pid, entry in items
            if (entry.get("created_at", ""), pid) > after
        ]

    page = items[:limit]
    has_more = len(items) > limit

    next_cursor: str | None = None
    if has_more:
        last_id, last_entry = page[-1]
        next_cursor = _encode_cursor(
            key,
            {
                "schema_version": 1,
                "project_id": None,
                "query_hash": query_hash,
                "last_created_at": last_entry.get("created_at", ""),
                "last_id": last_id,
            },
        )

    return {
        "projects": [_project_view(pid, entry) for pid, entry in page],
        "next_cursor": next_cursor,
    }


def resolve_project(
    identifier: str | Path, *, data_root: Path | None = None
) -> dict[str, Any]:
    """Resolve a project by ID, or by a path matching a registered canonical root."""
    data_root = data_root or default_data_root()
    registry = _load_registry(data_root)
    projects = registry["projects"]
    ident_str = str(identifier)
    if ident_str in projects:
        return _project_view(ident_str, projects[ident_str])

    candidate_root = str(_canonical_root(identifier))
    for project_id, entry in projects.items():
        if entry.get("root") == candidate_root:
            return _project_view(project_id, entry)

    raise ProjectNotFoundError(f"no registered project matches: {identifier}")


def resolve_active_project(
    project: str | Path | None,
    *,
    session_id: str | None = None,
    data_root: Path | None = None,
) -> dict[str, Any]:
    """Resolve an explicit `project` (ID or path), or fall back to the
    session-bound selection. Raises `ProjectRequiredError` when neither
    resolves (plan §6.1: "no project argument and no interface-bound
    selection returns PROJECT_REQUIRED")."""
    data_root = data_root or default_data_root()
    if project is not None:
        return resolve_project(project, data_root=data_root)
    if session_id is not None:
        selected = get_selected_project(session_id, data_root=data_root)
        if selected is not None:
            return selected
    raise ProjectRequiredError("no project argument and no interface-bound selection")


def create_project(
    parent: Path | str,
    name: str,
    *,
    init_git: bool = False,
    data_root: Path | None = None,
) -> ProjectRecord:
    """Create a named folder at a user-selected parent and register it.

    Refuses an occupied destination. Never writes anything into the new
    folder beyond the `.rush/` project descriptor and (if explicitly
    requested) `git init` -- no application scaffold. On any failure after
    the folder is created, removes only that empty folder, never existing
    content (``rmdir`` is a no-op error on a non-empty directory).
    """
    parent_root = _canonical_root(parent)
    if not parent_root.is_dir():
        raise ProjectRootMissingError(f"parent is not a directory: {parent_root}")

    destination = parent_root / name
    try:
        destination.mkdir(parents=False)
    except FileExistsError as exc:
        raise ProjectDestinationExistsError(
            f"destination already exists: {destination}"
        ) from exc

    try:
        if init_git:
            subprocess.run(
                ["git", "init", "--quiet", str(destination)],
                check=True,
                capture_output=True,
            )
        return register_project(destination, name=name, data_root=data_root)
    except Exception:
        try:
            destination.rmdir()
        except OSError:
            pass
        raise


def _session_selection_path(data_root: Path) -> Path:
    return data_root / SESSION_SELECTION_FILE


def _load_session_selections(data_root: Path) -> dict[str, str]:
    path = _session_selection_path(data_root)
    if not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    if not isinstance(payload, dict):
        return {}
    return {k: v for k, v in payload.items() if isinstance(v, str)}


def select_project(
    session_id: str, project_id: str, *, data_root: Path | None = None
) -> dict[str, Any]:
    """Bind a project to one interface/session, never a global cwd."""
    data_root = data_root or default_data_root()
    registry = _load_registry_for_mutation(data_root)
    projects = registry["projects"]
    if project_id not in projects:
        raise ProjectNotFoundError(f"no registered project: {project_id}")

    selection_state = read_session_selections_strict(data_root)
    _raise_if_unusable(selection_state, "session selection file")
    selections = {
        k: v
        for k, v in (selection_state["selections"] or {}).items()
        if isinstance(v, str)
    }
    selections[session_id] = project_id
    atomic_write_bytes(
        data_root,
        SESSION_SELECTION_FILE,
        json.dumps(selections, indent=2, sort_keys=True).encode("utf-8") + b"\n",
    )
    return _project_view(project_id, projects[project_id])


def get_selected_project(
    session_id: str, *, data_root: Path | None = None
) -> dict[str, Any] | None:
    """Return the project bound to this session, or None if unselected/stale."""
    data_root = data_root or default_data_root()
    project_id = _load_session_selections(data_root).get(session_id)
    if project_id is None:
        return None
    try:
        return resolve_project(project_id, data_root=data_root)
    except ProjectNotFoundError:
        return None


def _validate_settings(settings: dict[str, Any] | None) -> dict[str, Any]:
    if settings is None:
        return {}
    if not isinstance(settings, dict):
        raise ProjectInvalidRequestError("settings must be an object")
    unknown = set(settings) - _SETTINGS_KEYS
    if unknown:
        raise ProjectInvalidRequestError(f"unknown settings keys: {sorted(unknown)}")
    # T6: strict types, no `int()` coercion (`"3"` and `True` are rejected).
    for key, maximum in (("concurrency", 8), ("timeout_seconds", 3600)):
        if key not in settings:
            continue
        value = settings[key]
        if type(value) is not int:
            raise ProjectInvalidRequestError(f"{key} must be an integer")
        if not 1 <= value <= maximum:
            raise ProjectInvalidRequestError(f"{key} out of range 1-{maximum}")
    if "severity" in settings and settings["severity"] not in ("info", "warn", "error"):
        raise ProjectInvalidRequestError("severity must be info|warn|error")
    if "memory_record" in settings and not isinstance(settings["memory_record"], bool):
        raise ProjectInvalidRequestError("memory_record must be a boolean")
    for key in ("exclude_tools", "agent_ids"):
        if key in settings and not (
            isinstance(settings[key], list)
            and all(isinstance(item, str) for item in settings[key])
        ):
            raise ProjectInvalidRequestError(f"{key} must be a list of strings")
    return settings


def compute_settings_plan_id(settings: dict[str, Any]) -> str:
    """Canonical SHA256 plan_id over the proposed settings (plan §6.1)."""
    return hashlib.sha256(_canonical_json(settings)).hexdigest()


def configure_project(
    project_id: str,
    settings: dict[str, Any] | None = None,
    *,
    expected_revision: int | None = None,
    apply: bool = False,
    plan_id: str | None = None,
    data_root: Path | None = None,
    lock_timeout: float = 5.0,
) -> dict[str, Any]:
    """Preview or apply one project's own scan/memory/agent settings.

    Preview (default, `apply=False`): read-only, returns an immutable plan
    `{project_id, plan_id, settings}` with a canonical SHA256 `plan_id`.
    Apply (`apply=True`): requires that exact `plan_id` plus the current
    `expected_revision`; a stale/wrong plan raises `ProjectPlanStaleError`,
    a stale revision raises `ProjectRevisionConflictError`. Settings are
    isolated per project_id -- configuring one project never changes
    another project's stored settings.
    """
    data_root = data_root or default_data_root()
    validated = _validate_settings(settings)

    if not apply:
        registry = _load_registry_for_mutation(data_root)
        if project_id not in registry["projects"]:
            raise ProjectNotFoundError(f"no registered project: {project_id}")
        return {
            "project_id": project_id,
            "plan_id": compute_settings_plan_id(validated),
            "settings": validated,
        }

    if plan_id is None or expected_revision is None:
        raise ProjectInvalidRequestError("apply requires plan_id and expected_revision")

    with _registry_lock(data_root, timeout=lock_timeout):
        registry = _load_registry_for_mutation(data_root)
        projects = registry["projects"]
        if project_id not in projects:
            raise ProjectNotFoundError(f"no registered project: {project_id}")
        entry = projects[project_id]
        current_revision = int(entry.get("revision", 1))
        if expected_revision != current_revision:
            raise ProjectRevisionConflictError(
                f"expected revision {expected_revision}, registry is at "
                f"{current_revision}"
            )

        recomputed = compute_settings_plan_id(validated)
        if recomputed != plan_id:
            raise ProjectPlanStaleError("plan_id does not match current settings")

        existing = entry.get("settings")
        merged = {**(existing if isinstance(existing, dict) else {}), **validated}
        entry["settings"] = merged
        entry["configured"] = True
        entry["revision"] = current_revision + 1
        _save_registry(data_root, registry)
        return _project_view(project_id, entry)


def relink_project(
    project_id: str,
    new_path: Path | str,
    *,
    expected_revision: int,
    data_root: Path | None = None,
    lock_timeout: float = 5.0,
) -> dict[str, Any]:
    """Explicitly repoint a registered project at its new root after a move.

    Requires the caller's `expected_revision` to match the registry's
    current revision (else `ProjectRevisionConflictError`). Refuses to
    relink onto a root already registered under a different project, and
    onto a folder whose own `.rush/project.json` already claims a different
    project_id (identity check against filesystem escape/alias).
    """
    data_root = data_root or default_data_root()
    new_root = _canonical_root(new_path)
    if not new_root.is_dir():
        raise ProjectRootMissingError(f"not a directory: {new_root}")

    with _registry_lock(data_root, timeout=lock_timeout):
        registry = _load_registry(data_root)
        projects = registry["projects"]
        if project_id not in projects:
            raise ProjectNotFoundError(f"no registered project: {project_id}")
        entry = projects[project_id]
        current_revision = int(entry.get("revision", 1))
        if expected_revision != current_revision:
            raise ProjectRevisionConflictError(
                f"expected revision {expected_revision}, registry is at "
                f"{current_revision}"
            )

        new_root_str = str(new_root)
        for other_id, other_entry in projects.items():
            if other_id != project_id and other_entry.get("root") == new_root_str:
                raise ProjectRootConflictError(
                    f"root already registered under a different project: {other_id}"
                )

        descriptor = _read_descriptor(new_root)
        descriptor_id = descriptor.get("project_id") if descriptor else None
        if descriptor_id is not None and descriptor_id != project_id:
            raise ProjectRootConflictError(
                "identity mismatch: target folder already belongs to a different "
                "project"
            )

        entry["root"] = new_root_str
        entry["revision"] = current_revision + 1
        _save_registry(data_root, registry)
        record = ProjectRecord(
            project_id=project_id,
            root=new_root_str,
            name=entry.get("name", new_root.name),
            created_at=entry.get("created_at", datetime.now(UTC).isoformat()),
            configured=bool(entry.get("configured", False)),
            revision=entry["revision"],
        )
        _write_project_descriptor(new_root, record)
        return _project_view(project_id, entry)


def _iter_run_manifests(root: Path) -> list[dict[str, Any]]:
    """Every persisted run's *latest* (highest-generation) attempt manifest under `root`
    (plan §6.1 layout: `.rush/runs/<run_id>/attempts/<attempt_id>/manifest.json`), oldest
    run first. P69-03r: uses the shared `_highest_generation_attempt_dir()` selector
    (`project_run.py`, P69-02k) rather than this function's own independent
    `sorted(attempts)[-1]` UUID-lexicographic guess -- the third, identical drift point the
    plan's own P69-02k fix already warned about. A lazy, function-local import breaks the
    circular-import edge: `project_run.py` imports `resolve_project` from this module at its
    own module load time, so importing it back here at module scope would be circular."""
    from rush.workflows.project_run import _highest_generation_attempt_dir

    runs_dir = root / ".rush" / "runs"
    manifests: list[dict[str, Any]] = []
    if not runs_dir.is_dir():
        return manifests
    for run_dir in sorted(p for p in runs_dir.iterdir() if p.is_dir()):
        attempt_dir = _highest_generation_attempt_dir(root, run_dir.name)
        if attempt_dir is None:
            continue
        manifest_path = attempt_dir / "manifest.json"
        if not manifest_path.is_file():
            continue
        try:
            manifests.append(json.loads(manifest_path.read_text(encoding="utf-8")))
        except (OSError, ValueError):
            continue
    return manifests


def _iter_all_attempt_manifests(root: Path) -> list[dict[str, Any]]:
    """Every attempt manifest of every run under `root` (oldest run first),
    each read through `_read_contained_manifest`; unreadable ones are skipped."""
    runs_dir = root / ".rush" / "runs"
    manifests: list[dict[str, Any]] = []
    if not runs_dir.is_dir():
        return manifests
    for run_dir in sorted(p for p in runs_dir.iterdir() if p.is_dir()):
        attempts_dir = run_dir / "attempts"
        if not _MAP_ID_RE.match(run_dir.name) or not attempts_dir.is_dir():
            continue
        for attempt_dir in sorted(p for p in attempts_dir.iterdir() if p.is_dir()):
            if not _MAP_ID_RE.match(attempt_dir.name):
                continue
            try:
                manifest = _read_contained_manifest(
                    root, run_dir.name, attempt_dir.name
                )
            except (FileNotFoundError, ValueError, OSError):
                continue
            if isinstance(manifest, dict):
                manifests.append(
                    {
                        **manifest,
                        "run_id": manifest.get("run_id", run_dir.name),
                        "attempt_id": manifest.get("attempt_id", attempt_dir.name),
                    }
                )
    return manifests


def _iter_handoffs(root: Path) -> list[dict[str, Any]]:
    """Every persisted `rush.workflows.project_run.build_handoff` packet under `root`
    (`.rush/handoffs/*.json`), sorted for determinism."""
    handoffs_dir = root / ".rush" / "handoffs"
    handoffs: list[dict[str, Any]] = []
    if not handoffs_dir.is_dir():
        return handoffs
    for path in sorted(handoffs_dir.glob("*.json")):
        try:
            handoffs.append(json.loads(path.read_text(encoding="utf-8")))
        except (OSError, ValueError):
            continue
    return handoffs


# --- Phase 70 T23: read-only attempt chronology ------------------------------


@dataclass(frozen=True)
class AttemptEvidence:
    """One validated `attempt.json` header plus its terminal manifest (`None`
    while the attempt is incomplete)."""

    run_id: str
    attempt_id: str
    started_at: datetime
    attempt_generation: int | None
    header: dict[str, Any]
    manifest: dict[str, Any] | None

    @property
    def completed(self) -> bool:
        return self.manifest is not None


@dataclass(frozen=True)
class ChronologyView:
    """`select_attempt_chronology`'s result. `state` is `none | resolved |
    incomplete | latest_unresolved | chronology_ambiguous`; `published` is
    the most recently started completed attempt (`published_state` `none |
    resolved | chronology_ambiguous`), `attempts` every validated attempt."""

    state: str
    run_id: str | None = None
    attempt_id: str | None = None
    started_at: str | None = None
    attempt_generation: int | None = None
    ordering: str | None = None
    affected_ids: tuple[str, ...] = ()
    run_count: int = 0
    latest: AttemptEvidence | None = None
    published: AttemptEvidence | None = None
    published_state: str = "none"
    attempts: tuple[AttemptEvidence, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "state": self.state,
            "run_id": self.run_id,
            "attempt_id": self.attempt_id,
            "started_at": self.started_at,
            "attempt_generation": self.attempt_generation,
            "ordering": self.ordering,
            "affected_ids": list(self.affected_ids),
        }


def _real_subdirs(parent: Path) -> tuple[list[Path], list[str]]:
    """`lstat`-only listing: real subdirectories, and the names of symlinked
    entries (never followed -- corrupt evidence). Regular files are ignored.
    A missing `parent` lists nothing."""
    try:
        entries = sorted(os.scandir(parent), key=lambda entry: entry.name)
    except FileNotFoundError:
        return [], []
    dirs = [Path(e.path) for e in entries if e.is_dir(follow_symlinks=False)]
    links = [e.name for e in entries if e.is_symlink()]
    return dirs, links


def _read_regular_json(path: Path) -> Any:
    """JSON of a regular (never symlinked) file. Raises `FileNotFoundError`
    when absent and `ValueError` for anything else unusable."""
    try:
        st = os.lstat(path)
    except FileNotFoundError:
        raise
    except OSError as exc:
        raise ValueError(str(exc)) from exc
    if not stat.S_ISREG(st.st_mode):
        raise ValueError(f"{path.name} is not a regular file")
    try:
        return json.loads(path.read_bytes())
    except OSError as exc:
        raise ValueError(str(exc)) from exc


def _utc_timestamp(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    return parsed if parsed.utcoffset() == UTC.utcoffset(None) else None


def _load_attempt(
    attempt_dir: Path, run_id: str, project_id: str | None
) -> AttemptEvidence | None:
    """A validated attempt, or `None` for missing/corrupt ordering evidence:
    identities must match their directories (and the registered project), a
    present `attempt_generation` must be a positive non-bool int, and
    `started_at` must be ISO-8601 UTC. A present manifest must be an object."""
    try:
        header = _read_regular_json(attempt_dir / "attempt.json")
    except (FileNotFoundError, ValueError):
        return None
    if (
        not isinstance(header, dict)
        or header.get("run_id") != run_id
        or header.get("attempt_id") != attempt_dir.name
        or (project_id is not None and header.get("project_id") != project_id)
    ):
        return None
    generation = header.get("attempt_generation")
    if "attempt_generation" in header and (
        type(generation) is not int or generation < 1
    ):
        return None
    started_at = _utc_timestamp(header.get("started_at"))
    if started_at is None:
        return None
    try:
        manifest = _read_regular_json(attempt_dir / "manifest.json")
    except FileNotFoundError:
        manifest = None
    except ValueError:
        return None
    if manifest is not None and not isinstance(manifest, dict):
        return None
    return AttemptEvidence(
        run_id, attempt_dir.name, started_at, generation, header, manifest
    )


def _select_in_run(attempts: list[AttemptEvidence]) -> AttemptEvidence | None:
    """P69-02k within one run: generation-bearing attempts outrank legacy
    ones; `None` (ambiguous) for a duplicate generation, or for more than one
    attempt when none carries a generation."""
    stamped = [a for a in attempts if a.attempt_generation is not None]
    if stamped:
        generations = [a.attempt_generation for a in stamped]
        if len(set(generations)) != len(generations):
            return None
        return max(stamped, key=lambda a: a.attempt_generation or 0)
    return attempts[0] if len(attempts) == 1 else None


def _latest_started(
    candidates: list[AttemptEvidence],
) -> tuple[AttemptEvidence | None, list[str]]:
    """Across runs: the most recently started attempt, or `(None, tied run
    IDs)` when the maximum `started_at` is shared. UUIDs, per-run generations
    and manifest `created_at` never order runs."""
    if not candidates:
        return None, []
    top = max(a.started_at for a in candidates)
    tied = [a for a in candidates if a.started_at == top]
    if len(tied) > 1:
        return None, sorted(a.run_id for a in tied)
    return tied[0], []


@dataclass
class _RunScan:
    """Per-run evidence gathered by `_chronology_runs`."""

    latest: list[AttemptEvidence]
    completed: list[AttemptEvidence]
    validated: list[AttemptEvidence]
    unresolved: list[str]
    ambiguous: list[str]
    run_count: int


def _chronology_runs(root: Path, project_id: str | None) -> _RunScan:
    """Each run's selected attempt and selected completed attempt, every
    validated attempt, and the IDs of unresolved and ambiguous runs."""
    scan = _RunScan([], [], [], [], [], 0)
    rush_dir = root / ".rush"
    if rush_dir.is_symlink():
        scan.unresolved.append(".rush")
        return scan
    run_dirs, linked = _real_subdirs(rush_dir / "runs")
    scan.unresolved.extend(linked)
    scan.run_count = len(run_dirs) + len(linked)
    for run_dir in run_dirs:
        attempt_dirs, linked_attempts = _real_subdirs(run_dir / "attempts")
        loaded = [_load_attempt(d, run_dir.name, project_id) for d in attempt_dirs]
        attempts = [a for a in loaded if a is not None]
        scan.validated.extend(attempts)
        if linked_attempts or not loaded or len(attempts) != len(loaded):
            scan.unresolved.append(run_dir.name)
            continue
        selected = _select_in_run(attempts)
        if selected is None:
            scan.ambiguous.extend([run_dir.name, *(a.attempt_id for a in attempts)])
            continue
        scan.latest.append(selected)
        done = _select_in_run([a for a in attempts if a.completed])
        if done is not None:
            scan.completed.append(done)
    return scan


def select_attempt_chronology(root: Path, project_id: str | None) -> ChronologyView:
    """T23/P69-02k read-only chronology over `.rush/runs/*/attempts/*`.

    Validates every attempt header (`_load_attempt`); symlinked run/attempt
    directories are corrupt evidence, never followed. Any missing or corrupt
    evidence makes the latest attempt `latest_unresolved` (never an older
    success substituted); a duplicate generation or an equal cross-run
    `started_at` is `chronology_ambiguous`. Writes nothing."""
    scan = _chronology_runs(root, project_id)
    published, published_ties = _latest_started(scan.completed)
    published_state = (
        "chronology_ambiguous"
        if published_ties
        else ("resolved" if published is not None else "none")
    )
    shared: dict[str, Any] = {
        "run_count": scan.run_count,
        "published": published,
        "published_state": published_state,
        "attempts": tuple(scan.validated),
    }
    if scan.unresolved:
        return ChronologyView(
            "latest_unresolved", affected_ids=tuple(scan.unresolved), **shared
        )
    if scan.ambiguous:
        return ChronologyView(
            "chronology_ambiguous", affected_ids=tuple(scan.ambiguous), **shared
        )
    chosen, ties = _latest_started(scan.latest)
    if ties:
        return ChronologyView(
            "chronology_ambiguous", affected_ids=tuple(ties), **shared
        )
    if chosen is None:
        return ChronologyView("none", **shared)
    return ChronologyView(
        "resolved" if chosen.completed else "incomplete",
        run_id=chosen.run_id,
        attempt_id=chosen.attempt_id,
        started_at=chosen.started_at.isoformat(),
        attempt_generation=chosen.attempt_generation,
        ordering="started_at",
        latest=chosen,
        **shared,
    )


# --- Phase 66 P66-06: bounded, argv-based, read-only Git evidence -----------
#
# Every subprocess call below passes an argv list (never `shell=True`, never a
# raw string handed to a shell), so a hostile branch/tag name, commit
# subject, or ref cannot inject a second command. Only `log`/`status`/`show`
# are ever invoked -- nothing here can mutate the branch, index, or working
# tree (plan §6.4/P66-06: "Must never mutate the branch or index while
# reading history/status/diffs").

_GIT_HISTORY_PAGE_MAX = 50
_GIT_DIRTY_MAX = 200
_GIT_DIFF_MAX_LINES = 500
_GIT_LOG_FIELD_SEP = "\x1f"
_GIT_REF_RE = re.compile(r"^[0-9a-fA-F]{4,40}$")
# Read-only Git: never run a repository-configured fsmonitor hook, never take
# the optional index lock (so a status read cannot rewrite `.git/index`), and
# never show signatures (which runs the repository's `gpg.program`).
_GIT_READ = (
    "git",
    "-c",
    "core.fsmonitor=false",
    "-c",
    "log.showSignature=false",
    "--no-optional-locks",
)


def _git_read(root: Path) -> list[str]:
    """`_GIT_READ` plus an empty clean/smudge/process command for every filter
    driver the repository's own config defines (a hostile `.git/config` can
    name any program there; `status` runs a clean filter on racily-clean
    files). The user's global and system drivers (e.g. git-lfs) are trusted
    and left active. Reading the config runs nothing."""
    argv = list(_GIT_READ)
    try:
        listed = subprocess.run(
            [
                *_GIT_READ,
                "config",
                "--local",
                "--includes",
                "--name-only",
                "--get-regexp",
                r"^filter\..*\.(clean|smudge|process)$",
            ],
            cwd=root,
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
        ).stdout
    except (OSError, subprocess.SubprocessError):
        listed = ""
    for name in sorted({line.strip() for line in listed.splitlines() if line.strip()}):
        argv += ["-c", f"{name}="]
    return argv


def _git_log(root: Path, *, limit: int, skip: int = 0) -> list[dict[str, Any]]:
    """Bounded commit history (`git log`, argv-based). A hostile commit
    subject is returned verbatim as a plain string field -- it is never
    interpolated into a shell command or HTML, only JSON-serialized data."""
    fmt = f"%H{_GIT_LOG_FIELD_SEP}%an{_GIT_LOG_FIELD_SEP}%aI{_GIT_LOG_FIELD_SEP}%s"
    try:
        result = subprocess.run(
            [
                *_git_read(root),
                "log",
                "--no-show-signature",
                f"--format={fmt}",
                f"-n{max(1, limit)}",
                f"--skip={max(0, skip)}",
            ],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return []
    commits: list[dict[str, Any]] = []
    for line in result.stdout.split("\n"):
        if not line:
            continue
        parts = line.split(_GIT_LOG_FIELD_SEP)
        if len(parts) != 4:
            continue
        commit_hash, author, date, subject = parts
        commits.append(
            {"hash": commit_hash, "author": author, "date": date, "subject": subject}
        )
    return commits


def _git_dirty_files(root: Path) -> list[dict[str, Any]]:
    """Bounded working-tree/index status (`git status --porcelain=v1`). A
    rename is reported as `old_path`/`path` (porcelain's `R  old -> new`
    line shape) -- never collapsed to a delete+add."""
    try:
        result = subprocess.run(
            [*_git_read(root), "status", "--porcelain=v1"],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return []
    entries: list[dict[str, Any]] = []
    for line in result.stdout.splitlines()[:_GIT_DIRTY_MAX]:
        if len(line) < 4:
            continue
        status = line[:2].strip()
        rest = line[3:]
        old_path = None
        path = rest
        if " -> " in rest:
            old_path, path = rest.split(" -> ", 1)
        entries.append({"status": status, "path": path, "old_path": old_path})
    return entries


def _git_summary(root: Path) -> dict[str, Any]:
    """Best-effort Git HEAD/dirty/history/status; never raises -- a root
    without Git is valid (plan §6.1: "A root without Git is valid"). `history`
    and `dirty_files` are bounded previews shared by `project_snapshot`'s
    `git` field and the dashboard/TUI Git section (`project_git_history`
    below serves the full paginated history)."""
    if not (root / ".git").exists():
        return {
            "state": "empty",
            "has_git": False,
            "head": None,
            "dirty": None,
            "history": [],
            "dirty_files": [],
        }
    state = "populated"
    try:
        head = subprocess.run(
            [*_git_read(root), "rev-parse", "HEAD"],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
            timeout=5,
        ).stdout.strip()
        status = subprocess.run(
            [*_git_read(root), "status", "--porcelain"],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
            timeout=5,
        ).stdout
        dirty: bool | None = bool(status.strip())
    except (OSError, subprocess.SubprocessError):
        head, dirty, state = None, None, "failed"
    return {
        "state": state,
        "has_git": True,
        "head": head,
        "dirty": dirty,
        "history": _git_log(root, limit=_GIT_HISTORY_PAGE_MAX),
        "dirty_files": _git_dirty_files(root),
    }


def _git_text(root: Path, *args: str) -> str | None:
    """One hardened read-only Git command's stdout, or `None` on failure."""
    try:
        return subprocess.run(
            [*_git_read(root), *args],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
            timeout=5,
        ).stdout
    except (OSError, subprocess.SubprocessError):
        return None


def project_git_branch(
    project: str | Path, *, data_root: Path | None = None
) -> dict[str, Any]:
    """The checked-out branch (`None` when detached or not a Git root)."""
    root = Path(resolve_project(project, data_root=data_root)["root"])
    out = _git_text(root, "symbolic-ref", "--short", "-q", "HEAD")
    return {"branch": (out or "").strip() or None}


def project_git_worktree(
    project: str | Path, *, data_root: Path | None = None
) -> dict[str, Any]:
    """The worktree top level and the shared Git directory it belongs to."""
    root = Path(resolve_project(project, data_root=data_root)["root"])
    out = _git_text(root, "rev-parse", "--show-toplevel", "--git-common-dir")
    lines = (out or "").splitlines()
    if len(lines) < 2:
        return {"toplevel": None, "git_common_dir": None}
    common = Path(lines[1])
    if not common.is_absolute():
        common = root / common
    return {"toplevel": lines[0], "git_common_dir": str(common.resolve())}


def project_git_dirty_diff(
    project: str | Path, path: str, *, data_root: Path | None = None
) -> dict[str, Any]:
    """Bounded working-tree diff of one path, only when Git's own dirty listing
    names it; any other path is `not_dirty` and no diff runs."""
    root = Path(resolve_project(project, data_root=data_root)["root"])
    if not (root / ".git").exists():
        return {"path": path, "error": "not_dirty"}
    dirty = {
        name
        for entry in _git_dirty_files(root)
        for name in (entry.get("path"), entry.get("old_path"))
        if name
    }
    if path not in dirty:
        return {"path": path, "error": "not_dirty"}
    out = _git_text(
        root, "diff", "--no-color", "--no-ext-diff", "--no-textconv", "--", path
    )
    if out is None:
        return {"path": path, "error": "failed"}
    lines = out.splitlines()
    return {
        "path": path,
        "lines": lines[:_GIT_DIFF_MAX_LINES],
        "truncated": len(lines) > _GIT_DIFF_MAX_LINES,
    }


def project_git_history(
    project: str | Path,
    *,
    data_root: Path | None = None,
    limit: int = 20,
    skip: int = 0,
) -> dict[str, Any]:
    """Bounded, paginated Git commit history for the browser/TUI Git section
    (plan §6.4/P66-06: "bounded pagination"). A non-Git project returns
    `has_git: False` and an empty page, never an error (plan §6.1: "A root
    without Git is valid")."""
    record = resolve_project(project, data_root=data_root)
    root = Path(record["root"])
    if not (root / ".git").exists():
        return {"has_git": False, "commits": [], "next_skip": None}
    limit = max(1, min(limit, _GIT_HISTORY_PAGE_MAX))
    skip = max(0, skip)
    commits = _git_log(root, limit=limit + 1, skip=skip)
    has_more = len(commits) > limit
    return {
        "has_git": True,
        "commits": commits[:limit],
        "next_skip": (skip + limit) if has_more else None,
    }


def project_git_commit_diff(
    project: str | Path, commit: str, *, data_root: Path | None = None
) -> dict[str, Any]:
    """Bounded, read-only diff for one commit (`git show`, argv-based). Only
    ever invoked with `commit` validated against `_GIT_REF_RE` (a bare hex
    object id) -- never a raw ref/branch name -- so it is never possible to
    pass an option-like or `ref:path` argument into git's own parser.
    Renames are detected (`--find-renames`), never shown as a plain
    delete+add. `changed_paths` includes both the old and new name of a
    rename, enabling exact-identity linking to scan-output artifact paths."""
    record = resolve_project(project, data_root=data_root)
    root = Path(record["root"])
    if not (root / ".git").exists():
        return {
            "has_git": False,
            "commit": commit,
            "lines": [],
            "changed_paths": [],
            "truncated": False,
        }
    if not _GIT_REF_RE.match(commit):
        return {
            "has_git": True,
            "commit": commit,
            "lines": [],
            "changed_paths": [],
            "truncated": False,
            "error": "invalid_ref",
        }
    try:
        patch = subprocess.run(
            [
                *_git_read(root),
                "show",
                "--no-show-signature",
                "--no-ext-diff",
                "--no-textconv",
                "--find-renames",
                "--no-color",
                "--patch",
                commit,
            ],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
            timeout=5,
        ).stdout
        name_status = subprocess.run(
            [
                *_git_read(root),
                "show",
                "--no-show-signature",
                "--no-ext-diff",
                "--no-textconv",
                "--find-renames",
                "--name-status",
                "--format=",
                commit,
            ],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
            timeout=5,
        ).stdout
    except (OSError, subprocess.SubprocessError):
        return {
            "has_git": True,
            "commit": commit,
            "lines": [],
            "changed_paths": [],
            "truncated": False,
            "error": "unavailable",
        }
    changed_paths: list[str] = []
    for line in name_status.splitlines():
        parts = line.split("\t")
        if not parts or not parts[0]:
            continue
        if parts[0].startswith("R") and len(parts) == 3:
            changed_paths.extend([parts[1], parts[2]])
        elif len(parts) >= 2:
            changed_paths.append(parts[1])
    lines = patch.splitlines()
    truncated = len(lines) > _GIT_DIFF_MAX_LINES
    return {
        "has_git": True,
        "commit": commit,
        "lines": lines[:_GIT_DIFF_MAX_LINES],
        "changed_paths": changed_paths,
        "truncated": truncated,
    }


def _git_show_path_digest(root: Path, commit: str, path: str) -> str | None:
    """SHA-256 of `path`'s content as recorded in `commit`'s tree (`git show
    <commit>:<path>`), or `None` if the path doesn't exist at that commit or
    the read fails -- the same digest algorithm `project_run.py`'s staging
    engines use for `git_link["path_digests"]`."""
    try:
        result = subprocess.run(
            [
                *_git_read(root),
                "show",
                "--no-ext-diff",
                "--no-textconv",
                f"{commit}:{path}",
            ],
            cwd=root,
            check=True,
            capture_output=True,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return hashlib.sha256(result.stdout).hexdigest()


def git_link_matches_commit(
    root: Path, git_link: dict[str, Any] | None, commit: str
) -> bool:
    """P69-07.2b: exact source-revision match (P69-03.2's Git-link
    predicate, reused verbatim) -- a scan output links to a commit only when
    its persisted `git_link` HEAD matches the commit, the tree was clean at
    scan start, and every recorded per-path digest matches that commit's
    tree for its path. Never merely an intersecting file path."""
    if not _GIT_REF_RE.match(commit):
        return False
    if not git_link or not git_link.get("repository"):
        return False
    if git_link.get("head") != commit:
        return False
    if git_link.get("dirty"):
        return False
    digests = git_link.get("path_digests") or {}
    if not digests:
        return False
    return all(
        _git_show_path_digest(root, commit, path) == digest
        for path, digest in digests.items()
    )


def _readonly_memory_refs(
    root: Path,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Live and tombstoned memory artifact refs over the zero-write reader --
    the same SQL as `TypedArtifactStore.list_artifact_refs`/`list_deleted_refs`,
    never reading `content`. No DB is no refs."""

    def _read(
        conn: sqlite3.Connection,
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        conn.row_factory = sqlite3.Row
        if not sqlite_has_table(conn, "memory_artifacts"):
            return [], []
        live = conn.execute(
            "SELECT id, family, subject, trust_tier, source, created_at, "
            "artifact_version FROM memory_artifacts ORDER BY id ASC"
        ).fetchall()
        deleted: list[sqlite3.Row] = []
        if sqlite_has_table(conn, "memory_changes"):
            deleted = conn.execute(
                "SELECT artifact_id AS id, subject, "
                "MAX(artifact_version) AS revision, MAX(created_at) AS deleted_at "
                "FROM memory_changes WHERE tombstone = 1 "
                "AND artifact_id NOT IN (SELECT id FROM memory_artifacts) "
                "GROUP BY artifact_id ORDER BY artifact_id ASC"
            ).fetchall()
        return [dict(row) for row in live], [dict(row) for row in deleted]

    refs = read_sqlite_readonly(Path(root).resolve() / ".rush" / "memory.db", _read)
    return refs if refs is not None else ([], [])


def _readonly_memory_event_totals(
    root: Path, filters: Mapping[str, str] | None = None
) -> dict[str, int]:
    """Recorded memory-event token totals by kind, read without creating or
    migrating `.rush/telemetry/tokens.db`. Missing DB/table is no events.
    `filters` match stored identity columns; a schema without one of them
    holds only unscoped rows, which a scoped selection never includes."""
    filters = dict(filters or {})

    def _read(conn: sqlite3.Connection) -> dict[str, int]:
        if not sqlite_has_table(conn, "memory_events"):
            return {}
        columns = {row[1] for row in conn.execute("PRAGMA table_info(memory_events)")}
        if not set(filters) <= columns:
            return {}
        where = " AND ".join(f"{column} = ?" for column in filters)
        rows = conn.execute(
            "SELECT kind, COALESCE(SUM(tokens), 0) FROM memory_events"
            + (f" WHERE {where}" if where else "")
            + " GROUP BY kind",
            list(filters.values()),
        ).fetchall()
        return {str(kind): int(total) for kind, total in rows}

    db = Path(root).resolve() / ".rush" / "telemetry" / "tokens.db"
    totals = read_sqlite_readonly(db, _read)
    return totals or {}


def list_project_artifacts(
    project: str | Path,
    *,
    data_root: Path | None = None,
    include_internal: bool = False,
) -> dict[str, Any]:
    """Categorized, provenance-carrying references to everything this project has
    produced: scan-run outputs, agent handoff packets, and memory artifacts including
    tombstoned/deleted ones (plan §6.4, P65-07.2/.3: "Generic artifact listing prevents
    newly generated information becoming invisible until a bespoke widget exists").

    Scan-output categories are whatever `plan_scan`'s candidate classification assigned
    them (plan §6.4) -- passed through verbatim, never filtered against a known-category
    allowlist, so a category this function has never seen before (a future profiling/
    export engine) still comes back as a discoverable reference. Deliberately never
    includes raw finding evidence, tool stdout, or memory content -- reference metadata
    only, so a secret embedded in stored raw output can never surface here (plan §6.4:
    "Redacted views never expose secrets from raw storage").
    """
    record = resolve_project(project, data_root=data_root)
    root = Path(record["root"])

    scan_outputs: list[dict[str, Any]] = []
    for manifest in _iter_run_manifests(root):
        run_id = manifest.get("run_id")
        attempt_id = manifest.get("attempt_id")
        # P69-07.2c: the persisted Git-link provenance for this attempt
        # (P69-07.2b), passed through verbatim so a reference resolved back
        # via `expand_artifact_reference` carries the same attempt-scoped
        # Git/content identity its manifest recorded.
        git_link = manifest.get("git_link") or {}
        for item in manifest.get("scheduled") or []:
            child = item.get("child") or {}
            scan_outputs.append(
                {
                    # P69-07.2c: attempt-scoped, not just run-scoped -- two
                    # attempts of the same `run_id` previously produced
                    # identical `artifact_ref` values, so a stale reference
                    # silently resolved whichever attempt was currently
                    # highest-generation instead of the one it was minted for.
                    "artifact_ref": f"run:{run_id}:{attempt_id}:{item.get('candidate_id')}",
                    "category": item.get("category", "unknown"),
                    "kind": "scan_output",
                    "run_id": run_id,
                    "attempt_id": attempt_id,
                    "tool_id": item.get("candidate_id"),
                    "outcome": item.get("outcome"),
                    "status": child.get("status"),
                    "finding_count": len(child.get("findings") or []),
                    "paths": list(child.get("artifacts") or []),
                    "git_link": git_link,
                }
            )

    # T28-E: every attempt of every run (not only the latest), one entry per
    # captured path, each naming the immutable snapshot a reader/export uses.
    captured: list[dict[str, Any]] = []
    for manifest in _iter_all_attempt_manifests(root):
        for item in manifest.get("scheduled") or []:
            snapshots = (
                item.get("artifact_snapshots") if isinstance(item, dict) else None
            )
            if not isinstance(snapshots, dict):
                continue
            for rel_path, snap in snapshots.items():
                if not isinstance(snap, dict):
                    continue
                captured.append(
                    {
                        "artifact_ref": (
                            f"run:{manifest.get('run_id')}:{manifest.get('attempt_id')}:"
                            f"{item.get('candidate_id')}:{rel_path}"
                        ),
                        "category": item.get("category", "unknown"),
                        "kind": "captured_artifact",
                        "run_id": manifest.get("run_id"),
                        "attempt_id": manifest.get("attempt_id"),
                        "tool_id": item.get("candidate_id"),
                        "path": rel_path,
                        "sha256": snap.get("sha256"),
                        "size": snap.get("size"),
                        "media_type": snap.get("media_type"),
                    }
                )

    handoffs: list[dict[str, Any]] = []
    for handoff in _iter_handoffs(root):
        handoffs.append(
            {
                "artifact_ref": f"handoff:{handoff.get('handoff_id')}",
                "category": "handoff",
                "kind": "agent_handoff",
                "run_id": handoff.get("run_id"),
                "state": handoff.get("state"),
                "artifact_id": handoff.get("artifact_id"),
                "artifact_version": handoff.get("artifact_version"),
                "tokens": (handoff.get("packet") or {}).get("tokens"),
            }
        )

    # T28-A: zero-write reads (X1) -- a constructed store would create/migrate
    # `.rush/memory.db` and `.rush/cache` during a read-only evidence view.
    live_rows, deleted_rows = _readonly_memory_refs(root)
    memory_refs = [
        {
            "artifact_ref": f"memory:{row['id']}",
            "category": row["subject"],
            "kind": "memory",
            "family": row["family"],
            "id": row["id"],
            "artifact_version": row["artifact_version"],
            "trust_tier": row["trust_tier"],
            "deleted": False,
        }
        for row in live_rows
        if include_internal or not is_internal_memory_source(row["source"])
    ] + [
        {
            "artifact_ref": f"memory:{row['id']}",
            "category": row.get("subject") or "unknown",
            "kind": "memory",
            "id": row["id"],
            "artifact_version": row.get("revision"),
            "deleted": True,
        }
        for row in deleted_rows
    ]

    return {
        "project_id": record["project_id"],
        "scan_outputs": scan_outputs,
        "captured": captured,
        "handoffs": handoffs,
        "memory": memory_refs,
    }


def expand_artifact_reference(
    project: str | Path, artifact_ref: str, *, data_root: Path | None = None
) -> dict[str, Any]:
    """Resolve one `list_project_artifacts` reference back to its full
    manifest entry -- same redaction rule as `list_project_artifacts` (never
    raw finding evidence, tool stdout, or memory content). Never special-
    cases a `category`/`kind` it has not seen before, so a brand-new output
    type from a future engine still expands generically. A stale/removed
    reference returns `found: False`, never raises (plan §6.4/P66-06:
    "visibility of every manifest entry" -- a missing artifact degrades to an
    explicit state instead of a 500)."""
    payload = list_project_artifacts(project, data_root=data_root)
    for bucket in ("scan_outputs", "handoffs", "memory"):
        for item in payload.get(bucket) or []:
            if item.get("artifact_ref") == artifact_ref:
                return {
                    "found": True,
                    "kind": item.get("kind", "unknown"),
                    "entry": item,
                }
    return {"found": False, "kind": "unknown", "entry": None}


def export_project_data(
    project: str | Path, *, data_root: Path | None = None
) -> dict[str, Any]:
    """Per-project data export (plan §6.4/P66-06.3): the same redacted
    snapshot/artifact-reference serialization the dashboard/TUI already
    render, packaged as one downloadable document -- never a second,
    independently-computed export format."""
    snapshot = project_snapshot(project, data_root=data_root, include_internal=True)
    return {
        "schema_version": 1,
        "project_id": snapshot["project"]["project_id"],
        "exported_at": datetime.now(UTC).isoformat(),
        "snapshot": snapshot,
    }


def _identity_matches(record: Mapping[str, Any], filters: Mapping[str, str]) -> bool:
    """A record belongs to a scoped selection only by its own stored identity;
    a missing identity is unscoped and never reconstructed."""
    return all(record.get(key) == value for key, value in filters.items())


def project_token_usage(
    project: str | Path,
    *,
    data_root: Path | None = None,
    run_id: str | None = None,
    agent_id: str | None = None,
    session_id: str | None = None,
) -> dict[str, Any]:
    """Separates provider-reported real model usage, tokenizer-computed handoff-packet
    counts, recorded cache/memory-reuse event costs, and the estimated avoided-payload
    savings ratio -- never blends an estimate into a real count (plan §6.4/P65-07.1:
    "separating provider-reported tokens, tokenizer counts, cache hits and estimates").
    A provider total absent from every run manifest stays `None` ("unknown"), never
    coerced to `0` ("known-zero").
    """
    record = resolve_project(project, data_root=data_root)
    return root_token_usage(
        Path(record["root"]), run_id=run_id, agent_id=agent_id, session_id=session_id
    )


_TOKEN_USAGE_CACHE: dict[tuple[Any, ...], dict[str, Any]] = {}
_TOKEN_USAGE_CACHE_LOCK = threading.Lock()
_TOKEN_USAGE_CACHE_SIZE = 16


def token_usage_signature(root: Path) -> tuple[Any, ...]:
    """Every input `root_token_usage` reads, as (path, size, st_mtime_ns): the
    telemetry DB and its WAL, every attempt's JSON records (manifest and the
    attempt header the latest-attempt selector reads) and every handoff. An
    equal signature means an identical read, so the Tokens view and `rush
    gain` re-read only when it changes. Stats only; never creates anything."""
    root = Path(root)
    telemetry = root / ".rush" / "telemetry" / "tokens.db"
    paths = [
        telemetry,
        telemetry.with_name("tokens.db-wal"),
        *sorted(root.glob(".rush/runs/*/attempts/*/*.json")),
        *sorted(root.glob(".rush/handoffs/*.json")),
    ]
    entries: list[tuple[str, int | None, int | None]] = []
    for path in paths:
        try:
            info = path.stat()
        except OSError:
            entries.append((path.as_posix(), None, None))
        else:
            entries.append((path.as_posix(), info.st_size, info.st_mtime_ns))
    return tuple(entries)


def _has_identity(record: Mapping[str, Any], key: str) -> bool:
    """A stored identity value; absent, empty and the telemetry default
    `'unscoped'` are all no identity."""
    value = record.get(key)
    return value is not None and value not in ("", "unscoped")


def _event_time(value: Any) -> datetime | None:
    """A stored event time (ISO string or Unix seconds) as aware UTC."""
    if isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        return datetime.fromtimestamp(value, UTC)
    if isinstance(value, str) and value:
        try:
            parsed = datetime.fromisoformat(value)
        except ValueError:
            return None
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
    return None


def _readonly_telemetry_scope(
    root: Path, filters: Mapping[str, str], identity_keys: list[str]
) -> tuple[int, list[datetime]]:
    """Telemetry rows (token and memory events) without a stored value for
    one of `identity_keys`, and the earliest/latest stored time of the rows
    in this selection. A legacy table without an identity column holds only
    unscoped rows. Read-only, like `_readonly_memory_event_totals`."""

    def _read(conn: sqlite3.Connection) -> tuple[int, list[datetime]]:
        unscoped = 0
        times: list[datetime] = []
        for table in ("token_events", "memory_events"):
            if not sqlite_has_table(conn, table):
                continue
            columns = {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
            if not set(identity_keys) <= columns:
                unscoped += int(
                    conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                )
                selected = None if filters else ""
            else:
                missing = " OR ".join(
                    f"{key} IS NULL OR {key} IN ('', 'unscoped')"
                    for key in identity_keys
                )
                unscoped += int(
                    conn.execute(
                        f"SELECT COUNT(*) FROM {table} WHERE {missing}"
                    ).fetchone()[0]
                )
                selected = " AND ".join(f"{column} = ?" for column in filters)
            if selected is None or "timestamp" not in columns:
                continue
            bounds = conn.execute(
                f"SELECT MIN(timestamp), MAX(timestamp) FROM {table}"
                + (f" WHERE {selected}" if selected else ""),
                list(filters.values()) if selected else [],
            ).fetchone()
            times.extend(t for t in map(_event_time, bounds) if t is not None)
        return unscoped, times

    db = Path(root).resolve() / ".rush" / "telemetry" / "tokens.db"
    return read_sqlite_readonly(db, _read) or (0, [])


def root_token_usage(
    root: Path,
    *,
    run_id: str | None = None,
    agent_id: str | None = None,
    session_id: str | None = None,
) -> dict[str, Any]:
    """`project_token_usage` over an already-resolved project root: the one
    token authority shared by the Tokens section and `rush gain`, which may
    run against an unregistered root. Read-only. The result is cached by
    root, filters and `token_usage_signature`, taken before the read, so an
    unchanged selection is never re-read and a write during a read triggers
    one more."""
    filters = {
        key: value
        for key, value in (
            ("run_id", run_id),
            ("agent_id", agent_id),
            ("session_id", session_id),
        )
        if value is not None
    }
    key = (
        str(Path(root).resolve()),
        tuple(sorted(filters.items())),
        token_usage_signature(root),
    )
    with _TOKEN_USAGE_CACHE_LOCK:
        cached = _TOKEN_USAGE_CACHE.get(key)
    if cached is None:
        cached = _read_root_token_usage(root, filters)
        with _TOKEN_USAGE_CACHE_LOCK:
            _TOKEN_USAGE_CACHE[key] = cached
            while len(_TOKEN_USAGE_CACHE) > _TOKEN_USAGE_CACHE_SIZE:
                _TOKEN_USAGE_CACHE.pop(next(iter(_TOKEN_USAGE_CACHE)))
    return copy.deepcopy(cached)


def _read_root_token_usage(root: Path, filters: Mapping[str, str]) -> dict[str, Any]:
    # A scoped selection's unscoped events are those missing one of its
    # identities; an unscoped view's are those with no stored run identity.
    identity_keys = list(filters) or ["run_id"]
    times: list[datetime] = []

    provider_total: int | None = None
    provider_events = 0
    provider_by_tool: dict[str, int] = {}
    unscoped_provider = 0
    for manifest in _iter_run_manifests(root):
        matches = _identity_matches(manifest, filters)
        scoped = all(_has_identity(manifest, k) for k in identity_keys)
        for item in manifest.get("scheduled") or []:
            metrics = (item.get("child") or {}).get("metrics") or {}
            reported = metrics.get("total_tokens")
            if not isinstance(reported, int) or isinstance(reported, bool):
                continue
            unscoped_provider += not scoped
            if not matches:
                continue
            provider_total = (provider_total or 0) + reported
            provider_events += 1
            tool = str(item.get("candidate_id") or "unknown")
            provider_by_tool[tool] = provider_by_tool.get(tool, 0) + reported
            stamp = _event_time(manifest.get("created_at"))
            if stamp is not None:
                times.append(stamp)

    tokenizer_total = 0
    tokenizer_packets = 0
    unscoped_packets = 0
    for handoff in _iter_handoffs(root):
        tokens = (handoff.get("packet") or {}).get("tokens")
        if not isinstance(tokens, int) or isinstance(tokens, bool):
            continue
        unscoped_packets += not all(_has_identity(handoff, k) for k in identity_keys)
        if not _identity_matches(handoff, filters):
            continue
        tokenizer_total += tokens
        tokenizer_packets += 1
        stamp = _event_time(handoff.get("created_at"))
        if stamp is not None:
            times.append(stamp)

    # T28-A: read-only; `TelemetryStore(root)` creates/migrates tokens.db.
    # A corrupt or unreadable DB is an unavailable measurement with its
    # reason, never an exception into the Tokens section.
    telemetry_error: str | None = None
    try:
        recorded = _readonly_memory_event_totals(root, filters)
        avoided = read_summary_readonly(root, **filters)
        unscoped_telemetry, telemetry_times = _readonly_telemetry_scope(
            root, filters, identity_keys
        )
        times.extend(telemetry_times)
    except (MemoryStoreUnreadableError, sqlite3.DatabaseError) as exc:
        telemetry_error = f"token telemetry unreadable: {exc}"
        recorded = {}
        unscoped_telemetry = 0
        avoided = {
            "events_count": 0,
            "total_raw_tokens": 0,
            "total_compressed_tokens": 0,
            "net_tokens_saved": 0,
            "compression_ratio": 0.0,
            "dollar_savings_est": 0.0,
            "available": False,
            "reason": telemetry_error,
        }
    cache_kinds = ("retrieval", "expansion", "packing", "handoff", "embedding")
    cache_by_kind = {kind: recorded.get(kind, 0) for kind in cache_kinds}

    provider: dict[str, Any] = {
        "total_tokens": provider_total,
        "event_count": provider_events,
        "by_tool": provider_by_tool,
        "source": "run_manifest_metrics",
    }
    if provider_total is None:
        provider["reason"] = (
            "no run manifest in this selection reports provider token usage"
        )
    cache_hits: dict[str, Any] = {
        "total_tokens": sum(cache_by_kind.values()),
        "by_kind": cache_by_kind,
    }
    if telemetry_error is not None:
        cache_hits.update(available=False, reason=telemetry_error)

    unscoped: dict[str, Any] = {
        "event_count": unscoped_provider + unscoped_packets + unscoped_telemetry,
        "provider_events": unscoped_provider,
        "tokenizer_packets": unscoped_packets,
        "telemetry_events": unscoped_telemetry,
        "identity_keys": identity_keys,
    }
    if telemetry_error is not None:
        unscoped["reason"] = telemetry_error
    usage: dict[str, Any] = {
        "provider_reported": provider,
        "tokenizer_counted": {
            "total_tokens": tokenizer_total,
            "packet_count": tokenizer_packets,
            "encoding": "cl100k_base",
        },
        "cache_hits": cache_hits,
        "estimated_avoided": avoided,
        "unscoped": unscoped,
        # The measurement interval: earliest/latest stored time of an event
        # in this selection (None when none carries a time).
        "interval": {
            "earliest": min(times).isoformat() if times else None,
            "latest": max(times).isoformat() if times else None,
        },
    }
    # Unfiltered callers keep the original key set; only a scoped selection
    # reports the identities it was filtered by.
    if filters:
        usage["filters"] = filters
    return usage


def _memory_counts(
    conn: sqlite3.Connection, include_internal: bool
) -> tuple[dict[str, int], int] | None:
    """Every live row per subject (archived and expired included, as
    `list_artifact_refs`) and the tombstoned-id count (`list_deleted_refs`);
    `None` for a schema that predates `artifact_version`/archive/expiry."""
    columns = {row[1] for row in conn.execute("PRAGMA table_info(memory_artifacts)")}
    if not {"artifact_version", "archived_at", "expired_at"} <= columns:
        return None
    counts: dict[str, int] = {}
    for subject, source in conn.execute("SELECT subject, source FROM memory_artifacts"):
        if include_internal or not is_internal_memory_source(source):
            counts[subject] = counts.get(subject, 0) + 1
    if not sqlite_has_table(conn, "memory_changes"):
        return counts, 0
    deleted = conn.execute(
        "SELECT COUNT(DISTINCT artifact_id) FROM memory_changes WHERE tombstone = 1 "
        "AND artifact_id NOT IN (SELECT id FROM memory_artifacts)"
    ).fetchone()[0]
    return counts, int(deleted)


def _readonly_memory_counts(
    root: Path, *, include_internal: bool
) -> tuple[dict[str, int], int]:
    """T23: memory counts over the shared zero-write reader
    (`read_sqlite_readonly`) -- never a constructed store (no directory,
    schema, cursor key or sidecar). No DB counts nothing; an unreadable or
    unmigrated one raises `MemoryStoreUnreadableError`, never an empty count."""
    db = Path(root).resolve() / ".rush" / "memory.db"
    counts = read_sqlite_readonly(
        db, lambda conn: _memory_counts(conn, include_internal)
    )
    if counts is not None:
        return counts
    if db.exists():
        raise MemoryStoreUnreadableError(
            readonly_view_reason("migration_required"), code="E_MIGRATION"
        )
    return {}, 0


def _latest_run_summary(root: Path, project_id: str) -> dict[str, Any]:
    """T23: the latest attempt by the shared read-only chronology (never UUID
    order), and its own counts only -- never a sum across manifests. Shared by
    `project_snapshot` and the TUI Overview (`project_overview_evidence`)."""
    chronology = select_attempt_chronology(root, project_id)
    manifest = chronology.latest.manifest if chronology.latest else None
    aggregate = (manifest or {}).get("aggregate") or {}
    run_state = manifest.get("run_state") if manifest else None
    if chronology.state == "incomplete":
        run_state = "incomplete"
    return {
        "count": chronology.run_count,
        "latest_run_id": chronology.run_id,
        "latest_run_state": run_state,
        "coverage": (aggregate.get("metadata") or {}).get("coverage"),
        "findings_count": (
            len(aggregate.get("findings") or []) if manifest is not None else None
        ),
        "selection_state": chronology.state,
    }


def project_overview_evidence(root: Path, project_id: str | None) -> dict[str, Any]:
    """T28-A Overview evidence beyond `rush status`: Git branch/worktree state,
    detected stack and the latest attempt's coverage/finding counts. Read-only;
    an unregistered project (`project_id is None`) has no run evidence."""
    return {
        "git": _git_summary(root),
        "stack": sorted(detect_project_languages(root)),
        "runs": _latest_run_summary(root, project_id) if project_id else None,
    }


def project_snapshot(
    project: str | Path,
    *,
    data_root: Path | None = None,
    include_internal: bool = False,
) -> dict[str, Any]:
    """One shared evidence view for CLI/MCP/TUI/web (plan §6.4, P65-07.2): overview,
    run/coverage/finding summary, memory summary, token totals, Git summary, and
    categorized artifact references. Shares `list_project_artifacts`'s redaction rule --
    never surfaces raw finding evidence or memory content, reference metadata only."""
    record = resolve_project(project, data_root=data_root)
    root = Path(record["root"])

    runs = _latest_run_summary(root, record["project_id"])
    subject_counts, deleted_count = _readonly_memory_counts(
        root, include_internal=include_internal
    )

    return {
        "project": record,
        "runs": runs,
        "memory": {
            "counts_by_subject": subject_counts,
            "deleted_count": deleted_count,
            "admin_capabilities": [
                "write",
                "promote",
                "maintain",
                "delete",
                "edit",
                "archive",
            ],
        },
        "tokens": project_token_usage(record["project_id"], data_root=data_root),
        "git": _git_summary(root),
        "artifacts": list_project_artifacts(
            record["project_id"], data_root=data_root, include_internal=include_internal
        ),
    }


# --- Phase 70 T28-C: read-only project map evidence ---------------------------

_MAP_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
_NOT_CAPTURED = "not captured (unavailable)"
_MAX_ARTIFACT_PAGE_BYTES = 1024 * 1024


def _scan_file_inventory(root: Path) -> list[dict[str, str]]:
    """P69-03.2b: the project's own tracked-or-present files, its own
    concept -- never derived from a scan's findings or a `ScanPlan`'s
    `ScanCandidate` set (different tools legitimately target different file
    subsets). Reuses the same `SKIP_DIRS` ignore convention every other
    whole-tree walk in this codebase already shares (`rush.review.collection`)
    rather than inventing a second bespoke list."""
    if not root.is_dir():
        return []
    entries: list[dict[str, str]] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(root)
        if any(part in SKIP_DIRS or part.startswith(".") for part in rel.parts[:-1]):
            continue
        entries.append({"path": rel.as_posix()})
    return entries


def _manifest_rel(run_id: str, attempt_id: str) -> str:
    return f".rush/runs/{run_id}/attempts/{attempt_id}/manifest.json"


def _read_contained_manifest(root: Path, run_id: str, attempt_id: str) -> Any:
    """The attempt's `manifest.json` through `PhysicalRoot.open_contained`
    (no symlinked component, no escape) and `_read_regular_json`. Raises
    `FileNotFoundError` when absent, `ValueError` when refused or unusable."""
    try:
        path = PhysicalRoot(root).open_contained(_manifest_rel(run_id, attempt_id))
    except (ContainmentError, ValueError) as exc:
        raise ValueError(str(exc)) from exc
    return _read_regular_json(path)


def _current_map_memories(root: Path) -> list[dict[str, Any]] | str:
    """Recorded memory artifacts with `cites` only from the recorded
    `symbol_ref` (`path::Symbol`), over the zero-write reader."""

    def _read(conn: sqlite3.Connection) -> list[dict[str, Any]]:
        conn.row_factory = sqlite3.Row
        if not sqlite_has_table(conn, "memory_artifacts"):
            return []
        rows = conn.execute(
            "SELECT id, symbol_ref, source FROM memory_artifacts ORDER BY id ASC"
        ).fetchall()
        return [
            {
                "id": row["id"],
                "cites": (
                    [str(row["symbol_ref"]).split("::", 1)[0]]
                    if row["symbol_ref"]
                    else []
                ),
            }
            for row in rows
            if not is_internal_memory_source(row["source"])
        ]

    try:
        memories = read_sqlite_readonly(root / ".rush" / "memory.db", _read)
    except MemoryStoreUnreadableError as exc:
        return f"unavailable ({exc})"
    return memories if memories is not None else []


def _current_map_agents(root: Path, run_id: str) -> list[dict[str, Any]]:
    """`.rush/handoffs/*.json` recorded against exactly `run_id`, merged per
    agent (`assigned_to` = that run's handed-off `finding_ids`)."""
    agents: dict[str, list[str]] = {}
    for handoff in _iter_handoffs(root):
        if not isinstance(handoff, dict) or handoff.get("run_id") != run_id:
            continue
        agent_id = handoff.get("agent_id")
        if not isinstance(agent_id, str) or not agent_id:
            continue
        assigned = agents.setdefault(agent_id, [])
        for finding_id in handoff.get("finding_ids") or []:
            if isinstance(finding_id, str) and finding_id not in assigned:
                assigned.append(finding_id)
    return [{"id": agent_id, "assigned_to": ids} for agent_id, ids in agents.items()]


def project_map_snapshot(
    project: dict[str, Any], run_id: str | None, attempt_id: str | None
) -> dict[str, Any]:
    """T28-C: the `build_project_map` input (files/findings/memories/agents)
    for one resolved project, read-only. `run_id` given is a historical view
    whose memories/agents come only from the manifest's frozen
    `historical_memory_agent_snapshot` (never written here, never
    live-substituted); `run_id` None is the current view, resolved through
    T23's `select_attempt_chronology`. Missing, corrupt, or ambiguous
    evidence is `available: False` with a `reason`, never an exception."""
    root = Path(project["root"])
    project_id = project["project_id"]
    base: dict[str, Any] = {
        "schema_version": 1,
        "project_id": project_id,
        "root": str(root),
        "files": [],
        "findings": [],
        "memories": [],
        "agents": [],
    }

    def unavailable(reason: str, **extra: Any) -> dict[str, Any]:
        return {**base, **extra, "available": False, "reason": reason}

    historical = run_id is not None
    selection_state = "explicit"
    if run_id is None:
        chronology = select_attempt_chronology(root, project_id)
        selection_state = chronology.state
        if chronology.state in {"latest_unresolved", "chronology_ambiguous"}:
            return unavailable(chronology.state, selection_state=chronology.state)
        if chronology.published is None:
            # No published attempt yet: memories are project-scoped and
            # still read; agents are run-scoped, so there are none.
            return {
                **base,
                "run_id": None,
                "attempt_id": None,
                "selection_state": chronology.state,
                "memories": _current_map_memories(root),
                "artifact_snapshots": {},
            }
        run_id = chronology.published.run_id
        attempt_id = chronology.published.attempt_id
    if not _MAP_ID_RE.match(run_id):
        return unavailable("invalid_run_id")
    if attempt_id is None:
        from rush.workflows.project_run import _highest_generation_attempt_dir

        try:
            attempt_dir = _highest_generation_attempt_dir(root, run_id)
        except (OSError, ValueError):
            attempt_dir = None
        if attempt_dir is None:
            return unavailable("attempt_not_found", run_id=run_id)
        attempt_id = attempt_dir.name
    if not _MAP_ID_RE.match(attempt_id):
        return unavailable("invalid_attempt_id", run_id=run_id)
    ids = {"run_id": run_id, "attempt_id": attempt_id}
    try:
        manifest = _read_contained_manifest(root, run_id, attempt_id)
    except FileNotFoundError:
        return unavailable("manifest_missing", **ids)
    except ValueError as exc:
        return unavailable(f"manifest_unreadable: {exc}", **ids)
    if not isinstance(manifest, dict):
        return unavailable("manifest_unreadable: not a JSON object", **ids)

    aggregate = manifest.get("aggregate")
    raw_findings = aggregate.get("findings") if isinstance(aggregate, dict) else None
    findings = [
        dict(finding, id=finding.get("finding_id") or finding.get("id"))
        for finding in (raw_findings if isinstance(raw_findings, list) else [])
        if isinstance(finding, dict)
    ]
    snapshot: dict[str, Any] = {
        **base,
        **ids,
        "selection_state": selection_state,
        "findings": findings,
    }
    inventory = manifest.get("file_inventory")
    if isinstance(inventory, list):
        snapshot["files"] = inventory
    else:
        # A legacy manifest with no recorded inventory, or a malformed
        # (non-list) one: never a live rewalk substituted as if recorded;
        # only the attempt's own finding paths, flagged as such.
        snapshot["file_inventory_missing"] = True
        snapshot["files"] = [
            {"path": path}
            for path in sorted(
                {f["path"] for f in findings if isinstance(f.get("path"), str)}
            )
        ]

    if historical:
        frozen = manifest.get("historical_memory_agent_snapshot")
        frozen = frozen if isinstance(frozen, dict) else {}
        memories = frozen.get("memories")
        agents = frozen.get("agents")
        snapshot["memories"] = memories if isinstance(memories, list) else _NOT_CAPTURED
        snapshot["agents"] = agents if isinstance(agents, list) else _NOT_CAPTURED
    else:
        snapshot["memories"] = _current_map_memories(root)
        snapshot["agents"] = _current_map_agents(root, run_id)

    artifact_snapshots: dict[str, dict[str, Any]] = {}
    for item in manifest.get("scheduled") or []:
        if not isinstance(item, dict):
            continue
        captured = item.get("artifact_snapshots")
        if not isinstance(captured, dict):
            continue
        for path, entry in captured.items():
            if isinstance(entry, dict) and path not in artifact_snapshots:
                artifact_snapshots[path] = {
                    "tool_id": item.get("candidate_id"),
                    "sha256": entry.get("sha256"),
                }
    snapshot["artifact_snapshots"] = artifact_snapshots
    return snapshot


def open_contained_file(root: Path | str, relative_path: str) -> int:
    """Opens `relative_path` under `root` read-only and returns the fd.

    Lexical checks go through `PhysicalRoot.open_contained`; then every
    component is opened from the root's own fd with `dir_fd` and
    `O_NOFOLLOW` (`O_DIRECTORY` for directories), so a component swapped
    for a symlink after validation is refused instead of followed. The
    result must be a regular file with `st_nlink == 1` (a hard link can
    alias a file outside the root). Raises `ContainmentError` on a refusal,
    `FileNotFoundError` when a component is missing, `OSError` otherwise.
    The caller closes the fd."""
    physical = PhysicalRoot(root)
    target = physical.open_contained(relative_path)
    nofollow = getattr(os, "O_NOFOLLOW", 0)
    # O_NONBLOCK: opening a FIFO planted at the path must not hang the reader.
    file_flags = os.O_RDONLY | nofollow | getattr(os, "O_NONBLOCK", 0)
    parts = Path(relative_path).parts
    if not parts:
        raise ContainmentError("NOT_REGULAR_FILE", "Path names no file", relative_path)
    if os.open in os.supports_dir_fd:
        dir_flags = os.O_RDONLY | nofollow | getattr(os, "O_DIRECTORY", 0)
        dir_fd = os.open(physical.root_path, dir_flags)
        try:
            for part in parts[:-1]:
                next_fd = os.open(part, dir_flags, dir_fd=dir_fd)
                os.close(dir_fd)
                dir_fd = next_fd
            fd = os.open(parts[-1], file_flags, dir_fd=dir_fd)
        finally:
            os.close(dir_fd)
    else:
        # ponytail: no dir_fd (Windows) -- open_contained's component walk
        # plus O_NOFOLLOW on the leaf is the check; the fstat checks remain.
        fd = os.open(target, file_flags)
    try:
        st = os.fstat(fd)
        if not stat.S_ISREG(st.st_mode):
            raise ContainmentError(
                "NOT_REGULAR_FILE", "Not a regular file", relative_path
            )
        if st.st_nlink > 1:
            raise ContainmentError(
                "HARDLINK_DISALLOWED",
                "A hard-linked file may alias a file outside the root",
                relative_path,
            )
    except BaseException:
        os.close(fd)
        raise
    return fd


def read_project_artifact_page(
    project: str | Path,
    cursor: str,
    *,
    data_root: Path | None = None,
    offset: int | None = None,
    limit: int = _MAX_ARTIFACT_PAGE_BYTES,
) -> dict[str, Any]:
    """T28-C/T28-E: one bounded byte page of an attempt's captured immutable
    artifact snapshot (`scheduled[].artifact_snapshots`), never the live
    file. `cursor` is base64url JSON `{project_id, run_id, attempt_id,
    tool_id, path, sha256, offset}`. The manifest and the immutable path are
    both reached through `PhysicalRoot.open_contained`, and the snapshot is
    opened by `open_contained_file` (per-component `dir_fd` + `O_NOFOLLOW`,
    no hard link) and must be a regular file of the recorded size.
    Errors are returned as `error`: `invalid_cursor | not_found |
    immutable_content_unavailable | invalid_path | read_failed`. An explicit
    `offset` (the HTTP adapter's byte offset) replaces the cursor's offset,
    under the same validation."""
    record = resolve_project(project, data_root=data_root)
    root = Path(record["root"])
    project_id = record["project_id"]

    def error(kind: str, path: Any = None) -> dict[str, Any]:
        return {"path": path, "error": kind, "content_base64": None}

    try:
        payload = json.loads(_b64url_decode(cursor))
    except (ValueError, TypeError, RecursionError):
        return error("invalid_cursor")
    if not isinstance(payload, dict):
        return error("invalid_cursor")
    run_id = payload.get("run_id")
    attempt_id = payload.get("attempt_id")
    tool_id = payload.get("tool_id")
    rel_path = payload.get("path")
    sha256 = payload.get("sha256")
    if offset is None:
        offset = payload.get("offset", 0)
    if not isinstance(rel_path, str):
        return error("invalid_cursor")
    if (
        payload.get("project_id") != project_id
        or not isinstance(run_id, str)
        or not isinstance(attempt_id, str)
        or not isinstance(tool_id, str)
        or not isinstance(sha256, str)
        or not _MAP_ID_RE.match(run_id)
        or not _MAP_ID_RE.match(attempt_id)
        or type(offset) is not int
        or offset < 0
    ):
        return error("invalid_cursor", rel_path)
    try:
        manifest = _read_contained_manifest(root, run_id, attempt_id)
    except (FileNotFoundError, ValueError):
        return error("not_found", rel_path)
    # Identity is the cursor's project resolved to its root (the manifest was
    # read under that root); a CHECK_SUITE manifest records no project_id, so
    # only a manifest naming a different project is refused.
    if not isinstance(manifest, dict) or manifest.get("project_id", project_id) != (
        project_id
    ):
        return error("not_found", rel_path)
    snapshot = None
    for item in manifest.get("scheduled") or []:
        if isinstance(item, dict) and item.get("candidate_id") == tool_id:
            captured = item.get("artifact_snapshots")
            snapshot = captured.get(rel_path) if isinstance(captured, dict) else None
            break
    if not isinstance(snapshot, dict):
        return error("immutable_content_unavailable", rel_path)
    if snapshot.get("sha256") != sha256:
        return error("invalid_cursor", rel_path)
    total_size = snapshot.get("size")
    immutable_path = snapshot.get("immutable_path")
    if type(total_size) is not int or not isinstance(immutable_path, str):
        return error("immutable_content_unavailable", rel_path)
    limit = max(1, min(limit, _MAX_ARTIFACT_PAGE_BYTES))
    try:
        fd = open_contained_file(root, immutable_path)
    except (ContainmentError, ValueError):
        return error("invalid_path", rel_path)
    except FileNotFoundError:
        # The manifest records this snapshot but its captured bytes are gone:
        # the immutable content is unavailable (never a live-file fallback).
        return error("immutable_content_unavailable", rel_path)
    except OSError:
        return error("invalid_path", rel_path)
    try:
        st = os.fstat(fd)
        if st.st_size != total_size:
            return error("immutable_content_unavailable", rel_path)
        os.lseek(fd, offset, os.SEEK_SET)
        chunk = os.read(fd, limit)
    except OSError:
        return error("read_failed", rel_path)
    finally:
        os.close(fd)
    next_offset = offset + len(chunk)
    next_cursor = (
        _b64url_encode(json.dumps({**payload, "offset": next_offset}).encode("utf-8"))
        if next_offset < total_size
        else None
    )
    return {
        "path": rel_path,
        "run_id": run_id,
        "attempt_id": attempt_id,
        "tool_id": tool_id,
        "label": f"captured snapshot (run {run_id}, attempt {attempt_id})",
        "offset": offset,
        "size": total_size,
        "content_base64": base64.b64encode(chunk).decode("ascii"),
        "next_cursor": next_cursor,
        "sha256": sha256,
        "media_type": snapshot.get("media_type"),
    }


def export_project_artifact(
    project: str | Path,
    *,
    run_id: str,
    attempt_id: str,
    tool_id: str,
    path: str,
    destination: Path,
    permissions: Any,
    data_root: Path | None = None,
    expected_sha256: str | None = None,
) -> dict[str, Any]:
    """Copy one captured artifact snapshot's exact bytes to `destination`.

    Requires `artifact_write`. Bytes come only through `read_project_artifact_page`
    (contained, no subprocess). They land in an `O_EXCL` `<dest>.<uuid>.partial`
    file, are re-checked by SHA-256 and length, then `os.replace`d onto a
    destination that must not exist. An existing destination with identical
    bytes is a no-op; any other existing destination is `FileExistsError`. On
    failure only this call's own partial file is removed."""
    if not getattr(permissions, "artifact_write", False):
        raise PermissionError("artifact export requires the artifact_write grant")
    record = resolve_project(project, data_root=data_root)
    project_id = record["project_id"]
    sha256 = expected_sha256
    if sha256 is None:
        try:
            manifest = _read_contained_manifest(
                Path(record["root"]), run_id, attempt_id
            )
        except (FileNotFoundError, ValueError) as exc:
            raise FileNotFoundError(f"artifact not found: {path}") from exc
        for item in (manifest or {}).get("scheduled") or []:
            if isinstance(item, dict) and item.get("candidate_id") == tool_id:
                snaps = item.get("artifact_snapshots")
                snap = snaps.get(path) if isinstance(snaps, dict) else None
                if isinstance(snap, dict) and isinstance(snap.get("sha256"), str):
                    sha256 = snap["sha256"]
                break
        if sha256 is None:
            raise FileNotFoundError(f"no captured snapshot for artifact: {path}")
    cursor: str | None = _b64url_encode(
        json.dumps(
            {
                "project_id": project_id,
                "run_id": run_id,
                "attempt_id": attempt_id,
                "tool_id": tool_id,
                "path": path,
                "sha256": sha256,
                "offset": 0,
            }
        ).encode("utf-8")
    )
    chunks: list[bytes] = []
    size = 0
    while cursor is not None:
        page = read_project_artifact_page(project_id, cursor, data_root=data_root)
        if page.get("error"):
            raise FileNotFoundError(f"artifact unavailable ({page['error']}): {path}")
        chunks.append(base64.b64decode(page["content_base64"]))
        size = page["size"]
        cursor = page.get("next_cursor")
    data = b"".join(chunks)
    if len(data) != size or hashlib.sha256(data).hexdigest() != sha256:
        raise ValueError(f"artifact bytes do not match their recorded digest: {path}")

    destination = Path(destination)
    result = {"path": str(destination), "size": size, "sha256": sha256}
    if destination.is_symlink() or destination.exists():
        if (
            not destination.is_symlink()
            and destination.is_file()
            and destination.read_bytes() == data
        ):
            return {**result, "noop": True}
        raise FileExistsError(f"export destination already exists: {destination}")
    partial = destination.with_name(f"{destination.name}.{uuid.uuid4().hex}.partial")
    fd = os.open(
        partial, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    )
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        written = partial.read_bytes()
        if len(written) != size or hashlib.sha256(written).hexdigest() != sha256:
            raise OSError(f"export verification failed for {destination}")
        if destination.is_symlink() or destination.exists():
            raise FileExistsError(f"export destination already exists: {destination}")
        os.replace(partial, destination)
    except BaseException:
        partial.unlink(missing_ok=True)
        raise
    return {**result, "noop": False}


__all__ = [
    "CURSOR_KEY_FILE",
    "REGISTRY_LOCK_FILE",
    "AttemptEvidence",
    "ChronologyView",
    "ProjectBusyError",
    "ProjectDestinationExistsError",
    "ProjectError",
    "ProjectInvalidCursorError",
    "ProjectInvalidRequestError",
    "ProjectNotFoundError",
    "ProjectPlanStaleError",
    "ProjectRecord",
    "ProjectRequiredError",
    "ProjectRevisionConflictError",
    "ProjectRootConflictError",
    "ProjectRootMissingError",
    "ProjectSetupRequiredError",
    "RegistryState",
    "compute_settings_plan_id",
    "configure_project",
    "create_project",
    "ensure_cursor_key",
    "expand_artifact_reference",
    "export_project_artifact",
    "export_project_data",
    "get_selected_project",
    "list_project_artifacts",
    "list_projects",
    "list_projects_page",
    "open_contained_file",
    "project_git_branch",
    "project_git_commit_diff",
    "project_git_dirty_diff",
    "project_git_history",
    "project_git_worktree",
    "project_map_snapshot",
    "project_overview_evidence",
    "project_snapshot",
    "project_token_usage",
    "read_project_artifact_page",
    "read_registry_state",
    "register_project",
    "relink_project",
    "resolve_active_project",
    "resolve_project",
    "select_attempt_chronology",
    "select_project",
]
