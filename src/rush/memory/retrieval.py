"""MC02 §9.0 bounded recall and exact expansion.

`recall_page()` pages `TypedArtifactStore.search_candidates()` into a token/byte-bounded
result within a 512-candidate scan cap. 72-T02: a page is `complete` only when no eligible
candidate remains; a page stopped by its limit, a budget or the scan cap returns an opaque,
HMAC-bound continuation cursor, so following cursors returns every eligible record exactly
once. `expand_artifact()` returns exact byte slices of one stored artifact version, either
base64-encoded (the default) or (`representation="utf8"`) as scalar-aligned UTF-8 text with
the version's `payload_hash`; either way concatenation reconstructs the original bytes.

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
import os
import sqlite3
import time
import uuid
from collections.abc import Callable, Iterable, Iterator, Sequence
from contextlib import ExitStack, contextmanager
from pathlib import Path
from typing import Any, Literal, overload

import tiktoken

from rush.memory.embeddings import (
    MAX_BATCH,
    EmbeddingConfig,
    EmbeddingEngineTimeout,
    EmbeddingEngineUnavailable,
    EmbeddingResponseError,
    embed_chunks,
)
from rush.memory.merkle_invalidator import MerkleInvalidator
from rush.memory.store import (
    BindingVerifier,
    MemoryAccessChanged,
    MemoryArtifact,
    MemorySubject,
    OwnerScope,
    SignatureMismatchError,
    TrojanSourceFoundError,
    TypedArtifactStore,
    _inspect_text_for_trojan_chars,
    _row_to_artifact,
    _row_value,
    _stored_text,
    binding_verifier,
    compute_content_signature,
    embedding_text,
    legacy_owner_scope,
    owner_scope_for_row,
    payload_digest,
)
from rush.token_economy.telemetry import TelemetryStore

_SCAN_CAP = 512
_BATCH_SIZE = 64
_RANKING_VERSION = "mc02-v1"

# MC12 §6.7: reciprocal-rank-fusion constant and vector-candidate scan cap (documented
# ceiling, matches the lexical `_SCAN_CAP`).
_RRF_K = 60
_VECTOR_SCAN_CAP = 512
# 72-T08: the most texts one hybrid read can embed (every row of both capped scans plus
# the query); the admission minimum measures a label carrying this count.
_MAX_EMBEDDED_TEXTS = 2 * _VECTOR_SCAN_CAP + 1

# 72-T08 D14a: the committed paired-evaluation verdict that lets an implicit read default
# to hybrid. `None` until `docs/reports/phase-72-memory-eval/hybrid-verdict.json` records a
# global `benefit`; then `{"verdict", "model", "model_digest", "cases_sha256",
# "verdict_report_sha256"}` from that file and the frozen manifest.
HYBRID_DEFAULT_VERDICT: dict[str, str] | None = {
    "verdict": "benefit",
    "model": "nomic-embed-text",
    "model_digest": "0a109f422b47",
    "cases_sha256": "e04fcc6d17f873f939ae0d91a4da7055e4a0d6b2df6cdbe16dcf4a9c7e84377b",
    "verdict_report_sha256": "32eb82ecb9a09889b84d0205458190d57046e75abed1815ce862d44057c9a814",
}

# 72-T08: the one fixed `hybrid_unavailable_reason` text per labelled-fallback code.
# Exception text never reaches a page.
FALLBACK_REASONS: dict[str, str] = {
    "cursor_continuation": "hybrid retrieval has no cursor; this page continues lexically",
    "empty_query": "hybrid retrieval needs a non-empty query",
    "network_not_granted": "hybrid retrieval needs the network permission",
    "config_invalid": "rush.toml could not be loaded",
    "no_engine_configured": "no embedding engine configured",
    "endpoint_not_loopback": "configured embedding endpoint is not loopback http",
    "model_digest_mismatch": "embedding model or digest does not match",
    "engine_unreachable": "embedding engine unreachable",
    "engine_timeout": "embedding engine timed out",
    "invalid_vectors": "embedding engine returned invalid vectors",
}

DEFAULT_LIMIT = 8
DEFAULT_MAX_TOKENS = 2048
DEFAULT_MAX_BYTES = 8192
DEFAULT_ENCODING = "cl100k_base"

_EXCERPT_CHARS = 200

# T19: `MerkleInvalidator.hash_content` (sha256 of the UTF-8 text) through an
# instance built without `__init__`, whose constructor creates `.rush/cache`;
# a read-only recall creates nothing.
_CONTENT_HASHER = MerkleInvalidator.__new__(MerkleInvalidator)


@dataclasses.dataclass(frozen=True)
class ContainedSource:
    """One anchored source file: the project root and its relative `path_part`
    (read through `trust.read_contained_source`), path-like as the resolved
    contained `path`."""

    project_root: Path
    path_part: str
    path: Path

    def __fspath__(self) -> str:
        return os.fspath(self.path)


@dataclasses.dataclass
class SourceValidationMemo:
    """MC04 request-local canonical-path memo: caches a source file's contained snapshot
    text, its content hash and its API-diff freshness so `defended_recall()` computes each
    exactly once per request, however many returned candidates share that same backing
    file. 72-T01 R21: the text comes from one `trust.read_contained_source` fd and the
    API diff reuses that same text. Discard after the request that created it."""

    _text_cache: dict[tuple[Path, str], str | None] = dataclasses.field(
        default_factory=dict
    )
    _hash_cache: dict[tuple[Path, str], str | None] = dataclasses.field(
        default_factory=dict
    )
    _api_diff_cache: dict[tuple[Path, str, str], Any] = dataclasses.field(
        default_factory=dict
    )

    def source_text(self, project_root: Path, path_part: str) -> str | None:
        key = (Path(project_root), path_part)
        if key not in self._text_cache:
            from rush.memory.trust import read_contained_source

            self._text_cache[key] = read_contained_source(Path(project_root), path_part)
        return self._text_cache[key]

    def source_hash(
        self, project_root: Path | ContainedSource, path_part: str | None = None
    ) -> str | None:
        """Content hash of `path_part` under `project_root`, or of one
        `ContainedSource` (the single path-like argument `_freshness_of` passes)."""
        if isinstance(project_root, ContainedSource):
            root, part = project_root.project_root, project_root.path_part
        elif path_part is not None:
            root, part = Path(project_root), path_part
        else:
            raise TypeError("source_hash needs a ContainedSource or a path_part")
        key = (root, part)
        if key not in self._hash_cache:
            text = self.source_text(root, part)
            self._hash_cache[key] = (
                None if text is None else _CONTENT_HASHER.hash_content(text)
            )
        return self._hash_cache[key]

    def api_diff(
        self, project_root: Path, file_path: Path, symbol: str, path_part: str
    ) -> Any:
        key = (Path(project_root), path_part, symbol)
        if key not in self._api_diff_cache:
            # Deferred import mirrors `TypedArtifactStore.recall()`'s own local import of
            # `ApiDiffer` (avoids a module-load-time cycle between `rush.memory` and
            # `rush.tools`).
            from rush.tools.api_diff import ApiDiffer

            text = self.source_text(project_root, path_part)
            if text is None:
                self._api_diff_cache[key] = "unknown"
            else:
                self._api_diff_cache[key] = ApiDiffer(
                    project_root=project_root
                ).diff_symbol(file_path, symbol, source_text=text)
        return self._api_diff_cache[key]


# 72-T01: memory operation -> policy grant operation (T003 §4). Anything else
# (`overlay_read`, `write`, `bootstrap`, a raw grant name) passes through unchanged.
_GRANT_FOR_OPERATION = {
    "ask": "ask",
    "recall": "ask",
    "related": "ask",
    "explain": "ask",
    "list": "list",
    "expand": "expand",
    "historical": "history",
}

Freshness = Literal["current", "stale", "unknown", "not_applicable"]
VisibilityMode = Literal["ordinary", "inspect", "historical"]


PolicyMode = Literal["policy", "legacy", "unavailable"]


def _marked(canonical: Path) -> bool:
    """D1 registration marker: a final or pending marker in `<root>/.rush`, or an
    error other than absence while looking for one."""
    from rush.memory.authorization import REGISTRATION_MARKER

    rush = canonical / ".rush"
    try:
        names = os.listdir(rush)
    except (FileNotFoundError, NotADirectoryError):
        names = []
    except OSError:
        return True
    if any(name.startswith(REGISTRATION_MARKER + ".pending-") for name in names):
        return True
    try:
        os.lstat(rush / REGISTRATION_MARKER)
    except (FileNotFoundError, NotADirectoryError):
        return False
    except OSError:
        return True
    return True


def _store_owner_match(
    canonical: Path, grants: list[dict[str, Any]], open_store: Callable[[Path], Any]
) -> str | None:
    """D1 row 4/6: `match` when the project's store holds a project-owned row of a
    granted project, `unreadable` when the store cannot be read, else `None`.
    `open_store` is the predicate's read-only opener."""
    ids = {
        legacy_owner_scope(Path(g["project_root"])).id
        for g in grants
        if isinstance(g.get("project_root"), str)
    } | {
        g["owner_scope"]["id"]
        for g in grants
        if g.get("owner_scope", {}).get("kind") == "project"
    }
    try:
        opened = open_store(canonical)
    except (OSError, sqlite3.DatabaseError):
        return "unreadable"
    conn = opened.connection
    if conn is None:
        return "unreadable" if opened.state is not None else None
    try:
        columns = {
            row["name"] for row in conn.execute("PRAGMA table_info(memory_artifacts)")
        }
        if not {"owner_scope_kind", "owner_scope_id"} <= columns or not ids:
            return None
        found = conn.execute(
            "SELECT 1 FROM memory_artifacts WHERE owner_scope_kind = 'project' "
            "AND owner_scope_id IN (SELECT value FROM json_each(?)) LIMIT 1",
            (json.dumps(sorted(ids)),),
        ).fetchone()
    except sqlite3.DatabaseError:
        return "unreadable"
    finally:
        conn.close()
    return "match" if found is not None else None


def memory_policy_decision(
    project_root: Any, *, data_root: Path | None = None
) -> tuple[PolicyMode, str | None]:
    """D1: `(mode, reason)` for one project root. Read-only; never raises."""
    return memory_policy_mode(project_root, data_root=data_root, with_reason=True)


def _memory_policy_decision(
    project_root: Any,
    data_root: Path | None,
    open_store: Callable[[Path], Any],
) -> tuple[PolicyMode, str | None]:
    from rush.memory import authorization as auth
    from rush.workflows.projects import read_descriptor_strict, read_registry_strict

    pol = auth.load_policy_readonly(data_root=data_root)
    try:
        if not isinstance(project_root, (str, os.PathLike)):
            raise TypeError("project root")
        canonical = Path(project_root).resolve()
        os.fspath(canonical).encode("utf-8")
    except (OSError, RuntimeError, ValueError, TypeError, UnicodeError):
        return "unavailable", "project_missing"
    if pol["state"] == "invalid":
        return "unavailable", "policy_invalid"
    if pol["state"] == "unavailable":
        return "unavailable", "data_root_unavailable"
    try:
        overlay = Path(auth.user_overlay_owner_scope(data_root=data_root).id)
    except auth.MemoryPolicyError:
        return "unavailable", "data_root_unavailable"
    if canonical == overlay or overlay in canonical.parents:
        return "unavailable", "overlay_storage_root"
    if pol["state"] == "missing":
        return (
            ("unavailable", "policy_missing")
            if _marked(canonical)
            else (
                "legacy",
                None,
            )
        )
    grants = list(pol["grants"].values())
    root_text = str(canonical)
    registry = read_registry_strict(auth._data_root(data_root))
    rid: str | None = None
    if registry["state"] == "ok":
        for project_id, entry in registry["registry"]["projects"].items():
            if isinstance(entry, dict) and entry.get("root") == root_text:
                rid = str(project_id)
                break
    if any(
        g["project_root"] == root_text or (rid is not None and g["project_id"] == rid)
        for g in grants
    ):
        return "policy", None
    if grants:
        descriptor = read_descriptor_strict(canonical)
        if descriptor["state"] == "ok":
            described = (descriptor["descriptor"] or {}).get("project_id")
            if (
                isinstance(described, str)
                and described
                and any(g["project_id"] == described for g in grants)
            ):
                return "policy", None
        elif descriptor["state"] in ("corrupt", "unreadable"):
            return "unavailable", "project_descriptor_invalid"
        store = _store_owner_match(canonical, grants, open_store)
        if store == "match":
            return "policy", None
        if registry["state"] in ("corrupt", "unreadable"):
            return "unavailable", "project_registry_invalid"
        if store == "unreadable":
            return "unavailable", "memory_store_unreadable"
    if _marked(canonical):
        return "unavailable", "no_grant"
    return "legacy", None


@overload
def memory_policy_mode(
    project_root: Any,
    *,
    data_root: Path | None = None,
    with_reason: Literal[False] = False,
) -> PolicyMode: ...


@overload
def memory_policy_mode(
    project_root: Any, *, data_root: Path | None = None, with_reason: Literal[True]
) -> tuple[PolicyMode, str | None]: ...


def memory_policy_mode(
    project_root: Any, *, data_root: Path | None = None, with_reason: bool = False
) -> PolicyMode | tuple[PolicyMode, str | None]:
    """D1 predicate: the mode (`memory_policy_decision(...)[0]`), or with
    `with_reason=True` the `(mode, reason)` pair. Read-only; never raises. Its
    store-owner probe (rows 4/6) opens the store only through
    `TypedArtifactStore.open_readonly`, which creates nothing."""
    try:
        decision = _memory_policy_decision(
            project_root,
            data_root,
            lambda canonical: TypedArtifactStore.open_readonly(canonical),
        )
    except Exception:  # noqa: BLE001 - the mode predicate never raises
        decision = ("unavailable", "policy_invalid")
    return decision if with_reason else decision[0]


_ASK_OPERATIONS = frozenset(
    {
        "ask",
        "recall",
        "related",
        "explain",
        "prepare",
        "resume",
        "plan_checks",
        "last_success_diagnose",
    }
)
_MUTATING_OPERATIONS = frozenset(
    {"write", "edit", "archive", "delete", "promote", "maintain", "import"}
)


def required_operation_set(
    operation: str,
    *,
    action: str | None = None,
    apply: bool = False,
    historical: bool = False,
    overlay: bool = False,
) -> tuple[str, ...]:
    """D2: the grant operations one memory request needs (primary first)."""
    result = _required_operations(operation, action, apply, overlay)
    if historical and result[0] != "history" and "history" not in result:
        result = (*result, "history")
    return result


def _required_operations(
    operation: str, action: str | None, apply: bool, overlay: bool
) -> tuple[str, ...]:
    if operation == "historical":
        return ("history",)
    if operation == "overlay_read":
        return ("overlay_read",)
    if overlay:
        if operation in {"ask", "recall", "list", "related"} or (
            operation == "preference" and action == "resolve"
        ):
            return ("overlay_read", "list")
        if operation == "expand":
            return ("overlay_read", "expand")
        if operation == "history":
            return ("overlay_read", "history")
        if apply and operation in {
            "write",
            "edit",
            "archive",
            "delete",
            "promote",
            "preference",
        }:
            return ("write",)
        # D2: capsule routes keep their own sets (`preview_import` {list}, `import`
        # {write}, export {expand}) on an overlay-owner grant too.
        if not apply and operation != "capsule":
            return ("overlay_read", "list")
    if (
        operation in _ASK_OPERATIONS
        or (operation == "intent" and action == "check")
        or (operation == "recipe" and action == "resolve")
    ):
        return ("ask",)
    if (
        operation == "list"
        or (not apply and operation in _MUTATING_OPERATIONS)
        or (operation == "preference" and (action == "resolve" or not apply))
        or (operation == "capsule" and action in {"preview_import", "bridge"})
    ):
        return ("list",)
    if operation == "expand" or (
        operation == "capsule" and action in {"preview_export", "export"}
    ):
        return ("expand",)
    if operation == "history":
        return ("history",)
    if (
        (apply and operation in _MUTATING_OPERATIONS)
        or operation in {"link", "consolidate", "verify_attempt"}
        or (operation == "intent" and action in {"create", "confirm", "supersede"})
        or (operation == "recipe" and action in {"record", "outcome"})
        or (operation == "preference" and apply)
        or (operation == "capsule" and action == "import")
    ):
        return ("write",)
    if operation == "handoff":
        return ("write", "expand")
    if operation == "receive":
        return ("expand",)
    if operation in {"bootstrap", "write"}:
        return (operation,)
    raise ValueError(f"no D2 operation set for {operation!r} (action {action!r})")


