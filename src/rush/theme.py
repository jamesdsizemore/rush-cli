"""Neon palette + rich style helpers.

Architecture §9, requirement C8.
- CYAN   #22D3EE — primary, ok
- GREEN  #22FF88 — secondary, active
- YELLOW #FFE600 — tertiary, review-needed, warn
- PINK   #EC4899 — failed status only (bright, not red)
- GREY   #6B7280 — skipped, muted

Red is banned. Yellow is allowed (review-needed / warnings).

T27: every dynamic string reaches the terminal as `Text(safe_terminal_text(v))`
(never interpolated into markup), and the body under the status line comes
from the result's family projection (`FAMILY_PROJECTIONS`).
"""

from __future__ import annotations

import base64
import json
import re
import shlex
import sys
from collections.abc import Callable, Mapping
from typing import Any

import click
from rich.console import Console
from rich.panel import Panel
from rich.style import Style
from rich.table import Table
from rich.text import Text
from rich.theme import Theme

from rush.catalog import TOOL_SPECS

CYAN = "#22D3EE"
GREEN = "#22FF88"
YELLOW = "#FFE600"
PINK = "#EC4899"
GREY = "#6B7280"

RUSH_THEME = Theme(
    {
        "status.ok": Style(color=CYAN),
        "status.warn": Style(color=YELLOW),
        "status.fail": Style(color=PINK, bold=True),
        "status.error": Style(color=PINK, bold=True),
        "status.skipped": Style(color=GREY),
        "severity.info": Style(color=CYAN),
        "severity.warn": Style(color=YELLOW),
        "severity.error": Style(color=PINK),
        "tool.review": Style(color=GREEN),
        "tool.lint": Style(color=CYAN),
        "tool.format": Style(color=GREEN),
        "tool.test": Style(color=CYAN),
        "tool.security": Style(color=YELLOW),
    }
)

_shared_console: Console | None = None


def console() -> Console:
    """Return a shared Console wired to the rush theme.

    NB: stdout-bound by default. For MCP contexts, call with ``force_terminal=False``
    and capture output via rich's file= argument — never write to stdout except
    the final ToolResult JSON.
    """
    global _shared_console
    if _shared_console is None:
        _shared_console = Console(theme=RUSH_THEME)
    return _shared_console


# A CR directly before LF is a CRLF line ending, kept so verbatim CRLF
# source stays readable; a lone CR (cursor return) is still escaped. 72-T07: the
# bidi controls (U+061C, U+200E/F, U+202A-E, U+2066-9) are escaped too, so no
# dynamic string can reorder what the terminal shows.
_UNSAFE_CONTROL = re.compile(
    r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f\u061c\u200e\u200f\u202a-\u202e\u2066-\u2069]"
    r"|\r(?!\n)"
)


def _escape_control(match: re.Match[str]) -> str:
    code = ord(match.group())
    return f"\\x{code:02x}" if code <= 0xFF else f"\\u{code:04x}"


def safe_terminal_text(value: object) -> str:
    """X3: every C0 control except newline, tab and a CRLF's CR, plus DEL and
    C1, as a visible `\\xNN` escape, and every bidi control as `\\uNNNN`, so no
    dynamic string can clear the screen, retitle the terminal, move the cursor
    or reorder the line. Apply after secret
    redaction. Any value is accepted (None is ""); callers put the result in
    a `rich.text.Text` (never markup), so `[...]` in the value is shown
    literally."""
    text = "" if value is None else str(value)
    return _UNSAFE_CONTROL.sub(_escape_control, text)


_STATUS_GLYPHS = {
    "ok": "✓",
    "warn": "!",
    "fail": "✗",
    "error": "✗",
    "skipped": "–",
}
_ASCII_GLYPHS = {"ok": "OK", "warn": "!", "fail": "X", "error": "X", "skipped": "-"}

ROW_CAP = 20
FINDINGS_CAP = 50


def _plain(value: Any) -> str:
    if isinstance(value, bool):
        return "yes" if value else "no"
    return "-" if value is None else str(value)


def _text(value: Any, style: str = "") -> Text:
    return Text(safe_terminal_text(_plain(value)), style=style)


def _style(prefix: str, value: Any) -> str:
    """The theme's `<prefix>.<value>` style name when it exists, else none."""
    name = f"{prefix}.{value}"
    return name if name in RUSH_THEME.styles else ""


def _glyph(c: Console, status: str) -> str:
    if c.encoding.lower().startswith("utf"):
        return _STATUS_GLYPHS.get(status, "•")
    return _ASCII_GLYPHS.get(status, "*")


