"""73-T09/CODEC: the portable capsule codec behind `rush_memory(operation="capsule")`.

`rush_v1` is one canonical JSON capsule. `pas_v1` is the pinned PAS-Agent schema-1
session file plus a `<output>.rush-manifest.json` sidecar that carries the full
`rush_v1` capsule. Export reads only authorized, usable current rows; import never
writes outside the 72-T06 import seam. Previews create nothing; every refusal is a
result (`{"code": ..., ...}`), never an exception.
"""

from __future__ import annotations

import contextlib
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
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import ROUND_FLOOR, Decimal
from pathlib import Path
from typing import Any, Literal, cast

import rush
from rush.delivery.compact import canonical_json
from rush.io.atomic_file import AtomicFile, SanitizedBytes, SanitizedJsonValue
from rush.io.physical_paths import ContainmentError, PhysicalRoot
from rush.memory import authorization as auth
from rush.memory import retrieval
from rush.memory.retrieval import MemoryAccess
from rush.memory.store import (
    MemoryMigrationRequiredError,
    MemoryStoreUnreadableError,
    OwnerScope,
    TypedArtifactStore,
    readonly_view_reason,
    store_generation,
)
from rush.permissions import ExecutionPermissions, check_permissions

HARD_MAX_BYTES = 1_048_576
HARD_MAX_TOKENS = 131_072
DEFAULT_MAX_BYTES = 65_536
DEFAULT_MAX_TOKENS = 8_192
MAX_DEPTH = 16
MAX_EVIDENCE = 128
MAX_PAS_CHECKPOINTS = 10
MAX_FILES_CHANGED = 50
_SQLITE_MAX = 2**63 - 1

_STORE_DB = "memory.db"
_IMPORT_TARGET = ".rush/" + _STORE_DB
_RESERVED_PREFIXES = (_STORE_DB, "preferences.json", "memory-policy.required")
_SIDECAR_SUFFIX = ".rush-manifest.json"
_JOURNAL_SUFFIX = ".rush-journal.json"
_TARGET_LOCK_PREFIX = "memory-capsule-target:"
_ZERO_UUID = "00000000-0000-0000-0000-000000000000"
_MAPPING_REQUIREMENT = "origin_pair_mismatch_requires_local_approval"
_ENDED_EVENTS = frozenset({"task_end", "task_cancel"})
_OWNER_KINDS = frozenset({"user", "project", "session", "agent"})

_ACTIONS = ("preview_export", "export", "preview_import", "import", "bridge")
_EXPORT_ACTIONS = ("preview_export", "export")
_IMPORT_ACTIONS = ("preview_import", "import")
_FORMATS = ("rush_v1", "pas_v1")
_SELECTOR_KEYS = frozenset({"task_ref", "owner_scope", "sources", "include_personal"})

_UUID_RE = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")
_HEX64_RE = re.compile(r"[0-9a-f]{64}")
_PAS_HYPHENATED_RE = re.compile(
    r"[0-9A-Fa-f]{8}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{12}"
)
_PAS_SIMPLE_RE = re.compile(r"[0-9A-Fa-f]{32}")
_PAS_TIME_RE = re.compile(
    r"(\d{4})-(\d{2})-(\d{2})[Tt ]\s*(\d{2}):(\d{2}):(\d{2})(?:\.(\d+))?\s*"
    r"(Z|z|UTC|[+-]\d{2}:?\d{2})"
)
_JSON_STRING_RE = re.compile(r'"(?:[^"\\]|\\.)*"', re.DOTALL)
_BRACKET_RE = re.compile(r"[\[\]{}]")
_DRIVE_RE = re.compile(r"[A-Za-z]:")

_CAPSULE_KEYS = frozenset(
    {
        "schema_version",
        "format",
        "capsule_id",
        "created_at",
        "origin",
        "scope",
        "task",
        "evidence",
        "manifest",
        "payload_sha256",
    }
)
_ORIGIN_KEYS = frozenset(
    {"rush_version", "project_id", "worktree_id", "git", "store_revision"}
)
_GIT_KEYS = frozenset({"commit", "branch", "dirty"})
_SCOPE_KEYS = frozenset({"owner", "sources", "personal_owner"})
_TASK_KEYS = frozenset(
    {
        "description",
        "objective",
        "completed",
        "remaining",
        "next_action",
        "constraints",
        "decisions",
        "failed_approaches",
        "blockers",
        "discoveries",
        "last_verified_checkpoint",
    }
)
_NOTE_KEYS = frozenset({"text", "origin_ref"})
_CONSTRAINT_KEYS = frozenset({"constraint_id", "text", "origin_ref"})
_CHECKPOINT_KEYS = frozenset({"command", "status", "source_revision"})
_EVIDENCE_KEYS = frozenset(
    {
        "artifact_id",
        "version",
        "content_hash",
        "subject",
        "source",
        "owner",
        "provenance",
        "symbol_ref",
        "source_path",
        "source_revision",
        "freshness",
        "body",
        "body_sha256",
    }
)
_PROVENANCE_KEYS = frozenset({"trust_tier", "origin_kind", "origin_id"})
_MANIFEST_KEYS = frozenset(
    {
        "selected",
        "omitted",
        "redactions",
        "required_body_coverage",
        "encoding",
        "evidence_bytes",
        "evidence_tokens",
        "source_paths",
        "local_only_refs",
        "mapping_requirement",
        "omitted_bytes",
        "omitted_tokens",
    }
)
_EFFECT_KEYS = frozenset({"invocation_id", "effect_id", "request_digest"})
_SIDECAR_KEYS = frozenset(
    {
        "schema_version",
        "pas_sha256",
        "pas_session_id",
        "capsule_digest",
        "loss",
        "capsule",
        "export_effect",
    }
)
_LOSS_KEYS = frozenset({"field", "disposition", "pas_field"})
_JOURNAL_KEYS = frozenset(
    {"schema_version", "export_effect", "receipt", "pas", "sidecar"}
)
_RECEIPT_KEYS = frozenset(
    {
        "format",
        "output",
        "capsule_id",
        "created_at",
        "payload_sha256",
        "bytes",
        "invocation_id",
        "effect_id",
    }
)
_PAS_SESSION_KEYS = (
    "schema_version",
    "id",
    "project_name",
    "created_at",
    "updated_at",
    "task",
    "git",
    "checkpoints",
)
_PAS_TASK_KEYS = (
    "description",
    "objective",
    "completed",
    "remaining",
    "next_action",
    "blockers",
    "decisions",
    "constraints",
    "discoveries",
)
_PAS_TASK_LISTS = (
    "completed",
    "remaining",
    "blockers",
    "decisions",
    "constraints",
    "discoveries",
)
_PAS_CHECKPOINT_KEYS = (
    "id",
    "timestamp",
    "message",
    "task_snapshot",
    "git",
    "files_changed",
)
_PAS_STATUSES = frozenset({"Added", "Modified", "Deleted", "Untracked"})
_LOSS_LEDGER = (
    ("task.failed_approaches", "folded_into_pas_field", "task.decisions"),
    ("task.last_verified_checkpoint", "retained_in_sidecar", None),
    ("task.constraints[].origin_ref", "retained_in_sidecar", None),
    ("task.decisions[].origin_ref", "retained_in_sidecar", None),
    ("task.blockers[].origin_ref", "retained_in_sidecar", None),
    ("task.discoveries[].origin_ref", "retained_in_sidecar", None),
    ("evidence", "retained_in_sidecar", None),
    ("origin", "retained_in_sidecar", None),
    ("scope", "retained_in_sidecar", None),
    ("manifest", "retained_in_sidecar", None),
)


def _now() -> float:
    """The only clock for an exported `created_at` (a test seam)."""
    return time.time()


def _new_uuid() -> str:
    """The only source of a `capsule_id` and of a generated preview `invocation_id`."""
    return str(uuid.uuid4())


# --- results ------------------------------------------------------------------


class _Fail(Exception):
    """One refusal; `result()` is the dict `run_capsule` returns."""

    def __init__(
        self,
        code: str,
        reason: str | None = None,
        *,
        field: str | None = None,
        message: str | None = None,
        denial: bool = False,
        **extra: Any,
    ) -> None:
        super().__init__(code)
        self.code = code
        self.reason = reason
        self.field = field
        self.message = message
        self.denial = denial
        self.extra = extra

    def result(self) -> dict[str, Any]:
        data: dict[str, Any] = {"code": self.code}
        if self.field is not None:
            data["field"] = self.field
        if self.reason is not None:
            data["reason"] = self.reason
        if self.denial:
            data["denial"] = True
        else:
            data["message"] = self.message or (
                f"memory capsule refused: {self.reason or self.code}."
            )
        data.update(self.extra)
        return data


class _Invalid(Exception):
    """Internal: capsule, PAS or sidecar bytes are not valid."""


def _bad(field_name: str, message: str, reason: str | None = None) -> _Fail:
    return _Fail("E_INPUT", reason, field=field_name, message=message)


def _invalid(message: str = "the capsule bytes are not a valid capsule") -> _Fail:
    return _Fail("E_INPUT", "capsule_invalid", message=message)


def _blocked(message: str) -> _Fail:
    return _Fail("E_PERMISSION", "export_blocked", message=message)


def _recovery(message: str) -> _Fail:
    return _Fail("E_VERSION", "recovery_required", message=message)


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _digest(value: Any) -> str:
    return _sha(canonical_json(value))


# --- small predicates ---------------------------------------------------------


def _has_control(text: str) -> bool:
    return any(unicodedata.category(ch) in {"Cc", "Cf", "Cs"} for ch in text)


def _label(value: object) -> bool:
    """A non-empty identifier/label: no Cc, Cf or Cs character."""
    return isinstance(value, str) and bool(value) and not _has_control(value)


def _strict_int(value: object, low: int, high: int = _SQLITE_MAX) -> bool:
    return type(value) is int and low <= value <= high


def _hex64(value: object) -> bool:
    return isinstance(value, str) and _HEX64_RE.fullmatch(value) is not None


def _uuid(value: object) -> bool:
    return isinstance(value, str) and _UUID_RE.fullmatch(value) is not None


def _opt_str(value: object) -> bool:
    return value is None or isinstance(value, str)


def _portable_path(value: object) -> bool:
    """A relative path valid on every host: no root, drive, `..` or empty part."""
    if not isinstance(value, str) or not value or _has_control(value):
        return False
    if value.startswith(("/", "\\")) or _DRIVE_RE.match(value):
        return False
    parts = re.split(r"[\\/]", value)
    return ".." not in parts and "" not in parts


def _owner_hash(owner: OwnerScope) -> dict[str, str]:
    return {"kind": owner.kind, "id": _sha(owner.id.encode("utf-8"))}


def _depth(value: Any) -> int:
    """Nesting depth of a JSON value (a scalar is 0), without recursion."""
    deepest = 0
    stack: list[tuple[Any, int]] = [(value, 0)]
    while stack:
        node, level = stack.pop()
        if isinstance(node, dict):
            level += 1
            stack.extend((v, level) for v in node.values())
        elif isinstance(node, (list, tuple)):
            level += 1
            stack.extend((v, level) for v in node)
        deepest = max(deepest, level)
    return deepest


def _strings(value: Any) -> Iterator[str]:
    stack: list[Any] = [value]
    while stack:
        node = stack.pop()
        if isinstance(node, str):
            yield node
        elif isinstance(node, dict):
            for key, item in node.items():
                yield key
                stack.append(item)
        elif isinstance(node, list):
            stack.extend(node)


def _has_surrogate(text: str) -> bool:
    return any("\ud800" <= ch <= "\udfff" for ch in text)


# --- strict JSON decoding -----------------------------------------------------


def _no_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise _Invalid(f"duplicate key {key!r}")
        result[key] = value
    return result


def _no_constant(name: str) -> Any:
    raise _Invalid(f"{name} is not JSON")


def _strict_loads(data: bytes) -> Any:
    """Strict JSON: UTF-8 without BOM, nesting at most `MAX_DEPTH`, no duplicate key,
    no NaN/Infinity, no lone surrogate. Depth is checked on the text before parsing,
    so no hostile nesting reaches the recursive decoder."""
    if data.startswith(b"\xef\xbb\xbf"):
        raise _Invalid("byte order mark")
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise _Invalid("not UTF-8") from exc
    depth = 0
    for match in _BRACKET_RE.finditer(_JSON_STRING_RE.sub('""', text)):
        if match.group() in "[{":
            depth += 1
            if depth > MAX_DEPTH:
                raise _Invalid("nesting deeper than 16")
        else:
            depth -= 1
    try:
        value = json.loads(
            text, object_pairs_hook=_no_duplicates, parse_constant=_no_constant
        )
    except (ValueError, RecursionError) as exc:
        raise _Invalid("not strict JSON") from exc
    if any(_has_surrogate(s) for s in _strings(value)):
        raise _Invalid("lone surrogate")
    return value