@dataclasses.dataclass(frozen=True)
class MemoryAccess:
    """72-T01: the resolved authority behind one memory read or write.

    `kind="policy"` comes from `resolve()` (the owner-consented grant in
    `rush.memory.authorization`, never a caller claim); `kind="legacy_allowlist"` is
    the explicit `session_allowlist` form (`legacy()`), valid only in D1 `legacy`
    mode, which filters by source and, only when an owner is declared, by owner.
    `required_operations` is the D2 set this access was resolved for; every one of
    them is in the grant's allowed operations.
    """

    kind: Literal["policy", "legacy_allowlist"]
    project_root: Path
    operation: str
    sources: tuple[str, ...]
    owner_scope: OwnerScope | None
    grant_id: str | None = None
    policy_revision: int | None = None
    project_id: str | None = None
    worktree_id: str | None = None
    session_binding: str | None = None
    data_root: Path | None = None
    requested_sources: tuple[str, ...] = ()
    required_operations: frozenset[str] = frozenset()
    required_operations_order: tuple[str, ...] = ()
    # 72-T05 3.11: the caller's task context; it changes usability, never authority.
    task_id: str | None = None
    # 72-T05 D25: the store this access reads or writes (the overlay owner's
    # `<data_root>/user` store, else the project root); set by every constructor.
    storage_root: Path = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.storage_root is None:
            object.__setattr__(self, "storage_root", self.project_root)

    @classmethod
    def legacy(
        cls,
        project_root: Path,
        session_allowlist: Iterable[str] | None,
        *,
        owner_scope: OwnerScope | None = None,
        operation: str = "ask",
        data_root: Path | None = None,
        task_id: str | None = None,
    ) -> MemoryAccess:
        """The legacy explicit-allowlist access. An empty allowlist yields no sources,
        so every route fails closed on it."""
        root = Path(project_root).resolve()
        return cls(
            kind="legacy_allowlist",
            project_root=root,
            operation=operation,
            sources=tuple(sorted(set(session_allowlist or ()))),
            owner_scope=owner_scope,
            data_root=data_root,
            task_id=task_id,
            storage_root=root,
        )

    @classmethod
    def resolve(
        cls,
        project_root: Path,
        *,
        operation: str,
        action: str | None = None,
        apply: bool = False,
        historical: bool = False,
        overlay: bool = False,
        owner_scope: OwnerScope | None = None,
        requested_sources: Iterable[str] = (),
        session_binding: str | None = None,
        data_root: Path | None = None,
        task_id: str | None = None,
    ) -> MemoryAccess | None:
        """Policy access for one operation, or `None` when the policy denies it (a
        missing policy included). Never writes: `resolve_memory_scope` only reads."""
        return cls.resolve_with_reason(
            project_root,
            operation=operation,
            action=action,
            apply=apply,
            historical=historical,
            overlay=overlay,
            owner_scope=owner_scope,
            requested_sources=requested_sources,
            session_binding=session_binding,
            data_root=data_root,
            task_id=task_id,
        )[0]

    @classmethod
    def resolve_with_reason(
        cls,
        project_root: Path,
        *,
        operation: str,
        action: str | None = None,
        apply: bool = False,
        historical: bool = False,
        overlay: bool = False,
        owner_scope: OwnerScope | None = None,
        requested_sources: Iterable[str] = (),
        session_binding: str | None = None,
        data_root: Path | None = None,
        task_id: str | None = None,
    ) -> tuple[MemoryAccess | None, str]:
        """`resolve()` plus the denial reason (`granted` on success). D25: the
        overlay operation set applies whenever `owner_scope` is the overlay owner."""
        try:
            required = required_operation_set(
                operation,
                action=action,
                apply=apply,
                historical=historical,
                overlay=overlay or is_overlay_owner(owner_scope, data_root),
            )
        except ValueError:
            return None, "invalid_request"
        return cls._resolve_set(
            project_root,
            operation=operation,
            required=required,
            owner_scope=owner_scope,
            requested_sources=tuple(requested_sources),
            session_binding=session_binding,
            data_root=data_root,
            task_id=task_id,
        )

    @classmethod
    def _resolve_set(
        cls,
        project_root: Path,
        *,
        operation: str,
        required: tuple[str, ...],
        owner_scope: OwnerScope | None,
        requested_sources: tuple[str, ...],
        session_binding: str | None,
        data_root: Path | None,
        task_id: str | None = None,
    ) -> tuple[MemoryAccess | None, str]:
        from rush.memory.authorization import (
            WRITER_SOURCE_FAMILIES,
            resolve_memory_scope,
        )

        # D40: an internal caller may narrow to an approved `<family>:*` item; the
        # resolver (a request boundary) only ever sees literal labels.
        families = sorted(
            {
                s
                for s in requested_sources
                if isinstance(s, str)
                and s.endswith(":*")
                and s[:-2] in WRITER_SOURCE_FAMILIES
            }
        )
        literal = [s for s in requested_sources if s not in families]

        def scope(sources: list[str]) -> dict[str, Any]:
            return resolve_memory_scope(
                project_root=project_root,
                operation=required[0],
                owner_scope=owner_scope,
                requested_sources=sources,
                session_binding=session_binding,
                data_root=data_root,
            )

        result = scope(literal)
        if result.get("access") not in ("read", "write"):
            return None, str(result.get("reason") or "policy_invalid")
        approved = list(result["approved_sources"])
        if families:
            full = result if not literal else scope([])
            if full.get("access") not in ("read", "write"):
                return None, str(full.get("reason") or "policy_invalid")
            if not set(families) <= set(full["approved_sources"]):
                return None, "source_not_granted"
            approved = sorted({*(approved if literal else ()), *families})
        if not set(required) <= set(result["allowed_operations"]):
            return None, "operation_not_granted"
        try:
            owner = OwnerScope.from_value(result["owner_scope"])
        except (TypeError, ValueError):
            return None, "policy_invalid"
        storage_root = (
            Path(owner.id)
            if is_overlay_owner(owner, data_root)
            else Path(result["project_root"])
        )
        return (
            cls(
                kind="policy",
                project_root=Path(result["project_root"]),
                operation=operation,
                sources=tuple(approved),
                owner_scope=owner,
                grant_id=result["grant_id"],
                policy_revision=result["policy_revision"],
                project_id=result["project_id"],
                worktree_id=result["worktree_id"],
                session_binding=session_binding,
                data_root=data_root,
                requested_sources=requested_sources,
                required_operations=frozenset(required),
                required_operations_order=required,
                task_id=task_id,
                storage_root=storage_root,
            ),
            "granted",
        )

    def _re_resolve(self) -> tuple[MemoryAccess | None, str]:
        # 72-T01 pin: re-resolve the operations this access claims. A
        # `required_operations` set that no longer matches its recorded order (a
        # forged access) is resolved as claimed, so a grant lacking one denies it.
        required = self.required_operations_order
        if self.required_operations and set(required) != self.required_operations:
            required = tuple(sorted(self.required_operations))
        return MemoryAccess._resolve_set(
            self.project_root,
            operation=self.operation,
            required=required or required_operation_set(self.operation),
            owner_scope=self.owner_scope,
            requested_sources=self.requested_sources,
            session_binding=self.session_binding,
            data_root=self.data_root,
            task_id=self.task_id,
        )

    def recheck(self) -> Literal["ok", "changed", "denied"]:
        """Resolve again with this access's inputs: `denied` when the policy now denies
        it (or, for the legacy form, when the project is no longer in D1 `legacy`
        mode), `changed` when the grant, revision, ids, root, owner or sources moved."""
        if self.kind != "policy":
            try:
                same_root = Path(self.project_root).resolve() == self.project_root
            except (OSError, RuntimeError, ValueError):
                return "denied"
            if not same_root:
                return "denied"
            mode = memory_policy_mode(self.project_root, data_root=self.data_root)
            return "ok" if mode == "legacy" else "denied"
        fresh, _reason = self._re_resolve()
        if fresh is None:
            return "denied"
        # 72-T02 R3: the policy revision is provenance only; a revision bump with
        # every other resolved field unchanged (an unrelated grant) still holds.
        same = dataclasses.replace(fresh, policy_revision=self.policy_revision)
        return "ok" if same == self else "changed"

    def denial_reason(self) -> str:
        """Why a `denied` recheck denies (the fresh resolve reason)."""
        if self.kind != "policy":
            return "policy_mode_changed"
        _fresh, reason = self._re_resolve()
        return reason if reason != "granted" else "access_changed"

    @property
    def historical_allowed(self) -> bool:
        """Historical reads need a `history` grant (policy) or D1 `legacy` mode."""
        if self.kind == "policy":
            return "history" in self.required_operations
        return memory_policy_mode(self.project_root, data_root=self.data_root) == (
            "legacy"
        )


def is_overlay_owner(owner: OwnerScope | None, data_root: Path | None) -> bool:
    """D25: `owner` is the personal-overlay owner (`user_overlay_owner_scope()`)."""
    if owner is None:
        return False
    from rush.memory.authorization import MemoryPolicyError, user_overlay_owner_scope

    try:
        return owner == user_overlay_owner_scope(data_root=data_root)
    except MemoryPolicyError:
        return False


@dataclasses.dataclass(frozen=True)
class RouteDenial:
    """D1: one route's denial before any store, view or telemetry construction."""

    code: str
    reason: str


def recheck_failure(access: MemoryAccess) -> tuple[str, str] | None:
    """D1 race rule, called immediately before a mutation commits: `None` when
    `access` still holds, else the `(code, reason)` the mutation returns."""
    state = access.recheck()
    if state == "ok":
        return None
    if state == "changed":
        return "E_RESTART", "access_changed"
    return "E_PERMISSION", access.denial_reason()


def _recheck_code(access: MemoryAccess, denied_code: str) -> str | None:
    """72-T01 recheck: `None` when `access` still holds, else the route's failure code
    (`denied_code` when the policy now denies it, `E_RESTART` when it changed)."""
    status = access.recheck()
    if status == "ok":
        return None
    return denied_code if status == "denied" else "E_RESTART"


def _access_project_matches(access: MemoryAccess, root: Any) -> bool:
    """`access` was resolved for exactly the project `root` names."""
    try:
        return Path(access.project_root) == Path(root).resolve()
    except (OSError, RuntimeError, ValueError, TypeError):
        return False


def supplied_writer_access_ok(
    root: Path, source: str, access: MemoryAccess, *, data_root: Path | None = None
) -> bool:
    """D4: a caller-supplied writer access authorizes `source` at `root` when it is
    a policy `write` access granting the source, or a legacy access in D1 `legacy`
    mode."""
    from rush.memory.authorization import source_granted

    if not _access_project_matches(access, root):
        return False
    if access.recheck() != "ok":
        return False
    if access.kind == "policy":
        return "write" in access.required_operations and source_granted(
            source, access.sources
        )
    return memory_policy_mode(root, data_root=data_root or access.data_root) == "legacy"


@contextmanager
def authorize_writer(
    root: Path,
    source: str,
    *,
    owner: OwnerScope | None = None,
    data_root: Path | None = None,
    access: MemoryAccess | None = None,
) -> Iterator[MemoryAccess | RouteDenial]:
    """D4: the shared internal-writer gate. Holds the policy lock for the whole
    `with` body and yields the writer's access, or the `RouteDenial` the writer
    turns into its own denial value. Every effect belongs inside the body. A
    supplied `access` pins the data root and owner: a conflicting explicit
    `data_root` or `owner`, or another project's access, is refused."""
    from rush.dashboard.state import PolicyLockRootUncreatable
    from rush.memory.authorization import (
        _data_root,
        hold_policy_lock,
        literal_source_is_valid,
        load_policy_readonly,
    )

    if not isinstance(source, str) or "*" in source:
        yield RouteDenial("E_INPUT", "source_pattern")
        return
    if not literal_source_is_valid(source):
        yield RouteDenial("E_PERMISSION", "invalid_request")
        return
    if access is not None:
        try:
            conflicting = (
                data_root is not None
                and _data_root(data_root) != _data_root(access.data_root)
            ) or (
                owner is not None
                and access.owner_scope is not None
                and owner != access.owner_scope
            )
        except (OSError, RuntimeError, ValueError, TypeError):
            conflicting = True
        if conflicting:
            yield RouteDenial("E_PERMISSION", "policy_grant_required")
            return
        data_root = access.data_root
    # G3: the writer authority is decided before the lock root can be created.
    mode, reason = memory_policy_decision(root, data_root=data_root)
    if mode == "unavailable":
        yield RouteDenial("E_PERMISSION", reason or "policy_invalid")
        return
    with ExitStack() as stack:
        try:
            stack.enter_context(hold_policy_lock(data_root=data_root))
        except PolicyLockRootUncreatable:
            if load_policy_readonly(data_root=data_root)["state"] != "missing":
                yield RouteDenial("E_PERMISSION", "lock_unavailable")
                return
        except Exception:  # noqa: BLE001 - any lock failure denies the write
            yield RouteDenial("E_PERMISSION", "lock_unavailable")
            return
        mode, reason = memory_policy_decision(root, data_root=data_root)
        if mode == "unavailable":
            yield RouteDenial("E_PERMISSION", reason or "policy_invalid")
            return
        if access is not None:
            failure = (
                recheck_failure(access)
                if _access_project_matches(access, root)
                else None
            )
            if failure is not None:
                yield RouteDenial(*failure)
            elif supplied_writer_access_ok(root, source, access, data_root=data_root):
                yield access
            else:
                yield RouteDenial("E_PERMISSION", "policy_grant_required")
            return
        writer_owner = owner or legacy_owner_scope(root)
        if mode == "legacy":
            yield MemoryAccess.legacy(
                root,
                [source],
                owner_scope=writer_owner,
                operation="write",
                data_root=data_root,
            )
            return
        resolved, why = MemoryAccess.resolve_with_reason(
            root,
            operation="write",
            apply=True,
            owner_scope=writer_owner,
            requested_sources=[source],
            data_root=data_root,
        )
        yield resolved if resolved is not None else RouteDenial("E_PERMISSION", why)


def reader_route(
    project_root: Path, operation: str, sources: Sequence[str]
) -> MemoryAccess | RouteDenial:
    """D1 access for an internal reader of a fixed source set (review citations,
    the cache gate, status, continuity, patch memory, invariant graph, hook
    signatures, migration readers): `legacy` mode keeps the explicit allowlist;
    `policy` mode narrows the grant to the listed sources it approves (none
    approved is `source_not_granted`); `unavailable` denies with its reason."""
    from rush.memory.authorization import source_granted

    full = route_access(project_root, operation)
    if isinstance(full, RouteDenial):
        return full
    if full.kind != "policy":
        return MemoryAccess.legacy(project_root, sources, operation=operation)
    keep = [s for s in sources if source_granted(s, full.sources)]
    if not keep:
        return RouteDenial("E_PERMISSION", "source_not_granted")
    return route_access(project_root, operation, session_allowlist=keep)


def narrowed_reader_access(
    project_root: Path, operation: str, sources: Sequence[str]
) -> MemoryAccess | None:
    """`reader_route` with a denial as `None` (the reader reads nothing)."""
    access = reader_route(project_root, operation, sources)
    return access if isinstance(access, MemoryAccess) else None


def reader_row_allowed(access: MemoryAccess, project_root: Path, row: Any) -> bool:
    """D1 row test for an internal reader's `sqlite3.Row`: a legacy access keeps
    every row (HEAD behavior); a policy access keeps only rows of its owner whose
    source it approves."""
    if access.kind != "policy":
        return True
    from rush.memory.authorization import source_granted

    if not source_granted(_row_value(row, "source"), access.sources):
        return False
    return (
        access.owner_scope is None
        or _row_owner(row, Path(project_root).resolve()) == access.owner_scope
    )


def writer_owner(access: MemoryAccess) -> OwnerScope | None:
    """The owner an internal writer's row carries: a policy access's owner, else
    `None` (the store's legacy default)."""
    return access.owner_scope if access.kind == "policy" else None


def _sources_have_pattern(sources: Iterable[Any]) -> bool:
    return any(isinstance(s, str) and "*" in s for s in sources)


def _source_input_denial(sources: list[Any]) -> tuple[str, str] | None:
    """D40 request-source boundary: a `*` is `E_INPUT/source_pattern`; any other
    non-literal label is `E_PERMISSION/invalid_request`."""
    if _sources_have_pattern(sources):
        return "E_INPUT", "source_pattern"
    from rush.memory.authorization import literal_source_is_valid

    if not all(literal_source_is_valid(s) for s in sources):
        return "E_PERMISSION", "invalid_request"
    return None


def route_access(
    project_root: Path,
    operation: str,
    *,
    action: str | None = None,
    apply: bool = False,
    historical: bool = False,
    session_allowlist: Iterable[str] | None = None,
    owner_scope: OwnerScope | None = None,
    data_root: Path | None = None,
    task_id: str | None = None,
) -> MemoryAccess | RouteDenial:
    """D1: the one route-resolution helper. `policy` mode resolves the grant (an
    allowlist only narrows it), `legacy` mode builds the explicit-allowlist access,
    `unavailable` denies with the predicate reason."""
    allowlist = list(session_allowlist or ())
    refused = _source_input_denial(allowlist)
    if refused is not None:
        return RouteDenial(*refused)
    mode, reason = memory_policy_decision(project_root, data_root=data_root)
    if mode == "unavailable":
        return RouteDenial("E_PERMISSION", reason or "policy_invalid")
    if mode == "legacy":
        return MemoryAccess.legacy(
            project_root,
            allowlist,
            owner_scope=owner_scope,
            operation=operation,
            data_root=data_root,
            task_id=task_id,
        )
    access, why = MemoryAccess.resolve_with_reason(
        project_root,
        operation=operation,
        action=action,
        apply=apply,
        historical=historical,
        owner_scope=owner_scope,
        requested_sources=allowlist,
        data_root=data_root,
        task_id=task_id,
    )
    return access if access is not None else RouteDenial("E_PERMISSION", why)


def is_write_access(access: MemoryAccess) -> bool:
    """72-T03 D3: a policy access is write-capable only when `write` is one of the D2
    operations it was resolved for (a preview resolved as `{list}` never is, whatever
    the grant also allows); a legacy access only when its operation maps to `write`
    and the D1 predicate is `legacy` mode right now."""
    if access.kind == "policy":
        return "write" in access.required_operations
    return (
        access.kind == "legacy_allowlist"
        and _GRANT_FOR_OPERATION.get(access.operation, access.operation) == "write"
        and memory_policy_mode(access.project_root, data_root=access.data_root)
        == "legacy"
    )


@dataclasses.dataclass(frozen=True)
class VisibilityDecision:
    """72-T01: the one shared answer for one row under one access and mode."""

    visible: bool
    usable_as_current: bool
    freshness: Freshness
    reason_codes: tuple[str, ...]
    reference: dict[str, Any] | None


_NOT_VISIBLE = VisibilityDecision(False, False, "unknown", ("not_visible",), None)


def read_access(
    project_root: Path,
    operation: str,
    session_allowlist: Iterable[str] | None = None,
    *,
    owner_scope: OwnerScope | None = None,
    data_root: Path | None = None,
    action: str | None = None,
    historical: bool = False,
    task_id: str | None = None,
) -> MemoryAccess | None:
    """72-T01 read convention shared by `MemoryTool` and the learned-advice readers:
    `route_access` with a `RouteDenial` (or a source-less legacy access) as `None`,
    which means fail closed."""
    result = route_access(
        project_root,
        operation,
        action=action,
        historical=historical,
        session_allowlist=session_allowlist,
        owner_scope=owner_scope,
        data_root=data_root,
        task_id=task_id,
    )
    if isinstance(result, RouteDenial) or not result.sources:
        return None
    return result


