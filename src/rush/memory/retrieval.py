"""MC02 §9.0 bounded recall and exact expansion.

`recall_page()` pages `TypedArtifactStore.search_candidates()` into a token/byte-bounded
result within a 512-candidate scan cap, returning an HMAC-signed continuation cursor when the
cap is hit before the page fills. `expand_artifact()` returns exact byte slices of one stored
artifact version, base64-encoded so a caller can page across a multi-byte-character boundary
and still reconstruct the original bytes exactly on concatenation.

Both functions return a plain dict with a leading `"code"` key (`"OK"` or one of the §9.0
warn/fail codes); `rush.tools.memory.MemoryTool` maps that code onto `ToolResult.status` and
wraps the rest as the operation envelope's `data`. Neither function raises for a denied,
missing, or stale-cursor request — only for a genuine programming error.

`defended_recall()` (MC04) is the one shared defended-lookup path for cache/citation
consumers that used to run their own `store.search()`-then-`store.recall()` pair: it issues a
single `store.search_candidates()` query (MC02's already-bounded/ranked path, never a second
raw FTS query) and applies `store.recall()`'s exact signature/Trojan-source/staleness checks,
routed through a caller-supplied `SourceValidationMemo` so N candidate rows that share one
backing source file are hashed/API-diffed once per request, not once per row.
"""

from __future__ import annotations

import base64
import dataclasses
import hashlib
import hmac
import json
import math
from collections.abc import Callable, Iterable, Sequence
from pathlib import Path
from typing import Any

import tiktoken

from rush.memory.embeddings import (
    EmbeddingConfig,
    EmbeddingEngineUnavailable,
    EmbeddingResponseError,
    embed_chunks,
)
from rush.memory.merkle_invalidator import MerkleInvalidator
from rush.memory.store import (
    MemoryArtifact,
    MemorySubject,
    SignatureMismatchError,
    TrojanSourceFoundError,
    TypedArtifactStore,
    _inspect_text_for_trojan_chars,
    _row_to_artifact,
    compute_content_signature,
)
from rush.token_economy.telemetry import TelemetryStore

_SCAN_CAP = 512
_BATCH_SIZE = 64
_RANKING_VERSION = "mc02-v1"

# MC12 §6.7: reciprocal-rank-fusion constant and vector-candidate scan cap (documented
# ceiling, matches the lexical `_SCAN_CAP`).
_RRF_K = 60
_VECTOR_SCAN_CAP = 512

DEFAULT_LIMIT = 8
DEFAULT_MAX_TOKENS = 2048
DEFAULT_MAX_BYTES = 8192
DEFAULT_ENCODING = "cl100k_base"

_EXCERPT_CHARS = 200


@dataclasses.dataclass
class SourceValidationMemo:
    """MC04 request-local canonical-path memo: caches a source file's current content hash
    and API-diff freshness result so `defended_recall()` computes each exactly once per
    request, however many returned candidates share that same backing file. Discard after
    the request that created it — never persisted, never shared across requests."""

    _hash_cache: dict[Path, str | None] = dataclasses.field(default_factory=dict)
    _api_diff_cache: dict[tuple[Path, str], Any] = dataclasses.field(
        default_factory=dict
    )

    def source_hash(self, merkle: MerkleInvalidator, file_path: Path) -> str | None:
        if file_path not in self._hash_cache:
            try:
                self._hash_cache[file_path] = merkle.hash_content(
                    file_path.read_text(encoding="utf-8")
                )
            except (OSError, UnicodeError):
                self._hash_cache[file_path] = None
        return self._hash_cache[file_path]

    def api_diff(self, project_root: Path, file_path: Path, symbol: str) -> Any:
        key = (file_path, symbol)
        if key not in self._api_diff_cache:
            # Deferred import mirrors `TypedArtifactStore.recall()`'s own local import of
            # `ApiDiffer` (avoids a module-load-time cycle between `rush.memory` and
            # `rush.tools`).
            from rush.tools.api_diff import ApiDiffer

            self._api_diff_cache[key] = ApiDiffer(
                project_root=project_root
            ).diff_symbol(file_path, symbol)
        return self._api_diff_cache[key]