# --- the request --------------------------------------------------------------


@dataclass
class _Request:
    action: str
    fmt: str
    input: str | None
    output: str | None
    max_bytes: int
    max_tokens: int
    mapping_id: str | None
    expected_digest: str | None
    expected_store_revision: int | None
    confirm: tuple[str, ...]
    invocation_id: str | None
    task_ref: dict[str, Any] | None
    owner: OwnerScope | None
    sources: tuple[str, ...] | None
    include_personal: bool
    legacy: bool = False

    def selectors(self) -> dict[str, Any]:
        """The normalized selectors (sorted sources, `include_personal` default
        false, omitted keys absent): a preview-digest input."""
        normalized: dict[str, Any] = {"include_personal": self.include_personal}
        if self.task_ref is not None:
            normalized["task_ref"] = dict(self.task_ref)
        if self.owner is not None:
            normalized["owner_scope"] = self.owner.as_dict()
        if self.sources is not None:
            normalized["sources"] = sorted(self.sources)
        return normalized


def _request_keys() -> frozenset[str]:
    from rush.tools.memory import _CAPSULE_REQUEST_KEYS

    return _CAPSULE_REQUEST_KEYS


def _path_field(request: dict[str, Any], key: str) -> str | None:
    if key not in request:
        return None
    value = request[key]
    if not isinstance(value, str) or not value:
        raise _bad(key, f"{key} must be a non-empty path string")
    if _has_control(value):
        raise _bad(key, f"{key} holds a control or unpaired character", "path_invalid")
    return value


def _budget_field(request: dict[str, Any], key: str, default: int, cap: int) -> int:
    if key not in request:
        return default
    value = request[key]
    if type(value) is not int or value < 1:
        raise _bad(key, f"{key} must be an integer of at least 1")
    if value > cap:
        raise _bad(key, f"{key} is above the hard cap {cap}", "budget_above_hard_cap")
    return value


def _owner_field(value: object, name: str) -> OwnerScope:
    if (
        not isinstance(value, dict)
        or set(value) != {"kind", "id"}
        or not isinstance(value["kind"], str)
        or value["kind"] not in _OWNER_KINDS
        or not _label(value["id"])
    ):
        raise _bad(name, f"{name} must be {{kind, id}} with a known kind")
    return OwnerScope(cast(Any, value["kind"]), value["id"])


def _validate_request(request: object, transport: str) -> _Request:
    """The R1/R2/R3 rules for the in-process and CLI path (MCP adds the strict
    request model first)."""
    if not isinstance(request, dict):
        raise _bad("request", "request must be an object")
    allowed = _request_keys()
    for key in request:
        if not isinstance(key, str) or key not in allowed:
            raise _bad(str(key), f"unknown capsule request field {key!r}")
    action = request.get("action")
    if not isinstance(action, str) or action not in _ACTIONS:
        raise _bad("action", "action must be one of " + ", ".join(_ACTIONS))
    if action == "bridge":
        raise _Fail(
            "E_INPUT",
            "bridge_not_available",
            field="action",
            message="memory capsule bridge is not available in this release",
        )
    fmt = request.get("format", "rush_v1")
    if not isinstance(fmt, str) or fmt not in _FORMATS:
        raise _bad("format", "format must be rush_v1 or pas_v1")
    export = action in _EXPORT_ACTIONS
    final = action in ("export", "import")

    input_path = _path_field(request, "input")
    output_path = _path_field(request, "output")
    max_bytes = _budget_field(request, "max_bytes", DEFAULT_MAX_BYTES, HARD_MAX_BYTES)
    max_tokens = _budget_field(
        request, "max_tokens", DEFAULT_MAX_TOKENS, HARD_MAX_TOKENS
    )
    mapping_id = request.get("mapping_id")
    if mapping_id is not None and not _uuid(mapping_id):
        raise _bad("mapping_id", "mapping_id must be a lowercase UUID")
    if "mapping_id" in request and mapping_id is None:
        raise _bad("mapping_id", "mapping_id must be a lowercase UUID")
    invocation_id = request.get("invocation_id")
    if "invocation_id" in request and not _uuid(invocation_id):
        raise _bad("invocation_id", "invocation_id must be a lowercase UUID")
    expected_digest = request.get("expected_digest")
    if "expected_digest" in request and not _hex64(expected_digest):
        raise _bad("expected_digest", "expected_digest must be 64 lowercase hex")
    revision = request.get("expected_store_revision")
    if "expected_store_revision" in request and not _strict_int(revision, 0):
        raise _bad(
            "expected_store_revision", "expected_store_revision must be an integer"
        )
    confirm: tuple[str, ...] = ()
    if "confirm_constraint_ids" in request:
        raw = request["confirm_constraint_ids"]
        if (
            not isinstance(raw, list)
            or not all(_label(item) for item in raw)
            or len(set(raw)) != len(raw)
        ):
            raise _bad(
                "confirm_constraint_ids",
                "confirm_constraint_ids must be unique non-empty strings",
            )
        confirm = tuple(raw)
    if "apply" in request and type(request["apply"]) is not bool:
        raise _bad("apply", "apply must be a boolean")

    task_ref: dict[str, Any] | None = None
    owner: OwnerScope | None = None
    sources: tuple[str, ...] | None = None
    include_personal = False
    if "selectors" in request:
        selectors = request["selectors"]
        if not isinstance(selectors, dict) or not set(selectors) <= _SELECTOR_KEYS:
            raise _bad(
                "selectors", "selectors holds an unknown key or is not an object"
            )
        if "task_ref" in selectors:
            ref = selectors["task_ref"]
            if (
                not isinstance(ref, dict)
                or set(ref) != {"artifact_id", "version"}
                or not _label(ref["artifact_id"])
                or not _strict_int(ref["version"], 1)
            ):
                raise _bad(
                    "selectors.task_ref",
                    "task_ref must be {artifact_id, version >= 1}",
                )
            task_ref = {"artifact_id": ref["artifact_id"], "version": ref["version"]}
        if "owner_scope" in selectors:
            owner = _owner_field(selectors["owner_scope"], "selectors.owner_scope")
        if "sources" in selectors:
            raw_sources = selectors["sources"]
            if (
                not isinstance(raw_sources, list)
                or not all(auth.literal_source_is_valid(s) for s in raw_sources)
                or len(set(raw_sources)) != len(raw_sources)
            ):
                raise _bad(
                    "selectors.sources", "sources must be unique literal source labels"
                )
            sources = tuple(raw_sources)
        if "include_personal" in selectors:
            if type(selectors["include_personal"]) is not bool:
                raise _bad(
                    "selectors.include_personal", "include_personal must be a boolean"
                )
            include_personal = selectors["include_personal"]
        if not export:
            for key in ("task_ref", "sources", "include_personal"):
                if key in selectors:
                    raise _bad(
                        f"selectors.{key}", f"selectors.{key} applies only to export"
                    )

    # presence rules (R2)
    if export:
        if output_path is None:
            raise _bad("output", f"{action} requires output")
        if "input" in request:
            raise _bad("input", f"{action} does not take input")
        if os.path.basename(output_path).endswith((_SIDECAR_SUFFIX, _JOURNAL_SUFFIX)):
            raise _Fail(
                "E_INPUT",
                "capsule_invalid",
                field="output",
                message="an output may not name a capsule sidecar or journal",
            )
        if "apply" in request:
            raise _bad("apply", f"{action} does not take apply")
        if "confirm_constraint_ids" in request:
            raise _bad(
                "confirm_constraint_ids", f"{action} does not take constraint ids"
            )
        if "expected_store_revision" in request:
            raise _bad(
                "expected_store_revision", f"{action} does not take a store revision"
            )
    else:
        if input_path is None:
            raise _bad("input", f"{action} requires input")
        if "output" in request:
            raise _bad("output", f"{action} does not take output")
        if action == "import":
            if request.get("apply") is not True:
                raise _bad("apply", "import requires apply: true")
        elif "apply" in request:
            raise _bad("apply", "preview_import does not take apply")
    if final:
        if invocation_id is None:
            raise _bad("invocation_id", f"{action} requires the preview invocation_id")
        if expected_digest is None:
            raise _bad("expected_digest", f"{action} requires expected_digest")
        if action == "import" and revision is None:
            raise _bad("expected_store_revision", "import requires a store revision")
    else:
        if "expected_digest" in request:
            raise _bad("expected_digest", f"{action} does not take expected_digest")
        if "expected_store_revision" in request:
            raise _bad(
                "expected_store_revision", f"{action} does not take a store revision"
            )
    return _Request(
        action=action,
        fmt=fmt,
        input=input_path,
        output=output_path,
        max_bytes=max_bytes,
        max_tokens=max_tokens,
        mapping_id=mapping_id,
        expected_digest=expected_digest,
        expected_store_revision=revision,
        confirm=confirm,
        invocation_id=invocation_id,
        task_ref=task_ref,
        owner=owner,
        sources=sources,
        include_personal=include_personal,
    )


# --- the public entry point -----------------------------------------------------


def run_capsule(
    root: Path,
    request: dict[str, Any],
    *,
    permissions: ExecutionPermissions,
    transport: Literal["cli", "mcp"] = "cli",
) -> dict[str, Any]:
    """Run one capsule action. Returns `{"code": C, **data}` or `{"skipped": True,
    "action": A, "missing": [...]}`; request, file and policy faults are results."""
    try:
        return _run(Path(root), request, permissions, transport)
    except _Fail as fail:
        return fail.result()


def _run(
    root: Path, request: object, permissions: ExecutionPermissions, transport: str
) -> dict[str, Any]:
    req = _validate_request(request, transport)
    if req.action in _IMPORT_ACTIONS and transport == "mcp" and req.confirm:
        raise _Fail(
            "E_PERMISSION",
            "constraint_confirmation_requires_cli",
            message=(
                "constraint applicability is confirmed through the CLI "
                "(--confirm-constraint-id) or local review"
            ),
        )
    needed = {
        "export": ExecutionPermissions(artifact_write=True),
        "import": ExecutionPermissions(cache_write=True),
    }.get(req.action)
    if needed is not None:
        satisfied, missing = check_permissions(needed, permissions)
        if not satisfied:
            return {"skipped": True, "action": req.action, "missing": missing}
    mode, reason = retrieval.memory_policy_mode(root, with_reason=True)
    if mode == "unavailable":
        raise _Fail("E_PERMISSION", reason or "policy_invalid", denial=True)
    req.legacy = mode == "legacy"
    if req.action in _EXPORT_ACTIONS:
        return _export(root, req, transport)
    return _import(root, req, transport)


# --- access ---------------------------------------------------------------------


def _denial(reason: str, *, explicit_owner: bool) -> _Fail:
    """§2.1 item 3: the one resolve-reason -> code mapping."""
    if reason == "owner_not_granted":
        return _Fail(
            "E_OWNER" if explicit_owner else "E_PERMISSION", reason, denial=True
        )
    if reason == "source_not_granted":
        return _Fail("E_SCOPE", reason, denial=True)
    if reason == "owner_required":
        return _Fail("E_INPUT", reason, field="owner_scope", denial=True)
    return _Fail("E_PERMISSION", reason, denial=True)


def _resolve(
    root: Path,
    action: str,
    *,
    owner: OwnerScope | None,
    sources: tuple[str, ...] | None,
    legacy: bool,
) -> MemoryAccess:
    if legacy:
        # D1 `legacy`: no policy governs this project, and a capsule has no legacy
        # (session allowlist) access form.
        raise _Fail("E_PERMISSION", "policy_missing", denial=True)
    access, reason = MemoryAccess.resolve_with_reason(
        root,
        operation="capsule",
        action=action,
        apply=action == "import",
        owner_scope=owner,
        requested_sources=sources or (),
    )
    if access is None:
        raise _denial(reason, explicit_owner=owner is not None)
    return access


def _resolve_overlay(root: Path) -> MemoryAccess:
    owner = _overlay_owner()
    if owner is None:
        raise _Fail("E_PERMISSION", "data_root_unavailable", denial=True)
    access, reason = MemoryAccess.resolve_with_reason(
        root, operation="expand", overlay=True, owner_scope=owner
    )
    if access is None:
        raise _denial(reason, explicit_owner=True)
    return access


def _overlay_owner() -> OwnerScope | None:
    try:
        return auth.user_overlay_owner_scope()
    except auth.MemoryPolicyError:
        return None