def copyable_json_command(tool: str) -> str:
    """The `rush ... --json` command that prints the untruncated result: the
    real argv when it is this invocation's, else the Click command path.
    X3: argv values are secret-redacted before they are shown."""
    from rush.safety.redactor import sanitize_value

    ctx = click.get_current_context(silent=True)
    path = ctx.command_path.split()[1:] if ctx is not None else [tool]
    argv = sys.argv[1:]
    words = argv if path and all(part in argv for part in path) else path
    words = [str(word) for word in sanitize_value(list(words)).value]
    if "--json" not in words:
        words = [*words, "--json"]
    return shlex.join(["rush", *words])


def _truncation(c: Console, shown: int, total: int, noun: str, tool: str) -> None:
    c.print(
        _text(
            f"shown {shown}/{total} {noun}; full list: {copyable_json_command(tool)}",
            "dim",
        )
    )


# --- family projections -----------------------------------------------------

_SCALARS = (str, int, float, bool, type(None))
_COLLECTION_KEYS = (
    "projects",
    "items",
    "records",
    "rows",
    "runs",
    "artifacts",
    "agents",
    "sessions",
    "checkpoints",
    "entries",
    "results",
    "handoffs",
    "candidates",
)
_ROW_KEYS = (
    "project_id",
    "run_id",
    "handoff_id",
    "artifact_id",
    "agent_id",
    "session_id",
    "id",
    "name",
    "status",
    "state",
    "readiness.ready",
    "configured",
    "exists",
    "category",
    "kind",
    "root",
    "path",
)
# Keyed by tool, or by (tool, operation) where one tool has several lists.
_EMPTY_REASONS: dict[str | tuple[str, str], str] = {
    "project": "no projects are registered; register one with "
    "`rush project add PATH --allow-cache-write --allow-artifact-write`",
    ("project", "artifacts"): "no artifacts are recorded for this project "
    "(scan outputs, handoffs, memory)",
    "continuity": "no session checkpoints are saved",
    "agent_connection": "no agent hosts were found",
    "memory": "no memory records matched",
}


def _payload(result: Mapping[str, Any]) -> Any:
    """`raw.data` for an operation envelope, else `raw`."""
    raw = result.get("raw")
    if isinstance(raw, Mapping) and "operation" in raw and "data" in raw:
        return raw.get("data")
    return raw


def _reason(result: Mapping[str, Any]) -> str:
    raw = result.get("raw")
    error = raw.get("error") if isinstance(raw, Mapping) else None
    if isinstance(error, Mapping) and error.get("message"):
        return str(error["message"])
    return str(result.get("summary") or result.get("status"))


def _flatten(record: Mapping[str, Any]) -> dict[str, Any]:
    flat: dict[str, Any] = {}
    for key, value in record.items():
        if isinstance(value, Mapping):
            flat.update(
                {f"{key}.{k}": v for k, v in value.items() if isinstance(v, _SCALARS)}
            )
        elif isinstance(value, list | tuple):
            scalar_list = all(isinstance(v, _SCALARS) for v in value)
            flat[key] = (
                ", ".join(_plain(v) for v in value) or "none"
                if scalar_list and len(value) <= 10
                else f"{len(value)} item(s)"
            )
        else:
            flat[key] = value
    return flat


def _rows_of(payload: Any) -> list[Any] | None:
    if isinstance(payload, list):
        return payload
    if isinstance(payload, Mapping):
        for key in _COLLECTION_KEYS:
            if isinstance(payload.get(key), list):
                return list(payload[key])
    return None


def _row_line(row: Any) -> Text:
    if not isinstance(row, Mapping):
        return _text(f"  {_plain(row)}")
    flat = _flatten(row)
    keys = [k for k in _ROW_KEYS if k in flat][:6] or list(flat)[:4]
    return _text("  " + "  ".join(f"{k}: {_plain(flat[k])}" for k in keys))


def _metadata(result: Mapping[str, Any]) -> Mapping[str, Any]:
    """Legacy `metadata`, else strict V1 `extensions.metadata`."""
    metadata = result.get("metadata")
    if not isinstance(metadata, Mapping):
        extensions = result.get("extensions")
        metadata = (
            extensions.get("metadata") if isinstance(extensions, Mapping) else None
        )
    return metadata if isinstance(metadata, Mapping) else {}


def _count(scope: Mapping[str, Any], key: str) -> str:
    value = scope.get(key)
    if isinstance(value, int) and not isinstance(value, bool):
        return str(value)
    return f"unavailable: {scope.get('reason') or 'not reported'}"