def _route_access(
    store: TypedArtifactStore,
    access: MemoryAccess | None,
    session_allowlist: Iterable[str] | None,
    *,
    operation: str = "ask",
    historical: bool = False,
) -> tuple[MemoryAccess | None, str | None]:
    """One route's access and, when it is denied outside D1 `legacy` mode, the
    denial reason. A given `access` is used as is; otherwise `legacy` mode builds
    the explicit-allowlist form (an empty allowlist fails closed with no reason),
    `policy` mode resolves the grant narrowed by the allowlist and `unavailable`
    mode denies. Passing both raises `ValueError`."""
    if access is not None and session_allowlist is not None:
        raise ValueError("pass access or session_allowlist, not both")
    if access is None:
        allowlist = list(session_allowlist or ())
        refused = _source_input_denial(allowlist)
        if refused is not None:
            return None, refused[1]
        mode, reason = memory_policy_decision(store.project_root)
        if mode == "unavailable":
            return None, reason or "policy_invalid"
        if mode == "legacy":
            if not allowlist:
                return None, None
            access = MemoryAccess.legacy(store.project_root, allowlist)
        else:
            resolved, why = MemoryAccess.resolve_with_reason(
                store.project_root,
                operation=operation,
                historical=historical,
                requested_sources=allowlist,
            )
            if resolved is None:
                return None, why
            access = resolved
    return (access, None) if access.sources else (None, None)


def _row_owner(row: sqlite3.Row, project_root: Path) -> OwnerScope | None:
    try:
        return owner_scope_for_row(row, project_root)
    except (TypeError, ValueError):
        return None


def _root_allows(store: TypedArtifactStore, access: MemoryAccess) -> bool:
    """§3 step 2 root check (72-T05 D25): the store must be the access's
    `storage_root`; a storage root other than the project root (the personal overlay
    store) needs a policy access resolved for `overlay_read` or for `write` alone."""
    return store.project_root == access.storage_root and (
        access.storage_root == access.project_root
        or (
            access.kind == "policy"
            and (
                "overlay_read" in access.required_operations
                or access.required_operations == frozenset({"write"})
            )
        )
    )


def _access_allows(
    store: TypedArtifactStore,
    row: sqlite3.Row,
    access: MemoryAccess,
    mode: VisibilityMode,
) -> bool:
    from rush.memory.authorization import source_granted

    if not _root_allows(store, access) or not source_granted(
        row["source"], access.sources
    ):
        return False
    if (
        access.owner_scope is not None
        and _row_owner(row, store.project_root) != access.owner_scope
    ):
        return False
    return mode != "historical" or access.historical_allowed


def _lifecycle_reasons(row: sqlite3.Row, now: float) -> list[str]:
    """`expired` needs a sweep (`expired_at`) or a stamped `expires_at` in the past; an
    elapsed TTL alone stays the sweep's job."""
    reasons = []
    if _row_value(row, "archived_at") is not None:
        reasons.append("archived")
    expires_at = _row_value(row, "expires_at")
    if _row_value(row, "expired_at") is not None or (
        expires_at is not None and expires_at <= now
    ):
        reasons.append("expired")
    return reasons


def _parsed_content(row: sqlite3.Row | dict[str, Any]) -> dict[str, Any] | None:
    # 72-T02 D32: stored content is decoded first; non-UTF-8 bytes never parse.
    text = _stored_text(row["content"])
    if text is None:
        return None
    try:
        content = json.loads(text)
    except (TypeError, ValueError, RecursionError):
        return None
    return content if isinstance(content, dict) else None


def _integrity(
    row: sqlite3.Row, verifier: BindingVerifier | None = None
) -> tuple[list[str], str]:
    """Integrity reasons and the OD-1 label: `verified` (bound by an authorized write),
    `backfilled` (bound by the additive migration) or `unbound` (no binding). D41: a
    STATED row whose row binding is `unbound` carries `store_unbound` when no other
    integrity reason already blocks it."""
    content = _parsed_content(row)
    reasons = []
    if content is None:
        reasons.append("integrity_content_corrupt")
    if row["trust_tier"] == "STATED":
        signature = row["signature"]
        if not signature:
            reasons.append("integrity_signature_missing")
        elif content is None or compute_content_signature(content) != signature:
            reasons.append("integrity_signature_mismatch")
    if content is not None and _inspect_text_for_trojan_chars(
        json.dumps(content, ensure_ascii=False)
    ):
        reasons.append("integrity_trojan_source")
    digest = _row_value(row, "payload_hash")
    text = _stored_text(row["content"])
    mismatched = digest is not None and (text is None or payload_digest(text) != digest)
    if mismatched:
        reasons.append("integrity_payload_mismatch")
        label = "mismatch"
    elif digest is None:
        label = "unbound"
    elif _row_value(row, "payload_hash_origin") == "backfill":
        label = "backfilled"
    else:
        label = "verified"
    if (
        not reasons
        and verifier is not None
        and (
            (row["trust_tier"] == "STATED" and verifier.row(row) == "unbound")
            # D41/72-T05: a covered column (including applicability and the task
            # binding) changed outside the store, whatever the row's tier.
            or verifier.row_tampered(row)
        )
    ):
        reasons.append("store_unbound")
    return reasons, label


# PM gate delta 2 (B6): checkpoint-journal rows store the checkpoint *name* in
# `symbol_ref` (`checkpoint_journal.py`), not a code anchor.
_CHECKPOINT_SOURCE = "checkpoint_journal:save_checkpoint"


def _freshness_of(
    store: TypedArtifactStore,
    symbol_ref: str | None,
    content_hash: str | None,
    memo: SourceValidationMemo,
    source: str | None,
) -> tuple[Freshness, tuple[str, ...]]:
    """§3 step 6: the first matching check wins. Containment is decided before the
    file is touched, so an outside file is never hashed, read or parsed. A checkpoint
    row naming a checkpoint (no `::`) is unanchored; an anchored one is checked."""
    if symbol_ref is None or (source == _CHECKPOINT_SOURCE and "::" not in symbol_ref):
        return "not_applicable", ()
    # `path::` (an empty symbol) anchors the whole file, as cache fills write it.
    path_part, sep, symbol = symbol_ref.partition("::")
    if not sep or not path_part:
        return "unknown", ("symbol_ref_malformed",)
    from rush.memory.trust import contained_source_path

    file_path = contained_source_path(store.project_root, path_part)
    if file_path is None:
        return "unknown", ("source_not_contained",)
    if not content_hash:
        return "unknown", ("source_hash_missing",)
    if not file_path.is_file():
        return "unknown", ("source_missing",)
    current_hash = memo.source_hash(
        ContainedSource(store.project_root, path_part, file_path)
    )
    if current_hash is None:
        return "unknown", ("source_unreadable",)
    if current_hash != content_hash:
        return "stale", ("source_hash_mismatch",)
    if file_path.suffix != ".py":
        return "unknown", ("parser_unsupported",)
    if not symbol:
        # A whole-file anchor has no symbol to API-diff: its source hash decides, as
        # before T01, and a read spawns no `git`.
        return "current", ()
    diff = memo.api_diff(store.project_root, file_path, symbol, path_part)
    if isinstance(diff, dict):
        return "stale", ("api_changed",)
    if diff is not None:
        return "unknown", ("api_baseline_unknown",)
    return "current", ()


# D33/PR1: informational reasons never block ordinary use.
_INFORMATIONAL_REASONS = frozenset({"unanchored_note"})
_UNANCHORED_NOTE_SUBJECTS = frozenset(
    {"domain_knowledge", "skill_pattern", "failure", "architectural_decision"}
)
_SESSION_ROW_SOURCES = frozenset(
    {
        "session_memory:record_turn",
        "migration:session_memory",
        "migration:hook_signatures",
    }
)
_EXPERIENCE_KINDS = frozenset(
    {"behavior_success", "repair_episode", "cause_experiment"}
)


def _freshness_class(
    store: TypedArtifactStore,
    row: sqlite3.Row | dict[str, Any],
    memo: SourceValidationMemo,
) -> tuple[Freshness, tuple[str, ...]]:
    """D33/PR1: `(freshness, reasons)` for one row; the first matching class wins.
    Anchored rows (`path::symbol`) keep `_freshness_of`; every unanchored writer
    class is explicit, and an unmatched row is `unknown`."""
    from rush.memory.store import INTERNAL_MEMORY_SOURCES

    symbol_ref = row["symbol_ref"]
    source = row["source"]
    content = _parsed_content(row) or {}
    kind = content.get("kind")
    subject = row["subject"]
    if symbol_ref is not None and "::" in symbol_ref:
        return _freshness_of(store, symbol_ref, row["content_hash"], memo, None)
    if subject == "preference" or row["trust_tier"] == "STATED":
        return "not_applicable", ()
    if subject == "active_context":
        return "not_applicable", ()
    if source in INTERNAL_MEMORY_SOURCES or source in _SESSION_ROW_SOURCES:
        return "not_applicable", ()
    if kind in ("observation", "intent"):
        return "not_applicable", ()
    if subject == "episodic" and kind == "checkpoint" and symbol_ref is None:
        return "not_applicable", ()
    if kind == "consolidated_episode_summary" or kind in _EXPERIENCE_KINDS:
        return "not_applicable", ()
    if kind == "recipe":
        from rush.memory.recipes import resolve_symbol_source

        helper = content.get("helper_ref")
        resolved = resolve_symbol_source(
            store.project_root, helper if isinstance(helper, dict) else None
        )
        if resolved is None:
            return "unknown", ("recipe_helper_unresolved",)
        if resolved[1] != content.get("helper_source_hash"):
            return "stale", ("recipe_helper_changed",)
        return "current", ()
    if source == "skills_generator:generate_skill_markdown":
        digest = content.get("closure_digest")
        if isinstance(digest, str) and digest:
            return "not_applicable", ()
        return "unknown", ("closure_digest_missing",)
    if symbol_ref is None and subject in _UNANCHORED_NOTE_SUBJECTS:
        return "not_applicable", ("unanchored_note",)
    if symbol_ref is not None:
        return "unknown", ("symbol_ref_malformed",)
    return "unknown", ("unanchored_unclassified",)


def _artifact_row(artifact: MemoryArtifact) -> dict[str, Any]:
    return {
        "symbol_ref": artifact.symbol_ref,
        "source": artifact.source,
        "content": json.dumps(artifact.content),
        "subject": artifact.subject,
        "trust_tier": artifact.trust_tier,
        "content_hash": artifact.content_hash,
    }


def artifact_freshness(
    store: TypedArtifactStore,
    artifact: MemoryArtifact | sqlite3.Row,
    *,
    now: float | None = None,
    memo: SourceValidationMemo | None = None,
) -> tuple[str, tuple[str, ...]]:
    """X5: `(freshness, reasons)` for one artifact, with no access value and no write --
    the same freshness `evaluate_artifact_visibility` reports (D33 classes; the
    informational `unanchored_note` is omitted). `now` is accepted for a uniform read
    signature; freshness depends only on the source file."""
    del now
    memo = memo or SourceValidationMemo()
    row = _artifact_row(artifact) if isinstance(artifact, MemoryArtifact) else artifact
    freshness, reasons = _freshness_class(store, row, memo)
    return freshness, tuple(r for r in reasons if r not in _INFORMATIONAL_REASONS)


def _reference(
    store: TypedArtifactStore,
    row: sqlite3.Row,
    access: MemoryAccess,
    freshness: str,
    integrity: str,
    *,
    informational: tuple[str, ...] = (),
    binding: str = "bound",
) -> dict[str, Any]:
    owner = _row_owner(row, store.project_root)
    reference = {
        "artifact_id": row["id"],
        "artifact_version": row["artifact_version"],
        "project_id": access.project_id,
        "worktree_id": access.worktree_id,
        "owner_scope": owner.as_dict() if owner is not None else None,
        "source": row["source"],
        "subject": row["subject"],
        "trust_tier": row["trust_tier"],
        "origin_kind": row["origin_kind"],
        "origin_id": row["origin_id"],
        "freshness": freshness,
        "integrity": integrity,
        "payload_hash": _row_value(row, "payload_hash"),
        "reason_codes": list(informational),
        "applicability": _row_value(row, "applicability"),
        "task_binding": _task_binding(row),
    }
    if binding == "unbound":
        reference["store_binding"] = "unbound"
    return reference


_APPLICABILITY_REASONS = {
    "rejected": "applicability_rejected",
    "superseded": "applicability_superseded",
    "pending": "applicability_pending",
}
# 72-T05: rows a plain listing never shows as current artifacts (it carries no
# reasons); `PreferenceStore.resolve` reads them through the decision instead.
NOT_CURRENT_REASONS = frozenset(
    {*_APPLICABILITY_REASONS.values(), "applicability_invalid", "task_mismatch"}
)


def _task_binding(row: sqlite3.Row) -> list[Any] | None:
    binding = [
        _row_value(row, "task_project_id"),
        _row_value(row, "task_worktree_id"),
        _row_value(row, "task_id"),
    ]
    return binding if binding[2] is not None else None


def _applicability_reasons(row: sqlite3.Row, access: MemoryAccess) -> list[str]:
    """72-T05 3.3: non-blocking reasons that keep a row visible but not usable as
    current: a non-active applicability, or a task binding other than the access's
    own (project, worktree, task)."""
    reasons: list[str] = []
    applicability = _row_value(row, "applicability")
    if applicability in _APPLICABILITY_REASONS:
        reasons.append(_APPLICABILITY_REASONS[applicability])
    elif applicability not in (None, "active"):
        reasons.append("applicability_invalid")
    binding = _task_binding(row)
    if binding is not None and not (
        access.kind == "policy"
        and access.task_id is not None
        and access.project_id is not None
        and access.worktree_id is not None
        and binding == [access.project_id, access.worktree_id, access.task_id]
    ):
        reasons.append("task_mismatch")
    return reasons


def _decide(
    store: TypedArtifactStore,
    row: sqlite3.Row,
    *,
    access: MemoryAccess,
    mode: VisibilityMode,
    now: float | None,
    memo: SourceValidationMemo | None,
    verifier: BindingVerifier | None = None,
) -> VisibilityDecision:
    """§3 steps 3-8 for a row that already passed the access gate."""
    moment = time.time() if now is None else now
    verifier = verifier if verifier is not None else binding_verifier(store)
    integrity_reasons, label = _integrity(row, verifier)
    blocking = _lifecycle_reasons(row, moment) + integrity_reasons
    if blocking and mode != "historical":
        return _NOT_VISIBLE
    freshness, freshness_reasons = _freshness_class(
        store, row, memo or SourceValidationMemo()
    )
    informational = tuple(r for r in freshness_reasons if r in _INFORMATIONAL_REASONS)
    derived_reasons: tuple[str, ...] = ()
    content = _parsed_content(row)
    if (
        isinstance(content, dict)
        and content.get("kind") == "consolidated_episode_summary"
    ):
        # 72-T03 derived-summary adapter. Deferred import: consolidation imports this
        # module. Members that are summaries are refused before they are decided, so
        # this never recurses.
        from rush.memory.consolidation import summary_invalid_reason

        invalid = summary_invalid_reason(
            store, content, access=access, now=moment, memo=memo
        )
        if invalid == "derived_member_not_visible":
            # C01/C02: a summary never discloses support the reader cannot see, in
            # any mode (ordinary, inspect or historical).
            return _NOT_VISIBLE
        derived_reasons = (invalid,) if invalid is not None else ()
    reasons = tuple(
        sorted(
            {
                *blocking,
                *(r for r in freshness_reasons if r not in informational),
                *derived_reasons,
                *_applicability_reasons(row, access),
            }
        )
    )
    return VisibilityDecision(
        visible=True,
        usable_as_current=not reasons and freshness in ("current", "not_applicable"),
        freshness=freshness,
        reason_codes=reasons,
        reference=_reference(
            store,
            row,
            access,
            freshness,
            label,
            informational=informational,
            binding=verifier.row(row),
        ),
    )


def evaluate_artifact_visibility(
    store: TypedArtifactStore,
    artifact: sqlite3.Row | MemoryArtifact | None,
    *,
    access: MemoryAccess,
    mode: VisibilityMode = "ordinary",
    now: float | None = None,
    memo: SourceValidationMemo | None = None,
    verifier: BindingVerifier | None = None,
) -> VisibilityDecision:
    """72-T01: the one shared visibility decision every memory read route uses.

    A `MemoryArtifact` is re-read as its current row. Denied by root, source, owner or
    an unauthorized historical mode: `NOT` (`visible=False`, `("not_visible",)`, no
    reference). Archived, expired or integrity-failed rows are `NOT` in ordinary and
    inspect modes and visible-but-not-usable, with sorted reasons, in historical mode.
    Ordinary delivery needs `visible and usable_as_current`: no reasons and freshness
    `current` or `not_applicable`.
    """
    row = (
        store.get_current_row(artifact.id)
        if isinstance(artifact, MemoryArtifact)
        else artifact
    )
    if row is None or not _access_allows(store, row, access, mode):
        return _NOT_VISIBLE
    return _decide(
        store, row, access=access, mode=mode, now=now, memo=memo, verifier=verifier
    )


def _raise_legacy_integrity(row: sqlite3.Row) -> None:
    """The legacy recall contract (Invariants 3/4): raise rather than skip."""
    content = _parsed_content(row)
    if row["trust_tier"] == "STATED" and (
        not row["signature"]
        or content is None
        or compute_content_signature(content) != row["signature"]
    ):
        raise SignatureMismatchError(
            f"signature mismatch for STATED artifact {row['id']}"
        )
    if content is not None:
        findings = _inspect_text_for_trojan_chars(
            json.dumps(content, ensure_ascii=False)
        )
        if findings:
            raise TrojanSourceFoundError(
                f"Trojan Source characters detected in artifact {row['id']}: {findings}"
            )