def _storage_root(access: MemoryAccess) -> Path:
    """D25: where the access's rows live (the overlay root for the overlay owner)."""
    pinned = getattr(access, "storage_root", None)
    if pinned is not None:
        return Path(pinned)
    if access.owner_scope is not None and access.owner_scope == _overlay_owner():
        return Path(access.owner_scope.id)
    return Path(access.project_root)


def _recheck(*accesses: MemoryAccess | None) -> None:
    for access in accesses:
        if access is None:
            continue
        failure = retrieval.recheck_failure(access)
        if failure is not None:
            raise _Fail(failure[0], failure[1], denial=True)


@contextlib.contextmanager
def _locked(target: str, *accesses: MemoryAccess | None) -> Iterator[None]:
    """Lock order positions 2 and 4: the policy lock (then a recheck of every
    access under it), then `memory-capsule-target:<target>`. Never the dashboard
    project lock."""
    from rush.dashboard.state import cross_process_project_lock
    from rush.tools.memory import _policy_mutation

    primary = next(a for a in accesses if a is not None)
    with _policy_mutation(primary) as denied:
        if denied is not None:
            raise _Fail(denied.code, denied.reason, denial=True)
        _recheck(*accesses)
        with cross_process_project_lock(_TARGET_LOCK_PREFIX + target, data_root=None):
            yield


def _policy_revision(access: MemoryAccess) -> int:
    return int(auth.load_policy_readonly(data_root=access.data_root)["policy_revision"])


# --- the store view (R13 route: read-only) -----------------------------------------


def _open_view(storage_root: Path) -> TypedArtifactStore | None:
    view, state = TypedArtifactStore.open_readonly_view(storage_root)
    if state == "migration_required":
        raise _Fail(
            "E_MIGRATION", "migration_required", message=readonly_view_reason(state)
        )
    if state is not None:
        code = "E_STORE_CORRUPT" if state == "corrupt" else "E_STORE_BUSY"
        raise _Fail(code, state, message=readonly_view_reason(state))
    return view


def _usable(view: TypedArtifactStore, row: Any, access: MemoryAccess) -> Any:
    """The visibility decision when `row` is ordinary-usable, else `None`."""
    if row is None:
        return None
    decision = retrieval.evaluate_artifact_visibility(
        view, row, access=access, mode="ordinary"
    )
    return decision if decision.visible and decision.usable_as_current else None


# --- export ---------------------------------------------------------------------


@dataclass
class _Selection:
    row: Any
    content: dict[str, Any]
    task: dict[str, Any]
    evidence: list[dict[str, Any]]
    store_revision: int

    @property
    def selected(self) -> list[dict[str, Any]]:
        head = {"artifact_id": self.row["id"], "version": self.row["artifact_version"]}
        tail = [
            {"artifact_id": e["artifact_id"], "version": e["version"]}
            for e in self.evidence
        ]
        return [head, *tail]


def _checkpoint(view: TypedArtifactStore, row: Any, access: MemoryAccess) -> Any:
    """The parsed content of an eligible checkpoint row, else `None`."""
    if _usable(view, row, access) is None:
        return None
    try:
        content = json.loads(row["content"])
    except (ValueError, TypeError, RecursionError):
        return None
    if (
        not isinstance(content, dict)
        or content.get("kind") != "checkpoint"
        or type(content.get("schema_version")) is not int
        or content.get("schema_version") != 1
        or access.project_id is None
        or access.worktree_id is None
        or content.get("project_id") != access.project_id
        or content.get("worktree_id") != access.worktree_id
        or not _label(content.get("task_id"))
    ):
        return None
    return content


def _notes(content: dict[str, Any], key: str) -> list[dict[str, str]]:
    items = content.get(key)
    if not isinstance(items, list) or not all(
        isinstance(i, dict)
        and set(i) == _NOTE_KEYS
        and isinstance(i["text"], str)
        and isinstance(i["origin_ref"], str)
        for i in items
    ):
        raise _blocked(f"checkpoint {key} entries must be {{text, origin_ref}}")
    return [{"text": i["text"], "origin_ref": i["origin_ref"]} for i in items]


def _project_task(content: dict[str, Any]) -> dict[str, Any]:
    """Item 5: the checkpoint row projected to the capsule `task` object."""
    for key in ("description", "objective"):
        if not isinstance(content.get(key), str):
            raise _blocked(f"checkpoint {key} must be a string")
    next_action = content.get("next_action")
    if not isinstance(next_action, str) or not next_action:
        raise _blocked("checkpoint next_action must be a non-empty string")
    for key in ("implemented", "unresolved"):
        if not isinstance(content.get(key), list):
            raise _blocked(f"checkpoint {key} must be a list")
    decisions = _notes(content, "decisions")
    blockers = _notes(content, "blockers")
    discoveries = _notes(content, "discoveries")
    disproved = _notes(content, "disproved")
    requirements = content.get("requirements")
    if not isinstance(requirements, list) or not all(
        isinstance(q, dict)
        and set(q) == {"id", "text", "authority", "provenance"}
        and _label(q["id"])
        and all(isinstance(q[k], str) for k in ("text", "authority", "provenance"))
        for q in requirements
    ):
        raise _blocked(
            "checkpoint requirements must be {id, text, authority, provenance}"
        )
    if len({q["id"] for q in requirements}) != len(requirements):
        raise _blocked("checkpoint requirement ids must be unique")
    checks = content.get("checks")
    if not isinstance(checks, list) or not all(
        isinstance(c, dict)
        and set(c)
        == {"command", "exit_code", "status", "source_revision", "receipt_id"}
        and isinstance(c["command"], list)
        and all(isinstance(part, str) for part in c["command"])
        and type(c["exit_code"]) is int
        and c["status"] in ("passed", "failed")
        and isinstance(c["source_revision"], str)
        and isinstance(c["receipt_id"], str)
        for c in checks
    ):
        raise _blocked("checkpoint checks entries are malformed")
    passing = [c for c in checks if c["status"] == "passed" and c["exit_code"] == 0]
    if not passing:
        raise _blocked("the checkpoint has no passing check")
    refs = content.get("evidence_refs")
    if not isinstance(refs, list) or not all(
        isinstance(r, dict)
        and set(r) == {"artifact_id", "version"}
        and _label(r["artifact_id"])
        and _strict_int(r["version"], 1)
        for r in refs
    ):
        raise _blocked(
            "checkpoint evidence_refs entries must be {artifact_id, version}"
        )
    source = content.get("source")
    if (
        not isinstance(source, dict)
        or not _opt_str(source.get("commit"))
        or not _opt_str(source.get("branch"))
        or type(source.get("dirty")) is not bool
    ):
        raise _blocked("checkpoint source must be {commit, branch, dirty}")
    last = passing[-1]
    return {
        "description": content["description"],
        "objective": content["objective"],
        "completed": content["implemented"],
        "remaining": content["unresolved"],
        "next_action": next_action,
        "constraints": [
            {"constraint_id": q["id"], "text": q["text"], "origin_ref": q["provenance"]}
            for q in requirements
        ],
        "decisions": decisions,
        "failed_approaches": disproved,
        "blockers": blockers,
        "discoveries": discoveries,
        "last_verified_checkpoint": {
            "command": last["command"],
            "status": last["status"],
            "source_revision": last["source_revision"],
        },
    }


def _evidence_entry(row: Any, decision: Any, commit: str | None) -> dict[str, Any]:
    symbol_ref = row["symbol_ref"]
    source_path: str | None = None
    if symbol_ref is not None:
        if not isinstance(symbol_ref, str):
            raise _blocked("evidence symbol_ref is malformed")
        source_path = symbol_ref.partition("::")[0]
        if not _portable_path(source_path):
            raise _blocked("evidence is anchored at a non-portable path")
    owner_kind, owner_id = row["owner_scope_kind"], row["owner_scope_id"]
    if not isinstance(owner_kind, str) or not isinstance(owner_id, str):
        raise _blocked("evidence has no owner")
    try:
        body = json.loads(row["content"])
        if not isinstance(body, dict):
            raise _blocked("evidence body is not an object")
        body_sha = _digest(body)
    except (ValueError, TypeError, UnicodeError, RecursionError) as exc:
        raise _blocked("evidence body cannot be serialized") from exc
    return {
        "artifact_id": row["id"],
        "version": row["artifact_version"],
        "content_hash": row["content_hash"],
        "subject": row["subject"],
        "source": row["source"],
        "owner": {"kind": owner_kind, "id": _sha(owner_id.encode("utf-8"))},
        "provenance": {
            "trust_tier": row["trust_tier"],
            "origin_kind": row["origin_kind"],
            "origin_id": row["origin_id"],
        },
        "symbol_ref": symbol_ref,
        "source_path": source_path,
        "source_revision": commit if symbol_ref is not None else None,
        "freshness": decision.freshness,
        "body": body,
        "body_sha256": body_sha,
    }


def _select_export(
    req: _Request, access: MemoryAccess, overlay: MemoryAccess | None
) -> _Selection:
    """G8-T4/T5: the task row, its projection and its exact evidence."""
    with contextlib.ExitStack() as stack:
        view = _open_view(_storage_root(access))
        if view is None:
            if req.task_ref is not None:
                raise _Fail(
                    "E_NOT_VISIBLE", "not_visible", message="no such checkpoint"
                )
            raise _blocked("no eligible open task checkpoint")
        stack.callback(view.close)
        try:
            return _select_in_view(req, view, access, overlay, stack)
        except RecursionError as exc:
            raise _blocked("a stored body is nested too deeply") from exc


def _select_in_view(
    req: _Request,
    view: TypedArtifactStore,
    access: MemoryAccess,
    overlay: MemoryAccess | None,
    stack: contextlib.ExitStack,
) -> _Selection:
    with view._connect() as conn:
        revision = store_generation(conn)
        rows = conn.execute(
            "SELECT * FROM memory_artifacts WHERE subject = ?", ("episodic",)
        ).fetchall()
    eligible: dict[str, tuple[Any, dict[str, Any]]] = {}
    for row in rows:
        content = _checkpoint(view, row, access)
        if content is not None:
            eligible[row["id"]] = (row, content)
    newest: dict[str, tuple[tuple[float, str], str]] = {}
    for artifact_id, (row, content) in eligible.items():
        key = (float(row["created_at"]), artifact_id)
        task_id = content["task_id"]
        if task_id not in newest or key > newest[task_id][0]:
            newest[task_id] = (key, artifact_id)
    if req.task_ref is not None:
        ref_id = req.task_ref["artifact_id"]
        if ref_id not in eligible:
            raise _Fail("E_NOT_VISIBLE", "not_visible", message="no such checkpoint")
        row, content = eligible[ref_id]
        if row["artifact_version"] != req.task_ref["version"]:
            raise _recovery("the checkpoint version is not current")
        if newest[content["task_id"]][1] != ref_id:
            raise _recovery("the checkpoint is not its task's newest")
        if content.get("event_kind") in _ENDED_EVENTS:
            raise _blocked("the task has ended")
    else:
        open_ids = sorted(
            aid
            for _key, aid in newest.values()
            if eligible[aid][1].get("event_kind") not in _ENDED_EVENTS
        )
        if len(open_ids) > 1:
            raise _Fail(
                "E_INPUT",
                "task_ref_required",
                field="selectors.task_ref",
                message="more than one open task: name one with selectors.task_ref",
            )
        if not open_ids:
            raise _blocked("no eligible open task checkpoint")
        row, content = eligible[open_ids[0]]
    task = _project_task(content)
    commit = content["source"]["commit"]
    overlay_view: list[TypedArtifactStore | None] = []

    def overlay_store() -> TypedArtifactStore | None:
        if not overlay_view:
            assert overlay is not None
            opened = _open_view(_storage_root(overlay))
            if opened is not None:
                stack.callback(opened.close)
            overlay_view.append(opened)
        return overlay_view[0]

    evidence: list[dict[str, Any]] = []
    for ref in content["evidence_refs"]:
        found: tuple[Any, Any] | None = None
        candidate = view.get_current_row(ref["artifact_id"])
        decision = _usable(view, candidate, access)
        if (
            candidate is not None
            and decision is not None
            and candidate["artifact_version"] == ref["version"]
        ):
            found = (candidate, decision)
        elif overlay is not None:
            other = overlay_store()
            if other is not None:
                candidate = other.get_current_row(ref["artifact_id"])
                decision = _usable(other, candidate, overlay)
                if (
                    candidate is not None
                    and decision is not None
                    and candidate["artifact_version"] == ref["version"]
                ):
                    found = (candidate, decision)
        if found is None:
            raise _blocked(
                f"evidence {ref['artifact_id']} is not usable at that version"
            )
        evidence.append(_evidence_entry(found[0], found[1], commit))
    if len(evidence) > MAX_EVIDENCE:
        raise _blocked("more than 128 evidence entries")
    return _Selection(row, content, task, evidence, revision)