def defended_recall(
    store: TypedArtifactStore,
    subject: MemorySubject,
    query: str,
    session_allowlist: Iterable[str] | None,
    *,
    memo: SourceValidationMemo | None = None,
) -> list[MemoryArtifact]:
    """MC04 one-query defended lookup: `store.search_candidates()` (MC02's own bounded/ranked
    query — never a second raw FTS query) validated with `store.recall()`'s exact
    signature/Trojan-source/staleness checks, deduplicating source-file hashing and API-diff
    calls across candidates via `memo` (fresh per call when the caller passes none).

    `query` is the raw (unquoted) search text — `search_candidates()` quotes it as an FTS5
    literal phrase itself; callers must not pre-quote it (unlike the legacy `store.search()`).
    Raises `SignatureMismatchError`/`TrojanSourceFoundError` exactly as `store.recall()` does;
    callers that treat a defended read as fail-closed should keep wrapping this in
    `contextlib.suppress(Exception)`, same as before.
    """
    allowed_sources = set(session_allowlist) if session_allowlist else set()
    if not allowed_sources:
        return []
    memo = memo or SourceValidationMemo()
    merkle = MerkleInvalidator(project_root=store.project_root)
    rows = store.search_candidates(
        subject,
        query,
        source_allowlist=sorted(allowed_sources),
        scan_limit=_SCAN_CAP,
    )
    verified: list[MemoryArtifact] = []
    for row in rows:
        artifact = _row_to_artifact(row)
        if artifact.source not in allowed_sources:
            continue
        if artifact.trust_tier == "STATED" and (
            artifact.signature is None
            or compute_content_signature(artifact.content) != artifact.signature
        ):
            raise SignatureMismatchError(
                f"signature mismatch for STATED artifact {artifact.id}"
            )

        findings = _inspect_text_for_trojan_chars(
            json.dumps(artifact.content, ensure_ascii=False)
        )
        if findings:
            raise TrojanSourceFoundError(
                f"Trojan Source characters detected in artifact {artifact.id}: {findings}"
            )

        if artifact.symbol_ref is not None and artifact.content_hash is not None:
            path_part = artifact.symbol_ref.split("::", 1)[0]
            file_path = (store.project_root / path_part).resolve()
            current_hash = memo.source_hash(merkle, file_path)
            if current_hash != artifact.content_hash:
                artifact = dataclasses.replace(artifact, stale=True)

        # API-diff staleness (§6.5 Invariant 5), mirrors `store.recall()`: evaluated
        # unconditionally, never gated by the merkle check above; only ever sets
        # stale=True, never resets it.
        if artifact.symbol_ref is not None:
            path_part, sep, symbol_part = artifact.symbol_ref.partition("::")
            if sep and symbol_part:
                file_path = (store.project_root / path_part).resolve()
                if file_path.is_file():
                    diff_result = memo.api_diff(
                        store.project_root, file_path, symbol_part
                    )
                    if isinstance(diff_result, dict):
                        artifact = dataclasses.replace(artifact, stale=True)

        verified.append(artifact)
    return verified


def _record_memory_event(
    telemetry: TelemetryStore | None,
    kind: str,
    tokens: int,
    *,
    request_id: str | None,
    event_id: str | None,
    opt_in: bool,
    cache_write: bool,
) -> None:
    """No-op unless a caller opts into real cost accounting by passing `telemetry` plus both
    IDs — existing `recall_page()`/`expand_artifact()` callers that pass none of this see zero
    behavior change."""
    if telemetry is None or not request_id or not event_id:
        return
    telemetry.record_memory_event(
        kind,
        tokens,
        request_id=request_id,
        event_id=event_id,
        opt_in=opt_in,
        cache_write=cache_write,
    )