def _analysis(result: Mapping[str, Any], c: Console) -> None:
    """Assessed scope, coverage and engines; the findings table follows."""
    metadata = _metadata(result)
    scope = metadata.get("scope")
    if isinstance(scope, Mapping):
        roots = scope.get("requested_targets") or scope.get("logical_root")
        if isinstance(roots, list):
            roots = ", ".join(_plain(r) for r in roots)
        c.print(_text(f"scope: {roots or 'unavailable: no requested roots reported'}"))
        if scope.get("kind") == "operation":
            c.print(_text(f"files: not applicable ({scope.get('reason')})"))
        else:
            c.print(
                _text(
                    f"files: matched {_count(scope, 'matched_file_count')}, "
                    f"consumed {_count(scope, 'consumed_file_count')}"
                )
            )
        coverage = scope.get("coverage") or "unavailable"
        reason = scope.get("reason") or (
            "not reported" if coverage == "unavailable" else None
        )
        c.print(_text(f"coverage: {coverage}" + (f" ({reason})" if reason else "")))
    else:
        c.print(_text("scope: unavailable: the producer reported no scope"))
    engines = [e for e in metadata.get("engines") or [] if isinstance(e, Mapping)]
    for entry in engines:
        reason = entry.get("reason")
        c.print(
            _text(
                f"engine {_plain(entry.get('engine'))}: {_plain(entry.get('status'))}"
                + (f" ({reason})" if reason else "")
            )
        )
    if not engines:
        c.print(_text("engines: unavailable: the producer reported no engine entries"))


def _collection(result: Mapping[str, Any], c: Console) -> None:
    if result.get("status") in ("error", "skipped"):
        return
    tool = str(result.get("tool"))
    payload = _payload(result)
    rows = _rows_of(payload) or []
    if not rows:
        raw = result.get("raw")
        operation = str(raw.get("operation")) if isinstance(raw, Mapping) else ""
        reason = _EMPTY_REASONS.get(
            (tool, operation),
            _EMPTY_REASONS.get(tool, "the producer returned no records"),
        )
        c.print(_text(f"0 records: {reason}"))
        return
    total = payload.get("total") if isinstance(payload, Mapping) else None
    if not isinstance(total, int) or isinstance(total, bool) or total < len(rows):
        total = len(rows)
    for row in rows[:ROW_CAP]:
        c.print(_row_line(row))
    shown = min(len(rows), ROW_CAP)
    if shown < total:
        _truncation(c, shown, total, "records", tool)
    else:
        c.print(_text(f"{shown}/{total} records", "dim"))


def _inspection(result: Mapping[str, Any], c: Console) -> None:
    payload = _payload(result)
    if isinstance(payload, list):
        _collection(result, c)
        return
    if not isinstance(payload, Mapping) or not payload:
        return
    items = list(_flatten(payload).items())
    for key, value in items[:ROW_CAP]:
        c.print(_text(f"  {key}: {_plain(value)}"))
    if len(items) > ROW_CAP:
        _truncation(c, ROW_CAP, len(items), "fields", str(result.get("tool")))


def _mutation(result: Mapping[str, Any], c: Console) -> None:
    """Changed IDs and paths plus the producer's readback -- success is never
    inferred from the status word alone."""
    if result.get("status") in ("error", "skipped", "fail"):
        c.print(_text(f"no change applied: {_reason(result)}"))
        return
    payload = _payload(result)
    payload = payload if isinstance(payload, Mapping) else {}
    changed, readback = payload.get("changed"), payload.get("readback")
    if payload.get("unchanged"):
        c.print(_text(f"unchanged: {_plain(payload['unchanged'])}"))
    elif isinstance(changed, Mapping) and changed:
        listed = ", ".join(f"{k}={_plain(v)}" for k, v in _flatten(changed).items())
        c.print(_text(f"changed: {listed}"))
    else:
        c.print(_text("changed: not reported by the producer"))
    if not isinstance(readback, Mapping) or not readback:
        c.print(
            _text("readback: unavailable (the producer returned no readback record)")
        )
        return
    items = list(_flatten(readback).items())
    for key, value in items[:ROW_CAP]:
        c.print(_text(f"  readback {key}: {_plain(value)}"))
    if len(items) > ROW_CAP:
        _truncation(c, ROW_CAP, len(items), "fields", str(result.get("tool")))


# --- 72-T07 memory projections ------------------------------------------------

_MEMORY_FAILED = ("error", "skipped", "fail")


def _memory_state_lines(result: Mapping[str, Any], c: Console) -> dict[str, Any]:
    """The classifier's state and action (not for `ok`) and the producer's
    `next_action` command, every value as literal text."""
    from .tools.memory import memory_ui_state

    ui = memory_ui_state(result)
    if ui["state"] != "ok":
        c.print(_text(f"state: {ui['state']}: {ui['reason']}"))
        c.print(_text(f"action: {ui['action']}"))
    guidance = ui["next_action"]
    if isinstance(guidance, Mapping) and guidance.get("command") is not None:
        c.print(_text(f"command: {_plain(guidance['command'])}"))
    return ui


