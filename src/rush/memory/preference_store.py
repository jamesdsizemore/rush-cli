"""User and agent preference store persisting to .rush/preferences.json.

72-T05: besides the compatibility map (`get`/`set`/`delete`/`list_all`), a
`PreferenceStore` resolves, records, corrects and ends consented layered preferences:
project and task rules live in the project's own `memory.db`, personal rules in the
separate user overlay store (`<data_root>/user`), each read and written only under the
access the caller resolved for that layer. Every refusal is a `PreferenceError`.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import math
import os
import re
import threading
import time
import unicodedata
import uuid
from collections.abc import Iterator, Mapping
from pathlib import Path
from typing import TYPE_CHECKING, Any

from rush.hook.trojan_source import BIDI_CHARS
from rush.memory.migration import (
    PreferenceError,
    read_origin,
    read_origin_kind,
    read_origin_readonly,
    replace_origin_content,
)
from rush.memory.store import TypedArtifactStore, VersionBinding
from rush.memory.transactions import CASMapTransaction

if TYPE_CHECKING:
    import sqlite3

    from rush.memory.retrieval import MemoryAccess, VisibilityDecision

__all__ = [
    "PreferenceError",
    "PreferenceStore",
    "get_preference_readonly",
    "resume_preference_publications",
]

MIGRATION_SOURCE = "migration:preference_store"
_SCOPES = ("personal", "project", "task")
_AUTHORITIES = ("explicit", "inferred")
_LAYERS = ("project", "personal")
_KINDS = ("correct", "reject", "supersede")
_SCOPE_RANK = {"task": 0, "project": 1, "personal": 2}
# Reasons a resolve row may carry and still be classified (brief 3.4 item 4).
_CLASSIFIABLE = frozenset(
    {
        "applicability_rejected",
        "applicability_pending",
        "applicability_superseded",
        "task_mismatch",
    }
)
_SCAN = 512
_PUBLICATION_PREFIX = "preference-publication:"


class _Missing:
    """`PreferenceStore.correct`'s "no value given" sentinel."""

    def __repr__(self) -> str:
        return "<missing>"


_MISSING: Any = _Missing()


# --- input predicates ---------------------------------------------------------


def _clean_text(value: Any) -> bool:
    """A non-empty str with no Cc/Cf character and no lone surrogate."""
    return (
        isinstance(value, str)
        and bool(value)
        and all(unicodedata.category(ch) not in ("Cc", "Cf", "Cs") for ch in value)
    )


def _value_ok(value: Any) -> bool:
    """JSON-serializable without NaN/Infinity; no nested str holds a NUL, a lone
    surrogate or a bidirectional control character."""
    try:
        json.dumps(value, allow_nan=False)
    except (TypeError, ValueError, RecursionError):
        return False
    pending: list[Any] = [value]
    while pending:
        item = pending.pop()
        if isinstance(item, str):
            if "\x00" in item or any(
                unicodedata.category(ch) == "Cs" or ch in BIDI_CHARS for ch in item
            ):
                return False
        elif isinstance(item, Mapping):
            pending.extend(item.keys())
            pending.extend(item.values())
        elif isinstance(item, (list, tuple)):
            pending.extend(item)
    return True


def _strict_version(value: Any) -> bool:
    from rush.memory.store import sqlite_integer_in_range

    return type(value) is int and sqlite_integer_in_range(value)


def _member(value: Any, allowed: tuple[str, ...]) -> bool:
    """Type check before membership: an unhashable value is never a member."""
    return isinstance(value, str) and value in allowed