def _encoder(encoding: str) -> tiktoken.Encoding:
    return tiktoken.get_encoding(encoding)


def _count_tokens(text: str, encoding: str) -> int:
    return len(_encoder(encoding).encode(text))


def _encode_cursor(key: bytes, payload: dict[str, Any]) -> str:
    body = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    body_b64 = base64.urlsafe_b64encode(body).rstrip(b"=").decode("ascii")
    signature = hmac.new(key, body, hashlib.sha256).hexdigest()
    return f"{body_b64}.{signature}"


def _decode_cursor(key: bytes, cursor: str) -> dict[str, Any] | None:
    """Returns `None` for anything untrustworthy: wrong shape, bad signature, or a payload
    that isn't the JSON object `_encode_cursor()` produces. Callers treat `None` as
    restart-required, never as an empty-but-valid cursor."""
    try:
        body_b64, signature = cursor.split(".", 1)
        padding = "=" * (-len(body_b64) % 4)
        body = base64.urlsafe_b64decode(body_b64 + padding)
        expected = hmac.new(key, body, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(signature, expected):
            return None
        payload = json.loads(body)
    except (ValueError, TypeError):
        return None
    return payload if isinstance(payload, dict) else None


def _excerpt(content: dict[str, Any]) -> str:
    text = content.get("text")
    if not isinstance(text, str):
        text = json.dumps(content, ensure_ascii=False, sort_keys=True)
    return text[:_EXCERPT_CHARS]


def _candidate_to_item(row: Any) -> dict[str, Any] | None:
    """`None` marks a corrupt candidate (malformed/non-object `content`) to skip — never
    raises, so one bad row can't abort the whole page (MC02.1 "corrupt candidates do not
    starve page")."""
    try:
        content = json.loads(row["content"])
    except (TypeError, ValueError):
        return None
    if not isinstance(content, dict):
        return None
    return {
        "id": row["id"],
        "version": row["artifact_version"],
        "excerpt": _excerpt(content),
        "source": row["source"],
        "trust": row["trust_tier"],
        "freshness": "stale" if row["stale"] else "fresh",
        # MC03 (relations.py) isn't implemented yet; every item reports no known relations
        # rather than fabricating any.
        "relations": [],
    }


def _measure_page(
    items: list[dict[str, Any]], next_cursor: str | None, complete: bool, encoding: str
) -> tuple[int, int]:
    """Byte/token size of the serialized `data` payload a page will actually return — the
    §9.0 "budgets include the serialized returned memory payload, metadata and cursor"
    envelope, not the outer MCP/JSON-RPC transport framing (counted separately, per §9.0)."""
    payload = {
        "items": items,
        "next_cursor": next_cursor,
        "complete": complete,
        "encoding": encoding,
    }
    text = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    return len(text.encode("utf-8")), _count_tokens(text, encoding)


def _page(
    code: str,
    *,
    items: list[dict[str, Any]] | None = None,
    next_cursor: str | None = None,
    complete: bool = False,
    encoding: str = DEFAULT_ENCODING,
    tokens: int = 0,
    bytes_: int = 0,
) -> dict[str, Any]:
    return {
        "code": code,
        "items": items or [],
        "next_cursor": next_cursor,
        "complete": complete,
        "tokens": tokens,
        "bytes": bytes_,
        "encoding": encoding,
    }


def recall_page(
    store: TypedArtifactStore,
    *,
    subject: MemorySubject,
    query: str,
    session_allowlist: Iterable[str] | None,
    limit: int = DEFAULT_LIMIT,
    max_tokens: int = DEFAULT_MAX_TOKENS,
    max_bytes: int = DEFAULT_MAX_BYTES,
    encoding: str = DEFAULT_ENCODING,
    cursor: str | None = None,
    telemetry: TelemetryStore | None = None,
    request_id: str | None = None,
    event_id: str | None = None,
    opt_in: bool = False,
    cache_write: bool = False,
) -> dict[str, Any]:
    """MC02 §9.0 bounded recall: pages `store.search_candidates()` (already filtered by
    subject/source/trust/expiry) into a token/byte-bounded result.

    MC04: passing `telemetry` plus `request_id`/`event_id` records this page's real token
    cost as a `"retrieval"` event (deduplicated by those IDs), gated on `opt_in`/`cache_write`
    exactly like `TelemetryStore.record_memory_event()`. Omitting `telemetry` (the default)
    persists nothing — existing callers see no behavior change.

    Scans up to `_SCAN_CAP` (512) candidates for *this call*; if the cap is hit before the
    page is full, returns `complete=False` and a `next_cursor` bound to `(subject, query,
    session_allowlist, store generation, ranking version)` — any change to that binding
    between calls fails the continuation closed with `"E_RESTART"` rather than silently
    paging over stale or rescoped data. An empty `session_allowlist` fails closed (an empty,
    `complete=True` page), matching `TypedArtifactStore.recall()`'s existing precedent.
    """
    allowed_sources = sorted(set(session_allowlist or ()))
    if not allowed_sources:
        return _page("OK", complete=True, encoding=encoding)

    key = store.cursor_key()
    namespace = str(store.project_root)

    if cursor is None:
        scan_offset = 0
        generation = store.current_generation()
    else:
        decoded = _decode_cursor(key, cursor)
        if decoded is None:
            return _page("E_RESTART", encoding=encoding)
        expected_binding = (
            subject,
            query,
            allowed_sources,
            namespace,
            _RANKING_VERSION,
        )
        actual_binding = (
            decoded.get("subject"),
            decoded.get("query"),
            decoded.get("sources"),
            decoded.get("namespace"),
            decoded.get("ranking_version"),
        )
        if expected_binding != actual_binding:
            return _page("E_RESTART", encoding=encoding)
        generation = int(decoded.get("generation", -1))
        if generation != store.current_generation():
            return _page("E_RESTART", encoding=encoding)
        scan_offset = int(decoded.get("scan_offset", 0))

    floor_bytes, floor_tokens = _measure_page([], None, True, encoding)
    if floor_bytes > max_bytes or floor_tokens > max_tokens:
        return _page("E_BUDGET", encoding=encoding)

    items: list[dict[str, Any]] = []
    scanned = 0
    hit_cap = False
    exhausted = False
    budget_full = False

    while scanned < _SCAN_CAP and len(items) < limit and not budget_full:
        batch_limit = min(_BATCH_SIZE, _SCAN_CAP - scanned)
        batch = store.search_candidates(
            subject,
            query,
            source_allowlist=allowed_sources,
            scan_offset=scan_offset,
            scan_limit=batch_limit,
        )
        if not batch:
            exhausted = True
            break
        for row in batch:
            scanned += 1
            item = _candidate_to_item(row)
            if item is None:
                continue
            trial_bytes, trial_tokens = _measure_page(
                [*items, item], None, True, encoding
            )
            if trial_bytes > max_bytes or trial_tokens > max_tokens:
                budget_full = True
                break
            items.append(item)
            if len(items) >= limit:
                break
        scan_offset += len(batch)
        if len(batch) < batch_limit:
            exhausted = True
        if scanned >= _SCAN_CAP:
            hit_cap = True
        if budget_full or len(items) >= limit or exhausted or hit_cap:
            break

    complete = not (hit_cap and not exhausted and len(items) < limit)
    # `hit_cap` only forces a continuation when neither the candidate set nor the page's own
    # limit/budget already finished it first (MC02.1: continue "until budget/limit is filled
    # or a 512-candidate scan cap is reached" — the cap is the fallback stop, not a race).
    next_cursor = None
    if not complete:
        next_cursor = _encode_cursor(
            key,
            {
                "subject": subject,
                "query": query,
                "sources": allowed_sources,
                "namespace": namespace,
                "ranking_version": _RANKING_VERSION,
                "generation": generation,
                "scan_offset": scan_offset,
            },
        )

    size_bytes, size_tokens = _measure_page(items, next_cursor, complete, encoding)
    _record_memory_event(
        telemetry,
        "retrieval",
        size_tokens,
        request_id=request_id,
        event_id=event_id,
        opt_in=opt_in,
        cache_write=cache_write,
    )
    return _page(
        "OK",
        items=items,
        next_cursor=next_cursor,
        complete=complete,
        encoding=encoding,
        tokens=size_tokens,
        bytes_=size_bytes,
    )


def _measure_expand(
    chunk: bytes, next_offset: int | None, complete: bool, encoding: str
) -> tuple[int, int]:
    payload = {
        "content_base64": base64.b64encode(chunk).decode("ascii"),
        "next_offset": next_offset,
        "complete": complete,
        "encoding": encoding,
    }
    text = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    return len(text.encode("utf-8")), _count_tokens(text, encoding)


def _expand(
    code: str,
    *,
    artifact_id: str,
    version: int | None,
    offset: int = 0,
    next_offset: int | None = None,
    complete: bool = False,
    content_base64: str | None = None,
    encoding: str = DEFAULT_ENCODING,
    tokens: int = 0,
    bytes_: int = 0,
) -> dict[str, Any]:
    return {
        "code": code,
        "id": artifact_id,
        "version": version,
        "offset": offset,
        "next_offset": next_offset,
        "complete": complete,
        "content_base64": content_base64,
        "tokens": tokens,
        "bytes": bytes_,
        "encoding": encoding,
    }


def expand_artifact(
    store: TypedArtifactStore,
    *,
    artifact_id: str,
    version: int,
    session_allowlist: Iterable[str] | None,
    offset: int = 0,
    max_tokens: int = DEFAULT_MAX_TOKENS,
    max_bytes: int = DEFAULT_MAX_BYTES,
    encoding: str = DEFAULT_ENCODING,
    telemetry: TelemetryStore | None = None,
    request_id: str | None = None,
    event_id: str | None = None,
    opt_in: bool = False,
    cache_write: bool = False,
) -> dict[str, Any]:
    """MC02 §9.0 exact expansion: returns a base64-encoded byte slice of one stored artifact
    version, starting at `offset`. Concatenating `content_base64` across pages (following
    `next_offset` until `complete`) reconstructs the stored version's bytes exactly, even
    across a multi-byte UTF-8 character split mid-page.

    Visibility is re-checked against the *current* row, not any earlier `recall_page()`
    snapshot: a missing artifact or a denied `source` both return `"E_NOT_VISIBLE"` (identical
    bodies, per §9.0, so a caller can't distinguish "never existed" from "revoked"). Only the
    artifact's *current* `artifact_version` may be expanded — a caller holding a since-changed
    `version` gets `"E_VERSION"`, never silently newer or stale content.

    MC04: passing `telemetry` plus `request_id`/`event_id` records a real successful
    expansion's token cost as an `"expansion"` event; omitted (the default), nothing persists.
    """
    allowed_sources = set(session_allowlist or ())
    current = store.get_current(artifact_id)
    if current is None or not allowed_sources or current.source not in allowed_sources:
        return _expand(
            "E_NOT_VISIBLE",
            artifact_id=artifact_id,
            version=None,
            offset=offset,
            encoding=encoding,
        )
    if current.artifact_version != version:
        return _expand(
            "E_VERSION",
            artifact_id=artifact_id,
            version=current.artifact_version,
            offset=offset,
            encoding=encoding,
        )
    stored_text = store.get_version_content(artifact_id, version)
    if stored_text is None:
        return _expand(
            "E_NOT_VISIBLE",
            artifact_id=artifact_id,
            version=None,
            offset=offset,
            encoding=encoding,
        )

    stored_bytes = stored_text.encode("utf-8")
    total = len(stored_bytes)
    offset = max(0, min(offset, total))

    floor_bytes, floor_tokens = _measure_expand(b"", None, True, encoding)
    if floor_bytes > max_bytes or floor_tokens > max_tokens:
        return _expand(
            "E_BUDGET",
            artifact_id=artifact_id,
            version=version,
            offset=offset,
            encoding=encoding,
        )

    remaining = stored_bytes[offset:]
    if not remaining:
        size = _measure_expand(b"", None, True, encoding)
        _record_memory_event(
            telemetry,
            "expansion",
            size[1],
            request_id=request_id,
            event_id=event_id,
            opt_in=opt_in,
            cache_write=cache_write,
        )
        return _expand(
            "OK",
            artifact_id=artifact_id,
            version=version,
            offset=offset,
            next_offset=None,
            complete=True,
            content_base64="",
            encoding=encoding,
            tokens=size[1],
            bytes_=size[0],
        )

    chunk_len = len(remaining)
    while chunk_len > 0:
        chunk = remaining[:chunk_len]
        next_offset = offset + chunk_len if offset + chunk_len < total else None
        complete = next_offset is None
        size_bytes, size_tokens = _measure_expand(
            chunk, next_offset, complete, encoding
        )
        if size_bytes <= max_bytes and size_tokens <= max_tokens:
            size = (size_bytes, size_tokens)
            break
        chunk_len -= max(1, chunk_len // 4)
    else:
        # Shrank the chunk all the way to nothing without ever fitting the envelope inside
        # both caps: the budget itself is too small to return any content at all.
        return _expand(
            "E_BUDGET",
            artifact_id=artifact_id,
            version=version,
            offset=offset,
            encoding=encoding,
        )

    _record_memory_event(
        telemetry,
        "expansion",
        size[1],
        request_id=request_id,
        event_id=event_id,
        opt_in=opt_in,
        cache_write=cache_write,
    )
    return _expand(
        "OK",
        artifact_id=artifact_id,
        version=version,
        offset=offset,
        next_offset=next_offset,
        complete=complete,
        content_base64=base64.b64encode(chunk).decode("ascii"),
        encoding=encoding,
        tokens=size[1],
        bytes_=size[0],
    )


def embedding_text(content: dict[str, Any]) -> str:
    """MC12 §6.7: the exact, deterministic text embedded (and hashed for the vector cache
    key) for one artifact's `content` -- sorted-key JSON so the same content always produces
    the same text regardless of dict insertion order."""
    return json.dumps(content, ensure_ascii=False, sort_keys=True)


def _cosine(a: Sequence[float], b: Sequence[float]) -> float:
    if len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)


def hybrid_candidates(
    store: TypedArtifactStore,
    *,
    subject: MemorySubject,
    query: str,
    session_allowlist: Iterable[str] | None,
    embed_config: EmbeddingConfig | None,
    cache_write: bool = False,
    embed_fn: Callable[
        [EmbeddingConfig, Sequence[str]], list[list[float]]
    ] = embed_chunks,
    scan_limit: int = _VECTOR_SCAN_CAP,
) -> dict[str, Any]:
    """MC12 §6.7 hybrid ranking: fuses MC02's lexical `search_candidates()` ranking with
    cosine similarity over authorized scoped candidates (`TypedArtifactStore.scope_artifacts()`
    -- never lexical-matched, so a candidate with zero shared terms with `query` is still
    eligible) via deterministic reciprocal-rank fusion: `1/(60+lexical_rank) +
    1/(60+vector_rank)`, an absent rank contributing zero, ID-ascending tie-break.

    Returns `{"available": False, "reason": ...}` when no engine is configured or it is
    unreachable/invalid -- callers must fall back to a plainly-labelled lexical result, never
    report that as hybrid success. Denied sources are excluded by the same scope filter both
    `search_candidates()` and `scope_artifacts()` apply, before any content ever reaches the
    embedding endpoint. Without `cache_write`, a freshly computed vector is used for this
    call's ranking only and is never persisted (`TypedArtifactStore.put_embedding()` is only
    ever called when `cache_write` is true).

    An `"available": True` result also carries `"candidates_truncated"`: `True` when either
    the lexical or vector-scope scan returned a full `scan_limit` (512) batch, meaning
    unseen candidates beyond the cap were never ranked (§6.7 "report candidate truncation").
    """
    allowed_sources = sorted(set(session_allowlist or ()))
    if not allowed_sources:
        return {"available": True, "rows": [], "candidates_truncated": False}
    if embed_config is None:
        return {"available": False, "reason": "no embedding engine configured"}

    lexical_rows = store.search_candidates(
        subject, query, source_allowlist=allowed_sources, scan_limit=scan_limit
    )
    lexical_order = [row["id"] for row in lexical_rows]

    scoped_rows = store.scope_artifacts(
        subject, source_allowlist=allowed_sources, scan_limit=scan_limit
    )
    # §6.7 "bound vector candidates to 512 and report candidate truncation": either scan
    # returning a full `scan_limit` batch means unseen rows may exist beyond the cap, mirroring
    # `recall_page()`'s own `scanned >= _SCAN_CAP` cap-hit detection.
    candidates_truncated = (
        len(lexical_rows) >= scan_limit or len(scoped_rows) >= scan_limit
    )
    rows_by_id: dict[str, Any] = {row["id"]: row for row in scoped_rows}
    for row in lexical_rows:
        rows_by_id.setdefault(row["id"], row)
    if not rows_by_id:
        return {
            "available": True,
            "rows": [],
            "candidates_truncated": candidates_truncated,
        }

    texts: dict[str, str] = {}
    hashes: dict[str, str] = {}
    for artifact_id, row in rows_by_id.items():
        try:
            content = json.loads(row["content"])
        except (TypeError, ValueError):
            continue
        text = embedding_text(content)
        texts[artifact_id] = text
        hashes[artifact_id] = hashlib.sha256(text.encode("utf-8")).hexdigest()

    vectors: dict[str, list[float]] = {}
    missing: list[str] = []
    for artifact_id in texts:
        row = rows_by_id[artifact_id]
        cached = store.get_embedding(
            artifact_id=artifact_id,
            artifact_version=row["artifact_version"],
            content_hash=hashes[artifact_id],
            model_digest=embed_config.model_digest,
            chunking_version=embed_config.chunking_version,
        )
        if cached is not None:
            vectors[artifact_id] = cached
        else:
            missing.append(artifact_id)

    try:
        if missing:
            fresh = embed_fn(embed_config, [texts[i] for i in missing])
            for artifact_id, vector in zip(missing, fresh, strict=True):
                vectors[artifact_id] = vector
                if cache_write:
                    row = rows_by_id[artifact_id]
                    store.put_embedding(
                        artifact_id=artifact_id,
                        artifact_version=row["artifact_version"],
                        content_hash=hashes[artifact_id],
                        model_digest=embed_config.model_digest,
                        chunking_version=embed_config.chunking_version,
                        vector=vector,
                    )
        (query_vector,) = embed_fn(embed_config, [query])
    except EmbeddingEngineUnavailable as exc:
        return {"available": False, "reason": str(exc)}
    except EmbeddingResponseError as exc:
        return {"available": False, "reason": str(exc)}

    vector_order = sorted(
        vectors, key=lambda aid: (-_cosine(query_vector, vectors[aid]), aid)
    )

    lexical_rank = {aid: i + 1 for i, aid in enumerate(lexical_order)}
    vector_rank = {aid: i + 1 for i, aid in enumerate(vector_order)}
    all_ids = set(lexical_order) | set(vector_order)

    def rrf_score(aid: str) -> float:
        score = 0.0
        if aid in lexical_rank:
            score += 1.0 / (_RRF_K + lexical_rank[aid])
        if aid in vector_rank:
            score += 1.0 / (_RRF_K + vector_rank[aid])
        return score

    ranked_ids = sorted(all_ids, key=lambda aid: (-rrf_score(aid), aid))
    return {
        "available": True,
        "rows": [rows_by_id[aid] for aid in ranked_ids],
        "candidates_truncated": candidates_truncated,
    }


def hybrid_page(
    store: TypedArtifactStore,
    *,
    subject: MemorySubject,
    query: str,
    session_allowlist: Iterable[str] | None,
    embed_config: EmbeddingConfig | None,
    limit: int = DEFAULT_LIMIT,
    max_tokens: int = DEFAULT_MAX_TOKENS,
    max_bytes: int = DEFAULT_MAX_BYTES,
    encoding: str = DEFAULT_ENCODING,
    cache_write: bool = False,
    embed_fn: Callable[
        [EmbeddingConfig, Sequence[str]], list[list[float]]
    ] = embed_chunks,
    telemetry: TelemetryStore | None = None,
    request_id: str | None = None,
    event_id: str | None = None,
    opt_in: bool = False,
) -> dict[str, Any]:
    """MC12 §6.7 hybrid retrieval page: `hybrid_candidates()`'s RRF-fused ranking, applying
    the same compact-item budget rules `recall_page()` uses. No cursor/continuation in this
    cut -- the candidate pool is already bounded to `_VECTOR_SCAN_CAP` (512); `data.
    candidates_truncated` reports when that bound actually clipped the scan (§6.7 "report
    candidate truncation") instead of silently treating the capped pool as exhaustive.
    # ponytail: no hybrid pagination; add a cursor if a real workload needs paging past one
    # page of a 512-candidate pool.

    Falls back to a plainly-labelled lexical page (`code: "E_EMBEDDING_UNAVAILABLE"`,
    `retrieval: "lexical"`, `embedding_status: "skipped"`, plus `hybrid_unavailable_reason`)
    when no engine is configured or it is unreachable/invalid -- never reports that as hybrid
    success (§9.0 fixed contract).
    """
    allowed_sources = sorted(set(session_allowlist or ()))
    if not allowed_sources:
        page = _page("OK", complete=True, encoding=encoding)
        page["retrieval"] = "hybrid"
        page["candidates_truncated"] = False
        return page

    fused = hybrid_candidates(
        store,
        subject=subject,
        query=query,
        session_allowlist=allowed_sources,
        embed_config=embed_config,
        cache_write=cache_write,
        embed_fn=embed_fn,
    )
    if not fused["available"]:
        fallback = recall_page(
            store,
            subject=subject,
            query=query,
            session_allowlist=allowed_sources,
            limit=limit,
            max_tokens=max_tokens,
            max_bytes=max_bytes,
            encoding=encoding,
            telemetry=telemetry,
            request_id=request_id,
            event_id=event_id,
            opt_in=opt_in,
            cache_write=cache_write,
        )
        fallback["code"] = "E_EMBEDDING_UNAVAILABLE"
        fallback["retrieval"] = "lexical"
        fallback["embedding_status"] = "skipped"
        fallback["hybrid_unavailable_reason"] = fused["reason"]
        return fallback

    items: list[dict[str, Any]] = []
    for row in fused["rows"]:
        item = _candidate_to_item(row)
        if item is None:
            continue
        trial_bytes, trial_tokens = _measure_page([*items, item], None, True, encoding)
        if trial_bytes > max_bytes or trial_tokens > max_tokens:
            break
        items.append(item)
        if len(items) >= limit:
            break

    size_bytes, size_tokens = _measure_page(items, None, True, encoding)
    _record_memory_event(
        telemetry,
        "retrieval",
        size_tokens,
        request_id=request_id,
        event_id=event_id,
        opt_in=opt_in,
        cache_write=cache_write,
    )
    page = _page(
        "OK",
        items=items,
        next_cursor=None,
        complete=True,
        encoding=encoding,
        tokens=size_tokens,
        bytes_=size_bytes,
    )
    page["retrieval"] = "hybrid"
    page["candidates_truncated"] = fused["candidates_truncated"]
    return page