def _memory_raw(result: Mapping[str, Any]) -> Mapping[str, Any]:
    raw = result.get("raw")
    return raw if isinstance(raw, Mapping) else {}


def _memory_field(item: Mapping[str, Any], *keys: str) -> Any:
    """The first non-null of `keys` in the item's `reference`, then the item."""
    ref = item.get("reference")
    for source in (ref if isinstance(ref, Mapping) else {}, item):
        for key in keys:
            if source.get(key) is not None:
                return source[key]
    return None


def _memory_identity(item: Mapping[str, Any]) -> tuple[Any, Any]:
    return (
        _memory_field(item, "artifact_id", "id"),
        _memory_field(item, "artifact_version", "version"),
    )


def _memory_owner(item: Mapping[str, Any]) -> str:
    owner = _memory_field(item, "owner_scope", "owner")
    if isinstance(owner, Mapping):
        return f"{_plain(owner.get('kind'))}:{_plain(owner.get('id'))}"
    return _plain(owner)


def _memory_freshness(item: Mapping[str, Any]) -> str:
    freshness = _memory_field(item, "freshness")
    if freshness is None and item.get("stale") is not None:
        return "stale" if item.get("stale") is True else "current"
    return _plain(freshness)


def _memory_decode(value: str) -> str:
    try:
        return base64.b64decode(value).decode("utf-8", errors="backslashreplace")
    except ValueError:
        return value


def memory_hostile_text(body: str) -> str | None:
    """The decoded `text` of a JSON-object payload when it holds characters the
    terminal projection escapes. The payload spells them JSON-escaped (`\\u001b`),
    so the exact bytes never show what the record says; this is that text, escaped
    for display by the caller's `_text`/`_safe`."""
    try:
        decoded = json.loads(body)
    except ValueError:
        return None
    text = decoded.get("text") if isinstance(decoded, dict) else None
    if isinstance(text, str) and safe_terminal_text(text) != text:
        return text
    return None


def _memory_excerpt(item: Mapping[str, Any]) -> str | None:
    content = item.get("content")
    if isinstance(item.get("excerpt"), str):
        return str(item["excerpt"])
    if isinstance(content, Mapping) and isinstance(content.get("text"), str):
        return str(content["text"])
    if isinstance(item.get("content_utf8"), str):
        return str(item["content_utf8"])
    if isinstance(item.get("content_base64"), str):
        return _memory_decode(str(item["content_base64"]))
    if content is not None:
        return json.dumps(content, ensure_ascii=False, sort_keys=True)[:200]
    return None


def _memory_items(result: Mapping[str, Any], key: str = "items") -> list[Any]:
    raw = _memory_raw(result)
    if isinstance(raw.get(key), list) and raw[key]:
        return list(raw[key])
    return _rows_of(_payload(result)) or []


def _memory_hint(label: str, leaf: str, body: Mapping[str, Any]) -> Text:
    return _text(
        f"{label}: rush memory {leaf} --input FILE  "
        f"(FILE: {json.dumps(body, sort_keys=True)})"
    )


def _memory_count(c: Console, result: Mapping[str, Any], rows: list[Any]) -> None:
    raw = _memory_raw(result)
    payload = _payload(result)
    total = raw.get("total")
    if total is None and isinstance(payload, Mapping):
        total = payload.get("total")
    if not isinstance(total, int) or isinstance(total, bool) or total < len(rows):
        total = len(rows)
    shown = min(len(rows), ROW_CAP)
    if shown < total:
        _truncation(c, shown, total, "records", str(result.get("tool")))
    else:
        c.print(_text(f"{shown}/{total} records", "dim"))


def _memory_none(result: Mapping[str, Any], c: Console) -> None:
    reason = _EMPTY_REASONS.get(
        ("memory", str(_memory_raw(result).get("operation"))),
        _EMPTY_REASONS.get("memory", "the producer returned no records"),
    )
    c.print(_text(f"0 records: {reason}"))


