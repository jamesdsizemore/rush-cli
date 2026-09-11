"""Cross-tool memory query/write tool used by the CLI and MCP transports (Phase 61 P61.12)."""

from __future__ import annotations

import dataclasses
import time
import uuid
from pathlib import Path
from typing import Any, Literal

from ..memory.consolidation import consolidate_episodes
from ..memory.embeddings import EmbeddingConfig
from ..memory.experience import compare_last_success, prepare_memory
from ..memory.handoff import (
    HandoffError,
    acknowledge_readback,
    prepare_handoff,
    receive_handoff,
)
from ..memory.intent import check_intent, record_intent, supersede_intent
from ..memory.maintenance import MaintenanceTask, run_maintenance_cycle
from ..memory.recipes import record_recipe, record_recipe_outcome, resolve_recipe
from ..memory.relations import add_relation, related_artifacts
from ..memory.retrieval import (
    DEFAULT_ENCODING,
    DEFAULT_MAX_BYTES,
    DEFAULT_MAX_TOKENS,
    expand_artifact,
    hybrid_page,
    recall_page,
)
from ..memory.retrieval import DEFAULT_LIMIT as _COMPACT_DEFAULT_LIMIT
from ..memory.store import (
    MemoryArtifact,
    MemoryFamily,
    MemoryScopeError,
    MemorySubject,
    SignatureMismatchError,
    TrojanSourceFoundError,
    TypedArtifactStore,
    VersionConflictError,
)
from ..memory.trust import default_entry_tier
from ..permissions import ExecutionPermissions, check_permissions
from ..token_economy.telemetry import TelemetryStore
from .base import ToolFn, ToolResult

MemoryOperation = Literal[
    "ask",
    "write",
    "promote",
    "list",
    "recall",
    "maintain",
    "expand",
    "link",
    "related",
    "consolidate",
    "verify_attempt",
    "prepare",
    "resume",
    "intent",
    "recipe",
    "plan_checks",
    "last_success_diagnose",
    "handoff",
    "receive",
    "delete",
    "edit",
    "archive",
]
SourceKind = Literal["local_tool", "cross_tool_handoff", "human_derived"]

VALID_OPERATIONS = {
    "ask",
    "write",
    "promote",
    "list",
    "recall",
    "maintain",
    "expand",
    "link",
    "related",
    "consolidate",
    "verify_attempt",
    "prepare",
    "resume",
    "intent",
    "recipe",
    "plan_checks",
    "last_success_diagnose",
    "handoff",
    "receive",
    "delete",
    "edit",
    "archive",
}
_VERIFY_ATTEMPT_REQUEST_KEYS = {
    "attempt_id",
    "behavior_ids",
    "contract",
    "patch",
    "declared_permissions",
}
_WRITE_PERMISSION = ExecutionPermissions(cache_write=True)
# MC05: maps a `VerifyAttemptOutcome.outcome` onto the outer `ToolResult.status`.
_VERIFY_ATTEMPT_OUTCOME_STATUS: dict[str, str] = {
    "completed": "ok",
    "failed": "fail",
    "unavailable": "skipped",
    "denied": "skipped",
}

# MC02 §9.0 status/code pairs: maps an envelope `code` onto the outer `ToolResult.status`.
_CODE_STATUS: dict[str, str] = {
    "OK": "ok",
    "E_INPUT": "error",
    "E_PERMISSION": "fail",
    "E_NOT_VISIBLE": "fail",
    "E_VERSION": "fail",
    "E_MIGRATION": "warn",
    "E_RESTART": "warn",
    "E_BUDGET": "warn",
    "E_UNAVAILABLE": "warn",
    "E_EMBEDDING_UNAVAILABLE": "warn",
    "UNRESOLVED": "warn",
    "E_SCOPE": "fail",
}
_COMPACT_REQUEST_KEYS = {
    "view",
    "limit",
    "max_tokens",
    "max_bytes",
    "encoding",
    "cursor",
    "retrieval",
    "embedding_endpoint",
    "embedding_model",
    "embedding_model_digest",
    "embedding_chunking_version",
}
_RETRIEVAL_MODES = {"lexical", "hybrid"}
_EXPAND_REQUEST_KEYS = {
    "id",
    "version",
    "offset",
    "max_tokens",
    "max_bytes",
    "encoding",
}
_LINK_REQUEST_KEYS = {
    "source_id",
    "source_version",
    "target_id",
    "target_version",
    "kind",
    "origin_ref",
}
_RELATED_REQUEST_KEYS = {
    "id",
    "version",
    "depth",
    "max_nodes",
    "max_tokens",
    "max_bytes",
    "encoding",
}
_CONSOLIDATE_REQUEST_KEYS = {"symptom"}
_PREPARE_REQUEST_KEYS = {"task", "conditions", "behavior_ids", "query"}
_INTENT_REQUEST_KEYS = {
    "action",
    "intent_id",
    "behavior_id",
    "statement_ref",
    "new_statement_ref",
    "new_behavior_id",
    "source_refs",
    "check_refs",
    "exceptions",
    "expected_version",
    "current_revision",
}
_INTENT_ACTIONS = {"create", "confirm", "supersede", "check"}
_RECIPE_REQUEST_KEYS = {
    "action",
    "recipe_id",
    "purpose",
    "helper_ref",
    "required_symbols",
    "required_dependencies",
    "required_config_digest",
    "checks",
    "exceptions",
    "expected_version",
    "current_dependencies",
    "current_config_digest",
    "recipe_version",
    "patch_hash",
    "verifier_receipt_ref",
}
_RECIPE_ACTIONS = {"record", "resolve", "outcome"}
_PLAN_CHECKS_REQUEST_KEYS = {"changed_targets", "required_checks", "environment"}
_LAST_SUCCESS_DIAGNOSE_REQUEST_KEYS = {"behavior_id", "conditions", "historical"}
_RECEIVE_REQUEST_KEYS = {"session_id", "capability", "cursor", "page_size", "ack"}
_HANDOFF_REQUEST_KEYS = {
    "action",
    "receiver_namespace",
    "receiver_audience",
    "goal",
    "constraints",
    "unresolved_decisions",
    "selected_refs",
    "handoff_id",
}
_HANDOFF_ACTIONS = {"prepare", "dispatch", "status"}
_DELETE_REQUEST_KEYS = {"artifact_ids", "expected_revisions", "scope", "apply"}
_DELETE_MAX_BATCH = 100
_EDIT_REQUEST_KEYS = {"scope", "id", "expected_version", "content", "apply"}
_ARCHIVE_REQUEST_KEYS = {"scope", "id", "expected_version", "apply", "archived"}

# Subject -> family mapping (Phase 61 §6.1): active_context/handoff rows, episodic/experience
# rows, preference/failure/architectural_decision/domain_knowledge/memory rows, skill_pattern/skill rows.
_SUBJECT_FAMILY: dict[str, MemoryFamily] = {
    "active_context": "handoff",
    "episodic": "experience",
    "preference": "memory",
    "failure": "memory",
    "architectural_decision": "memory",
    "domain_knowledge": "memory",
    "skill_pattern": "skill",
}


def _family_for_subject(subject: MemorySubject) -> MemoryFamily:
    return _SUBJECT_FAMILY.get(subject, "memory")