def _capsule_doc(
    sel: _Selection,
    access: MemoryAccess,
    overlay: MemoryAccess | None,
    *,
    capsule_id: str,
    created_at: float,
    export_effect: dict[str, str] | None,
) -> dict[str, Any]:
    assert access.owner_scope is not None
    source = sel.content["source"]
    evidence_bytes = canonical_json(sel.evidence)
    manifest: dict[str, Any] = {
        "selected": sel.selected,
        "omitted": [],
        "redactions": [],
        "required_body_coverage": "complete",
        "encoding": retrieval.DEFAULT_ENCODING,
        "evidence_bytes": len(evidence_bytes),
        "evidence_tokens": retrieval._count_tokens(
            evidence_bytes.decode("utf-8"), retrieval.DEFAULT_ENCODING
        ),
        "source_paths": sorted(
            {e["source_path"] for e in sel.evidence if e["source_path"] is not None}
        ),
        "local_only_refs": [],
        "mapping_requirement": _MAPPING_REQUIREMENT,
        "omitted_bytes": 0,
        "omitted_tokens": 0,
    }
    if export_effect is not None:
        manifest["export_effect"] = export_effect
    personal = (
        _owner_hash(overlay.owner_scope)
        if overlay is not None and overlay.owner_scope is not None
        else None
    )
    doc: dict[str, Any] = {
        "schema_version": 1,
        "format": "rush_v1",
        "capsule_id": capsule_id,
        "created_at": created_at,
        "origin": {
            "rush_version": rush.__version__,
            "project_id": access.project_id,
            "worktree_id": access.worktree_id,
            "git": {
                "commit": source["commit"],
                "branch": source["branch"],
                "dirty": source["dirty"],
            },
            "store_revision": sel.store_revision,
        },
        "scope": {
            "owner": _owner_hash(access.owner_scope),
            "sources": sorted(access.sources),
            "personal_owner": personal,
        },
        "task": sel.task,
        "evidence": sel.evidence,
        "manifest": manifest,
    }
    doc["payload_sha256"] = _digest(doc)
    return doc


def _pas_text_items(items: list[Any]) -> list[str]:
    return [
        item if isinstance(item, str) else canonical_json(item).decode("utf-8")
        for item in items
    ]


def _pas_timestamp(seconds: float) -> str:
    """chrono `to_rfc3339_opts(SecondsFormat::AutoSi, true)` of `seconds`."""
    exact = Decimal(repr(seconds))
    whole = int(exact.to_integral_value(rounding=ROUND_FLOOR))
    nanos = int((exact - whole) * 1_000_000_000)
    text = datetime.fromtimestamp(whole, tz=UTC).strftime("%Y-%m-%dT%H:%M:%S")
    if nanos == 0:
        fraction = ""
    elif nanos % 1_000_000 == 0:
        fraction = f".{nanos // 1_000_000:03d}"
    elif nanos % 1_000 == 0:
        fraction = f".{nanos // 1_000:06d}"
    else:
        fraction = f".{nanos:09d}"
    return f"{text}{fraction}Z"


def _pas_session(doc: dict[str, Any], project_name: str) -> dict[str, Any]:
    """The PAS schema-1 session carrying the capsule task (struct field order)."""
    task = doc["task"]
    decisions = [d["text"] for d in task["decisions"]] + [
        f"Failed approach (do not retry): {f['text']}"
        for f in task["failed_approaches"]
    ]
    pas_task = {
        "description": task["description"],
        "objective": task["objective"],
        "completed": _pas_text_items(task["completed"]),
        "remaining": _pas_text_items(task["remaining"]),
        "next_action": task["next_action"],
        "blockers": [b["text"] for b in task["blockers"]],
        "decisions": decisions,
        "constraints": [c["text"] for c in task["constraints"]],
        "discoveries": [d["text"] for d in task["discoveries"]],
    }
    git = doc["origin"]["git"]
    stamp = _pas_timestamp(doc["created_at"])
    session = {
        "schema_version": 1,
        "id": doc["capsule_id"],
        "project_name": project_name,
        "created_at": stamp,
        "updated_at": stamp,
        "task": pas_task,
        "git": {
            "branch": git["branch"],
            "commit": git["commit"],
            "dirty": git["dirty"],
        },
        "checkpoints": [],
    }
    if any("\x00" in text for text in _strings(session)):
        raise _blocked("a task string holds NUL, which PAS cannot carry")
    return session


def _loss_ledger(task: dict[str, Any]) -> list[dict[str, Any]]:
    loss = [{"field": f, "disposition": d, "pas_field": p} for f, d, p in _LOSS_LEDGER]
    for key in ("completed", "remaining"):
        if any(not isinstance(item, str) for item in task[key]):
            loss.append(
                {
                    "field": f"task.{key}[]",
                    "disposition": "encoded_as_canonical_json_string",
                    "pas_field": f"task.{key}",
                }
            )
    return loss


def _pretty(value: Any) -> bytes:
    """`serde_json::to_string_pretty` bytes."""
    return json.dumps(value, indent=2, ensure_ascii=False).encode("utf-8")


@dataclass
class _Built:
    files: list[tuple[Path, bytes, SanitizedBytes]]
    doc: dict[str, Any]
    required: dict[str, int]


def _build(
    req: _Request,
    sel: _Selection,
    access: MemoryAccess,
    overlay: MemoryAccess | None,
    out: Path,
    *,
    capsule_id: str,
    created_at: float,
    effect: dict[str, str],
    bound: bool = False,
) -> _Built:
    """Serialize the capsule (or PAS pair), run the item 9 secret gate over the
    objects and over the exact bytes, and measure the bytes and tokens. With
    `bound` (a placeholder capsule id and clock) the measure is the upper bound of
    every export of the same content: each value the export generates (capsule id,
    clock, payload and PAS digests, export effect) is counted at its largest byte
    size. For tokens every generated hex or UUID string is first replaced by zeros
    of its length (so the count never depends on the request's own digests), then
    each occurrence adds one token per byte plus two for the tokens it can change at
    its two boundaries (a token holds at least one byte). Digit runs tokenize in
    fixed three-digit chunks, so the clock values stay in the text."""
    varying: list[tuple[str, int]] = []
    try:
        if req.fmt == "rush_v1":
            doc = _capsule_doc(
                sel,
                access,
                overlay,
                capsule_id=capsule_id,
                created_at=created_at,
                export_effect=effect,
            )
            objects: list[Any] = [doc]
            payloads = [(out, canonical_json(doc))]
            varying = [
                (doc["capsule_id"], 36),
                (repr(doc["created_at"]), 18),
                (doc["payload_sha256"], 64),
                *_effect_varying(effect),
            ]
        else:
            doc = _capsule_doc(
                sel,
                access,
                overlay,
                capsule_id=capsule_id,
                created_at=created_at,
                export_effect=None,
            )
            session = _pas_session(doc, Path(access.project_root).name)
            pas = _pretty(session)
            sidecar = {
                "schema_version": 1,
                "pas_sha256": _sha(pas),
                "pas_session_id": session["id"],
                "capsule_digest": doc["payload_sha256"],
                "loss": _loss_ledger(doc["task"]),
                "capsule": doc,
                "export_effect": effect,
            }
            objects = [session, sidecar]
            payloads = [
                (out, pas),
                (Path(str(out) + _SIDECAR_SUFFIX), canonical_json(sidecar)),
            ]
            stamp = session["created_at"]
            varying = [
                (session["id"], 36),
                (stamp, 30),
                (stamp, 30),
                (sidecar["pas_sha256"], 64),
                (session["id"], 36),
                (doc["payload_sha256"], 64),
                (doc["capsule_id"], 36),
                (repr(doc["created_at"]), 18),
                (doc["payload_sha256"], 64),
                *_effect_varying(effect),
            ]
    except (ValueError, TypeError, UnicodeError, RecursionError) as exc:
        raise _blocked("the capsule cannot be serialized") from exc
    if max(_depth(obj) for obj in objects) > MAX_DEPTH:
        raise _blocked("the capsule nests deeper than 16")
    if SanitizedJsonValue.from_value(objects).redaction_count != 0:
        raise _blocked("a mandatory body holds a secret or private value")
    files: list[tuple[Path, bytes, SanitizedBytes]] = []
    for path, data in payloads:
        checked = SanitizedBytes.from_bytes(data)
        if checked.redaction_count != 0 or checked.data != data:
            raise _blocked("a mandatory body holds a secret or private value")
        files.append((path, data, checked))
    texts = [data.decode("utf-8") for _p, data, _s in files]
    required = {
        "bytes": sum(len(data) for _p, data, _s in files),
        "tokens": sum(_tokens(text) for text in texts),
    }
    if bound:
        generated = {
            value: most for value, most in varying if _hex64(value) or _uuid(value)
        }
        for value in generated:
            texts = [text.replace(value, "0" * len(value)) for text in texts]
        tokens = sum(_tokens(text) for text in texts)
        for value, most_bytes in varying:
            required["bytes"] += max(0, most_bytes - len(value.encode("utf-8")))
            if value not in generated:
                tokens += most_bytes + 2
        for value, most_bytes in generated.items():
            occurrences = sum(
                data.decode("utf-8").count(value) for _p, data, _s in files
            )
            tokens += occurrences * (most_bytes + 2)
        required["tokens"] = tokens
    return _Built(files, doc, required)


def _effect_varying(effect: dict[str, str]) -> list[tuple[str, int]]:
    """The export-effect values a new request changes (invocation id, effect id,
    request digest), each at its largest byte size."""
    return [
        (effect["invocation_id"], 36),
        (effect["effect_id"], 64),
        (effect["request_digest"], 64),
    ]


def _tokens(text: str) -> int:
    return retrieval._count_tokens(text, retrieval.DEFAULT_ENCODING)


def _check_budget(req: _Request, required: dict[str, int], reason: str) -> None:
    limits = {"max_bytes": req.max_bytes, "max_tokens": req.max_tokens}
    if required["bytes"] > min(req.max_bytes, HARD_MAX_BYTES) or required[
        "tokens"
    ] > min(req.max_tokens, HARD_MAX_TOKENS):
        raise _Fail(
            "E_BUDGET",
            reason,
            message="the content needs more than the allowed bytes or tokens",
            required=required,
            limits=limits,
        )


# --- export targets -------------------------------------------------------------


def _anchor(value: str, root: Path, transport: str) -> Path:
    path = Path(value)
    if not path.is_absolute():
        path = root / path if transport == "mcp" else Path(os.path.abspath(path))
    return path


def _refused(message: str) -> _Fail:
    return _Fail("E_PERMISSION", "export_target_refused", message=message)


def _canonical(out: Path) -> Path:
    try:
        parent = out.parent.resolve()
    except (OSError, RuntimeError, ValueError) as exc:
        raise _refused("the output directory cannot be resolved") from exc
    if not os.path.isdir(parent):
        raise _Fail(
            "E_INPUT",
            "output_parent_missing",
            field="output",
            message="the output directory does not exist",
        )
    return parent / out.name


def _data_root() -> Path | None:
    from rush.setup.provision import default_data_root

    try:
        return default_data_root().resolve()
    except Exception:  # noqa: BLE001 - an unavailable data root names no store area
        return None


def _target_paths(out: Path, fmt: str) -> list[Path]:
    if fmt == "rush_v1":
        return [out]
    return [out, Path(str(out) + _SIDECAR_SUFFIX), Path(str(out) + _JOURNAL_SUFFIX)]


def _target_rules(
    root: Path, out: Path, fmt: str, transport: str, *, absence: bool
) -> Path:
    """G8-T2: every export target-refusal rule (the MCP absence rule only when
    `absence`). Returns the canonical output path."""
    from rush.workflows import projects

    canonical = _canonical(out)
    canonical_root = root.resolve()
    store_area = canonical_root / ".rush"
    data_root = _data_root()
    for named, path in zip(
        _target_paths(out, fmt), _target_paths(canonical, fmt), strict=True
    ):
        if (
            path == store_area
            or path.is_relative_to(store_area)
            or (data_root is not None and path.is_relative_to(data_root))
        ):
            raise _refused("the output is inside a memory store area")
        if path.name.startswith(_RESERVED_PREFIXES):
            raise _refused("the output names a reserved memory file")
        if os.path.islink(named) or (
            os.path.lexists(named) and not stat.S_ISREG(os.lstat(named).st_mode)
        ):
            raise _refused("the output is a link or not a regular file")
        under = projects._export_under_root(root, named)
        if under is not None:
            try:
                projects.check_export_destination(root, named)
            except ContainmentError as exc:
                raise _refused("the output leaves the project root") from exc
        if transport == "mcp":
            if under is None:
                raise _refused("over MCP the output must be under the project root")
            if absence and os.path.lexists(named):
                raise _refused("over MCP the output must not exist")
    return canonical