def _memory_collection(result: Mapping[str, Any], c: Console) -> None:
    """ask/list/recall/related: one line per record with its exact reference, its
    badges, a citation and an excerpt, then the next steps for the first row."""
    ui = _memory_state_lines(result, c)
    if result.get("status") in _MEMORY_FAILED:
        return
    rows = _memory_items(result)
    if not rows:
        _memory_none(result, c)
        return
    badges = {
        (row["artifact_id"], row["artifact_version"]): row["badges"]
        for row in ui["rows"]
    }
    for row in rows[:ROW_CAP]:
        if not isinstance(row, Mapping):
            c.print(_row_line(row))
            continue
        ident, version = _memory_identity(row)
        line = (
            f"  {_plain(ident)}@v{_plain(version)}"
            f"  subject {_plain(_memory_field(row, 'subject'))}"
            f"  owner {_memory_owner(row)}"
            f"  source {_plain(_memory_field(row, 'source'))}"
            f"  trust {_plain(_memory_field(row, 'trust_tier', 'trust'))}"
            f"  freshness {_memory_freshness(row)}"
        )
        retrieval = _memory_field(row, "retrieval")
        if retrieval is not None:
            line += f"  retrieval {_plain(retrieval)}"
        c.print(_text(line))
        marks = badges.get((ident, version))
        if marks:
            c.print(_text(f"    badges: {', '.join(marks)}"))
        digest = _memory_field(row, "payload_hash") or "unknown"
        # A citation is copied whole: it never folds at the console width.
        c.print(
            _text(f"    cite {_plain(ident)}@v{_plain(version)} sha256:{digest}"),
            soft_wrap=True,
        )
        excerpt = _memory_excerpt(row)
        if excerpt is not None:
            c.print(_text(f"    {excerpt}"))
    _memory_count(c, result, rows)
    raw = _memory_raw(result)
    if raw.get("next_cursor"):
        c.print(_text(f"next page: rerun with --cursor {_plain(raw['next_cursor'])}"))
    first = rows[0]
    if not isinstance(first, Mapping):
        return
    ident, version = _memory_identity(first)
    owner = _memory_field(first, "owner_scope")
    exact = {"schema_version": 2, "artifact_id": ident, "artifact_version": version}
    c.print(_memory_hint("inspect", "expand", {**exact, "representation": "utf8"}))
    c.print(_text(f"history: rush memory history {_plain(ident)}"))
    c.print(_memory_hint("related", "related", exact))
    c.print(_text(f"explain: rush memory explain {_plain(ident)}"))
    correction = {
        "schema_version": 2,
        "subject": _memory_field(first, "subject"),
        "artifact_id": ident,
        "expected_version": version,
        "owner_scope": dict(owner) if isinstance(owner, Mapping) else owner,
        "correction": {
            "kind": "correct",
            "reason": "REASON",
            "supersedes": [{"artifact_id": ident, "artifact_version": version}],
        },
        "apply": False,
    }
    c.print(_memory_hint("correct", "edit", correction))


def _memory_inspection(result: Mapping[str, Any], c: Console) -> None:
    """expand (and the other single-record reads): the exact byte page with its
    reference, or the generic field listing when no page is present."""
    ui = _memory_state_lines(result, c)
    if operation_key(result) == "bootstrap":
        payload = _payload(result)
        if not isinstance(payload, Mapping):
            return
        fields = ["intent", "progress_state", "next_action"]
        if _memory_raw(result).get("code") == "OK":
            fields.extend(("checkpoint", "task", "unresolved"))
        for key in fields:
            if payload.get(key) is not None:
                c.print(
                    _text(f"  {key}: {json.dumps(payload[key], ensure_ascii=False)}")
                )
        return
    items = _memory_raw(result).get("items")
    page: Mapping[str, Any] | None = None
    for candidate in (
        items[0] if isinstance(items, list) and items else None,
        _payload(result),
    ):
        if isinstance(candidate, Mapping) and (
            "content_utf8" in candidate or "content_base64" in candidate
        ):
            page = candidate
            break
    if page is None:
        _inspection(result, c)
        return
    utf8 = isinstance(page.get("content_utf8"), str)
    body = (
        str(page["content_utf8"])
        if utf8
        else _memory_decode(str(page.get("content_base64") or ""))
    )
    ident, version = _memory_identity(page)
    offset = page.get("offset") or 0
    next_offset = page.get("next_offset")
    end: Any = "?"
    if isinstance(next_offset, int) and not isinstance(next_offset, bool):
        end = next_offset
    elif isinstance(offset, int) and not isinstance(offset, bool):
        end = offset + len(body.encode("utf-8"))
    representation = page.get("representation") or ("utf8" if utf8 else "base64")
    c.print(
        _text(
            f"  {_plain(ident)}@v{_plain(version)}"
            f"  bytes {_plain(offset)}..{_plain(end)}"
            f" of {_plain(page.get('total_bytes') or '?')}"
            f"  representation {_plain(representation)}"
            f"  integrity {_plain(_memory_field(page, 'integrity') or '?')}"
            f"  sha256:{_plain(_memory_field(page, 'payload_hash') or 'unknown')}"
        )
    )
    if ui["state"] == "digest_mismatch":
        return
    for segment in body.split("\n"):
        c.print(_text(segment))
    hostile = memory_hostile_text(body)
    if hostile is not None:
        c.print(_text(f"  text: {hostile}"))
    if next_offset is not None:
        follow = {
            "schema_version": 2,
            "artifact_id": ident,
            "artifact_version": version,
            "offset": next_offset,
            "representation": representation,
        }
        c.print(_memory_hint("next page", "expand", follow))