class MemoryTool(ToolFn):
    """Query, write, and promote cross-LLM memory artifacts through one result contract."""

    name = "memory"

    @property
    def mcp_description(self) -> str:
        return (
            "Query, write, or promote a cross-tool memory artifact in the typed artifact "
            "store. Returns {status, findings[], summary}; write/promote/maintain/verify_attempt "
            "require explicit permissions."
        )

    def __call__(
        self,
        path: Path,
        operation: MemoryOperation = "ask",
        subject: MemorySubject | None = None,
        query: str = "",
        session_allowlist: list[str] | None = None,
        content: dict[str, Any] | None = None,
        source: str = "",
        symbol_ref: str | None = None,
        source_kind: SourceKind = "local_tool",
        user_stated: bool = False,
        candidate_sources: list[str] | None = None,
        task: MaintenanceTask | None = None,
        batch_size: int = 500,
        include_archived: bool = False,
        allow_cache_write: bool = False,
        allow_artifact_write: bool = False,
        allow_build: bool = False,
        allow_network: bool = False,
        allow_download: bool = False,
        allow_slow: bool = False,
        allow_browser: bool = False,
        request: dict[str, Any] | None = None,
    ) -> ToolResult:
        return self.run(
            path,
            operation=operation,
            subject=subject,
            query=query,
            session_allowlist=session_allowlist,
            content=content,
            source=source,
            symbol_ref=symbol_ref,
            source_kind=source_kind,
            user_stated=user_stated,
            candidate_sources=candidate_sources,
            task=task,
            batch_size=batch_size,
            include_archived=include_archived,
            permissions=ExecutionPermissions(
                cache_write=allow_cache_write,
                artifact_write=allow_artifact_write,
                build=allow_build,
                network=allow_network,
                download=allow_download,
                slow=allow_slow,
                browser=allow_browser,
            ),
            request=request,
        )

    def run(
        self,
        path: Path,
        *,
        operation: MemoryOperation = "ask",
        subject: MemorySubject | None = None,
        query: str = "",
        session_allowlist: list[str] | None = None,
        content: dict[str, Any] | None = None,
        source: str = "",
        symbol_ref: str | None = None,
        source_kind: SourceKind = "local_tool",
        user_stated: bool = False,
        candidate_sources: list[str] | None = None,
        task: MaintenanceTask | None = None,
        batch_size: int = 500,
        include_archived: bool = False,
        permissions: ExecutionPermissions | None = None,
        request: dict[str, Any] | None = None,
    ) -> ToolResult:
        started = time.monotonic()
        root = Path(path).resolve()
        granted = permissions or ExecutionPermissions()

        if operation not in VALID_OPERATIONS:
            return self._result(
                started,
                "error",
                f"Unsupported memory operation: {operation}.",
                operation=str(operation),
            )

        dispatch_table = {
            "ask": lambda: (
                self._compact_query(
                    started,
                    root,
                    subject,
                    query,
                    session_allowlist,
                    "ask",
                    request,
                    granted,
                )
                if request is not None
                else self._query(
                    started, root, subject, query, session_allowlist, "ask"
                )
            ),
            "recall": lambda: (
                self._compact_query(
                    started,
                    root,
                    subject,
                    query,
                    session_allowlist,
                    "recall",
                    request,
                    granted,
                )
                if request is not None
                else self._query(
                    started, root, subject, query, session_allowlist, "recall"
                )
            ),
            "list": lambda: (
                self._compact_query(
                    started,
                    root,
                    subject,
                    query,
                    session_allowlist,
                    "list",
                    request,
                    granted,
                )
                if request is not None
                else self._query(
                    started,
                    root,
                    subject,
                    query,
                    session_allowlist,
                    "list",
                    include_archived=include_archived,
                )
            ),
            "expand": lambda: self._expand(
                started, root, session_allowlist, request, granted
            ),
            "write": lambda: self._run_write(
                started,
                root,
                subject,
                content,
                source,
                symbol_ref,
                source_kind,
                granted,
            ),
            "promote": lambda: self._run_promote(
                started,
                root,
                subject,
                content,
                source,
                symbol_ref,
                source_kind,
                user_stated,
                candidate_sources,
                granted,
            ),
            "maintain": lambda: self._run_maintain(
                started, root, task, batch_size, granted
            ),
            "link": lambda: self._link(started, root, granted, request),
            "related": lambda: self._related(started, root, session_allowlist, request),
            "consolidate": lambda: self._consolidate(
                started, root, session_allowlist, granted, request
            ),
            "verify_attempt": lambda: self._verify_attempt(
                started, root, granted, request
            ),
            "prepare": lambda: self._prepare(
                started, root, session_allowlist, request, "prepare"
            ),
            "resume": lambda: self._prepare(
                started, root, session_allowlist, request, "resume"
            ),
            "intent": lambda: self._intent(started, root, granted, request),
            "recipe": lambda: self._recipe(started, root, granted, request),
            "plan_checks": lambda: self._plan_checks(started, root, request),
            "last_success_diagnose": lambda: self._last_success_diagnose(
                started, root, request
            ),
            "handoff": lambda: self._handoff(started, root, granted, request),
            "receive": lambda: self._receive(started, root, request),
            "delete": lambda: self._run_delete(started, root, granted, request),
            "edit": lambda: self._run_edit(started, root, granted, request),
            "archive": lambda: self._run_archive(started, root, granted, request),
        }
        return dispatch_table[operation]()

    def _query(
        self,
        started: float,
        root: Path,
        subject: MemorySubject | None,
        query: str,
        session_allowlist: list[str] | None,
        operation: str,
        *,
        include_archived: bool = False,
    ) -> ToolResult:
        if not subject or not query:
            return self._result(
                started,
                "error",
                f"memory {operation} requires subject and query.",
                operation=operation,
            )
        if not session_allowlist:
            return self._result(
                started,
                "skipped",
                f"memory {operation} requires a non-empty session_allowlist "
                "(fail-closed, no default cross-session access).",
                operation=operation,
            )
        store = TypedArtifactStore(root)
        try:
            artifacts = store.recall(
                subject, query, session_allowlist, include_archived=include_archived
            )
        except (SignatureMismatchError, TrojanSourceFoundError) as exc:
            return self._result(started, "error", str(exc), operation=operation)
        return self._result(
            started,
            "ok",
            f"Found {len(artifacts)} memory artifact(s) for '{query}'.",
            operation=operation,
            raw=[self._artifact_dict(a) for a in artifacts],
        )

    def _compact_query(
        self,
        started: float,
        root: Path,
        subject: MemorySubject | None,
        query: str,
        session_allowlist: list[str] | None,
        operation: str,
        request: dict[str, Any],
        granted: ExecutionPermissions,
    ) -> ToolResult:
        """MC02 §9.0 bounded `view=compact` mode for `ask`/`recall`/`list`. Only reachable
        when a caller passes `request` — legacy calls (`request=None`) always take `_query()`
        above, unchanged.

        MC04: records a real `"retrieval"` telemetry event via `recall_page()`'s
        `telemetry`/`request_id`/`event_id`/`cache_write` kwargs, gated on `granted
        .cache_write` (mirrors `continuity/context.py`'s existing gate) so a plain read
        never touches `TelemetryStore` at all.
        """
        unknown = set(request) - _COMPACT_REQUEST_KEYS
        if unknown:
            return self._envelope_result(
                started,
                operation,
                "E_INPUT",
                {"message": f"unknown request field(s): {sorted(unknown)}"},
            )
        if request.get("view") != "compact":
            return self._envelope_result(
                started,
                operation,
                "E_INPUT",
                {"message": "request.view must be 'compact'"},
            )
        requires_query = operation in ("ask", "recall")
        if not subject or (requires_query and not query):
            return self._envelope_result(
                started,
                operation,
                "E_INPUT",
                {
                    "message": f"memory {operation} requires subject"
                    + (" and query." if requires_query else ".")
                },
            )
        retrieval = request.get("retrieval", "lexical")
        if retrieval not in _RETRIEVAL_MODES:
            return self._envelope_result(
                started,
                operation,
                "E_INPUT",
                {"message": f"unsupported retrieval mode: {retrieval!r}"},
            )
        limit = request.get("limit", _COMPACT_DEFAULT_LIMIT)
        max_tokens = request.get("max_tokens", DEFAULT_MAX_TOKENS)
        max_bytes = request.get("max_bytes", DEFAULT_MAX_BYTES)
        encoding = request.get("encoding", DEFAULT_ENCODING)
        cursor = request.get("cursor")
        embedding_endpoint = request.get("embedding_endpoint")
        embedding_model = request.get("embedding_model")
        embedding_model_digest = request.get("embedding_model_digest")
        embedding_chunking_version = request.get("embedding_chunking_version")
        if (
            not isinstance(limit, int)
            or isinstance(limit, bool)
            or not isinstance(max_tokens, int)
            or isinstance(max_tokens, bool)
            or not isinstance(max_bytes, int)
            or isinstance(max_bytes, bool)
            or not isinstance(encoding, str)
            or (cursor is not None and not isinstance(cursor, str))
            or (
                embedding_endpoint is not None
                and not isinstance(embedding_endpoint, str)
            )
            or (embedding_model is not None and not isinstance(embedding_model, str))
            or (
                embedding_model_digest is not None
                and not isinstance(embedding_model_digest, str)
            )
            or (
                embedding_chunking_version is not None
                and not isinstance(embedding_chunking_version, str)
            )
        ):
            return self._envelope_result(
                started,
                operation,
                "E_INPUT",
                {"message": "invalid field type in request"},
            )
        if not session_allowlist:
            return self._envelope_result(
                started,
                operation,
                "E_PERMISSION",
                {
                    "message": f"memory {operation} requires a non-empty session_allowlist "
                    "(fail-closed, no default cross-session access)."
                },
            )
        store = TypedArtifactStore(root)
        telemetry = TelemetryStore(root) if granted.cache_write else None
        if retrieval == "hybrid":
            if not granted.network:
                return self._envelope_result(
                    started,
                    operation,
                    "E_PERMISSION",
                    {
                        "message": f"memory {operation} retrieval=hybrid requires network."
                    },
                )
            embed_config = None
            if embedding_endpoint and embedding_model and embedding_model_digest:
                embed_config = EmbeddingConfig(
                    endpoint=embedding_endpoint,
                    model=embedding_model,
                    model_digest=embedding_model_digest,
                    chunking_version=embedding_chunking_version or "mc12-v1",
                )
            page = hybrid_page(
                store,
                subject=subject,
                query=query or "",
                session_allowlist=session_allowlist,
                embed_config=embed_config,
                limit=limit,
                max_tokens=max_tokens,
                max_bytes=max_bytes,
                encoding=encoding,
                cache_write=granted.cache_write,
                telemetry=telemetry,
                request_id=f"{operation}:{subject}:{query}:hybrid",
                event_id="retrieval",
                opt_in=False,
            )
        else:
            page = recall_page(
                store,
                subject=subject,
                query=query or "",
                session_allowlist=session_allowlist,
                limit=limit,
                max_tokens=max_tokens,
                max_bytes=max_bytes,
                encoding=encoding,
                cursor=cursor,
                telemetry=telemetry,
                request_id=f"{operation}:{subject}:{query}:{cursor}",
                event_id="retrieval",
                opt_in=False,
                cache_write=granted.cache_write,
            )
        code = page.pop("code")
        return self._envelope_result(started, operation, code, page)

    def _expand(
        self,
        started: float,
        root: Path,
        session_allowlist: list[str] | None,
        request: dict[str, Any] | None,
        granted: ExecutionPermissions,
    ) -> ToolResult:
        """MC02 §9.0 `expand` operation: exact-byte expansion of one artifact version.

        MC04: records a real `"expansion"` telemetry event via `expand_artifact()`'s
        `telemetry`/`request_id`/`event_id`/`cache_write` kwargs, gated on `granted
        .cache_write` (mirrors `continuity/context.py`'s existing gate) so a plain read
        never touches `TelemetryStore` at all.
        """
        if request is None:
            return self._envelope_result(
                started,
                "expand",
                "E_INPUT",
                {"message": "memory expand requires request."},
            )
        unknown = set(request) - _EXPAND_REQUEST_KEYS
        if unknown:
            return self._envelope_result(
                started,
                "expand",
                "E_INPUT",
                {"message": f"unknown request field(s): {sorted(unknown)}"},
            )
        artifact_id = request.get("id")
        version = request.get("version")
        if (
            not isinstance(artifact_id, str)
            or not artifact_id
            or not isinstance(version, int)
            or isinstance(version, bool)
        ):
            return self._envelope_result(
                started,
                "expand",
                "E_INPUT",
                {"message": "memory expand requires id and version."},
            )
        offset = request.get("offset", 0)
        max_tokens = request.get("max_tokens", DEFAULT_MAX_TOKENS)
        max_bytes = request.get("max_bytes", DEFAULT_MAX_BYTES)
        encoding = request.get("encoding", DEFAULT_ENCODING)
        if (
            not isinstance(offset, int)
            or isinstance(offset, bool)
            or not isinstance(max_tokens, int)
            or isinstance(max_tokens, bool)
            or not isinstance(max_bytes, int)
            or isinstance(max_bytes, bool)
            or not isinstance(encoding, str)
        ):
            return self._envelope_result(
                started,
                "expand",
                "E_INPUT",
                {"message": "invalid field type in request"},
            )
        store = TypedArtifactStore(root)
        telemetry = TelemetryStore(root) if granted.cache_write else None
        result = expand_artifact(
            store,
            artifact_id=artifact_id,
            version=version,
            session_allowlist=session_allowlist,
            offset=offset,
            max_tokens=max_tokens,
            max_bytes=max_bytes,
            encoding=encoding,
            telemetry=telemetry,
            request_id=f"{artifact_id}:{version}:{offset}",
            event_id="expansion",
            opt_in=False,
            cache_write=granted.cache_write,
        )
        code = result.pop("code")
        return self._envelope_result(started, "expand", code, result)

    def _link(
        self,
        started: float,
        root: Path,
        granted: ExecutionPermissions,
        request: dict[str, Any] | None,
    ) -> ToolResult:
        """MC03 §6.3 `link` operation: adds one versioned evidence edge. Requires
        `cache_write`, same gate as `write`/`promote`/`maintain`."""
        allowed, missing = check_permissions(_WRITE_PERMISSION, granted)
        if not allowed:
            return self._envelope_result(
                started,
                "link",
                "E_PERMISSION",
                {"message": f"Memory link requires {', '.join(missing)}."},
            )
        if request is None:
            return self._envelope_result(
                started, "link", "E_INPUT", {"message": "memory link requires request."}
            )
        unknown = set(request) - _LINK_REQUEST_KEYS
        if unknown:
            return self._envelope_result(
                started,
                "link",
                "E_INPUT",
                {"message": f"unknown request field(s): {sorted(unknown)}"},
            )
        source_id = request.get("source_id")
        source_version = request.get("source_version")
        target_id = request.get("target_id")
        target_version = request.get("target_version")
        kind = request.get("kind")
        origin_ref = request.get("origin_ref")
        if (
            not isinstance(source_id, str)
            or not source_id
            or not isinstance(target_id, str)
            or not target_id
            or not isinstance(source_version, int)
            or isinstance(source_version, bool)
            or not isinstance(target_version, int)
            or isinstance(target_version, bool)
            or not isinstance(kind, str)
            or (origin_ref is not None and not isinstance(origin_ref, str))
        ):
            return self._envelope_result(
                started,
                "link",
                "E_INPUT",
                {
                    "message": "memory link requires source_id, source_version, target_id, "
                    "target_version and kind."
                },
            )
        store = TypedArtifactStore(root)
        result = add_relation(
            store,
            source_id=source_id,
            source_version=source_version,
            target_id=target_id,
            target_version=target_version,
            kind=kind,
            origin_ref=origin_ref,
        )
        code = result.pop("code")
        return self._envelope_result(started, "link", code, result)

    def _related(
        self,
        started: float,
        root: Path,
        session_allowlist: list[str] | None,
        request: dict[str, Any] | None,
    ) -> ToolResult:
        """MC03 §6.3 `related` operation: bounded, authorized traversal from one seed."""
        if request is None:
            return self._envelope_result(
                started,
                "related",
                "E_INPUT",
                {"message": "memory related requires request."},
            )
        unknown = set(request) - _RELATED_REQUEST_KEYS
        if unknown:
            return self._envelope_result(
                started,
                "related",
                "E_INPUT",
                {"message": f"unknown request field(s): {sorted(unknown)}"},
            )
        artifact_id = request.get("id")
        version = request.get("version")
        if (
            not isinstance(artifact_id, str)
            or not artifact_id
            or not isinstance(version, int)
            or isinstance(version, bool)
        ):
            return self._envelope_result(
                started,
                "related",
                "E_INPUT",
                {"message": "memory related requires id and version."},
            )
        depth = request.get("depth", 1)
        max_nodes = request.get("max_nodes", 32)
        max_tokens = request.get("max_tokens", DEFAULT_MAX_TOKENS)
        max_bytes = request.get("max_bytes", DEFAULT_MAX_BYTES)
        encoding = request.get("encoding", DEFAULT_ENCODING)
        if (
            not isinstance(depth, int)
            or isinstance(depth, bool)
            or not isinstance(max_nodes, int)
            or isinstance(max_nodes, bool)
            or not isinstance(max_tokens, int)
            or isinstance(max_tokens, bool)
            or not isinstance(max_bytes, int)
            or isinstance(max_bytes, bool)
            or not isinstance(encoding, str)
        ):
            return self._envelope_result(
                started,
                "related",
                "E_INPUT",
                {"message": "invalid field type in request"},
            )
        store = TypedArtifactStore(root)
        result = related_artifacts(
            store,
            artifact_id=artifact_id,
            version=version,
            session_allowlist=session_allowlist,
            depth=depth,
            max_nodes=max_nodes,
            max_tokens=max_tokens,
            max_bytes=max_bytes,
            encoding=encoding,
        )
        code = result.pop("code")
        return self._envelope_result(started, "related", code, result)

    def _consolidate(
        self,
        started: float,
        root: Path,
        session_allowlist: list[str] | None,
        granted: ExecutionPermissions,
        request: dict[str, Any] | None,
    ) -> ToolResult:
        """MC03 §6.3 `consolidate` operation: derives a duplicate-episode summary. Requires
        `cache_write`, same gate as `write`/`promote`/`maintain`/`link`."""
        allowed, missing = check_permissions(_WRITE_PERMISSION, granted)
        if not allowed:
            return self._envelope_result(
                started,
                "consolidate",
                "E_PERMISSION",
                {"message": f"Memory consolidate requires {', '.join(missing)}."},
            )
        if request is None:
            return self._envelope_result(
                started,
                "consolidate",
                "E_INPUT",
                {"message": "memory consolidate requires request."},
            )
        unknown = set(request) - _CONSOLIDATE_REQUEST_KEYS
        if unknown:
            return self._envelope_result(
                started,
                "consolidate",
                "E_INPUT",
                {"message": f"unknown request field(s): {sorted(unknown)}"},
            )
        symptom = request.get("symptom")
        if not isinstance(symptom, str) or not symptom:
            return self._envelope_result(
                started,
                "consolidate",
                "E_INPUT",
                {"message": "memory consolidate requires symptom."},
            )
        store = TypedArtifactStore(root)
        result = consolidate_episodes(
            store, symptom=symptom, session_allowlist=session_allowlist
        )
        code = result.pop("code")
        return self._envelope_result(started, "consolidate", code, result)

    def _prepare(
        self,
        started: float,
        root: Path,
        session_allowlist: list[str] | None,
        request: dict[str, Any] | None,
        operation: str,
    ) -> ToolResult:
        """MC06.3 `prepare`/`resume`: read-only repair-episode recall. Executes no
        commands and never withholds or prohibits a patch -- it only surfaces recorded
        evidence for a caller to act on."""
        if request is None:
            return self._envelope_result(
                started,
                operation,
                "E_INPUT",
                {"message": f"memory {operation} requires request."},
            )
        unknown = set(request) - _PREPARE_REQUEST_KEYS
        if unknown:
            return self._envelope_result(
                started,
                operation,
                "E_INPUT",
                {"message": f"unknown request field(s): {sorted(unknown)}"},
            )
        task = request.get("task")
        conditions = request.get("conditions")
        behavior_ids = request.get("behavior_ids", [])
        query = request.get("query", "")
        if (
            not isinstance(task, str)
            or not task
            or not isinstance(conditions, dict)
            or not isinstance(behavior_ids, list)
            or not all(isinstance(b, str) for b in behavior_ids)
            or not isinstance(query, str)
        ):
            return self._envelope_result(
                started,
                operation,
                "E_INPUT",
                {"message": f"memory {operation} requires task and conditions."},
            )
        result = prepare_memory(
            project_root=root,
            symptom=query or task,
            conditions=conditions,
            behavior_ids=behavior_ids,
            session_allowlist=session_allowlist,
        )
        code = result.pop("code")
        return self._envelope_result(started, operation, code, result)

    def _envelope_result(
        self, started: float, operation: str, code: str, data: dict[str, Any]
    ) -> ToolResult:
        """MC02 §9.0 operation envelope: `{"schema_version":1,"operation":...,"code":...,
        "data":{...}}` in `ToolResult.raw`, with `code` mapped onto `ToolResult.status` via
        the §9.0 status/code pairs table."""
        status = _CODE_STATUS.get(code, "error")
        return ToolResult(
            tool=self.name,
            engine=None,
            engine_version=None,
            status=status,  # type: ignore[typeddict-item]
            duration_ms=max(0, int((time.monotonic() - started) * 1000)),
            summary=f"memory {operation} returned {code}.",
            findings=[],
            raw={
                "schema_version": 1,
                "operation": operation,
                "code": code,
                "data": data,
            },
            metadata={"operation": operation},
        )

    def _run_write(
        self,
        started: float,
        root: Path,
        subject: MemorySubject | None,
        content: dict[str, Any] | None,
        source: str,
        symbol_ref: str | None,
        source_kind: SourceKind,
        granted: ExecutionPermissions,
    ) -> ToolResult:
        allowed, missing = check_permissions(_WRITE_PERMISSION, granted)
        if not allowed:
            return self._result(
                started,
                "skipped",
                f"Memory write requires {', '.join(missing)}.",
                operation="write",
            )
        if not subject or content is None or not source:
            return self._result(
                started,
                "error",
                "memory write requires subject, content, and source.",
                operation="write",
            )
        store = TypedArtifactStore(root)
        stored = store.write(
            self._build_artifact(subject, content, source, symbol_ref, source_kind)
        )
        return self._result(
            started,
            "ok",
            f"Wrote memory artifact to subject '{subject}'.",
            operation="write",
            raw=self._artifact_dict(stored),
        )

    def _run_promote(
        self,
        started: float,
        root: Path,
        subject: MemorySubject | None,
        content: dict[str, Any] | None,
        source: str,
        symbol_ref: str | None,
        source_kind: SourceKind,
        user_stated: bool,
        candidate_sources: list[str] | None,
        granted: ExecutionPermissions,
    ) -> ToolResult:
        allowed, missing = check_permissions(_WRITE_PERMISSION, granted)
        if not allowed:
            return self._result(
                started,
                "skipped",
                f"Memory promote requires {', '.join(missing)}.",
                operation="promote",
            )
        if not subject or content is None or not source:
            return self._result(
                started,
                "error",
                "memory promote requires subject, content, and source.",
                operation="promote",
            )
        artifact = self._build_artifact(
            subject, content, source, symbol_ref, source_kind
        )
        store = TypedArtifactStore(root)
        stored = store.write(artifact)
        stored, decision = store.promote(
            stored.id,
            user_stated=user_stated,
            candidate_sources=candidate_sources,
        )
        summary = (
            f"Promoted subject '{subject}' to STATED."
            if decision.promoted
            else f"Promotion denied for subject '{subject}': {decision.denial_reason}."
        )
        return self._result(
            started,
            "ok",
            summary,
            operation="promote",
            raw={
                "promoted": decision.promoted,
                "new_tier": decision.new_tier,
                "denial_reason": decision.denial_reason,
                "corroboration_count": decision.corroboration_count,
                "artifact": self._artifact_dict(stored),
            },
        )

    def _run_maintain(
        self,
        started: float,
        root: Path,
        task: MaintenanceTask | None,
        batch_size: int,
        granted: ExecutionPermissions,
    ) -> ToolResult:
        if task is None:
            return self._result(
                started,
                "error",
                "memory maintain requires task.",
                operation="maintain",
            )
        allowed, missing = check_permissions(_WRITE_PERMISSION, granted)
        if not allowed:
            return self._result(
                started,
                "skipped",
                f"Memory maintain requires {', '.join(missing)}.",
                operation="maintain",
            )
        result = run_maintenance_cycle(task, batch_size=batch_size, project_root=root)
        return self._result(
            started,
            "ok",
            f"Maintenance cycle '{task}' processed {result.processed} row(s), "
            f"changed {result.changed}.",
            operation="maintain",
            raw=dataclasses.asdict(result),
        )

    def _verify_attempt(
        self,
        started: float,
        root: Path,
        granted: ExecutionPermissions,
        request: dict[str, Any] | None,
    ) -> ToolResult:
        # Lazy import: `rush.memory.verification` -> `rush.patch.applier` ->
        # `rush.tools.common` -> `rush.tools.__init__` -> this module. A module-level
        # import here would be circular.
        from ..memory.verification import parse_patch_contract, verify_attempt

        if request is None:
            return self._result(
                started,
                "error",
                "memory verify_attempt requires request.",
                operation="verify_attempt",
            )
        unknown = set(request) - _VERIFY_ATTEMPT_REQUEST_KEYS
        if unknown:
            return self._result(
                started,
                "error",
                f"memory verify_attempt unknown request field(s): {sorted(unknown)}.",
                operation="verify_attempt",
            )
        attempt_id = request.get("attempt_id")
        behavior_ids = request.get("behavior_ids")
        contract_raw = request.get("contract")
        patch = request.get("patch")
        declared_permissions = request.get("declared_permissions", ())
        if (
            not attempt_id
            or not isinstance(attempt_id, str)
            or not behavior_ids
            or not isinstance(behavior_ids, (list, tuple))
            or not isinstance(contract_raw, dict)
            or not patch
            or not isinstance(patch, str)
        ):
            return self._result(
                started,
                "error",
                "memory verify_attempt requires attempt_id, behavior_ids, contract, and patch.",
                operation="verify_attempt",
            )
        if not isinstance(declared_permissions, (list, tuple)) or not all(
            isinstance(name, str) for name in declared_permissions
        ):
            return self._result(
                started,
                "error",
                "memory verify_attempt declared_permissions must be a list of strings.",
                operation="verify_attempt",
            )
        try:
            contract = parse_patch_contract(contract_raw, default_sandbox_path=root)
        except (KeyError, TypeError, ValueError) as exc:
            return self._result(
                started,
                "error",
                f"memory verify_attempt invalid contract: {exc}.",
                operation="verify_attempt",
            )
        outcome = verify_attempt(
            attempt_id=attempt_id,
            behavior_ids=tuple(behavior_ids),
            repo_root=root,
            contract=contract,
            patch=patch,
            granted=granted,
            declared_permission_names=tuple(declared_permissions),
        )
        status = _VERIFY_ATTEMPT_OUTCOME_STATUS.get(outcome.outcome, "error")
        return self._result(
            started,
            status,  # type: ignore[arg-type]
            outcome.summary,
            operation="verify_attempt",
            raw={
                "attempt_id": outcome.attempt_id,
                "behavior_ids": list(outcome.behavior_ids),
                "outcome": outcome.outcome,
                "result": dataclasses.asdict(outcome.result)
                if outcome.result is not None
                else None,
            },
        )

    def _intent(
        self,
        started: float,
        root: Path,
        granted: ExecutionPermissions,
        request: dict[str, Any] | None,
    ) -> ToolResult:
        """MC07.3 `intent` operation: `create`/`confirm`/`supersede` a confirmed-intent
        record (each requires `cache_write`, same gate as `write`/`promote`), or read-only
        `check` its exact-revision execution evidence (no permission, never launches a
        command)."""
        if request is None:
            return self._envelope_result(
                started,
                "intent",
                "E_INPUT",
                {"message": "memory intent requires request."},
            )
        unknown = set(request) - _INTENT_REQUEST_KEYS
        if unknown:
            return self._envelope_result(
                started,
                "intent",
                "E_INPUT",
                {"message": f"unknown request field(s): {sorted(unknown)}"},
            )
        action = request.get("action")
        intent_id = request.get("intent_id")
        if (
            action not in _INTENT_ACTIONS
            or not isinstance(intent_id, str)
            or not intent_id
        ):
            return self._envelope_result(
                started,
                "intent",
                "E_INPUT",
                {
                    "message": "memory intent requires action in "
                    "{create,confirm,supersede,check} and intent_id."
                },
            )

        if action == "check":
            current_revision = request.get("current_revision")
            if current_revision is not None and not isinstance(current_revision, str):
                return self._envelope_result(
                    started,
                    "intent",
                    "E_INPUT",
                    {"message": "current_revision must be a string."},
                )
            result = check_intent(
                project_root=root,
                intent_id=intent_id,
                current_revision=current_revision,
            )
            code = result.pop("code")
            return self._envelope_result(started, "intent", code, result)

        allowed, missing = check_permissions(_WRITE_PERMISSION, granted)
        if not allowed:
            return self._envelope_result(
                started,
                "intent",
                "E_PERMISSION",
                {"message": f"Memory intent {action} requires {', '.join(missing)}."},
            )

        source_refs = request.get("source_refs")
        check_refs = request.get("check_refs")
        exceptions = request.get("exceptions")
        if (
            (source_refs is not None and not isinstance(source_refs, list))
            or (check_refs is not None and not isinstance(check_refs, list))
            or (exceptions is not None and not isinstance(exceptions, list))
        ):
            return self._envelope_result(
                started,
                "intent",
                "E_INPUT",
                {"message": "source_refs, check_refs and exceptions must be lists."},
            )
        statement_ref = request.get("statement_ref")
        if statement_ref is not None and not isinstance(statement_ref, dict):
            return self._envelope_result(
                started,
                "intent",
                "E_INPUT",
                {"message": "statement_ref must be a dict."},
            )
        expected_version = request.get("expected_version")
        if expected_version is not None and (
            not isinstance(expected_version, int) or isinstance(expected_version, bool)
        ):
            return self._envelope_result(
                started,
                "intent",
                "E_INPUT",
                {"message": "expected_version must be an int."},
            )

        if action in ("create", "confirm"):
            behavior_id = request.get("behavior_id")
            if behavior_id is not None and not isinstance(behavior_id, str):
                return self._envelope_result(
                    started,
                    "intent",
                    "E_INPUT",
                    {"message": "behavior_id must be a string."},
                )
            if action == "confirm" and expected_version is None:
                return self._envelope_result(
                    started,
                    "intent",
                    "E_INPUT",
                    {"message": "intent confirm requires expected_version."},
                )
            result = record_intent(
                project_root=root,
                intent_id=intent_id,
                behavior_id=behavior_id,
                statement_ref=statement_ref,
                source_refs=source_refs,
                check_refs=check_refs,
                exceptions=exceptions,
                expected_version=expected_version,
            )
            code = result.pop("code")
            return self._envelope_result(started, "intent", code, result)

        # action == "supersede"
        new_statement_ref = request.get("new_statement_ref")
        new_behavior_id = request.get("new_behavior_id")
        if (
            expected_version is None
            or not isinstance(new_statement_ref, dict)
            or not new_statement_ref
        ):
            return self._envelope_result(
                started,
                "intent",
                "E_INPUT",
                {
                    "message": "intent supersede requires expected_version and new_statement_ref."
                },
            )
        if new_behavior_id is not None and not isinstance(new_behavior_id, str):
            return self._envelope_result(
                started,
                "intent",
                "E_INPUT",
                {"message": "new_behavior_id must be a string."},
            )
        result = supersede_intent(
            project_root=root,
            intent_id=intent_id,
            expected_old_version=expected_version,
            new_statement_ref=new_statement_ref,
            new_behavior_id=new_behavior_id,
            source_refs=source_refs,
            check_refs=check_refs,
            exceptions=exceptions,
        )
        code = result.pop("code")
        return self._envelope_result(started, "intent", code, result)

    def _recipe(
        self,
        started: float,
        root: Path,
        granted: ExecutionPermissions,
        request: dict[str, Any] | None,
    ) -> ToolResult:
        """MC08.3 `recipe` operation: read-only `resolve` (no permission, resolves current
        source on disk) versus `record`/`outcome` (each requires `cache_write`, same gate as
        `write`/`promote`/`intent`)."""
        if request is None:
            return self._envelope_result(
                started,
                "recipe",
                "E_INPUT",
                {"message": "memory recipe requires request."},
            )
        unknown = set(request) - _RECIPE_REQUEST_KEYS
        if unknown:
            return self._envelope_result(
                started,
                "recipe",
                "E_INPUT",
                {"message": f"unknown request field(s): {sorted(unknown)}"},
            )
        action = request.get("action")
        recipe_id = request.get("recipe_id")
        if (
            action not in _RECIPE_ACTIONS
            or not isinstance(recipe_id, str)
            or not recipe_id
        ):
            return self._envelope_result(
                started,
                "recipe",
                "E_INPUT",
                {
                    "message": "memory recipe requires action in "
                    "{record,resolve,outcome} and recipe_id."
                },
            )

        if action == "resolve":
            current_dependencies = request.get("current_dependencies")
            current_config_digest = request.get("current_config_digest")
            if current_dependencies is not None and not isinstance(
                current_dependencies, dict
            ):
                return self._envelope_result(
                    started,
                    "recipe",
                    "E_INPUT",
                    {"message": "current_dependencies must be a dict."},
                )
            if current_config_digest is not None and not isinstance(
                current_config_digest, str
            ):
                return self._envelope_result(
                    started,
                    "recipe",
                    "E_INPUT",
                    {"message": "current_config_digest must be a string."},
                )
            result = resolve_recipe(
                project_root=root,
                recipe_id=recipe_id,
                current_dependencies=current_dependencies,
                current_config_digest=current_config_digest,
            )
            code = result.pop("code")
            return self._envelope_result(started, "recipe", code, result)

        allowed, missing = check_permissions(_WRITE_PERMISSION, granted)
        if not allowed:
            return self._envelope_result(
                started,
                "recipe",
                "E_PERMISSION",
                {"message": f"Memory recipe {action} requires {', '.join(missing)}."},
            )

        if action == "record":
            helper_ref = request.get("helper_ref")
            required_symbols = request.get("required_symbols")
            required_dependencies = request.get("required_dependencies")
            checks = request.get("checks")
            exceptions = request.get("exceptions")
            expected_version = request.get("expected_version")
            if helper_ref is not None and not isinstance(helper_ref, dict):
                return self._envelope_result(
                    started,
                    "recipe",
                    "E_INPUT",
                    {"message": "helper_ref must be a dict."},
                )
            if (
                (
                    required_symbols is not None
                    and not isinstance(required_symbols, list)
                )
                or (
                    required_dependencies is not None
                    and not isinstance(required_dependencies, dict)
                )
                or (checks is not None and not isinstance(checks, list))
                or (exceptions is not None and not isinstance(exceptions, list))
            ):
                return self._envelope_result(
                    started,
                    "recipe",
                    "E_INPUT",
                    {
                        "message": "required_symbols and checks must be lists, "
                        "required_dependencies must be a dict."
                    },
                )
            if expected_version is not None and (
                not isinstance(expected_version, int)
                or isinstance(expected_version, bool)
            ):
                return self._envelope_result(
                    started,
                    "recipe",
                    "E_INPUT",
                    {"message": "expected_version must be an int."},
                )
            result = record_recipe(
                project_root=root,
                recipe_id=recipe_id,
                purpose=request.get("purpose"),
                helper_ref=helper_ref,
                required_symbols=required_symbols,
                required_dependencies=required_dependencies,
                required_config_digest=request.get("required_config_digest"),
                checks=checks,
                exceptions=exceptions,
                expected_version=expected_version,
            )
            code = result.pop("code")
            return self._envelope_result(started, "recipe", code, result)

        # action == "outcome"
        recipe_version = request.get("recipe_version")
        patch_hash = request.get("patch_hash")
        verifier_receipt_ref = request.get("verifier_receipt_ref")
        if (
            not isinstance(recipe_version, int)
            or isinstance(recipe_version, bool)
            or not isinstance(patch_hash, str)
            or not patch_hash
            or not isinstance(verifier_receipt_ref, dict)
        ):
            return self._envelope_result(
                started,
                "recipe",
                "E_INPUT",
                {
                    "message": "memory recipe outcome requires recipe_version, patch_hash "
                    "and verifier_receipt_ref."
                },
            )
        result = record_recipe_outcome(
            project_root=root,
            recipe_id=recipe_id,
            recipe_version=recipe_version,
            patch_hash=patch_hash,
            verifier_receipt_ref=verifier_receipt_ref,
        )
        code = result.pop("code")
        return self._envelope_result(started, "recipe", code, result)

    def _plan_checks(
        self,
        started: float,
        root: Path,
        request: dict[str, Any] | None,
    ) -> ToolResult:
        """MC09.3 `plan_checks` operation: read-only -- ranks `required_checks` by real
        observed evidence (never drops or adds required membership). No permission gate,
        same as `recipe` resolve/`intent` check: it only reads already-recorded evidence
        and never executes anything."""
        # Lazy import: mirrors `_verify_attempt`'s existing circular-import workaround
        # (`rush.memory.verification` -> `rush.patch.applier` -> `rush.tools.common` ->
        # `rush.tools.__init__` -> this module).
        from ..memory.verification import plan_checks

        if request is None:
            return self._envelope_result(
                started,
                "plan_checks",
                "E_INPUT",
                {"message": "memory plan_checks requires request."},
            )
        unknown = set(request) - _PLAN_CHECKS_REQUEST_KEYS
        if unknown:
            return self._envelope_result(
                started,
                "plan_checks",
                "E_INPUT",
                {"message": f"unknown request field(s): {sorted(unknown)}"},
            )
        changed_targets = request.get("changed_targets")
        required_checks = request.get("required_checks")
        environment = request.get("environment", {})
        if (
            not isinstance(changed_targets, list)
            or not all(
                isinstance(t, dict) and isinstance(t.get("id"), str) and t.get("id")
                for t in changed_targets
            )
            or not isinstance(required_checks, list)
            or not required_checks
            or not all(
                isinstance(c, dict) and isinstance(c.get("id"), str) and c.get("id")
                for c in required_checks
            )
            or not isinstance(environment, dict)
        ):
            return self._envelope_result(
                started,
                "plan_checks",
                "E_INPUT",
                {
                    "message": "memory plan_checks requires changed_targets (list of "
                    "{id, ...}), a non-empty required_checks (list of {id, ...}), and "
                    "environment."
                },
            )
        result = plan_checks(
            project_root=root,
            changed_targets=changed_targets,
            required_checks=required_checks,
            environment=environment,
        )
        return self._envelope_result(started, "plan_checks", "OK", result)

    def _last_success_diagnose(
        self,
        started: float,
        root: Path,
        request: dict[str, Any] | None,
    ) -> ToolResult:
        """MC10.3 `last_success_diagnose` operation: read-only -- compares current
        `conditions` to the recorded per-behavior/runtime last-success pointer. No
        permission gate, same as `plan_checks`/`recipe` resolve: it only reads already-
        recorded evidence, never executes anything."""
        if request is None:
            return self._envelope_result(
                started,
                "last_success_diagnose",
                "E_INPUT",
                {"message": "memory last_success_diagnose requires request."},
            )
        unknown = set(request) - _LAST_SUCCESS_DIAGNOSE_REQUEST_KEYS
        if unknown:
            return self._envelope_result(
                started,
                "last_success_diagnose",
                "E_INPUT",
                {"message": f"unknown request field(s): {sorted(unknown)}"},
            )
        behavior_id = request.get("behavior_id")
        conditions = request.get("conditions")
        historical = request.get("historical", False)
        if (
            not isinstance(behavior_id, str)
            or not behavior_id
            or not isinstance(conditions, dict)
            or not isinstance(historical, bool)
        ):
            return self._envelope_result(
                started,
                "last_success_diagnose",
                "E_INPUT",
                {
                    "message": "memory last_success_diagnose requires behavior_id (str) "
                    "and conditions (dict); historical must be a bool."
                },
            )
        result = compare_last_success(
            project_root=root,
            behavior_id=behavior_id,
            conditions=conditions,
            historical=historical,
        )
        return self._envelope_result(started, "last_success_diagnose", "OK", result)

    def _handoff(
        self,
        started: float,
        root: Path,
        granted: ExecutionPermissions,
        request: dict[str, Any] | None,
    ) -> ToolResult:
        """MC14 sender-side `handoff` operation (Phase 63 plan §9.1 `handoff prepare` /
        `handoff dispatch/status` rows -- "one CLI leaf with actions"). `action=prepare`
        creates a new bounded handoff session via `rush.memory.handoff.prepare_handoff`,
        gated by `cache_write` like `link`/`consolidate`. `receiver_namespace` (when given)
        becomes the session's own `session_allowlist` -- the set of sources this handoff is
        permitted to see is exactly the receiver's own namespace, never widened by the
        caller. `dispatch`/`status` are the receiver-process-lifecycle actions; MC11 never
        added a `dispatch_handoff` entry point (`src/rush/memory/handoff.py` and
        `src/rush/memory/transport.py` have no such function, and both files are outside
        this packet's owned writes), so they report `E_UNAVAILABLE` honestly rather than
        faking a result."""
        allowed, missing = check_permissions(_WRITE_PERMISSION, granted)
        if not allowed:
            return self._envelope_result(
                started,
                "handoff",
                "E_PERMISSION",
                {"message": f"Memory handoff requires {', '.join(missing)}."},
            )
        if request is None:
            return self._envelope_result(
                started,
                "handoff",
                "E_INPUT",
                {"message": "memory handoff requires request."},
            )
        unknown = set(request) - _HANDOFF_REQUEST_KEYS
        if unknown:
            return self._envelope_result(
                started,
                "handoff",
                "E_INPUT",
                {"message": f"unknown request field(s): {sorted(unknown)}"},
            )
        action = request.get("action")
        if action not in _HANDOFF_ACTIONS:
            return self._envelope_result(
                started,
                "handoff",
                "E_INPUT",
                {"message": f"action must be one of {sorted(_HANDOFF_ACTIONS)}."},
            )
        if action in ("dispatch", "status"):
            return self._envelope_result(
                started,
                "handoff",
                "E_UNAVAILABLE",
                {
                    "message": f"handoff {action} is not yet implemented: "
                    "rush.memory.handoff has no dispatch/status entry point."
                },
            )
        receiver_namespace = request.get("receiver_namespace")
        receiver_audience = request.get("receiver_audience")
        goal = request.get("goal")
        constraints = request.get("constraints")
        unresolved_decisions = request.get("unresolved_decisions")
        selected_refs = request.get("selected_refs")
        valid_refs = False
        if isinstance(selected_refs, list) and selected_refs:
            valid_refs = all(
                isinstance(ref, dict)
                and isinstance(ref.get("id"), str)
                and ref.get("id")
                and isinstance(ref.get("version"), int)
                and not isinstance(ref.get("version"), bool)
                for ref in selected_refs
            )
        if (
            not isinstance(receiver_audience, str)
            or not receiver_audience
            or not isinstance(goal, str)
            or not goal
            or not valid_refs
            or (
                receiver_namespace is not None
                and not isinstance(receiver_namespace, str)
            )
            or (constraints is not None and not isinstance(constraints, dict))
            or (
                unresolved_decisions is not None
                and not isinstance(unresolved_decisions, list)
            )
        ):
            return self._envelope_result(
                started,
                "handoff",
                "E_INPUT",
                {
                    "message": "memory handoff prepare requires receiver_audience (str), "
                    "goal (str) and selected_refs (nonempty list of {id, version})."
                },
            )
        assert isinstance(selected_refs, list)  # guaranteed by valid_refs above
        store = TypedArtifactStore(root)
        session_allowlist = (
            [receiver_namespace] if receiver_namespace else [receiver_audience]
        )
        try:
            session, raw_capability, delta = prepare_handoff(
                store,
                root=root,
                audience=receiver_audience,
                granted_ids=[ref["id"] for ref in selected_refs],
                session_allowlist=session_allowlist,
                constraints={
                    **(constraints or {}),
                    "goal": goal,
                    "unresolved_decisions": unresolved_decisions or [],
                },
            )
        except HandoffError as exc:
            return self._envelope_result(
                started, "handoff", exc.code, {"message": str(exc)}
            )
        return self._envelope_result(
            started,
            "handoff",
            "OK",
            {
                "handoff_id": session.session_id,
                "capability": raw_capability,
                "expires_at": session.expires_at,
                "delta": delta,
            },
        )

    def _receive(
        self,
        started: float,
        root: Path,
        request: dict[str, Any] | None,
    ) -> ToolResult:
        """MC11 `receive` operation: the one write-capable-looking action a restricted
        handoff receiver may call. `session_id`/`capability` gate everything -- no
        `session_allowlist`/permission kwarg reaches this path at all, only the handoff
        session's own immutable grants (`rush.memory.handoff.load_session`). An optional
        `ack` list is verified and applied *first* (an exact receiver read-back, never a
        bare delivery acknowledgement), then the next bounded page is returned."""
        if request is None:
            return self._envelope_result(
                started,
                "receive",
                "E_INPUT",
                {"message": "memory receive requires request."},
            )
        unknown = set(request) - _RECEIVE_REQUEST_KEYS
        if unknown:
            return self._envelope_result(
                started,
                "receive",
                "E_INPUT",
                {"message": f"unknown request field(s): {sorted(unknown)}"},
            )
        session_id = request.get("session_id")
        capability = request.get("capability")
        if (
            not isinstance(session_id, str)
            or not session_id
            or not isinstance(capability, str)
            or not capability
        ):
            return self._envelope_result(
                started,
                "receive",
                "E_INPUT",
                {"message": "memory receive requires session_id and capability."},
            )
        cursor = request.get("cursor")
        page_size = request.get("page_size", 50)
        ack = request.get("ack")
        if (
            (cursor is not None and not isinstance(cursor, str))
            or not isinstance(page_size, int)
            or isinstance(page_size, bool)
            or (ack is not None and not isinstance(ack, list))
        ):
            return self._envelope_result(
                started,
                "receive",
                "E_INPUT",
                {"message": "invalid field type in request"},
            )
        store = TypedArtifactStore(root)
        try:
            if ack:
                acknowledge_readback(
                    store, session_id=session_id, capability=capability, readbacks=ack
                )
            result = receive_handoff(
                store,
                session_id=session_id,
                capability=capability,
                cursor=cursor,
                page_size=page_size,
            )
        except HandoffError as exc:
            return self._envelope_result(
                started, "receive", exc.code, {"message": str(exc)}
            )
        return self._envelope_result(started, "receive", "OK", result)

    def _run_delete(
        self,
        started: float,
        root: Path,
        granted: ExecutionPermissions,
        request: dict[str, Any] | None,
    ) -> ToolResult:
        """P65-07.3 public `delete`: batch-removes memory artifacts through the §6.4
        transaction/outbox algorithm (`TypedArtifactStore.delete_batch`). Preview
        (`apply=False`, the default) is always allowed and never writes. Apply requires
        `cache_write` for the database mutation; a Rush-owned handoff-packet blob among
        the affected ids is additionally unlinked only when `artifact_write` is granted --
        otherwise it is left in place and reported `cleanup_pending` (idempotent to retry
        later), never claimed as atomically erased across the DB/filesystem boundary.
        External source files are never touched by this operation.
        """
        if request is None:
            return self._envelope_result(
                started,
                "delete",
                "E_INPUT",
                {"message": "memory delete requires request."},
            )
        unknown = set(request) - _DELETE_REQUEST_KEYS
        if unknown:
            return self._envelope_result(
                started,
                "delete",
                "E_INPUT",
                {"message": f"unknown request field(s): {sorted(unknown)}"},
            )
        artifact_ids = request.get("artifact_ids")
        expected_revisions = request.get("expected_revisions")
        scope = request.get("scope")
        apply = bool(request.get("apply", False))

        valid_ids = (
            isinstance(artifact_ids, list)
            and 1 <= len(artifact_ids) <= _DELETE_MAX_BATCH
            and all(isinstance(a, str) and a for a in artifact_ids)
            and len(set(artifact_ids)) == len(artifact_ids)
            and not any(("/" in a or "\\" in a or ".." in a) for a in artifact_ids)
        )
        if not valid_ids:
            return self._envelope_result(
                started,
                "delete",
                "E_INPUT",
                {
                    "message": (
                        f"artifact_ids must be 1-{_DELETE_MAX_BATCH} unique non-empty "
                        "IDs with no path separators."
                    )
                },
            )
        assert isinstance(artifact_ids, list)  # narrowed by valid_ids above
        if scope not in _SUBJECT_FAMILY:
            return self._envelope_result(
                started, "delete", "E_INPUT", {"message": f"invalid scope: {scope!r}"}
            )
        valid_revisions = (
            isinstance(expected_revisions, dict)
            and set(expected_revisions) == set(artifact_ids)
            and all(
                isinstance(v, int) and not isinstance(v, bool)
                for v in expected_revisions.values()
            )
        )
        if not valid_revisions:
            return self._envelope_result(
                started,
                "delete",
                "E_INPUT",
                {
                    "message": (
                        "expected_revisions must map exactly the given artifact_ids to "
                        "integer revisions."
                    )
                },
            )

        assert isinstance(expected_revisions, dict)  # narrowed by valid_revisions above

        if apply:
            allowed, missing = check_permissions(_WRITE_PERMISSION, granted)
            if not allowed:
                return self._envelope_result(
                    started,
                    "delete",
                    "E_PERMISSION",
                    {"message": f"memory delete apply requires {', '.join(missing)}."},
                )

        store = TypedArtifactStore(root)
        try:
            result = store.delete_batch(
                artifact_ids,
                expected_revisions=expected_revisions,
                scope=scope,
                apply=apply,
            )
        except KeyError as exc:
            return self._envelope_result(
                started, "delete", "E_INPUT", {"message": f"unknown artifact_id: {exc}"}
            )
        except MemoryScopeError as exc:
            return self._envelope_result(
                started, "delete", "E_SCOPE", {"message": str(exc)}
            )
        except VersionConflictError as exc:
            return self._envelope_result(
                started, "delete", "E_VERSION", {"message": str(exc)}
            )

        cleanup: dict[str, str] = {}
        for item in result["affected"]:
            blob_relpath = item.pop("blob_path", None)
            if not result["applied"] or not blob_relpath:
                continue
            if not granted.artifact_write:
                cleanup[item["id"]] = "cleanup_pending"
                continue
            try:
                (root / blob_relpath).resolve().unlink(missing_ok=True)
                cleanup[item["id"]] = "removed"
            except OSError:
                cleanup[item["id"]] = "cleanup_pending"

        data: dict[str, Any] = {
            "applied": result["applied"],
            "affected": result["affected"],
        }
        if cleanup:
            data["blob_cleanup"] = cleanup
        return self._envelope_result(started, "delete", "OK", data)

    def _run_edit(
        self,
        started: float,
        root: Path,
        granted: ExecutionPermissions,
        request: dict[str, Any] | None,
    ) -> ToolResult:
        """P65-07 §6.4 public `edit`: applies `TypedArtifactStore.edit()`'s compare-and-swap
        content update. Preview (`apply=False`, the default) is always allowed and never
        writes; apply requires `cache_write`."""
        return self._edit_or_archive(
            started, root, granted, request, "edit", _EDIT_REQUEST_KEYS
        )

    def _run_archive(
        self,
        started: float,
        root: Path,
        granted: ExecutionPermissions,
        request: dict[str, Any] | None,
    ) -> ToolResult:
        """P65-07 §6.4 public `archive`: sets/clears an archived marker via
        `TypedArtifactStore.archive()`. Preview (`apply=False`, the default) is always
        allowed and never writes; apply requires `cache_write`. Never deletes content."""
        return self._edit_or_archive(
            started, root, granted, request, "archive", _ARCHIVE_REQUEST_KEYS
        )

    def _edit_or_archive(
        self,
        started: float,
        root: Path,
        granted: ExecutionPermissions,
        request: dict[str, Any] | None,
        operation: Literal["edit", "archive"],
        valid_keys: set[str],
    ) -> ToolResult:
        if request is None:
            return self._envelope_result(
                started,
                operation,
                "E_INPUT",
                {"message": f"memory {operation} requires request."},
            )
        unknown = set(request) - valid_keys
        if unknown:
            return self._envelope_result(
                started,
                operation,
                "E_INPUT",
                {"message": f"unknown request field(s): {sorted(unknown)}"},
            )
        scope = request.get("scope")
        artifact_id = request.get("id")
        expected_version = request.get("expected_version")
        apply = bool(request.get("apply", False))

        if scope not in _SUBJECT_FAMILY:
            return self._envelope_result(
                started, operation, "E_INPUT", {"message": f"invalid scope: {scope!r}"}
            )
        if (
            not isinstance(artifact_id, str)
            or not artifact_id
            or "/" in artifact_id
            or "\\" in artifact_id
            or ".." in artifact_id
        ):
            return self._envelope_result(
                started,
                operation,
                "E_INPUT",
                {"message": "id must be a non-empty ID with no path separators."},
            )
        if not isinstance(expected_version, int) or isinstance(expected_version, bool):
            return self._envelope_result(
                started,
                operation,
                "E_INPUT",
                {"message": "expected_version must be an integer."},
            )

        content: dict[str, Any] = {}
        archived = True
        if operation == "edit":
            requested_content = request.get("content")
            if not isinstance(requested_content, dict):
                return self._envelope_result(
                    started,
                    operation,
                    "E_INPUT",
                    {"message": "content must be an object."},
                )
            content = requested_content
        else:
            requested_archived = request.get("archived", True)
            if not isinstance(requested_archived, bool):
                return self._envelope_result(
                    started,
                    operation,
                    "E_INPUT",
                    {"message": "archived must be a boolean."},
                )
            archived = requested_archived

        if apply:
            allowed, missing = check_permissions(_WRITE_PERMISSION, granted)
            if not allowed:
                return self._envelope_result(
                    started,
                    operation,
                    "E_PERMISSION",
                    {
                        "message": f"memory {operation} apply requires {', '.join(missing)}."
                    },
                )

        store = TypedArtifactStore(root)
        try:
            if operation == "edit":
                result = store.edit(
                    artifact_id,
                    content,
                    expected_version=expected_version,
                    scope=scope,
                    apply=apply,
                )
            else:
                result = store.archive(
                    artifact_id,
                    expected_version=expected_version,
                    scope=scope,
                    apply=apply,
                    archived=archived,
                )
        except KeyError as exc:
            return self._envelope_result(
                started,
                operation,
                "E_INPUT",
                {"message": f"unknown artifact_id: {exc}"},
            )
        except MemoryScopeError as exc:
            return self._envelope_result(
                started, operation, "E_SCOPE", {"message": str(exc)}
            )
        except VersionConflictError as exc:
            return self._envelope_result(
                started, operation, "E_VERSION", {"message": str(exc)}
            )

        return self._envelope_result(started, operation, "OK", result)

    @staticmethod
    def _build_artifact(
        subject: MemorySubject,
        content: dict[str, Any],
        source: str,
        symbol_ref: str | None,
        source_kind: SourceKind,
    ) -> MemoryArtifact:
        return MemoryArtifact(
            id=str(uuid.uuid4()),
            family=_family_for_subject(subject),
            subject=subject,
            trust_tier=default_entry_tier(source_kind),
            content=content,
            source=source,
            created_at=time.time(),
            symbol_ref=symbol_ref,
        )

    @staticmethod
    def _artifact_dict(artifact: MemoryArtifact) -> dict[str, Any]:
        return dataclasses.asdict(artifact)

    def _result(
        self,
        started: float,
        status: Literal["ok", "warn", "fail", "error", "skipped"],
        summary: str,
        *,
        operation: str,
        raw: Any = None,
    ) -> ToolResult:
        return ToolResult(
            tool=self.name,
            engine=None,
            engine_version=None,
            status=status,
            duration_ms=max(0, int((time.monotonic() - started) * 1000)),
            summary=summary,
            findings=[],
            raw=raw,
            metadata={"operation": operation},
        )