def _absence(out: Path, fmt: str) -> None:
    for path in _target_paths(out, fmt):
        if os.path.lexists(path):
            raise _refused("over MCP the output must not exist")


def _read_regular(path: Path, *, follow: bool = False) -> bytes | None:
    """The bytes of a regular file (at most `HARD_MAX_BYTES + 1`), else `None`."""
    flags = os.O_RDONLY | getattr(os, "O_NONBLOCK", 0) | getattr(os, "O_BINARY", 0)
    if not follow:
        flags |= getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(path, flags)
    except OSError:
        return None
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            return None
        chunks: list[bytes] = []
        size = 0
        while size <= HARD_MAX_BYTES:
            chunk = os.read(fd, HARD_MAX_BYTES + 1 - size)
            if not chunk:
                break
            chunks.append(chunk)
            size += len(chunk)
        return b"".join(chunks)
    except OSError:
        return None
    finally:
        os.close(fd)


def _file_state(path: Path) -> dict[str, Any]:
    exists = os.path.lexists(path)
    data = _read_regular(path) if exists else None
    return {
        "path": str(path),
        "exists": exists,
        "sha256": _sha(data) if data is not None else None,
    }


def _target_state(out: Path, fmt: str) -> Any:
    if fmt == "rush_v1":
        return _file_state(out)
    return [_file_state(out), _file_state(Path(str(out) + _SIDECAR_SUFFIX))]


def _export_request_digest(
    req: _Request, invocation_id: str, output: Path, expected_digest: str | None
) -> str:
    return _digest(
        {
            "action": "export",
            "format": req.fmt,
            "invocation_id": invocation_id,
            "selectors": req.selectors(),
            "mapping_id": req.mapping_id,
            "max_bytes": req.max_bytes,
            "max_tokens": req.max_tokens,
            "expected_digest": expected_digest,
            "output": str(output),
        }
    )


def _effect_id(invocation_id: str, apply_action: str, target: str) -> str:
    return _digest([invocation_id, apply_action, target])


def _export_digest(
    req: _Request,
    invocation_id: str,
    sel: _Selection,
    policy_revision: int,
    target: Any,
) -> str:
    return _digest(
        {
            "action": "export",
            "format": req.fmt,
            "invocation_id": invocation_id,
            "selectors": req.selectors(),
            "mapping_id": req.mapping_id,
            "confirm_constraint_ids": [],
            "max_bytes": req.max_bytes,
            "max_tokens": req.max_tokens,
            "policy_revision": policy_revision,
            "input_sha256": None,
            "source_store_revision": sel.store_revision,
            "selected_ids": [[s["artifact_id"], s["version"]] for s in sel.selected],
            "target": target,
        }
    )


@dataclass
class _ExportPlan:
    out: Path
    sel: _Selection
    digest: str
    built: _Built


def _plan_export(
    req: _Request,
    access: MemoryAccess,
    overlay: MemoryAccess | None,
    out: Path,
    invocation_id: str,
    effect_id: str,
) -> _ExportPlan:
    """Selection, secret gate and budget over the placeholder capsule, then the
    preview digest (the preview and the export compute the same value)."""
    sel = _select_export(req, access, overlay)
    digest = _export_digest(
        req, invocation_id, sel, _policy_revision(access), _target_state(out, req.fmt)
    )
    built = _build(
        req,
        sel,
        access,
        overlay,
        out,
        capsule_id=_ZERO_UUID,
        created_at=float(int(_now())),
        effect={
            "invocation_id": invocation_id,
            "effect_id": effect_id,
            "request_digest": _export_request_digest(req, invocation_id, out, digest),
        },
        bound=True,
    )
    _check_budget(req, built.required, "export_blocked")
    return _ExportPlan(out, sel, digest, built)


def _export(root: Path, req: _Request, transport: str) -> dict[str, Any]:
    assert req.output is not None
    out = _anchor(req.output, root, transport)
    access = _resolve(
        root, req.action, owner=req.owner, sources=req.sources, legacy=req.legacy
    )
    overlay = _resolve_overlay(root) if req.include_personal else None
    if req.action == "preview_export":
        canonical = _target_rules(root, out, req.fmt, transport, absence=True)
        invocation_id = req.invocation_id or _new_uuid()
        effect_id = _effect_id(invocation_id, "export", str(canonical))
        plan = _plan_export(req, access, overlay, canonical, invocation_id, effect_id)
        return {
            "code": "OK",
            "action": req.action,
            "format": req.fmt,
            "invocation_id": invocation_id,
            "effect_id": effect_id,
            "digest": plan.digest,
            "output": str(canonical),
            "selected": plan.sel.selected,
            "source_store_revision": plan.sel.store_revision,
            "target": _target_state(canonical, req.fmt),
            "required": plan.built.required,
            "limits": {"max_bytes": req.max_bytes, "max_tokens": req.max_tokens},
        }
    assert req.invocation_id is not None
    _recheck(access, overlay)
    # One unlocked pass first: a refusal leaves no lock file behind.
    canonical = _export_pass(root, req, transport, access, overlay, out, act=False)
    if isinstance(canonical, dict):
        return canonical
    with _locked(str(canonical), access, overlay):
        outcome = _export_pass(root, req, transport, access, overlay, out, act=True)
        if isinstance(outcome, dict):
            return outcome
        return _publish_export(req, access, overlay, outcome)


def _export_pass(
    root: Path,
    req: _Request,
    transport: str,
    access: MemoryAccess,
    overlay: MemoryAccess | None,
    out: Path,
    *,
    act: bool,
) -> Any:
    """Target rules, replay, MCP absence and the digest compare. Returns a replay
    receipt (dict), the plan (`act`), or the canonical output path."""
    assert req.invocation_id is not None
    canonical = _target_rules(root, out, req.fmt, transport, absence=False)
    effect_id = _effect_id(req.invocation_id, "export", str(canonical))
    request_digest = _export_request_digest(
        req, req.invocation_id, canonical, req.expected_digest
    )
    replay = _replay_export(req, canonical, effect_id, request_digest, act=act)
    if replay is not None:
        if act or replay.get("_pending") is None:
            return {k: v for k, v in replay.items() if not k.startswith("_")}
        return canonical
    if transport == "mcp":
        _absence(canonical, req.fmt)
    plan = _plan_export(req, access, overlay, canonical, req.invocation_id, effect_id)
    if plan.digest != req.expected_digest:
        raise _recovery("the export changed since its preview")
    return plan if act else canonical


def _receipt(
    req: _Request, out: Path, doc: dict[str, Any], size: int, effect_id: str
) -> dict[str, Any]:
    return {
        "format": req.fmt,
        "output": str(out),
        "capsule_id": doc["capsule_id"],
        "created_at": doc["created_at"],
        "payload_sha256": doc["payload_sha256"],
        "bytes": size,
        "invocation_id": req.invocation_id,
        "effect_id": effect_id,
    }


def _publish_export(
    req: _Request,
    access: MemoryAccess,
    overlay: MemoryAccess | None,
    plan: _ExportPlan,
) -> dict[str, Any]:
    assert req.invocation_id is not None
    out = plan.out
    effect = {
        "invocation_id": req.invocation_id,
        "effect_id": _effect_id(req.invocation_id, "export", str(out)),
        "request_digest": _export_request_digest(
            req, req.invocation_id, out, req.expected_digest
        ),
    }
    built = _build(
        req,
        plan.sel,
        access,
        overlay,
        out,
        capsule_id=_new_uuid(),
        created_at=_now(),
        effect=effect,
    )
    _check_budget(req, built.required, "export_blocked")
    _recheck(access, overlay)
    receipt = _receipt(
        req, out, built.doc, built.required["bytes"], effect["effect_id"]
    )
    if req.fmt == "rush_v1":
        path, _data, checked = built.files[0]
        try:
            AtomicFile(PhysicalRoot(path.parent)).write_bytes(path.name, checked)
        except (OSError, ValueError, ContainmentError) as exc:
            raise _Fail(
                "E_PERMISSION", "export_target_refused", message="the write failed"
            ) from exc
    else:
        _publish_pas(out, built, receipt, effect)
    return {"code": "OK", "action": "export", **receipt, "replayed": False}


# --- export replay and the PAS two-file publication ---------------------------------


def _export_effect_ok(value: object) -> bool:
    return (
        isinstance(value, dict)
        and set(value) == _EFFECT_KEYS
        and _uuid(value["invocation_id"])
        and _hex64(value["effect_id"])
        and _hex64(value["request_digest"])
    )


def _replay_export(
    req: _Request, out: Path, effect_id: str, request_digest: str, *, act: bool
) -> dict[str, Any] | None:
    """G8-T8: a published capsule (or pair, or journal) of this effect answers the
    retry. `None` is no match; a mismatched request raises."""
    if req.fmt == "rush_v1":
        data = _read_regular(out)
        if data is None:
            return None
        try:
            doc = _check_capsule(_strict_loads(data))
        except _Invalid:
            return None
        marker = doc["manifest"].get("export_effect")
        if marker is None or marker["effect_id"] != effect_id:
            return None
        if marker["request_digest"] != request_digest:
            raise _Fail(
                "E_VERSION",
                "effect_digest_conflict",
                message="this invocation already exported a different request",
            )
        receipt = _receipt(req, out, doc, len(data), effect_id)
        return {"code": "OK", "action": "export", **receipt, "replayed": True}
    paths = _pas_paths(out, effect_id)
    if os.path.lexists(paths["jour"]):
        return _replay_journal(req, paths, effect_id, request_digest, act=act)
    pas = _read_regular(paths["out"])
    side = _read_regular(paths["side"])
    if pas is None or side is None:
        return None
    try:
        sidecar = _check_sidecar(_strict_loads(side))
    except _Invalid:
        return None
    if sidecar["pas_sha256"] != _sha(pas):
        return None
    marker = sidecar["export_effect"]
    if marker["effect_id"] != effect_id:
        return None
    if marker["request_digest"] != request_digest:
        raise _Fail(
            "E_VERSION",
            "effect_digest_conflict",
            message="this invocation already exported a different request",
        )
    receipt = _receipt(req, out, sidecar["capsule"], len(pas) + len(side), effect_id)
    return {"code": "OK", "action": "export", **receipt, "replayed": True}


def _pas_paths(out: Path, effect_id: str) -> dict[str, Path]:
    tag = effect_id[:16]
    parent, name = out.parent, out.name
    return {
        "out": out,
        "side": Path(str(out) + _SIDECAR_SUFFIX),
        "jour": Path(str(out) + _JOURNAL_SUFFIX),
        "stage_pas": parent / f".{name}.rush-stage-pas-{tag}",
        "stage_side": parent / f".{name}.rush-stage-sidecar-{tag}",
        "backup": parent / f".{name}.rush-backup-{tag}",
    }


_ABSENT = "absent"
_OTHER = "other"


def _state_of(path: Path) -> str:
    """A file's sha256, `absent`, or `other` (not a readable regular file)."""
    if not os.path.lexists(path):
        return _ABSENT
    data = _read_regular(path)
    return _sha(data) if data is not None else _OTHER


def _as_state(digest: str | None) -> str:
    return _ABSENT if digest is None else digest


def _load_journal(paths: dict[str, Path]) -> dict[str, Any]:
    """The journal, only when every field is valid and every path is the one this
    output and effect derive (a forged path never steers a replace or unlink)."""
    data = _read_regular(paths["jour"])
    if data is None:
        raise _recovery("the export journal is unreadable")
    try:
        journal = _strict_loads(data)
    except _Invalid as exc:
        raise _recovery("the export journal is invalid") from exc
    pas = journal.get("pas") if isinstance(journal, dict) else None
    side = journal.get("sidecar") if isinstance(journal, dict) else None
    receipt = journal.get("receipt") if isinstance(journal, dict) else None
    valid = (
        isinstance(journal, dict)
        and set(journal) == _JOURNAL_KEYS
        and journal["schema_version"] == 1
        and type(journal["schema_version"]) is int
        and _export_effect_ok(journal["export_effect"])
        and isinstance(receipt, dict)
        and set(receipt) == _RECEIPT_KEYS
        and isinstance(pas, dict)
        and set(pas) == {"path", "old_sha256", "intended_sha256", "stage", "backup"}
        and isinstance(side, dict)
        and set(side) == {"path", "old_sha256", "intended_sha256", "stage"}
    )
    if not valid:
        raise _recovery("the export journal is invalid")
    assert isinstance(pas, dict) and isinstance(side, dict)
    expected_backup = None if pas["old_sha256"] is None else str(paths["backup"])
    if (
        pas["path"] != str(paths["out"])
        or pas["stage"] != str(paths["stage_pas"])
        or pas["backup"] != expected_backup
        or side["path"] != str(paths["side"])
        or side["stage"] != str(paths["stage_side"])
        or not all(
            d is None or _hex64(d) for d in (pas["old_sha256"], side["old_sha256"])
        )
        or not _hex64(pas["intended_sha256"])
        or not _hex64(side["intended_sha256"])
    ):
        raise _recovery("the export journal does not describe this output")
    return cast(dict[str, Any], journal)


