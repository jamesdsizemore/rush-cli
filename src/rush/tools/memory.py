"""Cross-tool memory query/write tool used by the CLI and MCP transports (Phase 61 P61.12)."""

from __future__ import annotations

import base64
import dataclasses
import json
import sqlite3
import time
import uuid
from collections.abc import Callable, Iterator
from contextlib import ExitStack, contextmanager
from pathlib import Path
from typing import Any, Literal, cast, get_args

from ..delivery import compact
from ..invocation.models import InvocationContext
from ..memory.consolidation import consolidate_episodes
from ..memory.embeddings import EmbeddingConfig
from ..memory.experience import MemoryWriteDenied, compare_last_success, prepare_memory
from ..memory.handoff import (
    DEFAULT_PAGE_SIZE,
    HandoffError,
    acknowledge_readback,
    load_session,
    prepare_handoff,
    receive_handoff,
    validate_readbacks,
)
from ..memory.intent import check_intent, record_intent, supersede_intent
from ..memory.maintenance import (
    MaintenanceTask,
    preview_maintenance_candidates,
    run_maintenance_cycle,
)
from ..memory.recipes import record_recipe, record_recipe_outcome, resolve_recipe
from ..memory.relations import add_relation, related_artifacts, relation_input_error
from ..memory.retrieval import (
    DEFAULT_ENCODING,
    DEFAULT_MAX_BYTES,
    DEFAULT_MAX_TOKENS,
    FrameBytes,
    MemoryAccess,
    RouteDenial,
    SourceValidationMemo,
    _fit_optional,
    _measure_page,
    evaluate_artifact_visibility,
    expand_admission,
    expand_artifact,
    hybrid_page,
    memory_policy_mode,
    recall_admission,
    recall_page,
    recheck_failure,
    route_access,
)
from ..memory.retrieval import DEFAULT_LIMIT as _COMPACT_DEFAULT_LIMIT
from ..memory.retrieval import _expand as _expand_body
from ..memory.store import (
    MemoryAccessChanged,
    MemoryArtifact,
    MemoryFamily,
    MemoryMigrationRequiredError,
    MemoryScopeError,
    MemoryStoreUnreadableError,
    MemorySubject,
    OwnerScope,
    OwnerScopeError,
    SignatureMismatchError,
    TrojanSourceFoundError,
    TrustTier,
    TypedArtifactStore,
    VersionConflictError,
    _inspect_text_for_trojan_chars,
    _row_to_artifact,
    artifact_version_sources,
    collect_committed_writes,
    compute_content_signature,
    internal_source_exclusion_sql,
    legacy_owner_scope,
    owner_scope_for_row,
    readonly_state_code,
    readonly_view_reason,
    store_generation,
)
from ..memory.trust import default_entry_tier
from ..permissions import ExecutionPermissions, check_permissions
from ..token_economy.telemetry import TelemetryStore
from .base import ToolFn, ToolResult
from .routing import attach_memory_attribution, memory_block, memory_receipt

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
    # P69-07 ownership contract: an owner mismatch is a rejected mutation, exactly
    # like E_VERSION -- deliberately distinct from E_SCOPE, which means wrong `subject`.
    "E_OWNER": "fail",
    # T20 read-only overview: an unreadable store is an error (exit 2), never a warn.
    "E_STORE_CORRUPT": "error",
    "E_SCHEMA_UNSUPPORTED": "error",
    "E_STORE_BUSY": "error",
    # 72-T02: an expand offset that is negative, past the end or inside a scalar.
    "E_OFFSET": "error",
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
    "representation",
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
_PREPARE_ENTRY_KEYS = (
    "failures",
    "verified_repairs",
    "untested_hypotheses",
    "intent_evidence",
)
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
# `owner_scope` (P69-07) is accepted by all three request-gated operations below --
# each has its own independent allowlist, so adding it to only one would silently
# reject it on the other two.
_DELETE_REQUEST_KEYS = {
    "artifact_ids",
    "expected_revisions",
    "scope",
    "owner_scope",
    "apply",
    "receipt_operation_id",
    "receipt_operation_ids",
    "required_grants",
}
_DELETE_MAX_BATCH = 100
_EDIT_REQUEST_KEYS = {
    "scope",
    "id",
    "expected_version",
    "content",
    "owner_scope",
    "apply",
    "receipt_operation_id",
    "required_grants",
}
_ARCHIVE_REQUEST_KEYS = {
    "scope",
    "id",
    "expected_version",
    "owner_scope",
    "apply",
    "archived",
    "receipt_operation_id",
    "required_grants",
}
# T28-D: `write`/`promote`/`maintain` take their data as named parameters; `request`
# carries only the review contract -- `apply` (default False once a request is sent;
# `request=None` keeps the legacy apply-immediately behavior), the grants pinned at
# review time, and (maintain) the previewed candidate set.
_WRITE_REQUEST_KEYS = {"apply", "required_grants"}
# T28-D: a TUI promote of a listed row names that row and the version reviewed.
_PROMOTE_REQUEST_KEYS = _WRITE_REQUEST_KEYS | {
    "source_id",
    "expected_version",
    "candidate_refs",
}
_MAINTAIN_REQUEST_KEYS = {
    "apply",
    "required_grants",
    "candidate_ids",
    "expected_revisions",
}
_GRANT_NAMES = frozenset(f.name for f in dataclasses.fields(ExecutionPermissions))
_TRUST_TIERS = frozenset(get_args(TrustTier))
_FRESHNESS_FILTERS = {"fresh", "stale"}
_LIST_SCAN_PAGE = 512

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


# 72-T01 D22: the restricted bridge's refusal of an id its session never selected.
_NOT_SELECTED = RouteDenial("E_PERMISSION", "not_selected")
#: 72-T01 D22: the restricted bridge's `(sender access or its delivery denial,
#: selected ids)`.
_BridgeAuthority = tuple[MemoryAccess | HandoffError, tuple[str, ...]]
# 72-T01: `open_readonly_view()` states -> compact/expand envelope codes.
_READ_STATE_CODES = {
    "migration_required": "E_MIGRATION",
    "corrupt": "E_STORE_CORRUPT",
    "busy": "E_STORE_BUSY",
}


