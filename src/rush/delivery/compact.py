"""Compact result delivery and recoverable result views (Phase 70 T16).

`deliver` is the single entry point both transports call once per request
(W2 finding 11): it validates the view options, rejects `--no-cache` with
compact, requires the cache-write grant and preflights CCR containment --
all before anything runs -- then executes, redacts the full result, stores
it in `.rush/cache/ccr.db` and returns a bounded projection.

`project_page` and the bytes slicer serve `retrieve_result_view`
(`rush.continuity.context`), so a compact delivery and a later page share
one projection. Sizes are measured with the transport's real serializer.
"""

from __future__ import annotations

import base64
import binascii
import copy
import hashlib
import json
import os
import re
import sqlite3
from collections.abc import Callable
from contextlib import closing
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Any

from pydantic import WithJsonSchema

from rush.io.physical_paths import PhysicalRoot
from rush.safety.redactor import sanitize_value
from rush.token_economy.ccr_store import CCRStore

DEFAULT_LIMIT = 50
DEFAULT_MAX_BYTES = 32_768
LIMIT_BOUNDS = (1, 50)
MAX_BYTES_BOUNDS = (4_096, 65_536)
#: R16.6: fixed allowance for the JSON-RPC frame around a CallToolResult.
MCP_RESERVE_BYTES = 96
CCR_RELATIVE = ".rush/cache/ccr.db"
STORE_KEYS = frozenset({"version", "created_at", "full_result", "finding_ids"})
_HANDLE = re.compile(r"[0-9a-f]{64}")

Serializer = Callable[[dict[str, Any]], int]
Prepared = tuple[Path, Callable[[], Any]]

_HELP = (
    "Compact output stores the full redacted result in the local cache "
    "(.rush/cache/ccr.db). Pass --allow-cache-write (MCP: allow_cache_write="
    "true), or use the full view (--result-view full), which writes nothing."
)

# Published MCP parameter types: plain values, so FastMCP's argument model
# never coerces `True` to 1 before Rush's own strict validation runs.
ResultViewParam = Annotated[
    Any,
    WithJsonSchema(
        {
            "anyOf": [
                {"type": "string", "enum": ["full", "compact"]},
                {"type": "null"},
            ],
            "description": "full (default) returns the whole result; compact stores "
            "it (requires allow_cache_write) and returns a bounded page and handle.",
        }
    ),
]
LimitParam = Annotated[
    Any,
    WithJsonSchema(
        {
            "anyOf": [
                {"type": "integer", "minimum": 1, "maximum": 50},
                {"type": "null"},
            ],
            "description": "Findings per page, 1-50 (default 50).",
        }
    ),
]
MaxBytesParam = Annotated[
    Any,
    WithJsonSchema(
        {
            "anyOf": [
                {"type": "integer", "minimum": 4096, "maximum": 65536},
                {"type": "null"},
            ],
            "description": "Size budget of the whole serialized response, "
            "4096-65536 bytes (default 32768).",
        }
    ),
]