def visible_artifacts(
    store: TypedArtifactStore,
    rows: Iterable[sqlite3.Row],
    *,
    access: MemoryAccess,
    mode: VisibilityMode = "ordinary",
    now: float | None = None,
    memo: SourceValidationMemo | None = None,
    legacy_raise: bool = False,
) -> list[MemoryArtifact]:
    """`rows` through the shared decision, as `MemoryArtifact`s carrying their decision
    `freshness`. The decision sets `stale=True` only for `stale` freshness and never
    clears a stored `stale` flag. Ordinary mode keeps rows usable as
    current; inspect and historical keep every visible row. With `legacy_raise`, a
    legacy-allowlist access raises `SignatureMismatchError`/`TrojanSourceFoundError`
    for a row that passed the source/owner filter."""
    memo = memo or SourceValidationMemo()
    moment = time.time() if now is None else now
    default_owner = legacy_owner_scope(store.project_root)
    verifier = binding_verifier(store)
    found: list[MemoryArtifact] = []
    for row in rows:
        if not _access_allows(store, row, access, mode):
            continue
        if legacy_raise and access.kind == "legacy_allowlist":
            _raise_legacy_integrity(row)
        decision = _decide(
            store,
            row,
            access=access,
            mode=mode,
            now=moment,
            memo=memo,
            verifier=verifier,
        )
        if (
            not decision.visible
            or (mode == "ordinary" and not decision.usable_as_current)
            or (mode == "inspect" and NOT_CURRENT_REASONS & set(decision.reason_codes))
        ):
            continue
        try:
            artifact = _row_to_artifact(row, default_owner_scope=default_owner)
        except (TypeError, ValueError):
            continue
        if not isinstance(artifact.content, dict):
            continue
        found.append(
            dataclasses.replace(
                artifact,
                freshness=decision.freshness,
                stale=artifact.stale or decision.freshness == "stale",
            )
        )
    return found


def read_visible(
    project_root: Path,
    queries: Iterable[tuple[MemorySubject, str]],
    *,
    access: MemoryAccess,
    now: float | None = None,
) -> list[list[MemoryArtifact]]:
    """72-T01 (OD-3) learned-advice reads: one `search_rows()` FTS match per
    `(subject, query)` through a read-only view and the shared decision (ordinary mode),
    one result list per query. A missing, old or unreadable store reads nothing and
    creates nothing."""
    pending = list(queries)
    view, _state = TypedArtifactStore.open_readonly_view(access.storage_root)
    if view is None:
        return [[] for _ in pending]
    memo = SourceValidationMemo()
    try:
        found = [
            visible_artifacts(
                view,
                view.search_rows(subject, query),
                access=access,
                now=now,
                memo=memo,
            )
            for subject, query in pending
        ]
    finally:
        view.close()
    # 72-T01 F2: recheck immediately before emit; a moved policy emits nothing.
    return found if access.recheck() == "ok" else [[] for _ in pending]


def defended_recall(
    store: TypedArtifactStore,
    subject: MemorySubject,
    query: str,
    session_allowlist: Iterable[str] | None = None,
    *,
    memo: SourceValidationMemo | None = None,
    access: MemoryAccess | None = None,
    now: float | None = None,
) -> list[MemoryArtifact]:
    """MC04 one-query defended lookup: `store.search_candidates()` (MC02's own bounded/ranked
    query — never a second raw FTS query), deduplicating source-file hashing and API-diff
    calls across candidates via `memo` (fresh per call when the caller passes none).

    72-T01: every candidate goes through `evaluate_artifact_visibility` in ordinary mode,
    so only rows usable as current come back. `access` and `session_allowlist` are
    mutually exclusive (`ValueError`); neither fails closed.

    `query` is the raw (unquoted) search text — `search_candidates()` quotes it as an FTS5
    literal phrase itself; callers must not pre-quote it (unlike the legacy `store.search()`).
    A legacy allowlist raises `SignatureMismatchError`/`TrojanSourceFoundError` exactly as
    `store.recall()` does; callers that treat a defended read as fail-closed should keep
    wrapping this in `contextlib.suppress(Exception)`, same as before.
    """
    access, _why = _route_access(store, access, session_allowlist)
    if access is None or access.recheck() != "ok":
        return []
    moment = time.time() if now is None else now
    rows = store.search_candidates(
        subject,
        query,
        source_allowlist=list(access.sources),
        scan_limit=_SCAN_CAP,
        owner_scope=access.owner_scope,
        now=moment,
    )
    found = visible_artifacts(
        store,
        rows,
        access=access,
        mode="ordinary",
        now=moment,
        memo=memo,
        legacy_raise=True,
    )
    # 72-T01 F2: recheck immediately before emit; a moved policy emits nothing.
    return found if access.recheck() == "ok" else []


def _record_memory_event(
    telemetry: TelemetryStore | Callable[[], TelemetryStore] | None,
    kind: str,
    tokens: int,
    *,
    request_id: str | None,
    event_id: str | None,
    invocation_id: str | None,
    project_id: str | None,
    run_id: str | None = None,
    agent_id: str | None = None,
    session_id: str | None = None,
    opt_in: bool,
    cache_write: bool,
    access: MemoryAccess | None = None,
    encoding: str = DEFAULT_ENCODING,
    artifact_version: int | None = None,
    offset: int | None = None,
    payload_hash: str | None = None,
) -> None:
    """Stage delivery events; retain primitive accounting outside receipt scopes."""
    from rush.delivery import compact

    if (
        telemetry is None
        or not request_id
        or not event_id
        or not (opt_in or cache_write)
    ):
        return
    owner = access.owner_scope if access is not None else None
    arguments: dict[str, Any] = {
        "request_id": request_id,
        "event_id": event_id,
        "invocation_id": invocation_id,
        "opt_in": opt_in,
        "cache_write": cache_write,
        "owner_scope_kind": owner.kind if owner is not None else None,
        "owner_scope_id": owner.id if owner is not None else None,
        "sources_json": json.dumps(sorted(access.sources))
        if access is not None
        else None,
    }
    arguments.update(
        {
            key: value
            for key, value in (
                ("project_id", project_id),
                ("run_id", run_id),
                ("agent_id", agent_id),
                ("session_id", session_id),
            )
            if value is not None
        }
    )
    frame = compact.RECEIPT_FRAME.get()
    if kind in {"retrieval", "expansion"} and frame is not None:
        if frame.pending_memory_events is None or access is None:
            return
        arguments.update(
            artifact_version=artifact_version, offset=offset, payload_hash=payload_hash
        )
        frame.pending_memory_events.append(
            compact.PendingMemoryEvent(telemetry, kind, encoding, access, arguments)
        )
        return
    recorder = (
        telemetry()
        if callable(telemetry) and not isinstance(telemetry, TelemetryStore)
        else telemetry
    )
    recorder.record_memory_event(kind, tokens, **arguments)


def _encoder(encoding: str) -> tiktoken.Encoding:
    return tiktoken.get_encoding(encoding)


def _count_tokens(text: str, encoding: str) -> int:
    # Stored text may spell a special token (`<|endoftext|>`): it is ordinary text here.
    return len(_encoder(encoding).encode(text, disallowed_special=()))


_CURSOR_PREFIX = "m2."
# base64url, no padding, of 20 bytes: nonce (4) + sealed scan offset (4) + tag (12).
_CURSOR_BODY_CHARS = 27


def _cursor_binding(
    *,
    namespace: str,
    project_id: str | None,
    worktree_id: str | None,
    owner: tuple[str, str] | None,
    grant_id: str | None,
    subject: str,
    query: str,
    sources: Sequence[str],
    task_id: str | None = None,
    v2: dict[str, Any] | None = None,
) -> bytes:
    """72-T02: the digest a page token is bound to. Any change to the scope, the query or
    the ranking makes every earlier token fail closed (`E_RESTART`). R3: the policy
    revision is not bound (an unrelated grant between pages keeps a cursor valid).

    72-T06: a schema_version 2 page (`v2`) binds its subjects, trust tiers,
    freshness, archive mode and visibility mode in place of the single v1 `subject`;
    a v1 binding's bytes are unchanged."""
    body: dict[str, Any] = {
        "v": 3,
        "namespace": namespace,
        "project_id": project_id,
        "worktree_id": worktree_id,
        "owner": list(owner) if owner else None,
        "grant_id": grant_id,
        "subject": subject,
        "query": query,
        "sources": sorted(sources),
        "task_id": task_id,
        "archive_mode": "active",
        "ranking_version": _RANKING_VERSION,
    }
    if v2 is not None:
        del body["subject"]
        body.update(v2)
    text = json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(text.encode("utf-8")).digest()


def _encode_cursor(
    key: bytes, binding: bytes, generation: int, scan_offset: int
) -> str:
    """72-T02: a deterministic, opaque 30-character page token. The scan offset is sealed
    and the token is HMAC-bound to `binding` and the store `generation`; it exposes no
    IDs, offset or generation."""
    offset_bytes = scan_offset.to_bytes(4, "big")
    gen = generation.to_bytes(8, "big")
    nonce = hmac.new(
        key,
        b"rush.page-cursor.nonce\x00" + binding + gen + offset_bytes,
        hashlib.sha256,
    ).digest()[:4]
    stream = hmac.new(
        key, b"rush.page-cursor.stream\x00" + nonce, hashlib.sha256
    ).digest()[:4]
    sealed = bytes(a ^ b for a, b in zip(offset_bytes, stream, strict=True))
    tag = hmac.new(
        key,
        b"rush.page-cursor.tag\x00" + nonce + sealed + binding + gen,
        hashlib.sha256,
    ).digest()[:12]
    body = base64.urlsafe_b64encode(nonce + sealed + tag).rstrip(b"=").decode("ascii")
    return _CURSOR_PREFIX + body


def _decode_cursor(
    key: bytes, cursor: str, binding: bytes, generation: int
) -> int | None:
    """The sealed scan offset, or `None` (restart required) for anything malformed,
    non-canonical, foreign or drifted. Never raises."""
    if not _cursor_syntax_ok(cursor):
        return None
    raw = base64.urlsafe_b64decode(cursor[len(_CURSOR_PREFIX) :] + "=")
    nonce, sealed, tag = raw[:4], raw[4:8], raw[8:]
    gen = generation.to_bytes(8, "big")
    expected = hmac.new(
        key,
        b"rush.page-cursor.tag\x00" + nonce + sealed + binding + gen,
        hashlib.sha256,
    ).digest()[:12]
    if not hmac.compare_digest(tag, expected):
        return None
    stream = hmac.new(
        key, b"rush.page-cursor.stream\x00" + nonce, hashlib.sha256
    ).digest()[:4]
    return int.from_bytes(
        bytes(a ^ b for a, b in zip(sealed, stream, strict=True)), "big"
    )


def _cursor_syntax_ok(cursor: str) -> bool:
    """72-T02 D36: the canonical `m2.` token shape (27 ASCII base64url characters of
    20 bytes, unused bits zero). A token failing this is malformed input (`E_INPUT`),
    never a restart."""
    if not cursor.startswith(_CURSOR_PREFIX):
        return False
    body = cursor[len(_CURSOR_PREFIX) :]
    if len(body) != _CURSOR_BODY_CHARS or not body.isascii():
        return False
    try:
        raw = base64.urlsafe_b64decode(body + "=")
    except ValueError:
        return False
    return (
        len(raw) == 20
        and base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii") == body
    )


FrameBytes = Callable[[str, dict[str, Any]], bytes]
"""72-T02 D35: `(code, data) -> bytes` -- the exact bytes the caller's transport writes
for the memory envelope carrying `code` and `data`. Budgets (both caps) apply to them."""

# Keys a refusal carries only when the framed response still fits both caps.
_OPTIONAL_KEYS = (
    "required",
    "message",
    "state",
    "alternatives",
    "field",
    "reason",
    "total_bytes",
)


def _frame_tokens(raw: bytes, encoding: str) -> int:
    return len(_encoder(encoding).encode(raw.decode("utf-8"), disallowed_special=()))


class MixedFrame:
    """72-T06 D35: a `FrameBytes` for a call that supplied only one cap. A caller-
    supplied cap is measured on the transport `frame`; the defaulted one on the
    transport-independent `payload`. `on_frame` is `(bytes, tokens)`."""

    def __init__(
        self,
        frame: FrameBytes,
        payload: FrameBytes,
        on_frame: tuple[bool, bool],
    ) -> None:
        self.frame = frame
        self.payload = payload
        self.on_frame = on_frame

    def __call__(self, code: str, data: dict[str, Any]) -> bytes:
        return self.frame(code, data)


def _measured(
    frame_bytes: FrameBytes, code: str, data: dict[str, Any]
) -> tuple[bytes, bytes]:
    """The bytes each cap (bytes, tokens) is measured on."""
    raw = frame_bytes(code, data)
    if isinstance(frame_bytes, MixedFrame):
        payload = frame_bytes.payload(code, data)
        return (
            raw if frame_bytes.on_frame[0] else payload,
            raw if frame_bytes.on_frame[1] else payload,
        )
    return raw, raw


def _frame_size(
    frame_bytes: FrameBytes, code: str, data: dict[str, Any], encoding: str
) -> tuple[int, int]:
    for_bytes, for_tokens = _measured(frame_bytes, code, data)
    return len(for_bytes), _frame_tokens(for_tokens, encoding)


def _frame_fits(
    frame_bytes: FrameBytes,
    code: str,
    data: dict[str, Any],
    encoding: str,
    max_bytes: int,
    max_tokens: int,
) -> bool:
    """Whether the framed response fits both caps. Tiktoken encodings are byte-level
    (tokens <= bytes), so a frame within `max_tokens` bytes is not tokenized."""
    for_bytes, for_tokens = _measured(frame_bytes, code, data)
    if len(for_bytes) > max_bytes:
        return False
    return (
        len(for_tokens) <= max_tokens
        or _frame_tokens(for_tokens, encoding) <= max_tokens
    )


def _fit_optional(
    page: dict[str, Any],
    frame_bytes: FrameBytes | None,
    encoding: str,
    max_bytes: int,
    max_tokens: int,
) -> dict[str, Any]:
    """A refusal `page` (with `code`) whose optional keys are dropped, in
    `_OPTIONAL_KEYS` order, until its framed response fits both caps."""
    if frame_bytes is None:
        return page
    code = page["code"]
    data = {key: value for key, value in page.items() if key != "code"}
    for key in _OPTIONAL_KEYS:
        if _frame_fits(frame_bytes, code, data, encoding, max_bytes, max_tokens):
            break
        data.pop(key, None)
    else:
        # B16: the last-pruned frame is emitted even when nothing fits; measure it.
        frame_bytes(code, data)
    return {"code": code, **data}


def _excerpt(content: dict[str, Any]) -> str:
    text = content.get("text")
    if not isinstance(text, str):
        text = json.dumps(content, ensure_ascii=False, sort_keys=True)
    return text[:_EXCERPT_CHARS]


def _item_relations(
    store: TypedArtifactStore,
    artifact_id: str,
    version: int,
    access: MemoryAccess,
    *,
    now: float | None = None,
    memo: SourceValidationMemo | None = None,
) -> list[dict[str, Any]]:
    """MC03: the candidate's authorized depth-1 relations through
    `related_artifacts()` under the same `access`. 72-T03: every neighbor goes through
    the shared decision before the node cap, so a neighbor not delivered as current
    (archived, expired, tampered, another owner, stale) is dropped, never disclosed."""
    # Deferred import: `rush.memory.relations` imports this module's budgets.
    from rush.memory.relations import related_artifacts

    related = related_artifacts(
        store,
        artifact_id=artifact_id,
        version=version,
        session_allowlist=None,
        access=access,
        now=now,
        memo=memo,
    )
    return related["items"] if related["code"] == "OK" else []


# D34: `(subject, owner kind, owner id, symbol_ref)`, and a page's visible peers per
# key plus the `contradicts` version pairs touching its rows (`_contest_index`).
_ContestKey = tuple[str, str, str, str | None]
_ContestIndex = tuple[
    dict[_ContestKey, list[tuple[str, int, MemoryArtifact]]],
    set[tuple[tuple[str, int], tuple[str, int]]],
]


def _candidate_to_item(
    row: Any,
    store: TypedArtifactStore,
    access: MemoryAccess,
    decision: VisibilityDecision,
    *,
    contest: _ContestIndex,
    now: float | None = None,
    memo: SourceValidationMemo | None = None,
) -> dict[str, Any] | None:
    """`None` marks a corrupt candidate (malformed/non-object `content`) to skip — never
    raises, so one bad row can't abort the whole page (MC02.1 "corrupt candidates do not
    starve page"). 72-T01: `freshness` is the shared decision's vocabulary."""
    content = _parsed_content(row)
    if content is None:
        return None
    item: dict[str, Any] = {
        "id": row["id"],
        "version": row["artifact_version"],
        "excerpt": _excerpt(content),
        "source": row["source"],
        "trust": row["trust_tier"],
        "freshness": decision.freshness,
        "relations": _item_relations(
            store, row["id"], row["artifact_version"], access, now=now, memo=memo
        ),
    }
    if (decision.reference or {}).get("store_binding") == "unbound":
        item["store_binding"] = "unbound"
    if _contested(store, row, contest):
        item["contested"] = True
    return item


# 72-T06: the reference keys of a schema_version 2 item.
V2_REFERENCE_KEYS = (
    "artifact_id",
    "artifact_version",
    "project_id",
    "worktree_id",
    "owner_scope",
    "source",
    "subject",
    "trust_tier",
    "origin_kind",
    "origin_id",
    "freshness",
    "integrity",
    "payload_hash",
)


def v2_reference(decision: VisibilityDecision) -> dict[str, Any]:
    """The schema_version 2 `reference` of one decided row."""
    reference = decision.reference or {}
    return {key: reference.get(key) for key in V2_REFERENCE_KEYS}


def _v2_item(
    item: dict[str, Any], row: Any, decision: VisibilityDecision
) -> dict[str, Any]:
    """A compact item plus its v2 reference, hashes, usability and exclusion reasons."""
    return {
        **item,
        "reference": v2_reference(decision),
        "content_hash": row["content_hash"],
        "symbol_ref": row["symbol_ref"],
        "usable_as_current": decision.usable_as_current,
        "reason_codes": list(decision.reason_codes),
    }


