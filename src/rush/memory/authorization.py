"""73-T02/POLICY: the per-OS-user memory authorization policy.

The policy file lives at `<data_root>/user/.rush/memory_authorization.json` and is
the only authority that lets a memory operation read or write a project's memory.

- `load_policy_readonly` and `resolve_memory_scope` never create anything.
- Writers (`grant_memory_scope`, `revoke_memory_scope`, `register_memory_binding`)
  check consent first, validate pure inputs, then reload, compare revisions and
  write through `CASMapTransaction` while holding `hold_policy_lock`.
- Path and identity strings are stored as lowercase UTF-8 hex so they survive the
  secret redactor that `CASMapTransaction` applies to everything it writes. Every
  consumer must read the policy through `load_policy_readonly`, whose views decode
  those fields.

Import rule: module level imports stdlib plus `rush.setup.provision`,
`rush.memory.transactions`, `rush.io.*` and `rush.safety.redactor` only. The
dashboard lock, the project registry and `OwnerScope` are imported inside the
functions that need them, because `rush.memory.store` and `rush.memory.retrieval`
import this module.
"""

from __future__ import annotations

import copy
import hashlib
import json
import math
import os
import re
import stat
import sys
import time
import unicodedata
import uuid
from collections.abc import Callable, Iterator, Sequence
from contextlib import ExitStack, contextmanager
from pathlib import Path
from typing import TYPE_CHECKING, Any, Self

from rush.io.physical_paths import ContainmentError, PhysicalRoot
from rush.memory.transactions import CASConflictError, CASMapTransaction, StoreError
from rush.safety.redactor import SecretRedactor, sanitize_value
from rush.setup.provision import DataRootUnavailableError, default_data_root

if TYPE_CHECKING:
    from rush.memory.store import OwnerScope

GRANT_OPERATIONS = frozenset(
    {"ask", "bootstrap", "expand", "list", "write", "history", "overlay_read"}
)
POLICY_RELATIVE_PATH = Path("user/.rush/memory_authorization.json")

_ENVELOPE_KEYS = frozenset({"schema_version", "version", "data"})
_DATA_KEYS = frozenset(
    {"schema_version", "policy_revision", "grants", "bindings", "mappings"}
)
_GRANT_KEYS = frozenset(
    {
        "grant_id",
        "principal",
        "project_id",
        "project_root_hex",
        "worktree_id",
        "owner_scope",
        "approved_sources_hex",
        "allowed_operations",
        "consented_at",
        "expires_at",
        "granted_revision",
        "revoked",
        "revoked_at",
        "revoked_revision",
        "superseded_by",
    }
)
_BINDING_KEYS = frozenset(
    {
        "binding_id",
        "grant_id",
        "policy_revision",
        "project_id",
        "worktree_id",
        "scope_fingerprint",
        "host_id_hex",
        "session_id_hex",
        "revoked",
    }
)
_OWNER_KINDS = frozenset({"user", "project", "session", "agent"})
_PRINCIPAL_RE = re.compile(r"uid:\d+|sid:S-1(-\d+)+")
_HEX64_RE = re.compile(r"[0-9a-f]{64}")
_HEX_RE = re.compile(r"(?:[0-9a-f]{2})+")
_LABEL_MAX = 256
_SYMLINK_CODES = frozenset({"SYMLINK_DISALLOWED", "REPARSE_POINT_DISALLOWED"})


class MemoryPolicyError(Exception):
    """A writer refused. `code` is the stable `E_*` code; `reason` narrows it."""

    def __init__(self, code: str, reason: str | None = None) -> None:
        super().__init__(code if reason is None else f"{code}: {reason}")
        self.code = code
        self.reason = reason


class _Invalid(Exception):
    """Internal: the policy file is invalid for `reason`."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


class _Missing(Exception):
    """Internal: the policy file (or a directory above it) does not exist."""


# --- seams -------------------------------------------------------------------


def _now() -> float:
    return time.time()


def _current_os_principal() -> str:
    """`uid:<uid>` on POSIX, `sid:<token user SID>` on Windows. Raises on failure."""
    if sys.platform == "win32":  # pragma: no cover - Windows only
        return _windows_sid_principal()
    return f"uid:{os.getuid()}"


def _windows_sid_principal() -> str:  # pragma: no cover - Windows only
    if sys.platform != "win32":
        raise OSError("SID principals exist only on Windows")
    import ctypes
    from ctypes import wintypes

    advapi32 = ctypes.WinDLL("advapi32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.GetCurrentProcess.restype = wintypes.HANDLE
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.LocalFree.argtypes = [ctypes.c_void_p]
    advapi32.OpenProcessToken.argtypes = [
        wintypes.HANDLE,
        wintypes.DWORD,
        ctypes.POINTER(wintypes.HANDLE),
    ]
    advapi32.GetTokenInformation.argtypes = [
        wintypes.HANDLE,
        ctypes.c_int,
        ctypes.c_void_p,
        wintypes.DWORD,
        ctypes.POINTER(wintypes.DWORD),
    ]
    advapi32.ConvertSidToStringSidW.argtypes = [
        ctypes.c_void_p,
        ctypes.POINTER(wintypes.LPWSTR),
    ]
    token_query, token_user = 0x0008, 1
    token = wintypes.HANDLE()
    if not advapi32.OpenProcessToken(
        kernel32.GetCurrentProcess(), token_query, ctypes.byref(token)
    ):
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        size = wintypes.DWORD()
        advapi32.GetTokenInformation(token, token_user, None, 0, ctypes.byref(size))
        buffer = ctypes.create_string_buffer(size.value)
        if not advapi32.GetTokenInformation(
            token, token_user, buffer, size, ctypes.byref(size)
        ):
            raise ctypes.WinError(ctypes.get_last_error())
        # TOKEN_USER starts with SID_AND_ATTRIBUTES, whose first field is the PSID.
        sid = ctypes.cast(buffer, ctypes.POINTER(ctypes.c_void_p))[0]
        text = wintypes.LPWSTR()
        if not advapi32.ConvertSidToStringSidW(sid, ctypes.byref(text)):
            raise ctypes.WinError(ctypes.get_last_error())
        try:
            value = str(text.value)
        finally:
            kernel32.LocalFree(ctypes.cast(text, ctypes.c_void_p))
    finally:
        kernel32.CloseHandle(token)
    principal = f"sid:{value}"
    if not _PRINCIPAL_RE.fullmatch(principal):
        raise OSError(f"unexpected SID format: {value!r}")
    return principal


# --- paths and identity ------------------------------------------------------


def _data_root(data_root: Path | None) -> Path:
    return Path(data_root or default_data_root()).resolve()


def policy_path(*, data_root: Path | None = None) -> Path:
    """The absolute policy file path for `data_root` (default: the OS data root)."""
    return _writer_root(data_root) / POLICY_RELATIVE_PATH


def _overlay_owner_key(root: Path) -> tuple[str, str]:
    """`(kind, id)` of the overlay owner for the resolved data root `root`."""
    try:
        return "user", str((root / "user").resolve())
    except (OSError, RuntimeError, ValueError):
        raise MemoryPolicyError("E_POLICY_INVALID", "data_root_unavailable") from None


def _overlay_owner(root: Path) -> OwnerScope:
    """The overlay `OwnerScope` for the resolved data root `root`."""
    from rush.memory.store import OwnerScope

    return OwnerScope(*_overlay_owner_key(root))  # type: ignore[arg-type]


def user_overlay_owner_scope(*, data_root: Path | None = None) -> OwnerScope:
    """The owner a personal-overlay grant must carry (72-T05)."""
    return _overlay_owner(_writer_root(data_root))


@contextmanager
def hold_policy_lock(*, data_root: Path | None = None) -> Iterator[None]:
    """Hold the cross-process policy writer lock (reentrant within one thread)."""
    from rush.dashboard.state import cross_process_project_lock

    root = _writer_root(data_root)
    lock_id = "memory-policy:" + str(root / POLICY_RELATIVE_PATH)
    with cross_process_project_lock(lock_id, data_root=root, storage="directory"):
        yield


def _worktree_id(canonical_root: Path) -> str:
    ino = os.stat(canonical_root).st_ino
    return hashlib.sha256(f"{canonical_root}\0{ino}".encode()).hexdigest()


def _registry_lookup(root: Path, canonical: Path) -> tuple[str, str | None]:
    """`(registry state, project_id or None)` for the registered `canonical` root."""
    from rush.workflows.projects import read_registry_strict

    result = read_registry_strict(root)
    state = str(result["state"])
    if state != "ok":
        return state, None
    for project_id, entry in result["registry"]["projects"].items():
        if isinstance(entry, dict) and entry.get("root") == str(canonical):
            return state, str(project_id)
    return state, None


def _registered_root(root: Path, project_id: str) -> str | None:
    from rush.workflows.projects import read_registry_strict

    result = read_registry_strict(root)
    if result["state"] != "ok":
        return None
    entry = result["registry"]["projects"].get(project_id)
    if not isinstance(entry, dict) or not isinstance(entry.get("root"), str):
        return None
    return str(entry["root"])


# --- encoding ----------------------------------------------------------------


def _hex(value: str) -> str:
    return value.encode("utf-8").hex()


def _unhex(value: Any) -> str:
    if not isinstance(value, str) or not _HEX_RE.fullmatch(value):
        raise _Invalid("record_invalid")
    try:
        return bytes.fromhex(value).decode("utf-8")
    except UnicodeDecodeError:
        raise _Invalid("record_invalid") from None


def _is_int(value: Any) -> bool:
    return type(value) is int


def _is_number(value: Any) -> bool:
    """A finite int or float (not bool); an int too large for a float is not."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    try:
        return math.isfinite(value)
    except OverflowError:
        return False