class MemoryTool(ToolFn):
    """Query, write, and promote cross-LLM memory artifacts through one result contract."""

    name = "memory"

    def __init__(self, readonly_store: TypedArtifactStore | None = None) -> None:
        # R20.G8: a local read surface (dashboard GET) passes an
        # `open_readonly_view()` store; `expand`/`related` then read through it
        # instead of constructing a writable `TypedArtifactStore(root)`.
        self._readonly_store = readonly_store

    @property
    def mcp_description(self) -> str:
        from rush.catalog import TOOL_SPECS

        return TOOL_SPECS["memory"].mcp_description

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
        owner_scope: dict[str, str] | OwnerScope | None = None,
        allow_cache_write: bool = False,
        allow_artifact_write: bool = False,
        allow_build: bool = False,
        allow_network: bool = False,
        allow_download: bool = False,
        allow_slow: bool = False,
        allow_browser: bool = False,
        request: dict[str, Any] | None = None,
        invocation_id: str | None = None,
        project_id: str | None = None,
        run_id: str | None = None,
        agent_id: str | None = None,
        session_id: str | None = None,
        context: InvocationContext | None = None,
    ) -> ToolResult:
        # 72-T02 D35: the transport frame a memory response leaves through (set by
        # the transport adapter), carrying this call's InvocationContext so its
        # default scope is part of every measured frame.
        published = compact.MEMORY_FRAME.get()
        frame: compact.FrameContext | None = None
        if published is not None:
            frame = dataclasses.replace(published, context=context)
        elif context is not None:
            frame = compact.FrameContext("in_process", None, context=context)
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
            owner_scope=owner_scope,
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
            invocation_id=invocation_id,
            project_id=project_id,
            run_id=run_id,
            agent_id=agent_id,
            session_id=session_id,
            frame=frame,
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
        # P69-07: `write`/`promote` take their inputs as named parameters (not a
        # request dict with an allowlist), so ownership has to be a real parameter
        # here, threaded through the dispatch lambdas below, to reach storage at all.
        owner_scope: dict[str, str] | OwnerScope | None = None,
        permissions: ExecutionPermissions | None = None,
        request: dict[str, Any] | None = None,
        receipt_operation_ids: dict[str, str] | None = None,
        # M11: the public invocation boundary. A caller reusing the same `invocation_id`
        # (a genuine retry of this exact call) dedupes against the earlier telemetry row
        # instead of minting a fresh identity every call; two distinct calls (the caller
        # omits `invocation_id`, or passes a different one) each count. `project_id`/
        # `run_id`/`agent_id`/`session_id` are pure caller-supplied attribution, threaded
        # unchanged into retrieval's telemetry writes -- never guessed from `path`.
        invocation_id: str | None = None,
        project_id: str | None = None,
        run_id: str | None = None,
        agent_id: str | None = None,
        session_id: str | None = None,
        # T28-D reviewable listing: legacy (`request=None`) `list` only. Each set
        # filter narrows the result to exactly the rows matching it; see `_list_filtered`.
        trust_filter: str | None = None,
        source_filter: str | None = None,
        freshness_filter: str | None = None,
        archived_filter: bool | None = None,
        owner_filter: str | None = None,
        # 72-T01 D22: internal-only (never on `__call__`, never read from a request):
        # the restricted bridge's `(sender access, selected ids)`. `expand`, `related`
        # and `resume` then read under that access, limited to the selected ids.
        bridge_authority: _BridgeAuthority | None = None,
        # 72-T02 D35: the response's transport frame; omitted, the frame a transport
        # adapter published (`compact.MEMORY_FRAME`), else payload measurement.
        frame: compact.FrameContext | None = None,
    ) -> ToolResult:
        started = time.monotonic()
        if frame is None:
            frame = compact.MEMORY_FRAME.get()
        try:
            root = Path(path).resolve()
        except (TypeError, ValueError, OSError, RuntimeError):
            return self._envelope_result(
                started,
                str(operation),
                "E_INPUT",
                {"field": "path", "message": "invalid project path"},
            )
        granted = permissions or ExecutionPermissions()
        real_invocation_id = invocation_id or str(uuid.uuid4())

        if operation not in VALID_OPERATIONS:
            return self._result(
                started,
                "error",
                f"Unsupported memory operation: {operation}.",
                operation=str(operation),
            )
        list_filters = {
            "trust_filter": trust_filter,
            "source_filter": source_filter,
            "freshness_filter": freshness_filter,
            "archived_filter": archived_filter,
            "owner_filter": owner_filter,
        }
        filter_error = self._list_filter_error(operation, request, list_filters)
        if filter_error:
            return self._result(started, "error", filter_error, operation=operation)

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
                    invocation_id=real_invocation_id,
                    project_id=project_id,
                    run_id=run_id,
                    agent_id=agent_id,
                    session_id=session_id,
                    owner_scope=owner_scope,
                    frame=frame,
                )
                if request is not None
                else self._query(
                    started,
                    root,
                    subject,
                    query,
                    session_allowlist,
                    "ask",
                    owner_scope=owner_scope,
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
                    invocation_id=real_invocation_id,
                    project_id=project_id,
                    run_id=run_id,
                    agent_id=agent_id,
                    session_id=session_id,
                    owner_scope=owner_scope,
                    frame=frame,
                )
                if request is not None
                else self._query(
                    started,
                    root,
                    subject,
                    query,
                    session_allowlist,
                    "recall",
                    owner_scope=owner_scope,
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
                    invocation_id=real_invocation_id,
                    project_id=project_id,
                    run_id=run_id,
                    agent_id=agent_id,
                    session_id=session_id,
                    owner_scope=owner_scope,
                    frame=frame,
                )
                if request is not None
                else self._list_filtered(
                    started,
                    root,
                    subject,
                    query,
                    session_allowlist,
                    include_archived,
                    trust_filter=trust_filter,
                    source_filter=source_filter,
                    freshness_filter=freshness_filter,
                    archived_filter=archived_filter,
                    owner_filter=owner_filter,
                )
                # T28-D: an unqueried list browses every live row of `subject`.
                if not query
                or any(value is not None for value in list_filters.values())
                else self._query(
                    started,
                    root,
                    subject,
                    query,
                    session_allowlist,
                    "list",
                    include_archived=include_archived,
                    owner_scope=owner_scope,
                )
            ),
            "expand": lambda: self._expand(
                started,
                root,
                session_allowlist,
                request,
                granted,
                invocation_id=real_invocation_id,
                project_id=project_id,
                run_id=run_id,
                agent_id=agent_id,
                session_id=session_id,
                owner_scope=owner_scope,
                bridge=bridge_authority,
                frame=frame,
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
                owner_scope,
                request,
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
                receipt_operation_ids,
                owner_scope,
                request,
            ),
            "maintain": lambda: self._run_maintain(
                started, root, task, batch_size, granted, owner_scope, request
            ),
            "link": lambda: self._link(started, root, granted, request, owner_scope),
            "related": lambda: self._related(
                started,
                root,
                session_allowlist,
                request,
                owner_scope,
                bridge=bridge_authority,
            ),
            "consolidate": lambda: self._consolidate(
                started, root, session_allowlist, granted, request, owner_scope
            ),
            "verify_attempt": lambda: self._verify_attempt(
                started, root, granted, request, owner_scope
            ),
            "prepare": lambda: self._prepare(
                started, root, session_allowlist, request, "prepare", owner_scope
            ),
            "resume": lambda: self._prepare(
                started,
                root,
                session_allowlist,
                request,
                "resume",
                owner_scope,
                bridge=bridge_authority,
            ),
            "intent": lambda: self._intent(
                started, root, granted, request, owner_scope
            ),
            "recipe": lambda: self._recipe(
                started, root, granted, request, owner_scope
            ),
            "plan_checks": lambda: self._plan_checks(
                started, root, request, owner_scope
            ),
            "last_success_diagnose": lambda: self._last_success_diagnose(
                started, root, request, owner_scope
            ),
            "handoff": lambda: self._handoff(
                started, root, granted, request, owner_scope
            ),
            "receive": lambda: self._receive(started, root, request, owner_scope),
            "delete": lambda: self._run_delete(
                started, root, granted, request, owner_scope
            ),
            "edit": lambda: self._run_edit(
                started, root, granted, request, owner_scope
            ),
            "archive": lambda: self._run_archive(
                started, root, granted, request, owner_scope
            ),
        }
        try:
            with collect_committed_writes() as committed:
                result = dispatch_table[operation]()
        except (MemoryAccessChanged, MemoryWriteDenied) as exc:
            # D1 race rule: the access changed before the commit; nothing committed.
            return self._denied(started, operation, RouteDenial(exc.code, exc.reason))
        if operation in _MUTATION_VIEW_OPERATIONS:
            result = _with_mutation_view(root, result, committed)
        result = cast(
            ToolResult,
            attach_memory_attribution(
                result, _memory_attribution(root, operation, result, committed)
            ),
        )
        if frame is not None and frame.context is not None:
            metadata = dict(result.get("metadata") or {})
            if "scope" not in metadata:
                metadata["scope"] = _frame_scope(frame)
                result["metadata"] = metadata
        return result

    @staticmethod
    def _list_filter_error(
        operation: str, request: dict[str, Any] | None, filters: dict[str, Any]
    ) -> str:
        """Validate T28-D listing filters; empty string when valid. A filter is never
        silently ignored: one sent to any other operation, or with `request`, is an
        error rather than an unfiltered result."""
        present = sorted(name for name, value in filters.items() if value is not None)
        if not present:
            return ""
        if operation != "list" or request is not None:
            return (
                f"{', '.join(present)} apply only to legacy memory list (no request)."
            )
        trust = filters["trust_filter"]
        if trust is not None and trust not in _TRUST_TIERS:
            return f"trust_filter must be one of {sorted(_TRUST_TIERS)}."
        source = filters["source_filter"]
        if source is not None and (not isinstance(source, str) or not source):
            return "source_filter must be a non-empty string."
        freshness = filters["freshness_filter"]
        if freshness is not None and freshness not in _FRESHNESS_FILTERS:
            return f"freshness_filter must be one of {sorted(_FRESHNESS_FILTERS)}."
        archived = filters["archived_filter"]
        if archived is not None and not isinstance(archived, bool):
            return "archived_filter must be a boolean."
        owner = filters["owner_filter"]
        if owner is not None and not (
            isinstance(owner, str) and all(owner.partition(":")[0::2])
        ):
            return "owner_filter must be 'kind:id'."
        return ""

    def _list_filtered(
        self,
        started: float,
        root: Path,
        subject: MemorySubject | None,
        query: str,
        session_allowlist: list[str] | None,
        include_archived: bool,
        *,
        trust_filter: str | None,
        source_filter: str | None,
        freshness_filter: str | None,
        archived_filter: bool | None,
        owner_filter: str | None = None,
    ) -> ToolResult:
        """T28-D reviewable `list`: exactly the `subject` rows matching every set filter,
        read through `open_readonly_view()` (never creates `.rush/` or a DB).

        - `source_filter` names the one source to list (the caller's own explicit
          scope, same authority as `session_allowlist`); unset, the allowlist scopes.
        - `trust_filter`: exact trust tier. `freshness_filter`: `"fresh"`/`"stale"`
          against the stored `stale` marker the staleness sweep maintains.
        - `archived_filter`: `True` only archived rows, `False` only live rows; unset
          falls back to `include_archived`. Expired rows are never listed.
        - `owner_filter`: `"kind:id"`, exactly the rows whose owner scope (a legacy
          row resolves to this project's own owner) matches.
        - A non-empty `query` further keeps only the rows its FTS match returns.
        Every returned row passes `recall()`'s signature and Trojan-source checks."""
        if not subject:
            return self._result(
                started, "error", "memory list requires subject.", operation="list"
            )
        want_archived = include_archived if archived_filter is None else archived_filter
        resolved = self._read_access(
            root,
            "list",
            [source_filter] if source_filter else session_allowlist,
            None,
            historical=bool(want_archived),
        )
        if isinstance(resolved, RouteDenial):
            return self._denied(started, "list", resolved)
        access = resolved
        if access.kind == "legacy_allowlist" and not session_allowlist:
            access = dataclasses.replace(access, sources=())
        if not access.sources:
            return self._result(
                started,
                "skipped",
                "memory list requires a non-empty session_allowlist "
                "(fail-closed, no default cross-session access).",
                operation="list",
            )
        view, state = TypedArtifactStore.open_readonly_view(root)
        if state is not None:
            return self._result(
                started, "error", readonly_view_reason(state), operation="list"
            )
        if view is None:
            return self._result(
                started, "ok", "Found 0 memory artifact(s).", operation="list", raw=[]
            )
        policy = access.kind == "policy"
        mode: Literal["inspect", "historical"] = (
            "historical" if want_archived else "inspect"
        )
        memo = SourceValidationMemo()
        decided: list[tuple[sqlite3.Row, str]] = []
        try:
            rows: list[sqlite3.Row] = []
            offset = 0
            while True:
                page = view.scope_artifacts(
                    subject,
                    source_allowlist=list(access.sources),
                    trust_tiers=[trust_filter] if trust_filter else None,
                    include_archived=bool(want_archived),
                    scan_offset=offset,
                    scan_limit=_LIST_SCAN_PAGE,
                    owner_scope=access.owner_scope,
                )
                rows.extend(page)
                if len(page) < _LIST_SCAN_PAGE:
                    break
                offset += _LIST_SCAN_PAGE
            matched = (
                {
                    a.id
                    for a in view.search(
                        subject, query, include_archived=bool(want_archived)
                    )
                }
                if query
                else None
            )
            for row in rows:
                decision = evaluate_artifact_visibility(
                    view, row, access=access, mode=mode, memo=memo
                )
                if decision.visible:
                    decided.append((row, decision.freshness))
        finally:
            view.close()
        artifacts: list[tuple[MemoryArtifact, str]] = []
        for row, freshness in decided:
            if archived_filter is True and row["archived_at"] is None:
                continue
            if freshness_filter is not None:
                if policy:
                    fresh = freshness in ("current", "not_applicable") and not bool(
                        row["stale"]
                    )
                    stale = freshness == "stale" or bool(row["stale"])
                    keep = fresh if freshness_filter == "fresh" else stale
                else:
                    keep = bool(row["stale"]) == (freshness_filter == "stale")
                if not keep:
                    continue
            if matched is not None and row["id"] not in matched:
                continue
            artifact = _row_to_artifact(
                row, default_owner_scope=legacy_owner_scope(root)
            )
            if owner_filter is not None and (
                artifact.owner_scope is None
                or f"{artifact.owner_scope.kind}:{artifact.owner_scope.id}"
                != owner_filter
            ):
                continue
            if (
                not policy
                and artifact.trust_tier == "STATED"
                and (
                    artifact.signature is None
                    or compute_content_signature(artifact.content) != artifact.signature
                )
            ):
                return self._result(
                    started,
                    "error",
                    f"signature mismatch for STATED artifact {artifact.id}",
                    operation="list",
                )
            findings = (
                []
                if policy
                else _inspect_text_for_trojan_chars(
                    json.dumps(artifact.content, ensure_ascii=False)
                )
            )
            if findings:
                return self._result(
                    started,
                    "error",
                    f"Trojan Source characters detected in artifact {artifact.id}: "
                    f"{findings}",
                    operation="list",
                )
            artifacts.append((artifact, freshness))
        if access.recheck() != "ok":
            return self._denied(
                started,
                "list",
                RouteDenial(
                    *(recheck_failure(access) or ("E_RESTART", "access_changed"))
                ),
            )
        # 72-T01 F3: the same additive `freshness` key as the queried list.
        return self._result(
            started,
            "ok",
            f"Found {len(artifacts)} memory artifact(s).",
            operation="list",
            raw=[
                self._artifact_dict(
                    dataclasses.replace(a, freshness=freshness), with_freshness=True
                )
                for a, freshness in artifacts
            ],
        )

    @staticmethod
    def _parse_mutation_request(
        request: dict[str, Any] | None, valid_keys: set[str]
    ) -> tuple[bool, list[str] | None, list[str] | None, str]:
        """T28-D review contract for `write`/`promote`/`maintain`: returns
        `(apply, required_grants, candidate_ids, error)`. `request=None` is the legacy
        apply-immediately call; a sent request previews unless `apply` is True."""
        if request is None:
            return True, None, None, ""
        unknown = set(request) - valid_keys
        if unknown:
            return False, None, None, f"unknown request field(s): {sorted(unknown)}"
        apply = request.get("apply", False)
        if not isinstance(apply, bool):
            return False, None, None, "apply must be a boolean."
        grants, error = _reviewed_grants(request)
        if error:
            return False, None, None, error
        candidate_ids = request.get("candidate_ids")
        if candidate_ids is not None and not (
            isinstance(candidate_ids, list)
            and all(isinstance(c, str) and c for c in candidate_ids)
            and len(set(candidate_ids)) == len(candidate_ids)
        ):
            return False, None, None, "candidate_ids must be unique non-empty IDs."
        return apply, grants, candidate_ids, ""

    def _grant_refusal(
        self,
        started: float,
        operation: str,
        grants: list[str],
        granted: ExecutionPermissions,
    ) -> ToolResult | None:
        """Refuse a `write`/`promote`/`maintain` apply whose permissions lack a
        reviewed grant, before anything is opened for writing."""
        missing = _missing_grants(grants, granted)
        if not missing:
            return None
        message = _grant_refusal_message(operation, missing)
        return self._result(
            started,
            "skipped",
            message,
            operation=operation,
            raw={
                "message": message,
                "required_grants": grants,
                "missing_grants": missing,
            },
        )

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
        owner_scope: dict[str, str] | OwnerScope | None = None,
    ) -> ToolResult:
        """Legacy (`request=None`) `ask`/`recall`/queried `list`. 72-T01: reads through
        `open_readonly_view()` (a missing store is an empty result and creates nothing)
        and the shared decision: `ask`/`recall` return only rows usable as current,
        `list` every visible row (historical with `include_archived`)."""
        if not subject or not query:
            return self._result(
                started,
                "error",
                f"memory {operation} requires subject and query.",
                operation=operation,
            )
        try:
            owner = self._parse_owner_scope(owner_scope, root)
        except ValueError as exc:
            return self._result(
                started, "error", f"invalid owner_scope: {exc}", operation=operation
            )
        historical = operation == "list" and include_archived
        resolved = self._read_access(
            root, operation, session_allowlist, owner, historical=historical
        )
        if isinstance(resolved, RouteDenial):
            return self._denied(started, operation, resolved)
        access = resolved
        if not access.sources:
            return self._result(
                started,
                "skipped",
                f"memory {operation} requires a non-empty session_allowlist "
                "(fail-closed, no default cross-session access).",
                operation=operation,
            )
        view, state = TypedArtifactStore.open_readonly_view(root)
        if state is not None:
            return self._result(
                started, "error", readonly_view_reason(state), operation=operation
            )
        if view is None:
            return self._result(
                started,
                "ok",
                f"Found 0 memory artifact(s) for '{query}'.",
                operation=operation,
                raw=[],
            )
        mode: Literal["ordinary", "inspect", "historical"] = (
            "ordinary"
            if operation in ("ask", "recall")
            else ("historical" if historical else "inspect")
        )
        try:
            artifacts = view.recall(subject, query, access=access, mode=mode)
        except (SignatureMismatchError, TrojanSourceFoundError) as exc:
            return self._result(started, "error", str(exc), operation=operation)
        finally:
            view.close()
        # 72-T01 F2: recheck immediately before emit. A revoked policy fails closed
        # (`E_PERMISSION`); a changed one asks the caller to restart (`E_RESTART`).
        recheck = access.recheck()
        if recheck != "ok":
            code = "E_PERMISSION" if recheck == "denied" else "E_RESTART"
            message = f"memory {operation}: the memory policy changed during the read."
            return self._result(
                started,
                "fail" if recheck == "denied" else "warn",
                f"{message} ({code})",
                operation=operation,
                raw={"code": code, "message": message},
            )
        return self._result(
            started,
            "ok",
            f"Found {len(artifacts)} memory artifact(s) for '{query}'.",
            operation=operation,
            raw=[self._artifact_dict(a, with_freshness=True) for a in artifacts],
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
        *,
        invocation_id: str | None = None,
        project_id: str | None = None,
        run_id: str | None = None,
        agent_id: str | None = None,
        session_id: str | None = None,
        owner_scope: dict[str, str] | OwnerScope | None = None,
        frame: compact.FrameContext | None = None,
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
        if not isinstance(query, str) or "\x00" in query or not _utf8_encodable(query):
            # 72-T02 G4: a NUL or an unpaired surrogate never reaches SQLite.
            return self._envelope_result(
                started,
                operation,
                "E_INPUT",
                {"field": "query", "message": "query must be UTF-8 text without NUL"},
            )
        retrieval = request.get("retrieval", "lexical")
        if not isinstance(retrieval, str) or retrieval not in _RETRIEVAL_MODES:
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
            # 72-T02 G4: `encoding` is echoed in every page; it must be UTF-8 text.
            or not _utf8_encodable(encoding)
            or (cursor is not None and not isinstance(cursor, str))
            # 72-T02: hybrid has no continuation; a cursor sent to it would silently
            # restart from the first page.
            or (retrieval == "hybrid" and cursor is not None)
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
        try:
            owner = self._parse_owner_scope(owner_scope, root)
        except ValueError as exc:
            return self._envelope_result(
                started,
                operation,
                "E_INPUT",
                {"message": f"invalid owner_scope: {exc}"},
            )
        # 72-T02 (C05): admission before access, the store view, telemetry or any
        # embedding call, for both retrieval modes. The lexical minimum is only a lower
        # bound for hybrid's larger envelope; its exact minimum is 72-T08's job. D35:
        # under a transport frame the duration is frozen once, here, and admission,
        # every page fit and the emitted envelope use the same framed bytes.
        frozen = _frozen_duration(started) if frame is not None else None
        fit = self._frame_fit(root, operation, frozen, frame)
        refused = recall_admission(
            limit=limit,
            max_bytes=max_bytes,
            max_tokens=max_tokens,
            encoding=encoding,
            cursor=cursor,
            frame_bytes=fit,
        )
        if refused is not None:
            code = refused.pop("code")
            return self._envelope_result(
                started, operation, code, refused, duration_ms=frozen, frame=frame
            )

        def finish(code: str, data: dict[str, Any]) -> ToolResult:
            """An admitted refusal: optional keys only when the frame still fits."""
            page = _fit_optional(
                {"code": code, **data}, fit, encoding, max_bytes, max_tokens
            )
            code = page.pop("code")
            return self._envelope_result(
                started, operation, code, page, duration_ms=frozen, frame=frame
            )

        resolved = self._read_access(root, operation, session_allowlist, owner)
        if isinstance(resolved, RouteDenial):
            return finish(resolved.code, _denial_data(operation, resolved))
        access = resolved
        if not access.sources:
            return finish(
                "E_PERMISSION",
                {
                    "message": f"memory {operation} requires a non-empty session_allowlist "
                    "(fail-closed, no default cross-session access)."
                },
            )
        if retrieval == "hybrid" and not granted.network:
            return finish(
                "E_PERMISSION",
                {"message": f"memory {operation} retrieval=hybrid requires network."},
            )
        # 72-T01: reads use `open_readonly_view()`. 72-T02 R2: only a hybrid read
        # allowed to persist embeddings, over a store whose writable open runs no DDL
        # or migration (`writable_open_ddl_free`), reopens it writable; any other
        # store stays the read-only view (embeddings are then never persisted).
        store, state = TypedArtifactStore.open_readonly_view(root)
        if state is not None:
            return finish(
                _READ_STATE_CODES[state], {"message": readonly_view_reason(state)}
            )
        if (
            store is not None
            and retrieval == "hybrid"
            and granted.cache_write
            and store.writable_open_ddl_free()
        ):
            store.close()
            store = TypedArtifactStore(root)
        if store is None:
            empty: dict[str, Any] = {
                "items": [],
                "next_cursor": None,
                "complete": True,
                "tokens": 0,
                "bytes": 0,
                "encoding": encoding,
            }
            if retrieval == "hybrid":
                empty.update(retrieval="hybrid", candidates_truncated=False)
            else:
                # 72-T02 (T074 F8): report the real serialized size, the same as an
                # empty page from an existing store. Hybrid sizing is 72-T08's job.
                empty["bytes"], empty["tokens"] = _measure_page(
                    [], None, True, encoding
                )
            return finish("OK", empty)
        try:
            return self._compact_page(
                started,
                store,
                access,
                subject,
                query,
                operation,
                retrieval,
                request,
                granted,
                limit=limit,
                max_tokens=max_tokens,
                max_bytes=max_bytes,
                encoding=encoding,
                cursor=cursor,
                invocation_id=invocation_id,
                project_id=project_id,
                run_id=run_id,
                agent_id=agent_id,
                session_id=session_id,
                frozen=frozen,
                frame=frame,
                fit=fit,
            )
        finally:
            store.close()

    def _compact_page(
        self,
        started: float,
        store: TypedArtifactStore,
        access: MemoryAccess,
        subject: MemorySubject,
        query: str,
        operation: str,
        retrieval: str,
        request: dict[str, Any],
        granted: ExecutionPermissions,
        *,
        limit: int,
        max_tokens: int,
        max_bytes: int,
        encoding: str,
        cursor: str | None,
        invocation_id: str | None,
        project_id: str | None,
        run_id: str | None,
        agent_id: str | None,
        session_id: str | None,
        frozen: int | None = None,
        frame: compact.FrameContext | None = None,
        fit: FrameBytes | None = None,
    ) -> ToolResult:
        """`_compact_query()`'s page over an opened store and a resolved access."""
        root = store.project_root
        embedding_endpoint = request.get("embedding_endpoint")
        embedding_model = request.get("embedding_model")
        embedding_model_digest = request.get("embedding_model_digest")
        embedding_chunking_version = request.get("embedding_chunking_version")
        telemetry = (
            cast(TelemetryStore, _LazyTelemetry(lambda: TelemetryStore(root)))
            if granted.cache_write
            else None
        )
        if retrieval == "hybrid":
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
                access=access,
                embed_config=embed_config,
                limit=limit,
                max_tokens=max_tokens,
                max_bytes=max_bytes,
                encoding=encoding,
                cache_write=granted.cache_write,
                telemetry=telemetry,
                request_id=f"{operation}:{subject}:{query}:hybrid",
                event_id="retrieval",
                invocation_id=invocation_id,
                project_id=project_id,
                run_id=run_id,
                agent_id=agent_id,
                session_id=session_id,
                opt_in=False,
                frame_bytes=fit,
            )
        else:
            page = recall_page(
                store,
                subject=subject,
                query=query or "",
                access=access,
                limit=limit,
                max_tokens=max_tokens,
                max_bytes=max_bytes,
                encoding=encoding,
                cursor=cursor,
                telemetry=telemetry,
                request_id=f"{operation}:{subject}:{query}:{cursor}",
                event_id="retrieval",
                invocation_id=invocation_id,
                project_id=project_id,
                run_id=run_id,
                agent_id=agent_id,
                session_id=session_id,
                opt_in=False,
                cache_write=granted.cache_write,
                frame_bytes=fit,
            )
        code = page.pop("code")
        return self._envelope_result(
            started, operation, code, page, duration_ms=frozen, frame=frame
        )

    def _expand(
        self,
        started: float,
        root: Path,
        session_allowlist: list[str] | None,
        request: dict[str, Any] | None,
        granted: ExecutionPermissions,
        *,
        invocation_id: str | None = None,
        project_id: str | None = None,
        run_id: str | None = None,
        agent_id: str | None = None,
        session_id: str | None = None,
        owner_scope: dict[str, str] | OwnerScope | None = None,
        bridge: _BridgeAuthority | None = None,
        frame: compact.FrameContext | None = None,
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
        if not _utf8_encodable(artifact_id):
            # 72-T02 G4: an unpaired surrogate never reaches SQLite.
            return self._envelope_result(
                started,
                "expand",
                "E_INPUT",
                {"field": "id", "message": "id must be UTF-8 text"},
            )
        offset = request.get("offset", 0)
        max_tokens = request.get("max_tokens", DEFAULT_MAX_TOKENS)
        max_bytes = request.get("max_bytes", DEFAULT_MAX_BYTES)
        encoding = request.get("encoding", DEFAULT_ENCODING)
        representation = request.get("representation", "base64")
        if (
            not isinstance(offset, int)
            or isinstance(offset, bool)
            or not isinstance(max_tokens, int)
            or isinstance(max_tokens, bool)
            or not isinstance(max_bytes, int)
            or isinstance(max_bytes, bool)
            or not isinstance(encoding, str)
            # 72-T02 G4: `encoding` is echoed in every page; it must be UTF-8 text.
            or not _utf8_encodable(encoding)
            or representation not in ("base64", "utf8")
        ):
            return self._envelope_result(
                started,
                "expand",
                "E_INPUT",
                {"message": "invalid field type in request"},
            )
        try:
            owner = self._parse_owner_scope(owner_scope, root)
        except ValueError as exc:
            return self._envelope_result(
                started,
                "expand",
                "E_INPUT",
                {"message": f"invalid owner_scope: {exc}"},
            )
        # 72-T02 (C05): admission before access, the store view or telemetry. D35:
        # under a transport frame the duration is frozen once, here.
        frozen = _frozen_duration(started) if frame is not None else None
        fit = self._frame_fit(root, "expand", frozen, frame)
        refused = expand_admission(
            artifact_id=artifact_id,
            version=version,
            offset=offset,
            max_bytes=max_bytes,
            max_tokens=max_tokens,
            encoding=encoding,
            representation=representation,
            frame_bytes=fit,
        )
        if refused is not None:
            code = refused.pop("code")
            return self._envelope_result(
                started, "expand", code, refused, duration_ms=frozen, frame=frame
            )

        def finish(code: str, data: dict[str, Any]) -> ToolResult:
            """An admitted refusal: optional keys only when the frame still fits."""
            page = _fit_optional(
                {"code": code, **data}, fit, encoding, max_bytes, max_tokens
            )
            code = page.pop("code")
            return self._envelope_result(
                started, "expand", code, page, duration_ms=frozen, frame=frame
            )

        resolved = self._read_access(root, "expand", session_allowlist, owner)
        if isinstance(resolved, RouteDenial):
            return finish(resolved.code, _denial_data("expand", resolved))
        if bridge is not None:
            authority = self._bridge_access(started, "expand", bridge, artifact_id)
            if isinstance(authority, dict):
                refusal = cast(dict[str, Any], cast(ToolResult, authority)["raw"])
                return finish(refusal["code"], refusal["data"])
            resolved = authority
        access: MemoryAccess | None = resolved if resolved.sources else None
        not_visible = _expand_body(
            "E_NOT_VISIBLE",
            artifact_id=artifact_id,
            version=None,
            offset=offset,
            encoding=encoding,
            representation=representation,
        )
        not_visible.pop("code")
        if access is None:
            return finish("E_NOT_VISIBLE", not_visible)
        # 72-T01: a read-only view; a missing store creates nothing and expands nothing.
        store = self._readonly_store
        own_view = store is None
        if store is None:
            store, state = TypedArtifactStore.open_readonly_view(root)
            if state is not None:
                return finish(
                    _READ_STATE_CODES[state], {"message": readonly_view_reason(state)}
                )
        if store is None:
            return finish("E_NOT_VISIBLE", not_visible)
        telemetry = (
            cast(TelemetryStore, _LazyTelemetry(lambda: TelemetryStore(root)))
            if granted.cache_write
            else None
        )
        try:
            result = self._expand_read(
                store,
                access,
                artifact_id,
                version,
                offset=offset,
                max_tokens=max_tokens,
                max_bytes=max_bytes,
                encoding=encoding,
                representation=representation,
                telemetry=telemetry,
                cache_write=granted.cache_write,
                invocation_id=invocation_id,
                project_id=project_id,
                run_id=run_id,
                agent_id=agent_id,
                session_id=session_id,
                frame_bytes=fit,
            )
        finally:
            if own_view:
                store.close()
        code = result.pop("code")
        return self._envelope_result(
            started, "expand", code, result, duration_ms=frozen, frame=frame
        )

    @staticmethod
    def _expand_read(
        store: TypedArtifactStore,
        access: MemoryAccess,
        artifact_id: str,
        version: int,
        *,
        offset: int,
        max_tokens: int,
        max_bytes: int,
        encoding: str,
        representation: Literal["base64", "utf8"] = "base64",
        telemetry: TelemetryStore | None,
        cache_write: bool,
        invocation_id: str | None,
        project_id: str | None,
        run_id: str | None,
        agent_id: str | None,
        session_id: str | None,
        frame_bytes: FrameBytes | None = None,
    ) -> dict[str, Any]:
        # 72-T02: base64 telemetry ids are unchanged; utf8 pages get their own.
        suffix = ":utf8" if representation == "utf8" else ""
        return expand_artifact(
            store,
            artifact_id=artifact_id,
            version=version,
            access=access,
            offset=offset,
            max_tokens=max_tokens,
            max_bytes=max_bytes,
            encoding=encoding,
            representation=representation,
            telemetry=telemetry,
            request_id=f"{artifact_id}:{version}:{offset}{suffix}",
            event_id="expansion",
            invocation_id=invocation_id,
            project_id=project_id,
            run_id=run_id,
            agent_id=agent_id,
            session_id=session_id,
            opt_in=False,
            cache_write=cache_write,
            frame_bytes=frame_bytes,
        )

    def _link(
        self,
        started: float,
        root: Path,
        granted: ExecutionPermissions,
        request: dict[str, Any] | None,
        owner_scope: dict[str, str] | OwnerScope | None = None,
    ) -> ToolResult:
        """MC03 §6.3 `link` operation: adds one versioned evidence edge. Requires
        `cache_write`, same gate as `write`/`promote`/`maintain`. 72-T01: D2 `{write}`
        is resolved, and the policy lock held, before the store is constructed.
        72-T03: `policy` mode links under that resolved `write` access; `legacy` mode
        runs the same-owner path (`access=None`)."""
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
        invalid = relation_input_error(
            source_id=source_id,
            source_version=source_version,
            target_id=target_id,
            target_version=target_version,
            kind=kind,
            origin_ref=origin_ref,
            known_kind=False,
        )
        if invalid is not None:
            code = invalid.pop("code")
            return self._envelope_result(started, "link", code, invalid)
        if not source_id or not target_id:
            return self._envelope_result(
                started,
                "link",
                "E_INPUT",
                {
                    "message": "memory link requires source_id, source_version, target_id, "
                    "target_version and kind."
                },
            )
        try:
            owner = self._parse_owner_scope(owner_scope, root)
        except ValueError as exc:
            return self._envelope_result(
                started, "link", "E_INPUT", {"message": f"invalid owner_scope: {exc}"}
            )
        resolved = self._read_access(root, "link", None, owner, apply=True)
        if isinstance(resolved, RouteDenial):
            return self._mutation_denied(started, "link", resolved)
        invalid = relation_input_error(
            source_id=source_id,
            source_version=source_version,
            target_id=target_id,
            target_version=target_version,
            kind=kind,
            origin_ref=origin_ref,
        )
        if invalid is not None:
            code = invalid.pop("code")
            return self._envelope_result(started, "link", code, invalid)
        with _policy_mutation(resolved) as refused:
            if refused is not None:
                return self._denied(started, "link", refused)
            if not (root / ".rush" / "memory.db").exists():
                # R21: no store, so no endpoint; nothing is created.
                return self._envelope_result(
                    started,
                    "link",
                    "E_NOT_VISIBLE",
                    {"message": "relation endpoint is not visible"},
                )
            store = TypedArtifactStore(root)
            access: MemoryAccess | None = resolved
            if resolved.kind == "legacy_allowlist":
                # D3 as amended (AM1): no declared owner -> the same-owner
                # `access=None` form; a declared owner narrows to that owner.
                access = None
                if owner is not None:
                    access = _legacy_link_access(
                        store, resolved, owner, (source_id, target_id)
                    )
                    if access is None:
                        return self._envelope_result(
                            started,
                            "link",
                            "E_NOT_VISIBLE",
                            {"message": "relation endpoint is not visible"},
                        )
            result = add_relation(
                store,
                source_id=source_id,
                source_version=cast(int, source_version),
                target_id=target_id,
                target_version=cast(int, target_version),
                kind=cast(str, kind),
                origin_ref=origin_ref,
                access=access,
            )
        code = result.pop("code")
        return self._envelope_result(started, "link", code, result)

    def _related(
        self,
        started: float,
        root: Path,
        session_allowlist: list[str] | None,
        request: dict[str, Any] | None,
        owner_scope: dict[str, str] | OwnerScope | None = None,
        *,
        bridge: _BridgeAuthority | None = None,
    ) -> ToolResult:
        """MC03 §6.3 `related` operation: bounded, authorized traversal from one seed.
        72-T01: D1 `ask` access first; reads a read-only view, so a missing store
        creates nothing. 72-T03: the traversal runs under that access, which is resolved
        again after it: a now-denied access returns the missing-root body, a changed
        policy returns `E_RESTART` with no items."""
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
        try:
            artifact_id.encode("utf-8")
        except UnicodeEncodeError:
            return self._envelope_result(
                started,
                "related",
                "E_INPUT",
                {
                    "field": "id",
                    "message": "memory related id must be valid UTF-8 text.",
                },
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
        if session_allowlist is not None and (
            not isinstance(session_allowlist, list | tuple)
            or not all(isinstance(item, str) for item in session_allowlist)
        ):
            return self._envelope_result(
                started,
                "related",
                "E_INPUT",
                {
                    "field": "session_allowlist",
                    "message": "session_allowlist must be a list of strings.",
                },
            )
        try:
            owner = self._parse_owner_scope(owner_scope, root)
        except ValueError as exc:
            return self._envelope_result(
                started,
                "related",
                "E_INPUT",
                {"message": f"invalid owner_scope: {exc}"},
            )
        resolved = self._read_access(root, "related", session_allowlist, owner)
        if isinstance(resolved, RouteDenial):
            return self._denied(started, "related", resolved)
        if bridge is not None:
            authority = self._bridge_access(started, "related", bridge, artifact_id)
            if isinstance(authority, dict):
                return cast(ToolResult, authority)
            resolved = authority
        store = self._readonly_store
        own_view = store is None
        if store is None:
            store, state = TypedArtifactStore.open_readonly_view(root)
            if state is not None:
                return self._envelope_result(
                    started,
                    "related",
                    _READ_STATE_CODES[state],
                    {"message": readonly_view_reason(state)},
                )
        if store is None:
            return self._envelope_result(
                started,
                "related",
                "E_NOT_VISIBLE",
                {
                    "items": [],
                    "complete": True,
                    "tokens": 0,
                    "bytes": 0,
                    "encoding": encoding,
                },
            )
        try:
            result = related_artifacts(
                store,
                artifact_id=artifact_id,
                version=version,
                session_allowlist=None,
                access=resolved,
                selected_ids=bridge[1] if bridge is not None else None,
                depth=depth,
                max_nodes=max_nodes,
                max_tokens=max_tokens,
                max_bytes=max_bytes,
                encoding=encoding,
            )
            # D36/R18: the route's access is rechecked before emission; a denial
            # or a changed grant replaces the traversal (no items).
            failure = recheck_failure(resolved)
            if failure is not None:
                code, reason = failure
                result = {
                    "code": code,
                    "reason": reason,
                    "message": (
                        "memory policy changed during related traversal; retry"
                        if code == "E_RESTART"
                        else f"memory related denied: {reason}."
                    ),
                }
        finally:
            if own_view:
                store.close()
        revoked = self._revoked(started, "related", resolved)
        if revoked is not None:
            return revoked
        code = result.pop("code")
        return self._envelope_result(started, "related", code, result)

    def _consolidate(
        self,
        started: float,
        root: Path,
        session_allowlist: list[str] | None,
        granted: ExecutionPermissions,
        request: dict[str, Any] | None,
        owner_scope: dict[str, str] | OwnerScope | None = None,
    ) -> ToolResult:
        """MC03 §6.3 `consolidate` operation: derives a duplicate-episode summary. Requires
        `cache_write`, same gate as `write`/`promote`/`maintain`/`link`. 72-T01: D2
        `{write}` and the policy lock precede the store. 72-T03: `policy` mode
        consolidates that owner's members under the resolved `write` access (a
        `session_allowlist` only narrows the sources); `legacy` mode runs the
        allowlist path."""
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
        if session_allowlist is not None and (
            not isinstance(session_allowlist, list | tuple)
            or not all(isinstance(item, str) for item in session_allowlist)
        ):
            return self._envelope_result(
                started,
                "consolidate",
                "E_INPUT",
                {
                    "field": "session_allowlist",
                    "message": "session_allowlist must be a list of strings.",
                },
            )
        try:
            owner = self._parse_owner_scope(owner_scope, root)
        except ValueError as exc:
            return self._envelope_result(
                started,
                "consolidate",
                "E_INPUT",
                {"message": f"invalid owner_scope: {exc}"},
            )
        requested = session_allowlist
        if session_allowlist and memory_policy_mode(root) != "legacy":
            # The summary is written under source "consolidation"; the grant must
            # approve it beside the narrowed sources (72-T03 B17).
            requested = sorted({*session_allowlist, "consolidation"})
        resolved = self._read_access(root, "consolidate", requested, owner, apply=True)
        if isinstance(resolved, RouteDenial):
            return self._mutation_denied(started, "consolidate", resolved)
        access = resolved
        if resolved.kind == "legacy_allowlist":
            # D3: legacy consolidation is restricted to the legacy owner.
            legacy_owner = legacy_owner_scope(root)
            if owner is not None and owner != legacy_owner:
                return self._envelope_result(
                    started,
                    "consolidate",
                    "E_NOT_VISIBLE",
                    {"message": "memory consolidate owner_scope is not visible"},
                )
            if not resolved.sources:
                return self._envelope_result(
                    started,
                    "consolidate",
                    "E_PERMISSION",
                    {
                        "message": "memory consolidate requires a non-empty "
                        "session_allowlist (fail-closed, no default cross-session "
                        "access)."
                    },
                )
            access = MemoryAccess.legacy(
                root,
                resolved.sources,
                owner_scope=legacy_owner,
                operation="write",
                data_root=resolved.data_root,
            )
        with _policy_mutation(resolved) as refused:
            if refused is not None:
                return self._denied(started, "consolidate", refused)
            if not (root / ".rush" / "memory.db").exists():
                # R21: no store, so no episode; nothing is created.
                return self._envelope_result(
                    started,
                    "consolidate",
                    "E_INPUT",
                    {"message": f"no episodes found for symptom {symptom!r}"},
                )
            store = TypedArtifactStore(root)
            result = consolidate_episodes(
                store,
                symptom=symptom,
                session_allowlist=session_allowlist,
                access=access,
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
        owner_scope: dict[str, str] | OwnerScope | None = None,
        *,
        bridge: _BridgeAuthority | None = None,
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
        gated = self._read_gate(
            started, root, operation, owner_scope, allowlist=session_allowlist
        )
        if isinstance(gated, dict):
            return cast(ToolResult, gated)
        allowlist = session_allowlist
        if bridge is not None:
            authority = self._bridge_access(started, operation, bridge)
            if isinstance(authority, dict):
                return cast(ToolResult, authority)
            allowlist = list(authority.sources)
        result = prepare_memory(
            project_root=root,
            symptom=query or task,
            conditions=conditions,
            behavior_ids=behavior_ids,
            session_allowlist=allowlist,
        )
        if bridge is not None:
            # D22: only the session's selected ids are enumerated.
            for key in _PREPARE_ENTRY_KEYS:
                result[key] = [e for e in result[key] if e["id"] in bridge[1]]
            result["evidence_refs"] = [
                {"id": e["id"], "version": e["version"]}
                for key in _PREPARE_ENTRY_KEYS
                for e in result[key]
            ]
        code = result.pop("code")
        return self._envelope_result(started, operation, code, result)

    def _envelope_result(
        self,
        started: float,
        operation: str,
        code: str,
        data: dict[str, Any],
        *,
        duration_ms: int | None = None,
        frame: compact.FrameContext | None = None,
    ) -> ToolResult:
        """MC02 §9.0 operation envelope: `{"schema_version":1,"operation":...,"code":...,
        "data":{...}}` in `ToolResult.raw`, with `code` mapped onto `ToolResult.status` via
        the §9.0 status/code pairs table. 72-T02 D35: `duration_ms` is the frozen
        duration of a framed response; `frame.context` adds its default scope."""
        status = _CODE_STATUS.get(code, "error")
        metadata: dict[str, Any] = {"operation": operation}
        if frame is not None and frame.context is not None:
            metadata["scope"] = _frame_scope(frame)
        return ToolResult(
            tool=self.name,
            engine=None,
            engine_version=None,
            status=status,  # type: ignore[typeddict-item]
            duration_ms=duration_ms
            if duration_ms is not None
            else _frozen_duration(started),
            summary=f"memory {operation} returned {code}.",
            findings=[],
            raw={
                "schema_version": 1,
                "operation": operation,
                "code": code,
                "data": data,
            },
            metadata=metadata,
        )

    def _frame_fit(
        self,
        root: Path,
        operation: str,
        frozen: int | None,
        frame: compact.FrameContext | None,
    ) -> FrameBytes | None:
        """72-T02 D35: the exact bytes `frame`'s transport writes for this
        operation's envelope -- the same object `run()` returns (frozen duration,
        default scope, memory attribution), so every fit is the emitted frame."""
        if frame is None:
            return None

        def fit(code: str, data: dict[str, Any]) -> bytes:
            result = self._envelope_result(
                0.0, operation, code, data, duration_ms=frozen, frame=frame
            )
            final = attach_memory_attribution(
                result, _memory_attribution(root, operation, result, [])
            )
            return compact.frame_bytes(frame, final)

        return fit

    @staticmethod
    def _read_access(
        root: Path,
        operation: str,
        session_allowlist: list[str] | None,
        owner: OwnerScope | None,
        *,
        action: str | None = None,
        apply: bool = False,
        historical: bool = False,
    ) -> MemoryAccess | RouteDenial:
        """72-T01 D1/D2 access for one route (`retrieval.route_access`): `legacy`
        mode builds the explicit-allowlist form (a source-less one keeps each route's
        fail-closed output), `policy` mode resolves the grant (the allowlist only
        narrows it), `unavailable` mode denies."""
        return route_access(
            root,
            operation,
            action=action,
            apply=apply,
            historical=historical,
            session_allowlist=session_allowlist,
            owner_scope=owner,
        )

    def _read_gate(
        self,
        started: float,
        root: Path,
        operation: str,
        owner_scope: dict[str, str] | OwnerScope | None,
        *,
        allowlist: list[str] | None = None,
        historical: bool = False,
    ) -> MemoryAccess | ToolResult:
        """D1 gate for a read route whose reader resolves its own access: the
        route's denial (or an invalid owner) before any read, else the access."""
        try:
            owner = self._parse_owner_scope(owner_scope, root)
        except ValueError as exc:
            return self._envelope_result(
                started,
                operation,
                "E_INPUT",
                {"message": f"invalid owner_scope: {exc}"},
            )
        resolved = self._read_access(
            root, operation, allowlist, owner, historical=historical
        )
        if isinstance(resolved, RouteDenial):
            return self._denied(started, operation, resolved)
        return resolved

    def _bridge_access(
        self,
        started: float,
        operation: str,
        bridge: _BridgeAuthority,
        artifact_id: str | None = None,
    ) -> MemoryAccess | ToolResult:
        """72-T01 D22, after the route's own gate passed: the sender's authority
        (or its delivery denial), then the selection -- an id the session never
        selected is refused before any read."""
        authority, selected = bridge
        if isinstance(authority, HandoffError):
            return self._envelope_result(
                started, operation, authority.code, authority.data()
            )
        if artifact_id is not None and artifact_id not in selected:
            return self._denied(started, operation, _NOT_SELECTED)
        return authority

    def _mutation_denied(
        self, started: float, operation: str, denial: RouteDenial
    ) -> ToolResult:
        """72-T03 R2: a `link`/`consolidate` policy resolve that needs an owner
        (more than one granted owner) is an input error on `owner_scope`; any other
        denial is `_denied`."""
        if denial.reason == "owner_required":
            return self._envelope_result(
                started,
                operation,
                "E_INPUT",
                {
                    "field": "owner_scope",
                    "reason": denial.reason,
                    "message": f"memory {operation} requires owner_scope: more than "
                    "one owner is granted for this project.",
                },
            )
        return self._denied(started, operation, denial)

    def _denied(
        self, started: float, operation: str, denial: RouteDenial
    ) -> ToolResult:
        """A D1 denial: the denial code with its exact reason, before any effect."""
        return self._envelope_result(
            started, operation, denial.code, _denial_data(operation, denial)
        )

    def _revoked(
        self, started: float, operation: str, access: MemoryAccess
    ) -> ToolResult | None:
        """D1 race rule for a read or preview: the denial when `access` no longer
        holds, checked immediately before a successful result carrying store data."""
        failure = recheck_failure(access)
        if failure is None:
            return None
        return self._denied(started, operation, RouteDenial(*failure))

    @staticmethod
    def _parse_owner_scope(
        value: dict[str, str] | OwnerScope | None, root: Path
    ) -> OwnerScope | None:
        """Validate a caller-supplied `owner_scope` (P69-07 subsection a).

        Structural validation only for `user`/`agent`/`session` kinds -- this phase has
        no identity provider to authenticate an opaque id against. A `project`-kind id
        written as a filesystem path must be *this* request's own project: a registered
        project's canonical id is a registry UUID (resolved a layer up, in the dashboard
        adapter, which is the only layer that knows it), so a UUID passes through here
        untouched while a path naming a different project is rejected outright.
        """
        if value is None:
            return None
        try:
            owner_scope = OwnerScope.from_value(value)
        except TypeError as exc:
            # 72-T02 G4: a list/dict where a string belongs is invalid input.
            raise ValueError(str(exc)) from exc
        if owner_scope.kind == "project":
            candidate = Path(owner_scope.id)
            resolved = candidate
            try:
                if candidate.is_absolute():
                    resolved = candidate.resolve()
            except (OSError, RuntimeError, ValueError) as exc:
                # 72-T02 G4: a symlink loop or unencodable path is invalid input.
                raise ValueError("invalid project owner path") from exc
            # 72-T01 D1: outside `legacy` mode the grant decides the owner (a
            # different project's owner is denied by resolution, not here).
            if (
                candidate.is_absolute()
                and resolved != root
                and memory_policy_mode(root) == "legacy"
            ):
                raise ValueError(
                    f"project-kind owner_scope {owner_scope.id!r} names a different "
                    f"project than {str(root)!r}"
                )
        return owner_scope

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
        owner_scope: dict[str, str] | OwnerScope | None = None,
        request: dict[str, Any] | None = None,
    ) -> ToolResult:
        apply, grants, _, request_error = self._parse_mutation_request(
            request, _WRITE_REQUEST_KEYS
        )
        if request_error:
            return self._result(
                started,
                "error",
                request_error,
                operation="write",
                raw={"message": request_error},
            )
        if apply:
            allowed, missing = check_permissions(_WRITE_PERMISSION, granted)
            if not allowed:
                return self._result(
                    started,
                    "skipped",
                    f"Memory write requires {', '.join(missing)}.",
                    operation="write",
                )
            refusal = self._grant_refusal(started, "write", grants or [], granted)
            if refusal is not None:
                return refusal
        if not subject or content is None or not source:
            return self._result(
                started,
                "error",
                "memory write requires subject, content, and source.",
                operation="write",
            )
        try:
            owner = self._parse_owner_scope(owner_scope, root)
        except ValueError as exc:
            return self._result(
                started, "error", f"invalid owner_scope: {exc}", operation="write"
            )
        resolved = self._read_access(root, "write", [source], owner, apply=apply)
        if isinstance(resolved, RouteDenial):
            return self._denied(started, "write", resolved)
        artifact = self._build_artifact(
            subject,
            content,
            source,
            symbol_ref,
            source_kind,
            _write_owner(owner, resolved),
        )
        if not apply:
            return self._result(
                started,
                "ok",
                f"Preview: would write a new memory artifact to subject '{subject}'.",
                operation="write",
                raw=_new_artifact_preview(artifact, root, grants, granted),
            )
        with _policy_mutation(resolved) as refused:
            if refused is not None:
                return self._denied(started, "write", refused)
            store = TypedArtifactStore(root)
            stored = store.write(artifact, commit_check=_commit_check(resolved))
        raw = self._artifact_dict(stored)
        if grants is not None:
            raw["required_grants"] = grants
        return self._result(
            started,
            "ok",
            f"Wrote memory artifact to subject '{subject}'.",
            operation="write",
            raw=raw,
        )

    @staticmethod
    def _promote_source_conflict(
        root: Path, source_id: str, expected_version: int
    ) -> dict[str, Any] | None:
        """T28-D: the reviewed promote source must still be the live row at the
        reviewed version; otherwise the candidate would carry content nobody
        reviewed (or revive an archived row)."""
        base = {"source_id": source_id, "expected_version": expected_version}
        view, store_state = TypedArtifactStore.open_readonly_view(root)
        if store_state is not None:
            return {
                **base,
                "actual_version": None,
                "reason": f"the store is {store_state}: {readonly_view_reason(store_state)}",
            }
        try:
            current = view.get_current(source_id) if view is not None else None
        finally:
            if view is not None:
                view.close()
        if current is None:
            return {**base, "actual_version": None, "reason": "it no longer exists"}
        if current.archived_at is not None:
            return {
                **base,
                "actual_version": current.artifact_version,
                "reason": "it was archived",
            }
        if current.artifact_version != expected_version:
            return {
                **base,
                "actual_version": current.artifact_version,
                "reason": (
                    f"reviewed v{expected_version}, now v{current.artifact_version}"
                ),
            }
        return None

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
        receipt_operation_ids: dict[str, str] | None = None,
        owner_scope: dict[str, str] | OwnerScope | None = None,
        request: dict[str, Any] | None = None,
    ) -> ToolResult:
        apply, grants, _, request_error = self._parse_mutation_request(
            request, _PROMOTE_REQUEST_KEYS
        )
        source_id = (request or {}).get("source_id")
        expected_version = (request or {}).get("expected_version")
        if not request_error and (source_id is None) != (expected_version is None):
            request_error = "source_id and expected_version are given together."
        if (
            not request_error
            and source_id is not None
            and not (
                isinstance(source_id, str)
                and source_id
                and type(expected_version) is int
                and expected_version >= 1
            )
        ):
            request_error = (
                "source_id must be a non-empty ID and expected_version a positive int."
            )
        if request_error:
            return self._result(
                started,
                "error",
                request_error,
                operation="promote",
                raw={"message": request_error},
            )
        if apply:
            allowed, missing = check_permissions(_WRITE_PERMISSION, granted)
            if not allowed:
                return self._result(
                    started,
                    "skipped",
                    f"Memory promote requires {', '.join(missing)}.",
                    operation="promote",
                )
            refusal = self._grant_refusal(started, "promote", grants or [], granted)
            if refusal is not None:
                return refusal
        if not subject or content is None or not source:
            return self._result(
                started,
                "error",
                "memory promote requires subject, content, and source.",
                operation="promote",
            )
        try:
            owner = self._parse_owner_scope(owner_scope, root)
        except ValueError as exc:
            return self._result(
                started, "error", f"invalid owner_scope: {exc}", operation="promote"
            )
        resolved = self._read_access(root, "promote", [source], owner, apply=apply)
        if isinstance(resolved, RouteDenial):
            return self._denied(started, "promote", resolved)
        owner = _write_owner(owner, resolved)
        artifact = self._build_artifact(
            subject, content, source, symbol_ref, source_kind, owner
        )
        candidate_refs = (request or {}).get("candidate_refs")
        if candidate_refs is not None:
            if (
                source_id is None
                or not isinstance(candidate_refs, list)
                or not 1 <= len(candidate_refs) <= 64
                or any(
                    not isinstance(ref, dict)
                    or set(ref) != {"id", "version", "source"}
                    or not isinstance(ref["id"], str)
                    or not ref["id"]
                    or type(ref["version"]) is not int
                    or ref["version"] < 1
                    or not isinstance(ref["source"], str)
                    or not ref["source"]
                    for ref in candidate_refs
                )
            ):
                return self._result(
                    started,
                    "error",
                    "invalid promotion candidate refs",
                    operation="promote",
                )
            view, store_state = TypedArtifactStore.open_readonly_view(root)
            if store_state is not None or view is None:
                return self._result(
                    started,
                    "fail",
                    f"promotion candidates unavailable: {store_state}",
                    operation="promote",
                    raw={"code": "E_VERSION", "reason": store_state},
                )
            try:
                selected = view.get_current(source_id)
                sources: set[str] = set()
                valid = (
                    selected is not None
                    and selected.artifact_version == expected_version
                )
                valid = valid and any(ref["id"] == source_id for ref in candidate_refs)
                if valid and selected is not None:
                    valid = (
                        selected.source == source
                        and selected.subject == subject
                        and selected.symbol_ref == symbol_ref
                        and selected.content == content
                        and selected.owner_scope == owner
                        and selected.archived_at is None
                    )
                if valid:
                    for ref in candidate_refs:
                        current = view.get_current(ref["id"])
                        if (
                            current is None
                            or current.artifact_version != ref["version"]
                            or current.source != ref["source"]
                            or current.subject != subject
                            or current.symbol_ref != symbol_ref
                            or current.content != content
                            or current.owner_scope != owner
                            or current.trust_tier == "STATED"
                            or current.stale
                            or current.archived_at is not None
                        ):
                            valid = False
                            break
                        sources.add(current.source)
            finally:
                view.close()
            if not valid:
                return self._result(
                    started,
                    "fail",
                    "promotion candidates changed since review",
                    operation="promote",
                    raw={"code": "E_VERSION", "reason": "candidate changed"},
                )
            candidate_sources = sorted(sources)
        if source_id is not None and isinstance(expected_version, int):
            stale = self._promote_source_conflict(root, source_id, expected_version)
            if stale is not None:
                return self._result(
                    started,
                    "fail",
                    f"Promotion source {source_id} changed since review: {stale['reason']}.",
                    operation="promote",
                    raw={"code": "E_VERSION", **stale},
                )
        if not apply:
            revoked = self._revoked(started, "promote", resolved)
            if revoked is not None:
                return revoked
            preview = _new_artifact_preview(artifact, root, grants, granted)
            preview["user_stated"] = user_stated
            preview["candidate_sources"] = list(candidate_sources or [])
            return self._result(
                started,
                "ok",
                f"Preview: would create a candidate in subject '{subject}' and "
                "request its promotion to STATED.",
                operation="promote",
                raw=preview,
            )
        with _policy_mutation(resolved) as refused:
            if refused is not None:
                return self._denied(started, "promote", refused)
            store = TypedArtifactStore(root)
            # P69-01.2f/S04: promotion is two separately-committed effects (candidate
            # creation, then a distinct promotion decision) -- each consumes its own
            # independently-reserved effect id (`_s04_effect_ids`'s `candidate_create`/
            # `promotion` keys) so recovery can tell "created" apart from "created and
            # promoted" via two independently-addressable receipts, never one shared
            # base id suffixed into two derived strings.
            reserved = receipt_operation_ids or {}
            stored = store.write(
                artifact,
                receipt_operation_id=reserved.get("candidate_create"),
                commit_check=_commit_check(resolved),
            )
            try:
                stored, decision = store.promote(
                    stored.id,
                    user_stated=user_stated,
                    candidate_sources=candidate_sources,
                    candidate_refs=candidate_refs,
                    expected_version=stored.artifact_version,
                    owner_scope=owner,
                    receipt_operation_id=reserved.get("promotion"),
                    commit_check=_commit_check(resolved),
                )
                promotion_error: VersionConflictError | None = None
            except VersionConflictError as conflict:
                promotion_error = conflict
        if promotion_error is not None:
            return self._result(
                started,
                "fail",
                "Promotion candidate created but corroboration changed: "
                f"{promotion_error}",
                operation="promote",
                raw={
                    "code": "E_VERSION",
                    "reason": str(promotion_error),
                    "artifact": self._artifact_dict(stored),
                },
            )
        summary = (
            f"Promoted subject '{subject}' to STATED."
            if decision.promoted
            else f"Promotion denied for subject '{subject}': {decision.denial_reason}."
        )
        promote_raw: dict[str, Any] = {
            "promoted": decision.promoted,
            "new_tier": decision.new_tier,
            "denial_reason": decision.denial_reason,
            "corroboration_count": decision.corroboration_count,
            "artifact": self._artifact_dict(stored),
        }
        if grants is not None:
            promote_raw["required_grants"] = grants
        return self._result(
            started, "ok", summary, operation="promote", raw=promote_raw
        )

    def _run_maintain(
        self,
        started: float,
        root: Path,
        task: MaintenanceTask | None,
        batch_size: int,
        granted: ExecutionPermissions,
        owner_scope: dict[str, str] | OwnerScope | None = None,
        request: dict[str, Any] | None = None,
    ) -> ToolResult:
        if task is None:
            return self._result(
                started,
                "error",
                "memory maintain requires task.",
                operation="maintain",
            )
        apply, grants, candidate_ids, request_error = self._parse_mutation_request(
            request, _MAINTAIN_REQUEST_KEYS
        )
        expected_revisions = (request or {}).get("expected_revisions")
        if not request_error and expected_revisions is not None:
            if not (
                isinstance(expected_revisions, dict)
                and all(
                    isinstance(k, str)
                    and k
                    and isinstance(v, int)
                    and not isinstance(v, bool)
                    and v >= 1
                    for k, v in expected_revisions.items()
                )
            ):
                request_error = "expected_revisions must map non-empty IDs to versions."
            elif candidate_ids is not None and set(candidate_ids) != set(
                expected_revisions
            ):
                request_error = "expected_revisions must cover exactly candidate_ids."
        if request_error:
            return self._result(
                started,
                "error",
                request_error,
                operation="maintain",
                raw={"message": request_error},
            )
        if apply:
            allowed, missing = check_permissions(_WRITE_PERMISSION, granted)
            if not allowed:
                return self._result(
                    started,
                    "skipped",
                    f"Memory maintain requires {', '.join(missing)}.",
                    operation="maintain",
                )
            refusal = self._grant_refusal(started, "maintain", grants or [], granted)
            if refusal is not None:
                return refusal
        try:
            owner = self._parse_owner_scope(owner_scope, root)
        except ValueError as exc:
            return self._result(
                started, "error", f"invalid owner_scope: {exc}", operation="maintain"
            )
        if owner is None:
            return self._result(
                started,
                "error",
                "memory maintain requires owner_scope (M09: no silent "
                "legacy-owner default at this boundary).",
                operation="maintain",
            )
        resolved = self._read_access(root, "maintain", None, owner, apply=apply)
        if isinstance(resolved, RouteDenial):
            return self._denied(started, "maintain", resolved)
        if not apply:
            try:
                candidates = preview_maintenance_candidates(
                    task,
                    batch_size=batch_size,
                    project_root=root,
                    owner_scope=owner,
                    candidate_ids=candidate_ids,
                )
            except (MemoryStoreUnreadableError, MemoryMigrationRequiredError) as exc:
                return self._result(
                    started,
                    "error",
                    str(exc),
                    operation="maintain",
                    raw={"message": str(exc)},
                )
            candidates = _in_source_scope(
                resolved,
                candidates,
                lambda: TypedArtifactStore.open_readonly_view(root),
            )
            revoked = self._revoked(started, "maintain", resolved)
            if revoked is not None:
                return revoked
            ids = [str(c["id"]) for c in candidates]
            effective = grants if grants is not None else ["cache_write"]
            return self._result(
                started,
                "ok",
                f"Preview: maintenance cycle '{task}' would visit {len(ids)} row(s).",
                operation="maintain",
                raw={
                    "task": task,
                    "apply": False,
                    "candidate_ids": ids,
                    "target_ids": ids,
                    "expected_revisions": {
                        str(c["id"]): c["artifact_version"] for c in candidates
                    },
                    "owner_scope": {"kind": owner.kind, "id": owner.id},
                    "required_grants": effective,
                    "missing_grants": _missing_grants(effective, granted),
                },
            )
        # Restricted only when a reviewed candidate set was sent; otherwise the
        # legacy unrestricted call is unchanged.
        restriction: dict[str, Any] = (
            {} if candidate_ids is None else {"candidate_ids": candidate_ids}
        )
        if expected_revisions is not None:
            restriction["expected_revisions"] = expected_revisions
        with _policy_mutation(resolved) as refused:
            if refused is not None:
                return self._denied(started, "maintain", refused)
            if resolved.kind == "policy":
                # D40/D1: a policy-mode sweep visits only rows of the resolved
                # owner whose source the grant approves.
                try:
                    scoped = _in_source_scope(
                        resolved,
                        preview_maintenance_candidates(
                            task,
                            batch_size=batch_size,
                            project_root=root,
                            owner_scope=owner,
                            candidate_ids=candidate_ids,
                        ),
                        lambda: TypedArtifactStore.open_readonly_view(root),
                    )
                except (
                    MemoryStoreUnreadableError,
                    MemoryMigrationRequiredError,
                ) as exc:
                    return self._result(
                        started,
                        "error",
                        str(exc),
                        operation="maintain",
                        raw={"message": str(exc)},
                    )
                restriction["candidate_ids"] = [str(c["id"]) for c in scoped]
                if expected_revisions is not None:
                    restriction["expected_revisions"] = {
                        k: v
                        for k, v in expected_revisions.items()
                        if k in restriction["candidate_ids"]
                    }
            result = run_maintenance_cycle(
                task,
                batch_size=batch_size,
                project_root=root,
                owner_scope=owner,
                **restriction,
            )
        maintain_raw = dataclasses.asdict(result)
        if grants is not None:
            maintain_raw["required_grants"] = grants
        if candidate_ids is not None:
            maintain_raw["candidate_ids"] = candidate_ids
        summary = (
            f"Maintenance cycle '{task}' processed {result.processed} row(s), "
            f"changed {result.changed}."
        )
        if result.refused:
            summary += " Refused (changed since review, left unchanged): " + ", ".join(
                f"{c.id} reviewed v{c.expected}, now "
                + ("deleted" if c.actual is None else f"v{c.actual}")
                for c in result.refused
            )
        return self._result(
            started,
            "warn" if result.refused else "ok",
            summary,
            operation="maintain",
            raw=maintain_raw,
        )

    def _verify_attempt(
        self,
        started: float,
        root: Path,
        granted: ExecutionPermissions,
        request: dict[str, Any] | None,
        owner_scope: dict[str, str] | OwnerScope | None = None,
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
            owner = self._parse_owner_scope(owner_scope, root)
        except ValueError as exc:
            return self._result(
                started,
                "error",
                f"invalid owner_scope: {exc}",
                operation="verify_attempt",
            )
        # 72-T01 G3: D2 `{write}` before the sandbox or any observation write; the
        # observation write itself requires its `verify_attempt:<id>` source (D40).
        resolved = self._read_access(root, "verify_attempt", None, owner, apply=True)
        if isinstance(resolved, RouteDenial):
            return self._denied(started, "verify_attempt", resolved)
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
            access=resolved,
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
        owner_scope: dict[str, str] | OwnerScope | None = None,
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
        try:
            owner = self._parse_owner_scope(owner_scope, root)
        except ValueError as exc:
            return self._envelope_result(
                started,
                "intent",
                "E_INPUT",
                {"message": f"invalid owner_scope: {exc}"},
            )
        # 72-T01 D2: `check` is an `ask` read (its reader narrows to the intent's
        # source itself); a write narrows the grant to `intent:<id>`.
        resolved = self._read_access(
            root,
            "intent",
            None if action == "check" else [f"intent:{intent_id}"],
            owner,
            action=action,
        )
        if isinstance(resolved, RouteDenial):
            return self._denied(started, "intent", resolved)

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
            revoked = self._revoked(started, "intent", resolved)
            if revoked is not None:
                return revoked
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
            with _policy_mutation(resolved) as refused:
                if refused is not None:
                    return self._denied(started, "intent", refused)
                result = record_intent(
                    project_root=root,
                    intent_id=intent_id,
                    behavior_id=behavior_id,
                    statement_ref=statement_ref,
                    source_refs=source_refs,
                    check_refs=check_refs,
                    exceptions=exceptions,
                    expected_version=expected_version,
                    owner_scope=_write_owner(owner, resolved),
                    commit_check=_commit_check(resolved),
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
        with _policy_mutation(resolved) as refused:
            if refused is not None:
                return self._denied(started, "intent", refused)
            result = supersede_intent(
                project_root=root,
                intent_id=intent_id,
                expected_old_version=expected_version,
                new_statement_ref=new_statement_ref,
                new_behavior_id=new_behavior_id,
                source_refs=source_refs,
                check_refs=check_refs,
                exceptions=exceptions,
                commit_check=_commit_check(resolved),
            )
        code = result.pop("code")
        return self._envelope_result(started, "intent", code, result)

    def _recipe(
        self,
        started: float,
        root: Path,
        granted: ExecutionPermissions,
        request: dict[str, Any] | None,
        owner_scope: dict[str, str] | OwnerScope | None = None,
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
        try:
            owner = self._parse_owner_scope(owner_scope, root)
        except ValueError as exc:
            return self._envelope_result(
                started,
                "recipe",
                "E_INPUT",
                {"message": f"invalid owner_scope: {exc}"},
            )
        # 72-T01 D2: `resolve` is an `ask` read (its reader narrows to the recipe's
        # source itself); a write narrows the grant to `recipe:<id>`.
        resolved = self._read_access(
            root,
            "recipe",
            None if action == "resolve" else [f"recipe:{recipe_id}"],
            owner,
            action=action,
        )
        if isinstance(resolved, RouteDenial):
            return self._denied(started, "recipe", resolved)

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
            with _policy_mutation(resolved) as refused:
                if refused is not None:
                    return self._denied(started, "recipe", refused)
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
                    owner_scope=_write_owner(owner, resolved),
                    commit_check=_commit_check(resolved),
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
        with _policy_mutation(resolved) as refused:
            if refused is not None:
                return self._denied(started, "recipe", refused)
            result = record_recipe_outcome(
                project_root=root,
                recipe_id=recipe_id,
                recipe_version=recipe_version,
                patch_hash=patch_hash,
                verifier_receipt_ref=verifier_receipt_ref,
                commit_check=_commit_check(resolved),
            )
        code = result.pop("code")
        return self._envelope_result(started, "recipe", code, result)

    def _plan_checks(
        self,
        started: float,
        root: Path,
        request: dict[str, Any] | None,
        owner_scope: dict[str, str] | OwnerScope | None = None,
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
        gated = self._read_gate(started, root, "plan_checks", owner_scope)
        if isinstance(gated, dict):
            return cast(ToolResult, gated)
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
        owner_scope: dict[str, str] | OwnerScope | None = None,
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
        gated = self._read_gate(
            started,
            root,
            "last_success_diagnose",
            owner_scope,
            historical=bool(historical),
        )
        if isinstance(gated, dict):
            return cast(ToolResult, gated)
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
        owner_scope: dict[str, str] | OwnerScope | None = None,
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
        try:
            owner = self._parse_owner_scope(owner_scope, root)
        except ValueError as exc:
            return self._envelope_result(
                started,
                "handoff",
                "E_INPUT",
                {"message": f"invalid owner_scope: {exc}"},
            )
        # 72-T01 D2/D21: every handoff action needs one grant with write+expand.
        gate = self._read_access(root, "handoff", None, owner, action=action)
        if isinstance(gate, RouteDenial):
            return self._denied(started, "handoff", gate)
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
        session_allowlist = (
            [receiver_namespace] if receiver_namespace else [receiver_audience]
        )
        resolved = self._read_access(
            root, "handoff", session_allowlist, owner, action=action
        )
        if isinstance(resolved, RouteDenial):
            return self._denied(started, "handoff", resolved)
        try:
            with _policy_mutation(resolved) as refused:
                if refused is not None:
                    return self._denied(started, "handoff", refused)
                store = TypedArtifactStore(root)
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
                    sender=resolved,
                    commit_check=_commit_check(resolved),
                )
        except HandoffError as exc:
            return self._envelope_result(started, "handoff", exc.code, exc.data())
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
        owner_scope: dict[str, str] | OwnerScope | None = None,
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
        page_size = request.get("page_size", DEFAULT_PAGE_SIZE)
        ack = request.get("ack")
        if (
            (cursor is not None and not isinstance(cursor, str))
            or not isinstance(page_size, int)
            or isinstance(page_size, bool)
            or not 1 <= page_size <= DEFAULT_PAGE_SIZE
            or (ack is not None and not isinstance(ack, list))
        ):
            return self._envelope_result(
                started,
                "receive",
                "E_INPUT",
                {"message": "invalid field type in request"},
            )
        try:
            if ack:
                validate_readbacks(ack)
            owner = self._parse_owner_scope(owner_scope, root)
        except HandoffError as exc:
            return self._envelope_result(started, "receive", exc.code, exc.data())
        except ValueError as exc:
            return self._envelope_result(
                started,
                "receive",
                "E_INPUT",
                {"message": f"invalid owner_scope: {exc}"},
            )
        gate = self._read_access(root, "receive", None, owner)
        if isinstance(gate, RouteDenial):
            return self._denied(started, "receive", gate)
        # 72-T01 D22: a read-only load; a writable store opens only for a valid,
        # authorized ack, after every check.
        view, _state = TypedArtifactStore.open_readonly_view(root)
        try:
            if view is None:
                load_session(None, session_id, capability)
            assert view is not None
            if ack:
                acknowledge_readback(
                    lambda: TypedArtifactStore(root),
                    session_id=session_id,
                    capability=capability,
                    readbacks=ack,
                    view=view,
                )
                view.close()
                view, _state = TypedArtifactStore.open_readonly_view(root)
                if view is None:
                    load_session(None, session_id, capability)
                assert view is not None
            result = receive_handoff(
                view,
                session_id=session_id,
                capability=capability,
                cursor=cursor,
                page_size=page_size,
            )
        except HandoffError as exc:
            return self._envelope_result(started, "receive", exc.code, exc.data())
        finally:
            if view is not None:
                view.close()
        revoked = self._revoked(started, "receive", gate)
        if revoked is not None:
            return revoked
        return self._envelope_result(started, "receive", "OK", result)

    def _run_delete(
        self,
        started: float,
        root: Path,
        granted: ExecutionPermissions,
        request: dict[str, Any] | None,
        owner_scope: dict[str, str] | OwnerScope | None = None,
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
        raw_apply = request.get("apply", False)
        if not isinstance(raw_apply, bool):
            return self._envelope_result(
                started, "delete", "E_INPUT", {"message": "apply must be a boolean."}
            )
        apply = raw_apply

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

        try:
            owner = self._parse_owner_scope(
                request.get("owner_scope", owner_scope), root
            )
        except ValueError as exc:
            return self._envelope_result(
                started, "delete", "E_INPUT", {"message": f"invalid owner_scope: {exc}"}
            )
        grants, grants_error = _reviewed_grants(request)
        if grants_error:
            return self._envelope_result(
                started, "delete", "E_INPUT", {"message": grants_error}
            )
        resolved = self._read_access(root, "delete", None, owner, apply=apply)
        if isinstance(resolved, RouteDenial):
            return self._denied(started, "delete", resolved)
        owner = _write_owner(owner, resolved)
        hidden = _hidden_targets(
            resolved,
            artifact_ids,
            lambda: TypedArtifactStore.open_readonly_view(root),
        )
        if hidden:
            return self._envelope_result(
                started,
                "delete",
                "E_INPUT",
                {"message": f"unknown artifact_id: {hidden[0]!r}"},
            )

        if apply:
            allowed, missing = check_permissions(_WRITE_PERMISSION, granted)
            if not allowed:
                return self._envelope_result(
                    started,
                    "delete",
                    "E_PERMISSION",
                    {"message": f"memory delete apply requires {', '.join(missing)}."},
                )
            refused = self._envelope_grant_refusal(started, "delete", grants, granted)
            if refused is not None:
                return refused

        receipt_operation_ids = request.get("receipt_operation_ids")
        if not isinstance(receipt_operation_ids, dict):
            receipt_operation_ids = None
        try:
            if not apply:
                # A preview is genuinely read-only: it runs over a query-only view and
                # never constructs a writable `TypedArtifactStore` (which would create
                # `.rush/memory.db`).
                view, view_state = TypedArtifactStore.open_readonly_view(root)
                if view is None:
                    if view_state is None:
                        raise KeyError(artifact_ids[0])
                    return self._envelope_result(
                        started,
                        "delete",
                        _READ_STATE_CODES[view_state],
                        {"message": readonly_view_reason(view_state)},
                    )
                try:
                    result = view.delete_batch(
                        artifact_ids,
                        expected_revisions=expected_revisions,
                        scope=scope,
                        owner_scope=owner,
                        apply=False,
                    )
                finally:
                    view.close()
                failure = recheck_failure(resolved)
                if failure is not None:
                    return self._denied(started, "delete", RouteDenial(*failure))
            else:
                with _policy_mutation(resolved) as lock_refused:
                    if lock_refused is not None:
                        return self._denied(started, "delete", lock_refused)
                    store = TypedArtifactStore(root)
                    result = store.delete_batch(
                        artifact_ids,
                        expected_revisions=expected_revisions,
                        scope=scope,
                        owner_scope=owner,
                        apply=True,
                        receipt_operation_id=request.get("receipt_operation_id"),
                        receipt_operation_ids=receipt_operation_ids,
                        commit_check=_commit_check(resolved),
                    )
        except KeyError as exc:
            return self._envelope_result(
                started, "delete", "E_INPUT", {"message": f"unknown artifact_id: {exc}"}
            )
        except OwnerScopeError as exc:
            return self._envelope_result(
                started, "delete", "E_OWNER", {"message": str(exc)}
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
        if grants is not None:
            data["required_grants"] = grants
        return self._envelope_result(started, "delete", "OK", data)

    def _run_edit(
        self,
        started: float,
        root: Path,
        granted: ExecutionPermissions,
        request: dict[str, Any] | None,
        owner_scope: dict[str, str] | OwnerScope | None = None,
    ) -> ToolResult:
        """P65-07 §6.4 public `edit`: applies `TypedArtifactStore.edit()`'s compare-and-swap
        content update. Preview (`apply=False`, the default) is always allowed and never
        writes; apply requires `cache_write`."""
        return self._edit_or_archive(
            started, root, granted, request, "edit", _EDIT_REQUEST_KEYS, owner_scope
        )

    def _run_archive(
        self,
        started: float,
        root: Path,
        granted: ExecutionPermissions,
        request: dict[str, Any] | None,
        owner_scope: dict[str, str] | OwnerScope | None = None,
    ) -> ToolResult:
        """P65-07 §6.4 public `archive`: sets/clears an archived marker via
        `TypedArtifactStore.archive()`. Preview (`apply=False`, the default) is always
        allowed and never writes; apply requires `cache_write`. Never deletes content."""
        return self._edit_or_archive(
            started,
            root,
            granted,
            request,
            "archive",
            _ARCHIVE_REQUEST_KEYS,
            owner_scope,
        )

    def _edit_or_archive(
        self,
        started: float,
        root: Path,
        granted: ExecutionPermissions,
        request: dict[str, Any] | None,
        operation: Literal["edit", "archive"],
        valid_keys: set[str],
        owner_scope: dict[str, str] | OwnerScope | None = None,
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
        raw_apply = request.get("apply", False)
        if not isinstance(raw_apply, bool):
            return self._envelope_result(
                started, operation, "E_INPUT", {"message": "apply must be a boolean."}
            )
        apply = raw_apply

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

        try:
            owner = self._parse_owner_scope(
                request.get("owner_scope", owner_scope), root
            )
        except ValueError as exc:
            return self._envelope_result(
                started,
                operation,
                "E_INPUT",
                {"message": f"invalid owner_scope: {exc}"},
            )
        grants, grants_error = _reviewed_grants(request)
        if grants_error:
            return self._envelope_result(
                started, operation, "E_INPUT", {"message": grants_error}
            )
        resolved = self._read_access(root, operation, None, owner, apply=apply)
        if isinstance(resolved, RouteDenial):
            return self._denied(started, operation, resolved)
        owner = _write_owner(owner, resolved)
        hidden = _hidden_targets(
            resolved,
            [artifact_id],
            lambda: TypedArtifactStore.open_readonly_view(root),
        )
        if hidden:
            return self._envelope_result(
                started,
                operation,
                "E_INPUT",
                {"message": f"unknown artifact_id: {artifact_id!r}"},
            )

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
            refused = self._envelope_grant_refusal(started, operation, grants, granted)
            if refused is not None:
                return refused

        receipt_operation_id = request.get("receipt_operation_id")
        try:
            if not apply:
                # P69-07 subsection f: a preview is genuinely read-only -- it never
                # constructs a writable `TypedArtifactStore`, whose mere construction
                # creates `.rush/`, runs the schema script, mints a cursor key, and
                # (as of this packet) runs the `owner_scope` migration.
                result = TypedArtifactStore.preview_mutation(
                    root,
                    artifact_id,
                    expected_version=expected_version,
                    scope=scope,
                    owner_scope=owner,
                    operation=operation,
                )
                revoked = self._revoked(started, operation, resolved)
                if revoked is not None:
                    return revoked
            else:
                with _policy_mutation(resolved) as lock_refused:
                    if lock_refused is not None:
                        return self._denied(started, operation, lock_refused)
                    if operation == "edit":
                        result = TypedArtifactStore(root).edit(
                            artifact_id,
                            content,
                            expected_version=expected_version,
                            scope=scope,
                            owner_scope=owner,
                            apply=True,
                            receipt_operation_id=receipt_operation_id,
                            commit_check=_commit_check(resolved),
                        )
                    else:
                        result = TypedArtifactStore(root).archive(
                            artifact_id,
                            expected_version=expected_version,
                            scope=scope,
                            owner_scope=owner,
                            apply=True,
                            archived=archived,
                            receipt_operation_id=receipt_operation_id,
                            commit_check=_commit_check(resolved),
                        )
        except KeyError as exc:
            return self._envelope_result(
                started,
                operation,
                "E_INPUT",
                {"message": f"unknown artifact_id: {exc}"},
            )
        except MemoryMigrationRequiredError as exc:
            return self._envelope_result(
                started, operation, "E_MIGRATION", {"message": str(exc)}
            )
        except MemoryStoreUnreadableError as exc:
            return self._envelope_result(
                started, operation, exc.code, {"message": str(exc)}
            )
        except OwnerScopeError as exc:
            return self._envelope_result(
                started, operation, "E_OWNER", {"message": str(exc)}
            )
        except MemoryScopeError as exc:
            return self._envelope_result(
                started, operation, "E_SCOPE", {"message": str(exc)}
            )
        except VersionConflictError as exc:
            return self._envelope_result(
                started, operation, "E_VERSION", {"message": str(exc)}
            )

        if grants is not None:
            result = {**result, "required_grants": grants}
        return self._envelope_result(started, operation, "OK", result)

    def _envelope_grant_refusal(
        self,
        started: float,
        operation: str,
        grants: list[str] | None,
        granted: ExecutionPermissions,
    ) -> ToolResult | None:
        """T28-D: `E_PERMISSION` for an `edit`/`archive`/`delete` apply whose
        permissions lack a reviewed grant, before any store is opened for writing."""
        missing = _missing_grants(grants or [], granted)
        if not missing:
            return None
        return self._envelope_result(
            started,
            operation,
            "E_PERMISSION",
            {
                "message": _grant_refusal_message(operation, missing),
                "required_grants": grants,
                "missing_grants": missing,
            },
        )

    @staticmethod
    def _build_artifact(
        subject: MemorySubject,
        content: dict[str, Any],
        source: str,
        symbol_ref: str | None,
        source_kind: SourceKind,
        owner_scope: OwnerScope | None = None,
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
            owner_scope=owner_scope,
        )

    @staticmethod
    def _artifact_dict(
        artifact: MemoryArtifact, *, with_freshness: bool = False
    ) -> dict[str, Any]:
        # 72-T01: legacy `list`/`recall`/`ask` rows carry the additive decision
        # `freshness` (F3); write/promote records keep their pre-T01 shape.
        data = dataclasses.asdict(artifact)
        if not with_freshness:
            data.pop("freshness", None)
        return data

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


def _legacy_link_access(
    store: TypedArtifactStore,
    resolved: MemoryAccess,
    owner: OwnerScope,
    endpoint_ids: tuple[str, str],
) -> MemoryAccess | None:
    """72-T03 D3 (AM1): legacy `link` with a declared owner decides the endpoints
    under the legacy allowlist of their own sources, read under the policy lock,
    narrowed to that owner. `None` when neither endpoint exists."""
    conn = store._connect()
    try:
        sources = sorted(
            {
                row[0]
                for row in conn.execute(
                    "SELECT source FROM memory_artifacts WHERE id IN (?, ?)",
                    endpoint_ids,
                ).fetchall()
            }
        )
    finally:
        conn.close()
    if not sources:
        return None
    return MemoryAccess.legacy(
        store.project_root,
        sources,
        owner_scope=owner,
        operation="write",
        data_root=resolved.data_root,
    )


# --- 72-T01 D1 mutation guard ------------------------------------------------


@contextmanager
def _policy_mutation(access: MemoryAccess) -> Iterator[RouteDenial | None]:
    """D1 race rule for one mutation: hold the policy lock, then re-evaluate the
    access under it. Yields the denial (`lock_unavailable`, the recheck failure)
    or `None` while the lock is held; the caller commits with `commit_check`."""
    from ..dashboard.state import PolicyLockRootUncreatable
    from ..memory.authorization import hold_policy_lock, load_policy_readonly

    with ExitStack() as stack:
        try:
            stack.enter_context(hold_policy_lock(data_root=access.data_root))
        except PolicyLockRootUncreatable:
            if not (
                access.kind == "legacy_allowlist"
                and load_policy_readonly(data_root=access.data_root)["state"]
                == "missing"
            ):
                yield RouteDenial("E_PERMISSION", "lock_unavailable")
                return
        except (OSError, ValueError):
            yield RouteDenial("E_PERMISSION", "lock_unavailable")
            return
        except Exception as exc:  # noqa: BLE001 - a policy error denies the mutation
            reason = getattr(exc, "reason", None) or "lock_unavailable"
            yield RouteDenial("E_PERMISSION", str(reason))
            return
        failure = recheck_failure(access)
        yield RouteDenial(*failure) if failure is not None else None


def _hidden_targets(
    access: MemoryAccess, ids: list[str], open_view: Callable[[], Any]
) -> list[str]:
    """Policy mode: the existing target ids whose source the grant does not
    approve (they are reported exactly like unknown ids). Legacy: none."""
    if access.kind != "policy":
        return []
    from ..memory.authorization import source_granted

    view, _state = open_view()
    if view is None:
        return []
    try:
        hidden = []
        for artifact_id in ids:
            row = view.get_current_row(artifact_id)
            if row is not None and not source_granted(row["source"], access.sources):
                hidden.append(artifact_id)
        return hidden
    finally:
        view.close()


def _in_source_scope(
    access: MemoryAccess,
    candidates: list[dict[str, Any]],
    open_view: Callable[[], Any],
) -> list[dict[str, Any]]:
    """Policy mode: the candidates whose current row's source the grant approves
    (legacy mode keeps every owner-scoped candidate, as before)."""
    if access.kind != "policy" or not candidates:
        return candidates
    from ..memory.authorization import source_granted

    view, _state = open_view()
    if view is None:
        return []
    try:
        kept = []
        for candidate in candidates:
            row = view.get_current_row(str(candidate["id"]))
            if row is not None and source_granted(row["source"], access.sources):
                kept.append(candidate)
        return kept
    finally:
        view.close()


def _write_owner(owner: OwnerScope | None, access: MemoryAccess) -> OwnerScope | None:
    """The owner a new row is written under: the declared owner, else (policy
    mode) the resolved grant's owner, else the store's legacy default."""
    if owner is not None or access.kind != "policy":
        return owner
    return access.owner_scope


def _commit_check(access: MemoryAccess) -> Callable[[], tuple[str, str] | None]:
    """D1: the check every store mutation runs immediately before its commit."""
    return lambda: recheck_failure(access)


def _frozen_duration(started: float) -> int:
    return max(0, int((time.monotonic() - started) * 1000))


def _frame_scope(frame: compact.FrameContext) -> dict[str, Any]:
    """72-T02 D35: the executor's default scope, attached before any fit."""
    from ..invocation.executor import default_scope

    return default_scope({}, frame.context)


def _utf8_encodable(text: str) -> bool:
    try:
        text.encode("utf-8", "strict")
    except UnicodeEncodeError:
        return False
    return True


def _denial_data(operation: str, denial: RouteDenial) -> dict[str, Any]:
    return {
        "reason": denial.reason,
        "message": f"memory {operation} denied: {denial.reason}.",
    }


class _LazyTelemetry:
    """G3: a `TelemetryStore` constructed (by the route's own factory) only when an
    event is actually recorded."""

    def __init__(self, open_store: Callable[[], TelemetryStore]) -> None:
        self._open_store = open_store
        self._store: TelemetryStore | None = None

    def record_memory_event(self, *args: Any, **kwargs: Any) -> Any:
        if self._store is None:
            self._store = self._open_store()
        return self._store.record_memory_event(*args, **kwargs)


# --- T28-D: reviewed grants ----------------------------------------------------------
#
# A mutation request may pin the `ExecutionPermissions` grant names reviewed in its
# preview. Apply is refused, before any store is opened for writing, when the call's
# own permissions lack any of them.


def _reviewed_grants(request: dict[str, Any]) -> tuple[list[str] | None, str]:
    grants = request.get("required_grants")
    if grants is None:
        return None, ""
    if not isinstance(grants, list) or not all(
        isinstance(g, str) and g in _GRANT_NAMES for g in grants
    ):
        return None, f"required_grants must be a list of {sorted(_GRANT_NAMES)}."
    return list(grants), ""


def _missing_grants(grants: list[str], granted: ExecutionPermissions) -> list[str]:
    return [g for g in grants if not getattr(granted, g)]


def _grant_refusal_message(operation: str, missing: list[str]) -> str:
    return (
        f"memory {operation} apply refused: reviewed required_grants not granted: "
        f"{', '.join(missing)}."
    )


def _new_artifact_preview(
    artifact: MemoryArtifact,
    root: Path,
    grants: list[str] | None,
    granted: ExecutionPermissions,
) -> dict[str, Any]:
    """Read-only preview of a `write`/`promote` that would create a new row: no
    existing row is targeted (its id is minted at apply time), so `target_ids` and
    `expected_revisions` are empty."""
    owner = artifact.owner_scope or legacy_owner_scope(root)
    effective = grants if grants is not None else ["cache_write"]
    return {
        "apply": False,
        "target_ids": [],
        "expected_revisions": {},
        "owner_scope": {"kind": owner.kind, "id": owner.id},
        "required_grants": effective,
        "missing_grants": _missing_grants(effective, granted),
        "draft": {
            "family": artifact.family,
            "subject": artifact.subject,
            "trust_tier": artifact.trust_tier,
            "source": artifact.source,
            "symbol_ref": artifact.symbol_ref,
            "content": artifact.content,
        },
    }


# --- T19: memory attribution ---------------------------------------------------------
#
# `written` is every MemoryArtifact revision the operation committed (noted by the store
# only after each commit, so a denied, failed or preview-only mutation reports nothing).
# `used` is every artifact whose identity or content the operation's successful result
# actually returns -- after its own access checks, never an unreturned candidate.

_Ref = tuple[str, int, str | None]


def _ref(
    entry: Any, *, id_key: str = "id", version_key: str = "version"
) -> _Ref | None:
    if not isinstance(entry, dict):
        return None
    artifact_id = entry.get(id_key)
    version = entry.get(version_key)
    if not isinstance(artifact_id, str) or not isinstance(version, int):
        return None
    source = entry.get("source")
    return artifact_id, version, source if isinstance(source, str) else None


def _refs(entries: Any, **keys: str) -> list[_Ref]:
    if not isinstance(entries, list):
        return []
    return [
        ref for ref in (_ref(entry, **keys) for entry in entries) if ref is not None
    ]


def _plan_check_refs(data: dict[str, Any]) -> list[_Ref]:
    refs = [
        ref
        for check in data.get("checks") or []
        if isinstance(check, dict)
        for ref in _refs(check.get("refs"))
    ]
    refs.extend(
        ref
        for gap in data.get("coverage_gaps") or []
        if isinstance(gap, dict) and (ref := _ref(gap.get("ref"))) is not None
    )
    return refs


def _handoff_prepare_refs(data: dict[str, Any]) -> list[_Ref]:
    delta = data.get("delta") or {}
    constraints = delta.get("constraints") or {}
    return _refs(delta.get("changes")) + _refs(constraints.get("intent_refs"))


def _envelope_read_refs(operation: str, code: Any, data: dict[str, Any]) -> list[_Ref]:
    """The artifacts one successful envelope operation returned."""
    if operation in ("ask", "recall", "list", "related"):
        return _refs(data.get("items"))
    if operation == "expand":
        ref = _ref(data)
        return [ref] if code == "OK" and ref is not None else []
    if operation in ("prepare", "resume"):
        return _refs(data.get("evidence_refs"))
    if operation == "receive":
        return _refs(data.get("changes"))
    if operation == "handoff":
        return _handoff_prepare_refs(data)
    if operation == "last_success_diagnose":
        ref = _ref(data.get("baseline_ref"))
        return [ref] if ref is not None else []
    if operation == "plan_checks":
        return _plan_check_refs(data)
    if operation == "recipe" and "usable" in data:
        ref = _ref(data, id_key="recipe_id")
        return [ref] if ref is not None else []
    if operation == "intent":
        ref = _ref(data.get("evidence_ref"))
        return [ref] if ref is not None else []
    return []


def _read_refs(operation: str, result: ToolResult) -> list[_Ref]:
    if result.get("status") not in ("ok", "warn"):
        return []
    raw = result.get("raw")
    if isinstance(raw, list):
        # Legacy (`request=None`) ask/recall/list: the returned artifacts.
        return _refs(raw, version_key="artifact_version")
    if isinstance(raw, dict) and isinstance(raw.get("data"), dict):
        return _envelope_read_refs(operation, raw.get("code"), raw["data"])
    return []


_MUTATION_VIEW_OPERATIONS = frozenset({"write", "promote", "archive", "edit", "delete"})


def _with_mutation_view(
    root: Path, result: ToolResult, committed: list[dict[str, Any]]
) -> ToolResult:
    """T27: `changed` (the revisions this call committed, per id) plus
    `readback` (each changed id's current row, re-read after the write), or
    `unchanged` with the reason when nothing was committed. Added to
    `raw.data` for an operation envelope, else to `raw`."""
    raw = result.get("raw")
    if not isinstance(raw, dict):
        return result
    envelope = "operation" in raw and "data" in raw
    payload = raw["data"] if envelope else raw
    if not isinstance(payload, dict):
        return result
    view: dict[str, Any]
    if committed:
        changed: dict[str, dict[str, Any]] = {}
        for entry in committed:
            prior = changed.get(entry["id"])
            kind = (
                entry["kind"] if prior is None else f"{prior['kind']}, {entry['kind']}"
            )
            changed[entry["id"]] = {"revision": entry["revision"], "kind": kind}
        store = TypedArtifactStore(root)
        memories, _generation = store.snapshot_memories(include_internal=True)
        archived = {m["id"]: m["archived"] for m in memories if m["id"] in changed}
        view = {
            "changed": changed,
            "readback": {
                i: _readback_row(store.get_current(i), archived.get(i)) for i in changed
            },
        }
    elif payload.get("applied") is False:
        view = {"unchanged": "preview only (apply=false); nothing committed"}
    elif payload.get("promoted") is False:
        view = {"unchanged": f"promotion denied: {payload.get('denial_reason')}"}
    else:
        view = {"unchanged": str(payload.get("message") or result.get("summary"))}
    updated = {**payload, **view}
    new_raw = {**raw, "data": updated} if envelope else updated
    return cast(ToolResult, {**result, "raw": new_raw})


def _readback_row(
    artifact: MemoryArtifact | None, archived: bool | None
) -> dict[str, Any]:
    """`archived` comes from the archived-aware inventory reader
    (`snapshot_memories`); a row that reader no longer lists is not present."""
    if artifact is None or archived is None:
        return {"present": False}
    return {
        "present": True,
        "archived": archived,
        "revision": artifact.artifact_version,
        "subject": artifact.subject,
        "trust_tier": artifact.trust_tier,
        "source": artifact.source,
    }


def _memory_attribution(
    root: Path,
    operation: str,
    result: ToolResult,
    committed: list[dict[str, Any]],
) -> dict[str, Any] | None:
    """The operation name is the verb; `promote` keeps its two committed effects
    apart (candidate `write`, then `promote`)."""
    refs = _read_refs(operation, result)
    missing = [(i, v) for i, v, source in refs if source is None]
    sources = artifact_version_sources(root, missing) if missing else {}
    used = [
        memory_receipt(i, v, source or sources[(i, v)], operation)
        for i, v, source in refs
        if source is not None or (i, v) in sources
    ]
    written = [
        memory_receipt(
            entry["id"],
            entry["revision"],
            entry["source"],
            entry["kind"] if operation == "promote" else operation,
        )
        for entry in committed
    ]
    return memory_block(used, written)


# --- T20: bare `rush memory` read-only overview --------------------------------------
#
# A module function, deliberately not a `MemoryOperation`: the overview is a local-admin
# terminal browse, never an agent retrieval channel, so no MCP schema or restricted
# memory-session server can reach it (R20.1).

OVERVIEW_LIMIT = 20
_OVERVIEW_TOKEN_KEYS = {"v", "root", "generation", "filters", "limit"}


def _overview_token(root: str, generation: int, include_internal: bool) -> str:
    payload = {
        "v": 1,
        "root": root,
        "generation": generation,
        "filters": {"include_internal": include_internal},
        "limit": OVERVIEW_LIMIT,
    }
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _overview_token_error(
    token: str, root: str, include_internal: bool
) -> tuple[str, int | None]:
    """Validate a continuation token before any DB open. Returns `(reason, None)` on
    rejection, `("", generation)` when valid."""
    try:
        payload = json.loads(base64.urlsafe_b64decode(token + "=" * (-len(token) % 4)))
    except ValueError:
        return "malformed_token", None
    if not isinstance(payload, dict) or set(payload) != _OVERVIEW_TOKEN_KEYS:
        return "malformed_token", None
    filters = payload["filters"]
    generation = payload["generation"]
    if (
        type(payload["v"]) is not int
        or payload["v"] != 1
        or not isinstance(payload["root"], str)
        or type(generation) is not int
        or generation < 0
        or type(payload["limit"]) is not int
        or not isinstance(filters, dict)
        or set(filters) != {"include_internal"}
        or type(filters["include_internal"]) is not bool
    ):
        return "malformed_token", None
    if payload["root"] != root:
        return "project_mismatch", None
    if (
        filters["include_internal"] != include_internal
        or payload["limit"] != OVERVIEW_LIMIT
    ):
        return "filter_mismatch", None
    return "", generation


_OVERVIEW_REJECTIONS = {
    "token_required": "--offset greater than 0 requires --generation from a previous page",
    "malformed_token": "--generation is not a valid overview token",
    "project_mismatch": "--generation belongs to a different project",
    "filter_mismatch": "--generation was issued for different filters",
    "stale_generation": "memory changed since --generation was issued",
}


def memory_overview(
    root: Path,
    *,
    offset: int = 0,
    generation: str | None = None,
    include_internal: bool = False,
) -> ToolResult:
    """T20: the project's most recent useful memory rows, newest first, read-only.

    Excludes archived, expired and (unless `include_internal`) bookkeeping rows. Rows
    carry metadata only (no content, no author), with `source`/owner redacted. Paging is
    `offset` plus the `generation` token the previous page returned; a token for another
    project, other filters, or an older store generation is rejected with `E_INPUT` and
    a restart-at-offset-0 hint. Never creates or modifies any file."""
    from ..safety.redactor import sanitize_value
    from ..workflows.projects import ProjectNotFoundError, resolve_project

    started = time.monotonic()
    tool = MemoryTool()
    try:
        canonical = Path(resolve_project(root)["root"])
    except ProjectNotFoundError:
        canonical = Path(root).resolve()
    canonical_str = str(canonical)
    db = canonical / ".rush" / "memory.db"

    def _reject(reason: str) -> ToolResult:
        message = (
            f"{_OVERVIEW_REJECTIONS[reason]}; restart with `rush memory` at offset 0."
        )
        return tool._envelope_result(
            started,
            "overview",
            "E_INPUT",
            {"message": message, "reason": reason, "restart": {"offset": 0}},
        )

    def _fail(code: str, reason: str, message: str) -> ToolResult:
        return tool._envelope_result(
            started,
            "overview",
            code,
            sanitize_value(
                {"message": message, "reason": reason, "restart": {"offset": 0}}
            ).value,
        )

    from ..memory.retrieval import RouteDenial, reader_row_allowed, route_access

    # 72-T01 D1 `list`: the overview reads the project's memory rows, so its access is
    # resolved before any store is opened. `policy` mode lists only the grant owner's
    # rows of approved sources (and counts only those); a denial lists nothing.
    access = route_access(canonical, "list")
    if isinstance(access, RouteDenial):
        return _fail(
            access.code, access.reason, f"memory overview denied: {access.reason}"
        )
    policy_access = access if access.kind == "policy" else None

    token_generation: int | None = None
    if generation is not None:
        reason, token_generation = _overview_token_error(
            generation, canonical_str, include_internal
        )
        if reason:
            return _reject(reason)
    elif offset > 0:
        return _reject("token_required")

    opened = TypedArtifactStore.open_readonly(canonical)
    if opened.state is not None:
        code = readonly_state_code(opened.state, db)
        state = "corrupt" if code == "E_STORE_CORRUPT" else "busy"
        return _fail(code, f"store_{state}", readonly_view_reason(state))
    if opened.migration_required:
        return _fail(
            "E_SCHEMA_UNSUPPORTED",
            "migration_required",
            readonly_view_reason("migration_required"),
        )

    rows: list[dict[str, Any]] = []
    total = hidden_internal = current_generation = 0
    reason_text: str | None = None
    conn = opened.connection
    if conn is None:
        if token_generation not in (None, 0):
            return _reject("stale_generation")
        reason_text = f"no memory store at {db}"
    else:
        try:
            conn.execute("BEGIN")
            columns = {
                row["name"]
                for row in conn.execute("PRAGMA table_info(memory_artifacts)")
            }
            current_generation = store_generation(conn)
            if token_generation is not None and token_generation != current_generation:
                conn.rollback()
                return _reject("stale_generation")
            live = [
                f"{c} IS NULL" for c in ("archived_at", "expired_at") if c in columns
            ]
            internal_sql, internal_params = internal_source_exclusion_sql()
            where = live if include_internal else [*live, internal_sql]
            params: tuple[str, ...] = () if include_internal else internal_params
            where_sql = f"WHERE {' AND '.join(where)}" if where else ""
            owner_columns = [
                c for c in ("owner_scope_kind", "owner_scope_id") if c in columns
            ]
            selected = ", ".join(
                ["id", "subject", "source", "created_at", "trust_tier", *owner_columns]
            )
            if policy_access is None:
                total = int(
                    conn.execute(
                        f"SELECT COUNT(*) FROM memory_artifacts {where_sql}", params
                    ).fetchone()[0]
                )
                page = conn.execute(
                    f"SELECT {selected} FROM memory_artifacts {where_sql} "
                    "ORDER BY created_at DESC, id DESC LIMIT ? OFFSET ?",
                    (*params, OVERVIEW_LIMIT, offset),
                ).fetchall()
            else:
                allowed = [
                    row
                    for row in conn.execute(
                        f"SELECT {selected} FROM memory_artifacts {where_sql} "
                        "ORDER BY created_at DESC, id DESC",
                        params,
                    ).fetchall()
                    if reader_row_allowed(policy_access, canonical, row)
                ]
                total = len(allowed)
                page = allowed[offset : offset + OVERVIEW_LIMIT]
            if not include_internal:
                hidden_where = " AND ".join([*live, f"NOT ({internal_sql})"])
                if policy_access is None:
                    hidden_internal = int(
                        conn.execute(
                            "SELECT COUNT(*) FROM memory_artifacts "
                            f"WHERE {hidden_where}",
                            internal_params,
                        ).fetchone()[0]
                    )
                else:
                    hidden_internal = sum(
                        1
                        for row in conn.execute(
                            f"SELECT {selected} FROM memory_artifacts "
                            f"WHERE {hidden_where}",
                            internal_params,
                        ).fetchall()
                        if reader_row_allowed(policy_access, canonical, row)
                    )
            conn.commit()
        except sqlite3.OperationalError as exc:
            if "locked" in str(exc) or "busy" in str(exc):
                return _fail(
                    "E_STORE_BUSY", "store_busy", f"{db} is busy: {exc}; retry."
                )
            return _fail(
                "E_STORE_CORRUPT", "store_corrupt", f"{db} is unreadable: {exc}"
            )
        except sqlite3.DatabaseError as exc:
            return _fail(
                "E_STORE_CORRUPT", "store_corrupt", f"{db} is unreadable: {exc}"
            )
        finally:
            conn.close()
        rows = [
            {
                "id": row["id"],
                "subject": row["subject"],
                "source": row["source"],
                "owner_scope": owner_scope_for_row(row, canonical).as_dict(),
                "created_at": row["created_at"],
                "trust_tier": row["trust_tier"],
            }
            for row in page
        ]
        if total == 0:
            reason_text = (
                "no memory records"
                if include_internal
                else f"no useful memory records; {hidden_internal} internal record(s) "
                "hidden (use --include-internal to show them)"
            )

    end = offset + len(rows)
    data: dict[str, Any] = {
        "project_root": canonical_str,
        "total": total,
        "offset": offset,
        "limit": OVERVIEW_LIMIT,
        "include_internal": include_internal,
        "rows": rows,
        "next_offset": end if rows and end < total else None,
    }
    if not include_internal:
        data["hidden_internal"] = hidden_internal
    if reason_text is not None:
        data["reason"] = reason_text
    data = sanitize_value(data).value
    # Added after redaction: the token is opaque base64 and must round-trip byte-exact.
    data["generation_token"] = _overview_token(
        canonical_str, current_generation, include_internal
    )
    # D1 race rule: a `list` grant revoked or changed during selection or response
    # construction returns the denial, never the rows, counts or token.
    failure = recheck_failure(access)
    if failure is not None:
        return _fail(failure[0], failure[1], f"memory overview denied: {failure[1]}")
    return tool._envelope_result(started, "overview", "OK", data)