def _contest_index(
    store: TypedArtifactStore,
    rows: Iterable[Any],
    access: MemoryAccess,
    *,
    now: float | None,
    memo: SourceValidationMemo | None,
    verifier: BindingVerifier | None = None,
) -> _ContestIndex:
    """D34: the visible peers of `rows` from one untruncated SQL scan per subject
    (a page has one) limited to the rows' distinct `(owner, subject, symbol_ref)`
    keys and the D40 predicate over `access.sources`, keyed `(subject, owner kind,
    owner id, symbol_ref)`, plus every `contradicts` relation joining one of the
    rows' versions."""
    default_owner = legacy_owner_scope(store.project_root)
    keys: dict[str, set[tuple[str, str, str | None]]] = {}
    versions: list[tuple[str, int]] = []
    for row in rows:
        owner = _row_owner(row, store.project_root)
        if owner is None:
            continue
        keys.setdefault(row["subject"], set()).add(
            (owner.kind, owner.id, row["symbol_ref"])
        )
        versions.append((row["id"], row["artifact_version"]))
    peers: dict[_ContestKey, list[tuple[str, int, MemoryArtifact]]] = {}
    for subject, subject_keys in keys.items():
        grouped = store.contest_peers(subject, subject_keys, access.sources)
        for (kind, owner_id, symbol_ref), group in grouped.items():
            visible: list[tuple[str, int, MemoryArtifact]] = []
            for peer in group:
                if not evaluate_artifact_visibility(
                    store, peer, access=access, now=now, memo=memo, verifier=verifier
                ).visible:
                    continue
                try:
                    other = _row_to_artifact(peer, default_owner_scope=default_owner)
                except (TypeError, ValueError):
                    continue
                if isinstance(other.content, dict):
                    visible.append((peer["id"], peer["artifact_version"], other))
            peers[(subject, kind, owner_id, symbol_ref)] = visible
    return peers, store.contradiction_pairs(versions)


def _contested(store: TypedArtifactStore, row: Any, contest: _ContestIndex) -> bool:
    """D34: a visible peer with the same owner, subject and anchor contradicts this
    row (either direction of `trust.evaluate_conflict`), or a versioned
    `contradicts` relation joins the two. Peers come from `_contest_index`."""
    from rush.memory.trust import evaluate_conflict

    owner = _row_owner(row, store.project_root)
    if owner is None:
        return False
    try:
        mine = _row_to_artifact(
            row, default_owner_scope=legacy_owner_scope(store.project_root)
        )
    except (TypeError, ValueError):
        return False
    peers, contradictions = contest
    me = (row["id"], row["artifact_version"])
    key = (row["subject"], owner.kind, owner.id, row["symbol_ref"])
    for peer_id, peer_version, other in peers.get(key, ()):
        if peer_id == row["id"]:
            continue
        if (
            evaluate_conflict(mine, other) == "delete"
            or evaluate_conflict(other, mine) == "delete"
            or (me, (peer_id, peer_version)) in contradictions
        ):
            return True
    return False


def _page_text(
    items: list[dict[str, Any]],
    next_cursor: str | None,
    complete: bool,
    encoding: str,
    extra: dict[str, Any] | None = None,
) -> str:
    payload = {
        "items": items,
        "next_cursor": next_cursor,
        "complete": complete,
        "encoding": encoding,
    }
    if extra:
        payload.update(extra)
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def _measure_page(
    items: list[dict[str, Any]],
    next_cursor: str | None,
    complete: bool,
    encoding: str,
    extra: dict[str, Any] | None = None,
) -> tuple[int, int]:
    """Byte/token size of the serialized `data` payload a page will actually return — the
    §9.0 "budgets include the serialized returned memory payload, metadata and cursor"
    envelope, not the outer MCP/JSON-RPC transport framing (counted separately, per §9.0).
    `extra` (72-T02: `required`) is merged after the four page keys."""
    text = _page_text(items, next_cursor, complete, encoding, extra)
    return len(text.encode("utf-8")), _count_tokens(text, encoding)


def _page_bytes(
    items: list[dict[str, Any]], next_cursor: str | None, complete: bool, encoding: str
) -> int:
    """`_measure_page`'s byte size alone, without tokenizing."""
    return len(_page_text(items, next_cursor, complete, encoding).encode("utf-8"))


def _contains_special_token(text: str, encoding: str) -> bool:
    """Whether tiktoken's default `encode` would refuse `text` (it raises
    `ValueError` on any special-token string)."""
    return any(token in text for token in _encoder(encoding).special_tokens_set)


def _trial_page_bytes(
    items: list[dict[str, Any]],
    items_bytes: int,
    item: dict[str, Any],
    *,
    max_bytes: int,
    max_tokens: int,
    encoding: str,
    reserve_cursor: str | None = None,
    extra: dict[str, Any] | None = None,
    complete: bool | None = None,
) -> int | None:
    """Byte size of the cursor-free `_measure_page(items + [item], None, True, ...)`
    page when the trial page fits both budgets, else `None` -- the same decision as
    measuring the whole trial page, without retokenizing it per candidate.

    72-T02: the trial page is `items + [item]` with `next_cursor=reserve_cursor` and
    `complete=(reserve_cursor is None)`, so an item is accepted only if the page still
    fits with the continuation token it may have to carry. The token is ASCII and adds
    `len(token) + 2` (quotes) in place of `null` (4), and `false` adds one byte over
    `true`.

    `items_bytes` is the running byte size of the current cursor-free page. Appending
    an item adds its compact JSON plus one separating comma. Tiktoken's encodings are
    byte-level, so a text never has more tokens than bytes: while the trial page's
    bytes are within `max_tokens` its tokens are too, and only a larger page is fully
    tokenized. An item carrying a special-token string is always fully tokenized so
    tiktoken raises its `ValueError` exactly as it did when every trial page was
    tokenized.

    72-T08: `extra` (page labels) is counted exactly as `_measure_page` counts it and
    `complete` overrides the trial page's flag (a hybrid trial page is incomplete);
    `items_bytes` must be measured with the same two."""
    trial_complete = reserve_cursor is None if complete is None else complete
    item_text = json.dumps(item, ensure_ascii=False, separators=(",", ":"))
    trial_bytes = items_bytes + len(item_text.encode("utf-8")) + (1 if items else 0)
    reserved_bytes = trial_bytes
    if reserve_cursor is not None:
        reserved_bytes += len(reserve_cursor) + 2 - 4 + 1
    if reserved_bytes > max_tokens or _contains_special_token(item_text, encoding):
        _bytes, trial_tokens = _measure_page(
            [*items, item], reserve_cursor, trial_complete, encoding, extra
        )
        if trial_tokens > max_tokens:
            return None
    if reserved_bytes > max_bytes:
        return None
    return trial_bytes


def _page(
    code: str,
    *,
    items: list[dict[str, Any]] | None = None,
    next_cursor: str | None = None,
    complete: bool = False,
    encoding: str = DEFAULT_ENCODING,
    tokens: int = 0,
    bytes_: int = 0,
    reason: str | None = None,
) -> dict[str, Any]:
    page: dict[str, Any] = {
        "code": code,
        "items": items or [],
        "next_cursor": next_cursor,
        "complete": complete,
        "tokens": tokens,
        "bytes": bytes_,
        "encoding": encoding,
    }
    if reason is not None:
        page["reason"] = reason
    return page


def _page_data(
    items: list[dict[str, Any]],
    next_cursor: str | None,
    complete: bool,
    encoding: str,
    size: tuple[int, int],
) -> dict[str, Any]:
    """An OK page's envelope `data` (every `_page` key except `code`)."""
    return {
        "items": items,
        "next_cursor": next_cursor,
        "complete": complete,
        "tokens": size[1],
        "bytes": size[0],
        "encoding": encoding,
    }


def _recheck_page(failure: tuple[str, str], encoding: str) -> dict[str, Any]:
    """72-T02 D36: a failed recheck -- `E_PERMISSION` with the resolver's reason, or
    `E_RESTART` for an authorized access that moved."""
    code, why = failure
    return _page(
        code, encoding=encoding, reason=why if code == "E_PERMISSION" else None
    )


def _records(telemetry: Any, page: dict[str, Any]) -> bool:
    """72-T02 R1: a route's telemetry factory records only an OK page with at least
    one item; a caller-built `TelemetryStore` records every OK page (HEAD)."""
    return isinstance(telemetry, TelemetryStore) or bool(page["items"])


def _emit_current(
    store: TypedArtifactStore,
    generation: int,
    items: list[dict[str, Any]],
    access: MemoryAccess,
    now: float | None,
    mode: VisibilityMode = "ordinary",
) -> bool:
    """72-T02 R13/D39: whether a page may still be emitted, decided on one fresh
    reader (never the request's own, possibly immutable, view) inside one read
    transaction: the store generation is unchanged and every emitted id is still
    current at its emitted version and eligible under `mode` for a fresh visibility
    decision (expiry, source, owner). A reader that cannot open is a restart."""
    with store.fresh_reader() as conn:
        if conn is None or store.current_generation(conn) != generation:
            return False
        moment = time.time() if now is None else now
        memo = SourceValidationMemo()
        verifier = binding_verifier(store)
        for item in items:
            row = store.get_current_row(item["id"], conn=conn)
            if row is None or row["artifact_version"] != item["version"]:
                return False
            decision = evaluate_artifact_visibility(
                store,
                row,
                access=access,
                mode=mode,
                now=moment,
                memo=memo,
                verifier=verifier,
            )
            if not _eligible(decision, mode):
                return False
    return True


def _denied_page(reason: str, encoding: str) -> dict[str, Any]:
    """R1: a route denied outside D1 `legacy` mode: no items, never `complete`."""
    page = _page("E_PERMISSION", encoding=encoding)
    page["reason"] = reason
    return page


def _within(size: tuple[int, int], max_bytes: int, max_tokens: int) -> bool:
    return size[0] <= max_bytes and size[1] <= max_tokens


def _recall_floor(encoding: str) -> list[tuple[str, dict[str, Any]]]:
    """72-T02 C05: every post-admission compact response's base data, optional keys
    removed: the empty complete page, the self-measured `E_BUDGET` page and each
    refusal page (and the envelope-level refusal with empty `data`)."""

    def data(complete: bool, size: tuple[int, int] = (0, 0)) -> dict[str, Any]:
        return _page_data([], None, complete, encoding, size)

    floor = [
        ("OK", data(True, _measure_page([], None, True, encoding))),
        ("E_BUDGET", data(False, _measure_page([], None, False, encoding))),
    ]
    for code in (
        "E_RESTART",
        "E_PERMISSION",
        "E_MIGRATION",
        "E_STORE_CORRUPT",
        "E_STORE_BUSY",
    ):
        floor.extend([(code, data(False)), (code, {})])
    return floor


def _recall_required(
    max_bytes: int,
    max_tokens: int,
    encoding: str,
    frame_bytes: FrameBytes | None = None,
) -> dict[str, int] | None:
    """72-T02 admission: the smallest canonical `E_BUDGET` page's size when a cap is
    below it (the caller gets `E_INPUT` with these as `required`), else `None`. With
    `frame_bytes` (D35) it is the largest framed response over every post-admission
    code, bytes and tokens maximised separately."""
    if frame_bytes is None:
        min_bytes, min_tokens = _measure_page([], None, False, encoding)
    else:
        sizes = [
            _frame_size(frame_bytes, code, data, encoding)
            for code, data in _recall_floor(encoding)
        ]
        min_bytes = max(size[0] for size in sizes)
        min_tokens = max(size[1] for size in sizes)
    if max_bytes < min_bytes or max_tokens < min_tokens:
        return {"max_bytes": min_bytes, "max_tokens": min_tokens}
    return None


def recall_admission(
    *,
    limit: Any,
    max_bytes: int,
    max_tokens: int,
    encoding: str,
    cursor: Any = None,
    frame_bytes: FrameBytes | None = None,
) -> dict[str, Any] | None:
    """72-T02 recall admission (contract C05: before any store read or effect): the
    `E_INPUT` page for `limit < 1`, a cursor that is not a canonical `m2.` token
    (D36), an unknown `encoding` or caps below the smallest admitted response (with
    `required`), else `None`."""
    if not isinstance(limit, int) or isinstance(limit, bool) or limit < 1:
        return _page("E_INPUT", encoding=encoding)
    if cursor is not None and (
        not isinstance(cursor, str) or not _cursor_syntax_ok(cursor)
    ):
        return _page("E_INPUT", encoding=encoding)
    try:
        _encoder(encoding)
    except (ValueError, TypeError):
        return _page("E_INPUT", encoding=encoding)
    required = _recall_required(max_bytes, max_tokens, encoding, frame_bytes)
    if required is not None:
        refused = _page("E_INPUT", encoding=encoding)
        refused["required"] = required
        return refused
    return None


def hybrid_admission(
    *,
    limit: Any,
    max_bytes: int,
    max_tokens: int,
    encoding: str,
    cursor: Any = None,
    frame_bytes: FrameBytes | None = None,
) -> dict[str, Any] | None:
    """72-T08 (R6, contract C05): `recall_admission`'s `limit`/cursor/`encoding` refusals,
    then `E_INPUT` with `required` when a cap is below the largest zero-item envelope the
    hybrid route can emit (its `E_BUDGET` page, or a labelled fallback page for any
    `FALLBACK_REASONS` code, each carrying `_MAX_EMBEDDED_TEXTS`) plus the framing the
    lexical admission adds over its own minimum page (with `frame_bytes`, 72-T02 D35: the
    framed response). Runs before any store read, access resolution, telemetry or
    network call."""
    refused = recall_admission(
        limit=limit,
        max_bytes=max_bytes,
        max_tokens=max_tokens,
        encoding=encoding,
        cursor=cursor,
        frame_bytes=frame_bytes,
    )
    if refused is not None and "required" not in refused:
        return refused
    floor = recall_admission(
        limit=1,
        max_bytes=0,
        max_tokens=0,
        encoding=encoding,
        frame_bytes=frame_bytes,
    )
    lexical_min = _measure_page([], None, False, encoding)
    framing = (0, 0)
    if floor is not None and "required" in floor:
        framing = (
            floor["required"]["max_bytes"] - lexical_min[0],
            floor["required"]["max_tokens"] - lexical_min[1],
        )
    envelopes: list[dict[str, Any]] = [
        _hybrid_labels(False, "candidate_cap", _MAX_EMBEDDED_TEXTS)
    ]
    envelopes.extend(
        _fallback_labels(code, _MAX_EMBEDDED_TEXTS) for code in FALLBACK_REASONS
    )
    sizes = [_measure_page([], None, False, encoding, env) for env in envelopes]
    required = {
        "max_bytes": max(size[0] for size in sizes) + framing[0],
        "max_tokens": max(size[1] for size in sizes) + framing[1],
    }
    if max_bytes < required["max_bytes"] or max_tokens < required["max_tokens"]:
        page = _page("E_INPUT", encoding=encoding)
        page["required"] = required
        return page
    return None


def _hybrid_labels(
    candidates_truncated: bool, incomplete_reason: str | None, embedded_texts: int
) -> dict[str, Any]:
    """72-T08: the labels of a page ranked by hybrid retrieval."""
    return {
        "retrieval": "hybrid",
        "candidates_truncated": candidates_truncated,
        "incomplete_reason": incomplete_reason,
        "embedded_texts": embedded_texts,
    }


def _fallback_labels(code: str, embedded_texts: int) -> dict[str, Any]:
    """72-T08: the labels of a hybrid-requested page served lexically."""
    return {
        "retrieval": "lexical",
        "embedding_status": "skipped",
        "embedding_fallback_code": code,
        "hybrid_unavailable_reason": FALLBACK_REASONS[code],
        "embedded_texts": embedded_texts,
    }