def _memory_history(result: Mapping[str, Any], c: Console) -> None:
    """history: every version oldest first with that version's own labels."""
    _memory_state_lines(result, c)
    if result.get("status") in _MEMORY_FAILED:
        return
    versions = _memory_items(result, "versions") or _memory_items(result)
    if not versions:
        _memory_none(result, c)
        return
    for version in versions[:ROW_CAP]:
        if not isinstance(version, Mapping):
            c.print(_row_line(version))
            continue
        ident, number = _memory_identity(version)
        reason_codes = version.get("reason_codes")
        codes = (
            ",".join(_plain(code) for code in reason_codes)
            if isinstance(reason_codes, list | tuple)
            else ""
        )
        freshness = version.get("freshness") or _memory_freshness(version)
        integrity = version.get("integrity") or _memory_field(version, "integrity")
        c.print(
            _text(
                f"  {_plain(ident)}@v{_plain(number)}"
                f"  trust {_plain(_memory_field(version, 'trust_tier', 'trust'))}"
                f"  freshness {_plain(freshness)}"
                f"  integrity {_plain(integrity)}" + (f"  {codes}" if codes else "")
            )
        )
        excerpt = _memory_excerpt(version)
        if excerpt is not None:
            c.print(_text(f"    {excerpt}"))
            hostile = memory_hostile_text(excerpt)
            if hostile is not None:
                c.print(_text(f"    text: {hostile}"))
    shown = min(len(versions), ROW_CAP)
    if shown < len(versions):
        _truncation(c, shown, len(versions), "versions", str(result.get("tool")))
    else:
        c.print(_text(f"{shown}/{len(versions)} versions", "dim"))


_EXPLAIN_BUCKETS = (
    ("why (supporting)", "supporting"),
    ("contrary", "contrary"),
    ("what tried (attempted)", "attempted"),
    ("affected code refs", "affected"),
)


def _memory_explain(result: Mapping[str, Any], c: Console) -> None:
    """explain: the cited why / contrary / what-tried / affected buckets and the
    unknowns; an absent rationale is `unknown`, never invented text."""
    _memory_state_lines(result, c)
    if result.get("status") in _MEMORY_FAILED:
        return
    raw = _memory_raw(result)
    stale: list[str] = []
    supporting = raw.get("supporting")
    if not (isinstance(supporting, list) and supporting):
        c.print(_text("  why: unknown (no recorded rationale)"))
    for heading, key in _EXPLAIN_BUCKETS:
        c.print(_text(f"  {heading}:"))
        bucket = raw.get(key)
        entries = bucket if isinstance(bucket, list) else []
        if not entries:
            c.print(_text("    none recorded"))
        for entry in entries:
            if not isinstance(entry, Mapping):
                c.print(_text(f"    {_plain(entry)}"))
                continue
            ident, version = _memory_identity(entry)
            freshness = _memory_freshness(entry)
            line = (
                f"    {_plain(ident)}@v{_plain(version)}"
                f"  source {_plain(_memory_field(entry, 'source'))}"
                f"  freshness {freshness}"
            )
            symbol = _memory_field(entry, "symbol_ref")
            if key == "affected" and symbol is not None:
                line += f"  symbol {_plain(symbol)}"
            c.print(_text(line))
            cited = f"{_plain(ident)}@v{_plain(version)}"
            if freshness in ("stale", "unknown") and cited not in stale:
                stale.append(cited)
    c.print(_text("  unknowns:"))
    listed = raw.get("unknowns")
    unknowns = listed if isinstance(listed, list) else []
    if not unknowns:
        c.print(_text("    none recorded"))
    for unknown in unknowns:
        c.print(_text(f"    {_plain(unknown)}"))
    c.print(_text(f"  stale: {', '.join(stale) if stale else 'none'}"))