def _replay_journal(
    req: _Request,
    paths: dict[str, Path],
    effect_id: str,
    request_digest: str,
    *,
    act: bool,
) -> dict[str, Any]:
    journal = _load_journal(paths)
    marker = journal["export_effect"]
    if marker["effect_id"] != effect_id:
        raise _recovery("another export's recovery is pending for this output")
    if marker["request_digest"] != request_digest:
        raise _Fail(
            "E_VERSION",
            "effect_digest_conflict",
            message="this invocation already exported a different request",
        )
    pas, side = journal["pas"], journal["sidecar"]
    pas_new, pas_old = pas["intended_sha256"], _as_state(pas["old_sha256"])
    side_new, side_old = side["intended_sha256"], _as_state(side["old_sha256"])
    now_pas, now_side = _state_of(paths["out"]), _state_of(paths["side"])
    steps: list[tuple[Path, Path]]
    if now_pas == pas_new and now_side == side_new:
        steps = []
    elif (
        now_pas == pas_new
        and now_side == side_old
        and _state_of(paths["stage_side"]) == side_new
    ):
        steps = [(paths["stage_side"], paths["side"])]
    elif (
        now_pas == pas_old
        and now_side == side_old
        and _state_of(paths["stage_pas"]) == pas_new
        and _state_of(paths["stage_side"]) == side_new
        and (pas["old_sha256"] is None or _state_of(paths["backup"]) == pas_old)
    ):
        steps = [
            (paths["stage_pas"], paths["out"]),
            (paths["stage_side"], paths["side"]),
        ]
    else:
        raise _recovery("the output pair matches neither its old nor its new bytes")
    result = {"code": "OK", "action": "export", **journal["receipt"], "replayed": True}
    if not act:
        return {**result, "_pending": True}
    try:
        for src, dst in steps:
            os.replace(src, dst)
            _fsync_dir(paths["out"].parent)
    except OSError as exc:
        raise _recovery("completing the pair failed; the journal is kept") from exc
    _finish(paths)
    return result