class ViewError(Exception):
    """A rejected view request: a structured error result, never a traceback."""

    def __init__(self, code: str, message: str, help_text: str | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.help_text = help_text


@dataclass(frozen=True)
class ViewOptions:
    """One request's view options, exactly as the transport received them."""

    result_view: Any = None
    limit: Any = None
    max_bytes: Any = None
    no_cache: bool = False

    @property
    def compact(self) -> bool:
        return self.result_view == "compact"


def _strict_int(name: str, value: Any, bounds: tuple[int, int]) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise ViewError("RESULT_VIEW_INVALID", f"{name} must be an integer")
    if not bounds[0] <= value <= bounds[1]:
        raise ViewError(
            "RESULT_VIEW_INVALID",
            f"{name} must be between {bounds[0]} and {bounds[1]}; got {value}",
        )
    return value


def validate_budget(limit: Any, max_bytes: Any) -> tuple[int, int]:
    """S16.4: `limit` 1-50 and `max_bytes` 4096-65536, integers, never bool."""
    return (
        _strict_int("limit", limit, LIMIT_BOUNDS) or DEFAULT_LIMIT,
        _strict_int("max_bytes", max_bytes, MAX_BYTES_BOUNDS) or DEFAULT_MAX_BYTES,
    )


def validate(options: ViewOptions) -> tuple[int, int]:
    if options.result_view not in (None, "full", "compact"):
        raise ViewError(
            "RESULT_VIEW_INVALID",
            f"result_view must be 'full' or 'compact'; got {options.result_view!r}",
        )
    return validate_budget(options.limit, options.max_bytes)


def error_payload(
    tool: str,
    code: str,
    message: str,
    *,
    help_text: str | None = None,
    analysis_status: str | None = None,
) -> dict[str, Any]:
    """A delivery error: status `error` (exit 2) and never a result handle."""
    from rush.runtime.result_helpers import error_result

    error: dict[str, Any] = {"code": code, "message": message}
    if help_text is not None:
        error["help"] = help_text
    return dict(
        error_result(
            tool,
            None,
            f"{code}: {message}",
            metadata={
                "error": error,
                "delivery": {
                    "schema_version": 1,
                    "complete": False,
                    "result_handle": None,
                    "analysis_status": analysis_status,
                },
            },
        )
    )


def canonical_json(value: Any) -> bytes:
    """§3 item 7: the one byte form stored, hashed and cursor-encoded."""
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def cli_size(value: dict[str, Any]) -> int:
    """R16.6: exactly what the CLI prints for `--json` (plus its newline)."""
    return len(json.dumps(value, indent=2, default=str).encode("utf-8")) + 1


def mcp_size(convert: Callable[[Any], Any]) -> Serializer:
    """R16.6: the real MCP CallToolResult (text content and, for a tool with
    an output schema, structuredContent) plus the JSON-RPC reserve."""
    from mcp.types import CallToolResult

    def size(value: dict[str, Any]) -> int:
        converted = convert(value)
        content, structured = (
            converted if isinstance(converted, tuple) else (converted, None)
        )
        envelope = CallToolResult(content=list(content), structuredContent=structured)
        body = envelope.model_dump_json(by_alias=True, exclude_none=True)
        return len(body.encode("utf-8")) + MCP_RESERVE_BYTES

    return size


def retrieval_size(value: dict[str, Any]) -> int:
    """Retrieval pages leave through either transport; budget the larger."""
    from mcp.types import CallToolResult, TextContent

    text = json.dumps(value, indent=2, default=str)
    envelope = CallToolResult(
        content=[TextContent(type="text", text=text)],
        structuredContent={"result": value},
    )
    body = envelope.model_dump_json(by_alias=True, exclude_none=True)
    return max(cli_size(value), len(body.encode("utf-8")) + MCP_RESERVE_BYTES)


def ccr_path(root: Path, purpose: str) -> Path:
    """§3 items 7.4/10.2: the contained CCR database path (symlinks rejected,
    nothing created)."""
    return PhysicalRoot(root).open_contained(CCR_RELATIVE, purpose=purpose)


def finding_identity(finding: dict[str, Any]) -> str:
    fingerprint = finding.get("fingerprint")
    if isinstance(fingerprint, str) and fingerprint:
        return fingerprint
    return hashlib.sha256(canonical_json(finding)).hexdigest()


# -- cursors (§3 item 9, R16.7: unsigned, never authorization) ---------------


def _root_hash(root: Path) -> str:
    return hashlib.sha256(os.path.realpath(root).encode("utf-8")).hexdigest()


def encode_cursor(
    root: Path, handle: str, view: str, nxt: int, limit: int, max_bytes: int
) -> str:
    payload = {
        "v": 1,
        "root": _root_hash(root),
        "handle": handle,
        "view": view,
        "next": nxt,
        "limit": limit,
        "max_bytes": max_bytes,
    }
    return base64.urlsafe_b64encode(canonical_json(payload)).decode("ascii")


def decode_cursor(
    cursor: str,
    *,
    root: Path,
    handle: str,
    view: str,
    limit: int,
    max_bytes: int,
    total: int,
) -> int:
    """The cursor's `next`, when every field equals the current request."""
    try:
        raw = base64.urlsafe_b64decode(
            cursor.encode("ascii") + b"=" * (-len(cursor) % 4)
        )
        payload = json.loads(raw)
    except (ValueError, binascii.Error, UnicodeError):
        payload = None
    expected = {
        "v": 1,
        "root": _root_hash(root),
        "handle": handle,
        "view": view,
        "limit": limit,
        "max_bytes": max_bytes,
    }
    if not isinstance(payload, dict) or set(payload) != {*expected, "next"}:
        raise ViewError("RESULT_CURSOR_INVALID", "cursor is malformed")
    nxt = payload["next"]
    if any(payload[key] != value for key, value in expected.items()) or not (
        isinstance(nxt, int) and not isinstance(nxt, bool) and 0 <= nxt <= total
    ):
        raise ViewError(
            "RESULT_CURSOR_INVALID",
            "cursor does not match this root, handle, view or budget",
        )
    return nxt


# -- projection (§3 item 8) ----------------------------------------------------


def _reference(value: Any, identity: dict[str, Any] | None = None) -> dict[str, Any]:
    body = canonical_json(value)
    ref: dict[str, Any] = {
        "content_omitted": True,
        "reason": "compact_view",
        "bytes": len(body),
        "sha256": hashlib.sha256(body).hexdigest(),
    }
    if identity is not None:
        ref["identity"] = identity
    return ref


def _finding_reference(finding: dict[str, Any], finding_id: str) -> dict[str, Any]:
    identity = {"finding_id": finding_id}
    identity.update(
        {key: finding[key] for key in ("path", "line", "rule") if key in finding}
    )
    return _reference(finding, identity)


Slot = tuple[dict[str, Any] | list[Any], Any]


def _metadata_slots(metadata: dict[str, Any]) -> list[list[Slot]]:
    """Engine summaries, scope lists, memory receipts, then whole engine
    entries and the scope (the minimum envelope references everything)."""
    engines = metadata.get("engines")
    engines = engines if isinstance(engines, list) else []
    entries = [e for e in engines if isinstance(e, dict)]
    scopes: list[dict[str, Any]] = [
        scope
        for scope in (metadata.get("scope"), *(e.get("scope") for e in entries))
        if isinstance(scope, dict)
    ]
    whole: list[Slot] = [
        (engines, i) for i, e in enumerate(engines) if isinstance(e, dict)
    ]
    if isinstance(metadata.get("scope"), dict):
        whole.append((metadata, "scope"))
    return [
        [(entry, "summary") for entry in entries if "summary" in entry],
        [
            (scope, key)
            for scope in scopes
            for key, value in scope.items()
            if isinstance(value, list)
        ],
        [(metadata, key) for key in metadata if "memory" in key or "receipt" in key],
        whole,
    ]


def _slots(proj: dict[str, Any]) -> list[Slot]:
    """Omittable fields in design order, largest first within each group,
    finding values last."""
    findings: list[Slot] = [(proj["findings"], i) for i in range(len(proj["findings"]))]
    return [
        slot
        for group in [*_metadata_slots(proj["metadata"]), findings]
        for slot in sorted(group, key=lambda s: -len(canonical_json(s[0][s[1]])))
    ]


def _omit(
    proj: dict[str, Any],
    ids: list[str],
    threshold: int,
    fits: Callable[[], bool],
    *,
    findings: bool,
) -> bool:
    """Replace variable fields larger than `threshold` bytes by references,
    largest first in design order, until the projection fits; returns
    whether anything was omitted."""
    omitted = False
    for container, key in _slots(proj):
        if fits():
            break
        is_finding = container is proj["findings"]
        value = container[key]
        if (is_finding and not findings) or (
            isinstance(value, dict) and value.get("content_omitted")
        ):
            continue
        ref = _finding_reference(value, ids[key]) if is_finding else _reference(value)
        size = len(canonical_json(value))
        if size > threshold and size > len(canonical_json(ref)):
            container[key] = ref
            omitted = True
    return omitted


def _envelope(
    full: dict[str, Any], delivery: dict[str, Any], page: list[dict[str, Any]]
) -> dict[str, Any]:
    proj = copy.deepcopy(
        {k: v for k, v in full.items() if k not in ("findings", "raw")}
    )
    proj["findings"] = copy.deepcopy(page)
    raw = full.get("raw")
    proj["raw"] = None if raw is None else _reference(raw)
    metadata = dict(proj.get("metadata") or {})
    metadata["delivery"] = delivery
    proj["metadata"] = metadata
    return proj


def project_page(
    full: dict[str, Any],
    finding_ids: list[str],
    *,
    root: Path,
    handle: str,
    view: str,
    start: int,
    limit: int,
    max_bytes: int,
    full_bytes: int,
    serialize: Serializer,
) -> dict[str, Any]:
    """The largest page of findings from `start` that fits `max_bytes`,
    oversized fields replaced by references first, then trailing findings
    dropped. Raises RESULT_BUDGET_TOO_SMALL if even zero findings do not fit."""
    findings = list(full.get("findings") or [])
    total = len(findings)
    page_ids = finding_ids[start : start + limit]

    def build(count: int) -> tuple[dict[str, Any], bool]:
        nxt = start + count
        delivery = {
            "schema_version": 1,
            "view": view,
            "result_handle": handle,
            "total_findings": total,
            "returned_findings": count,
            "complete": False,
            "next_cursor": encode_cursor(root, handle, "result", nxt, limit, max_bytes)
            if nxt < total
            else None,
            "max_bytes": max_bytes,
            "full_result_bytes": full_bytes,
        }
        proj = _envelope(full, delivery, findings[start:nxt])

        def fits() -> bool:
            return serialize(proj) <= max_bytes

        # Oversized values (over a quarter of the budget) first; then every
        # other variable field, so zero findings is the minimum envelope.
        omitted = _omit(proj, page_ids, max_bytes // 4, fits, findings=True)
        omitted = _omit(proj, page_ids, 0, fits, findings=False) or omitted
        delivery["complete"] = start == 0 and nxt == total and not omitted
        return proj, serialize(proj) <= max_bytes

    count = min(limit, max(total - start, 0))
    proj, fits = build(count)
    if fits:
        return proj
    low, high, best = 0, count - 1, None
    while low <= high:
        middle = (low + high) // 2
        candidate, ok = build(middle)
        if ok:
            best, low = candidate, middle + 1
        else:
            high = middle - 1
    if best is None:
        raise ViewError(
            "RESULT_BUDGET_TOO_SMALL",
            f"max_bytes={max_bytes} cannot hold even an empty page",
        )
    return best


def slice_bytes(
    stored: dict[str, Any],
    data: bytes,
    *,
    root: Path,
    handle: str,
    offset: int,
    limit: int,
    max_bytes: int,
    serialize: Serializer,
) -> dict[str, Any]:
    """§3 item 10.7: the longest UTF-8-safe slice from `offset` whose whole
    page fits `max_bytes`."""
    total = len(data)
    if offset > total or (offset < total and data[offset] & 0xC0 == 0x80):
        raise ViewError(
            "RESULT_VIEW_INVALID", f"offset {offset} is not a UTF-8 boundary"
        )
    full = stored["full_result"]

    def build(length: int) -> dict[str, Any]:
        end = offset + length
        while end < total and end > offset and data[end] & 0xC0 == 0x80:
            end -= 1
        nxt = end if end < total else None
        return {
            "tool": full.get("tool"),
            "status": full.get("status"),
            "duration_ms": full.get("duration_ms", 0),
            "summary": full.get("summary", ""),
            "findings": [],
            "raw": {
                "view": "bytes",
                "offset": offset,
                "length": end - offset,
                "total_bytes": total,
                "sha256": handle,
                "content": data[offset:end].decode("utf-8"),
                "next_offset": nxt,
            },
            "metadata": {
                "delivery": {
                    "schema_version": 1,
                    "view": "bytes",
                    "result_handle": handle,
                    "complete": offset == 0 and nxt is None,
                    "next_cursor": encode_cursor(
                        root, handle, "bytes", nxt, limit, max_bytes
                    )
                    if nxt is not None
                    else None,
                    "max_bytes": max_bytes,
                    "full_result_bytes": total,
                }
            },
        }

    low, high, best = 0, total - offset, None
    while low <= high:
        middle = (low + high) // 2
        candidate = build(middle)
        if serialize(candidate) <= max_bytes:
            best, low = candidate, middle + 1
        else:
            high = middle - 1
    if best is None or (best["raw"]["length"] == 0 and offset < total):
        raise ViewError(
            "RESULT_BUDGET_TOO_SMALL",
            f"max_bytes={max_bytes} cannot hold any content from offset {offset}",
        )
    return best


# -- store ---------------------------------------------------------------------


def is_storage_object(content: str) -> bool:
    """Finding 28: exactly a T16 storage object `{version:1, created_at,
    full_result, finding_ids}` -- never a context pack."""
    try:
        value = json.loads(content)
    except ValueError:
        return False
    return (
        isinstance(value, dict) and set(value) == STORE_KEYS and value["version"] == 1
    )


def purge_compact_results(root: Path) -> tuple[int, int]:
    """R16.8/finding 28: delete only T16 storage rows from ccr.db; returns
    (purged, retained). A missing database is never created."""
    db = ccr_path(root, "write")
    if not db.is_file():
        return 0, 0
    with closing(sqlite3.connect(db)) as conn, conn:
        rows = conn.execute("SELECT hash, content FROM chunks").fetchall()
        purge = [(digest,) for digest, content in rows if is_storage_object(content)]
        conn.executemany("DELETE FROM chunks WHERE hash = ?", purge)
    return len(purge), len(rows) - len(purge)


def _as_dict(result: Any) -> dict[str, Any]:
    return result.to_dict() if hasattr(result, "to_dict") else dict(result)


def _store(root: Path, full: dict[str, Any]) -> tuple[str, int, list[str]]:
    finding_ids = [finding_identity(f) for f in full.get("findings") or []]
    content = canonical_json(
        {
            "version": 1,
            "created_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            "full_result": full,
            "finding_ids": finding_ids,
        }
    )
    ccr_path(root, "write")
    CCRStore(root).store_chunk(content.decode("utf-8"))
    return hashlib.sha256(content).hexdigest(), len(content), finding_ids


def _compact(
    tool_name: str,
    full_result: Any,
    *,
    root: Path,
    limit: int,
    max_bytes: int,
    serialize: Serializer,
    export: Callable[[dict[str, Any]], None] | None,
) -> dict[str, Any]:
    redacted = sanitize_value(_as_dict(full_result)).value
    full = json.loads(json.dumps(redacted, default=str))
    try:
        handle, size, ids = _store(root, full)
    except (sqlite3.Error, OSError, ValueError) as exc:
        return error_payload(
            tool_name,
            "RESULT_STORE_FAILED",
            f"the full result could not be stored: {type(exc).__name__}",
            analysis_status=full.get("status"),
        )
    if export is not None:
        export(full)
    return project_page(
        full,
        ids,
        root=root,
        handle=handle,
        view="compact",
        start=0,
        limit=limit,
        max_bytes=max_bytes,
        full_bytes=size,
        serialize=serialize,
    )


def deliver(
    tool_name: str,
    options: ViewOptions,
    *,
    cache_write: bool,
    prepare: Callable[[], Prepared | dict[str, Any]],
    serialize: Serializer,
    export: Callable[[dict[str, Any]], None] | None = None,
) -> Any:
    """§3 item 7: validate, conflict check, grant check, containment
    preflight -- zero spawns and zero writes before any of them fails --
    then execute, and for compact redact, store and project. `prepare`
    returns `(logical_root, run)` or a ready error result."""
    try:
        limit, max_bytes = validate(options)
        if options.compact and options.no_cache:
            raise ViewError(
                "RESULT_VIEW_CACHE_CONFLICT",
                "compact output stores the result, which --no-cache forbids",
            )
        if options.compact and not cache_write:
            raise ViewError(
                "RESULT_VIEW_REQUIRES_CACHE_WRITE",
                "compact output needs the cache-write grant",
                _HELP,
            )
        prepared = prepare()
        if not isinstance(prepared, tuple):
            return prepared
        root, run = prepared
        if not options.compact:
            return run()
        ccr_path(root, "write")
        return _compact(
            tool_name,
            run(),
            root=root,
            limit=limit,
            max_bytes=max_bytes,
            serialize=serialize,
            export=export,
        )
    except ViewError as exc:
        return error_payload(tool_name, exc.code, exc.message, help_text=exc.help_text)


__all__ = [
    "DEFAULT_LIMIT",
    "DEFAULT_MAX_BYTES",
    "MCP_RESERVE_BYTES",
    "LimitParam",
    "MaxBytesParam",
    "ResultViewParam",
    "ViewError",
    "ViewOptions",
    "canonical_json",
    "ccr_path",
    "cli_size",
    "decode_cursor",
    "deliver",
    "error_payload",
    "is_storage_object",
    "mcp_size",
    "project_page",
    "purge_compact_results",
    "retrieval_size",
    "slice_bytes",
    "validate_budget",
]