def _canon(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _is_overlay(access: MemoryAccess | None) -> bool:
    """The access is a policy access for the personal-overlay owner (D25)."""
    if access is None or access.kind != "policy":
        return False
    from rush.memory.authorization import MemoryPolicyError, user_overlay_owner_scope

    try:
        return access.owner_scope == user_overlay_owner_scope(
            data_root=access.data_root
        )
    except MemoryPolicyError:
        return False


def _require_policy(access: MemoryAccess) -> None:
    if access.kind != "policy":
        raise PreferenceError("E_PERMISSION", "policy_grant_required")


def _view_error(state: str) -> PreferenceError:
    if state == "migration_required":
        return PreferenceError("E_MIGRATION", "migration_required")
    return PreferenceError(
        "E_UNAVAILABLE", "store_busy" if state == "busy" else "store_corrupt"
    )


def _open_view(root: Path) -> TypedArtifactStore | None:
    """The non-creating read view of `root`'s store (`None`: no store yet)."""
    view, state = TypedArtifactStore.open_readonly_view(root)
    if state is not None:
        raise _view_error(state)
    return view


def _store_absent(root: Path) -> bool:
    """No store exists at `root` (a store in any other state is not absent)."""
    view, state = TypedArtifactStore.open_readonly_view(root)
    if view is not None:
        view.close()
    return view is None and state is None


@contextlib.contextmanager
def _policy_lock(data_root: Path | None) -> Iterator[None]:
    """Lock order 2: the policy writer lock (`E_PERMISSION lock_unavailable`)."""
    from rush.memory.authorization import MemoryPolicyError, hold_policy_lock

    with contextlib.ExitStack() as stack:
        try:
            stack.enter_context(hold_policy_lock(data_root=data_root))
        except (OSError, MemoryPolicyError):
            raise PreferenceError("E_PERMISSION", "lock_unavailable") from None
        yield


def _recheck(access: MemoryAccess) -> None:
    from rush.memory.retrieval import recheck_failure

    failure = recheck_failure(access)
    if failure is not None:
        raise PreferenceError(*failure)


def _parsed(row: Any) -> dict[str, Any]:
    try:
        content = json.loads(row["content"])
    except (TypeError, ValueError):
        return {}
    return content if isinstance(content, dict) else {}


def _row_value(row: Any, name: str) -> Any:
    from rush.memory.store import _row_value as value

    return value(row, name)


def _personal_next_action(reason: str, data_root: Path | None) -> dict[str, Any]:
    from rush.memory.authorization import MemoryPolicyError, user_overlay_owner_scope

    try:
        owner = f"user:{user_overlay_owner_scope(data_root=data_root).id}"
    except MemoryPolicyError:
        owner = "user"
    return {
        "text": (
            f"Personal overlay not applied ({reason}): grant overlay_read and list "
            f"on owner {owner} for this project."
        ),
        "command": None,
    }


def _denied_personal(reason: str, data_root: Path | None) -> dict[str, Any]:
    return {
        "state": "denied",
        "reason": reason,
        "next_action": _personal_next_action(reason, data_root),
    }


# --- the compatibility map's crash-safe publication (D27/§3.9) -----------------


def _committed_publications(project_root: Path) -> list[tuple[str, dict[str, Any]]]:
    from rush.memory.store import (
        MemoryStoreUnreadableError,
        read_sqlite_readonly,
        sqlite_has_table,
    )

    def read(conn: sqlite3.Connection) -> list[tuple[str, dict[str, Any]]]:
        if not sqlite_has_table(conn, "mutation_receipts"):
            return []
        rows = conn.execute(
            "SELECT operation_id, payload FROM mutation_receipts "
            "WHERE operation_id LIKE ? AND json_valid(payload) "
            "AND json_extract(payload, '$.stage') = 'committed' "
            "ORDER BY created_at, operation_id",
            (_PUBLICATION_PREFIX + "%",),
        ).fetchall()
        return [(str(r[0]), json.loads(r[1])) for r in rows]

    try:
        found = read_sqlite_readonly(project_root / ".rush" / "memory.db", read)
    except MemoryStoreUnreadableError:
        raise PreferenceError("E_UNAVAILABLE", "store_unreadable") from None
    return found or []


def _origin_content(project_root: Path, key: str) -> dict[str, Any] | None:
    """The `preference` origin row's content for `key` (`{}` when unparsable), read
    without the policy row filter: it decides which grant a compatibility write
    needs, never what a reader sees. Non-creating; `None` when no row exists."""
    from rush.memory.store import (
        MemoryStoreUnreadableError,
        read_sqlite_readonly,
        sqlite_has_table,
    )

    def read(conn: sqlite3.Connection) -> dict[str, Any] | None:
        if not sqlite_has_table(conn, "memory_artifacts"):
            return None
        row = conn.execute(
            "SELECT content FROM memory_artifacts "
            "WHERE origin_kind = 'preference' AND origin_id = ? LIMIT 1",
            (key,),
        ).fetchone()
        return None if row is None else _parsed(row)

    try:
        return read_sqlite_readonly(project_root / ".rush" / "memory.db", read)
    except MemoryStoreUnreadableError:
        raise PreferenceError("E_UNAVAILABLE", "store_unreadable") from None


def _set_stage(
    store: TypedArtifactStore, operation_id: str, payload: dict[str, Any], stage: str
) -> None:
    """Payload rewrite only; the receipt's `created_at` is kept."""
    with store._connect() as conn:
        conn.execute(
            "UPDATE mutation_receipts SET payload = ? WHERE operation_id = ?",
            (json.dumps({**payload, "stage": stage}), operation_id),
        )
        conn.commit()


def resume_preference_publications(
    project_root: Path, tx: CASMapTransaction | None = None
) -> None:
    """Finish every `committed` set/delete publication, oldest first, under the
    caller's `"preferences:"` lock (Lock 4): an unchanged live map gets the desired
    map; a live map already equal to it is marked published; any other live map is
    an external edit -- the receipt becomes `superseded` and the call raises
    `E_VERSION migration_conflict` with no JSON write. `tx` defaults to the
    project's own `preferences.json` map."""
    pending = _committed_publications(project_root)
    if not pending:
        return
    from rush.memory.transactions import StoreError

    if tx is None:
        tx = CASMapTransaction(
            file_path=Path(project_root) / ".rush" / "preferences.json",
            root_path=Path(project_root),
        )

    store = TypedArtifactStore(project_root)
    for operation_id, payload in pending:
        live = tx.read(allow_missing=True)
        desired = payload.get("desired")
        if (
            live.version == payload.get("old_version")
            and live.content_hash == payload.get("old_digest")
            and isinstance(desired, dict)
        ):
            try:
                tx.write(desired, expected_version=live.version)
            except StoreError:
                raise PreferenceError(
                    "E_UNAVAILABLE", "publication_unconfirmed"
                ) from None
            _set_stage(store, operation_id, payload, "published")
        elif live.data == desired:
            _set_stage(store, operation_id, payload, "published")
        else:
            _set_stage(store, operation_id, payload, "superseded")
            raise PreferenceError("E_VERSION", "migration_conflict")


class PreferenceStore:
    """Manages persistent developer preferences."""

    def __init__(
        self, project_root: Path | None = None, *, data_root: Path | None = None
    ) -> None:
        if data_root is not None and not isinstance(data_root, (str, os.PathLike)):
            raise PreferenceError("E_INPUT", "data_root_invalid")
        try:
            root = (
                Path(project_root).resolve() if project_root else Path.cwd().resolve()
            )
            os.fspath(root).encode("utf-8")
            self.data_root = Path(data_root) if data_root is not None else None
        except (TypeError, ValueError, OSError, RuntimeError, UnicodeError):
            raise PreferenceError("E_INPUT", "project_root_invalid") from None
        self.project_root = root
        self.store_file = self.project_root / ".rush" / "preferences.json"
        # Non-creating: the CAS map (which creates the root) is built on first use.
        self._tx: CASMapTransaction | None = None
        self._tx_lock = threading.Lock()

    @property
    def tx(self) -> CASMapTransaction:
        with self._tx_lock:
            if self._tx is None:
                self._tx = CASMapTransaction(
                    file_path=self.store_file, root_path=self.project_root
                )
            return self._tx

    def _ensure_file(self) -> None:
        self.store_file.parent.mkdir(parents=True, exist_ok=True)

    def _read(self) -> dict[str, Any]:
        return self.tx.read(allow_missing=True).data

    def _write(self, data: dict[str, Any]) -> None:
        def mutator(_old: dict[str, Any]) -> dict[str, Any]:
            return data

        self.tx.update(mutator, max_retries=20)

    @contextlib.contextmanager
    def _prefs_lock(self) -> Iterator[None]:
        """Lock order 4: the `"preferences:"` lock on this project's map (the same
        lock the D27 migration core takes)."""
        from rush.memory.migration import preference_source_lock

        with preference_source_lock(self.project_root):
            yield

    def get(self, key: str, default: Any = None) -> Any:
        data = self._read()
        if key in data:
            return data[key]
        migrated = read_origin(self.project_root, "preference", key)
        if migrated is not None:
            return migrated.get("value", default)
        return default

    # --- compatibility writes (D10) ---------------------------------------------

    def set(self, key: str, value: Any) -> None:
        """D10: `legacy` mode keeps the original JSON write unchanged; `policy` mode
        needs a `{write}` grant (plus source `migration:preference_store` for a
        migrated key); `unavailable` refuses."""
        if self._compat_mode() == "legacy":
            with self._prefs_lock():
                self._ensure_file()

                def mutator(data: dict[str, Any]) -> dict[str, Any]:
                    data[key] = value
                    return data

                self.tx.update(mutator, max_retries=20)
                if read_origin(self.project_root, "preference", key) is not None:
                    self._update_migrated(key, {"key": key, "value": value})
            return
        self._policy_write(key, "set", value)

    def _update_migrated(self, key: str, content: dict[str, Any]) -> None:
        replace_origin_content(
            TypedArtifactStore(self.project_root), "preference", key, content
        )

    def delete(self, key: str) -> bool:
        if self._compat_mode() == "legacy":
            with self._prefs_lock():
                return self._legacy_delete(key)
        return self._policy_write(key, "delete", None)

    def _legacy_delete(self, key: str) -> bool:
        snapshot = self.tx.read(allow_missing=True)
        migrated = read_origin(self.project_root, "preference", key)
        has_migrated = migrated is not None and not migrated.get("deleted", False)
        if key not in snapshot.data and not has_migrated:
            return False

        deleted = False

        def mutator(data: dict[str, Any]) -> dict[str, Any]:
            nonlocal deleted
            if key in data:
                del data[key]
                deleted = True
            return data

        self.tx.update(mutator, max_retries=20)
        if has_migrated:
            # Retain the origin key so replaying the .migrated backup cannot resurrect it.
            self._update_migrated(key, {"deleted": True})
        return deleted or has_migrated

    def _compat_mode(self) -> str:
        from rush.memory.retrieval import memory_policy_decision

        mode, reason = memory_policy_decision(
            self.project_root, data_root=self.data_root
        )
        if mode == "unavailable":
            raise PreferenceError("E_PERMISSION", reason or "policy_invalid")
        return mode

    def _policy_write(self, key: str, action: str, value: Any) -> bool:
        """The D10 policy-mode `set`/`delete`: policy lock -> mode recheck -> origin
        lookup -> `{write}` resolve -> `"preferences:"` lock -> publication resume ->
        one origin transaction (with its publication receipt) -> CAS JSON write."""
        from rush.memory.retrieval import MemoryAccess, memory_policy_decision
        from rush.memory.store import legacy_owner_scope

        with _policy_lock(self.data_root):
            mode, reason = memory_policy_decision(
                self.project_root, data_root=self.data_root
            )
            if mode != "policy":
                raise PreferenceError(
                    "E_PERMISSION",
                    "policy_mode_changed"
                    if mode == "legacy"
                    else reason or "policy_invalid",
                )
            origin = _origin_content(self.project_root, key)
            access, why = MemoryAccess.resolve_with_reason(
                self.project_root,
                operation="write",
                apply=True,
                owner_scope=legacy_owner_scope(self.project_root),
                requested_sources=[MIGRATION_SOURCE] if origin is not None else (),
                data_root=self.data_root,
            )
            if access is None:
                raise PreferenceError("E_PERMISSION", why)
            with self._prefs_lock():
                self._ensure_file()
                resume_preference_publications(self.project_root, self.tx)
                return self._publish(key, action, value, origin, access)

    def _publish(
        self,
        key: str,
        action: str,
        value: Any,
        origin: dict[str, Any] | None,
        access: MemoryAccess,
    ) -> bool:
        from rush.memory.migration import replace_origin_content_tx
        from rush.memory.retrieval import recheck_failure
        from rush.memory.store import note_committed_write
        from rush.memory.transactions import StoreError

        snapshot = self.tx.read(allow_missing=True)
        desired = dict(snapshot.data)
        if action == "set":
            desired[key] = value
            result = True
        else:
            had_json = key in desired
            desired.pop(key, None)
            result = had_json or (origin is not None and not origin.get("deleted"))
            if not result:
                return False
        if origin is None:
            if desired != snapshot.data:

                def mutator(data: dict[str, Any]) -> dict[str, Any]:
                    if action == "set":
                        data[key] = value
                    else:
                        data.pop(key, None)
                    return data

                self.tx.update(mutator, max_retries=20)
            return result
        content: dict[str, Any] = (
            {"key": key, "value": value} if action == "set" else {"deleted": True}
        )
        store = TypedArtifactStore(self.project_root)
        operation_id = (
            _PUBLICATION_PREFIX
            + hashlib.sha256(
                json.dumps(
                    [key, action, desired, snapshot.content_hash], sort_keys=True
                ).encode()
            ).hexdigest()
        )
        payload = {
            "key": key,
            "action": action,
            "old_version": snapshot.version,
            "old_digest": snapshot.content_hash,
            "desired": desired,
            "stage": "committed",
        }
        with store._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                found = conn.execute(
                    "SELECT id, source FROM memory_artifacts "
                    "WHERE origin_kind = 'preference' AND origin_id = ?",
                    (key,),
                ).fetchone()
                version = replace_origin_content_tx(
                    conn, "preference", key, content, project_root=self.project_root
                )
                if version is None or found is None:
                    conn.rollback()
                    if desired != snapshot.data:
                        self.tx.write(desired, expected_version=snapshot.version)
                    return result
                store._write_receipt(
                    conn,
                    operation_id,
                    found["id"],
                    "preference_publication",
                    version,
                    payload,
                )
                failure = recheck_failure(access)
                if failure is not None:
                    raise PreferenceError(*failure)
                conn.commit()
            except BaseException:
                conn.rollback()
                raise
        note_committed_write(found["id"], version, found["source"], "update")
        try:
            self.tx.write(desired, expected_version=snapshot.version)
        except StoreError:
            raise PreferenceError("E_UNAVAILABLE", "publication_unconfirmed") from None
        _set_stage(store, operation_id, payload, "published")
        return result

    def list_all(self) -> dict[str, Any]:
        data = dict(self._read())
        for entry in read_origin_kind(self.project_root, "preference"):
            key = entry.get("key")
            if key is not None and key not in data:
                data[key] = entry.get("value")
        return data

    # --- layered preferences (72-T05) -------------------------------------------

    def resolve(
        self,
        key: str | None = None,
        *,
        access: MemoryAccess | None,
        overlay_access: MemoryAccess | None = None,
        query: str | None = None,
        project_id: str | None = None,
        worktree_id: str | None = None,
        task_id: str | None = None,
        now: float | None = None,
    ) -> dict[str, Any]:
        """Brief 3.4: the applicable value per key across the task, project and
        personal layers. Explicit (user-stated, STATED) rules win over advice;
        among explicit rules the narrowest scope wins (task > project > personal);
        differing explicit rules at the winning scope are `unresolved` unless a
        reviewed `supersedes` edge settles them. Read-only: views only, never the
        compatibility readers, never a writable store."""
        if (key is None) == (query is None):
            raise PreferenceError("E_INPUT", "key_or_query_required")
        if key is not None and not _clean_text(key):
            raise PreferenceError("E_INPUT", "key_invalid")
        terms: list[str] = []
        if query is not None:
            if not isinstance(query, str):
                raise PreferenceError("E_INPUT", "query_invalid")
            terms = list(dict.fromkeys(re.findall(r"[0-9a-z]+", query.lower())))
            if not terms:
                raise PreferenceError("E_INPUT", "query_empty")
        if _is_overlay(access) or (
            overlay_access is not None and not _is_overlay(overlay_access)
        ):
            raise PreferenceError("E_OWNER", "layer_owner_mismatch")
        ref = access if access is not None else overlay_access
        if ref is None:
            raise PreferenceError("E_PERMISSION", "policy_grant_required")
        if ref.kind == "policy":
            if project_id != ref.project_id or worktree_id != ref.worktree_id:
                raise PreferenceError("E_INPUT", "ids_mismatch")
            if task_id != ref.task_id:
                raise PreferenceError("E_INPUT", "task_id_mismatch")
        else:
            if not ref.sources:
                raise PreferenceError("E_PERMISSION", "session_allowlist_required")
            if not _clean_text(project_id) or not _clean_text(worktree_id):
                raise PreferenceError("E_INPUT", "ids_required")
        at = time.time() if now is None else now
        layers: dict[str, Any] = {}
        groups: list[tuple[TypedArtifactStore, MemoryAccess, str]] = []
        views: list[TypedArtifactStore] = []
        try:
            if access is not None:
                view = _open_view(access.storage_root)
                layers["project"] = {
                    "state": "read",
                    "owner_scope": access.owner_scope.as_dict()
                    if access.owner_scope is not None
                    else None,
                }
                if view is not None:
                    views.append(view)
                    groups.append((view, access, "project"))
            else:
                layers["project"] = {
                    "state": "denied",
                    "reason": self._project_denial(ref, task_id),
                }
            if overlay_access is not None:
                overlay_view, state = TypedArtifactStore.open_readonly_view(
                    overlay_access.storage_root
                )
                if state is not None:
                    layers["personal"] = _denied_personal(
                        _view_error(state).reason, overlay_access.data_root
                    )
                else:
                    layers["personal"] = {
                        "state": "read",
                        "reason": None,
                        "next_action": None,
                    }
                    if overlay_view is not None:
                        views.append(overlay_view)
                        groups.append((overlay_view, overlay_access, "personal"))
            else:
                assert access is not None
                layers["personal"] = _denied_personal(
                    self._overlay_denial(access), access.data_root
                )

            def items_for(
                granted: list[tuple[TypedArtifactStore, MemoryAccess, str]],
            ) -> list[dict[str, Any]]:
                return self._resolve_items(
                    granted,
                    key=key,
                    terms=terms,
                    project_id=project_id,
                    worktree_id=worktree_id,
                    task_id=task_id,
                    now=at,
                )

            items = items_for(groups)
            # Recheck every granted layer immediately before emitting anything.
            if access is not None:
                _recheck(access)
            if overlay_access is not None and layers["personal"]["state"] == "read":
                from rush.memory.retrieval import recheck_failure

                failure = recheck_failure(overlay_access)
                if failure is not None:
                    if access is None:
                        raise PreferenceError(*failure)
                    layers["personal"] = _denied_personal(
                        failure[1], overlay_access.data_root
                    )
                    groups = [g for g in groups if g[2] != "personal"]
                    items = items_for(groups)
        finally:
            for opened in views:
                opened.close()
        return {
            "code": "OK",
            "project_id": project_id,
            "worktree_id": worktree_id,
            "task_id": task_id,
            "preferences": items,
            "layers": layers,
        }

    def _project_denial(self, ref: MemoryAccess, task_id: str | None) -> str:
        """The actual project-layer denial when only the overlay layer is granted."""
        from rush.memory.retrieval import MemoryAccess, memory_policy_decision
        from rush.memory.store import legacy_owner_scope

        mode, why = memory_policy_decision(self.project_root, data_root=ref.data_root)
        if mode == "unavailable":
            return why or "policy_invalid"
        found, reason = MemoryAccess.resolve_with_reason(
            self.project_root,
            operation="preference",
            action="resolve",
            owner_scope=legacy_owner_scope(self.project_root),
            data_root=ref.data_root,
            task_id=task_id,
        )
        return reason if found is None else "not_requested"

    def _overlay_denial(self, access: MemoryAccess) -> str:
        """Why the personal layer is not applied when no overlay access was given."""
        if access.kind != "policy":
            return "policy_missing"
        from rush.memory.authorization import (
            MemoryPolicyError,
            user_overlay_owner_scope,
        )
        from rush.memory.retrieval import MemoryAccess

        try:
            owner = user_overlay_owner_scope(data_root=access.data_root)
        except MemoryPolicyError:
            return "data_root_unavailable"
        found, reason = MemoryAccess.resolve_with_reason(
            self.project_root,
            operation="preference",
            action="resolve",
            overlay=True,
            owner_scope=owner,
            data_root=access.data_root,
            task_id=access.task_id,
        )
        return reason if found is None else "not_requested"

    def _resolve_items(
        self,
        groups: list[tuple[TypedArtifactStore, MemoryAccess, str]],
        *,
        key: str | None,
        terms: list[str],
        project_id: str | None,
        worktree_id: str | None,
        task_id: str | None,
        now: float,
    ) -> list[dict[str, Any]]:
        from rush.memory.retrieval import evaluate_artifact_visibility

        def decide(
            view: TypedArtifactStore, acc: MemoryAccess, row: Any
        ) -> VisibilityDecision:
            return evaluate_artifact_visibility(
                view, row, access=acc, mode="inspect", now=now
            )

        keys: set[str] = set()
        if key is not None:
            keys.add(key)
        else:
            for view, acc, _storage in groups:
                for term in terms:
                    for row in view.search_candidates(
                        "preference",
                        term,
                        source_allowlist=acc.sources,
                        owner_scope=acc.owner_scope,
                        scan_limit=_SCAN,
                    ):
                        found = _parsed(row).get("key")
                        if isinstance(found, str) and decide(view, acc, row).visible:
                            keys.add(found)
        rows: dict[str, list[dict[str, Any]]] = {k: [] for k in keys}
        for view, acc, storage in groups:
            offset = 0
            while True:
                batch = view.scope_artifacts(
                    "preference",
                    source_allowlist=acc.sources,
                    owner_scope=acc.owner_scope,
                    scan_limit=_SCAN,
                    scan_offset=offset,
                )
                for row in batch:
                    content = _parsed(row)
                    row_key = content.get("key")
                    if not isinstance(row_key, str) or row_key not in rows:
                        continue
                    entry = self._classify(
                        view,
                        row,
                        content,
                        decide(view, acc, row),
                        storage,
                        project_id=project_id,
                        worktree_id=worktree_id,
                        task_id=task_id,
                    )
                    if entry is not None:
                        rows[row_key].append(entry)
                if len(batch) < _SCAN:
                    break
                offset += _SCAN
        # A requested `key` always gets its entry (`status "none"` with no applicable
        # row); a `query` lists only the keys it found rows for.
        return [
            self._select(row_key, rows[row_key])
            for row_key in sorted(rows)
            if rows[row_key] or key is not None
        ]

    @staticmethod
    def _classify(
        view: TypedArtifactStore,
        row: Any,
        content: dict[str, Any],
        decision: VisibilityDecision,
        storage: str,
        *,
        project_id: str | None,
        worktree_id: str | None,
        task_id: str | None,
    ) -> dict[str, Any] | None:
        """One row's scope match and class (brief 3.4 items 4-6), or `None`."""
        if not (
            decision.visible
            and set(decision.reason_codes) <= _CLASSIFIABLE
            and decision.freshness in ("current", "not_applicable")
        ):
            return None
        stated_scope = content.get("scope")
        if storage == "personal":
            if stated_scope != "personal":
                return None
            scope = "personal"
        elif stated_scope == "task":
            binding = (
                _row_value(row, "task_project_id"),
                _row_value(row, "task_worktree_id"),
                _row_value(row, "task_id"),
            )
            if None in (project_id, worktree_id, task_id) or binding != (
                project_id,
                worktree_id,
                task_id,
            ):
                return None
            scope = "task"
        elif stated_scope == "project":
            if content.get("project_id") != project_id:
                return None
            scope = "project"
        elif stated_scope is None:
            scope = "project"  # a compatibility (migrated) row of this project's store
        else:
            return None
        applicability = _row_value(row, "applicability")
        authority = content.get("authority")
        if applicability == "superseded":
            cls = "superseded"
        elif applicability == "rejected":
            cls = "contrary"
        elif applicability == "pending":
            cls = "pending"
        elif (
            applicability == "active"
            and authority == "explicit"
            and row["trust_tier"] == "STATED"
        ):
            cls = "explicit"
        else:
            cls = "advice"
        return {
            "view": view,
            "cls": cls,
            "rank": _SCOPE_RANK[scope],
            "ref": {
                "artifact_id": row["id"],
                "artifact_version": row["artifact_version"],
                "scope": scope,
                "authority": authority,
                "applicability": applicability,
                "value": content.get("value"),
                "storage": storage,
                "source": row["source"],
            },
        }

    @staticmethod
    def _select(key: str, entries: list[dict[str, Any]]) -> dict[str, Any]:
        """Brief 3.4 items 7-8: selection and the `why` list for one key."""
        from rush.memory.store import sqlite_has_table

        entries = sorted(entries, key=lambda e: (e["rank"], e["ref"]["artifact_id"]))
        decisions: dict[int, str] = {}
        winning: list[dict[str, Any]] = []
        winning_scope: str | None = None
        for scope in ("task", "project", "personal"):
            winning = [
                e
                for e in entries
                if e["cls"] == "explicit" and e["ref"]["scope"] == scope
            ]
            if winning:
                winning_scope = scope
                break
        status = "none"
        selected: dict[str, Any] | None = None
        applied: list[dict[str, Any]] = []
        unresolved: list[dict[str, Any]] = []

        def superseded_by(winner: dict[str, Any], other: dict[str, Any]) -> bool:
            if winner["view"] is not other["view"]:
                return False
            conn = winner["view"]._connect()
            if not sqlite_has_table(conn, "memory_relations"):
                return False
            return (
                conn.execute(
                    "SELECT 1 FROM memory_relations WHERE source_id = ? AND "
                    "target_id = ? AND kind = 'supersedes' AND target_version = ? "
                    "LIMIT 1",
                    (
                        winner["ref"]["artifact_id"],
                        other["ref"]["artifact_id"],
                        other["ref"]["artifact_version"],
                    ),
                ).fetchone()
                is not None
            )

        if winning:
            values = {_canon(e["ref"]["value"]) for e in winning}
            if len(values) == 1:
                status, selected, applied = "applied", winning[0], winning
            else:
                winners = [
                    r
                    for r in winning
                    if all(
                        superseded_by(r, o)
                        for o in winning
                        if _canon(o["ref"]["value"]) != _canon(r["ref"]["value"])
                    )
                ]
                if len(winners) == 1:
                    status, selected = "applied", winners[0]
                    chosen = _canon(selected["ref"]["value"])
                    applied = [
                        e for e in winning if _canon(e["ref"]["value"]) == chosen
                    ]
                    for e in winning:
                        if _canon(e["ref"]["value"]) != chosen:
                            decisions[id(e)] = "superseded_by_edge"
                else:
                    status, unresolved = "unresolved", winning
                    for e in winning:
                        decisions[id(e)] = "conflict_unresolved"
        for e in applied:
            decisions[id(e)] = "selected" if e is selected else "applied"
        for e in entries:
            if id(e) in decisions:
                continue
            authority = e["ref"]["authority"]
            decisions[id(e)] = {
                "explicit": f"shadowed_by_{winning_scope}",
                "contrary": "rejected_contrary",
                "pending": "pending_review",
                "superseded": "superseded",
                "advice": "advice_inferred"
                if authority == "inferred"
                else "advice_not_explicit",
            }[e["cls"]]
        return {
            "key": key,
            "status": status,
            "selected": selected["ref"] if selected is not None else None,
            "applied_refs": [e["ref"] for e in applied],
            "unresolved": [e["ref"] for e in unresolved],
            "advice": [e["ref"] for e in entries if e["cls"] == "advice"],
            "pending": [e["ref"] for e in entries if e["cls"] == "pending"],
            "contrary": [e["ref"] for e in entries if e["cls"] == "contrary"],
            "why": [
                {
                    "artifact_id": e["ref"]["artifact_id"],
                    "artifact_version": e["ref"]["artifact_version"],
                    "decision": decisions[id(e)],
                }
                for e in entries
            ],
        }

    def record(
        self,
        key: str,
        value: Any,
        *,
        access: MemoryAccess,
        apply: bool = False,
        cache_write: bool = False,
        scope: str,
        authority: str,
        task_id: str | None = None,
        expires_at: float | None = None,
        user_stated: bool = False,
        attribution: str | None = None,
    ) -> dict[str, Any]:
        """Brief 3.5: record one preference rule. `explicit` authority needs the
        user's word (`user_stated`) and is promoted to STATED in the same
        transaction; `personal` scope is explicit-only and writes only the overlay
        store under the overlay-owner access."""
        if not _member(scope, _SCOPES):
            raise PreferenceError("E_INPUT", "scope_invalid")
        if authority == "imported_unverified":
            raise PreferenceError("E_INPUT", "authority_import_only")
        if not _member(authority, _AUTHORITIES):
            raise PreferenceError("E_INPUT", "authority_invalid")
        _require_policy(access)
        if (scope == "personal") != _is_overlay(access):
            raise PreferenceError("E_OWNER", "layer_owner_mismatch")
        if (scope == "task") != (task_id is not None) or (
            scope == "task" and task_id != access.task_id
        ):
            raise PreferenceError("E_INPUT", "task_id_mismatch")
        if apply and not cache_write:
            raise PreferenceError("E_PERMISSION", "cache_write_required")
        if apply and authority == "explicit" and not user_stated:
            raise PreferenceError("E_PERMISSION", "user_stated_required")
        if not _clean_text(key):
            raise PreferenceError("E_INPUT", "key_invalid")
        if not _value_ok(value):
            raise PreferenceError("E_INPUT", "value_invalid")
        if scope == "personal" and authority != "explicit":
            raise PreferenceError("E_INPUT", "personal_requires_explicit")
        if expires_at is not None and not (
            type(expires_at) in (int, float)
            and math.isfinite(expires_at)
            and expires_at > time.time()
        ):
            raise PreferenceError("E_INPUT", "expires_at_invalid")
        if attribution is not None and not (
            isinstance(attribution, str)
            and all(
                unicodedata.category(ch) not in ("Cc", "Cf", "Cs") for ch in attribution
            )
        ):
            raise PreferenceError("E_INPUT", "attribution_invalid")
        if len(access.sources) != 1:
            raise PreferenceError("E_INPUT", "source_required")
        source = access.sources[0]
        scoped = scope != "personal"
        content = {
            "key": key,
            "value": value,
            "scope": scope,
            "authority": authority,
            "applicability": "active",
            "project_id": access.project_id if scoped else None,
            "worktree_id": access.worktree_id if scoped else None,
            "task_id": task_id if scope == "task" else None,
            "expires_at": expires_at,
            "source": source,
            "correction_refs": [],
            "attribution": attribution,
        }
        storage = "personal" if scope == "personal" else "project"
        explicit = authority == "explicit"
        if not apply:
            view = _open_view(access.storage_root)
            if view is not None:
                view.close()
            return {
                "applied": False,
                "record": content,
                "storage": storage,
                "artifact_version_after": 2 if explicit else 1,
            }
        return self._record_apply(access, content, source, storage, explicit)

    def _record_apply(
        self,
        access: MemoryAccess,
        content: dict[str, Any],
        source: str,
        storage: str,
        explicit: bool,
    ) -> dict[str, Any]:
        from rush.memory import store as store_module
        from rush.memory.store import MemoryArtifact, note_committed_write
        from rush.memory.trust import default_entry_tier

        task = content["scope"] == "task"
        artifact = MemoryArtifact(
            id=str(uuid.uuid4()),
            family="memory",
            subject="preference",
            trust_tier=default_entry_tier("human_derived"),
            content=content,
            source=source,
            created_at=time.time(),
            owner_scope=access.owner_scope,
            applicability="active",
            task_project_id=access.project_id if task else None,
            task_worktree_id=access.worktree_id if task else None,
            task_id=content["task_id"] if task else None,
        )
        with _policy_lock(access.data_root):
            _recheck(access)
            store = TypedArtifactStore(access.storage_root)
            versions = [1]
            with store._connect() as conn:
                conn.execute("BEGIN IMMEDIATE")
                try:
                    stored, _evicted = store._prepare_write(conn, artifact)
                    store._insert_row(conn, stored)
                    if content["expires_at"] is not None:
                        conn.execute(
                            "UPDATE memory_artifacts SET expires_at = ? WHERE id = ?",
                            (content["expires_at"], artifact.id),
                        )
                    if explicit:
                        _promoted, decision = store_module.promote_stored_artifact(
                            conn,
                            artifact.id,
                            store=store,
                            access=access,
                            user_stated=True,
                            expected_version=1,
                        )
                        if not decision.promoted:
                            raise PreferenceError(
                                "E_INPUT",
                                str(decision.denial_reason or "promotion_denied"),
                            )
                        versions.append(2)
                    _recheck(access)
                    row = conn.execute(
                        "SELECT artifact_version, trust_tier, corroboration_count "
                        "FROM memory_artifacts WHERE id = ?",
                        (artifact.id,),
                    ).fetchone()
                    conn.commit()
                except BaseException:
                    conn.rollback()
                    raise
        for version in versions:
            note_committed_write(
                artifact.id, version, source, "write" if version == 1 else "update"
            )
        return {
            "applied": True,
            "artifact_id": artifact.id,
            "artifact_version": row["artifact_version"],
            "trust_tier": row["trust_tier"],
            "corroboration_count": row["corroboration_count"],
            "scope": content["scope"],
            "applicability": "active",
            "storage": storage,
        }

    def correct(
        self,
        artifact_id: str,
        *,
        access: MemoryAccess,
        apply: bool = False,
        cache_write: bool = False,
        layer: str,
        kind: str,
        reason: str,
        expected_version: int,
        value: Any = _MISSING,
        user_stated: bool = False,
    ) -> dict[str, Any]:
        """Brief 3.6.1: correct, reject or supersede one preference row of `layer`,
        retaining every original version, the reason and the affected downstream
        refs. Apply runs the shared correction core (`apply_correction`)."""
        return self.correct_with_receipt(
            artifact_id,
            access=access,
            apply=apply,
            cache_write=cache_write,
            layer=layer,
            kind=kind,
            reason=reason,
            expected_version=expected_version,
            value=value,
            user_stated=user_stated,
        )

    def correct_with_receipt(
        self,
        artifact_id: str,
        *,
        access: MemoryAccess,
        apply: bool,
        cache_write: bool,
        layer: str,
        kind: str,
        reason: str,
        expected_version: int,
        value: Any = _MISSING,
        user_stated: bool,
        receipt_operation_id: str | None = None,
    ) -> dict[str, Any]:
        """`correct` plus the request's `receipt_operation_id`, written once inside
        the correction transaction as an `edit` receipt (brief 3.6.2 step 8)."""
        if not _member(layer, _LAYERS):
            raise PreferenceError("E_INPUT", "layer_invalid")
        if not _member(kind, _KINDS):
            raise PreferenceError("E_INPUT", "kind_invalid")
        _require_policy(access)
        if (layer == "personal") != _is_overlay(access):
            raise PreferenceError("E_OWNER", "layer_owner_mismatch")
        if apply and not cache_write:
            raise PreferenceError("E_PERMISSION", "cache_write_required")
        if apply and not user_stated:
            raise PreferenceError("E_PERMISSION", "user_stated_required")
        if not _clean_text(artifact_id):
            raise PreferenceError("E_INPUT", "artifact_id_invalid")
        if kind == "reject" and value is not _MISSING:
            raise PreferenceError("E_INPUT", "value_not_allowed")
        if value is not _MISSING and not _value_ok(value):
            raise PreferenceError("E_INPUT", "value_invalid")
        if not _clean_text(reason):
            raise PreferenceError("E_INPUT", "reason_invalid")
        if not _strict_version(expected_version):
            raise PreferenceError("E_INPUT", "expected_version_invalid")
        if receipt_operation_id is not None and not _clean_text(receipt_operation_id):
            raise PreferenceError("E_INPUT", "receipt_operation_id_invalid")
        if not apply:
            target, replacement, _binding = self._correction_plan(
                access, artifact_id, layer, kind, reason, expected_version, value
            )
            return {
                "applied": False,
                "kind": kind,
                "target": target,
                "replacement": replacement,
            }
        if _store_absent(access.storage_root):
            raise PreferenceError("E_NOT_VISIBLE", "not_visible")
        with _policy_lock(access.data_root):
            _recheck(access)
            # The writable constructor applies the additive migrations first.
            store = TypedArtifactStore(access.storage_root)
            target, replacement, binding = self._correction_plan(
                access, artifact_id, layer, kind, reason, expected_version, value
            )

            def write_receipt(
                conn: sqlite3.Connection, payload: dict[str, Any]
            ) -> None:
                assert receipt_operation_id is not None
                store._write_receipt(
                    conn,
                    receipt_operation_id,
                    payload["artifact_id"],
                    "edit",
                    payload["artifact_version"],
                    payload["result"],
                )

            out = store.apply_correction(
                access=access,
                kind=kind,
                artifact_id=artifact_id,
                expected_version=expected_version,
                target_content=target,
                replacement_content=replacement,
                binding=binding,
                receipt_writer=write_receipt
                if receipt_operation_id is not None
                else None,
            )
        if out["code"] != "OK":
            raise PreferenceError(out["code"], out["reason"])
        return {
            "applied": True,
            "kind": kind,
            **{k: v for k, v in out.items() if k != "code"},
        }

    def _correction_plan(
        self,
        access: MemoryAccess,
        artifact_id: str,
        layer: str,
        kind: str,
        reason: str,
        expected_version: int,
        value: Any,
    ) -> tuple[dict[str, Any], dict[str, Any] | None, VersionBinding]:
        """Brief 3.6.1 content builders over the row read from the storage view:
        `(target content, replacement content or None, the row's task binding)`."""
        from rush.memory.retrieval import evaluate_artifact_visibility

        view = _open_view(access.storage_root)
        if view is None:
            raise PreferenceError("E_NOT_VISIBLE", "not_visible")
        try:
            row = view.get_current_row(artifact_id)
            if (
                row is None
                or not evaluate_artifact_visibility(
                    view, row, access=access, mode="ordinary"
                ).visible
            ):
                raise PreferenceError("E_NOT_VISIBLE", "not_visible")
            if row["artifact_version"] != expected_version:
                raise PreferenceError("E_VERSION", "version_changed")
            if row["subject"] != "preference":
                raise PreferenceError("E_INPUT", "not_a_preference")
            current = _parsed(row)
            affected = self._affected(view, access, artifact_id)
            binding = VersionBinding(
                applicability=None,
                task_project_id=_row_value(row, "task_project_id"),
                task_worktree_id=_row_value(row, "task_worktree_id"),
                task_id=_row_value(row, "task_id"),
            )
        finally:
            view.close()
        ref = {
            "kind": kind,
            "reason": reason,
            "at": time.time(),
            "from_version": expected_version,
            "affected": affected,
        }
        refs = [*(current.get("correction_refs") or []), ref]
        scope0 = current.get("scope") or (
            "personal" if layer == "personal" else "project"
        )
        scoped = scope0 != "personal"

        def confirmed(new_value: Any) -> dict[str, Any]:
            return {
                **current,
                "key": current.get("key"),
                "value": new_value,
                "scope": scope0,
                "authority": "explicit",
                "applicability": "active",
                "project_id": access.project_id if scoped else None,
                "worktree_id": access.worktree_id if scoped else None,
                "task_id": current.get("task_id"),
                "correction_refs": refs,
            }

        new_value = current.get("value") if value is _MISSING else value
        replacement: dict[str, Any] | None = None
        if kind == "correct":
            target = confirmed(new_value)
        elif kind == "reject":
            target = {**current, "applicability": "rejected", "correction_refs": refs}
        else:
            replacement = confirmed(new_value)
            target = {
                **current,
                "applicability": "superseded",
                "correction_refs": refs,
            }
        return target, replacement, binding

    @staticmethod
    def _affected(
        view: TypedArtifactStore, access: MemoryAccess, artifact_id: str
    ) -> list[dict[str, Any]]:
        """B13: the visible sources of the relations whose target is `artifact_id`."""
        from rush.memory.retrieval import evaluate_artifact_visibility
        from rush.memory.store import sqlite_has_table

        conn = view._connect()
        if not sqlite_has_table(conn, "memory_relations"):
            return []
        found: set[tuple[str, int]] = set()
        for source_id, source_version in conn.execute(
            "SELECT source_id, source_version FROM memory_relations WHERE target_id = ?",
            (artifact_id,),
        ).fetchall():
            row = view.get_current_row(source_id)
            if (
                row is not None
                and evaluate_artifact_visibility(
                    view, row, access=access, mode="ordinary"
                ).visible
            ):
                found.add((source_id, source_version))
        return [
            {"artifact_id": source_id, "artifact_version": version}
            for source_id, version in sorted(found)
        ]

    def end_task(
        self,
        *,
        access: MemoryAccess,
        apply: bool = False,
        cache_write: bool = False,
        project_id: str,
        worktree_id: str,
        task_id: str,
        expected_versions: Mapping[str, int],
    ) -> dict[str, Any]:
        """Brief 3.7: explicitly end every task-bound preference of one
        `(project_id, worktree_id, task_id)`; the caller cites the exact set and
        versions it reviewed."""
        _require_policy(access)
        if _is_overlay(access):
            raise PreferenceError("E_OWNER", "layer_owner_mismatch")
        if project_id != access.project_id or worktree_id != access.worktree_id:
            raise PreferenceError("E_INPUT", "ids_mismatch")
        if not _clean_text(task_id):
            raise PreferenceError("E_INPUT", "task_id_invalid")
        if not isinstance(expected_versions, Mapping) or not all(
            _clean_text(k) for k in expected_versions
        ):
            raise PreferenceError("E_INPUT", "expected_versions_invalid")
        if not all(_strict_version(v) for v in expected_versions.values()):
            raise PreferenceError("E_INPUT", "expected_version_invalid")
        if apply and not cache_write:
            raise PreferenceError("E_PERMISSION", "cache_write_required")
        triple = (project_id, worktree_id, task_id)
        if not apply or _store_absent(access.storage_root):
            matching = self._task_rows(access, triple)
            self._check_task_versions(matching, expected_versions)
            return {
                "applied": apply,
                "ended": [
                    {"artifact_id": k, "artifact_version": v}
                    for k, v in sorted(matching.items())
                ],
            }
        from rush.memory.store import _write_version, note_committed_write

        ended: list[dict[str, Any]] = []
        sources: dict[str, str] = {}
        with _policy_lock(access.data_root):
            _recheck(access)
            # The writable constructor applies the additive migrations first.
            store = TypedArtifactStore(access.storage_root)
            matching = self._task_rows(access, triple)
            self._check_task_versions(matching, expected_versions)
            if not matching:
                return {"applied": True, "ended": []}
            with store._connect() as conn:
                conn.execute("BEGIN IMMEDIATE")
                try:
                    for artifact_id in sorted(matching):
                        row = conn.execute(
                            "SELECT * FROM memory_artifacts WHERE id = ?",
                            (artifact_id,),
                        ).fetchone()
                        if (
                            row is None
                            or row["artifact_version"] != matching[artifact_id]
                            or row["expired_at"] is not None
                        ):
                            raise PreferenceError("E_VERSION", "version_changed")
                        version = _write_version(
                            conn,
                            artifact_id,
                            content=_parsed(row),
                            source=row["source"],
                            trust_tier=row["trust_tier"],
                            expected_version=matching[artifact_id],
                        )
                        conn.execute(
                            "UPDATE memory_artifacts SET expired_at = ?, expired_by = ?, "
                            "artifact_version = ? WHERE id = ?",
                            (time.time(), "end_task:" + task_id, version, artifact_id),
                        )
                        sources[artifact_id] = row["source"]
                        ended.append(
                            {"artifact_id": artifact_id, "artifact_version": version}
                        )
                    _recheck(access)
                    conn.commit()
                except BaseException:
                    conn.rollback()
                    raise
        for item in ended:
            note_committed_write(
                item["artifact_id"],
                item["artifact_version"],
                sources[item["artifact_id"]],
                "update",
            )
        return {"applied": True, "ended": ended}

    @staticmethod
    def _check_task_versions(
        matching: dict[str, int], expected_versions: Mapping[str, int]
    ) -> None:
        if set(expected_versions) != set(matching):
            raise PreferenceError("E_VERSION", "task_records_changed")
        if any(expected_versions[k] != v for k, v in matching.items()):
            raise PreferenceError("E_VERSION", "version_changed")

    @staticmethod
    def _task_rows(
        access: MemoryAccess, triple: tuple[str, str, str]
    ) -> dict[str, int]:
        """`{id: artifact_version}` of the live preference rows bound to `triple`
        and visible under `access` (inspect mode)."""
        from rush.memory.retrieval import evaluate_artifact_visibility

        view = _open_view(access.storage_root)
        if view is None:
            return {}
        found: dict[str, int] = {}
        try:
            offset = 0
            while True:
                batch = view.scope_artifacts(
                    "preference",
                    source_allowlist=access.sources,
                    owner_scope=access.owner_scope,
                    scan_limit=_SCAN,
                    scan_offset=offset,
                )
                for row in batch:
                    binding = (
                        _row_value(row, "task_project_id"),
                        _row_value(row, "task_worktree_id"),
                        _row_value(row, "task_id"),
                    )
                    if (
                        binding == triple
                        and row["expired_at"] is None
                        and evaluate_artifact_visibility(
                            view, row, access=access, mode="inspect"
                        ).visible
                    ):
                        found[row["id"]] = row["artifact_version"]
                if len(batch) < _SCAN:
                    break
                offset += _SCAN
        finally:
            view.close()
        return found

    def migrate(
        self,
        *,
        access: MemoryAccess,
        apply: bool = False,
        cache_write: bool = False,
        preview_digest: str | None = None,
    ) -> dict[str, Any]:
        """D27: preview (read-only plan and its digest) or apply the
        `preferences.json` migration (Lock 2 here, then the migration core's
        `"preferences:"` Lock 4)."""
        from rush.memory import migration

        _require_policy(access)
        if _is_overlay(access):
            raise PreferenceError("E_OWNER", "layer_owner_mismatch")
        if apply and not cache_write:
            raise PreferenceError("E_PERMISSION", "cache_write_required")
        if preview_digest is not None and not _clean_text(preview_digest):
            raise PreferenceError("E_INPUT", "preview_digest_invalid")
        if not apply:
            view = _open_view(self.project_root)
            if view is not None:
                view.close()
            plan = migration._preference_migration_plan(self.project_root)
            return {
                "applied": False,
                **plan["preview"],
                "preview_digest": plan["preview_digest"],
            }
        if preview_digest is None:
            raise PreferenceError("E_INPUT", "preview_digest_required")
        # G3: the read-only plan refuses a corrupt source, a changed preview and a
        # conflict before the first lock; the core re-checks all three under Lock 4.
        plan = migration._preference_migration_plan(self.project_root)
        if preview_digest != plan["preview_digest"]:
            raise PreferenceError("E_VERSION", "preview_changed")
        if plan["conflicts"]:
            raise PreferenceError("E_VERSION", "migration_conflict")
        from rush.memory.retrieval import recheck_failure

        with _policy_lock(access.data_root):
            _recheck(access)
            with self._prefs_lock():
                resume_preference_publications(self.project_root)
                return migration._preference_migration_apply(
                    self.project_root,
                    preview_digest=preview_digest,
                    require_digest=True,
                    owner_scope=access.owner_scope,
                    commit_check=lambda: recheck_failure(access),
                )


def get_preference_readonly(project_root: Path, key: str, default: Any = None) -> Any:
    """Non-creating `PreferenceStore.get`: never creates the project root, `.rush/`,
    the preference file, the memory store or its cache, and never migrates an
    existing `memory.db`."""
    root = Path(project_root).resolve()
    source = root / ".rush" / "preferences.json"
    data = (
        CASMapTransaction(file_path=source, root_path=root)
        .read(allow_missing=True)
        .data
        if os.path.lexists(source)
        else {}
    )
    if key in data:
        return data[key]
    migrated = read_origin_readonly(root, "preference", key)
    return migrated.get("value", default) if migrated is not None else default