def _budget_page(
    encoding: str,
    required: tuple[int, int],
    max_bytes: int,
    max_tokens: int,
    frame_bytes: FrameBytes | None = None,
    labels: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """72-T02: an `E_BUDGET` page that itself fits both caps (its framed response
    with `frame_bytes`). `required` is included only when it still fits; otherwise
    the canonical minimum (admitted) page is sent. 72-T08: `labels` (retrieval labels)
    are always carried and counted."""
    base = dict(labels or {})

    def build(extra: dict[str, Any]) -> tuple[dict[str, Any], bool]:
        size = _measure_page([], None, False, encoding, extra or None)
        page = _page("E_BUDGET", encoding=encoding, tokens=size[1], bytes_=size[0])
        page.update(extra)
        if frame_bytes is None:
            return page, _within(size, max_bytes, max_tokens)
        data = {key: value for key, value in page.items() if key != "code"}
        return page, _frame_fits(
            frame_bytes, "E_BUDGET", data, encoding, max_bytes, max_tokens
        )

    page, fits = build(
        {**base, "required": {"max_bytes": required[0], "max_tokens": required[1]}}
    )
    if fits:
        return page
    # B16: the minimum is emitted too, so admission measures its frame.
    return build(base)[0]


def recall_page(
    store: TypedArtifactStore,
    *,
    subject: MemorySubject | None = None,
    query: str,
    session_allowlist: Iterable[str] | None = None,
    access: MemoryAccess | None = None,
    limit: int = DEFAULT_LIMIT,
    max_tokens: int = DEFAULT_MAX_TOKENS,
    max_bytes: int = DEFAULT_MAX_BYTES,
    encoding: str = DEFAULT_ENCODING,
    cursor: str | None = None,
    telemetry: TelemetryStore | Callable[[], TelemetryStore] | None = None,
    request_id: str | None = None,
    event_id: str | None = None,
    invocation_id: str | None = None,
    project_id: str | None = None,
    run_id: str | None = None,
    agent_id: str | None = None,
    session_id: str | None = None,
    opt_in: bool = False,
    cache_write: bool = False,
    now: float | None = None,
    frame_bytes: FrameBytes | None = None,
    subjects: Sequence[MemorySubject] | None = None,
    mode: VisibilityMode = "ordinary",
    trust_tiers: Sequence[str] | None = None,
    freshness: Sequence[str] | None = None,
    archive_mode: Literal["active", "historical"] = "active",
    v2_items: bool = False,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """MC02 §9.0 bounded recall: pages `store.search_candidates()` (prefiltered by
    subject/source/owner/archive/expiry) into a token/byte-bounded result.

    72-T01: every candidate goes through `evaluate_artifact_visibility` in ordinary mode;
    only rows usable as current become items. `access` (a resolved `MemoryAccess`) and
    `session_allowlist` (the legacy form) are mutually exclusive (`ValueError`); neither,
    or an empty allowlist, fails closed (an empty, `complete=True` page). The access is
    rechecked at entry and again after the page is measured, before telemetry: a denied
    recheck returns `E_PERMISSION`, a changed grant or revision `E_RESTART`, both with
    no items.

    MC04: passing `telemetry` plus `request_id`/`event_id` records this page's real token
    cost as a `"retrieval"` event (deduplicated by those IDs), gated on `opt_in`/`cache_write`
    exactly like `TelemetryStore.record_memory_event()`. Omitting `telemetry` (the default)
    persists nothing — existing callers see no behavior change. Only OK pages record.

    72-T02 honest paging: `complete=True` only when no eligible candidate remains. A page
    stopped by `limit`, a byte/token cap or the 512-row scan cap returns `complete=False`
    and an opaque `next_cursor` (`m2.` + 27 base64url characters) pointing at the first
    candidate not yet consumed; following cursors returns every eligible record exactly
    once in rank order. The cursor is HMAC-bound to the namespace, the access's project,
    worktree, owner, policy revision and grant, the subject, query, sources and ranking
    version, the store generation and the scan position; any drift, forgery or legacy
    cursor is `E_RESTART` with no items. A record that fits no page at the resume point
    is `E_BUDGET` (no items, no cursor, `required` caps that return it). Caps below the
    smallest `E_BUDGET` page, `limit < 1` or an unknown `encoding` are `E_INPUT` before
    any store read. A store with no cursor key (a read-only view) is `E_MIGRATION`.

    72-T02 D35: with `frame_bytes` every fit decision (admission, each trial page,
    `required`) is made on the exact transport bytes of the response; `tokens`/`bytes`
    stay the payload measure. R13: before a page is returned the access is rechecked
    (`E_PERMISSION` with its reason wins) and the generation is re-read on a fresh
    reader (`E_RESTART` on drift). R3: the cursor does not bind the policy revision.

    72-T08: `extra` (the labelled hybrid fallback's retrieval labels) is merged into
    every `OK` and `E_BUDGET` page and counted in every trial and final measure; the
    default `None` leaves every page byte-identical.
    """
    labels: dict[str, Any] = dict(extra or {})
    # 72-T06: a v2 page scans every requested subject (in place of the v1 `subject`),
    # keeps rows by its visibility `mode` (`ordinary`: usable as current; `inspect`
    # and `historical`: visible) and its freshness filter, prefilters trust tiers, and
    # binds all of it into the cursor.
    v2 = subjects is not None
    scope_subjects = sorted(set(subjects)) if subjects is not None else [subject]
    subject_arg: Any = scope_subjects[0] if len(scope_subjects) == 1 else scope_subjects
    historical = archive_mode == "historical"
    v2_binding = (
        {
            "subjects": scope_subjects,
            "trust_tiers": sorted(trust_tiers) if trust_tiers is not None else None,
            "freshness": sorted(freshness) if freshness is not None else None,
            "archive_mode": archive_mode,
            "mode": mode,
        }
        if v2
        else None
    )
    scan_filters: dict[str, Any] = (
        {
            "trust_tiers": list(trust_tiers) if trust_tiers is not None else None,
            "include_archived": historical,
            "include_expired": historical,
        }
        if v2
        else {}
    )
    # R6: admission (a malformed cursor, caps) precedes policy resolution.
    refused = recall_admission(
        limit=limit,
        max_bytes=max_bytes,
        max_tokens=max_tokens,
        encoding=encoding,
        cursor=cursor,
        frame_bytes=frame_bytes,
    )
    if refused is not None:
        return refused
    access, why = _route_access(store, access, session_allowlist)

    def refusal(page: dict[str, Any]) -> dict[str, Any]:
        return _fit_optional(page, frame_bytes, encoding, max_bytes, max_tokens)

    if access is None:
        if why is not None:
            return refusal(_denied_page(why, encoding))
        return _page("OK", complete=True, encoding=encoding)
    failure = recheck_failure(access)
    if failure is not None:
        return refusal(_recheck_page(failure, encoding))
    allowed_sources = list(access.sources)
    moment = time.time() if now is None else now
    memo = SourceValidationMemo()

    # P69-07 subsection e: mint a real per-call identity when the caller doesn't supply
    # one (today's only caller, `tools/memory.py`, passes a content-derived `request_id`
    # instead) so two distinct calls sharing identical content never collide.
    real_invocation_id = invocation_id or str(uuid.uuid4())

    try:
        key = store.cursor_key()
    except (TypeError, sqlite3.OperationalError):
        # A read-only view whose store has no key row: never create one on a read.
        return _page("E_MIGRATION", encoding=encoding)
    generation = store.current_generation()
    owner = access.owner_scope
    binding = _cursor_binding(
        namespace=str(store.project_root),
        project_id=access.project_id,
        worktree_id=access.worktree_id,
        owner=(owner.kind, owner.id) if owner is not None else None,
        grant_id=access.grant_id,
        subject=str(subject),
        query=query,
        sources=allowed_sources,
        task_id=access.task_id,
        v2=v2_binding,
    )
    if cursor is None:
        scan_offset = 0
    else:
        decoded = _decode_cursor(key, cursor, binding, generation)
        if decoded is None:
            return _page("E_RESTART", encoding=encoding)
        scan_offset = decoded

    def token(at: int) -> str:
        return _encode_cursor(key, binding, generation, at)

    def eligible_item(row: Any, contest: _ContestIndex) -> dict[str, Any] | None:
        decision = evaluate_artifact_visibility(
            store, row, access=access, mode=mode, now=moment, memo=memo
        )
        keep = decision.usable_as_current if mode == "ordinary" else decision.visible
        if not keep or (freshness is not None and decision.freshness not in freshness):
            return None
        item = _candidate_to_item(
            row, store, access, decision, contest=contest, now=moment, memo=memo
        )
        return _v2_item(item, row, decision) if v2_items and item is not None else item

    def page_fit(
        page_items: list[dict[str, Any]], next_cursor: str | None, complete: bool
    ) -> tuple[int, int] | None:
        """The page's payload size when its response fits both caps, else `None`."""
        size = _measure_page(page_items, next_cursor, complete, encoding, labels)
        if frame_bytes is None:
            return size if _within(size, max_bytes, max_tokens) else None
        data = _page_data(page_items, next_cursor, complete, encoding, size)
        data.update(labels)
        fits = _frame_fits(frame_bytes, "OK", data, encoding, max_bytes, max_tokens)
        return size if fits else None

    def page_need(
        page_items: list[dict[str, Any]], next_cursor: str | None, complete: bool
    ) -> tuple[int, int]:
        """The caps the page needs: its payload size, or its framed size."""
        size = _measure_page(page_items, next_cursor, complete, encoding, labels)
        if frame_bytes is None:
            return size
        data = _page_data(page_items, next_cursor, complete, encoding, size)
        data.update(labels)
        return _frame_size(frame_bytes, "OK", data, encoding)

    def trial(item: dict[str, Any], reserve: str | None) -> int | None:
        if frame_bytes is None:
            return _trial_page_bytes(
                items,
                base_bytes,
                item,
                max_bytes=max_bytes,
                max_tokens=max_tokens,
                encoding=encoding,
                reserve_cursor=reserve,
                extra=labels,
            )
        # ponytail: one full framed serialization per candidate (O(limit x page));
        # an incremental frame-size model is the upgrade if pages grow large.
        fitted = page_fit([*items, item], reserve, reserve is None)
        return base_bytes if fitted is not None else None

    items: list[dict[str, Any]] = []
    base_bytes = len(_page_text([], None, True, encoding, labels).encode("utf-8"))
    position = last_fit = scan_offset
    # (item, start): fits only as the final page / fits no page at all.
    pending: tuple[dict[str, Any], int] | None = None
    blocked: tuple[dict[str, Any], int] | None = None
    more = exhausted = False
    scanned = 0
    while not more and not exhausted and scanned < _SCAN_CAP:
        batch_limit = min(_BATCH_SIZE, _SCAN_CAP - scanned)
        batch = (
            store.search_candidates(
                subject_arg,
                query,
                source_allowlist=allowed_sources,
                scan_offset=position,
                scan_limit=batch_limit,
                owner_scope=access.owner_scope,
                **scan_filters,
                # 72-T02 fix1: no `now=` here. An SQL expiry filter under LIMIT/OFFSET
                # shrinks the rank set when a row expires between pages and skips a
                # row; expiry is decided per row by `evaluate_artifact_visibility`.
            )
            if query
            # 72-T01 R5: an unqueried (compact `list`) page browses the subject's
            # rows in ID order through the same per-row decision.
            else store.scope_artifacts(
                subject_arg,
                source_allowlist=allowed_sources,
                scan_offset=position,
                scan_limit=batch_limit,
                owner_scope=access.owner_scope,
                **scan_filters,
            )
        )
        contest = _contest_index(store, batch, access, now=moment, memo=memo)
        for row in batch:
            item = eligible_item(row, contest)
            if item is not None and (pending is not None or len(items) >= limit):
                more = True  # an eligible row is left, not consumed
                break
            start, position, scanned = position, position + 1, scanned + 1
            if item is None:
                continue  # corrupt or ineligible: consumed
            fit = trial(item, token(position))
            if fit is not None:
                items.append(item)
                base_bytes = fit
                last_fit = position
                continue
            final = trial(item, None)
            if final is not None:
                pending = (item, start)
                continue
            blocked = (item, start)
            position, scanned, more = start, scanned - 1, True
            break
        if not more and len(batch) < batch_limit:
            exhausted = True

    def emit(page: dict[str, Any]) -> dict[str, Any]:
        """72-T02 R13: the policy recheck first (a revocation wins over drift), then
        the store generation on a fresh reader -- never this request's own, possibly
        immutable, view -- before a page is returned or telemetry recorded."""
        failure = recheck_failure(access)
        if failure is not None:
            return refusal(_recheck_page(failure, encoding))
        if not _emit_current(store, generation, page["items"], access, now, mode=mode):
            return _page("E_RESTART", encoding=encoding)
        if page["code"] == "OK" and _records(telemetry, page):
            _record_memory_event(
                telemetry,
                "retrieval",
                page["tokens"],
                request_id=request_id,
                event_id=event_id,
                invocation_id=real_invocation_id,
                project_id=project_id,
                run_id=run_id,
                agent_id=agent_id,
                session_id=session_id,
                opt_in=opt_in,
                cache_write=cache_write,
                access=access,
                encoding=encoding,
            )
        return page

    def ok(
        page_items: list[dict[str, Any]],
        next_cursor: str | None,
        size: tuple[int, int],
    ) -> dict[str, Any]:
        page = _page(
            "OK",
            items=page_items,
            next_cursor=next_cursor,
            complete=next_cursor is None,
            encoding=encoding,
            tokens=size[1],
            bytes_=size[0],
        )
        page.update(labels)
        return emit(page)

    stuck = pending or blocked
    if exhausted:
        final_items = [*items, pending[0]] if pending is not None else items
        fitted = page_fit(final_items, None, True)
        if fitted is not None:
            return ok(final_items, None, fitted)
        resume = last_fit  # unreachable in practice: fall back to the accepted trial
    else:
        resume = stuck[1] if stuck is not None else position
    if items:
        next_cursor = token(resume)
        fitted = page_fit(items, next_cursor, False)
        if fitted is None and resume != last_fit:
            next_cursor = token(last_fit)  # identical to the accepted trial page
            fitted = page_fit(items, next_cursor, False)
        size = fitted or _measure_page(items, next_cursor, False, encoding, labels)
        return ok(items, next_cursor, size)
    if stuck is not None:
        need = page_need([stuck[0]], token(stuck[1] + 1), False)
        return emit(
            _budget_page(
                encoding,
                need,
                max_bytes,
                max_tokens,
                frame_bytes=frame_bytes,
                labels=labels,
            )
        )
    # The scan cap was spent on ineligible rows: an empty continuation page.
    next_cursor = token(resume)
    fitted = page_fit([], next_cursor, False)
    if fitted is not None:
        return ok([], next_cursor, fitted)
    need = page_need([], next_cursor, False)
    return emit(
        _budget_page(
            encoding,
            need,
            max_bytes,
            max_tokens,
            frame_bytes=frame_bytes,
            labels=labels,
        )
    )


def _measure_expand(page: dict[str, Any], encoding: str) -> tuple[int, int]:
    """72-T02: byte/token size of a base64 expand response's measured payload --
    every key except `code`, `tokens` and `bytes` (the same rule as utf8)."""
    payload = {
        key: value
        for key, value in page.items()
        if key not in ("code", "tokens", "bytes")
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
    representation: str = "base64",
) -> dict[str, Any]:
    """A base64 expand envelope, or (72-T02, `representation="utf8"`) the content-free
    utf8 envelope of the same code: null content, digest and `total_bytes`."""
    if representation == "utf8":
        page: dict[str, Any] = {"code": code}
        page.update(
            _utf8_payload(
                artifact_id=artifact_id,
                version=version,
                offset=offset,
                next_offset=None,
                complete=False,
                content_utf8=None,
                payload_hash=None,
                total_bytes=None,
                encoding=encoding,
            )
        )
        page["tokens"] = tokens
        page["bytes"] = bytes_
        return page
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


def _utf8_payload(
    *,
    artifact_id: str,
    version: int | None,
    offset: int,
    next_offset: int | None,
    complete: bool,
    content_utf8: str | None,
    payload_hash: str | None,
    total_bytes: int | None,
    encoding: str,
) -> dict[str, Any]:
    """72-T02: the measured payload of a utf8 expand response (every key except `code`,
    `tokens` and `bytes`)."""
    return {
        "id": artifact_id,
        "version": version,
        "representation": "utf8",
        "offset": offset,
        "next_offset": next_offset,
        "complete": complete,
        "content_utf8": content_utf8,
        "payload_hash": payload_hash,
        "total_bytes": total_bytes,
        "encoding": encoding,
    }


def _measure_utf8(payload: dict[str, Any], encoding: str) -> tuple[int, int]:
    """Byte/token size of a utf8 expand payload (or any measured error payload)."""
    text = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    return len(text.encode("utf-8")), _count_tokens(text, encoding)


def _utf8_page(
    code: str, payload: dict[str, Any], size: tuple[int, int]
) -> dict[str, Any]:
    page = {"code": code, **payload}
    page["tokens"] = size[1]
    page["bytes"] = size[0]
    return page


def _is_boundary(data: bytes, offset: int) -> bool:
    """Whether `offset` starts a UTF-8 scalar (or is the end of `data`)."""
    return offset == len(data) or (data[offset] & 0xC0) != 0x80


def _utf8_slice_end(
    data: bytes, offset: int, fits: Callable[[int], bool]
) -> int | None:
    """The largest tried scalar-boundary end for a slice from `offset` that `fits`, at
    least one scalar; `None` when even one scalar does not fit. `offset < len(data)`."""
    total = len(data)
    first = offset + 1
    while first < total and not _is_boundary(data, first):
        first += 1  # end of one scalar
    end = total
    while True:
        while end > first and not _is_boundary(data, end):
            end -= 1
        if end <= first:
            return first if fits(first) else None
        if fits(end):
            return end
        span = end - offset
        end = offset + span - max(1, span // 4)


def _expand_refusal(
    code: str,
    *,
    artifact_id: str,
    version: int | None,
    offset: int,
    encoding: str,
    representation: str,
    required: Any = None,
) -> dict[str, Any]:
    """A content-free expand refusal; `required` is added when given."""
    page = _expand(
        code,
        artifact_id=artifact_id,
        version=version,
        offset=offset,
        encoding=encoding,
        representation="utf8" if representation == "utf8" else "base64",
    )
    if required is not None:
        page["required"] = required
    return page


def _expand_floor(
    artifact_id: str, version: int, offset: int, encoding: str, representation: str
) -> list[tuple[str, dict[str, Any]]]:
    """72-T02 C05: every post-admission expand refusal's content-free base data,
    optional keys removed (and the envelope-level refusal with empty `data`)."""
    floor: list[tuple[str, dict[str, Any]]] = []
    for code in (
        "E_BUDGET",
        "E_NOT_VISIBLE",
        "E_PERMISSION",
        "E_VERSION",
        "E_OFFSET",
        "E_RESTART",
        "E_MIGRATION",
        "E_STORE_CORRUPT",
        "E_STORE_BUSY",
        "E_INPUT",
    ):
        echoed: int | None = None
        if code == "E_VERSION":
            echoed = 2**63 - 1
        elif code in ("E_BUDGET", "E_OFFSET", "E_MIGRATION", "E_INPUT"):
            echoed = version
        page = _expand_refusal(
            code,
            artifact_id=artifact_id,
            version=echoed,
            offset=offset,
            encoding=encoding,
            representation=representation,
        )
        page.pop("code")
        floor.extend([(code, page), (code, {})])
    return floor


def expand_admission(
    *,
    artifact_id: str,
    version: int,
    offset: int,
    max_bytes: int,
    max_tokens: int,
    encoding: str,
    representation: str,
    mode: str = "ordinary",
    frame_bytes: FrameBytes | None = None,
) -> dict[str, Any] | None:
    """72-T02 expand admission (contract C05: before any store read or effect): the
    `E_INPUT` page for an unknown representation, mode or `encoding`, `E_OFFSET` for
    a negative offset, `E_INPUT` with `required` for caps below the smallest envelope
    (with `frame_bytes`, D35: the largest framed post-admission refusal), else
    `None`."""

    def refuse(
        code: str, *, version_: int | None = None, required: Any = None
    ) -> dict[str, Any]:
        return _expand_refusal(
            code,
            artifact_id=artifact_id,
            version=version_,
            offset=offset,
            encoding=encoding,
            representation=representation,
            required=required,
        )

    if representation not in ("base64", "utf8") or mode not in (
        "ordinary",
        "historical",
    ):
        return refuse("E_INPUT")
    if offset < 0:
        return refuse("E_OFFSET", version_=version)
    try:
        _encoder(encoding)
    except (ValueError, TypeError):
        return refuse("E_INPUT")
    if frame_bytes is not None:
        sizes = [
            _frame_size(frame_bytes, code, data, encoding)
            for code, data in _expand_floor(
                artifact_id, version, offset, encoding, representation
            )
        ]
        minimum = (max(size[0] for size in sizes), max(size[1] for size in sizes))
    elif representation == "utf8":
        null_payload = _utf8_payload(
            artifact_id=artifact_id,
            version=version,
            offset=offset,
            next_offset=None,
            complete=False,
            content_utf8=None,
            payload_hash=None,
            total_bytes=None,
            encoding=encoding,
        )
        minimum = _measure_utf8(null_payload, encoding)
    else:
        minimum = _measure_expand(
            _expand_refusal(
                "E_BUDGET",
                artifact_id=artifact_id,
                version=version,
                offset=offset,
                encoding=encoding,
                representation="base64",
            ),
            encoding,
        )
    if not _within(minimum, max_bytes, max_tokens):
        return refuse(
            "E_INPUT",
            required={"max_bytes": minimum[0], "max_tokens": minimum[1]},
        )
    return None


def expand_artifact(
    store: TypedArtifactStore,
    *,
    artifact_id: str,
    version: int,
    session_allowlist: Iterable[str] | None = None,
    access: MemoryAccess | None = None,
    mode: Literal["ordinary", "historical"] = "ordinary",
    now: float | None = None,
    offset: int = 0,
    max_tokens: int = DEFAULT_MAX_TOKENS,
    max_bytes: int = DEFAULT_MAX_BYTES,
    encoding: str = DEFAULT_ENCODING,
    representation: Literal["base64", "utf8"] = "base64",
    telemetry: TelemetryStore | Callable[[], TelemetryStore] | None = None,
    request_id: str | None = None,
    event_id: str | None = None,
    invocation_id: str | None = None,
    project_id: str | None = None,
    run_id: str | None = None,
    agent_id: str | None = None,
    session_id: str | None = None,
    opt_in: bool = False,
    cache_write: bool = False,
    frame_bytes: FrameBytes | None = None,
) -> dict[str, Any]:
    """MC02 §9.0 exact expansion: returns a base64-encoded byte slice of one stored artifact
    version, starting at `offset`. Concatenating `content_base64` across pages (following
    `next_offset` until `complete`) reconstructs the stored version's bytes exactly, even
    across a multi-byte UTF-8 character split mid-page.

    72-T02 `representation="utf8"`: each page is `content_utf8`, a slice of the exact
    persisted UTF-8 JSON from one scalar boundary to another, plus `payload_hash` and
    `total_bytes`; joining the slices gives back the exact bytes, whose sha256 is
    `payload_hash`. Offsets are byte offsets in both representations and are never
    clamped: a negative offset, one past the end, or (utf8) one inside a scalar is
    `E_OFFSET`; `offset == total` is an empty, complete page. Caps below the smallest
    `E_BUDGET` envelope are `E_INPUT` with `required`, before any store read; a utf8
    page that cannot carry one scalar is `E_BUDGET` with `required` caps that do.

    72-T02 D32: the version row is labelled by its binding -- `verified` (no key),
    `backfilled`, `unbound` (utf8 `payload_hash` is the stored bytes' sha256, computed
    now) or `mismatch` -- as `integrity`. Ordinary mode never expands a mismatched or
    non-UTF-8 version (`E_NOT_VISIBLE`); historical mode returns its exact bytes with
    `integrity_payload_mismatch`/`integrity_content_corrupt`, and a non-UTF-8 version
    has no utf8 representation (`E_INPUT`, `alternatives: ["base64"]`). D36: a recheck
    the policy now denies is `E_PERMISSION` with its reason, a moved access
    `E_RESTART`. D35: with `frame_bytes` every fit is on the exact transport bytes.

    72-T01: visibility is decided first, through `evaluate_artifact_visibility` on the
    *current* row: a missing, denied, archived, expired, tampered or not-current artifact
    returns `"E_NOT_VISIBLE"` (identical bodies apart from the echoed id, so a caller
    can't distinguish "never existed" from "excluded"), whatever `version` was asked.
    Only then may a visible current row answer `"E_VERSION"` for a since-changed
    `version`. A version row whose `payload_hash` disagrees with its bytes is never
    expanded in ordinary mode.

    `mode="historical"` needs a historical-capable access; it may expand a superseded
    version (`version_superseded`), reports a version payload mismatch as
    `integrity_payload_mismatch`, and adds `"historical": True` and `"reason_codes"`.
    The access is rechecked at entry and after the slice is measured, before telemetry:
    denied is `E_PERMISSION` with its reason, changed is `E_RESTART` (72-T02 D36).

    MC04: passing `telemetry` plus `request_id`/`event_id` records a real successful
    expansion's token cost as an `"expansion"` event; omitted (the default), nothing persists.
    """
    # P69-07 subsection e: see `recall_page()`'s identical rationale.
    real_invocation_id = invocation_id or str(uuid.uuid4())
    requested_offset = offset
    utf8 = representation == "utf8"
    shape = "utf8" if utf8 else "base64"

    def refuse(
        code: str, *, version_: int | None = None, required: Any = None
    ) -> dict[str, Any]:
        return _expand_refusal(
            code,
            artifact_id=artifact_id,
            version=version_,
            offset=requested_offset,
            encoding=encoding,
            representation=shape,
            required=required,
        )

    def denied(code: str = "E_NOT_VISIBLE") -> dict[str, Any]:
        return refuse(code)

    admitted = expand_admission(
        artifact_id=artifact_id,
        version=version,
        offset=offset,
        max_bytes=max_bytes,
        max_tokens=max_tokens,
        encoding=encoding,
        representation=representation,
        mode=mode,
        frame_bytes=frame_bytes,
    )
    if admitted is not None:
        return admitted

    def fit_refusal(page: dict[str, Any]) -> dict[str, Any]:
        return _fit_optional(page, frame_bytes, encoding, max_bytes, max_tokens)

    def recheck_refusal(failure: tuple[str, str]) -> dict[str, Any]:
        code, why = failure
        page = refuse(code)
        if code == "E_PERMISSION":
            page["reason"] = why
        return fit_refusal(page)

    def fits(page: dict[str, Any], size: tuple[int, int]) -> bool:
        if frame_bytes is None:
            return _within(size, max_bytes, max_tokens)
        data = {key: value for key, value in page.items() if key != "code"}
        return _frame_fits(
            frame_bytes, page["code"], data, encoding, max_bytes, max_tokens
        )

    def need_of(page: dict[str, Any], size: tuple[int, int]) -> tuple[int, int]:
        if frame_bytes is None:
            return size
        data = {key: value for key, value in page.items() if key != "code"}
        return _frame_size(frame_bytes, page["code"], data, encoding)

    access, why = _route_access(
        store,
        access,
        session_allowlist,
        operation="expand",
        historical=mode == "historical",
    )
    if access is None:
        if why is not None:
            refusal = denied("E_PERMISSION")
            refusal["reason"] = why
            return fit_refusal(refusal)
        return denied()
    failure = recheck_failure(access)
    if failure is not None:
        return recheck_refusal(failure)
    historical = mode == "historical"
    # R13: the generation the emitted page is checked against.
    generation = store.current_generation()
    row = store.get_current_row(artifact_id)
    if row is None:
        return denied()
    verifier = binding_verifier(store)
    decision = evaluate_artifact_visibility(
        store,
        row,
        access=access,
        mode="historical" if historical else "ordinary",
        now=now,
        verifier=verifier,
    )
    if not decision.visible or not (historical or decision.usable_as_current):
        return denied()
    reasons = set(decision.reason_codes)
    current_version = row["artifact_version"]
    if row["trust_tier"] == "STATED":
        # D41: a STATED row whose current version bytes are not bound is never
        # expanded, in any mode or version.
        current_payload = store.get_version_payload(artifact_id, current_version)
        if (
            current_payload is None
            or verifier.version_bytes(row, current_version, current_payload[0])
            == "unbound"
        ):
            return denied()
    if version != current_version:
        if not historical:
            return refuse("E_VERSION", version_=current_version)
        reasons.add("version_superseded")
    binding = store.get_version_binding(artifact_id, version)
    if binding is None:
        return denied()
    stored_content, stored_digest, digest_origin = binding
    # D41: only a bound row's current version with its exact stored bytes carries
    # current-row authority; unbound STATED bytes are never delivered, other
    # unbound bytes are labelled.
    unbound = verifier.version_bytes(row, version, stored_content) == "unbound"
    binding_label = {"store_binding": "unbound"} if unbound else {}
    # 72-T02 D32: the version row's own bytes and binding label.
    stored_text = _stored_text(stored_content)
    stored_bytes = (
        bytes(stored_content)
        if isinstance(stored_content, (bytes, bytearray))
        else stored_content.encode("utf-8")
    )
    mismatch = stored_digest is not None and (
        stored_text is None or payload_digest(stored_text) != stored_digest
    )
    if mismatch:
        integrity = "mismatch"
    elif stored_digest is None:
        integrity = "unbound"
    elif digest_origin == "backfill":
        integrity = "backfilled"
    else:
        integrity = "verified"
    if stored_text is None or mismatch:
        if not historical:
            return denied()
        if mismatch:
            reasons.add("integrity_payload_mismatch")
        if stored_text is None:
            reasons.add("integrity_content_corrupt")
            if utf8:
                page = refuse("E_INPUT", version_=version)
                page["field"] = "representation"
                page["reason"] = "representation_unavailable"
                page["alternatives"] = ["base64"]
                return fit_refusal(page)
    digest = (
        stored_digest
        if integrity in ("verified", "backfilled") and stored_digest is not None
        else hashlib.sha256(stored_bytes).hexdigest()
    )
    extra: dict[str, Any] = {}
    if historical:
        extra.update(historical=True, reason_codes=sorted(reasons))
    if integrity != "verified":
        extra["integrity"] = integrity
    extra.update(binding_label)

    total = len(stored_bytes)
    if offset > total or (utf8 and not _is_boundary(stored_bytes, offset)):
        page = refuse("E_OFFSET", version_=version)
        if utf8:
            page["total_bytes"] = total
        return fit_refusal(page)

    def budget(need: tuple[int, int]) -> dict[str, Any]:
        """A base64 `E_BUDGET`; `required` only when the content-free page with it
        still fits both caps."""
        required = {"max_bytes": need[0], "max_tokens": need[1]}
        page = refuse("E_BUDGET", version_=version, required=required)
        if frame_bytes is None:
            size = _measure_expand(page, encoding)
            with_required = _within(size, max_bytes, max_tokens)
        else:
            with_required = fits(page, (0, 0))
        return page if with_required else refuse("E_BUDGET", version_=version)

    def base64_page(
        chunk: bytes, next_offset: int | None, complete: bool
    ) -> tuple[dict[str, Any], tuple[int, int]]:
        page = _expand(
            "OK",
            artifact_id=artifact_id,
            version=version,
            offset=offset,
            next_offset=next_offset,
            complete=complete,
            content_base64=base64.b64encode(chunk).decode("ascii"),
            encoding=encoding,
        )
        page.update(extra)
        size = _measure_expand(page, encoding)
        page["tokens"], page["bytes"] = size[1], size[0]
        return page, size

    if utf8:
        result = _expand_utf8_slice(
            stored_bytes,
            artifact_id=artifact_id,
            version=version,
            offset=offset,
            payload_hash=digest,
            max_bytes=max_bytes,
            max_tokens=max_tokens,
            encoding=encoding,
            extra=extra or None,
            frame_bytes=frame_bytes,
        )
        if result["code"] != "OK":
            return result
        size = (result["bytes"], result["tokens"])
    else:
        remaining = stored_bytes[offset:]
        result, size = base64_page(b"", None, True)
        if not fits(result, size):
            return budget(need_of(result, size))
        chunk_len = len(remaining)
        while chunk_len > 0:
            chunk = remaining[:chunk_len]
            next_offset = offset + chunk_len if offset + chunk_len < total else None
            trial_page, trial = base64_page(chunk, next_offset, next_offset is None)
            if fits(trial_page, trial):
                result, size = trial_page, trial
                break
            chunk_len -= max(1, chunk_len // 4)
        else:
            if remaining:
                # Shrank the chunk all the way to nothing without ever fitting the
                # envelope inside both caps: report the one-byte page's size.
                one = 1 + offset
                one_page, one_size = base64_page(
                    remaining[:1], one if one < total else None, one >= total
                )
                return budget(need_of(one_page, one_size))

    failure = recheck_failure(access)
    if failure is not None:
        return recheck_refusal(failure)
    # R13: an ordinary page is emitted only while its row is still current and usable
    # on a fresh reader; a row archived, expired or tampered during fitting restarts.
    if not historical and not _emit_current(
        store, generation, [{"id": artifact_id, "version": version}], access, now
    ):
        return fit_refusal(refuse("E_RESTART"))
    _record_memory_event(
        telemetry,
        "expansion",
        size[1],
        request_id=request_id,
        event_id=event_id,
        invocation_id=real_invocation_id,
        project_id=project_id,
        run_id=run_id,
        agent_id=agent_id,
        session_id=session_id,
        opt_in=opt_in,
        cache_write=cache_write,
        access=access,
        encoding=encoding,
        artifact_version=version,
        offset=offset,
        payload_hash=digest,
    )
    return result


def _expand_utf8_slice(
    data: bytes,
    *,
    artifact_id: str,
    version: int,
    offset: int,
    payload_hash: str,
    max_bytes: int,
    max_tokens: int,
    encoding: str,
    extra: dict[str, Any] | None = None,
    frame_bytes: FrameBytes | None = None,
) -> dict[str, Any]:
    """72-T02: the largest scalar-aligned utf8 page from `offset` within both caps, or
    an `E_BUDGET` page (itself within the caps) whose `required` returns one scalar.
    `extra` (the historical/integrity keys) is part of every measured OK page and of
    `required`. With `frame_bytes` (D35) the caps apply to the framed response."""

    def framed_fits(code: str, page: dict[str, Any]) -> bool:
        assert frame_bytes is not None
        data = {key: value for key, value in page.items() if key != "code"}
        return _frame_fits(frame_bytes, code, data, encoding, max_bytes, max_tokens)

    total = len(data)
    sizes: dict[int, tuple[int, int]] = {}

    def payload_for(end: int) -> dict[str, Any]:
        return {
            **_utf8_payload(
                artifact_id=artifact_id,
                version=version,
                offset=offset,
                next_offset=end if end < total else None,
                complete=end >= total,
                content_utf8=data[offset:end].decode("utf-8"),
                payload_hash=payload_hash,
                total_bytes=total,
                encoding=encoding,
            ),
            **(extra or {}),
        }

    def fits(end: int) -> bool:
        payload = payload_for(end)
        text = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        size_bytes = len(text.encode("utf-8"))
        if frame_bytes is not None:
            size = (size_bytes, _count_tokens(text, encoding))
            if not framed_fits("OK", _utf8_page("OK", payload, size)):
                return False
            sizes[end] = size
            return True
        if size_bytes > max_bytes:
            return False  # over the byte cap: no need to tokenize
        size = (size_bytes, _count_tokens(text, encoding))
        if size[1] > max_tokens:
            return False
        sizes[end] = size
        return True

    if offset == total:
        end: int | None = total if fits(total) else None
    else:
        end = _utf8_slice_end(data, offset, fits)
    if end is not None:
        return _utf8_page("OK", payload_for(end), sizes[end])
    first = offset + 1
    while first < total and not _is_boundary(data, first):
        first += 1
    one_scalar = payload_for(min(first, total))
    need = _measure_utf8(one_scalar, encoding)
    if frame_bytes is not None:
        one_page = _utf8_page("OK", one_scalar, need)
        need = _frame_size(
            frame_bytes,
            "OK",
            {key: value for key, value in one_page.items() if key != "code"},
            encoding,
        )
    refusal = _utf8_payload(
        artifact_id=artifact_id,
        version=version,
        offset=offset,
        next_offset=None,
        complete=False,
        content_utf8=None,
        payload_hash=None,
        total_bytes=None,
        encoding=encoding,
    )
    with_required = {
        **refusal,
        "required": {"max_bytes": need[0], "max_tokens": need[1]},
    }
    size = _measure_utf8(with_required, encoding)
    budget_page = _utf8_page("E_BUDGET", with_required, size)
    if (
        _within(size, max_bytes, max_tokens)
        if frame_bytes is None
        else framed_fits("E_BUDGET", budget_page)
    ):
        return budget_page
    size = _measure_utf8(refusal, encoding)
    budget_page = _utf8_page("E_BUDGET", refusal, size)
    if frame_bytes is not None:
        # B16: the keyless minimum is emitted too, so admission measures its frame.
        frame_bytes("E_BUDGET", {k: v for k, v in budget_page.items() if k != "code"})
    return budget_page


def _valid_vector(vector: Any) -> bool:
    """72-T08: a usable embedding is a nonempty list of non-bool finite numbers with a
    nonzero norm (cached, fresh and query vectors alike)."""
    if not isinstance(vector, list) or not vector:
        return False
    for value in vector:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return False
        if not math.isfinite(value):
            return False
    return any(value != 0 for value in vector)


def _eligible(decision: VisibilityDecision, mode: VisibilityMode) -> bool:
    """72-T08: ordinary reads embed and return only rows usable as current; inspect and
    historical reads every visible row."""
    return decision.usable_as_current if mode == "ordinary" else decision.visible


def _fill_allowed(
    store: TypedArtifactStore,
    access: MemoryAccess,
    fill_access: MemoryAccess | None,
    cache_write: bool,
) -> bool:
    """72-T08 D39: a fresh vector may be persisted only under `cache_write`, on a
    writable store, through a `write`-capable policy access for the same owner or a
    legacy allowlist while the project is still in legacy mode."""
    if not cache_write or fill_access is None:
        return False
    if getattr(store, "_readonly_conn", None) is not None:
        return False
    if access.kind == "policy":
        return (
            fill_access.kind == "policy"
            and "write" in fill_access.required_operations
            and fill_access.owner_scope == access.owner_scope
        )
    return (
        memory_policy_mode(access.project_root, data_root=access.data_root) == "legacy"
    )


def _persist_embeddings(
    store: TypedArtifactStore,
    access: MemoryAccess,
    fill_access: MemoryAccess,
    fresh: dict[str, list[float]],
    rows_by_id: dict[str, Any],
    hashes: dict[str, str],
    embed_config: EmbeddingConfig,
) -> None:
    """72-T08 D39: persist this read's fresh vectors after every endpoint call, under the
    policy lock, only while the fill access still holds. `put_embedding` re-reads each row
    (version, granted source, embedding-text hash) inside its own transaction and runs the
    same recheck before commit. A lock that cannot be taken skips persistence; the read
    itself is unaffected."""
    from rush.memory import authorization

    def commit_check() -> tuple[str, str] | None:
        return recheck_failure(fill_access)

    try:
        with authorization.hold_policy_lock(data_root=fill_access.data_root):
            if access.kind == "policy":
                if recheck_failure(fill_access) is not None:
                    return
            elif (
                memory_policy_mode(access.project_root, data_root=access.data_root)
                != "legacy"
            ):
                return
            for artifact_id, vector in fresh.items():
                row = rows_by_id[artifact_id]
                if not authorization.source_granted(row["source"], fill_access.sources):
                    continue
                try:
                    store.put_embedding(
                        artifact_id=artifact_id,
                        artifact_version=row["artifact_version"],
                        content_hash=hashes[artifact_id],
                        model_digest=embed_config.model_digest,
                        chunking_version=embed_config.chunking_version,
                        vector=vector,
                        write_sources=fill_access.sources,
                        commit_check=commit_check,
                    )
                except MemoryAccessChanged:
                    return
    except OSError:
        return
    except authorization.MemoryPolicyError as exc:
        if (exc.code, exc.reason) != ("E_POLICY_INVALID", "data_root_unavailable"):
            raise


def _unavailable(code: str, embedded_texts: int) -> dict[str, Any]:
    return {
        "available": False,
        "fallback_code": code,
        "reason": FALLBACK_REASONS[code],
        "embedded_texts": embedded_texts,
    }


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
    session_allowlist: Iterable[str] | None = None,
    access: MemoryAccess | None = None,
    embed_config: EmbeddingConfig | None,
    cache_write: bool = False,
    fill_access: MemoryAccess | None = None,
    embed_fn: Callable[
        [EmbeddingConfig, Sequence[str]], list[list[float]]
    ] = embed_chunks,
    scan_limit: int = _VECTOR_SCAN_CAP,
    mode: VisibilityMode = "ordinary",
    now: float | None = None,
    memo: SourceValidationMemo | None = None,
) -> dict[str, Any]:
    """MC12 §6.7 hybrid ranking: fuses MC02's lexical `search_candidates()` ranking with
    cosine similarity over authorized scoped candidates (`TypedArtifactStore.scope_artifacts()`
    -- never lexical-matched, so a candidate with zero shared terms with `query` is still
    eligible) via deterministic reciprocal-rank fusion: `1/(60+lexical_rank) +
    1/(60+vector_rank)`, an absent rank contributing zero, ID-ascending tie-break.

    72-T08 (D39): each scan reads `scan_limit + 1` rows; more than `scan_limit` in either
    sets `candidates_truncated` and only the first `scan_limit` of each are ranked. Only
    rows eligible under `mode` (72-T01 `evaluate_artifact_visibility`) are embedded. A
    cached vector is reused only when it is a valid vector of the query's dimension.
    Missing rows go to `embed_fn` in slices of `MAX_BATCH`, the access rechecked before
    every slice and before the query (no lock is held during endpoint work). Results:

    - `{"available": False, "code": c, "embedded_texts": n}`: the access was revoked
      (`E_PERMISSION`, with `reason` at entry) or changed (`E_RESTART`); nothing persisted.
    - `{"available": False, "fallback_code": c, "reason": text, "embedded_texts": n}`: no
      engine, an unreachable or timed-out engine, or invalid vectors; nothing persisted.
    - `{"available": True, "rows", "candidates_truncated", "embedded_texts", "generation"}`
      where `generation` is the store generation read before the scans.

    `embedded_texts` counts every text submitted to `embed_fn`, a failed call included.
    Fresh vectors are persisted only when `_fill_allowed` holds (`fill_access` defaults to
    a legacy `access` itself), after every endpoint call, through `_persist_embeddings`.
    """
    access, why = _route_access(store, access, session_allowlist)
    if access is None:
        if why is not None:
            return {"available": False, "code": "E_PERMISSION", "reason": why}
        return {
            "available": True,
            "rows": [],
            "candidates_truncated": False,
            "embedded_texts": 0,
            "generation": store.current_generation(),
        }
    if embed_config is None:
        return _unavailable("no_engine_configured", 0)
    if fill_access is None and access.kind == "legacy_allowlist":
        fill_access = access
    generation = store.current_generation()
    allowed_sources = list(access.sources)
    moment = time.time() if now is None else now
    memo = memo or SourceValidationMemo()
    include_archived = mode == "historical"

    lexical_rows = store.search_candidates(
        subject,
        query,
        source_allowlist=allowed_sources,
        scan_limit=scan_limit + 1,
        owner_scope=access.owner_scope,
        now=moment,
        include_archived=include_archived,
    )
    scoped_rows = store.scope_artifacts(
        subject,
        source_allowlist=allowed_sources,
        scan_limit=scan_limit + 1,
        owner_scope=access.owner_scope,
        now=moment,
        include_archived=include_archived,
    )
    capped = len(lexical_rows) > scan_limit or len(scoped_rows) > scan_limit
    lexical_rows = lexical_rows[:scan_limit]
    scoped_rows = scoped_rows[:scan_limit]
    rows_by_id: dict[str, Any] = {}
    verifier = binding_verifier(store)
    for row in [*scoped_rows, *lexical_rows]:
        if row["id"] in rows_by_id:
            continue
        decision = evaluate_artifact_visibility(
            store,
            row,
            access=access,
            mode=mode,
            now=moment,
            memo=memo,
            verifier=verifier,
        )
        if _eligible(decision, mode):
            rows_by_id[row["id"]] = row
    lexical_order = [row["id"] for row in lexical_rows if row["id"] in rows_by_id]
    if not rows_by_id:
        return {
            "available": True,
            "rows": [],
            "candidates_truncated": capped,
            "embedded_texts": 0,
            "generation": generation,
        }

    texts: dict[str, str] = {}
    hashes: dict[str, str] = {}
    for artifact_id, row in rows_by_id.items():
        stored = _stored_text(row["content"])
        if stored is None:
            continue
        try:
            content = json.loads(stored)
        except (TypeError, ValueError, RecursionError):
            continue
        text = embedding_text(content)
        texts[artifact_id] = text
        hashes[artifact_id] = hashlib.sha256(text.encode("utf-8")).hexdigest()

    vectors: dict[str, list[float]] = {}
    missing: list[str] = []
    for artifact_id in texts:
        cached = store.get_embedding(
            artifact_id=artifact_id,
            artifact_version=rows_by_id[artifact_id]["artifact_version"],
            content_hash=hashes[artifact_id],
            model_digest=embed_config.model_digest,
            chunking_version=embed_config.chunking_version,
        )
        if cached is not None and _valid_vector(cached):
            vectors[artifact_id] = cached
        else:
            missing.append(artifact_id)

    embedded = 0
    fresh: dict[str, list[float]] = {}

    def embed_rows(ids: list[str]) -> str | None:
        nonlocal embedded
        for start in range(0, len(ids), MAX_BATCH):
            chunk = ids[start : start + MAX_BATCH]
            failed = _recheck_code(access, "E_PERMISSION")
            if failed is not None:
                return failed
            embedded += len(chunk)
            batch = embed_fn(embed_config, [texts[i] for i in chunk])
            for artifact_id, vector in zip(chunk, batch, strict=True):
                fresh[artifact_id] = vector
        return None

    try:
        failed = embed_rows(missing)
        if failed is None:
            failed = _recheck_code(access, "E_PERMISSION")
        if failed is not None:
            return {"available": False, "code": failed, "embedded_texts": embedded}
        embedded += 1
        (query_vector,) = embed_fn(embed_config, [query])
        if not _valid_vector(query_vector):
            return _unavailable("invalid_vectors", embedded)
        dimension = len(query_vector)
        # A cached vector of another dimension is a cache miss, recomputed here.
        mismatched = [
            aid for aid, vector in vectors.items() if len(vector) != dimension
        ]
        for artifact_id in mismatched:
            del vectors[artifact_id]
        failed = embed_rows(mismatched)
        if failed is not None:
            return {"available": False, "code": failed, "embedded_texts": embedded}
    except EmbeddingEngineTimeout:
        return _unavailable("engine_timeout", embedded)
    except EmbeddingEngineUnavailable:
        return _unavailable("engine_unreachable", embedded)
    except (EmbeddingResponseError, ValueError, TypeError):
        return _unavailable("invalid_vectors", embedded)
    for vector in fresh.values():
        if not _valid_vector(vector) or len(vector) != dimension:
            return _unavailable("invalid_vectors", embedded)
    vectors.update(fresh)

    if fresh and _fill_allowed(store, access, fill_access, cache_write):
        assert fill_access is not None
        _persist_embeddings(
            store, access, fill_access, fresh, rows_by_id, hashes, embed_config
        )

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
        "candidates_truncated": capped,
        "embedded_texts": embedded,
        "generation": generation,
    }


def hybrid_page(
    store: TypedArtifactStore,
    *,
    subject: MemorySubject,
    query: str,
    session_allowlist: Iterable[str] | None = None,
    access: MemoryAccess | None = None,
    embed_config: EmbeddingConfig | None,
    limit: int = DEFAULT_LIMIT,
    max_tokens: int = DEFAULT_MAX_TOKENS,
    max_bytes: int = DEFAULT_MAX_BYTES,
    encoding: str = DEFAULT_ENCODING,
    cursor: str | None = None,
    cache_write: bool = False,
    fill_access: MemoryAccess | None = None,
    mode: VisibilityMode = "ordinary",
    fallback_code: str | None = None,
    embed_fn: Callable[
        [EmbeddingConfig, Sequence[str]], list[list[float]]
    ] = embed_chunks,
    telemetry: TelemetryStore | Callable[[], TelemetryStore] | None = None,
    request_id: str | None = None,
    event_id: str | None = None,
    invocation_id: str | None = None,
    project_id: str | None = None,
    run_id: str | None = None,
    agent_id: str | None = None,
    session_id: str | None = None,
    opt_in: bool = False,
    now: float | None = None,
    frame_bytes: FrameBytes | None = None,
    v2_filters: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """MC12 §6.7 hybrid retrieval page over `hybrid_candidates()`'s RRF-fused ranking.

    72-T08: `hybrid_admission` runs first (caps below the hybrid envelope minimum are
    `E_INPUT` with `required`, before access, store, telemetry or network). A hybrid page
    has no cursor (`next_cursor` is always `None`) and carries `retrieval: "hybrid"`,
    `candidates_truncated`, `incomplete_reason` and `embedded_texts`, all counted in its
    reported size. Items are accepted while the incomplete trial page (labelled
    `candidate_cap`) fits; emission stops on `item_limit` (an eligible row is left),
    `byte_budget` or `token_budget`. `complete` is true only when nothing stopped
    emission and no scan was capped; otherwise `incomplete_reason` names the stop, or
    `candidate_cap`. A first item that fits no page is `E_BUDGET` with the stop reason.

    A hybrid-requested read that cannot rank (a `fallback_code` the caller already
    decided, an empty `query`, a `cursor`, or `hybrid_candidates` reporting no engine, an
    unreachable or timed-out engine, or invalid vectors) is `recall_page` lexically with
    the `_fallback_labels` counted in its size: `OK` becomes `E_EMBEDDING_UNAVAILABLE`,
    `E_BUDGET` and every error code are kept. A revocation or access change during
    embedding is `E_PERMISSION` / `E_RESTART` with zero items.

    Before emission (D39 R17) the access is rechecked and, on one fresh reader, the store
    generation must be unchanged and every item's current row must keep its version and
    stay eligible under `mode`; otherwise `E_RESTART` with zero items.
    """
    refused = hybrid_admission(
        limit=limit,
        max_bytes=max_bytes,
        max_tokens=max_tokens,
        encoding=encoding,
        cursor=cursor,
        frame_bytes=frame_bytes,
    )
    if refused is not None:
        return refused
    access, why = _route_access(store, access, session_allowlist)

    def refusal(page: dict[str, Any]) -> dict[str, Any]:
        return _fit_optional(page, frame_bytes, encoding, max_bytes, max_tokens)

    if access is None:
        if why is not None:
            return refusal(_denied_page(why, encoding))
        labels = _hybrid_labels(False, None, 0)
        size = _measure_page([], None, True, encoding, labels)
        page = _page(
            "OK", complete=True, encoding=encoding, tokens=size[1], bytes_=size[0]
        )
        page.update(labels)
        return page
    failure = recheck_failure(access)
    if failure is not None:
        return refusal(_recheck_page(failure, encoding))
    moment = time.time() if now is None else now
    memo = SourceValidationMemo()

    # P69-07 subsection e: minted once, forwarded to the lexical fallback below so a
    # fallback call never mints a second, different identity for this one logical call.
    real_invocation_id = invocation_id or str(uuid.uuid4())

    if fallback_code is None and cursor is not None:
        fallback_code = "cursor_continuation"
    if fallback_code is None and not query:
        fallback_code = "empty_query"
    embedded = 0
    fused: dict[str, Any] = {}
    if fallback_code is None:
        fused = hybrid_candidates(
            store,
            subject=subject,
            query=query,
            access=access,
            embed_config=embed_config,
            cache_write=cache_write,
            fill_access=fill_access,
            embed_fn=embed_fn,
            mode=mode,
            now=moment,
            memo=memo,
        )
        if "code" in fused:
            return refusal(
                _page(
                    fused["code"],
                    encoding=encoding,
                    reason=access.denial_reason()
                    if fused["code"] == "E_PERMISSION"
                    else None,
                )
            )
        if "fallback_code" in fused:
            fallback_code = fused["fallback_code"]
            embedded = fused["embedded_texts"]
    if fallback_code is not None:
        fallback = recall_page(
            store,
            # 72-T06: a v2 call's lexical fallback pages its own filters.
            subject=subject if v2_filters is None else None,
            query=query,
            access=access,
            limit=limit,
            max_tokens=max_tokens,
            max_bytes=max_bytes,
            encoding=encoding,
            cursor=cursor,
            # The token-economy store is a separate file, so a read-only memory view
            # still records its delivered lexical page.
            telemetry=telemetry,
            request_id=request_id,
            event_id=event_id,
            invocation_id=real_invocation_id,
            project_id=project_id,
            run_id=run_id,
            agent_id=agent_id,
            session_id=session_id,
            opt_in=opt_in,
            cache_write=cache_write,
            now=moment,
            **(v2_filters or {}),
            extra=_fallback_labels(fallback_code, embedded),
        )
        if fallback["code"] == "OK":
            fallback["code"] = "E_EMBEDDING_UNAVAILABLE"
        return fallback

    capped = bool(fused["candidates_truncated"])
    embedded = fused["embedded_texts"]
    trial_labels = _hybrid_labels(capped, "candidate_cap", embedded)
    items: list[dict[str, Any]] = []
    items_bytes = len(
        _page_text([], None, False, encoding, trial_labels).encode("utf-8")
    )
    stop: str | None = None
    blocked: dict[str, Any] | None = None
    verifier = binding_verifier(store)
    contest = _contest_index(
        store, fused["rows"], access, now=moment, memo=memo, verifier=verifier
    )
    for row in fused["rows"]:
        decision = evaluate_artifact_visibility(
            store,
            row,
            access=access,
            mode=mode,
            now=moment,
            memo=memo,
            verifier=verifier,
        )
        if not _eligible(decision, mode):
            continue
        item = _candidate_to_item(
            row, store, access, decision, contest=contest, now=moment, memo=memo
        )
        if item is None:
            continue
        if len(items) >= limit:
            stop = "item_limit"
            break
        if frame_bytes is None:
            fit = _trial_page_bytes(
                items,
                items_bytes,
                item,
                max_bytes=max_bytes,
                max_tokens=max_tokens,
                encoding=encoding,
                extra=trial_labels,
                complete=False,
            )
        else:
            trial_items = [*items, item]
            trial_size = _measure_page(trial_items, None, False, encoding, trial_labels)
            data = _page_data(trial_items, None, False, encoding, trial_size)
            data.update(trial_labels)
            framed = _frame_fits(
                frame_bytes, "OK", data, encoding, max_bytes, max_tokens
            )
            fit = items_bytes if framed else None
        if fit is None:
            trial = _page_text([*items, item], None, False, encoding, trial_labels)
            over_bytes = len(trial.encode("utf-8")) > max_bytes
            stop = "byte_budget" if over_bytes else "token_budget"
            blocked = item
            break
        items.append(item)
        items_bytes = fit

    def emit(page: dict[str, Any]) -> dict[str, Any]:
        """72-T02 R13 / 72-T08 D39 R17: the policy recheck first (a revocation wins over
        drift), then the store generation read before the scans and every item's current
        row on a fresh reader -- never this request's own, possibly immutable, view --
        before a page leaves or telemetry is recorded."""
        failure = recheck_failure(access)
        if failure is not None:
            return refusal(_recheck_page(failure, encoding))
        if not _emit_current(
            store, fused["generation"], page["items"], access, now, mode=mode
        ):
            return _page("E_RESTART", encoding=encoding)
        if page["code"] == "OK" and _records(telemetry, page):
            _record_memory_event(
                telemetry,
                "retrieval",
                page["tokens"],
                request_id=request_id,
                event_id=event_id,
                invocation_id=real_invocation_id,
                project_id=project_id,
                run_id=run_id,
                agent_id=agent_id,
                session_id=session_id,
                opt_in=opt_in,
                cache_write=cache_write,
                access=access,
                encoding=encoding,
            )
        return page

    if not items and blocked is not None and stop is not None:
        stop_labels = _hybrid_labels(capped, stop, embedded)
        need = _measure_page([blocked], None, False, encoding, stop_labels)
        return emit(
            _budget_page(
                encoding,
                need,
                max_bytes,
                max_tokens,
                frame_bytes=frame_bytes,
                labels=stop_labels,
            )
        )

    complete = stop is None and not capped
    reason = stop if stop is not None else ("candidate_cap" if capped else None)
    labels = _hybrid_labels(capped, reason, embedded)
    size = _measure_page(items, None, complete, encoding, labels)
    while items and not _within(size, max_bytes, max_tokens):
        reason = "byte_budget" if size[0] > max_bytes else "token_budget"
        items.pop()
        complete = False
        labels = _hybrid_labels(capped, reason, embedded)
        size = _measure_page(items, None, complete, encoding, labels)
    page = _page(
        "OK",
        items=items,
        next_cursor=None,
        complete=complete,
        encoding=encoding,
        tokens=size[1],
        bytes_=size[0],
    )
    page.update(labels)
    return emit(page)