def _is_uuid(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    try:
        return str(uuid.UUID(value)) == value
    except ValueError:
        return False


def _fingerprint(grant: dict[str, Any]) -> str:
    body = {
        key: grant[key]
        for key in (
            "grant_id",
            "granted_revision",
            "principal",
            "project_id",
            "project_root",
            "worktree_id",
            "owner_scope",
            "approved_sources",
            "allowed_operations",
            "expires_at",
        )
    }
    text = json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# --- strict loader -----------------------------------------------------------


def _empty_result(state: str, reason: str, shown: str | None) -> dict[str, Any]:
    return {
        "state": state,
        "reason": reason,
        "policy_path": shown,
        "policy_revision": 0,
        "content_sha256": None,
        "grants": {},
        "bindings": {},
        "mappings": {},
    }


def _lstat(path: Path) -> os.stat_result:
    try:
        return os.lstat(path)
    except FileNotFoundError:
        raise _Missing from None
    except OSError:
        raise _Invalid("unreadable") from None


def _read_policy_bytes(root: Path) -> bytes:
    """Steps 1-5: locate, contain, check and open the policy file; create nothing."""
    try:
        root_stat = os.stat(root)
    except FileNotFoundError:
        raise _Missing from None
    except OSError:
        raise _Invalid("unreadable") from None
    if not stat.S_ISDIR(root_stat.st_mode):
        raise _Invalid("not_directory")
    try:
        PhysicalRoot(root).open_contained(POLICY_RELATIVE_PATH, purpose="read")
    except ContainmentError as exc:
        raise _Invalid(
            "symlink" if exc.code in _SYMLINK_CODES else "path_escape"
        ) from None
    except ValueError:
        raise _Missing from None
    for directory in (root / "user", root / "user" / ".rush"):
        st = _lstat(directory)
        if stat.S_ISLNK(st.st_mode):
            raise _Invalid("symlink")
        if not stat.S_ISDIR(st.st_mode):
            raise _Invalid("not_directory")
    file_path = root / POLICY_RELATIVE_PATH
    file_stat = _lstat(file_path)
    if stat.S_ISLNK(file_stat.st_mode):
        raise _Invalid("symlink")
    if not stat.S_ISREG(file_stat.st_mode):
        raise _Invalid("not_regular_file")
    if os.name == "posix":
        try:
            principal = _current_os_principal()
        except Exception:  # noqa: BLE001 - any seam failure denies
            raise _Invalid("principal_unavailable") from None
        if f"uid:{file_stat.st_uid}" != principal:
            raise _Invalid("foreign_owner")
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_BINARY", 0)
    try:
        fd = os.open(file_path, flags)
    except OSError:
        raise _Invalid("unreadable") from None
    try:
        opened = os.fstat(fd)
        if (opened.st_dev, opened.st_ino) != (file_stat.st_dev, file_stat.st_ino):
            raise _Invalid("file_changed")
        chunks: list[bytes] = []
        while chunk := os.read(fd, 1 << 16):
            chunks.append(chunk)
    except OSError:
        raise _Invalid("unreadable") from None
    finally:
        os.close(fd)
    return b"".join(chunks)


def _reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise _Invalid("duplicate_key")
        result[key] = value
    return result


def _reject_constant(name: str) -> Any:
    raise ValueError(f"non-finite JSON constant {name}")


def _parse(raw: bytes) -> dict[str, Any]:
    """Steps 6-8: parse, then check the envelope and the data object."""
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        raise _Invalid("not_utf8") from None
    try:
        payload = json.loads(
            text, object_pairs_hook=_reject_duplicates, parse_constant=_reject_constant
        )
    except (ValueError, RecursionError):
        raise _Invalid("malformed_json") from None
    if not isinstance(payload, dict) or set(payload) != _ENVELOPE_KEYS:
        raise _Invalid("envelope_invalid")
    schema = payload["schema_version"]
    if not isinstance(schema, str) or schema != "1.0.0":
        raise _Invalid("envelope_invalid")
    version = payload["version"]
    if not _is_int(version) or version < 1:
        raise _Invalid("revision_invalid")
    data = payload["data"]
    if not isinstance(data, dict):
        raise _Invalid("envelope_invalid")
    keys = set(data)
    if keys - _DATA_KEYS:
        raise _Invalid("unknown_field")
    if _DATA_KEYS - keys:
        raise _Invalid("missing_field")
    if not _is_int(data["schema_version"]) or data["schema_version"] != 1:
        raise _Invalid("schema_version_unsupported")
    if not _is_int(data["policy_revision"]) or data["policy_revision"] != version:
        raise _Invalid("revision_mismatch")
    for name in ("grants", "bindings", "mappings"):
        if not isinstance(data[name], dict):
            raise _Invalid("record_invalid")
    return data


def _grant_view(grant_id: Any, record: Any, revision: int) -> dict[str, Any]:
    """Validate one stored grant and decode it into the plan's field names.

    An `overlay_read` grant whose owner kind is not `user` is invalid. The check
    is structural: the exact overlay id is matched only at resolve (stage 13) and
    in the writer, so a moved data root never invalidates the whole file.
    """
    if not isinstance(record, dict) or set(record) != _GRANT_KEYS:
        raise _Invalid("record_invalid")
    if not _is_uuid(grant_id) or record["grant_id"] != grant_id:
        raise _Invalid("record_invalid")
    principal = record["principal"]
    if not isinstance(principal, str) or not _PRINCIPAL_RE.fullmatch(principal):
        raise _Invalid("record_invalid")
    project_id = record["project_id"]
    if not isinstance(project_id, str) or not project_id:
        raise _Invalid("record_invalid")
    project_root = _unhex(record["project_root_hex"])
    worktree_id = record["worktree_id"]
    if not isinstance(worktree_id, str) or not _HEX64_RE.fullmatch(worktree_id):
        raise _Invalid("record_invalid")
    owner = record["owner_scope"]
    if not isinstance(owner, dict) or set(owner) != {"kind", "id_hex"}:
        raise _Invalid("record_invalid")
    owner_id = _unhex(owner["id_hex"])
    kind = owner["kind"]
    if not isinstance(kind, str) or kind not in _OWNER_KINDS or not owner_id.strip():
        raise _Invalid("record_invalid")
    sources_hex = record["approved_sources_hex"]
    if not isinstance(sources_hex, list) or not sources_hex:
        raise _Invalid("record_invalid")
    sources = [_unhex(item) for item in sources_hex]
    if sources != sorted(set(sources)):
        raise _Invalid("record_invalid")
    operations = record["allowed_operations"]
    if (
        not isinstance(operations, list)
        or not operations
        or not all(isinstance(op, str) and op in GRANT_OPERATIONS for op in operations)
        or operations != sorted(set(operations))
    ):
        raise _Invalid("record_invalid")
    if "overlay_read" in operations and owner["kind"] != "user":
        raise _Invalid("record_invalid")
    if not _is_number(record["consented_at"]):
        raise _Invalid("record_invalid")
    if record["expires_at"] is not None and not _is_number(record["expires_at"]):
        raise _Invalid("record_invalid")
    granted = record["granted_revision"]
    if not _is_int(granted) or not 1 <= granted <= revision:
        raise _Invalid("record_invalid")
    revoked = record["revoked"]
    if not isinstance(revoked, bool):
        raise _Invalid("record_invalid")
    superseded_by = record["superseded_by"]
    if revoked:
        revoked_revision = record["revoked_revision"]
        if (
            not _is_number(record["revoked_at"])
            or not _is_int(revoked_revision)
            or not granted <= revoked_revision <= revision
            or (superseded_by is not None and not _is_uuid(superseded_by))
        ):
            raise _Invalid("record_invalid")
    elif (
        record["revoked_at"] is not None
        or record["revoked_revision"] is not None
        or superseded_by is not None
    ):
        raise _Invalid("record_invalid")
    return {
        "grant_id": grant_id,
        "principal": principal,
        "project_id": project_id,
        "project_root": project_root,
        "worktree_id": worktree_id,
        "owner_scope": {"kind": owner["kind"], "id": owner_id},
        "approved_sources": sources,
        "allowed_operations": list(operations),
        "consented_at": record["consented_at"],
        "expires_at": record["expires_at"],
        "granted_revision": granted,
        "revoked": revoked,
        "revoked_at": record["revoked_at"],
        "revoked_revision": record["revoked_revision"],
        "superseded_by": superseded_by,
    }


def _binding_view(binding_id: Any, record: Any, revision: int) -> dict[str, Any]:
    """Validate one stored binding and decode it into the plan's 9 keys."""
    if not isinstance(record, dict) or set(record) != _BINDING_KEYS:
        raise _Invalid("record_invalid")
    if not _is_uuid(binding_id) or record["binding_id"] != binding_id:
        raise _Invalid("record_invalid")
    if not _is_uuid(record["grant_id"]):
        raise _Invalid("record_invalid")
    bound_revision = record["policy_revision"]
    if not _is_int(bound_revision) or not 1 <= bound_revision <= revision:
        raise _Invalid("record_invalid")
    if not isinstance(record["project_id"], str) or not record["project_id"]:
        raise _Invalid("record_invalid")
    for name in ("worktree_id", "scope_fingerprint"):
        value = record[name]
        if not isinstance(value, str) or not _HEX64_RE.fullmatch(value):
            raise _Invalid("record_invalid")
    host_id = _unhex(record["host_id_hex"])
    session_id = _unhex(record["session_id_hex"])
    if not isinstance(record["revoked"], bool):
        raise _Invalid("record_invalid")
    return {
        "binding_id": binding_id,
        "grant_id": record["grant_id"],
        "policy_revision": bound_revision,
        "project_id": record["project_id"],
        "worktree_id": record["worktree_id"],
        "scope_fingerprint": record["scope_fingerprint"],
        "host_id": host_id,
        "session_id": session_id,
        "revoked": record["revoked"],
    }


def _scope_key(record: dict[str, Any]) -> tuple[str, ...]:
    owner = record["owner_scope"]
    return (
        record["principal"],
        record["project_id"],
        record["project_root_hex"],
        record["worktree_id"],
        owner["kind"],
        owner["id_hex"],
    )


def _validate(
    data: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    """Step 9: every record, then dangling bindings, then duplicate active grants."""
    revision = data["policy_revision"]
    grants = {
        gid: _grant_view(gid, rec, revision) for gid, rec in data["grants"].items()
    }
    bindings = {
        bid: _binding_view(bid, rec, revision) for bid, rec in data["bindings"].items()
    }
    mappings = data["mappings"]
    for key, value in mappings.items():
        if not _is_uuid(key) or not isinstance(value, dict):
            raise _Invalid("record_invalid")
    if any(view["grant_id"] not in grants for view in bindings.values()):
        raise _Invalid("dangling_binding")
    seen: set[tuple[str, ...]] = set()
    for record in data["grants"].values():
        if record["revoked"]:
            continue
        key = _scope_key(record)
        if key in seen:
            raise _Invalid("duplicate_active_grant")
        seen.add(key)
    return grants, bindings, copy.deepcopy(mappings)


def _load(data_root: Path | None) -> tuple[dict[str, Any], dict[str, Any] | None]:
    """The strict read: `(public result, stored data or None)`. Creates nothing."""
    try:
        root = _data_root(data_root)
    except DataRootUnavailableError:
        return _empty_result("unavailable", "data_root_unavailable", None), None
    except (OSError, RuntimeError, ValueError, TypeError):
        return _empty_result("unavailable", "data_root_unavailable", None), None
    shown = str(root / POLICY_RELATIVE_PATH)
    try:
        raw = _read_policy_bytes(root)
        data = _parse(raw)
        grants, bindings, mappings = _validate(data)
    except _Missing:
        return _empty_result("missing", "policy_missing", shown), None
    except _Invalid as exc:
        return _empty_result("invalid", exc.reason, shown), None
    result = {
        "state": "ok",
        "reason": "ok",
        "policy_path": shown,
        "policy_revision": data["policy_revision"],
        "content_sha256": hashlib.sha256(raw).hexdigest(),
        "grants": grants,
        "bindings": bindings,
        "mappings": mappings,
    }
    return result, data


def load_policy_readonly(*, data_root: Path | None = None) -> dict[str, Any]:
    """Strictly read the policy without creating anything.

    Returns `state` (`ok`, `missing`, `invalid` or `unavailable`), an exact
    `reason`, the policy path, revision, content sha256 and decoded views of
    grants, bindings and mappings. A non-`ok` state carries revision 0, no sha
    and empty maps.
    """
    result, _data = _load(data_root)
    return result


# --- writers -----------------------------------------------------------------


def _require_consent(consent: Any) -> None:
    if consent is not True:
        raise MemoryPolicyError("E_CONSENT", "consent_required")


def _require_revision(expected: Any) -> int:
    if not _is_int(expected) or expected < 0:
        raise MemoryPolicyError("E_INPUT", "expected_policy_revision")
    return int(expected)


def _string_list(value: Any) -> list[str] | None:
    """A non-`str` sequence of stripped, non-empty strings, else `None`."""
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        return None
    items = list(value)
    if not all(
        isinstance(item, str) and item and item.strip() == item for item in items
    ):
        return None
    return items


def _not_utf8(value: str) -> bool:
    """A lone surrogate (category Cs) is the only `str` UTF-8 cannot encode."""
    return any(unicodedata.category(ch) == "Cs" for ch in value)


def _approved_item_is_valid(item: str) -> bool:
    """D40: an approved item is a literal label or a canonical `<family>:*` item."""
    if "*" not in item:
        return True
    return item.endswith(":*") and item[:-2] in WRITER_SOURCE_FAMILIES


def _require_sources(value: Any) -> list[str]:
    items = _string_list(value)
    if (
        not items
        or len(set(items)) != len(items)
        or "*" in items
        or any(_not_utf8(item) for item in items)
        or not all(_approved_item_is_valid(item) for item in items)
    ):
        raise MemoryPolicyError("E_INPUT", "approved_sources")
    return sorted(items)


# --- D40: writer source families ---------------------------------------------

WRITER_SOURCE_FAMILIES: dict[str, str] = {
    "intent": "intent:",
    "recipe": "recipe:",
    "repair_attempt": "repair_attempt:",
    "invocation": "invocation:",
    "verify_attempt": "verify_attempt:",
}

_WRITER_LITERAL_SOURCES = (
    "session_memory:record_turn",
    "provenance_ai:attribution_link",
    "flight_recorder:record_event",
    "skills_generator:generate_skill_markdown",
    "context_pack",
    "checkpoint_journal:save_checkpoint",
    "migration:preference_store",
    "migration:invariant_graph",
    "migration:merkle_invalidator",
    "migration:checkpoint_journal",
    "migration:failure_ledger",
    "migration:patch_memory",
    "migration:flight_recorder",
    "migration:hook_signatures",
    "migration:session_memory",
)


def literal_source_is_valid(value: object) -> bool:
    """A request source label: non-empty, unpadded, no `*`, no Cc/Cf/Cs character."""
    return (
        isinstance(value, str)
        and bool(value)
        and value.strip() == value
        and "*" not in value
        and not any(unicodedata.category(ch) in {"Cc", "Cf", "Cs"} for ch in value)
    )


def family_prefixes(approved: Sequence[str]) -> list[str]:
    """The canonical family prefixes named by `<family>:*` items of `approved`."""
    return sorted(
        WRITER_SOURCE_FAMILIES[item[:-2]]
        for item in approved
        if isinstance(item, str)
        and item.endswith(":*")
        and item[:-2] in WRITER_SOURCE_FAMILIES
    )


def source_granted(source: Any, approved: Sequence[str]) -> bool:
    """D40: `source` is an approved exact label or has a granted family prefix."""
    if not isinstance(source, str):
        return False
    if source in approved:
        return True
    return any(
        source.startswith(prefix) and len(source) > len(prefix)
        for prefix in family_prefixes(approved)
    )


def writer_source_catalog(project_root: Path) -> list[str]:
    """Every source an internal (D4) writer records under, in D40 order."""
    return [
        *_WRITER_LITERAL_SOURCES,
        str(Path(project_root).resolve()),
        *(f"{family}*" for family in WRITER_SOURCE_FAMILIES.values()),
    ]


def _require_operations(value: Any) -> list[str]:
    items = _string_list(value)
    if not items or len(set(items)) != len(items) or not set(items) <= GRANT_OPERATIONS:
        raise MemoryPolicyError("E_INPUT", "allowed_operations")
    return sorted(items)


def _require_expiry(value: Any) -> float | None:
    if value is None:
        return None
    if not _is_number(value) or not value > _now():
        raise MemoryPolicyError("E_INPUT", "expires_at")
    return float(value)


def _owner_tuple(value: Any) -> tuple[str, str] | None:
    from rush.memory.store import OwnerScope

    try:
        owner = OwnerScope.from_value(value)
    except (TypeError, ValueError):
        return None
    if _not_utf8(owner.id):
        return None
    return str(owner.kind), owner.id


def _require_label(value: Any, name: str) -> str:
    if (
        not isinstance(value, str)
        or not value
        or len(value) > _LABEL_MAX
        or any(unicodedata.category(ch) in ("Cc", "Cf", "Cs") for ch in value)
    ):
        raise MemoryPolicyError("E_INPUT", name)
    if SecretRedactor.redact_text(value) != value:
        raise MemoryPolicyError("E_INPUT", "secret_like_value")
    return value


def _writer_root(data_root: Path | None) -> Path:
    try:
        return _data_root(data_root)
    except (DataRootUnavailableError, OSError, RuntimeError, ValueError, TypeError):
        raise MemoryPolicyError("E_POLICY_INVALID", "data_root_unavailable") from None


def _writer_principal() -> str:
    try:
        principal = _current_os_principal()
    except Exception:  # noqa: BLE001 - any seam failure denies
        raise MemoryPolicyError("E_PRINCIPAL", "principal_unavailable") from None
    if not _PRINCIPAL_RE.fullmatch(principal):
        raise MemoryPolicyError("E_PRINCIPAL", "principal_unavailable")
    return principal


def _canonical_project(project_root: Any) -> Path:
    try:
        canonical = Path(project_root).resolve()
        is_dir = canonical.is_dir()
    except (TypeError, OSError, RuntimeError, ValueError):
        raise MemoryPolicyError("E_INPUT", "project_missing") from None
    if not is_dir or _not_utf8(str(canonical)):
        raise MemoryPolicyError("E_INPUT", "project_missing")
    return canonical


def _locked(root: Path) -> ExitStack:
    """Enter `hold_policy_lock`; an `OSError` while acquiring it is `E_LOCK`."""
    stack = ExitStack()
    try:
        stack.enter_context(hold_policy_lock(data_root=root))
    except OSError as exc:
        stack.close()
        raise MemoryPolicyError("E_LOCK", str(exc)) from exc
    return stack


def _reload(root: Path) -> tuple[int, dict[str, Any], dict[str, Any]]:
    """Strict reload under the lock: `(revision, public result, mutable data)`."""
    result, data = _load(root)
    if result["state"] == "missing":
        empty = {
            "schema_version": 1,
            "policy_revision": 0,
            "grants": {},
            "bindings": {},
            "mappings": {},
        }
        return 0, result, empty
    if result["state"] != "ok" or data is None:
        raise MemoryPolicyError("E_POLICY_INVALID", result["reason"])
    return int(result["policy_revision"]), result, copy.deepcopy(data)


def _check_version(expected: int, current: int) -> None:
    if expected != current:
        raise MemoryPolicyError(
            "E_VERSION", f"expected revision {expected}, found {current}"
        )


def _commit(root: Path, current: int, new_data: dict[str, Any]) -> None:
    """Redaction precheck, then the CAS write and its snapshot check."""
    if sanitize_value(new_data).redacted:
        raise MemoryPolicyError("E_POLICY_REDACTION", "secret_like_value")
    try:
        snapshot = CASMapTransaction(
            file_path=POLICY_RELATIVE_PATH, root_path=root
        ).write(new_data, expected_version=current)
    except CASConflictError:
        raise MemoryPolicyError("E_VERSION", "cas_conflict") from None
    except (StoreError, ContainmentError, ValueError, OSError) as exc:
        raise MemoryPolicyError("E_POLICY_IO", str(exc)) from exc
    if snapshot.version != current + 1 or snapshot.data != new_data:
        raise MemoryPolicyError("E_POLICY_IO", "written_snapshot_mismatch")


def _revoke_bindings(data: dict[str, Any], grant_id: str) -> list[str]:
    revoked: list[str] = []
    for binding_id, record in data["bindings"].items():
        if record["grant_id"] == grant_id and not record["revoked"]:
            record["revoked"] = True
            revoked.append(binding_id)
    return sorted(revoked)


def _grant_result(view: dict[str, Any]) -> dict[str, Any]:
    return {
        "grant_id": view["grant_id"],
        "policy_revision": view["granted_revision"],
        "project_id": view["project_id"],
        "worktree_id": view["worktree_id"],
        "owner_scope": dict(view["owner_scope"]),
        "approved_sources": list(view["approved_sources"]),
        "allowed_operations": list(view["allowed_operations"]),
    }


# --- D1 registration marker and `.rush/.gitignore` ----------------------------

REGISTRATION_MARKER = "memory-policy.required"
_PENDING_PREFIX = REGISTRATION_MARKER + ".pending-"
_GITIGNORE_PATTERN = b"memory-policy.required*"
_GITIGNORE_MAX = 65536
_GITIGNORE_ERRORS = (OSError, ContainmentError, ValueError, RuntimeError, UnicodeError)
_MARKER_ERRORS = (OSError, ContainmentError, ValueError, RuntimeError)


def _soft_flags() -> int:
    """`O_NOFOLLOW | O_NONBLOCK | O_BINARY` where the platform has them."""
    return (
        getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_NONBLOCK", 0)
        | getattr(os, "O_BINARY", 0)
    )


def _marker_io(exc: BaseException) -> MemoryPolicyError:
    return MemoryPolicyError("E_POLICY_IO", "registration_marker")


class _RushDir:
    """The canonical project's `.rush` directory for the D1 marker writer.

    POSIX (`os.open in os.supports_dir_fd`) works through `O_NOFOLLOW`
    directory fds; otherwise each step is a path operation preceded by a
    `PhysicalRoot.open_contained` check. `created` records whether this call
    made `.rush`.
    """

    def __init__(self, canonical: Path) -> None:
        self.canonical = canonical
        self.use_fd = os.open in os.supports_dir_fd
        self.root_fd: int | None = None
        self.rush_fd: int | None = None
        self.created = False

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *exc: object) -> None:
        for fd in (self.rush_fd, self.root_fd):
            if fd is not None:
                try:
                    os.close(fd)
                except OSError:
                    pass
        self.rush_fd = self.root_fd = None

    def _contained(self, rel: str) -> Path:
        return PhysicalRoot(self.canonical).open_contained(rel, purpose="write")

    def open(self) -> None:
        """Open (creating when absent) `.rush`; raises on any failure."""
        if self.use_fd:
            dir_flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
            dir_flags |= getattr(os, "O_NOFOLLOW", 0)
            if self.root_fd is None:
                self.root_fd = os.open(self.canonical, dir_flags)
            if self.rush_fd is None:
                try:
                    self.rush_fd = os.open(".rush", dir_flags, dir_fd=self.root_fd)
                except FileNotFoundError:
                    os.mkdir(".rush", 0o700, dir_fd=self.root_fd)
                    self.created = True
                    self.rush_fd = os.open(".rush", dir_flags, dir_fd=self.root_fd)
            return
        path = self._contained(".rush")
        if not os.path.lexists(path):
            os.mkdir(path, 0o700)
            self.created = True
        elif not path.is_dir():
            raise NotADirectoryError(str(path))

    def open_file(self, name: str, flags: int, mode: int = 0o600) -> int:
        self.open()
        if self.use_fd:
            return os.open(name, flags, mode, dir_fd=self.rush_fd)
        return os.open(self._contained(f".rush/{name}"), flags, mode)

    def unlink(self, name: str) -> None:
        self.open()
        if self.use_fd:
            os.unlink(name, dir_fd=self.rush_fd)
        else:
            os.unlink(self._contained(f".rush/{name}"))

    def listdir(self) -> list[str]:
        self.open()
        if self.use_fd:
            assert self.rush_fd is not None
            return os.listdir(self.rush_fd)
        return os.listdir(self._contained(".rush"))

    def rmdir_if_created(self) -> None:
        if not self.created:
            return
        try:
            if self.use_fd:
                if self.rush_fd is not None:
                    os.close(self.rush_fd)
                    self.rush_fd = None
                os.rmdir(".rush", dir_fd=self.root_fd)
            else:
                os.rmdir(self._contained(".rush"))
        except _MARKER_ERRORS:
            pass

    def _create_empty(self, name: str) -> None:
        flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY
        flags |= getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_BINARY", 0)
        os.close(self.open_file(name, flags, 0o600))

    def create_pending_marker(self) -> str:
        """Create this call's pending marker; any failure is `E_POLICY_IO`."""
        name = _PENDING_PREFIX + uuid.uuid4().hex
        try:
            self._create_empty(name)
        except _MARKER_ERRORS as exc:
            raise _marker_io(exc) from exc
        return name

    def ensure_final_marker(self) -> None:
        """The final marker exists afterwards; any failure is `E_POLICY_IO`."""
        try:
            self._create_empty(REGISTRATION_MARKER)
        except FileExistsError:
            return
        except _MARKER_ERRORS as exc:
            raise _marker_io(exc) from exc

    def promote_pending(self, pending: str) -> None:
        """Rename the pending marker onto the final one; a failure keeps it."""
        try:
            self.open()
            if self.use_fd:
                os.rename(
                    pending,
                    REGISTRATION_MARKER,
                    src_dir_fd=self.rush_fd,
                    dst_dir_fd=self.rush_fd,
                )
            else:
                src = self._contained(f".rush/{pending}")
                dst = self._contained(f".rush/{REGISTRATION_MARKER}")
                os.replace(src, dst)
        except _MARKER_ERRORS:
            pass


def _ignore_needs_pattern(data: bytes) -> bool:
    last: bytes | None = None
    for line in data.split(b"\n"):
        if line.endswith(b"\r"):
            line = line[:-1]
        stripped = line.strip(b" \t")
        if not stripped or stripped.startswith(b"#"):
            continue
        last = line
    return last not in (b"*", _GITIGNORE_PATTERN)


def _gitignore_step(rush: _RushDir) -> tuple[str, int, int] | None:
    """Make `.rush/.gitignore` ignore the marker; failures are swallowed.

    Returns this step's effect for an undo: `("created", 0, 0)` or
    `("appended", size_before, appended_length)`, else `None`.
    """
    soft = _soft_flags()
    try:
        try:
            fd = rush.open_file(
                ".gitignore", os.O_CREAT | os.O_EXCL | os.O_WRONLY | soft, 0o644
            )
        except FileExistsError:
            pass
        else:
            try:
                os.write(fd, b"*\n")
            finally:
                os.close(fd)
            return ("created", 0, 0)
        fd = rush.open_file(".gitignore", os.O_RDONLY | soft)
        try:
            info = os.fstat(fd)
            if not stat.S_ISREG(info.st_mode) or info.st_size > _GITIGNORE_MAX:
                return None
            chunks: list[bytes] = []
            while chunk := os.read(fd, 65536):
                chunks.append(chunk)
                if sum(len(c) for c in chunks) > _GITIGNORE_MAX:
                    return None
        finally:
            os.close(fd)
        data = b"".join(chunks)
        if not _ignore_needs_pattern(data):
            return None
        extra = (b"\n" if data and not data.endswith(b"\n") else b"") + (
            _GITIGNORE_PATTERN + b"\n"
        )
        fd = rush.open_file(".gitignore", os.O_WRONLY | os.O_APPEND | soft)
        try:
            if not stat.S_ISREG(os.fstat(fd).st_mode):
                return None
            os.write(fd, extra)
        finally:
            os.close(fd)
        return ("appended", len(data), len(extra))
    except _GITIGNORE_ERRORS:
        return None


def _undo_gitignore(rush: _RushDir, effect: tuple[str, int, int] | None) -> None:
    if effect is None:
        return
    try:
        if effect[0] == "created":
            rush.unlink(".gitignore")
            return
        _kind, before, appended = effect
        fd = rush.open_file(".gitignore", os.O_WRONLY | _soft_flags())
        try:
            info = os.fstat(fd)
            if stat.S_ISREG(info.st_mode) and info.st_size == before + appended:
                os.ftruncate(fd, before)
        finally:
            os.close(fd)
    except _GITIGNORE_ERRORS:
        pass


def _undo_registration(
    rush: _RushDir,
    pending: str | None,
    effects: list[tuple[str, int, int] | None],
) -> None:
    """A failed new grant: drop this call's pending marker and `.gitignore`
    effects (newest first), keep another call's marker ignored, and remove a
    `.rush` this call created."""
    if pending is not None:
        try:
            rush.unlink(pending)
        except _MARKER_ERRORS:
            pass
    for effect in effects:
        _undo_gitignore(rush, effect)
    try:
        if any(n.startswith(REGISTRATION_MARKER) for n in rush.listdir()):
            _gitignore_step(rush)
    except _MARKER_ERRORS:
        pass
    rush.rmdir_if_created()


def grant_memory_scope(
    *,
    project_root: Path,
    owner_scope: OwnerScope,
    approved_sources: Sequence[str],
    allowed_operations: Sequence[str],
    expected_policy_revision: int,
    consent: bool,
    expires_at: float | None = None,
    data_root: Path | None = None,
) -> dict[str, Any]:
    """Grant (or supersede) one scope after explicit consent.

    The scope key is `(principal, project_id, project_root, worktree_id,
    owner_scope)`. An identical active grant is returned without a write; a
    changed one supersedes the active grant and revokes its bindings in the
    same CAS write.
    """
    _require_consent(consent)
    expected = _require_revision(expected_policy_revision)
    owner = _owner_tuple(owner_scope)
    if owner is None:
        raise MemoryPolicyError("E_INPUT", "owner_scope")
    sources = _require_sources(approved_sources)
    operations = _require_operations(allowed_operations)
    expiry = _require_expiry(expires_at)
    root = _writer_root(data_root)
    if "overlay_read" in operations:
        overlay = user_overlay_owner_scope(data_root=root)
        if owner != (overlay.kind, overlay.id):
            raise MemoryPolicyError("E_INPUT", "overlay_read_requires_overlay_owner")
    canonical = _canonical_project(project_root)
    registry_state, project_id = _registry_lookup(root, canonical)
    if project_id is None:
        reason = (
            "project_registry_invalid"
            if registry_state in ("corrupt", "unreadable")
            else "project_not_registered"
        )
        raise MemoryPolicyError("E_PROJECT_NOT_REGISTERED", reason)
    try:
        worktree_id = _worktree_id(canonical)
    except OSError:
        raise MemoryPolicyError("E_INPUT", "project_missing") from None
    principal = _writer_principal()
    sources_hex = [_hex(source) for source in sources]
    key = (
        principal,
        project_id,
        _hex(str(canonical)),
        worktree_id,
        owner[0],
        _hex(owner[1]),
    )

    with _locked(root):
        current, loaded, data = _reload(root)
        grants = data["grants"]
        active = [
            gid
            for gid, record in grants.items()
            if not record["revoked"] and _scope_key(record) == key
        ]
        for gid in active:
            record = grants[gid]
            if (
                record["approved_sources_hex"] == sources_hex
                and record["allowed_operations"] == operations
                and record["expires_at"] == expiry
            ):
                with _RushDir(canonical) as rush:
                    _gitignore_step(rush)
                    rush.ensure_final_marker()
                return _grant_result(loaded["grants"][gid])
        _check_version(expected, current)
        with _RushDir(canonical) as rush:
            return _grant_new(
                rush, root, current, data, key, sources_hex, operations, expiry
            )


def _grant_new(
    rush: _RushDir,
    root: Path,
    current: int,
    data: dict[str, Any],
    key: tuple[str, ...],
    sources_hex: list[str],
    operations: list[str],
    expiry: float | None,
) -> dict[str, Any]:
    """D1: write a new grant with its pending registration marker and the
    `.rush/.gitignore` step around the CAS commit (lock held by the caller)."""
    undo_first = _gitignore_step(rush)
    try:
        pending = rush.create_pending_marker()
    except MemoryPolicyError:
        _undo_registration(rush, None, [undo_first])
        raise
    undo_second = _gitignore_step(rush)
    try:
        result = _commit_new_grant(
            root, current, data, key, sources_hex, operations, expiry
        )
    except MemoryPolicyError as exc:
        try:
            landed = _reload(root)[0] > current
        except MemoryPolicyError:
            raise exc from None
        if landed:
            rush.promote_pending(pending)
        else:
            _undo_registration(rush, pending, [undo_second, undo_first])
        raise
    rush.promote_pending(pending)
    return result


def _commit_new_grant(
    root: Path,
    current: int,
    data: dict[str, Any],
    key: tuple[str, ...],
    sources_hex: list[str],
    operations: list[str],
    expiry: float | None,
) -> dict[str, Any]:
    grants = data["grants"]
    active = [
        gid
        for gid, record in grants.items()
        if not record["revoked"] and _scope_key(record) == key
    ]
    principal, project_id, _root_hex, worktree_id, owner_kind, owner_hex = key
    revision = current + 1
    now = _now()
    grant_id = str(uuid.uuid4())
    for gid in active:
        grants[gid].update(
            revoked=True,
            revoked_at=now,
            revoked_revision=revision,
            superseded_by=grant_id,
        )
        _revoke_bindings(data, gid)
    record = {
        "grant_id": grant_id,
        "principal": principal,
        "project_id": project_id,
        "project_root_hex": key[2],
        "worktree_id": worktree_id,
        "owner_scope": {"kind": owner_kind, "id_hex": owner_hex},
        "approved_sources_hex": sources_hex,
        "allowed_operations": operations,
        "consented_at": now,
        "expires_at": expiry,
        "granted_revision": revision,
        "revoked": False,
        "revoked_at": None,
        "revoked_revision": None,
        "superseded_by": None,
    }
    grants[grant_id] = record
    data["policy_revision"] = revision
    _commit(root, current, data)
    return _grant_result(_grant_view(grant_id, record, revision))


def revoke_memory_scope(
    *,
    grant_id: str,
    expected_policy_revision: int,
    consent: bool,
    data_root: Path | None = None,
) -> dict[str, Any]:
    """Revoke one grant and every binding on it. Revoking twice is a no-op."""
    _require_consent(consent)
    expected = _require_revision(expected_policy_revision)
    if not isinstance(grant_id, str) or not grant_id:
        raise MemoryPolicyError("E_INPUT", "grant_id")
    root = _writer_root(data_root)
    principal = _writer_principal()

    with _locked(root):
        current, _loaded, data = _reload(root)
        record = data["grants"].get(grant_id)
        if record is None:
            raise MemoryPolicyError("E_GRANT_NOT_FOUND", grant_id)
        if record["principal"] != principal:
            raise MemoryPolicyError("E_PRINCIPAL", "principal_mismatch")
        if record["revoked"]:
            return {
                "grant_id": grant_id,
                "policy_revision": record["revoked_revision"],
                "revoked": True,
                "revoked_bindings": sorted(
                    bid
                    for bid, binding in data["bindings"].items()
                    if binding["grant_id"] == grant_id
                ),
            }
        _check_version(expected, current)
        revision = current + 1
        record.update(revoked=True, revoked_at=_now(), revoked_revision=revision)
        revoked_bindings = _revoke_bindings(data, grant_id)
        data["policy_revision"] = revision
        _commit(root, current, data)
        return {
            "grant_id": grant_id,
            "policy_revision": revision,
            "revoked": True,
            "revoked_bindings": revoked_bindings,
        }


def _still_mapped(root: Path, grant: dict[str, Any]) -> bool:
    """The grant's project id still maps to its root, with the same worktree."""
    if _registered_root(root, grant["project_id"]) != grant["project_root"]:
        return False
    try:
        return _worktree_id(Path(grant["project_root"])) == grant["worktree_id"]
    except OSError:
        return False


def register_memory_binding(
    *,
    grant_id: str,
    session_id: str,
    host_id: str,
    expected_policy_revision: int,
    consent: bool,
    data_root: Path | None = None,
) -> dict[str, Any]:
    """Bind one host session to an active grant. Host and session are attribution only."""
    _require_consent(consent)
    expected = _require_revision(expected_policy_revision)
    if not isinstance(grant_id, str) or not grant_id:
        raise MemoryPolicyError("E_INPUT", "grant_id")
    session = _require_label(session_id, "session_id")
    host = _require_label(host_id, "host_id")
    root = _writer_root(data_root)
    principal = _writer_principal()

    with _locked(root):
        current, loaded, data = _reload(root)
        grant = loaded["grants"].get(grant_id)
        if grant is None:
            raise MemoryPolicyError("E_GRANT_NOT_FOUND", grant_id)
        if grant["principal"] != principal:
            raise MemoryPolicyError("E_PRINCIPAL", "principal_mismatch")
        if grant["revoked"]:
            raise MemoryPolicyError("E_GRANT_INACTIVE", "revoked")
        if grant["expires_at"] is not None and not _now() < grant["expires_at"]:
            raise MemoryPolicyError("E_GRANT_INACTIVE", "expired")
        if not _still_mapped(root, grant):
            raise MemoryPolicyError("E_GRANT_INACTIVE", "relinked")
        session_hex, host_hex = _hex(session), _hex(host)
        for binding_id, record in data["bindings"].items():
            if (
                record["grant_id"] == grant_id
                and not record["revoked"]
                and record["session_id_hex"] == session_hex
                and record["host_id_hex"] == host_hex
            ):
                return dict(loaded["bindings"][binding_id])
        _check_version(expected, current)
        revision = current + 1
        binding_id = str(uuid.uuid4())
        record = {
            "binding_id": binding_id,
            "grant_id": grant_id,
            "policy_revision": revision,
            "project_id": grant["project_id"],
            "worktree_id": grant["worktree_id"],
            "scope_fingerprint": _fingerprint(grant),
            "host_id_hex": host_hex,
            "session_id_hex": session_hex,
            "revoked": False,
        }
        data["bindings"][binding_id] = record
        data["policy_revision"] = revision
        _commit(root, current, data)
        return _binding_view(binding_id, record, revision)


# --- resolve -----------------------------------------------------------------


def _denied(reason: str, operation: Any, policy_revision: int) -> dict[str, Any]:
    return {
        "access": "denied",
        "reason": reason,
        "operation": operation if isinstance(operation, str) else None,
        "grant_id": None,
        "grant_revision": None,
        "policy_revision": policy_revision,
        "project_id": None,
        "worktree_id": None,
        "project_root": None,
        "owner_scope": None,
        "approved_sources": [],
        "allowed_operations": [],
        "session_binding": None,
    }


def _owner_of(grant: dict[str, Any]) -> tuple[str, str]:
    return grant["owner_scope"]["kind"], grant["owner_scope"]["id"]


def resolve_memory_scope(
    *,
    project_root: Path,
    operation: str,
    owner_scope: OwnerScope | None = None,
    requested_sources: Sequence[str] = (),
    session_binding: str | None = None,
    data_root: Path | None = None,
) -> dict[str, Any]:
    """Decide one memory operation from scratch. Never raises.

    Returns the same 13 keys on success and denial. A denial carries exactly
    one reason and no grant-derived values.
    """
    try:
        return _resolve(
            project_root=project_root,
            operation=operation,
            owner_scope=owner_scope,
            requested_sources=requested_sources,
            session_binding=session_binding,
            data_root=data_root,
        )
    except Exception:  # noqa: BLE001 - resolve never raises
        return _denied("policy_invalid", operation, 0)


def _resolve(
    *,
    project_root: Any,
    operation: Any,
    owner_scope: Any,
    requested_sources: Any,
    session_binding: Any,
    data_root: Path | None,
) -> dict[str, Any]:
    # Stage 0: request types and operation name.
    if not isinstance(operation, str) or operation not in GRANT_OPERATIONS:
        return _denied("invalid_request", operation, 0)
    if not isinstance(project_root, (str, os.PathLike)):
        return _denied("invalid_request", operation, 0)
    target: tuple[str, str] | None = None
    if owner_scope is not None:
        target = _owner_tuple(owner_scope)
        if target is None:
            return _denied("invalid_request", operation, 0)
    requested = _string_list(requested_sources)
    if requested is None or not all(literal_source_is_valid(s) for s in requested):
        return _denied("invalid_request", operation, 0)
    if session_binding is not None and not isinstance(session_binding, str):
        return _denied("invalid_request", operation, 0)

    # Stage 1: policy state, before any registry or project access.
    loaded, _data = _load(data_root)
    if loaded["state"] == "missing":
        return _denied("policy_missing", operation, 0)
    if loaded["state"] != "ok":
        return _denied("policy_invalid", operation, 0)
    revision = int(loaded["policy_revision"])

    def deny(reason: str) -> dict[str, Any]:
        return _denied(reason, operation, revision)

    # Stage 2: OS principal.
    try:
        principal = _current_os_principal()
    except Exception:  # noqa: BLE001 - any seam failure denies
        return deny("principal_unavailable")

    # Stage 3: canonical root is a directory.
    try:
        canonical = Path(project_root).resolve()
        if not canonical.is_dir() or _not_utf8(str(canonical)):
            return deny("project_missing")
        worktree_id = _worktree_id(canonical)
    except (OSError, RuntimeError, ValueError):
        return deny("project_missing")
    root_text = str(canonical)

    # Stage 4: registry.
    root = _data_root(data_root)
    registry_state, project_id = _registry_lookup(root, canonical)
    if registry_state in ("corrupt", "unreadable"):
        return deny("project_registry_invalid")

    # Stage 5: session binding narrows the candidates to its grant.
    grants: dict[str, dict[str, Any]] = loaded["grants"]
    binding: dict[str, Any] | None = None
    if session_binding is not None:
        binding = loaded["bindings"].get(session_binding)
        if binding is None:
            return deny("binding_unknown")
        if binding["revoked"]:
            return deny("binding_revoked")
        candidates = [grants[binding["grant_id"]]]
    else:
        candidates = list(grants.values())

    # Stage 6: related grants.
    candidates = [
        g
        for g in candidates
        if g["project_root"] == root_text
        or (project_id is not None and g["project_id"] == project_id)
    ]
    if not candidates:
        if binding is not None:
            return deny("binding_scope_mismatch")
        if project_id is None:
            return deny("project_not_registered")
        return deny("no_grant")

    # Stages 7-11. With an explicit owner, the owner's own grants are the
    # candidate set; if the owner holds none, the reason comes from the full
    # related set until stage 12 reports `owner_not_granted`.
    now = _now()
    checks: list[tuple[str, Callable[[dict[str, Any]], bool]]] = [
        ("principal_mismatch", lambda g: g["principal"] == principal),
        (
            "relinked",
            lambda g: g["project_id"] == project_id and g["project_root"] == root_text,
        ),
        ("worktree_mismatch", lambda g: g["worktree_id"] == worktree_id),
        ("revoked", lambda g: not g["revoked"]),
        ("expired", lambda g: g["expires_at"] is None or now < g["expires_at"]),
    ]
    owned = [g for g in candidates if _owner_of(g) == target] if target else []
    for reason, passes in checks:
        candidates = [g for g in candidates if passes(g)]
        if not candidates:
            return deny(reason)
        if owned:
            owned = [g for g in owned if passes(g)]
            if not owned:
                return deny(reason)

    # Stage 12: owner.
    overlay_owner = _overlay_owner_key(root)
    if target is not None:
        if not owned:
            return deny("owner_not_granted")
        candidates = owned
    else:
        # A stale overlay grant (data root moved) is still an overlay grant.
        candidates = [
            g
            for g in candidates
            if _owner_of(g) != overlay_owner
            and not (
                g["owner_scope"]["kind"] == "user"
                and "overlay_read" in g["allowed_operations"]
            )
        ]
        owners = {_owner_of(g) for g in candidates}
        if not owners:
            return deny("owner_not_granted")
        if len(owners) > 1:
            return deny("owner_required")
    if len(candidates) != 1:
        return deny("policy_invalid")
    grant = candidates[0]

    # Stage 13: operation. `overlay_read` only ever flows through the overlay
    # owner's grant. The loader only rejects a non-`user` owner, so this exact
    # match denies a stale overlay grant left by a moved data root.
    if operation not in grant["allowed_operations"] or (
        operation == "overlay_read" and _owner_of(grant) != overlay_owner
    ):
        return deny("operation_not_granted")

    # Stage 14: sources (an empty request means all of the grant's sources).
    sources = sorted(set(requested)) or list(grant["approved_sources"])
    if not all(source_granted(s, grant["approved_sources"]) for s in sources):
        return deny("source_not_granted")

    # Stage 15: binding fingerprint, project and worktree.
    if binding is not None and (
        binding["scope_fingerprint"] != _fingerprint(grant)
        or binding["project_id"] != project_id
        or binding["worktree_id"] != worktree_id
    ):
        return deny("binding_stale")

    return {
        "access": "write" if operation == "write" else "read",
        "reason": "granted",
        "operation": operation,
        "grant_id": grant["grant_id"],
        "grant_revision": grant["granted_revision"],
        "policy_revision": revision,
        "project_id": project_id,
        "worktree_id": worktree_id,
        "project_root": root_text,
        "owner_scope": dict(grant["owner_scope"]),
        "approved_sources": sources,
        "allowed_operations": list(grant["allowed_operations"]),
        "session_binding": binding["binding_id"] if binding is not None else None,
    }
