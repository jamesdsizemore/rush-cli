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
    EmbeddingConfig,
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
    binding_verifier,
    compute_content_signature,
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
        if not apply:
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
        or (operation == "capsule" and action == "preview_import")
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

    @classmethod
    def legacy(
        cls,
        project_root: Path,
        session_allowlist: Iterable[str] | None,
        *,
        owner_scope: OwnerScope | None = None,
        operation: str = "ask",
        data_root: Path | None = None,
    ) -> MemoryAccess:
        """The legacy explicit-allowlist access. An empty allowlist yields no sources,
        so every route fails closed on it."""
        return cls(
            kind="legacy_allowlist",
            project_root=Path(project_root).resolve(),
            operation=operation,
            sources=tuple(sorted(set(session_allowlist or ()))),
            owner_scope=owner_scope,
            data_root=data_root,
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
    ) -> tuple[MemoryAccess | None, str]:
        """`resolve()` plus the denial reason (`granted` on success)."""
        try:
            required = required_operation_set(
                operation,
                action=action,
                apply=apply,
                historical=historical,
                overlay=overlay,
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
            ),
            "granted",
        )

    def _re_resolve(self) -> tuple[MemoryAccess | None, str]:
        return MemoryAccess._resolve_set(
            self.project_root,
            operation=self.operation,
            required=self.required_operations_order
            or required_operation_set(self.operation),
            owner_scope=self.owner_scope,
            requested_sources=self.requested_sources,
            session_binding=self.session_binding,
            data_root=self.data_root,
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
        return "ok" if fresh == self else "changed"

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
    )
    return access if access is not None else RouteDenial("E_PERMISSION", why)


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
    """§3 step 2 root check. X1: the personal-overlay access (`overlay_read` with the
    overlay owner) reads only the store rooted at `<data_root>/user`; every other
    access needs `access.project_root == store.project_root`."""
    if access.operation == "overlay_read" and access.owner_scope is not None:
        from rush.memory.authorization import (
            MemoryPolicyError,
            user_overlay_owner_scope,
        )

        try:
            overlay = user_overlay_owner_scope(data_root=access.data_root)
        except MemoryPolicyError:
            return False
        if access.owner_scope == overlay:
            return str(store.project_root) == overlay.id
    return access.project_root == store.project_root


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
    try:
        content = json.loads(row["content"])
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
    text = row["content"]
    mismatched = digest is not None and (
        not isinstance(text, str) or payload_digest(text) != digest
    )
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
        and row["trust_tier"] == "STATED"
        and verifier.row(row) == "unbound"
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
    }
    if binding == "unbound":
        reference["store_binding"] = "unbound"
    return reference


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
    reasons = tuple(
        sorted({*blocking, *(r for r in freshness_reasons if r not in informational)})
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
        if not decision.visible or (
            mode == "ordinary" and not decision.usable_as_current
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
    view, _state = TypedArtifactStore.open_readonly_view(project_root)
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
    telemetry: TelemetryStore | None,
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
) -> None:
    """No-op unless a caller opts into real cost accounting by passing `telemetry` plus both
    IDs — existing `recall_page()`/`expand_artifact()` callers that pass none of this see zero
    behavior change. P69-07 subsection e: `invocation_id` identifies this call, never the
    content-derived `request_id` — a caller (`tools/memory.py`, out of this fix's reach)
    passing the same content-derived `request_id` twice for two genuinely distinct calls no
    longer collides, since `invocation_id` is minted per call by `recall_page()`/
    `expand_artifact()`/`hybrid_page()`, not reused from `request_id`.

    M11: `project_id`/`run_id`/`agent_id`/`session_id` are pure caller-supplied attribution
    (never invented from `store.project_root` -- a path is not a registered project UUID).
    Omitted dimensions are left unset here so `TelemetryStore.record_memory_event()`'s own
    `_UNSCOPED` default applies, rather than duplicating that sentinel in two places."""
    if telemetry is None or not request_id or not event_id:
        return
    attribution = {
        key: value
        for key, value in (
            ("project_id", project_id),
            ("run_id", run_id),
            ("agent_id", agent_id),
            ("session_id", session_id),
        )
        if value is not None
    }
    # 72-T01 §3.9: the event records the access it was read under, so policy-mode
    # telemetry readers can scope totals to an owner and its granted sources.
    owner = access.owner_scope if access is not None else None
    telemetry.record_memory_event(
        kind,
        tokens,
        request_id=request_id,
        event_id=event_id,
        invocation_id=invocation_id,
        opt_in=opt_in,
        cache_write=cache_write,
        owner_scope_kind=owner.kind if owner is not None else None,
        owner_scope_id=owner.id if owner is not None else None,
        sources_json=json.dumps(sorted(access.sources)) if access is not None else None,
        **attribution,
    )


def _encoder(encoding: str) -> tiktoken.Encoding:
    return tiktoken.get_encoding(encoding)


def _count_tokens(text: str, encoding: str) -> int:
    return len(_encoder(encoding).encode(text))


_CURSOR_PREFIX = "m2."
# base64url, no padding, of 20 bytes: nonce (4) + sealed scan offset (4) + tag (12).
_CURSOR_BODY_CHARS = 27


def _cursor_binding(
    *,
    namespace: str,
    project_id: str | None,
    worktree_id: str | None,
    owner: tuple[str, str] | None,
    policy_revision: int | None,
    grant_id: str | None,
    subject: str,
    query: str,
    sources: Sequence[str],
) -> bytes:
    """72-T02: the digest a page token is bound to. Any change to the scope, the query or
    the ranking makes every earlier token fail closed (`E_RESTART`)."""
    body = {
        "v": 2,
        "namespace": namespace,
        "project_id": project_id,
        "worktree_id": worktree_id,
        "owner": list(owner) if owner else None,
        "policy_revision": policy_revision,
        "grant_id": grant_id,
        "subject": subject,
        "query": query,
        "sources": sorted(sources),
        "archive_mode": "active",
        "ranking_version": _RANKING_VERSION,
    }
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
    if not cursor.startswith(_CURSOR_PREFIX):
        return None
    body = cursor[len(_CURSOR_PREFIX) :]
    if len(body) != _CURSOR_BODY_CHARS:
        return None
    try:
        raw = base64.urlsafe_b64decode(body + "=")
    except ValueError:
        return None
    if len(raw) != 20 or (
        base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii") != body
    ):
        return None  # rejects variants that change only the 2 unused bits
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
    `related_artifacts()`, which revalidates every neighbor's source and current
    version. 72-T01: a neighbor the shared decision does not deliver as current
    (archived, expired, tampered, another owner, stale) is dropped, never disclosed."""
    # Deferred import: `rush.memory.relations` imports this module's budgets.
    from rush.memory.relations import related_artifacts

    related = related_artifacts(
        store,
        artifact_id=artifact_id,
        version=version,
        session_allowlist=list(access.sources),
    )
    if related["code"] != "OK":
        return []
    kept = []
    for item in related["items"]:
        decision = evaluate_artifact_visibility(
            store,
            store.get_current_row(item["id"]),
            access=access,
            now=now,
            memo=memo,
        )
        if decision.usable_as_current:
            kept.append(item)
    return kept


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
    try:
        content = json.loads(row["content"])
    except (TypeError, ValueError, RecursionError):
        return None
    if not isinstance(content, dict):
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


def _contest_index(
    store: TypedArtifactStore,
    rows: Iterable[Any],
    access: MemoryAccess,
    *,
    now: float | None,
    memo: SourceValidationMemo | None,
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
                    store, peer, access=access, now=now, memo=memo
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
    tokenized."""
    item_text = json.dumps(item, ensure_ascii=False, separators=(",", ":"))
    trial_bytes = items_bytes + len(item_text.encode("utf-8")) + (1 if items else 0)
    reserved_bytes = trial_bytes
    if reserve_cursor is not None:
        reserved_bytes += len(reserve_cursor) + 2 - 4 + 1
    if reserved_bytes > max_tokens or _contains_special_token(item_text, encoding):
        _bytes, trial_tokens = _measure_page(
            [*items, item], reserve_cursor, reserve_cursor is None, encoding
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


def _denied_page(reason: str, encoding: str) -> dict[str, Any]:
    """R1: a route denied outside D1 `legacy` mode: no items, never `complete`."""
    page = _page("E_PERMISSION", encoding=encoding)
    page["reason"] = reason
    return page


def _within(size: tuple[int, int], max_bytes: int, max_tokens: int) -> bool:
    return size[0] <= max_bytes and size[1] <= max_tokens


def _recall_required(
    max_bytes: int, max_tokens: int, encoding: str
) -> dict[str, int] | None:
    """72-T02 admission: the smallest canonical `E_BUDGET` page's size when a cap is
    below it (the caller gets `E_INPUT` with these as `required`), else `None`."""
    min_bytes, min_tokens = _measure_page([], None, False, encoding)
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
) -> dict[str, Any] | None:
    """72-T02 recall admission (contract C05: before any store read or effect): the
    `E_INPUT` page for `limit < 1`, a non-string cursor, an unknown `encoding` or caps
    below the smallest `E_BUDGET` page (with `required`), else `None`."""
    if not isinstance(limit, int) or isinstance(limit, bool) or limit < 1:
        return _page("E_INPUT", encoding=encoding)
    if cursor is not None and not isinstance(cursor, str):
        return _page("E_INPUT", encoding=encoding)
    try:
        _encoder(encoding)
    except (ValueError, TypeError):
        return _page("E_INPUT", encoding=encoding)
    required = _recall_required(max_bytes, max_tokens, encoding)
    if required is not None:
        refused = _page("E_INPUT", encoding=encoding)
        refused["required"] = required
        return refused
    return None


def _budget_page(
    encoding: str, required: tuple[int, int], max_bytes: int, max_tokens: int
) -> dict[str, Any]:
    """72-T02: an `E_BUDGET` page that itself fits both caps. `required` is included
    only when it still fits; otherwise the canonical minimum (admitted) page is sent."""
    extra: dict[str, Any] = {
        "required": {"max_bytes": required[0], "max_tokens": required[1]}
    }
    size = _measure_page([], None, False, encoding, extra)
    if not _within(size, max_bytes, max_tokens):
        extra = {}
        size = _measure_page([], None, False, encoding)
    page = _page("E_BUDGET", encoding=encoding, tokens=size[1], bytes_=size[0])
    page.update(extra)
    return page


def _recheck_code(access: MemoryAccess, denied_code: str) -> str | None:
    """72-T01 recheck: `None` when `access` still holds, else the route's failure code
    (`denied_code` when the policy now denies it, `E_RESTART` when it changed)."""
    status = access.recheck()
    if status == "ok":
        return None
    return denied_code if status == "denied" else "E_RESTART"


def recall_page(
    store: TypedArtifactStore,
    *,
    subject: MemorySubject,
    query: str,
    session_allowlist: Iterable[str] | None = None,
    access: MemoryAccess | None = None,
    limit: int = DEFAULT_LIMIT,
    max_tokens: int = DEFAULT_MAX_TOKENS,
    max_bytes: int = DEFAULT_MAX_BYTES,
    encoding: str = DEFAULT_ENCODING,
    cursor: str | None = None,
    telemetry: TelemetryStore | None = None,
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
    """
    access, why = _route_access(store, access, session_allowlist)
    if access is None:
        if why is not None:
            return _denied_page(why, encoding)
        return _page("OK", complete=True, encoding=encoding)
    refused = recall_admission(
        limit=limit,
        max_bytes=max_bytes,
        max_tokens=max_tokens,
        encoding=encoding,
        cursor=cursor,
    )
    if refused is not None:
        return refused
    failed = _recheck_code(access, "E_PERMISSION")
    if failed is not None:
        return _page(failed, encoding=encoding)
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
        policy_revision=access.policy_revision,
        grant_id=access.grant_id,
        subject=subject,
        query=query,
        sources=allowed_sources,
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
            store, row, access=access, now=moment, memo=memo
        )
        if not decision.usable_as_current:
            return None
        return _candidate_to_item(
            row, store, access, decision, contest=contest, now=moment, memo=memo
        )

    items: list[dict[str, Any]] = []
    base_bytes = _page_bytes([], None, True, encoding)
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
                subject,
                query,
                source_allowlist=allowed_sources,
                scan_offset=position,
                scan_limit=batch_limit,
                owner_scope=access.owner_scope,
                # 72-T02 fix1: no `now=` here. An SQL expiry filter under LIMIT/OFFSET
                # shrinks the rank set when a row expires between pages and skips a
                # row; expiry is decided per row by `evaluate_artifact_visibility`.
            )
            if query
            # 72-T01 R5: an unqueried (compact `list`) page browses the subject's
            # rows in ID order through the same per-row decision.
            else store.scope_artifacts(
                subject,
                source_allowlist=allowed_sources,
                scan_offset=position,
                scan_limit=batch_limit,
                owner_scope=access.owner_scope,
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
            fit = _trial_page_bytes(
                items,
                base_bytes,
                item,
                max_bytes=max_bytes,
                max_tokens=max_tokens,
                encoding=encoding,
                reserve_cursor=token(position),
            )
            if fit is not None:
                items.append(item)
                base_bytes = fit
                last_fit = position
                continue
            final = _trial_page_bytes(
                items,
                base_bytes,
                item,
                max_bytes=max_bytes,
                max_tokens=max_tokens,
                encoding=encoding,
            )
            if final is not None:
                pending = (item, start)
                continue
            blocked = (item, start)
            position, scanned, more = start, scanned - 1, True
            break
        if not more and len(batch) < batch_limit:
            exhausted = True

    def emit(page: dict[str, Any]) -> dict[str, Any]:
        """The snapshot and policy rechecks every page passes before it is returned."""
        if store.current_generation() != generation:
            return _page("E_RESTART", encoding=encoding)
        failed = _recheck_code(access, "E_PERMISSION")
        if failed is not None:
            return _page(failed, encoding=encoding)
        if page["code"] == "OK":
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
            )
        return page

    def ok(
        page_items: list[dict[str, Any]],
        next_cursor: str | None,
        size: tuple[int, int],
    ) -> dict[str, Any]:
        return emit(
            _page(
                "OK",
                items=page_items,
                next_cursor=next_cursor,
                complete=next_cursor is None,
                encoding=encoding,
                tokens=size[1],
                bytes_=size[0],
            )
        )

    stuck = pending or blocked
    if exhausted:
        final_items = [*items, pending[0]] if pending is not None else items
        size = _measure_page(final_items, None, True, encoding)
        if _within(size, max_bytes, max_tokens):
            return ok(final_items, None, size)
        resume = last_fit  # unreachable in practice: fall back to the accepted trial
    else:
        resume = stuck[1] if stuck is not None else position
    if items:
        next_cursor = token(resume)
        size = _measure_page(items, next_cursor, False, encoding)
        if not _within(size, max_bytes, max_tokens) and resume != last_fit:
            next_cursor = token(last_fit)  # identical to the accepted trial page
            size = _measure_page(items, next_cursor, False, encoding)
        return ok(items, next_cursor, size)
    if stuck is not None:
        need = _measure_page([stuck[0]], token(stuck[1] + 1), False, encoding)
        return emit(_budget_page(encoding, need, max_bytes, max_tokens))
    # The scan cap was spent on ineligible rows: an empty continuation page.
    next_cursor = token(resume)
    size = _measure_page([], next_cursor, False, encoding)
    if _within(size, max_bytes, max_tokens):
        return ok([], next_cursor, size)
    return emit(_budget_page(encoding, size, max_bytes, max_tokens))


def _measure_expand(
    chunk: bytes | None, next_offset: int | None, complete: bool, encoding: str
) -> tuple[int, int]:
    """base64 page size. `chunk=None` (72-T02) measures the content-free minimum."""
    payload = {
        "content_base64": None
        if chunk is None
        else base64.b64encode(chunk).decode("ascii"),
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


def expand_admission(
    *,
    artifact_id: str,
    version: int,
    offset: int,
    max_bytes: int,
    max_tokens: int,
    encoding: str,
    representation: str,
) -> dict[str, Any] | None:
    """72-T02 expand admission (contract C05: before any store read or effect): the
    `E_INPUT` page for an unknown representation or `encoding`, `E_OFFSET` for a
    negative offset, `E_INPUT` with `required` for caps below the smallest envelope,
    else `None`."""

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

    if representation not in ("base64", "utf8"):
        return refuse("E_INPUT")
    if offset < 0:
        return refuse("E_OFFSET", version_=version)
    try:
        _encoder(encoding)
    except (ValueError, TypeError):
        return refuse("E_INPUT")
    if representation == "utf8":
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
        minimum = _measure_expand(None, None, False, encoding)
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
    telemetry: TelemetryStore | None = None,
    request_id: str | None = None,
    event_id: str | None = None,
    invocation_id: str | None = None,
    project_id: str | None = None,
    run_id: str | None = None,
    agent_id: str | None = None,
    session_id: str | None = None,
    opt_in: bool = False,
    cache_write: bool = False,
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
    page that cannot carry one scalar is `E_BUDGET` with `required` caps that do. In
    utf8 mode a version with no `payload_hash` is `E_MIGRATION` and a digest that
    disagrees with the stored bytes is `E_NOT_VISIBLE`, in every mode.

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
    denied is `E_NOT_VISIBLE`, changed is `E_RESTART`.

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

    def budget(need: tuple[int, int]) -> dict[str, Any]:
        """A base64 `E_BUDGET`; `required` only when the content-free page with it
        still fits both caps."""
        required = {"max_bytes": need[0], "max_tokens": need[1]}
        text = json.dumps(
            {
                "content_base64": None,
                "next_offset": None,
                "complete": False,
                "encoding": encoding,
                "required": required,
            },
            ensure_ascii=False,
            separators=(",", ":"),
        )
        size = (len(text.encode("utf-8")), _count_tokens(text, encoding))
        fits = _within(size, max_bytes, max_tokens)
        return refuse("E_BUDGET", version_=version, required=required if fits else None)

    admitted = expand_admission(
        artifact_id=artifact_id,
        version=version,
        offset=offset,
        max_bytes=max_bytes,
        max_tokens=max_tokens,
        encoding=encoding,
        representation=representation,
    )
    if admitted is not None:
        return admitted

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
            return refusal
        return denied()
    failed = _recheck_code(access, "E_NOT_VISIBLE")
    if failed is not None:
        return denied(failed)
    historical = mode == "historical"
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
    payload = store.get_version_payload(artifact_id, version)
    if payload is None:
        return denied()
    stored_text, stored_digest = payload
    # D41: only a bound row's current version with its exact stored bytes carries
    # current-row authority; unbound STATED bytes are never delivered, other
    # unbound bytes are labelled.
    unbound = verifier.version_bytes(row, version, stored_text) == "unbound"
    binding_label = {"store_binding": "unbound"} if unbound else {}
    stored_bytes = stored_text.encode("utf-8")
    if utf8:
        if stored_digest is None:
            return refuse("E_MIGRATION", version_=version)
        if hashlib.sha256(stored_bytes).hexdigest() != stored_digest:
            return denied()
    elif stored_digest is not None and payload_digest(stored_text) != stored_digest:
        if not historical:
            return denied()
        reasons.add("integrity_payload_mismatch")

    total = len(stored_bytes)
    if offset > total or (utf8 and not _is_boundary(stored_bytes, offset)):
        page = refuse("E_OFFSET", version_=version)
        if utf8:
            page["total_bytes"] = total
        return page

    if utf8 and stored_digest is not None:  # a null digest returned E_MIGRATION above
        result = _expand_utf8_slice(
            stored_bytes,
            artifact_id=artifact_id,
            version=version,
            offset=offset,
            payload_hash=stored_digest,
            max_bytes=max_bytes,
            max_tokens=max_tokens,
            encoding=encoding,
            extra=(
                {
                    **(
                        {"historical": True, "reason_codes": sorted(reasons)}
                        if historical
                        else {}
                    ),
                    **binding_label,
                }
                or None
            ),
        )
        if result["code"] != "OK":
            return result
        size = (result["bytes"], result["tokens"])
    else:
        remaining = stored_bytes[offset:]
        chunk = b""
        next_offset: int | None = None
        complete = True
        size = _measure_expand(b"", None, True, encoding)
        if not _within(size, max_bytes, max_tokens):
            return budget(size)
        chunk_len = len(remaining)
        while chunk_len > 0:
            chunk = remaining[:chunk_len]
            next_offset = offset + chunk_len if offset + chunk_len < total else None
            complete = next_offset is None
            trial = _measure_expand(chunk, next_offset, complete, encoding)
            if _within(trial, max_bytes, max_tokens):
                size = trial
                break
            chunk_len -= max(1, chunk_len // 4)
        else:
            if remaining:
                # Shrank the chunk all the way to nothing without ever fitting the
                # envelope inside both caps: report the one-byte page's size.
                one = 1 + offset
                need = _measure_expand(
                    remaining[:1], one if one < total else None, one >= total, encoding
                )
                return budget(need)
        result = _expand(
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

    failed = _recheck_code(access, "E_NOT_VISIBLE")
    if failed is not None:
        return denied(failed)
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
    )
    if historical and not utf8:  # utf8 pages already carry (and measured) them
        result["historical"] = True
        result["reason_codes"] = sorted(reasons)
    if not utf8:
        result.update(binding_label)
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
) -> dict[str, Any]:
    """72-T02: the largest scalar-aligned utf8 page from `offset` within both caps, or
    an `E_BUDGET` page (itself within the caps) whose `required` returns one scalar.
    `extra` (the historical keys) is part of every measured OK page and of `required`."""
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
        text = json.dumps(payload_for(end), ensure_ascii=False, separators=(",", ":"))
        size_bytes = len(text.encode("utf-8"))
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
    need = _measure_utf8(payload_for(min(first, total)), encoding)
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
    if _within(size, max_bytes, max_tokens):
        return _utf8_page("E_BUDGET", with_required, size)
    size = _measure_utf8(refusal, encoding)
    return _utf8_page("E_BUDGET", refusal, size)


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
    session_allowlist: Iterable[str] | None = None,
    access: MemoryAccess | None = None,
    embed_config: EmbeddingConfig | None,
    cache_write: bool = False,
    embed_fn: Callable[
        [EmbeddingConfig, Sequence[str]], list[list[float]]
    ] = embed_chunks,
    scan_limit: int = _VECTOR_SCAN_CAP,
    now: float | None = None,
    memo: SourceValidationMemo | None = None,
) -> dict[str, Any]:
    """MC12 §6.7 hybrid ranking: fuses MC02's lexical `search_candidates()` ranking with
    cosine similarity over authorized scoped candidates (`TypedArtifactStore.scope_artifacts()`
    -- never lexical-matched, so a candidate with zero shared terms with `query` is still
    eligible) via deterministic reciprocal-rank fusion: `1/(60+lexical_rank) +
    1/(60+vector_rank)`, an absent rank contributing zero, ID-ascending tie-break.

    Returns `{"available": False, "reason": ...}` when no engine is configured or it is
    unreachable/invalid -- callers must fall back to a plainly-labelled lexical result, never
    report that as hybrid success. 72-T01: every candidate goes through
    `evaluate_artifact_visibility` (ordinary mode) before any content is embedded, so an
    excluded row never reaches the embedding endpoint. Without `cache_write`, a freshly
    computed vector is used for this call's ranking only and is never persisted
    (`TypedArtifactStore.put_embedding()` is only ever called when `cache_write` is true).

    An `"available": True` result also carries `"candidates_truncated"`: `True` when either
    the lexical or vector-scope scan returned a full `scan_limit` (512) batch, meaning
    unseen candidates beyond the cap were never ranked (§6.7 "report candidate truncation").
    """
    access, why = _route_access(store, access, session_allowlist)
    if access is None:
        if why is not None:
            return {"available": False, "code": "E_PERMISSION", "reason": why}
        return {"available": True, "rows": [], "candidates_truncated": False}
    if embed_config is None:
        return {"available": False, "reason": "no embedding engine configured"}
    allowed_sources = list(access.sources)
    moment = time.time() if now is None else now
    memo = memo or SourceValidationMemo()

    lexical_rows = store.search_candidates(
        subject,
        query,
        source_allowlist=allowed_sources,
        scan_limit=scan_limit,
        owner_scope=access.owner_scope,
        now=moment,
    )
    scoped_rows = store.scope_artifacts(
        subject,
        source_allowlist=allowed_sources,
        scan_limit=scan_limit,
        owner_scope=access.owner_scope,
        now=moment,
    )
    # §6.7 "bound vector candidates to 512 and report candidate truncation": either scan
    # returning a full `scan_limit` batch means unseen rows may exist beyond the cap, mirroring
    # `recall_page()`'s own `scanned >= _SCAN_CAP` cap-hit detection.
    candidates_truncated = (
        len(lexical_rows) >= scan_limit or len(scoped_rows) >= scan_limit
    )
    rows_by_id: dict[str, Any] = {}
    for row in [*scoped_rows, *lexical_rows]:
        if row["id"] in rows_by_id:
            continue
        decision = evaluate_artifact_visibility(
            store, row, access=access, now=moment, memo=memo
        )
        if decision.usable_as_current:
            rows_by_id[row["id"]] = row
    lexical_order = [row["id"] for row in lexical_rows if row["id"] in rows_by_id]
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
        except (TypeError, ValueError, RecursionError):
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
                        commit_check=lambda: recheck_failure(access),
                    )
        (query_vector,) = embed_fn(embed_config, [query])
    except MemoryAccessChanged as exc:
        return {"available": False, "code": exc.code, "reason": exc.reason}
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
    session_allowlist: Iterable[str] | None = None,
    access: MemoryAccess | None = None,
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
    invocation_id: str | None = None,
    project_id: str | None = None,
    run_id: str | None = None,
    agent_id: str | None = None,
    session_id: str | None = None,
    opt_in: bool = False,
    now: float | None = None,
) -> dict[str, Any]:
    """MC12 §6.7 hybrid retrieval page: `hybrid_candidates()`'s RRF-fused ranking, applying
    the same compact-item budget rules `recall_page()` uses. No cursor/continuation in this
    cut -- the candidate pool is already bounded to `_VECTOR_SCAN_CAP` (512); `data.
    candidates_truncated` reports when that bound actually clipped the scan (§6.7 "report
    candidate truncation") instead of silently treating the capped pool as exhaustive.
    # ponytail: no hybrid pagination; add a cursor if a real workload needs paging past one
    # page of a 512-candidate pool.

    72-T01: the same access rules as `recall_page()` (mutually exclusive `access` and
    `session_allowlist`, entry and pre-telemetry rechecks); only rows usable as current
    are embedded or returned.

    Falls back to a plainly-labelled lexical page (`code: "E_EMBEDDING_UNAVAILABLE"`,
    `retrieval: "lexical"`, `embedding_status: "skipped"`, plus `hybrid_unavailable_reason`)
    when no engine is configured or it is unreachable/invalid -- never reports that as hybrid
    success (§9.0 fixed contract).
    """
    access, why = _route_access(store, access, session_allowlist)
    if access is None:
        if why is not None:
            page = _denied_page(why, encoding)
            page["retrieval"] = "hybrid"
            return page
        page = _page("OK", complete=True, encoding=encoding)
        page["retrieval"] = "hybrid"
        page["candidates_truncated"] = False
        return page
    failed = _recheck_code(access, "E_PERMISSION")
    if failed is not None:
        return _page(failed, encoding=encoding)
    moment = time.time() if now is None else now
    memo = SourceValidationMemo()

    # P69-07 subsection e: minted once, forwarded to the lexical fallback below so a
    # fallback call never mints a second, different identity for this one logical call.
    real_invocation_id = invocation_id or str(uuid.uuid4())

    fused = hybrid_candidates(
        store,
        subject=subject,
        query=query,
        access=access,
        embed_config=embed_config,
        cache_write=cache_write,
        embed_fn=embed_fn,
        now=moment,
        memo=memo,
    )
    if not fused["available"]:
        fallback = recall_page(
            store,
            subject=subject,
            query=query,
            access=access,
            limit=limit,
            max_tokens=max_tokens,
            max_bytes=max_bytes,
            encoding=encoding,
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
        )
        if fallback["code"] in ("E_PERMISSION", "E_RESTART"):
            return fallback
        fallback["code"] = "E_EMBEDDING_UNAVAILABLE"
        fallback["retrieval"] = "lexical"
        fallback["embedding_status"] = "skipped"
        fallback["hybrid_unavailable_reason"] = fused["reason"]
        return fallback

    items: list[dict[str, Any]] = []
    items_bytes, _tokens = _measure_page([], None, True, encoding)
    contest = _contest_index(store, fused["rows"], access, now=moment, memo=memo)
    for row in fused["rows"]:
        decision = evaluate_artifact_visibility(
            store, row, access=access, now=moment, memo=memo
        )
        if not decision.usable_as_current:
            continue
        item = _candidate_to_item(
            row, store, access, decision, contest=contest, now=moment, memo=memo
        )
        if item is None:
            continue
        trial_bytes = _trial_page_bytes(
            items,
            items_bytes,
            item,
            max_bytes=max_bytes,
            max_tokens=max_tokens,
            encoding=encoding,
        )
        if trial_bytes is None:
            break
        items.append(item)
        items_bytes = trial_bytes
        if len(items) >= limit:
            break

    size_bytes, size_tokens = _measure_page(items, None, True, encoding)
    failed = _recheck_code(access, "E_PERMISSION")
    if failed is not None:
        return _page(failed, encoding=encoding)
    _record_memory_event(
        telemetry,
        "retrieval",
        size_tokens,
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