def _memory_mutation(result: Mapping[str, Any], c: Console) -> None:
    """A memory mutation: the producer's changed/readback lines, the state when
    not ok, then each committed exact version and where to see its history."""
    _mutation(result, c)
    _memory_state_lines(result, c)
    if result.get("status") in _MEMORY_FAILED:
        return
    raw = _memory_raw(result)
    payload = _payload(result)
    committed: list[tuple[Any, Any]] = []
    for key in ("result_refs", "items"):
        refs = raw.get(key)
        if isinstance(refs, list) and refs:
            committed = [_memory_identity(r) for r in refs if isinstance(r, Mapping)]
            break
    if (
        not committed
        and isinstance(payload, Mapping)
        and payload.get("revision") is not None
    ):
        committed = [(_memory_field(payload, "artifact_id", "id"), payload["revision"])]
    for ident, version in committed:
        if ident is None:
            continue
        c.print(_text(f"committed: {_plain(ident)}@v{_plain(version)}"))
        c.print(_text(f"next: rush memory history {_plain(ident)}"))


Projector = Callable[[Mapping[str, Any], Console], None]

_PROJECTORS: dict[str, Projector] = {
    "analysis": _analysis,
    "collection": _collection,
    "inspection": _inspection,
    "mutation": _mutation,
    "memory_collection": _memory_collection,
    "memory_inspection": _memory_inspection,
    "memory_history": _memory_history,
    "memory_explain": _memory_explain,
    "memory_mutation": _memory_mutation,
    "service": _inspection,
    "status": _inspection,
}

_WORKFLOW_FAMILIES = {
    "continuity": "inspection",
    "memory": "inspection",
    "commit-msg": "analysis",
    "ci": "analysis",
    "release": "analysis",
    "tdd": "analysis",
    "doctor": "service",
    "status": "status",
    "patch-apply": "mutation",
    "tui-diff": "analysis",
    "provenance-ai": "analysis",
    "pr-synthesize": "analysis",
    "check": "analysis",
}

_OPERATION_FAMILIES: dict[str, dict[str | None, str]] = {
    "project": {
        None: "inspection",
        "list": "collection",
        "show": "inspection",
        "snapshot": "inspection",
        "artifacts": "collection",
        "add": "mutation",
        "select": "mutation",
        "configure": "mutation",
        "create": "mutation",
        "relink": "mutation",
    },
    "scan": {
        None: "inspection",
        "plan": "inspection",
        "run": "mutation",
        "status": "inspection",
        "rescan": "mutation",
    },
    "scan-handoff": {
        None: "inspection",
        "prepare": "mutation",
        "dispatch": "mutation",
        "status": "inspection",
        "acknowledge": "mutation",
        "complete": "mutation",
    },
    "scan-rescan": {None: "mutation"},
    "scan-cancel": {None: "mutation"},
    "scan-resume": {None: "mutation"},
    "agent_connection": {
        None: "service",
        "list": "collection",
        "connect": "mutation",
        "disconnect": "mutation",
        "doctor": "service",
    },
    "memory": {
        "overview": "collection",
        "ask": "memory_collection",
        "list": "memory_collection",
        "recall": "memory_collection",
        "related": "memory_collection",
        "write": "memory_mutation",
        "promote": "memory_mutation",
        "maintain": "memory_mutation",
        "link": "memory_mutation",
        "consolidate": "memory_mutation",
        "handoff": "memory_mutation",
        "receive": "memory_mutation",
        "delete": "memory_mutation",
        "edit": "memory_mutation",
        "archive": "memory_mutation",
        "verify_attempt": "memory_mutation",
        "expand": "memory_inspection",
        "prepare": "memory_inspection",
        "resume": "memory_inspection",
        "intent": "memory_inspection",
        "recipe": "memory_inspection",
        "plan_checks": "memory_inspection",
        "last_success_diagnose": "memory_inspection",
        "preference": "memory_inspection",
        "capsule": "memory_inspection",
        "bootstrap": "memory_inspection",
        "history": "memory_history",
        "explain": "memory_explain",
    },
    "continuity": {
        "list": "collection",
        "save": "mutation",
        "restore": "inspection",
        "resume": "inspection",
        "provider_resume": "inspection",
        "pack": "inspection",
        "context_pack": "inspection",
        "retrieve": "inspection",
        "context_retrieve": "inspection",
        "coordination_check": "inspection",
        "coordination_merge_preview": "inspection",
        "coordination_recovery": "inspection",
    },
    "status": {"status": "status", "result": "status"},
    "audit": {None: "analysis"},
    "gate": {None: "analysis"},
    "plugin": {None: "analysis"},
    "workspace": {None: "inspection"},
    "install": {None: "service"},
}