def _fsync_dir(directory: Path) -> None:
    if sys.platform == "win32":
        return
    try:
        fd = os.open(directory, os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(fd)
    except OSError:
        pass
    finally:
        os.close(fd)


def _unlink_quiet(path: Path) -> bool:
    """Unlink `path`; `True` when it is gone afterwards."""
    try:
        os.unlink(path)
    except FileNotFoundError:
        return True
    except OSError:
        return False
    return True


def _finish(paths: dict[str, Path]) -> None:
    """Remove the backup, then the journal; a failure keeps the journal."""
    if not _unlink_quiet(paths["backup"]):
        raise _recovery("the pair is published; removing its backup failed")
    if not _unlink_quiet(paths["jour"]):
        raise _recovery("the pair is published; removing its journal failed")
    _fsync_dir(paths["out"].parent)


def _write_new(path: Path, data: bytes) -> None:
    flags = (
        os.O_WRONLY
        | os.O_CREAT
        | os.O_EXCL
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_BINARY", 0)
    )
    fd = os.open(path, flags, 0o600)
    try:
        view = memoryview(data)
        while view:
            written = os.write(fd, view)
            view = view[written:]
        os.fsync(fd)
    finally:
        os.close(fd)


def _publish_pas(
    out: Path, built: _Built, receipt: dict[str, Any], effect: dict[str, str]
) -> None:
    """G8-T9: stage both files, journal, replace the PAS file, then the sidecar
    (the commit marker). A failure restores only an unchanged partial state."""
    paths = _pas_paths(out, effect["effect_id"])
    (_p, pas, _s), (_q, side, _t) = built.files
    pas_new, side_new = _sha(pas), _sha(side)
    old_pas, old_side = _state_of(paths["out"]), _state_of(paths["side"])
    if _OTHER in (old_pas, old_side):
        raise _recovery("the output pair is not a pair of regular files")
    staged = [paths["stage_pas"], paths["stage_side"], paths["backup"]]

    def discard(*extra: Path) -> None:
        for path in (*staged, *extra):
            _unlink_quiet(path)

    try:
        for path in staged:
            if os.path.lexists(path) and not _unlink_quiet(path):
                raise OSError("a stale staged file cannot be removed")
        _write_new(paths["stage_pas"], pas)
        _write_new(paths["stage_side"], side)
        if old_pas != _ABSENT:
            previous = _read_regular(paths["out"])
            if previous is None or _sha(previous) != old_pas:
                raise OSError("the output changed while staging")
            _write_new(paths["backup"], previous)
        _fsync_dir(out.parent)
        journal = {
            "schema_version": 1,
            "export_effect": effect,
            "receipt": receipt,
            "pas": {
                "path": str(paths["out"]),
                "old_sha256": None if old_pas == _ABSENT else old_pas,
                "intended_sha256": pas_new,
                "stage": str(paths["stage_pas"]),
                "backup": None if old_pas == _ABSENT else str(paths["backup"]),
            },
            "sidecar": {
                "path": str(paths["side"]),
                "old_sha256": None if old_side == _ABSENT else old_side,
                "intended_sha256": side_new,
                "stage": str(paths["stage_side"]),
            },
        }
        AtomicFile(PhysicalRoot(out.parent)).write_bytes(
            paths["jour"].name, SanitizedBytes.from_bytes(canonical_json(journal))
        )
    except (OSError, ValueError, ContainmentError) as exc:
        discard(paths["jour"])
        raise _recovery(
            "staging the capsule pair failed; nothing was published"
        ) from exc
    if (
        _state_of(paths["stage_pas"]) != pas_new
        or _state_of(paths["stage_side"]) != side_new
    ):
        discard(paths["jour"])
        raise _recovery("a staged file changed before publication; nothing published")
    try:
        os.replace(paths["stage_pas"], paths["out"])
        _fsync_dir(out.parent)
    except OSError as exc:
        discard(paths["jour"])
        raise _recovery(
            "publishing the PAS file failed; nothing was published"
        ) from exc
    try:
        os.replace(paths["stage_side"], paths["side"])
        _fsync_dir(out.parent)
    except OSError as exc:
        _restore_partial(paths, pas_new, old_pas, old_side)
        raise _recovery(
            "publishing the sidecar failed; retry the same request to recover"
        ) from exc
    _finish(paths)


def _restore_partial(
    paths: dict[str, Path], pas_new: str, old_pas: str, old_side: str
) -> None:
    """Undo a PAS replace whose sidecar replace failed, only when the PAS file still
    holds the bytes this call wrote, the sidecar still holds its recorded state and
    the backup still holds the recorded old bytes; otherwise keep everything."""
    if (
        _state_of(paths["out"]) != pas_new
        or _state_of(paths["side"]) != old_side
        or (old_pas != _ABSENT and _state_of(paths["backup"]) != old_pas)
    ):
        return
    try:
        if old_pas == _ABSENT:
            os.unlink(paths["out"])
        else:
            os.replace(paths["backup"], paths["out"])
        _fsync_dir(paths["out"].parent)
    except OSError:
        return
    if _unlink_quiet(paths["stage_side"]):
        _unlink_quiet(paths["jour"])
    _fsync_dir(paths["out"].parent)


# --- capsule validation (import) ----------------------------------------------------


def _check_capsule(value: Any) -> dict[str, Any]:
    """A strictly valid `rush_v1` capsule (every key set exact, every hash true)."""
    if not isinstance(value, dict) or set(value) != _CAPSULE_KEYS:
        raise _Invalid("top-level keys")
    if type(value["schema_version"]) is not int or value["schema_version"] != 1:
        raise _Invalid("schema_version")
    if value["format"] != "rush_v1" or not _uuid(value["capsule_id"]):
        raise _Invalid("format or capsule_id")
    created = value["created_at"]
    if type(created) not in (int, float):
        raise _Invalid("created_at")
    try:
        if not math.isfinite(float(created)):
            raise _Invalid("created_at")
    except OverflowError as exc:
        raise _Invalid("created_at") from exc
    origin = value["origin"]
    if (
        not isinstance(origin, dict)
        or set(origin) != _ORIGIN_KEYS
        or not isinstance(origin["rush_version"], str)
        or not _label(origin["project_id"])
        or not _hex64(origin["worktree_id"])
        or not _strict_int(origin["store_revision"], 0)
        or not isinstance(origin["git"], dict)
        or set(origin["git"]) != _GIT_KEYS
        or not _opt_str(origin["git"]["commit"])
        or not _opt_str(origin["git"]["branch"])
        or type(origin["git"]["dirty"]) is not bool
    ):
        raise _Invalid("origin")
    scope = value["scope"]
    if (
        not isinstance(scope, dict)
        or set(scope) != _SCOPE_KEYS
        or not _owner_ref(scope["owner"])
        or not isinstance(scope["sources"], list)
        or not all(_label(s) for s in scope["sources"])
        or (
            scope["personal_owner"] is not None
            and not _owner_ref(scope["personal_owner"])
        )
    ):
        raise _Invalid("scope")
    _check_task(value["task"])
    evidence = value["evidence"]
    if not isinstance(evidence, list) or len(evidence) > MAX_EVIDENCE:
        raise _Invalid("evidence")
    for entry in evidence:
        _check_evidence(entry)
    _check_manifest(value["manifest"])
    payload = value["payload_sha256"]
    rest = {k: v for k, v in value.items() if k != "payload_sha256"}
    try:
        if not _hex64(payload) or _digest(rest) != payload:
            raise _Invalid("payload_sha256")
    except (ValueError, UnicodeError) as exc:
        raise _Invalid("payload") from exc
    return value


def _owner_ref(value: object) -> bool:
    return (
        isinstance(value, dict)
        and set(value) == {"kind", "id"}
        and value["kind"] in _OWNER_KINDS
        and _hex64(value["id"])
    )


def _note_list(value: object, keys: frozenset[str]) -> bool:
    return isinstance(value, list) and all(
        isinstance(item, dict)
        and set(item) == keys
        and all(isinstance(item[k], str) for k in keys)
        for item in value
    )


def _check_task(task: object) -> None:
    if not isinstance(task, dict) or set(task) != _TASK_KEYS:
        raise _Invalid("task keys")
    if not isinstance(task["description"], str) or not isinstance(
        task["objective"], str
    ):
        raise _Invalid("task text")
    if not isinstance(task["next_action"], str) or not task["next_action"]:
        raise _Invalid("next_action")
    if not isinstance(task["completed"], list) or not isinstance(
        task["remaining"], list
    ):
        raise _Invalid("task lists")
    constraints = task["constraints"]
    if not _note_list(constraints, _CONSTRAINT_KEYS) or not all(
        _label(c["constraint_id"]) for c in constraints
    ):
        raise _Invalid("constraints")
    if len({c["constraint_id"] for c in constraints}) != len(constraints):
        raise _Invalid("duplicate constraint ids")
    for key in ("decisions", "failed_approaches", "blockers", "discoveries"):
        if not _note_list(task[key], _NOTE_KEYS):
            raise _Invalid(key)
    last = task["last_verified_checkpoint"]
    if (
        not isinstance(last, dict)
        or set(last) != _CHECKPOINT_KEYS
        or not isinstance(last["command"], list)
        or not all(isinstance(p, str) for p in last["command"])
        or last["status"] != "passed"
        or not isinstance(last["source_revision"], str)
    ):
        raise _Invalid("last_verified_checkpoint")


def _check_evidence(entry: object) -> None:
    from rush.tools.memory import _SUBJECT_FAMILY

    if not isinstance(entry, dict) or set(entry) != _EVIDENCE_KEYS:
        raise _Invalid("evidence keys")
    symbol_ref, source_path = entry["symbol_ref"], entry["source_path"]
    expected_path = (
        symbol_ref.partition("::")[0] if isinstance(symbol_ref, str) else None
    )
    provenance = entry["provenance"]
    if (
        not _label(entry["artifact_id"])
        or not _strict_int(entry["version"], 1)
        or not (entry["content_hash"] is None or _hex64(entry["content_hash"]))
        or entry["subject"] not in _SUBJECT_FAMILY
        or not _label(entry["source"])
        or not _owner_ref(entry["owner"])
        or not isinstance(provenance, dict)
        or set(provenance) != _PROVENANCE_KEYS
        or not isinstance(provenance["trust_tier"], str)
        or not _opt_str(provenance["origin_kind"])
        or not _opt_str(provenance["origin_id"])
        or not _opt_str(symbol_ref)
        or source_path != expected_path
        or (source_path is not None and not _portable_path(source_path))
        or not _opt_str(entry["source_revision"])
        or not _label(entry["freshness"])
        or not isinstance(entry["body"], dict)
    ):
        raise _Invalid("evidence entry")
    try:
        if entry["body_sha256"] != _digest(entry["body"]):
            raise _Invalid("body_sha256")
    except (ValueError, UnicodeError) as exc:
        raise _Invalid("body") from exc


def _check_manifest(manifest: object) -> None:
    if not isinstance(manifest, dict):
        raise _Invalid("manifest")
    keys = set(manifest)
    if keys != _MANIFEST_KEYS and keys != _MANIFEST_KEYS | {"export_effect"}:
        raise _Invalid("manifest keys")
    if "export_effect" in manifest and not _export_effect_ok(manifest["export_effect"]):
        raise _Invalid("export_effect")
    selected = manifest["selected"]
    if not isinstance(selected, list) or not all(
        isinstance(s, dict)
        and set(s) == {"artifact_id", "version"}
        and _label(s["artifact_id"])
        and _strict_int(s["version"], 1)
        for s in selected
    ):
        raise _Invalid("selected")
    for key in ("omitted", "redactions", "local_only_refs"):
        if not isinstance(manifest[key], list):
            raise _Invalid(key)
    for key in ("required_body_coverage", "encoding", "mapping_requirement"):
        if not isinstance(manifest[key], str):
            raise _Invalid(key)
    for key in ("evidence_bytes", "evidence_tokens", "omitted_bytes", "omitted_tokens"):
        if not _strict_int(manifest[key], 0):
            raise _Invalid(key)
    paths = manifest["source_paths"]
    if not isinstance(paths, list) or not all(_portable_path(p) for p in paths):
        raise _Invalid("source_paths")


def _check_sidecar(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != _SIDECAR_KEYS:
        raise _Invalid("sidecar keys")
    if type(value["schema_version"]) is not int or value["schema_version"] != 1:
        raise _Invalid("sidecar schema_version")
    if not _hex64(value["pas_sha256"]) or not _uuid(value["pas_session_id"]):
        raise _Invalid("sidecar binding")
    loss = value["loss"]
    if not isinstance(loss, list) or not all(
        isinstance(e, dict)
        and set(e) == _LOSS_KEYS
        and _label(e["field"])
        and _label(e["disposition"])
        and _opt_str(e["pas_field"])
        for e in loss
    ):
        raise _Invalid("loss")
    if not _export_effect_ok(value["export_effect"]):
        raise _Invalid("sidecar export_effect")
    capsule = _check_capsule(value["capsule"])
    if value["capsule_digest"] != capsule["payload_sha256"]:
        raise _Invalid("capsule_digest")
    return value


# --- PAS schema 1 (import) --------------------------------------------------------


def _pas_uuid(value: object) -> str | None:
    """`uuid::Uuid::from_str`: simple, hyphenated, braced or URN; lowercase out."""
    if not isinstance(value, str):
        return None
    text = value
    wrapped = False
    if text.startswith("urn:uuid:"):
        text, wrapped = text[len("urn:uuid:") :], True
    elif text.startswith("{") and text.endswith("}"):
        text, wrapped = text[1:-1], True
    if _PAS_HYPHENATED_RE.fullmatch(text):
        return str(uuid.UUID(text))
    if not wrapped and _PAS_SIMPLE_RE.fullmatch(text):
        return str(uuid.UUID(hex=text))
    return None


def _pas_time(value: object) -> bool:
    """chrono's relaxed RFC 3339 (`T`, `t` or space; `Z`, `UTC`, `+hh:mm`, `+hhmm`)."""
    if not isinstance(value, str):
        return False
    match = _PAS_TIME_RE.fullmatch(value)
    if match is None:
        return False
    year, month, day, hour, minute, second = (int(match.group(i)) for i in range(1, 7))
    offset = match.group(8)
    if offset[0] in "+-":
        digits = offset[1:].replace(":", "")
        if int(digits[:2]) > 23 or int(digits[2:]) > 59:
            return False
    try:
        datetime(year, month, day, hour, minute, min(second, 59), tzinfo=UTC)
    except ValueError:
        return False
    return second <= 60


def _pas_string(value: object) -> bool:
    return isinstance(value, str) and "\x00" not in value


def _pas_task(value: object) -> dict[str, Any]:
    """TaskState with its serde defaults applied."""
    if not isinstance(value, dict) or not set(value) <= set(_PAS_TASK_KEYS):
        raise _Invalid("PAS task")
    task: dict[str, Any] = {}
    for key in ("description", "objective"):
        item = value.get(key, "")
        if not _pas_string(item):
            raise _Invalid(f"PAS task.{key}")
        task[key] = item
    for key in _PAS_TASK_LISTS:
        items = value.get(key, [])
        if not isinstance(items, list) or not all(_pas_string(i) for i in items):
            raise _Invalid(f"PAS task.{key}")
        task[key] = items
    next_action = value.get("next_action")
    if next_action is not None and not _pas_string(next_action):
        raise _Invalid("PAS next_action")
    task["next_action"] = next_action
    return task


def _pas_git(value: object) -> dict[str, Any] | None:
    if value is None:
        return None
    if not isinstance(value, dict) or not set(value) <= {"branch", "commit", "dirty"}:
        raise _Invalid("PAS git")
    branch, commit = value.get("branch"), value.get("commit")
    dirty = value.get("dirty", False)
    if (
        not (branch is None or _pas_string(branch))
        or not (commit is None or _pas_string(commit))
        or type(dirty) is not bool
    ):
        raise _Invalid("PAS git")
    return {"branch": branch, "commit": commit, "dirty": dirty}


def _pas_status(value: object) -> None:
    if isinstance(value, str):
        if value not in _PAS_STATUSES:
            raise _Invalid("PAS status")
        return
    if (
        not isinstance(value, dict)
        or set(value) != {"Renamed"}
        or not isinstance(value["Renamed"], dict)
        or set(value["Renamed"]) != {"from"}
        or not _portable_path(value["Renamed"]["from"])
    ):
        raise _Invalid("PAS status")


def _parse_pas(data: bytes) -> dict[str, Any]:
    """A pinned PAS-Agent schema-1 session, strictly (serde defaults accepted)."""
    value = _strict_loads(data)
    if not isinstance(value, dict) or not set(value) <= set(_PAS_SESSION_KEYS):
        raise _Invalid("PAS session keys")
    for key in ("id", "project_name", "created_at", "updated_at", "task"):
        if key not in value:
            raise _Invalid(f"PAS {key}")
    version = value.get("schema_version", 1)
    if type(version) is not int or version != 1:
        raise _Invalid("PAS schema_version")
    session_id = _pas_uuid(value["id"])
    if session_id is None or not _pas_string(value["project_name"]):
        raise _Invalid("PAS id or project_name")
    if not _pas_time(value["created_at"]) or not _pas_time(value["updated_at"]):
        raise _Invalid("PAS timestamps")
    task = _pas_task(value["task"])
    _pas_git(value.get("git"))
    checkpoints = value.get("checkpoints", [])
    if not isinstance(checkpoints, list) or len(checkpoints) > MAX_PAS_CHECKPOINTS:
        raise _Invalid("PAS checkpoints")
    for checkpoint in checkpoints:
        if not isinstance(checkpoint, dict) or not set(checkpoint) <= set(
            _PAS_CHECKPOINT_KEYS
        ):
            raise _Invalid("PAS checkpoint")
        for key in ("id", "timestamp", "message", "task_snapshot"):
            if key not in checkpoint:
                raise _Invalid(f"PAS checkpoint {key}")
        if (
            _pas_uuid(checkpoint["id"]) is None
            or not _pas_time(checkpoint["timestamp"])
            or not _pas_string(checkpoint["message"])
        ):
            raise _Invalid("PAS checkpoint fields")
        _pas_task(checkpoint["task_snapshot"])
        _pas_git(checkpoint.get("git"))
        files = checkpoint.get("files_changed", [])
        if not isinstance(files, list) or len(files) > MAX_FILES_CHANGED:
            raise _Invalid("PAS files_changed")
        for entry in files:
            if (
                not isinstance(entry, dict)
                or set(entry) != {"path", "status"}
                or not _portable_path(entry["path"])
            ):
                raise _Invalid("PAS file")
            _pas_status(entry["status"])
    return {"id": session_id, "project_name": value["project_name"], "task": task}


# --- import -----------------------------------------------------------------------


@dataclass
class _Input:
    records: list[dict[str, Any]]
    capsule_digest: str
    input_sha256: str
    origin: tuple[str, str] | None
    required: dict[str, int]
    extra: dict[str, Any]


def _input_refused(message: str) -> _Fail:
    return _Fail("E_PERMISSION", "import_source_refused", message=message)


def _check_input_source(root: Path, path: Path) -> None:
    """MCP: an input (and a sidecar) is a regular file under the project root,
    never a link, checked before any open."""
    from rush.workflows import projects

    if projects._export_under_root(root, path) is None:
        raise _input_refused("over MCP the input must be under the project root")
    try:
        projects.check_export_destination(root, path)
    except ContainmentError as exc:
        raise _input_refused("the input leaves the project root") from exc
    if os.path.islink(path):
        raise _input_refused("over MCP the input may not be a link")


def _records_from_capsule(capsule: dict[str, Any], fmt: str) -> list[dict[str, Any]]:
    """Item 7: the import records of a verified `rush_v1` capsule, in order."""
    from rush.tools.memory import _SUBJECT_FAMILY

    nulls: dict[str, Any] = {
        "foreign_owner": None,
        "foreign_symbol_ref": None,
        "foreign_content_hash": None,
    }
    task = {k: v for k, v in capsule["task"].items() if k != "constraints"}
    records: list[dict[str, Any]] = [
        {
            "foreign_origin_id": "task:" + capsule["capsule_id"],
            "family": "experience",
            "subject": "episodic",
            "content": {
                "kind": "imported_task",
                "origin": capsule["origin"],
                "task": task,
            },
            "foreign_source": fmt,
            **nulls,
        }
    ]
    for item in capsule["task"]["constraints"]:
        records.append(
            {
                "foreign_origin_id": "constraint:" + item["constraint_id"],
                "family": "memory",
                "subject": "domain_knowledge",
                "content": {
                    "kind": "constraint",
                    "constraint_id": item["constraint_id"],
                    "text": item["text"],
                    "origin_ref": item["origin_ref"],
                },
                "foreign_source": fmt,
                **nulls,
            }
        )
    for entry in capsule["evidence"]:
        records.append(
            {
                "foreign_origin_id": f"evidence:{entry['artifact_id']}@{entry['version']}",
                "family": _SUBJECT_FAMILY[entry["subject"]],
                "subject": entry["subject"],
                "content": entry["body"],
                "foreign_source": entry["source"],
                "foreign_owner": entry["owner"],
                "foreign_symbol_ref": entry["symbol_ref"],
                "foreign_content_hash": entry["content_hash"],
            }
        )
    if len({r["foreign_origin_id"] for r in records}) != len(records):
        raise _Invalid("duplicate foreign origin ids")
    return records


def _records_from_pas(session: dict[str, Any]) -> list[dict[str, Any]]:
    """Item 7 for a standalone PAS file: limited, unverified task claims."""
    task = session["task"]
    nulls: dict[str, Any] = {
        "foreign_owner": None,
        "foreign_symbol_ref": None,
        "foreign_content_hash": None,
    }
    records: list[dict[str, Any]] = [
        {
            "foreign_origin_id": "task:" + session["id"],
            "family": "experience",
            "subject": "episodic",
            "content": {
                "kind": "imported_task",
                "origin": {
                    "pas_session_id": session["id"],
                    "project_name": session["project_name"],
                },
                "task": {k: v for k, v in task.items() if k != "constraints"},
            },
            "foreign_source": "pas_v1",
            **nulls,
        }
    ]
    for index, text in enumerate(task["constraints"]):
        pointer = f"/task/constraints/{index}"
        constraint_id = _digest([session["id"], pointer, text])
        records.append(
            {
                "foreign_origin_id": "constraint:" + constraint_id,
                "family": "memory",
                "subject": "domain_knowledge",
                "content": {
                    "kind": "constraint",
                    "constraint_id": constraint_id,
                    "text": text,
                    "origin_ref": pointer,
                },
                "foreign_source": "pas_v1",
                **nulls,
            }
        )
    if len({r["foreign_origin_id"] for r in records}) != len(records):
        raise _Invalid("duplicate PAS constraints")
    return records


def _measure(
    req: _Request, *parts: bytes, hard_cap_only: bool = False
) -> dict[str, int]:
    """The input's bytes and tokens against the hard cap (before parsing, so an
    oversized input is never decoded) or against the request limits."""
    size = sum(len(p) for p in parts)
    tokens = sum(
        retrieval._count_tokens(
            p.decode("utf-8", "replace"), retrieval.DEFAULT_ENCODING
        )
        for p in parts
    )
    required = {"bytes": size, "tokens": tokens}
    if hard_cap_only:
        if size > HARD_MAX_BYTES:
            _check_budget(req, required, "import_blocked")
        return required
    _check_budget(req, required, "import_blocked")
    return required


def _read_input(root: Path, req: _Request, transport: str) -> _Input:
    """Read and validate the complete input (and sidecar) before anything else."""
    assert req.input is not None
    path = _anchor(req.input, root, transport)
    mcp = transport == "mcp"
    sidecar_path = Path(str(path) + _SIDECAR_SUFFIX)
    if mcp:
        _check_input_source(root, path)
        if req.fmt == "pas_v1" and os.path.lexists(sidecar_path):
            _check_input_source(root, sidecar_path)
    data = _read_regular(path, follow=not mcp)
    if data is None:
        raise _invalid("the input is not a readable regular file")
    if req.fmt == "rush_v1":
        if len(data) > HARD_MAX_BYTES:
            _measure(req, data, hard_cap_only=True)
        try:
            capsule = _check_capsule(_strict_loads(data))
            records = _records_from_capsule(capsule, "rush_v1")
        except _Invalid as exc:
            raise _invalid() from exc
        required = _measure(req, data)
        origin = capsule["origin"]
        return _Input(
            records,
            capsule["payload_sha256"],
            _sha(data),
            (origin["project_id"], origin["worktree_id"]),
            required,
            {},
        )
    if os.path.lexists(Path(str(path) + _JOURNAL_SUFFIX)):
        raise _invalid("the PAS pair is incomplete: an export journal is pending")
    side: bytes | None = None
    if os.path.lexists(sidecar_path):
        side = _read_regular(sidecar_path, follow=not mcp)
        if side is None:
            raise _invalid("the PAS sidecar is not a readable regular file")
    parts = [data, *([side] if side is not None else [])]
    if sum(len(part) for part in parts) > HARD_MAX_BYTES:
        _measure(req, *parts, hard_cap_only=True)
    input_sha = _digest([_sha(data), _sha(side) if side is not None else None])
    try:
        session = _parse_pas(data)
        if side is None:
            missing = ["evidence", "last_verified_checkpoint"]
            if not session["task"]["next_action"]:
                missing.insert(0, "next_action")
            records = _records_from_pas(session)
            return _Input(
                records,
                _sha(data),
                input_sha,
                None,
                _measure(req, *parts),
                {"limited": True, "missing_continuation": missing},
            )
        sidecar = _check_sidecar(_strict_loads(side))
        if (
            sidecar["pas_sha256"] != _sha(data)
            or sidecar["pas_session_id"] != session["id"]
        ):
            raise _Invalid("the sidecar does not bind this PAS file")
        capsule = sidecar["capsule"]
        records = _records_from_capsule(capsule, "pas_v1")
    except _Invalid as exc:
        raise _invalid() from exc
    origin = capsule["origin"]
    return _Input(
        records,
        capsule["payload_sha256"],
        input_sha,
        (origin["project_id"], origin["worktree_id"]),
        _measure(req, *parts),
        {},
    )


def _origin_owner(
    root: Path, req: _Request, origin: tuple[str, str] | None
) -> tuple[OwnerScope | None, str]:
    """G8-T13: the import owner and `origin_match`."""
    if origin is None:
        if req.mapping_id is not None:
            raise _Fail(
                "E_PERMISSION",
                "mapping_mismatch",
                message="a standalone PAS file carries no origin a mapping can match",
            )
        return req.owner, "absent"
    if req.mapping_id is None:
        local = auth.project_identity(root)
        if (
            local["project_id"] is not None
            and local["worktree_id"] is not None
            and origin == (local["project_id"], local["worktree_id"])
        ):
            return req.owner, "claimed"
        raise _Fail(
            "E_PERMISSION",
            "mapping_required",
            message="the capsule comes from another project or worktree; "
            "approve a mapping with `rush memory capsule mapping create`",
        )
    try:
        resolved = auth.resolve_capsule_mapping(
            mapping_id=req.mapping_id,
            origin_project_id=origin[0],
            origin_worktree_id=origin[1],
            project_root=root,
        )
    except auth.MemoryPolicyError as exc:
        raise _Fail(exc.code, exc.reason or "mapping_mismatch") from exc
    target = resolved["mapping"]["target_owner_scope"]
    owner = OwnerScope(target["kind"], target["id"])
    if req.owner is not None and req.owner != owner:
        raise _Fail(
            "E_PERMISSION",
            "mapping_mismatch",
            message="the owner differs from the mapping's target owner",
        )
    return owner, "mapped"


def _seam_failure(exc: Exception) -> _Fail:
    code = getattr(exc, "code", None) or "E_PERMISSION"
    reason = getattr(exc, "reason", None)
    if isinstance(exc, MemoryMigrationRequiredError):
        return _Fail("E_MIGRATION", "migration_required", message=str(exc))
    return _Fail(str(code), reason, message=str(exc) or None)


_SEAM_ERRORS = (
    auth.MemoryPolicyError,
    MemoryStoreUnreadableError,
    MemoryMigrationRequiredError,
)


def _seam_preview(
    access: MemoryAccess, inp: _Input, req: _Request, mapping_id: str | None
) -> dict[str, Any]:
    """D18 `preview_import_records` (R13 route: read-only)."""
    try:
        result = cast(Any, TypedArtifactStore).preview_import_records(
            records=tuple(inp.records),
            capsule_digest=inp.capsule_digest,
            confirm_constraint_ids=req.confirm,
            mapping_id=mapping_id,
            access=access,
        )
    except _SEAM_ERRORS as exc:
        raise _seam_failure(exc) from exc
    return cast(dict[str, Any], result)


def _seam_apply(
    access: MemoryAccess,
    inp: _Input,
    req: _Request,
    preview: dict[str, Any],
    *,
    effect_id: str,
    request_digest: str,
) -> dict[str, Any]:
    """D18 replay lookup and `apply_import_records` (R13 route: the one write)."""
    assert req.invocation_id is not None and req.expected_store_revision is not None
    try:
        result = cast(Any, TypedArtifactStore).apply_import_records(
            records=tuple(inp.records),
            preview_binding=preview["preview_binding"],
            expected_store_revision=req.expected_store_revision,
            expected_versions=preview["expected_versions"],
            confirm_foreign_ids=tuple(r["foreign_origin_id"] for r in inp.records),
            confirm_constraint_ids=req.confirm,
            invocation_id=req.invocation_id,
            effect_id=effect_id,
            request_digest=request_digest,
            access=access,
        )
    except _SEAM_ERRORS as exc:
        raise _seam_failure(exc) from exc
    return cast(dict[str, Any], result)


def _seam_replay(
    access: MemoryAccess, req: _Request, effect_id: str, request_digest: str
) -> dict[str, Any] | None:
    """D29 replay of a committed import (R13 route: read-only)."""
    assert req.invocation_id is not None
    try:
        found = cast(Any, TypedArtifactStore).find_import_effect_readonly(
            invocation_id=req.invocation_id,
            effect_id=effect_id,
            request_digest=request_digest,
            access=access,
        )
    except _SEAM_ERRORS as exc:
        raise _seam_failure(exc) from exc
    if isinstance(found, dict) and found.get("state") == "present":
        return cast(dict[str, Any], found["result"])
    return None


def _import_digest(
    req: _Request, invocation_id: str, inp: _Input, policy_revision: int, owner: Any
) -> str:
    selectors = {"include_personal": False}
    if owner is not None:
        selectors["owner_scope"] = owner
    return _digest(
        {
            "action": "import",
            "format": req.fmt,
            "invocation_id": invocation_id,
            "selectors": selectors,
            "mapping_id": req.mapping_id,
            "confirm_constraint_ids": list(req.confirm),
            "max_bytes": req.max_bytes,
            "max_tokens": req.max_tokens,
            "policy_revision": policy_revision,
            "input_sha256": inp.input_sha256,
            "source_store_revision": None,
            "selected_ids": [r["foreign_origin_id"] for r in inp.records],
            "target": {"path": _IMPORT_TARGET},
        }
    )


def _import(root: Path, req: _Request, transport: str) -> dict[str, Any]:
    inp = _read_input(root, req, transport)
    owner, origin_match = _origin_owner(root, req, inp.origin)
    access = _resolve(root, req.action, owner=owner, sources=None, legacy=req.legacy)
    invocation_id = req.invocation_id or _new_uuid()
    target = str(_storage_root(access) / ".rush" / _STORE_DB)
    effect_id = _effect_id(invocation_id, "import", target)
    owner_digest = req.owner.as_dict() if req.owner is not None else None
    digest = _import_digest(
        req, invocation_id, inp, _policy_revision(access), owner_digest
    )
    if req.action == "preview_import":
        constraint_ids = {
            r["content"]["constraint_id"]
            for r in inp.records
            if r["content"].get("kind") == "constraint"
        }
        unknown = [c for c in req.confirm if c not in constraint_ids]
        if unknown:
            raise _bad(
                "confirm_constraint_ids",
                "confirm_constraint_ids names a constraint this capsule does not hold",
            )
        preview = _seam_preview(access, inp, req, req.mapping_id)
        return {
            "code": "OK",
            "action": req.action,
            "format": req.fmt,
            "invocation_id": invocation_id,
            "effect_id": effect_id,
            "digest": digest,
            "capsule_digest": inp.capsule_digest,
            "origin_match": origin_match,
            "mapping_id": req.mapping_id,
            "records": preview["records"],
            "redactions": preview["redactions"],
            "store_state": preview["store_state"],
            "store_revision": preview["store_revision"],
            "expected_versions": preview["expected_versions"],
            "required": inp.required,
            **inp.extra,
        }
    assert req.expected_digest is not None
    request_digest = _digest(
        {
            "action": "import",
            "expected_digest": req.expected_digest,
            "expected_store_revision": req.expected_store_revision,
        }
    )
    _recheck(access)

    def checks(*, act: bool) -> dict[str, Any] | None:
        stored = _seam_replay(access, req, effect_id, request_digest)
        if stored is not None:
            return {
                "code": "OK",
                "action": "import",
                "format": req.fmt,
                "invocation_id": invocation_id,
                "effect_id": effect_id,
                **stored,
                "replayed": True,
            }
        if digest != req.expected_digest:
            raise _recovery("the import changed since its preview")
        preview = _seam_preview(access, inp, req, req.mapping_id)
        if preview["store_state"] == "migration_required":
            raise _Fail(
                "E_MIGRATION",
                "migration_required",
                message=readonly_view_reason("migration_required"),
            )
        if preview["store_revision"] != req.expected_store_revision:
            raise _Fail(
                "E_VERSION", "store_changed", message="the store changed since preview"
            )
        if not act:
            return None
        result = _seam_apply(
            access,
            inp,
            req,
            preview,
            effect_id=effect_id,
            request_digest=request_digest,
        )
        return {
            "code": "OK",
            "action": "import",
            "format": req.fmt,
            "invocation_id": invocation_id,
            "effect_id": effect_id,
            "capsule_digest": result.get("capsule_digest", inp.capsule_digest),
            "mappings": result["mappings"],
            "replayed": False,
        }

    # One unlocked pass first: a refusal leaves no lock file behind.
    early = checks(act=False)
    if early is not None:
        return early
    with _locked(target, access):
        outcome = checks(act=True)
    assert outcome is not None
    return outcome


__all__ = [
    "DEFAULT_MAX_BYTES",
    "DEFAULT_MAX_TOKENS",
    "HARD_MAX_BYTES",
    "HARD_MAX_TOKENS",
    "MAX_DEPTH",
    "MAX_EVIDENCE",
    "MAX_FILES_CHANGED",
    "MAX_PAS_CHECKPOINTS",
    "run_capsule",
]