def _build_families() -> dict[tuple[str, str | None], str]:
    families: dict[tuple[str, str | None], str] = {}
    for name, spec in TOOL_SPECS.items():
        # A new workflow tool without a family fails at import, never
        # silently renders as something it is not.
        families[(name, None)] = (
            _WORKFLOW_FAMILIES[name] if spec.category == "workflow" else "analysis"
        )
    for tool, operations in _OPERATION_FAMILIES.items():
        families.update({(tool, op): family for op, family in operations.items()})
    return families


FAMILIES = _build_families()
FAMILY_PROJECTIONS: dict[tuple[str, str | None], Projector] = {
    key: _PROJECTORS[family] for key, family in FAMILIES.items()
}


def operation_key(result: Mapping[str, Any]) -> str | None:
    """`raw.operation` for an envelope result, else the invoking Click
    subcommand (the operation a flat CLI result was produced for)."""
    raw = result.get("raw")
    if isinstance(raw, Mapping) and isinstance(raw.get("operation"), str):
        return str(raw["operation"])
    ctx = click.get_current_context(silent=True)
    if ctx is None or not ctx.info_name:
        return None
    return ctx.info_name.replace("-", "_")


def family_for(tool: str, operation: str | None) -> str | None:
    return FAMILIES.get((tool, operation)) or FAMILIES.get((tool, None))


def _projection(tool: str, operation: str | None) -> Projector:
    return (
        FAMILY_PROJECTIONS.get((tool, operation))
        or FAMILY_PROJECTIONS.get((tool, None))
        or _inspection
    )


def _render_findings(c: Console, tool: str, findings: list[Any]) -> None:
    t = Table(show_header=True, header_style="bold")
    t.add_column("path", style="dim")
    t.add_column("line", justify="right")
    t.add_column("rule")
    t.add_column("severity")
    t.add_column("message")
    has_any_fix = any(bool(f.get("fix")) for f in findings)
    if has_any_fix:
        t.add_column("fix", style="italic dim")

    for f in findings[:FINDINGS_CAP]:
        sev = f.get("severity", "info")
        fix_val = f.get("fix")
        fix_str = str(fix_val)[:40] if fix_val else ""
        t.add_row(
            _text(f.get("path", "")),
            _text(f.get("line", "")),
            _text(f.get("rule", "")),
            _text(sev, _style("severity", sev)),
            _text(str(f.get("message", ""))[:120]),
            *([_text(fix_str)] if has_any_fix else []),
        )
    c.print(t)
    if len(findings) > FINDINGS_CAP:
        _truncation(c, FINDINGS_CAP, len(findings), "findings", tool)
    else:
        c.print(_text(f"{len(findings)}/{len(findings)} findings", "dim"))


def render_result(result: dict) -> None:
    """Human-facing rich render of a ToolResult. CLI-only (requirement C4 — MCP returns raw JSON)."""
    tool = str(result.get("tool", "?"))
    status = str(result.get("status", "?"))
    findings = result.get("findings", []) or []

    c = console()
    # T9/S9.8: the glyph is derived from status (never a success mark for
    # skipped work) and the status word is printed. T27/X3: every engine- or
    # user-supplied string is literal, control-free text.
    c.print(
        Text.assemble(
            _glyph(c, status),
            " ",
            _text(tool),
            " ",
            _text(status, _style("status", status)),
            " ",
            _text(result.get("summary", "")),
        )
    )
    _projection(tool, operation_key(result))(result, c)
    if findings:
        _render_findings(c, tool, findings)


def render_dashboard(results: list[dict[str, Any]]) -> None:
    """Render a comprehensive interactive multi-tool execution dashboard."""
    c = console()
    bolt = "⚡ " if c.encoding.lower().startswith("utf") else ""
    t = Table(
        title=f"{bolt}Rush Quality & Verification Dashboard",
        show_header=True,
        header_style="bold",
    )
    t.add_column("Tool", style="bold")
    t.add_column("Engine", style="dim")
    t.add_column("Status", justify="center")
    t.add_column("Duration", justify="right")
    t.add_column("Findings", justify="right")
    t.add_column("Summary")

    total_findings = 0
    total_duration = 0

    for r in results:
        status = str(r.get("status", "ok"))
        duration = r.get("duration_ms", 0)
        findings = r.get("findings", []) or []

        total_findings += len(findings)
        total_duration += duration

        t.add_row(
            _text(r.get("tool", "?")),
            _text(r.get("engine") or "-"),
            _text(status.upper(), _style("status", status)),
            _text(f"{duration}ms"),
            _text(len(findings)),
            _text(str(r.get("summary", ""))[:80]),
        )

    c.print(Panel(t, border_style=CYAN))
    c.print(
        _text(
            f"Total tools executed: {len(results)} | Total duration: {total_duration}ms "
            f"| Total findings: {total_findings}",
            "dim",
        )
    )
