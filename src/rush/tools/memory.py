"""Cross-tool memory query/write tool used by the CLI and MCP transports (Phase 61 P61.12)."""

from __future__ import annotations

import base64
import copy
import dataclasses
import functools
import hashlib
import json
import os
import sqlite3
import time
import unicodedata
import uuid
from collections.abc import Callable, Iterator, Mapping, Sequence
from contextlib import ExitStack, contextmanager
from contextvars import ContextVar
from pathlib import Path
from typing import Any, ClassVar, Literal, cast, get_args

from ..config import RushConfigError, load_config
from ..delivery import compact
from ..invocation.models import InvocationContext
from ..memory import embeddings as _embeddings
from ..memory import retrieval as _retrieval
from ..memory.consolidation import consolidate_episodes
from ..memory.embeddings import (
    EmbeddingConfig,
    EmbeddingEngineTimeout,
    EmbeddingEngineUnavailable,
    EmbeddingResponseError,
    config_endpoint_ok,
    request_endpoint_error,
    valid_chunking,
    valid_digest,
    valid_model,
)
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
    FALLBACK_REASONS,
    NOT_CURRENT_REASONS,
    FrameBytes,
    MemoryAccess,
    MixedFrame,
    RouteDenial,
    SourceValidationMemo,
    _access_allows,
    _count_tokens,
    _fit_optional,
    _frame_tokens,
    _measure_page,
    _source_input_denial,
    evaluate_artifact_visibility,
    expand_admission,
    expand_artifact,
    hybrid_admission,
    hybrid_page,
    memory_policy_decision,
    memory_policy_mode,
    recall_admission,
    recall_page,
    recheck_failure,
    required_operation_set,
    route_access,
    v2_reference,
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
    sqlite_integer_in_range,
    store_generation,
    v2_operation_id,
)
from ..memory.trust import default_entry_tier, evaluate_conflict
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
    "preference",
    "history",
    "explain",
    "capsule",
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
    "preference",
    "history",
    "explain",
    "capsule",
}
# 72-T05 §3.11: the task context of the `run` in progress. Every access a handler
# builds reads it (`task_id=_TASK_ID.get()`); `run` sets and resets it.
_TASK_ID: ContextVar[str | None] = ContextVar("rush_memory_task_id", default=None)
_OVERLAY_REFUSED_OPERATIONS = frozenset(
    {"write", "promote", "edit", "link", "consolidate", "maintain"}
)
# 73-T09/CODEC: the handler-side `capsule` request keys (the CLI and in-process
# paths validate against these; `rush.memory.capsule` reads this one definition).
_CAPSULE_REQUEST_KEYS = frozenset(
    {
        "action",
        "format",
        "input",
        "output",
        "max_bytes",
        "max_tokens",
        "mapping_id",
        "expected_digest",
        "expected_store_revision",
        "confirm_constraint_ids",
        "apply",
        "invocation_id",
        "selectors",
    }
)
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

# 72-T07: the one presentation state every memory surface (CLI, TUI, dashboard) shows
# for a result, in the order the classifier reports them.
MEMORY_UI_STATES: tuple[str, ...] = (
    "server_error",
    "absent",
    "migration_required",
    "corrupt",
    "busy",
    "conflict",
    "restart",
    "partial",
    "not_visible",
    "invalid",
    "revoked",
    "expired",
    "denied",
    "digest_mismatch",
    "empty",
    "ok",
)
_UI_ACTIONS: dict[str, str] = {
    "server_error": "retry the request; if it fails again run rush doctor",
    "absent": (
        "no memory store yet: record one with rush memory write SUBJECT SOURCE "
        "--content JSON --allow-cache-write"
    ),
    "migration_required": (
        "run any rush memory write command to migrate the store, then refresh"
    ),
    "corrupt": "move .rush/memory.db aside or restore it from a backup, then refresh",
    "busy": "a writer holds the store; retry in a moment",
    "conflict": (
        "the record changed since you reviewed it; refresh, review the current "
        "version, then apply again"
    ),
    "restart": "access changed during the request; refresh to restart from the first page",
    "partial": "more results exist: open the next page",
    "not_visible": (
        "the record is not visible to your grant (deleted, archived, expired or "
        "another owner); refresh the list"
    ),
    "invalid": "fix the field named in the reason and retry",
    "revoked": (
        "the grant was revoked; ask the project owner to grant memory access again "
        "(rush memory grant)"
    ),
    "expired": "the grant expired; renew it with rush memory grant --expires-at TIME",
    "denied": "request access with rush memory grant",
    "digest_mismatch": (
        "content bytes do not match the recorded payload hash; content withheld; "
        "refresh and expand again"
    ),
    "empty": "no records match; change the subject, query or filters",
    "ok": "select a record to inspect, see history or correct it",
}
_UI_SKIPPED_ACTION = "name a source: rerun with --source SOURCE"
_UI_BUDGET_ACTION = (
    "raise --max-bytes/--max-tokens to the reported minimum or request a smaller page"
)
# `complete: false` on these is a committed receipt, never a partial page.
_UI_MUTATIONS = frozenset(
    {
        "write",
        "promote",
        "maintain",
        "link",
        "consolidate",
        "handoff",
        "receive",
        "delete",
        "edit",
        "archive",
        "verify_attempt",
    }
)
_UI_STORE_STATES = ("absent", "migration_required", "corrupt", "busy")
_UI_COLLECTIONS = frozenset({"ask", "list", "recall", "related", "history", "overview"})


def _ui_row(item: Mapping[str, Any]) -> dict[str, Any]:
    ref = item.get("reference")
    ref = ref if isinstance(ref, Mapping) else {}
    badges: list[str] = []
    freshness = ref.get("freshness", item.get("freshness"))
    if freshness in ("stale", "unknown"):
        badges.append(str(freshness))
    elif item.get("stale") is True:
        badges.append("stale")
    integrity = ref.get("integrity")
    if integrity in ("backfilled", "unbound", "mismatch"):
        badges.append(f"integrity:{integrity}")
    reason_codes = item.get("reason_codes")
    applicability = item.get("applicability", ref.get("applicability"))
    if applicability not in ("pending", "rejected", "superseded") and isinstance(
        reason_codes, list | tuple
    ):
        # A schema-2 item carries no `applicability` key (its reference keys are
        # pinned); the exclusion reason `applicability_<state>` names it.
        for state in ("pending", "rejected", "superseded"):
            if f"applicability_{state}" in reason_codes:
                applicability = state
                break
    if applicability in ("pending", "rejected", "superseded"):
        badges.append(str(applicability))
    if item.get("expired") is True or (
        isinstance(reason_codes, list | tuple) and "expired" in reason_codes
    ):
        badges.append("expired")
    if item.get("archived") is True or item.get("archived_at"):
        badges.append("archived")
    return {
        "artifact_id": ref.get("artifact_id", item.get("id")),
        "artifact_version": ref.get(
            "artifact_version", item.get("artifact_version", item.get("version"))
        ),
        "badges": badges,
    }


def memory_ui_state(
    result: Mapping[str, Any] | None,
    *,
    store_state: str | None = None,
    http_status: int | None = None,
    error: BaseException | None = None,
    observed_payload_sha256: str | None = None,
) -> dict[str, Any]:
    """72-T07: classify a memory result (or a store state, an HTTP status, an
    exception) into one of `MEMORY_UI_STATES` with its reason, the one action the
    user can take, the producer's `next_action` (D16) and per-row badges. A denial
    in `result` wins over `store_state`: a refused read is never shown as absent."""
    result_map: Mapping[str, Any] = result if isinstance(result, Mapping) else {}
    raw = result_map.get("raw")
    raw_map: Mapping[str, Any] = raw if isinstance(raw, Mapping) else {}
    code = raw_map.get("code")
    data = raw_map.get("data")
    data_map: Mapping[str, Any] = data if isinstance(data, Mapping) else {}
    status = result_map.get("status")
    operation = raw_map.get("operation")
    reason_value = (
        raw_map.get("reason")
        or data_map.get("reason")
        or data_map.get("message")
        or result_map.get("summary")
    )
    reason = "" if reason_value is None else str(reason_value)
    items: list[Any] = []
    # Only a listing read can be `empty`; a single-record read or a receipt with no
    # rows (a legacy expand, a mutation) is judged by its data, not its row count.
    collection = not isinstance(operation, str) or operation in _UI_COLLECTIONS
    if isinstance(raw_map.get("versions"), list):
        items = list(raw_map["versions"])
    elif isinstance(raw_map.get("items"), list):
        items = list(raw_map["items"])
    elif isinstance(data_map.get("items"), list):
        items = list(data_map["items"])
    elif isinstance(raw, list):
        items = list(raw)
    else:
        collection = False
    complete = raw_map.get("complete", data_map.get("complete"))
    guidance = raw_map.get("next_action")
    next_action = dict(guidance) if isinstance(guidance, Mapping) else None

    def classify() -> tuple[str, str]:
        if error is not None:
            return "server_error", f"{type(error).__name__}: {error}"
        # A denial precedes any store state: a refused read never reads as absent.
        if code == "E_PERMISSION" and reason in ("revoked", "expired"):
            return reason, reason
        if code in ("E_PERMISSION", "E_OWNER", "E_SCOPE"):
            return "denied", reason
        if result is None and store_state is None:
            return "server_error", "no result"
        if store_state in _UI_STORE_STATES:
            if store_state == "absent":
                return "absent", "no memory store exists for this project"
            return store_state, readonly_view_reason(store_state)  # type: ignore[arg-type]
        if code in ("E_MIGRATION", "E_SCHEMA_UNSUPPORTED"):
            return "migration_required", reason
        if code == "E_STORE_CORRUPT":
            return "corrupt", reason
        if code == "E_STORE_BUSY":
            return "busy", reason
        if code == "E_VERSION" or (code is None and http_status == 409):
            return "conflict", reason
        if code == "E_RESTART":
            return "restart", reason
        if code in ("E_BUDGET", "E_EMBEDDING_UNAVAILABLE", "UNRESOLVED"):
            return "partial", reason
        if code == "E_NOT_VISIBLE" or (code is None and http_status == 404):
            return "not_visible", reason
        if code in ("E_INPUT", "E_OFFSET") or (code is None and http_status == 400):
            return "invalid", reason
        if code is None and http_status in (401, 403):
            return "denied", reason
        if (code is not None and code != "OK") or (
            code is None
            and http_status is not None
            and http_status >= 500
            and status != "skipped"
        ):
            return "server_error", reason
        if code is None and status == "skipped":
            return "denied", reason
        if code is None and status == "error":
            return "invalid", reason
        if code is None and status == "warn":
            return "partial", reason
        if code is None and status == "fail":
            return "denied", reason
        # OK: the digest, then emptiness, then page completeness. A v2 expansion
        # carries its page and recorded hash in raw.items[0]; legacy in raw.data.
        recorded = data_map.get("payload_hash")
        integrity = data_map.get("integrity")
        if operation == "expand" and items and isinstance(items[0], Mapping):
            page = items[0]
            ref = page.get("reference")
            ref_map: Mapping[str, Any] = ref if isinstance(ref, Mapping) else {}
            recorded = ref_map.get("payload_hash", recorded)
            integrity = page.get("integrity", ref_map.get("integrity", integrity))
        if (
            observed_payload_sha256 is not None and observed_payload_sha256 != recorded
        ) or integrity == "mismatch":
            return "digest_mismatch", reason
        if collection and not items and complete is not False:
            return "empty", reason
        if complete is False and operation not in _UI_MUTATIONS:
            return "partial", reason
        return "ok", reason

    state, reason = classify()
    action = _UI_ACTIONS[state]
    if state == "denied" and code is None and status == "skipped":
        action = _UI_SKIPPED_ACTION
    elif state == "partial" and code == "E_BUDGET":
        required = data_map.get("required")
        action = _UI_BUDGET_ACTION + (
            f" (required {json.dumps(required, sort_keys=True)})"
            if required is not None
            else ""
        )
    if (
        state in ("revoked", "expired", "denied")
        and next_action is not None
        and isinstance(next_action.get("text"), str)
        and next_action["text"]
    ):
        action = next_action["text"]
    return {
        "state": state,
        "reason": reason,
        "action": action,
        "next_action": next_action,
        "rows": [_ui_row(item) for item in items if isinstance(item, Mapping)],
    }


def memory_view_authority(
    access: MemoryAccess | None, generation: int | None
) -> dict[str, Any]:
    """72-T07: the authority a memory view was produced under (D37): the grant
    fields, the owner, the sorted sources and the store generation. A denied or
    unavailable route has every field `None`."""
    if access is None:
        return dict.fromkeys(
            (
                "policy_revision",
                "grant_id",
                "project_id",
                "worktree_id",
                "owner_scope",
                "sources",
                "store_generation",
            )
        )
    owner = access.owner_scope
    return {
        "policy_revision": access.policy_revision,
        "grant_id": access.grant_id,
        "project_id": access.project_id,
        "worktree_id": access.worktree_id,
        "owner_scope": None if owner is None else {"kind": owner.kind, "id": owner.id},
        "sources": sorted(access.sources),
        "store_generation": generation,
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
# 72-T08: the engine identity a request field or `[tools.memory]` option supplies.
_EMBEDDING_OPTION_KEYS = (
    "embedding_endpoint",
    "embedding_model",
    "embedding_model_digest",
)


def _fallback_labels(code: str, embedded_texts: int) -> dict[str, Any]:
    """72-T08 §3.7 `L(c, n)`: the labels of a hybrid-requested read answered lexically."""
    return {
        "retrieval": "lexical",
        "embedding_status": "skipped",
        "embedding_fallback_code": code,
        "hybrid_unavailable_reason": FALLBACK_REASONS[code],
        "embedded_texts": embedded_texts,
    }


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


# --- 72-T06: schema_version 2 constants ----------------------------------------------


@dataclasses.dataclass(frozen=True, repr=False)
class _Unset:
    """A legacy `run`/`__call__` parameter the caller did not supply. Presence, not
    value, decides a mixed v2 form: an explicit `query=""` beside `schema_version` is
    still a legacy field. (A field-less dataclass, so a signature-derived schema can
    serialize it as a default.)"""

    def __repr__(self) -> str:
        return "<unset>"

    # A schema builder deep-copies defaults; the sentinel stays one object.
    def __copy__(self) -> _Unset:
        return self

    def __deepcopy__(self, memo: dict[int, Any]) -> _Unset:
        return self


_UNSET: Any = _Unset()
# The public (and legacy-branch) default of every sentinel-defaulted parameter.
_LEGACY_DEFAULTS: dict[str, Any] = {
    "subject": None,
    "query": "",
    "session_allowlist": None,
    "content": None,
    "source": "",
    "symbol_ref": None,
    "source_kind": "local_tool",
    "user_stated": False,
    "candidate_sources": None,
    "task": None,
    "batch_size": 500,
    "include_archived": False,
    "owner_scope": None,
}
_V2_READ_OPERATIONS = frozenset({"ask", "recall", "list"})
_V2_MUTATIONS = frozenset(
    {"write", "edit", "archive", "delete", "promote", "maintain", "link"}
)
_V2_OPERATIONS = (
    _V2_READ_OPERATIONS
    | _V2_MUTATIONS
    | {
        "expand",
        "related",
        "history",
        "explain",
    }
)
# 72-T05 decision: overlay content changes go through the preference route.
_OVERLAY_PREFERENCE_ONLY = frozenset({"write", "edit", "promote", "link", "maintain"})
# D22: the operations a restricted memory-session bridge may forward.
_BRIDGE_OPERATIONS = frozenset({"receive", "expand", "related", "resume"})
# D38 explain buckets.
_SUPPORTING_KINDS = frozenset(
    {"validated_by", "implements", "depends_on", "caused_by", "fixed_by"}
)
_ATTEMPT_SUBJECTS = frozenset({"failure", "episodic"})


def _is_v2_call(operation: Any, request: Any) -> bool:
    """72-T06: a schema_version 2 call (`history`/`explain` exist only in v2)."""
    if not isinstance(operation, str):
        return False
    if operation in ("history", "explain"):
        return True
    return (
        operation in _V2_OPERATIONS
        and isinstance(request, dict)
        and "schema_version" in request
    )


def _v2_raw(
    operation: str,
    code: str,
    *,
    items: Any = (),
    next_cursor: str | None = None,
    complete: bool = False,
    unknowns: Any = (),
    data: dict[str, Any] | None = None,
    **named: Any,
) -> dict[str, Any]:
    """The schema_version 2 result envelope (`ToolResult.raw`)."""
    return {
        "schema_version": 2,
        "operation": operation,
        "code": code,
        "items": list(items),
        "next_cursor": next_cursor,
        "complete": complete,
        "unknowns": sorted(set(unknowns)),
        "data": dict(data or {}),
        **named,
    }


@dataclasses.dataclass(frozen=True)
class _V2Call:
    """One validated schema_version 2 call."""

    started: float
    root: Path
    operation: str
    req: Any
    granted: ExecutionPermissions
    task_id: str | None
    attribution: dict[str, Any]
    # 72-T06 D35: the transport frame and the duration frozen once for this call, so
    # admission, every page fit and the emitted envelope measure the same bytes.
    frame: compact.FrameContext | None = None
    frozen: int | None = None

    @property
    def echo(self) -> dict[str, Any]:
        """The caller's reviewed request, returned unchanged on a refusal."""
        return cast(
            dict[str, Any], self.req.model_dump(mode="json", exclude_unset=True)
        )


class MemoryTool(ToolFn):
    """Query, write, and promote cross-LLM memory artifacts through one result contract."""

    name = "memory"
    # 73-T09/CODEC: the caller's transport is bound by the invocation, never by a
    # request field, and is not published in the MCP schema.
    internal_parameters: ClassVar[frozenset[str]] = frozenset({"transport"})

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
        # 72-T06: legacy parameters default to a presence sentinel (public defaults:
        # `_LEGACY_DEFAULTS`); only supplied ones reach `run`.
        subject: MemorySubject | None = _UNSET,
        query: str = _UNSET,
        session_allowlist: list[str] | None = _UNSET,
        content: dict[str, Any] | None = _UNSET,
        source: str = _UNSET,
        symbol_ref: str | None = _UNSET,
        source_kind: SourceKind = _UNSET,
        user_stated: bool = _UNSET,
        candidate_sources: list[str] | None = _UNSET,
        task: MaintenanceTask | None = _UNSET,
        batch_size: int = _UNSET,
        include_archived: bool = _UNSET,
        owner_scope: dict[str, str] | OwnerScope | None = _UNSET,
        sources: list[str] | None = _UNSET,
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
        task_id: str | None = None,
        transport: Literal["cli", "mcp"] = "cli",
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
            sources=sources,
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
            task_id=task_id,
            transport=transport,
        )

    def run(
        self,
        path: Path,
        *,
        operation: MemoryOperation = "ask",
        subject: MemorySubject | None = _UNSET,
        query: str = _UNSET,
        session_allowlist: list[str] | None = _UNSET,
        content: dict[str, Any] | None = _UNSET,
        source: str = _UNSET,
        symbol_ref: str | None = _UNSET,
        source_kind: SourceKind = _UNSET,
        user_stated: bool = _UNSET,
        candidate_sources: list[str] | None = _UNSET,
        task: MaintenanceTask | None = _UNSET,
        batch_size: int = _UNSET,
        include_archived: bool = _UNSET,
        owner_scope: dict[str, str] | OwnerScope | None = _UNSET,
        sources: list[str] | None = _UNSET,
        permissions: ExecutionPermissions | None = None,
        request: dict[str, Any] | None = None,
        receipt_operation_ids: dict[str, str] | None = None,
        invocation_id: str | None = None,
        project_id: str | None = None,
        run_id: str | None = None,
        agent_id: str | None = None,
        session_id: str | None = None,
        trust_filter: str | None = None,
        source_filter: str | None = None,
        freshness_filter: str | None = None,
        archived_filter: bool | None = None,
        owner_filter: str | None = None,
        task_id: str | None = None,
        bridge_authority: _BridgeAuthority | None = None,
        frame: compact.FrameContext | None = None,
        transport: Literal["cli", "mcp"] = "cli",
    ) -> ToolResult:
        """The one canonical memory route (CLI, MCP, dashboard, TUI).

        72-T06: a `schema_version` 2 request (and every `history`/`explain`) runs the
        strict v2 path; a legacy parameter supplied beside it -- even at its legacy
        default value -- is a mixed form (`E_INPUT`). Legacy calls keep their exact
        behavior, with omitted parameters at their legacy defaults.
        `bridge_authority` is internal (D22): the restricted session bridge's resolved
        access and the session's selected ids."""
        supplied: dict[str, Any] = {
            name: value
            for name, value in (
                ("subject", subject),
                ("query", query),
                ("session_allowlist", session_allowlist),
                ("content", content),
                ("source", source),
                ("symbol_ref", symbol_ref),
                ("source_kind", source_kind),
                ("user_stated", user_stated),
                ("candidate_sources", candidate_sources),
                ("task", task),
                ("batch_size", batch_size),
                ("include_archived", include_archived),
                ("owner_scope", owner_scope),
                ("sources", sources),
            )
            if not isinstance(value, _Unset)
        }
        filters: dict[str, Any] = {
            "trust_filter": trust_filter,
            "source_filter": source_filter,
            "freshness_filter": freshness_filter,
            "archived_filter": archived_filter,
            "owner_filter": owner_filter,
        }
        attribution: dict[str, Any] = {
            "invocation_id": invocation_id,
            "project_id": project_id,
            "run_id": run_id,
            "agent_id": agent_id,
            "session_id": session_id,
        }
        if not isinstance(operation, str):
            # An unhashable or non-string operation is an unsupported operation.
            return self._result(
                time.monotonic(),
                "error",
                f"Unsupported memory operation: {operation!r}.",
                operation=str(operation),
            )
        carries_version = isinstance(request, dict) and "schema_version" in request
        if bridge_authority is not None and carries_version:
            return self._v2_wrap(
                time.monotonic(),
                str(operation),
                _v2_raw(
                    str(operation),
                    "E_INPUT",
                    data={
                        "field": "schema_version",
                        "message": "the restricted memory session takes legacy "
                        "requests only",
                    },
                ),
            )
        if (
            carries_version
            and operation in VALID_OPERATIONS
            and operation not in _V2_OPERATIONS
        ):
            return self._v2_wrap(
                time.monotonic(), str(operation), _non_v2_rejection(str(operation))
            )
        if _is_v2_call(operation, request):
            started = time.monotonic()
            if bridge_authority is not None:
                return self._v2_wrap(
                    started,
                    str(operation),
                    _v2_raw(
                        str(operation),
                        "E_INPUT",
                        data={
                            "field": "schema_version",
                            "message": "the restricted memory session takes legacy "
                            "requests only",
                        },
                    ),
                )
            top_level: dict[str, Any] = dict(supplied)
            if receipt_operation_ids is not None:
                top_level["receipt_operation_ids"] = receipt_operation_ids
            top_level.update({k: v for k, v in filters.items() if v is not None})
            if task_id is not None:
                top_level["task_id"] = task_id
            return self._v2_dispatch(
                started,
                path,
                str(operation),
                request,
                top_level,
                permissions or ExecutionPermissions(),
                task_id=task_id,
                attribution=attribution,
                frame=frame,
            )
        return self._run_legacy(
            path,
            operation=operation,
            **supplied,
            permissions=permissions,
            request=request,
            receipt_operation_ids=receipt_operation_ids,
            **attribution,
            **filters,
            bridge=bridge_authority,
            frame=frame,
            task_id=task_id,
            transport=transport,
        )

    def _run_legacy(
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
        # 72-T04 D3: `maintain`'s explicit source list (the legacy-mode access, a
        # narrowing of the grant in policy mode); any other operation refuses it.
        sources: list[str] | None = None,
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
        bridge: _BridgeAuthority | None = None,
        # 72-T02 D35: the response's transport frame; omitted, the frame a transport
        # adapter published (`compact.MEMORY_FRAME`), else payload measurement.
        frame: compact.FrameContext | None = None,
        task_id: str | None = None,
        transport: Literal["cli", "mcp"] = "cli",
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
        if sources is not None and operation != "maintain":
            return self._envelope_result(
                started,
                str(operation),
                "E_INPUT",
                {"field": "sources", "message": "sources is a maintain field"},
            )
        if task_id is not None and not _valid_task_id(task_id):
            return self._envelope_result(
                started,
                str(operation),
                "E_INPUT",
                {
                    "field": "task_id",
                    "reason": "task_id_invalid",
                    "message": "task_id must be a non-empty string without "
                    "control characters.",
                },
            )
        # D25 / plan A2: only the preference route writes personal content; these
        # routes refuse the overlay owner before any resolution or construction.
        overlay_owner = _overlay_owner_named(owner_scope, request)
        if operation in _OVERLAY_REFUSED_OPERATIONS and overlay_owner is not None:
            # D1 row 1a (an overlay storage root as the project) still answers first.
            mode, why = memory_policy_decision(root)
            return self._denied(
                started,
                operation,
                RouteDenial("E_PERMISSION", why or "policy_invalid")
                if mode == "unavailable"
                else RouteDenial("E_OWNER", "overlay_requires_preference_route"),
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
        reserved = _reserved_receipt_field(operation, request, receipt_operation_ids)
        if reserved is not None:
            return self._envelope_result(
                started,
                operation,
                "E_INPUT",
                {
                    "field": reserved,
                    "reason": "reserved_receipt_namespace",
                    "message": f"{reserved} values starting 'v2:' are reserved.",
                },
            )
        if bridge is not None and operation not in _BRIDGE_OPERATIONS:
            return self._denied(
                started, operation, RouteDenial("E_PERMISSION", "operation_not_granted")
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
                bridge=bridge,
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
                started,
                root,
                task,
                batch_size,
                granted,
                owner_scope,
                request,
                sources,
                session_allowlist,
            ),
            "link": lambda: self._link(started, root, granted, request, owner_scope),
            "related": lambda: self._related(
                started, root, session_allowlist, request, owner_scope, bridge=bridge
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
                bridge=bridge,
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
            "preference": lambda: self._preference(
                started, root, granted, request, session_allowlist
            ),
            "capsule": lambda: self._capsule(
                started, root, granted, request, transport
            ),
        }
        token = _TASK_ID.set(task_id)
        try:
            with collect_committed_writes() as committed:
                result = dispatch_table[operation]()
            if operation == "preference":
                _personal_layer_guidance(result, root)
        except (MemoryAccessChanged, MemoryWriteDenied) as exc:
            # D1 race rule: the access changed before the commit; nothing committed.
            return self._denied(started, operation, RouteDenial(exc.code, exc.reason))
        finally:
            _TASK_ID.reset(token)
        if operation in _MUTATION_VIEW_OPERATIONS:
            # D25: an overlay-owner archive/delete changed the overlay store.
            view_root = root if overlay_owner is None else Path(overlay_owner.id)
            result = _with_mutation_view(view_root, result, committed)
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

    # --- 72-T06: schema_version 2 -------------------------------------------------

    def _v2_wrap(
        self,
        started: float,
        operation: str,
        raw: dict[str, Any],
        duration_ms: int | None = None,
    ) -> ToolResult:
        code = str(raw.get("code"))
        return ToolResult(
            tool=self.name,
            engine=None,
            engine_version=None,
            status=_CODE_STATUS.get(code, "error"),  # type: ignore[typeddict-item]
            duration_ms=duration_ms
            if duration_ms is not None
            else max(0, int((time.monotonic() - started) * 1000)),
            summary=f"memory {operation} returned {code}.",
            findings=[],
            raw=raw,
            metadata={"operation": operation},
        )

    def _v2_out(self, call: _V2Call, code: str, **fields: Any) -> ToolResult:
        """A v2 result. A mutation refusal or conflict returns the reviewed request."""
        data = dict(fields.pop("data", None) or {})
        if code != "OK" and call.operation in _V2_MUTATIONS:
            data["request"] = call.echo
        return self._v2_wrap(
            call.started,
            call.operation,
            _v2_raw(call.operation, code, data=data, **fields),
            duration_ms=call.frozen,
        )

    def _v2_fit(self, call: _V2Call) -> FrameBytes | None:
        """72-T06 D35: the exact bytes the call's transport writes for a v2 page of
        `(code, data)` -- the same object `_v2_page` returns, so every fit is the
        emitted frame. `None` outside a transport frame, and when the caller supplied
        neither cap (payload measurement: a default-cap page is identical on every
        transport). With one cap supplied, that cap is measured on the frame and the
        defaulted one on the payload (`MixedFrame`)."""
        frame = call.frame
        if frame is None:
            return None
        supplied = (
            "max_bytes" in call.req.model_fields_set,
            "max_tokens" in call.req.model_fields_set,
        )
        if not any(supplied):
            return None
        payload_frame = compact.FrameContext("in_process", None, context=frame.context)

        def build(code: str, data: dict[str, Any]) -> Any:
            body = dict(data)
            items = body.pop("items", None) or []
            next_cursor = body.pop("next_cursor", None)
            complete = bool(body.pop("complete", False)) and code in {
                "OK",
                "E_EMBEDDING_UNAVAILABLE",
            }
            result = self._v2_wrap(
                call.started,
                call.operation,
                _v2_raw(
                    call.operation,
                    code,
                    items=items,
                    next_cursor=next_cursor,
                    complete=complete,
                    data=body,
                ),
                duration_ms=call.frozen,
            )
            if frame.context is not None:
                result["metadata"] = {
                    **(result.get("metadata") or {}),
                    "scope": _frame_scope(frame),
                }
            return attach_memory_attribution(
                result, _memory_attribution(call.root, call.operation, result, [])
            )

        def fit(code: str, data: dict[str, Any]) -> bytes:
            return compact.frame_bytes(frame, build(code, data))

        if all(supplied):
            return fit

        def payload(code: str, data: dict[str, Any]) -> bytes:
            return compact.frame_bytes(payload_frame, build(code, data))

        return MixedFrame(fit, payload, supplied)

    def _v2_dispatch(
        self,
        started: float,
        path: Any,
        operation: str,
        request: Any,
        top_level: dict[str, Any],
        granted: ExecutionPermissions,
        *,
        task_id: str | None,
        attribution: dict[str, Any],
        frame: compact.FrameContext | None = None,
    ) -> ToolResult:
        """The path (72-T01: an invalid one is `E_INPUT` before anything else, for
        every operation), strict validation (the MCP model), then the operation."""
        from ..mcp_support.request_models import validate_memory_v2

        try:
            root = Path(path).resolve()
            os.fsencode(root)  # an unencodable path fails here, before any OS call
        except (TypeError, ValueError, OSError, RuntimeError):
            return self._v2_wrap(
                started,
                operation,
                _v2_raw(
                    operation,
                    "E_INPUT",
                    data={"field": "path", "message": "invalid project path"},
                ),
            )
        req, rejection = validate_memory_v2(operation, request, top_level)
        if rejection is not None:
            return self._v2_wrap(started, operation, rejection)
        call = _V2Call(
            started,
            root,
            operation,
            req,
            granted,
            task_id,
            attribution,
            frame=frame,
            frozen=_frozen_duration(started) if frame is not None else None,
        )
        handlers: dict[str, Callable[[_V2Call], ToolResult]] = {
            "ask": self._v2_read,
            "recall": self._v2_read,
            "list": self._v2_read,
            "expand": self._v2_expand,
            "related": self._v2_related,
            "history": self._v2_history,
            "explain": self._v2_explain,
        }
        handler = handlers.get(operation, self._v2_mutation)
        with collect_committed_writes() as committed:
            try:
                result = handler(call)
            except Exception as exc:
                failure = _v2_failure(exc)
                if failure is None:
                    raise
                result = self._v2_out(call, failure[0], data=failure[1])
        if frame is not None and frame.context is not None:
            metadata = dict(result.get("metadata") or {})
            if "scope" not in metadata:
                metadata["scope"] = _frame_scope(frame)
                result["metadata"] = metadata
        return cast(
            ToolResult,
            attach_memory_attribution(
                result, _memory_attribution(root, operation, result, committed)
            ),
        )

    # access ----------------------------------------------------------------------

    def _v2_access(self, call: _V2Call, *, apply: bool) -> MemoryAccess | ToolResult:
        """§3.2: the one access a v2 call runs under, or its denial."""
        from ..memory.authorization import user_overlay_owner_scope
        from ..memory.retrieval import memory_policy_decision

        req, op, root = call.req, call.operation, call.root
        owner = (
            OwnerScope.from_value(req.owner_scope.model_dump())
            if getattr(req, "owner_scope", None) is not None
            else None
        )
        historical = op == "history" or (
            getattr(req, "archive_mode", "active") == "historical"
        )
        mode, why = memory_policy_decision(root)
        overlay = owner is not None and owner == user_overlay_owner_scope()
        if mode == "unavailable":
            return self._v2_policy_denied(
                call,
                "E_PERMISSION",
                {"reason": why or "policy_invalid"},
                owner,
                apply=apply,
                historical=historical,
                overlay=overlay,
            )
        if mode == "legacy":
            return self._v2_legacy_access(call, owner, overlay, apply=apply)
        if overlay and op in _OVERLAY_PREFERENCE_ONLY:
            return self._v2_out(
                call, "E_OWNER", data={"reason": "overlay_requires_preference_route"}
            )
        # 72-T05 binds the task context; `None` when the caller names none.
        access, reason = MemoryAccess.resolve_with_reason(
            root,
            operation=op,
            apply=apply,
            historical=historical,
            overlay=overlay,
            owner_scope=owner,
            requested_sources=tuple(getattr(req, "sources", None) or ()),
            task_id=call.task_id,
        )
        if access is None:
            code, data = _v2_denial(owner, reason)
            return self._v2_policy_denied(
                call,
                code,
                data,
                owner,
                apply=apply,
                historical=historical,
                overlay=overlay,
            )
        return access

    def _v2_policy_denied(
        self,
        call: _V2Call,
        code: str,
        data: dict[str, Any],
        owner: OwnerScope | None,
        *,
        apply: bool,
        historical: bool,
        overlay: bool,
    ) -> ToolResult:
        """D19/73-T02 item 7: a v2 policy denial names the command that fixes it, as
        the legacy routes' `_denied` does."""
        result = self._v2_out(call, code, data=data)
        try:
            operations = required_operation_set(
                call.operation, apply=apply, historical=historical, overlay=overlay
            )
        except ValueError:
            operations = ()
        _attach_policy_next_action(
            result,
            reason=str(data.get("reason") or ""),
            project_root=call.root,
            operations=operations,
            owner_scope=owner,
            requested_sources=tuple(getattr(call.req, "sources", None) or ()),
            budget=(
                (call.req.encoding, call.req.max_bytes, call.req.max_tokens)
                if hasattr(call.req, "max_bytes")
                else None
            ),
        )
        return result

    def _v2_legacy_access(
        self,
        call: _V2Call,
        owner: OwnerScope | None,
        overlay: bool,
        *,
        apply: bool,
    ) -> MemoryAccess | ToolResult:
        """D1 `legacy` mode: the request's explicit sources, never an ambient grant."""
        req, op, root = call.req, call.operation, call.root
        if overlay:
            return self._v2_out(
                call, "E_PERMISSION", data={"reason": "overlay_requires_policy"}
            )
        sources = getattr(req, "sources", None)
        if sources is None and op == "write":
            sources = [req.source]
        if sources is None:
            # D1 `legacy` mode has no policy to grant sources: never an ambient one.
            return self._v2_out(call, "E_PERMISSION", data={"reason": "policy_missing"})
        if op in _V2_MUTATIONS:
            default_owner = legacy_owner_scope(root)
            if owner is not None and owner != default_owner:
                return self._v2_out(
                    call, "E_OWNER", data={"reason": "owner_not_granted"}
                )
            return MemoryAccess.legacy(
                root,
                sources,
                owner_scope=default_owner,
                operation="write",
                task_id=call.task_id,
            )
        return MemoryAccess.legacy(
            root, sources, owner_scope=owner, operation=op, task_id=call.task_id
        )

    def _v2_view(
        self, call: _V2Call, access: MemoryAccess
    ) -> TypedArtifactStore | ToolResult | None:
        """A read-only view of the access's store (`None`: no store)."""
        view, state = TypedArtifactStore.open_readonly_view(_storage_root(access))
        if state is not None:
            return self._v2_out(
                call,
                _READ_STATE_CODES[state],
                data={"reason": state, "message": readonly_view_reason(state)},
            )
        return view

    def _v2_admission(self, call: _V2Call) -> ToolResult | None:
        """C05: caps below the complete canonical v2 `E_BUDGET` raw are `E_INPUT`
        before access, any store or telemetry."""
        req = call.req
        try:
            fit = self._v2_fit(call)
            if fit is None:
                need = _v2_budget_floor(call.operation, req.encoding)
            else:
                # D35: the floor is the largest framed refusal the transport emits.
                framed = recall_admission(
                    limit=1,
                    max_bytes=0,
                    max_tokens=0,
                    encoding=req.encoding,
                    frame_bytes=fit,
                )
                required_floor = (framed or {})["required"]
                need = (
                    int(required_floor["max_bytes"]),
                    int(required_floor["max_tokens"]),
                )
        except (ValueError, TypeError, KeyError):
            return self._v2_out(
                call,
                "E_INPUT",
                data={"field": "encoding", "message": "unknown encoding"},
            )
        required = {"max_bytes": need[0], "max_tokens": need[1]}
        for name, cap, floor in (
            ("max_bytes", req.max_bytes, need[0]),
            ("max_tokens", req.max_tokens, need[1]),
        ):
            if cap < floor:
                return self._v2_out(
                    call,
                    "E_INPUT",
                    data={
                        "field": name,
                        "message": f"{name} is below the smallest response",
                        "required": required,
                    },
                )
        return None

    def _v2_note_read(
        self, call: _V2Call, access: MemoryAccess, raw: dict[str, Any]
    ) -> None:
        """MC04: a delivered `history`/`explain` page's real token cost, recorded
        only with `cache_write` (the same gate as every other read)."""
        from ..memory.retrieval import _record_memory_event

        telemetry = self._v2_telemetry(call, _storage_root(access))
        if telemetry is None:
            return
        target = getattr(call.req, "artifact_id", None) or getattr(
            call.req, "query", ""
        )
        _record_memory_event(
            telemetry,
            "retrieval",
            _v2_measure(raw, call.req.encoding)[1],
            request_id=f"{call.operation}:v2:{target}:{getattr(call.req, 'cursor', None)}",
            event_id="retrieval",
            invocation_id=call.attribution.get("invocation_id") or str(uuid.uuid4()),
            project_id=call.attribution.get("project_id"),
            run_id=call.attribution.get("run_id"),
            agent_id=call.attribution.get("agent_id"),
            session_id=call.attribution.get("session_id"),
            opt_in=False,
            cache_write=True,
            access=access,
        )

    def _v2_telemetry(self, call: _V2Call, root: Path) -> TelemetryStore | None:
        if not call.granted.cache_write:
            return None
        return cast(TelemetryStore, _LazyTelemetry(lambda: TelemetryStore(root)))

    # reads -----------------------------------------------------------------------

    def _v2_read(self, call: _V2Call) -> ToolResult:
        """`ask`/`recall` (ordinary), `list` (inspect; empty query browses), each
        `historical` with `archive_mode`, paged under the v2 envelope."""
        req, op = call.req, call.operation
        refused = self._v2_admission(call)
        if refused is not None:
            return refused
        if req.retrieval == "hybrid" and req.cursor is not None:
            return self._v2_out(
                call,
                "E_INPUT",
                data={"field": "cursor", "message": "hybrid retrieval has no cursor"},
            )
        access = self._v2_access(call, apply=False)
        if not isinstance(access, MemoryAccess):
            return access
        # 72-T08 §3.1: the effective retrieval of a compact read, for a v2 read. An
        # absent `retrieval` is the implicit default; a missing network grant or engine is
        # a labelled lexical page, never `E_PERMISSION`.
        hybrid, p_default, cfg_options, cfg_error = self._retrieval_plan(
            call.root, "retrieval" in req.model_fields_set, req.retrieval
        )
        fallback: str | None = None
        embed_config: EmbeddingConfig | None = None
        if hybrid:
            fallback, embed_config = self._hybrid_engine(
                {
                    key: getattr(req, key)
                    for key in (*_EMBEDDING_OPTION_KEYS, "embedding_chunking_version")
                },
                req.query,
                req.cursor,
                call.granted,
                cfg_options,
                cfg_error,
            )
        root = _storage_root(access)
        # Every v2 read is a read-only view: a read never runs a constructor
        # migration (72-T02 owns any DDL-free writable open for embeddings).
        opened = self._v2_view(call, access)
        if isinstance(opened, dict):
            return cast(ToolResult, opened)
        store = opened
        if p_default and fallback is None and embed_config is not None:
            fallback = self._tags_fallback(embed_config)
        if store is None:
            labels: dict[str, Any] | None = None
            if fallback is not None:
                labels = _fallback_labels(fallback, 0)
            elif hybrid:
                labels = {
                    "retrieval": "hybrid",
                    "candidates_truncated": False,
                    "incomplete_reason": None,
                    "embedded_texts": 0,
                }
            size = _measure_page([], None, True, req.encoding, labels)
            return self._v2_out(
                call,
                "OK",
                complete=True,
                data={
                    "tokens": size[1],
                    "bytes": size[0],
                    "encoding": req.encoding,
                    **(labels or {}),
                },
            )
        mode = (
            "historical"
            if req.archive_mode == "historical"
            else ("inspect" if op == "list" else "ordinary")
        )
        filters: dict[str, Any] = {
            "subjects": list(req.subjects),
            "mode": mode,
            "trust_tiers": req.trust_tiers,
            "freshness": req.freshness,
            "archive_mode": req.archive_mode,
            "v2_items": True,
        }
        fit = self._v2_fit(call)
        # D35: under a transport frame the caps measure the whole emitted frame.
        overhead = (0, 0) if fit is not None else _v2_overhead(op, req.encoding)
        common: dict[str, Any] = {
            "frame_bytes": fit,
            "query": req.query,
            "access": access,
            "limit": req.limit,
            "max_tokens": req.max_tokens - overhead[1],
            "max_bytes": req.max_bytes - overhead[0],
            "encoding": req.encoding,
            "telemetry": self._v2_telemetry(call, root),
            "request_id": f"{op}:v2:{','.join(sorted(req.subjects))}:{req.query}:"
            f"{req.cursor}",
            "event_id": "retrieval",
            "opt_in": False,
            "cache_write": call.granted.cache_write,
            **call.attribution,
        }
        try:
            if hybrid:
                subjects = sorted(set(req.subjects))
                page = hybrid_page(
                    store,
                    subject=cast(
                        MemorySubject, subjects[0] if len(subjects) == 1 else subjects
                    ),
                    embed_config=embed_config,
                    fallback_code=fallback,
                    cursor=req.cursor,
                    v2_filters=filters,
                    # No `fill_access`: a v2 read never persists a vector, but its
                    # delivered page is still a receipt under `cache_write`.
                    **common,
                )
            else:
                page = recall_page(store, cursor=req.cursor, **common, **filters)
        finally:
            store.close()
        return self._v2_page(call, page)

    def _v2_page(self, call: _V2Call, page: dict[str, Any]) -> ToolResult:
        """A retrieval page (`items`, `next_cursor`, `complete`, sizes) as a v2 raw."""
        data = dict(page)
        code = str(data.pop("code"))
        items = data.pop("items", None) or []
        next_cursor = data.pop("next_cursor", None)
        # 72-T06 §3.4: an error carries `items=[]`, `complete=False` (e.g. the
        # `related` missing-root body is `complete: True` at the relations layer).
        complete = bool(data.pop("complete", False)) and code in {
            "OK",
            "E_EMBEDDING_UNAVAILABLE",
        }
        if code == "E_INPUT" and "required" in data:
            data["field"] = "max_bytes"
        if code == "E_EMBEDDING_UNAVAILABLE":
            # A v2 hybrid read without an engine is the lexical page, labelled as such
            # in `data.retrieval` / `data.hybrid_unavailable_reason`.
            code = "OK"
        return self._v2_out(
            call,
            code,
            items=items,
            next_cursor=next_cursor,
            complete=complete,
            data=data,
        )

    def _v2_expand(self, call: _V2Call) -> ToolResult:
        req = call.req
        refused = self._v2_admission(call)
        if refused is not None:
            return refused
        # C05: caps below the smallest expand envelope plus the v2 envelope are
        # `E_INPUT` naming the cap, before access, any store or telemetry.
        fit = self._v2_fit(call)
        # D35: under a transport frame the caps measure the whole emitted frame.
        overhead = (
            (0, 0) if fit is not None else _v2_overhead(call.operation, req.encoding)
        )
        floor = expand_admission(
            artifact_id=req.artifact_id,
            version=req.artifact_version,
            offset=req.offset,
            max_bytes=req.max_bytes - overhead[0],
            max_tokens=req.max_tokens - overhead[1],
            encoding=req.encoding,
            representation=req.representation or "utf8",
            frame_bytes=fit,
        )
        if (
            floor is not None
            and floor.get("code") == "E_INPUT"
            and isinstance(floor.get("required"), dict)
        ):
            required = {
                "max_bytes": int(floor["required"]["max_bytes"]) + overhead[0],
                "max_tokens": int(floor["required"]["max_tokens"]) + overhead[1],
            }
            field = (
                "max_bytes" if req.max_bytes < required["max_bytes"] else "max_tokens"
            )
            return self._v2_out(
                call,
                "E_INPUT",
                data={
                    "field": field,
                    "message": f"{field} is below the smallest response",
                    "required": required,
                },
            )
        access = self._v2_access(call, apply=False)
        if not isinstance(access, MemoryAccess):
            return access
        opened = self._v2_view(call, access)
        if isinstance(opened, dict):
            return cast(ToolResult, opened)
        if opened is None:
            return self._v2_out(call, "E_NOT_VISIBLE", data={"reason": "not_visible"})
        store = opened
        mode: Literal["ordinary", "historical"] = (
            "historical" if req.archive_mode == "historical" else "ordinary"
        )
        try:
            expand_fit = fit
            if fit is not None:
                # The delivered page is `items=[payload + reference]`: measure it so.
                try:
                    reference_probe: dict[str, Any] = {
                        **v2_reference(
                            evaluate_artifact_visibility(
                                store,
                                store.get_current_row(req.artifact_id),
                                access=access,
                                mode=mode,
                            )
                        ),
                        "artifact_version": req.artifact_version,
                    }
                except Exception:  # noqa: BLE001 - a refusal frame carries no reference
                    reference_probe = {}

                def expand_fit(code: str, data: dict[str, Any]) -> bytes:
                    if code != "OK":
                        return fit(code, data)
                    return fit(
                        "OK",
                        {
                            "items": [{**data, "reference": reference_probe}],
                            "complete": bool(
                                data.get("complete", data.get("next_offset") is None)
                            ),
                            **{
                                key: data[key]
                                for key in ("tokens", "bytes", "encoding")
                                if key in data
                            },
                        },
                    )

            payload = expand_artifact(
                store,
                artifact_id=req.artifact_id,
                version=req.artifact_version,
                access=access,
                mode=mode,
                offset=req.offset,
                max_tokens=req.max_tokens - overhead[1],
                max_bytes=req.max_bytes - overhead[0],
                encoding=req.encoding,
                representation=req.representation or "utf8",
                frame_bytes=expand_fit,
                telemetry=self._v2_telemetry(call, _storage_root(access)),
                # The `id:version:` prefix is how the expansion-receipt readers find
                # the events of an exact revision (the v1 shape, utf8 suffixed).
                request_id=f"{req.artifact_id}:{req.artifact_version}:{req.offset}"
                + (":utf8" if (req.representation or "utf8") == "utf8" else ""),
                event_id="expansion",
                cache_write=call.granted.cache_write,
                **call.attribution,
            )
            reference: dict[str, Any] | None = None
            if payload.get("code") == "OK":
                decision = evaluate_artifact_visibility(
                    store,
                    store.get_current_row(req.artifact_id),
                    access=access,
                    mode=mode,
                )
                reference = {
                    **v2_reference(decision),
                    "artifact_version": req.artifact_version,
                }
        finally:
            store.close()
        code = str(payload.pop("code"))
        if code != "OK" or reference is None:
            # A refusal carries no content field, not even a null one.
            for content_key in ("content_utf8", "content_base64"):
                payload.pop(content_key, None)
            return self._v2_out(call, code, data=payload)
        complete = bool(payload.get("complete", payload.get("next_offset") is None))
        return self._v2_out(
            call,
            "OK",
            items=[{**payload, "reference": reference}],
            complete=complete,
            data={
                key: payload[key]
                for key in ("tokens", "bytes", "encoding")
                if key in payload
            },
        )

    def _v2_related(self, call: _V2Call) -> ToolResult:
        req = call.req
        refused = self._v2_admission(call)
        if refused is not None:
            return refused
        access = self._v2_access(call, apply=False)
        if not isinstance(access, MemoryAccess):
            return access
        opened = self._v2_view(call, access)
        if isinstance(opened, dict):
            return cast(ToolResult, opened)
        if opened is None:
            return self._v2_out(call, "E_NOT_VISIBLE", data={"reason": "not_visible"})
        store = opened
        overhead = _v2_overhead(call.operation, req.encoding)
        try:
            version = req.artifact_version
            if version is None:
                row = store.get_current_row(req.artifact_id)
                version = int(row["artifact_version"]) if row is not None else 0
            # 72-T03 owns access/mode on the traversal (pinned signature).
            page = related_artifacts(
                store,
                artifact_id=req.artifact_id,
                version=version,
                session_allowlist=None,
                access=access,
                mode="historical" if req.archive_mode == "historical" else "ordinary",
                depth=req.depth,
                max_nodes=req.max_nodes,
                max_tokens=req.max_tokens - overhead[1],
                max_bytes=req.max_bytes - overhead[0],
                encoding=req.encoding,
            )
        finally:
            store.close()
        if page.get("code") == "OK":
            # The seed the traversal started from, so a caller can tie the page to it.
            page["root"] = {"artifact_id": req.artifact_id, "artifact_version": version}
            self._v2_note_read(call, access, page)
        return self._v2_page(call, page)

    def _v2_history(self, call: _V2Call) -> ToolResult:
        """D31: every version of one artifact the access may see, oldest first,
        each decided on its own, paged under the caps."""
        from ..memory.retrieval import _cursor_binding, _decode_cursor, _encode_cursor

        req = call.req
        refused = self._v2_admission(call)
        if refused is not None:
            return refused
        access = self._v2_access(call, apply=False)
        if not isinstance(access, MemoryAccess):
            return access
        opened = self._v2_view(call, access)
        if isinstance(opened, dict):
            return cast(ToolResult, opened)
        if opened is None:
            return self._v2_out(call, "E_NOT_VISIBLE", data={"reason": "not_visible"})
        view = opened
        try:
            versions = view.version_history_readonly(
                req.artifact_id,
                access=access,
                archive_mode=req.archive_mode,
                representation=req.representation,
            )
            try:
                key = view.cursor_key()
            except (TypeError, sqlite3.OperationalError):
                return self._v2_out(
                    call, "E_MIGRATION", data={"reason": "migration_required"}
                )
            generation = view.current_generation()
        finally:
            view.close()
        owner = access.owner_scope
        binding = _cursor_binding(
            namespace=f"history:{req.artifact_id}",
            project_id=access.project_id,
            worktree_id=access.worktree_id,
            owner=(owner.kind, owner.id) if owner is not None else None,
            grant_id=access.grant_id,
            subject="history",
            query="",
            sources=list(access.sources),
            v2={
                "archive_mode": req.archive_mode,
                "representation": req.representation,
                "mode": "history",
            },
        )
        start = 0
        if req.cursor is not None:
            decoded = _decode_cursor(key, req.cursor, binding, generation)
            if decoded is None:
                return self._v2_out(call, "E_RESTART")
            start = decoded

        def token(at: int) -> str:
            return _encode_cursor(key, binding, generation, at)

        def fits(raw: dict[str, Any]) -> tuple[bool, tuple[int, int]]:
            size = _v2_measure(raw, req.encoding)
            return size[0] <= req.max_bytes and size[1] <= req.max_tokens, size

        page: list[dict[str, Any]] = []
        position = start
        while position < len(versions) and len(page) < req.limit:
            more = position + 1 < len(versions)
            trial = [*page, versions[position]]
            ok, _size = fits(
                _v2_raw(
                    "history",
                    "OK",
                    next_cursor=token(position + 1) if more else None,
                    complete=not more,
                    versions=trial,
                )
            )
            if not ok:
                if not page:
                    need = _v2_measure(
                        _v2_raw(
                            "history",
                            "OK",
                            next_cursor=token(position + 1) if more else None,
                            versions=trial,
                        ),
                        req.encoding,
                    )
                    return self._v2_out(
                        call,
                        "E_BUDGET",
                        data={
                            "required": {"max_bytes": need[0], "max_tokens": need[1]}
                        },
                    )
                break
            page = trial
            position += 1
        next_cursor = token(position) if position < len(versions) else None
        raw = _v2_raw(
            "history",
            "OK",
            next_cursor=next_cursor,
            complete=next_cursor is None,
            versions=page,
        )
        self._v2_note_read(call, access, raw)
        return self._v2_wrap(call.started, "history", raw)

    def _v2_explain(self, call: _V2Call) -> ToolResult:
        """D38: structured one-hop buckets over recorded relations; never generated
        text and never a model call."""
        req = call.req
        refused = self._v2_admission(call)
        if refused is not None:
            return refused
        access = self._v2_access(call, apply=False)
        if not isinstance(access, MemoryAccess):
            return access
        opened = self._v2_view(call, access)
        if isinstance(opened, dict):
            return cast(ToolResult, opened)
        query_mode = req.artifact_id is None
        if opened is None:
            if query_mode:
                return self._v2_out(
                    call,
                    "OK",
                    complete=True,
                    unknowns=["no_matches", "no_recorded_rationale"],
                    targets=[],
                    supporting=[],
                    contrary=[],
                    attempted=[],
                    affected=[],
                )
            return self._v2_out(call, "E_NOT_VISIBLE", data={"reason": "not_visible"})
        view = opened
        historical = req.archive_mode == "historical"
        mode: Literal["inspect", "historical"] = (
            "historical" if historical else "inspect"
        )
        unknowns: set[str] = set()
        try:
            memo = SourceValidationMemo()
            targets: list[tuple[sqlite3.Row, Any]] = []
            if not query_mode:
                row = view.get_current_row(req.artifact_id)
                decision = evaluate_artifact_visibility(
                    view, row, access=access, mode=mode, memo=memo
                )
                if row is None or not decision.visible:
                    return self._v2_out(
                        call, "E_NOT_VISIBLE", data={"reason": "not_visible"}
                    )
                targets.append((row, decision))
                if decision.freshness == "unknown":
                    unknowns.add("freshness_unknown")
            else:
                subjects = sorted(set(req.subjects))
                rows = view.search_candidates(
                    cast(
                        MemorySubject, subjects[0] if len(subjects) == 1 else subjects
                    ),
                    req.query,
                    source_allowlist=list(access.sources),
                    owner_scope=access.owner_scope,
                    scan_limit=_LIST_SCAN_PAGE,
                    include_archived=historical,
                    include_expired=historical,
                )
                for candidate in rows:
                    decision = evaluate_artifact_visibility(
                        view, candidate, access=access, mode=mode, memo=memo
                    )
                    if decision.visible:
                        targets.append((candidate, decision))
                    if len(targets) >= req.limit:
                        break
                if not targets:
                    unknowns.add("no_matches")
            buckets = _explain_buckets(view, access, mode, targets, memo=memo)
        finally:
            view.close()
        if query_mode:
            for row, decision in targets:
                if row["subject"] in _ATTEMPT_SUBJECTS:
                    _bucket_add(buckets["attempted"], decision, ("matched", "none"))
        if not buckets["supporting"]:
            unknowns.add("no_recorded_rationale")
        named: dict[str, Any] = {
            name: _bucket_list(entries) for name, entries in buckets.items()
        }
        raw = _v2_raw(
            "explain",
            "OK",
            complete=True,
            unknowns=unknowns,
            targets=[v2_reference(decision) for _row, decision in targets],
            **named,
        )
        size = _v2_measure(raw, req.encoding)
        if size[0] > req.max_bytes or size[1] > req.max_tokens:
            return self._v2_out(
                call,
                "E_BUDGET",
                data={"required": {"max_bytes": size[0], "max_tokens": size[1]}},
            )
        self._v2_note_read(call, access, raw)
        return self._v2_wrap(call.started, "explain", raw)

    # mutations -------------------------------------------------------------------

    def _v2_mutation(self, call: _V2Call) -> ToolResult:
        """D1 + D29: preview, or apply under the policy lock with one v2 receipt
        recorded in the effect's own transaction (replayed by its ids)."""
        req = call.req
        if not req.apply:
            return self._v2_preview(call)
        if not call.granted.cache_write:
            return self._v2_out(
                call,
                "E_PERMISSION",
                data={
                    "reason": "cache_write_required",
                    "message": f"memory {call.operation} apply requires cache_write.",
                },
            )
        missing = _missing_grants(req.required_grants or [], call.granted)
        if missing:
            return self._v2_out(
                call,
                "E_PERMISSION",
                data={
                    "reason": "required_grants_missing",
                    "message": _grant_refusal_message(call.operation, missing),
                    "required_grants": req.required_grants,
                    "missing_grants": missing,
                },
            )
        access = self._v2_access(call, apply=True)
        if not isinstance(access, MemoryAccess):
            return access
        db = _storage_root(access) / ".rush" / "memory.db"
        if call.operation != "write" and not db.exists():
            # Nothing to change: no store is created for a mutation of absent rows.
            return self._v2_out(call, "E_NOT_VISIBLE", data={"reason": "not_visible"})
        digest = _v2_request_digest(call.operation, access, req)
        if call.operation == "maintain":
            return self._v2_maintain(call, access, digest)
        with _policy_mutation(access) as lock_refused:
            if lock_refused is not None:
                return self._v2_out(
                    call, lock_refused.code, data={"reason": lock_refused.reason}
                )
            store = TypedArtifactStore(_storage_root(access))
            replay = self._v2_replay(call, store, access, digest)
            if replay is not None:
                return replay
            return self._v2_effect(call, store, access, digest)

    def _v2_targets(self, call: _V2Call) -> list[str]:
        req, op = call.req, call.operation
        if op in ("edit", "archive", "promote"):
            return [req.artifact_id]
        if op == "delete":
            return list(req.artifact_ids)
        if op == "link":
            return [req.source_id, req.target_id]
        if op == "maintain":
            return list(req.candidate_ids or ())
        return []

    def _v2_effect(
        self,
        call: _V2Call,
        store: TypedArtifactStore,
        access: MemoryAccess,
        digest: str,
    ) -> ToolResult:
        req, op = call.req, call.operation
        sources: set[str] = {req.source} if op == "write" else set()
        for artifact_id in self._v2_targets(call):
            row = store.get_current_row(artifact_id)
            if (
                row is None
                or not _access_allows(store, row, access, "inspect")
                # 72-T06 matrix: an edit needs the ordinary-mode view, so an archived
                # or expired row is `E_NOT_VISIBLE` (as `promote` already is).
                or (
                    op == "edit"
                    and not evaluate_artifact_visibility(
                        store, row, access=access
                    ).visible
                )
            ):
                raise KeyError(artifact_id)
            sources.add(str(row["source"]))
        binding = _v2_binding(access, sources)
        captured: dict[str, Any] = {}

        def writer(conn: sqlite3.Connection, payload: dict[str, Any]) -> None:
            record = _v2_record(binding, payload)
            store._write_v2_receipt(
                conn,
                invocation_id=req.invocation_id,
                effect_id=req.effect_id,
                request_digest=digest,
                artifact_id=payload.get("artifact_id"),
                kind=op,
                revision=payload.get("artifact_version"),
                payload=record,
            )
            captured.clear()
            captured.update(record)

        check = _commit_check(access)
        owner = _write_owner(None, access) or legacy_owner_scope(call.root)
        result: Any
        if op == "write":
            artifact = self._build_artifact(
                req.subject,
                req.content,
                req.source,
                req.symbol_ref,
                req.source_kind,
                owner,
            )
            task_binding = _v2_task_binding(access, call.task_id)
            if task_binding is not None:
                artifact = dataclasses.replace(
                    artifact,
                    task_project_id=task_binding[0],
                    task_worktree_id=task_binding[1],
                    task_id=task_binding[2],
                )
            result = store.write(
                artifact, access=access, receipt_writer=writer, commit_check=check
            )
        elif op == "edit" and req.correction is not None:
            result = self._v2_correction(call, store, access, writer)
            if result.get("code") != "OK":
                # A refused correction wrote nothing and recorded no receipt.
                code = str(result.pop("code"))
                return self._v2_out(call, code, data=result)
        elif op == "edit":
            result = store.edit(
                req.artifact_id,
                req.content,
                expected_version=req.expected_version,
                scope=req.subject,
                owner_scope=owner,
                apply=True,
                receipt_writer=writer,
                commit_check=check,
                task_binding=_v2_task_binding(access, call.task_id),
            )
        elif op == "archive":
            result = store.archive(
                req.artifact_id,
                expected_version=req.expected_version,
                scope=req.subject,
                owner_scope=owner,
                apply=True,
                archived=req.archived,
                receipt_writer=writer,
                commit_check=check,
            )
        elif op == "delete":
            result = store.delete_batch(
                list(req.artifact_ids),
                expected_revisions=dict(req.expected_revisions),
                scope=req.subject,
                owner_scope=owner,
                apply=True,
                receipt_writer=writer,
                commit_check=check,
            )
        elif op == "promote":
            result = store._write_and_promote_tx(
                artifact_id=req.artifact_id,
                expected_version=req.expected_version,
                access=access,
                user_stated=req.user_stated,
                candidate_refs=[ref.model_dump() for ref in req.candidate_refs]
                if req.candidate_refs is not None
                else None,
                receipt_writer=writer,
                commit_check=check,
            )
        else:  # link
            result = add_relation(
                store,
                source_id=req.source_id,
                source_version=req.source_version,
                target_id=req.target_id,
                target_version=req.target_version,
                kind=req.kind,
                origin_ref=req.origin_ref,
                access=access,
                receipt_writer=writer,
            )
            if result.get("code") != "OK":
                code = str(result.pop("code"))
                return self._v2_out(call, code, data=result)
        if not captured and isinstance(result, MemoryArtifact):
            # D30 event replay: the existing row, no new effect and no new receipt.
            refs = [
                {"artifact_id": result.id, "artifact_version": result.artifact_version}
            ]
            captured.update(_v2_record(binding, {"result_refs": refs, "result": {}}))
        record = captured or _v2_record(binding, {"result": _jsonable(result)})
        return self._v2_mutation_result(call, record, access)

    def _v2_mutation_result(
        self, call: _V2Call, record: dict[str, Any], access: MemoryAccess
    ) -> ToolResult:
        req = call.req
        raw = _v2_mutation_raw(call.operation, record, req.invocation_id, req.effect_id)
        if call.operation == "edit" and req.correction is not None:
            raw["data"]["affected"] = self._v2_affected(access, req.artifact_id)
        return self._v2_wrap(call.started, call.operation, raw)

    def _v2_affected(self, access: MemoryAccess, artifact_id: str) -> list[Any]:
        """The D38 `affected` bucket of one corrected target, read after commit."""
        view, state = TypedArtifactStore.open_readonly_view(_storage_root(access))
        if view is None or state is not None:
            return []
        try:
            row = view.get_current_row(artifact_id)
            if row is None:
                return []
            memo = SourceValidationMemo()
            decision = evaluate_artifact_visibility(
                view, row, access=access, mode="inspect", memo=memo
            )
            buckets = _explain_buckets(
                view, access, "inspect", [(row, decision)], memo=memo
            )
        finally:
            view.close()
        return _bucket_list(buckets["affected"])

    def _v2_correction(
        self,
        call: _V2Call,
        store: TypedArtifactStore,
        access: MemoryAccess,
        writer: Callable[[sqlite3.Connection, dict[str, Any]], None],
    ) -> Any:
        """72-T05 owns the correction transaction; T06 forwards every citation."""
        from ..memory.store import VersionBinding  # type: ignore[attr-defined]

        req = call.req
        correction = req.correction
        row = store.get_current_row(req.artifact_id)
        if row is None:
            raise KeyError(req.artifact_id)
        binding = VersionBinding(
            applicability=row["applicability"]
            if "applicability" in row.keys()  # noqa: SIM118 - sqlite3.Row
            else None,
            task_project_id=access.project_id,
            task_worktree_id=access.worktree_id,
            task_id=call.task_id,
        )
        # `apply_correction` takes a replacement for `supersede` only (omitted: the
        # row's own content); a `correct` with content states the corrected content
        # of the same row; `reject` keeps it.
        target_content = json.loads(row["content"])
        replacement_content = None
        if correction.kind == "supersede":
            replacement_content = (
                req.content if req.content is not None else dict(target_content)
            )
        elif correction.kind == "correct" and req.content is not None:
            target_content = req.content
        return store.apply_correction(  # type: ignore[attr-defined]
            access=access,
            kind=correction.kind,
            artifact_id=req.artifact_id,
            expected_version=req.expected_version,
            target_content=target_content,
            replacement_content=replacement_content,
            binding=binding,
            supersedes=[ref.model_dump() for ref in correction.supersedes]
            if correction.supersedes is not None
            else None,
            receipt_writer=writer,
        )

    def _v2_replay(
        self,
        call: _V2Call,
        store: TypedArtifactStore,
        access: MemoryAccess,
        digest: str,
    ) -> ToolResult | None:
        """D29 replay: binding, then digest, then every result ref, then the
        recorded result unchanged. `None` when these ids recorded nothing."""
        from ..memory.authorization import source_granted

        req = call.req
        with store._connect() as conn:
            row = store._find_v2_receipt(conn, req.invocation_id, req.effect_id)
        if row is None:
            return None
        payload = row["payload"]
        if isinstance(payload, (str, bytes)):
            payload = json.loads(payload)
        binding = payload.get("binding") or {}
        owner = access.owner_scope
        if (
            binding.get("project_id") != access.project_id
            or binding.get("worktree_id") != access.worktree_id
            or (owner is not None and binding.get("owner_scope") != owner.as_dict())
            or not all(
                source_granted(source, access.sources)
                for source in binding.get("sources") or ()
            )
        ):
            return self._v2_out(call, "E_NOT_VISIBLE", data={"reason": "not_visible"})
        if row["request_digest"] != digest:
            return self._v2_out(
                call, "E_VERSION", data={"reason": "effect_digest_conflict"}
            )
        for ref in payload.get("result_refs") or ():
            if not _ref_visible(store, access, ref, deleted=call.operation == "delete"):
                return self._v2_out(
                    call, "E_NOT_VISIBLE", data={"reason": "not_visible"}
                )
        return self._v2_mutation_result(call, payload, access)

    def _v2_maintain(
        self, call: _V2Call, access: MemoryAccess, digest: str
    ) -> ToolResult:
        """72-T04 + D29: replay lookup under a short policy lock, the cycle with no
        policy lock held, then the one receipt under a new short lock after an access
        and replay recheck. Rows the cycle committed stay committed."""
        req = call.req
        root = _storage_root(access)
        with _policy_mutation(access) as refused:
            if refused is not None:
                return self._v2_out(call, refused.code, data={"reason": refused.reason})
            store = TypedArtifactStore(root)
            replay = self._v2_replay(call, store, access, digest)
            if replay is not None:
                return replay
            sources = {
                str(row["source"])
                for artifact_id in self._v2_targets(call)
                if (row := store.get_current_row(artifact_id)) is not None
            }
        outcome = run_maintenance_cycle(  # type: ignore[call-arg]
            req.task,
            access=access,
            batch_size=req.batch_size,
            candidate_ids=list(req.candidate_ids)
            if req.candidate_ids is not None
            else None,
            expected_revisions=dict(req.expected_revisions)
            if req.expected_revisions is not None
            else None,
        )
        record = json.loads(
            json.dumps(
                {
                    "binding": _v2_binding(access, sources or set(access.sources)),
                    "result_refs": [],
                    "result": dataclasses.asdict(outcome),
                },
                default=str,
            )
        )
        with _policy_mutation(access) as refused:
            if refused is not None:
                return self._v2_out(call, refused.code, data={"reason": refused.reason})
            replay = self._v2_replay(call, store, access, digest)
            if replay is not None:
                return replay
            with store._connect() as conn:
                conn.execute("BEGIN IMMEDIATE")
                store._write_v2_receipt(
                    conn,
                    invocation_id=req.invocation_id,
                    effect_id=req.effect_id,
                    request_digest=digest,
                    artifact_id=None,
                    kind="maintain",
                    revision=None,
                    payload=record,
                )
                conn.commit()
        return self._v2_mutation_result(call, record, access)

    def _v2_preview(self, call: _V2Call) -> ToolResult:
        """`apply=false`: a read-only preview; no store is created or changed."""
        req, op = call.req, call.operation
        access = self._v2_access(call, apply=False)
        if not isinstance(access, MemoryAccess):
            return access
        root = _storage_root(access)
        owner = _write_owner(None, access) or legacy_owner_scope(call.root)
        preview: Any
        if op == "write":
            preview = _new_artifact_preview(
                self._build_artifact(
                    req.subject,
                    req.content,
                    req.source,
                    req.symbol_ref,
                    req.source_kind,
                    owner,
                ),
                root,
                req.required_grants,
                call.granted,
            )
        elif op == "maintain":
            preview = {
                "apply": False,
                "candidates": preview_maintenance_candidates(
                    req.task,
                    access=access,
                    batch_size=req.batch_size,
                    project_root=root,
                    candidate_ids=list(req.candidate_ids)
                    if req.candidate_ids is not None
                    else None,
                ),
            }
        else:
            revisions = (
                dict(req.expected_revisions)
                if op == "delete"
                else {req.artifact_id: req.expected_version}
            )
            hidden = _hidden_targets(
                access,
                list(revisions),
                lambda: TypedArtifactStore.open_readonly_view(root),
            )
            if hidden:
                raise KeyError(hidden[0])
            targets = [
                TypedArtifactStore.preview_mutation(
                    root,
                    artifact_id,
                    expected_version=version,
                    scope=req.subject,
                    owner_scope=owner,
                    operation="archive" if op in ("archive", "delete") else "edit",
                )
                for artifact_id, version in revisions.items()
            ]
            preview = {"apply": False, "operation": op, "targets": targets}
        return self._v2_out(call, "OK", complete=True, data={"preview": preview})

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
            task_id=_TASK_ID.get(),
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
        view, state = TypedArtifactStore.open_readonly_view(access.storage_root)
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
                if decision.visible and not (
                    mode != "historical"
                    and NOT_CURRENT_REASONS & set(decision.reason_codes)
                ):
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
                _recheck_denial(access) or RouteDenial("E_RESTART", "access_changed"),
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
            and all(_literal_id(c) for c in candidate_ids)
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
            root,
            operation,
            session_allowlist,
            owner,
            historical=historical,
            task_id=_TASK_ID.get(),
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
        view, state = TypedArtifactStore.open_readonly_view(access.storage_root)
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
        # 72-T08 (D14a): an absent `retrieval` is the implicit default, decided below.
        explicit = "retrieval" in request
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
        # 72-T08 (§3.2): request-sourced engine fields are validated by the predicates
        # the MCP models share, before the owner, admission or any effect.
        for field, valid in (
            (
                "embedding_endpoint",
                embedding_endpoint is None
                or request_endpoint_error(embedding_endpoint) is None,
            ),
            (
                "embedding_model",
                embedding_model is None or valid_model(embedding_model),
            ),
            (
                "embedding_model_digest",
                embedding_model_digest is None or valid_digest(embedding_model_digest),
            ),
            (
                "embedding_chunking_version",
                embedding_chunking_version is None
                or valid_chunking(embedding_chunking_version),
            ),
        ):
            if not valid:
                return self._envelope_result(
                    started,
                    operation,
                    "E_INPUT",
                    {"message": f"invalid {field} in request", "field": field},
                )
        try:
            owner = self._parse_owner_scope(owner_scope, root)
        except (ValueError, TypeError) as exc:
            return self._envelope_result(
                started,
                operation,
                "E_INPUT",
                {"message": f"invalid owner_scope: {exc}"},
            )
        # 72-T08 (§3.1): the `[tools.memory]` engine options are read (no effect) only when
        # the request is not explicitly lexical.
        hybrid_requested, p_default, cfg_options, cfg_error = self._retrieval_plan(
            root, explicit, retrieval
        )
        # 72-T02 (C05) / 72-T08 (§3.3): admission before access, the store view, telemetry
        # or any embedding call; a hybrid-requested read is admitted against the largest
        # zero-item envelope its route can emit. D35: under a transport frame the
        # duration is frozen once, here, and admission, every page fit and the emitted
        # envelope use the same framed bytes.
        frozen = _frozen_duration(started) if frame is not None else None
        fit = self._frame_fit(root, operation, frozen, frame)
        admit = hybrid_admission if hybrid_requested else recall_admission
        refused = admit(
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

        resolved = self._read_access(
            root, operation, session_allowlist, owner, task_id=_TASK_ID.get()
        )
        if isinstance(resolved, RouteDenial):
            denied = finish(resolved.code, _denial_data(operation, resolved))
            if isinstance(resolved, _PolicyDenial):
                _attach_policy_next_action(
                    denied,
                    reason=resolved.reason,
                    project_root=resolved.project_root,
                    operations=resolved.operations,
                    owner_scope=resolved.owner_scope,
                    requested_sources=resolved.requested_sources,
                    budget=(encoding, max_bytes, max_tokens),
                )
            return denied
        access = resolved
        if not access.sources:
            return finish(
                "E_PERMISSION",
                {
                    "message": f"memory {operation} requires a non-empty session_allowlist "
                    "(fail-closed, no default cross-session access)."
                },
            )
        # 72-T08 (§3.1): the labelled-fallback precedence, first match, after admission
        # and access and before any network request. A missing network grant is a
        # lexical fallback, never `E_PERMISSION`.
        fallback: str | None = None
        embed_config: EmbeddingConfig | None = None
        if hybrid_requested:
            fallback, embed_config = self._hybrid_engine(
                request, query, cursor, granted, cfg_options, cfg_error
            )
        # 72-T08 (§3.5, D39): embeddings persist only under a separately resolved write
        # authority for the same owner (policy) or a still-legacy project (legacy form).
        fill_access = (
            self._fill_access(access)
            if hybrid_requested and fallback is None and granted.cache_write
            else None
        )
        # 72-T01: reads use `open_readonly_view()`; 72-T02/72-T08: a writable store is
        # constructed only for an authorized fill on an existing DB whose writable open
        # runs no DDL, and the read-only view is closed first.
        store_root = access.storage_root
        store, state = TypedArtifactStore.open_readonly_view(store_root)
        if state is not None:
            return finish(
                _READ_STATE_CODES[state], {"message": readonly_view_reason(state)}
            )
        if fill_access is not None:
            if (
                store is not None
                and (store_root / ".rush" / "memory.db").exists()
                and store.writable_open_ddl_free()
            ):
                store.close()
                store = TypedArtifactStore(store_root)
            else:
                fill_access = None
        try:
            # 72-T08 (F8): the implicit default verifies the engine's model identity
            # before any page is labelled hybrid, the store present or absent.
            if p_default and fallback is None and embed_config is not None:
                fallback = self._tags_fallback(embed_config)
            if store is None:
                return self._absent_store_page(
                    finish, encoding, hybrid=hybrid_requested, fallback=fallback
                )
            return self._compact_page(
                started,
                store,
                access,
                subject,
                query,
                operation,
                "hybrid" if hybrid_requested else "lexical",
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
                embed_config=embed_config,
                fallback=fallback,
                fill_access=fill_access,
            )
        finally:
            if store is not None:
                store.close()

    @staticmethod
    def _retrieval_plan(
        root: Path, explicit: bool, retrieval: str
    ) -> tuple[bool, bool, dict[str, Any] | None, bool]:
        """72-T08 §3.1: `(hybrid_requested, p_default, cfg_options, cfg_error)` for one
        compact or v2 read. The `[tools.memory]` options are read (no effect) only when
        the request is not explicitly lexical."""
        cfg_options: dict[str, Any] | None = None
        cfg_error = False
        if not (explicit and retrieval == "lexical"):
            try:
                tool_config = load_config(root).tools.get("memory")
            except (RushConfigError, UnicodeDecodeError, OSError):
                cfg_error = True
            else:
                if tool_config is not None:
                    cfg_options = dict(tool_config.options)
        verdict = _retrieval.HYBRID_DEFAULT_VERDICT
        p_default = (
            not explicit
            and cfg_options is not None
            and all(cfg_options.get(key) is not None for key in _EMBEDDING_OPTION_KEYS)
            and verdict is not None
            and verdict.get("verdict") == "benefit"
            and cfg_options.get("embedding_model") == verdict.get("model")
            and cfg_options.get("embedding_model_digest") == verdict.get("model_digest")
        )
        hybrid_requested = (
            (explicit and retrieval == "hybrid")
            or p_default
            or (not explicit and cfg_error)
        )
        return hybrid_requested, p_default, cfg_options, cfg_error

    @staticmethod
    def _hybrid_engine(
        request: dict[str, Any],
        query: str,
        cursor: str | None,
        granted: ExecutionPermissions,
        cfg_options: dict[str, Any] | None,
        cfg_error: bool,
    ) -> tuple[str | None, EmbeddingConfig | None]:
        """72-T08 F1'-F7: the first fallback code for a hybrid-requested read, else the
        engine identity, each field taken from the request when given, else from config."""
        if cursor is not None:
            # Only an implicit read reaches here: explicit hybrid + cursor is E_INPUT.
            return "cursor_continuation", None
        if query == "":
            return "empty_query", None
        if not granted.network:
            return "network_not_granted", None
        values: dict[str, Any] = {}
        sources: dict[str, str | None] = {}
        for key in _EMBEDDING_OPTION_KEYS:
            value = request.get(key)
            source: str | None = "request" if value is not None else None
            if value is None and cfg_options is not None:
                value = cfg_options.get(key)
                source = "config" if value is not None else None
            values[key], sources[key] = value, source
        if any(source is None for source in sources.values()):
            return ("config_invalid" if cfg_error else "no_engine_configured"), None
        endpoint = values["embedding_endpoint"]
        model = values["embedding_model"]
        digest = values["embedding_model_digest"]
        if sources["embedding_endpoint"] == "config" and not config_endpoint_ok(
            endpoint
        ):
            return "endpoint_not_loopback", None
        if (sources["embedding_model"] == "config" and not valid_model(model)) or (
            sources["embedding_model_digest"] == "config" and not valid_digest(digest)
        ):
            return "model_digest_mismatch", None
        return None, EmbeddingConfig(
            endpoint=endpoint,
            model=model,
            model_digest=digest,
            chunking_version=request.get("embedding_chunking_version") or "mc12-v1",
        )

    @staticmethod
    def _tags_fallback(config: EmbeddingConfig) -> str | None:
        """72-T08 F8: `/api/tags` must list the configured model with a full digest that
        starts with the configured one."""
        try:
            tags = _embeddings.fetch_model_tags(config.endpoint)
        except EmbeddingEngineTimeout:
            return "engine_timeout"
        except EmbeddingEngineUnavailable:
            return "engine_unreachable"
        except EmbeddingResponseError:
            return "model_digest_mismatch"
        if _embeddings.model_matches(tags, config.model, config.model_digest):
            return None
        return "model_digest_mismatch"

    @staticmethod
    def _fill_access(access: MemoryAccess) -> MemoryAccess | None:
        """72-T08 §3.5: the write authority an embedding fill needs, or `None`."""
        from ..memory.authorization import user_overlay_owner_scope

        if access.kind == "policy":
            fill = MemoryAccess.resolve(  # type: ignore[call-arg]  # 72-T05 resolve(task_id=)
                access.project_root,
                operation="write",
                apply=True,
                overlay=(
                    access.owner_scope
                    == user_overlay_owner_scope(data_root=access.data_root)
                ),
                owner_scope=access.owner_scope,
                requested_sources=access.requested_sources,
                session_binding=access.session_binding,
                data_root=access.data_root,
                task_id=access.task_id,  # type: ignore[attr-defined]  # 72-T05 MemoryAccess.task_id
            )
            if (
                fill is not None
                and fill.kind == "policy"
                and "write" in fill.required_operations
                and fill.owner_scope == access.owner_scope
            ):
                return fill
            return None
        if (
            memory_policy_mode(access.project_root, data_root=access.data_root)
            == "legacy"
        ):
            return access
        return None

    @staticmethod
    def _absent_store_page(
        finish: Callable[[str, dict[str, Any]], ToolResult],
        encoding: str,
        *,
        hybrid: bool,
        fallback: str | None,
    ) -> ToolResult:
        """72-T08 §3.8: the empty page for a project with no store, its size measured
        with every label it carries; nothing embedded, `.rush` never created. 72-T02:
        `finish` fits it to the transport frame."""
        labels: dict[str, Any] | None = None
        code = "OK"
        if fallback is not None:
            labels = _fallback_labels(fallback, 0)
            code = "E_EMBEDDING_UNAVAILABLE"
        elif hybrid:
            labels = {
                "retrieval": "hybrid",
                "candidates_truncated": False,
                "incomplete_reason": None,
                "embedded_texts": 0,
            }
        empty: dict[str, Any] = {
            "items": [],
            "next_cursor": None,
            "complete": True,
            "tokens": 0,
            "bytes": 0,
            "encoding": encoding,
            **(labels or {}),
        }
        # 72-T02 (T074 F8): the real serialized size, the same as an empty page from an
        # existing store.
        empty["bytes"], empty["tokens"] = _measure_page(
            [], None, True, encoding, labels
        )
        return finish(code, empty)

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
        embed_config: EmbeddingConfig | None = None,
        fallback: str | None = None,
        fill_access: MemoryAccess | None = None,
    ) -> ToolResult:
        """`_compact_query()`'s page over an opened store and a resolved access.

        72-T08: `retrieval="hybrid"` with no `fallback` runs `hybrid_page()` with the
        resolved engine; a `fallback` code is a labelled lexical page (`OK` reported as
        `E_EMBEDDING_UNAVAILABLE`, every other code kept)."""
        root = store.project_root
        # 72-T02 R2: a hybrid read over a read-only view of a store whose writable
        # open would run DDL creates nothing, the labelled lexical fallback included.
        # A current store read through its view still records the delivery (R5a).
        telemetry = (
            cast(TelemetryStore, _LazyTelemetry(lambda: TelemetryStore(root)))
            if granted.cache_write
            and not (
                retrieval == "hybrid"
                and getattr(store, "_readonly_conn", None) is not None
                and not store.writable_open_ddl_free()
            )
            else None
        )
        if retrieval == "hybrid" and fallback is None:
            page = hybrid_page(
                store,
                subject=subject,
                query=query or "",
                access=access,
                embed_config=embed_config,
                fill_access=fill_access,
                mode="ordinary",
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
            # The fallback labels ride in the page and count in every measure; a plain
            # lexical read passes no `extra`, so its page is unchanged.
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
                extra=_fallback_labels(fallback, 0) if fallback is not None else None,
            )
            if fallback is not None and page["code"] == "OK":
                page["code"] = "E_EMBEDDING_UNAVAILABLE"
        if (
            retrieval == "hybrid"
            and page["code"] == "E_MIGRATION"
            and "message" not in page
        ):
            # 72-T02 B12: a hybrid read over a store that needs a write to open names
            # why, as the state-denial branch does, when the framed response fits.
            page = _fit_optional(
                {**page, "message": readonly_view_reason("migration_required")},
                fit,
                encoding,
                max_bytes,
                max_tokens,
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

        resolved = self._read_access(
            root, "expand", session_allowlist, owner, task_id=_TASK_ID.get()
        )
        if isinstance(resolved, RouteDenial):
            denied = finish(resolved.code, _denial_data("expand", resolved))
            if isinstance(resolved, _PolicyDenial):
                _attach_policy_next_action(
                    denied,
                    reason=resolved.reason,
                    project_root=resolved.project_root,
                    operations=resolved.operations,
                    owner_scope=resolved.owner_scope,
                    requested_sources=resolved.requested_sources,
                    budget=(encoding, max_bytes, max_tokens),
                )
            return denied
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
        store = self._readonly_store if access.storage_root == root else None
        own_view = store is None
        if store is None:
            store, state = TypedArtifactStore.open_readonly_view(access.storage_root)
            if state is not None:
                return finish(
                    _READ_STATE_CODES[state], {"message": readonly_view_reason(state)}
                )
        if store is None:
            return finish("E_NOT_VISIBLE", not_visible)
        # D25: an expand of the personal overlay store is not this project's usage, so
        # it records nothing in the project's token economy.
        telemetry = (
            cast(TelemetryStore, _LazyTelemetry(lambda: TelemetryStore(root)))
            if granted.cache_write and access.storage_root == root
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
        resolved = self._read_access(
            root, "link", None, owner, apply=True, task_id=_TASK_ID.get()
        )
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
        # 72-T06 D22: the receiver's own route gate first (its denial names the grant
        # that fixes it), then the sender's authority, as `expand` and `resume` do.
        resolved: MemoryAccess | RouteDenial = self._read_access(
            root, "related", session_allowlist, owner, task_id=_TASK_ID.get()
        )
        if not isinstance(resolved, RouteDenial) and bridge is not None:
            authority = self._bridge_access(started, "related", bridge, artifact_id)
            if isinstance(authority, dict):
                return cast(ToolResult, authority)
            resolved = authority
        if isinstance(resolved, RouteDenial):
            return self._denied(started, "related", resolved)
        store = self._readonly_store if resolved.storage_root == root else None
        own_view = store is None
        if store is None:
            store, state = TypedArtifactStore.open_readonly_view(resolved.storage_root)
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
        resolved = self._read_access(
            root,
            "consolidate",
            requested,
            owner,
            apply=True,
            task_id=_TASK_ID.get(),
        )
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
                task_id=_TASK_ID.get(),
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
        prepare_access = (
            gated
            if isinstance(gated, MemoryAccess) and gated.kind == "policy"
            else None
        )
        if bridge is not None:
            authority = self._bridge_access(started, operation, bridge)
            if isinstance(authority, dict):
                return cast(ToolResult, authority)
            allowlist = list(authority.sources)
            # 72-T05 3.12: a delegated read carries the sender's task context, which
            # the sender's authority already holds.
            prepare_access = authority if authority.kind == "policy" else None
        result = prepare_memory(
            project_root=root,
            symptom=query or task,
            conditions=conditions,
            behavior_ids=behavior_ids,
            session_allowlist=allowlist,
            access=prepare_access,
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

    def _preference(
        self,
        started: float,
        root: Path,
        granted: ExecutionPermissions,
        request: dict[str, Any] | None,
        session_allowlist: list[str] | None,
    ) -> ToolResult:
        """72-T05 §3.1/§3.13/§3.14: layered preferences. Precedence: strict request,
        `memory_policy_decision`, the legacy write refusal, the layer/owner predicate,
        the apply-only `cache_write`/`user_stated` checks, the D2 resolve, then the
        `PreferenceStore` action (which owns every row, id and content check)."""
        from pydantic import TypeAdapter, ValidationError

        from ..mcp_support.request_models import _REQUEST_MODELS
        from ..memory.authorization import MemoryPolicyError, user_overlay_owner_scope
        from ..memory.preference_store import PreferenceError, PreferenceStore
        from ..memory.retrieval import is_overlay_owner

        task_id = _TASK_ID.get()

        def refuse(code: str, reason: str, **extra: Any) -> ToolResult:
            return self._envelope_result(
                started,
                "preference",
                code,
                {**extra, "reason": reason, "message": f"{code}: {reason}"},
            )

        if not isinstance(request, dict):
            return refuse("E_INPUT", "request_invalid", field="request")
        try:
            TypeAdapter(_REQUEST_MODELS["preference"]).validate_python(request)
        except ValidationError as exc:
            errors = exc.errors(include_url=False, include_input=False)
            loc = [str(p) for p in errors[0]["loc"]] if errors else []
            if len(loc) > 1 and loc[0] == request.get("action"):
                loc = loc[1:]
            field = loc[0] if loc else "action"
            reason = f"{field}_invalid"
            if (
                field == "authority"
                and request.get("authority") == "imported_unverified"
            ):
                reason = "authority_import_only"  # only a reviewed import writes it
            return refuse(
                "E_INPUT",
                reason,
                field=field,
                details=[
                    {"loc": [str(p) for p in e["loc"]], "msg": e["msg"]} for e in errors
                ],
            )
        action = request["action"]
        if action != "end_task" and "task_id" in request:
            return refuse("E_INPUT", "task_id_top_level", field="task_id")
        try:
            owner = (
                None
                if request.get("owner_scope") is None
                else OwnerScope.from_value(request["owner_scope"])
            )
        except (TypeError, ValueError):
            return refuse("E_INPUT", "owner_scope_invalid", field="owner_scope")

        mode, why = memory_policy_decision(root)
        if mode == "unavailable":
            return refuse("E_PERMISSION", why or "policy_invalid")
        apply = bool(request.get("apply", False))
        user_stated = bool(request.get("user_stated", False))
        try:
            store = PreferenceStore(root)
            if mode == "legacy":
                if action != "resolve":
                    return refuse("E_PERMISSION", "policy_grant_required")
                legacy = MemoryAccess.legacy(
                    root,
                    session_allowlist,
                    owner_scope=legacy_owner_scope(root),
                    operation="preference",
                    task_id=task_id,
                )
                if not legacy.sources:
                    return refuse("E_PERMISSION", "session_allowlist_required")
                return self._preference_result(
                    started,
                    store.resolve(
                        request.get("key"),
                        access=legacy,
                        overlay_access=None,
                        query=request.get("query"),
                        project_id=request.get("project_id"),
                        worktree_id=request.get("worktree_id"),
                        task_id=task_id,
                    ),
                )

            personal = is_overlay_owner(owner, None)
            mismatch = {
                "resolve": personal,
                "record": (request.get("scope") == "personal") != personal,
                "correct": (request.get("layer") == "personal") != personal,
                "end_task": personal,
                "migrate": personal,
            }[action]
            if mismatch:
                return refuse("E_OWNER", "layer_owner_mismatch")
            if apply and action != "resolve":
                if not granted.cache_write:
                    return refuse("E_PERMISSION", "cache_write_required")
                needs_statement = action == "correct" or (
                    action == "record" and request.get("authority") == "explicit"
                )
                if needs_statement and not user_stated:
                    return refuse("E_PERMISSION", "user_stated_required")

            if action == "resolve":
                project, project_why = MemoryAccess.resolve_with_reason(
                    root,
                    operation="preference",
                    action="resolve",
                    owner_scope=owner,
                    requested_sources=session_allowlist or (),
                    task_id=task_id,
                )
                overlay, _overlay_why = MemoryAccess.resolve_with_reason(
                    root,
                    operation="preference",
                    action="resolve",
                    owner_scope=user_overlay_owner_scope(),
                    task_id=task_id,
                )
                # An explicit owner the project grant does not name is refused even
                # when the personal layer alone could still resolve (D2: E_OWNER).
                if project is None and (
                    overlay is None
                    or project_why == "owner_required"
                    or (owner is not None and project_why == "owner_not_granted")
                ):
                    return self._preference_denial(
                        refuse,
                        project_why,
                        owner,
                        root=root,
                        action=action,
                        apply=apply,
                        sources=session_allowlist or (),
                    )
                ids = project or overlay
                assert ids is not None
                return self._preference_result(
                    started,
                    store.resolve(
                        request.get("key"),
                        access=project,
                        overlay_access=overlay,
                        query=request.get("query"),
                        project_id=request.get("project_id", ids.project_id),
                        worktree_id=request.get("worktree_id", ids.worktree_id),
                        task_id=task_id,
                    ),
                )

            if action == "migrate":
                sources: list[str] = ["migration:preference_store"]
            elif action == "record" and request.get("source") is not None:
                sources = [request["source"]]
            else:
                sources = []
            access, access_why = MemoryAccess.resolve_with_reason(
                root,
                operation="preference",
                action=action,
                apply=apply,
                owner_scope=user_overlay_owner_scope() if personal else owner,
                requested_sources=sources,
                task_id=task_id,
            )
            if access is None:
                return self._preference_denial(
                    refuse,
                    access_why,
                    owner,
                    root=root,
                    action=action,
                    apply=apply,
                    sources=sources,
                )
            cache_write = granted.cache_write
            if action == "record":
                result = store.record(
                    request["key"],
                    request["value"],
                    access=access,
                    apply=apply,
                    cache_write=cache_write,
                    scope=request["scope"],
                    authority=request["authority"],
                    task_id=task_id,
                    expires_at=request.get("expires_at"),
                    user_stated=user_stated,
                    attribution=request.get("attribution"),
                )
            elif action == "correct":
                value = {"value": request["value"]} if "value" in request else {}
                result = store.correct_with_receipt(
                    request["artifact_id"],
                    access=access,
                    apply=apply,
                    cache_write=cache_write,
                    layer=request["layer"],
                    kind=request["kind"],
                    reason=request["reason"],
                    expected_version=request["expected_version"],
                    user_stated=user_stated,
                    receipt_operation_id=request.get("receipt_operation_id"),
                    **value,
                )
            elif action == "end_task":
                result = store.end_task(
                    access=access,
                    apply=apply,
                    cache_write=cache_write,
                    project_id=cast(str, request.get("project_id", access.project_id)),
                    worktree_id=cast(
                        str, request.get("worktree_id", access.worktree_id)
                    ),
                    task_id=request["task_id"],
                    expected_versions=request["expected_versions"],
                )
            else:
                result = store.migrate(
                    access=access,
                    apply=apply,
                    cache_write=cache_write,
                    preview_digest=request.get("preview_digest"),
                )
        except PreferenceError as exc:
            return refuse(exc.code, exc.reason)
        except MemoryPolicyError as exc:
            return refuse("E_PERMISSION", str(getattr(exc, "reason", "policy_invalid")))
        return self._preference_result(started, result)

    @staticmethod
    def _preference_denial(
        refuse: Callable[..., ToolResult],
        reason: str,
        owner: OwnerScope | None,
        *,
        root: Path,
        action: str,
        apply: bool,
        sources: Sequence[str],
    ) -> ToolResult:
        """D2 resolve denial mapping (§3.1); a policy denial also names the command
        that fixes it (73-T02 item 7)."""
        if reason == "source_not_granted":
            denied = refuse("E_SCOPE", reason)
        elif reason == "owner_not_granted" and owner is not None:
            denied = refuse("E_OWNER", reason)
        elif reason == "owner_required":
            denied = refuse("E_INPUT", reason, field="owner_scope")
        else:
            denied = refuse("E_PERMISSION", reason)
        _attach_policy_next_action(
            denied,
            reason=reason,
            project_root=root,
            operations=required_operation_set(
                "preference", action=action, apply=apply and action != "resolve"
            ),
            owner_scope=owner,
            requested_sources=sources,
        )
        return denied

    def _preference_result(self, started: float, result: dict[str, Any]) -> ToolResult:
        """A `PreferenceStore` answer as the envelope: `code` (default `OK`) plus every
        other key as `data`, identical to the in-process dict."""
        data = {k: v for k, v in result.items() if k != "code"}
        return self._envelope_result(
            started, "preference", str(result.get("code", "OK")), data
        )

    def _capsule(
        self,
        started: float,
        root: Path,
        granted: ExecutionPermissions,
        request: dict[str, Any] | None,
        transport: Literal["cli", "mcp"],
    ) -> ToolResult:
        """73-T09/CODEC: portable capsule export/import (`rush.memory.capsule`)."""
        from ..memory import capsule

        if request is None:
            return self._envelope_result(
                started,
                "capsule",
                "E_INPUT",
                {"field": "request", "message": "memory capsule requires a request."},
            )
        if not isinstance(request, dict):
            return self._envelope_result(
                started,
                "capsule",
                "E_INPUT",
                {
                    "field": "request",
                    "message": "memory capsule request must be an object.",
                },
            )
        unknown = sorted(str(k) for k in request if k not in _CAPSULE_REQUEST_KEYS)
        if unknown:
            return self._envelope_result(
                started,
                "capsule",
                "E_INPUT",
                {
                    "field": unknown[0],
                    "message": f"unknown capsule request field {unknown[0]!r}.",
                },
            )
        outcome = capsule.run_capsule(
            root, request, permissions=granted, transport=transport
        )
        if outcome.get("skipped"):
            action = str(outcome["action"])
            missing = list(outcome["missing"])
            return self._result(
                started,
                "skipped",
                f"memory capsule {action} requires {', '.join(missing)}.",
                operation="capsule",
                raw={
                    "schema_version": 1,
                    "operation": "capsule",
                    "action": action,
                    "missing_permissions": missing,
                },
            )
        data = dict(outcome)
        code = str(data.pop("code"))
        if data.pop("denial", False):
            # A policy denial goes through the one 72-T01 denial site.
            result = self._denied(
                started, "capsule", RouteDenial(code, str(data.pop("reason")))
            )
            cast(dict[str, Any], result["raw"])["data"].update(data)
            return result
        return self._envelope_result(started, "capsule", code, data)

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
        task_id: str | None = None,
        request_sources: list[str] | None = None,
    ) -> MemoryAccess | RouteDenial:
        """72-T01 D1/D2 access for one route (`retrieval.route_access`): `legacy`
        mode builds the explicit-allowlist form (a source-less one keeps each route's
        fail-closed output), `policy` mode resolves the grant (the allowlist only
        narrows it), `unavailable` mode denies. `request_sources` names the
        request's own sources when the route narrows to an internal label."""
        resolved = route_access(
            root,
            operation,
            action=action,
            apply=apply,
            historical=historical,
            session_allowlist=session_allowlist,
            owner_scope=owner,
            task_id=task_id,
        )
        sources = list(session_allowlist or ())
        if not isinstance(resolved, RouteDenial) or _source_input_denial(sources):
            return resolved
        # A D1 `unavailable` reason or a denied policy resolve: keep the denied
        # call's inputs for its `next_action` (73-T02 H4).
        try:
            operations = required_operation_set(
                operation, action=action, apply=apply, historical=historical
            )
        except ValueError:
            operations = ()
        return _PolicyDenial(
            resolved.code,
            resolved.reason,
            project_root=root,
            operations=operations,
            owner_scope=owner,
            requested_sources=tuple(
                sources if request_sources is None else request_sources
            ),
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
            root,
            operation,
            allowlist,
            owner,
            historical=historical,
            task_id=_TASK_ID.get(),
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
            required = self._envelope_result(
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
            if isinstance(denial, _PolicyDenial):
                _attach_policy_next_action(
                    required,
                    reason=denial.reason,
                    project_root=denial.project_root,
                    operations=denial.operations,
                    owner_scope=denial.owner_scope,
                    requested_sources=denial.requested_sources,
                )
            return required
        return self._denied(started, operation, denial)

    def _denied(
        self, started: float, operation: str, denial: RouteDenial
    ) -> ToolResult:
        """A D1 denial: the denial code with its exact reason, before any effect. A
        policy denial also names the command that fixes it (73-T02 item 7)."""
        result = self._envelope_result(
            started, operation, denial.code, _denial_data(operation, denial)
        )
        if isinstance(denial, _PolicyDenial):
            _attach_policy_next_action(
                result,
                reason=denial.reason,
                project_root=denial.project_root,
                operations=denial.operations,
                owner_scope=denial.owner_scope,
                requested_sources=denial.requested_sources,
            )
        return result

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
        resolved = self._read_access(
            root, "write", [source], owner, apply=apply, task_id=_TASK_ID.get()
        )
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
        from ..memory.authorization import MemoryPolicyError, source_granted

        root = _canonical_root(root)
        apply, grants, _, request_error = self._parse_mutation_request(
            request, _PROMOTE_REQUEST_KEYS
        )
        source_id = (request or {}).get("source_id")
        expected_version = (request or {}).get("expected_version")
        candidate_refs = (request or {}).get("candidate_refs")
        if not request_error and (source_id is None) != (expected_version is None):
            request_error = "source_id and expected_version are given together."
        if (
            not request_error
            and source_id is not None
            and not (_literal_id(source_id) and _revision_ok(expected_version))
        ):
            request_error = (
                "source_id must be a non-empty ID and expected_version a positive int."
            )
        if (
            not request_error
            and candidate_refs is not None
            and not _candidate_refs_ok(candidate_refs)
        ):
            request_error = "invalid promotion candidate refs"
        if request_error:
            return self._result(
                started,
                "error",
                request_error,
                operation="promote",
                raw={"message": request_error},
            )
        if candidate_sources is not None and candidate_refs is None:
            # 72-T04 D8: raw source labels are never evidence; only reviewed refs are.
            return self._envelope_result(
                started,
                "promote",
                "E_INPUT",
                {
                    "field": "candidate_sources",
                    "message": "candidate_sources requires request.candidate_refs",
                },
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
        except (TypeError, ValueError) as exc:
            return self._result(
                started, "error", f"invalid owner_scope: {exc}", operation="promote"
            )
        # 72-T04 D8: policy mode resolves every approved source (granted
        # corroborators stay visible) and checks the candidate's source separately;
        # legacy mode keeps the candidate-source allowlist for the candidate write.
        policy = memory_policy_mode(root) == "policy"
        resolved = self._read_access(
            root,
            "promote",
            None if policy else [source],
            owner,
            apply=apply,
            task_id=_TASK_ID.get(),
        )
        if isinstance(resolved, RouteDenial):
            if isinstance(resolved, _PolicyDenial):
                # H4: the candidate's `source` is the request's source (the access
                # itself resolves every approved source); the grant must cover it.
                resolved = dataclasses.replace(resolved, requested_sources=(source,))
            return self._denied(started, "promote", resolved)
        if resolved.kind == "policy" and not source_granted(source, resolved.sources):
            unsourced = self._envelope_result(
                started,
                "promote",
                "E_SCOPE",
                {
                    "reason": "source_not_granted",
                    "message": "memory promote denied: source_not_granted.",
                },
            )
            _attach_policy_next_action(
                unsourced,
                reason="source_not_granted",
                project_root=root,
                operations=required_operation_set("promote", apply=apply),
                owner_scope=owner,
                requested_sources=(source,),
            )
            return unsourced
        owner = _write_owner(owner, resolved)
        artifact = self._build_artifact(
            subject, content, source, symbol_ref, source_kind, owner
        )
        store_refs: list[dict[str, Any]] | None = None
        if candidate_refs is not None:
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
                refused = self._promote_refs_refusal(
                    started,
                    view,
                    root,
                    resolved,
                    owner,
                    artifact,
                    source_id,
                    expected_version,
                    candidate_refs,
                )
            finally:
                view.close()
            if refused is not None:
                return refused
            # The reviewed source row is the candidate's own observation, never a
            # corroborator of it: only the other refs reach the D8 evidence check.
            store_refs = [ref for ref in candidate_refs if ref["id"] != source_id]
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
            preview["candidate_sources"] = sorted(
                {str(ref["source"]) for ref in store_refs or []}
            )
            return self._result(
                started,
                "ok",
                f"Preview: would create a candidate in subject '{subject}' and "
                "request its promotion to STATED.",
                operation="promote",
                raw=preview,
            )
        promotion_error: VersionConflictError | None = None
        policy_error: MemoryPolicyError | None = None
        with _policy_mutation(resolved) as refused_access:
            if refused_access is not None:
                return self._denied(started, "promote", refused_access)
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
                    candidate_refs=store_refs,
                    expected_version=stored.artifact_version,
                    owner_scope=owner,
                    receipt_operation_id=reserved.get("promotion"),
                    access=resolved if resolved.kind == "policy" else None,
                    commit_check=_commit_check(resolved),
                )
            except VersionConflictError as conflict:
                promotion_error = conflict
            except MemoryPolicyError as exc:
                policy_error = exc
        if policy_error is not None:
            reason = policy_error.reason or policy_error.code
            # the candidate was already committed: name it, so adapters refresh.
            return self._envelope_result(
                started,
                "promote",
                policy_error.code,
                {
                    "reason": reason,
                    "message": f"memory promote denied: {reason}.",
                    "artifact": self._artifact_dict(stored),
                },
            )
        if promotion_error is not None:
            return self._result(
                started,
                "fail",
                "Promotion candidate created but corroboration changed: "
                f"{promotion_error}",
                operation="promote",
                raw={
                    "code": getattr(promotion_error, "code", "E_VERSION"),
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

    def _promote_refs_refusal(
        self,
        started: float,
        view: Any,
        root: Path,
        access: MemoryAccess,
        owner: OwnerScope | None,
        artifact: MemoryArtifact,
        source_id: str | None,
        expected_version: int | None,
        candidate_refs: list[dict[str, Any]],
    ) -> ToolResult | None:
        """72-T04 D8 review check before the candidate is written: the reviewed
        source row (when named) must still be the live row it was, and every other
        ref must name a row this access can see (`E_NOT_VISIBLE` otherwise -- a
        hidden id and an absent id are indistinguishable) that still matches the
        candidate at the reviewed version and source (`E_VERSION` otherwise). The
        store re-checks the refs against its own peer scan inside the promotion
        transaction."""
        from ..memory.authorization import source_granted

        message = "promotion corroborator changed since review"
        if access.kind == "policy":
            visible_sources = list(access.sources)
            visible_owner = access.owner_scope
        else:
            visible_sources = sorted(
                {artifact.source, *(str(ref["source"]) for ref in candidate_refs)}
            )
            visible_owner = owner or legacy_owner_scope(root)
        if source_id is not None:
            selected = view.get_current(source_id)
            if not (
                selected is not None
                and selected.artifact_version == expected_version
                and any(ref["id"] == source_id for ref in candidate_refs)
                and selected.source == artifact.source
                and selected.subject == artifact.subject
                and selected.symbol_ref == artifact.symbol_ref
                and selected.content == artifact.content
                and selected.owner_scope == visible_owner
                and selected.archived_at is None
            ):
                return self._result(
                    started,
                    "fail",
                    "promotion candidates changed since review",
                    operation="promote",
                    raw={"code": "E_VERSION", "reason": "candidate changed"},
                )
        code: str | None = None
        for ref in candidate_refs:
            if ref["id"] == source_id:
                continue
            current = view.get_current(ref["id"])
            if (
                current is None
                or not source_granted(current.source, visible_sources)
                or current.owner_scope != visible_owner
            ):
                code = "E_NOT_VISIBLE"
                break
            if (
                current.artifact_version != ref["version"]
                or current.source != ref["source"]
                or current.subject != artifact.subject
                or current.symbol_ref != artifact.symbol_ref
                or current.content != artifact.content
                or current.trust_tier in ("STATED", "IMPORTED")
                or current.stale
                or current.archived_at is not None
            ):
                code = "E_VERSION"
                break
        if code is None:
            return None
        return self._result(
            started,
            "fail",
            f"Promotion refused: {message}.",
            operation="promote",
            raw={"code": code, "reason": message},
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
        sources: list[str] | None = None,
        session_allowlist: list[str] | None = None,
    ) -> ToolResult:
        from ..memory.authorization import literal_source_is_valid, source_granted
        from ..memory.maintenance import MaintenanceAccessDenied

        root = _canonical_root(root)
        if task is None:
            return self._result(
                started,
                "error",
                "memory maintain requires task.",
                operation="maintain",
            )
        if task not in get_args(MaintenanceTask):
            return self._envelope_result(
                started,
                "maintain",
                "E_INPUT",
                {"field": "task", "message": "unknown maintenance task"},
            )
        apply, grants, candidate_ids, request_error = self._parse_mutation_request(
            request, _MAINTAIN_REQUEST_KEYS
        )
        expected_revisions = (request or {}).get("expected_revisions")
        if not request_error and expected_revisions is not None:
            if not (
                isinstance(expected_revisions, dict)
                and all(
                    _literal_id(k) and _revision_ok(v)
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
        if type(batch_size) is not int or not 1 <= batch_size <= 1000:
            return self._envelope_result(
                started,
                "maintain",
                "E_INPUT",
                {"field": "batch_size", "message": "batch_size must be 1-1000"},
            )
        requested = sources if sources is not None else session_allowlist
        if requested is not None and not (
            isinstance(requested, list)
            and all(literal_source_is_valid(s) for s in requested)
        ):
            return self._envelope_result(
                started,
                "maintain",
                "E_INPUT",
                {"field": "sources", "message": "sources must be literal labels"},
            )
        try:
            owner = self._parse_owner_scope(owner_scope, root)
        except (TypeError, ValueError) as exc:
            return self._result(
                started, "error", f"invalid owner_scope: {exc}", operation="maintain"
            )
        # 72-T04 D9/D3: the access names the owner and sources every selection,
        # peer scan and revision lookup is scoped to.
        legacy_owner = legacy_owner_scope(root)
        access: MemoryAccess
        if memory_policy_mode(root) == "legacy":
            if not requested:
                return self._denied(
                    started, "maintain", RouteDenial("E_PERMISSION", "sources_required")
                )
            if owner is not None and owner != legacy_owner:
                return self._denied(
                    started, "maintain", RouteDenial("E_NOT_VISIBLE", "not_visible")
                )
            access = MemoryAccess.legacy(
                root,
                requested,
                owner_scope=legacy_owner,
                operation="write" if apply else "list",
                data_root=None,
                task_id=_TASK_ID.get(),
            )
        else:
            # Policy mode: the grant's approved sources, narrowed to the requested
            # ones it grants (D9); a request naming none of them is `E_SCOPE`
            # (73-T02: `owner_not_granted` is `E_OWNER`, every policy denial names
            # the command that fixes it).
            narrowed: list[str] | None = None
            resolved = self._read_access(
                root, "maintain", None, owner, apply=apply, task_id=_TASK_ID.get()
            )
            if not isinstance(resolved, RouteDenial) and requested:
                narrowed = [s for s in requested if source_granted(s, resolved.sources)]
                if not narrowed:
                    resolved = _PolicyDenial(
                        "E_PERMISSION",
                        "source_not_granted",
                        project_root=root,
                        operations=required_operation_set("maintain", apply=apply),
                        owner_scope=owner,
                        requested_sources=tuple(requested),
                    )
                else:
                    resolved = self._read_access(
                        root,
                        "maintain",
                        narrowed,
                        owner,
                        apply=apply,
                        task_id=_TASK_ID.get(),
                    )
            if isinstance(resolved, RouteDenial):
                return self._denied(started, "maintain", _granular_code(resolved))
            access = resolved
        maintained_owner = access.owner_scope or legacy_owner
        if not apply:
            try:
                candidates = preview_maintenance_candidates(
                    task,
                    access=access,
                    batch_size=batch_size,
                    project_root=root,
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
            except MaintenanceAccessDenied as exc:
                return self._maintenance_denied(started, exc)
            # D1 race rule: a grant revoked while the candidates were read returns the
            # denial and none of them.
            revoked = self._revoked(started, "maintain", access)
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
                    "owner_scope": {
                        "kind": maintained_owner.kind,
                        "id": maintained_owner.id,
                    },
                    "required_grants": effective,
                    "missing_grants": _missing_grants(effective, granted),
                },
            )
        # Restricted only when a reviewed candidate set was sent; otherwise the
        # legacy unrestricted call is unchanged. The cycle owns its policy lock,
        # lease and hold deadline (72-T04 D26): no adapter lock encloses it.
        restriction: dict[str, Any] = (
            {} if candidate_ids is None else {"candidate_ids": candidate_ids}
        )
        if expected_revisions is not None:
            restriction["expected_revisions"] = expected_revisions
        try:
            result = run_maintenance_cycle(
                task,
                access=access,
                batch_size=batch_size,
                project_root=root,
                **restriction,
            )
        except MaintenanceAccessDenied as exc:
            return self._maintenance_denied(started, exc)
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
                + ("not visible" if c.actual is None else f"v{c.actual}")
                for c in result.refused
            )
        lock_lost = bool(getattr(result, "lock_lost", False))
        if lock_lost:
            summary += " Maintenance lease lost; unprocessed: " + ", ".join(
                getattr(result, "unprocessed", ())
            )
        return self._result(
            started,
            "fail" if lock_lost else ("warn" if result.refused else "ok"),
            summary,
            operation="maintain",
            raw=maintain_raw,
        )

    def _maintenance_denied(self, started: float, exc: Any) -> ToolResult:
        """A maintenance access refusal (72-T04 D9): its code and reason, and the
        selected rows it left unprocessed."""
        reason = str(getattr(exc, "reason", "") or "access_changed")
        return self._envelope_result(
            started,
            "maintain",
            str(getattr(exc, "code", "E_PERMISSION")),
            {
                "reason": reason,
                "message": f"memory maintain denied: {reason}.",
                "unprocessed": list(getattr(exc, "unprocessed", ())),
            },
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
        resolved = self._read_access(
            root, "verify_attempt", None, owner, apply=True, task_id=_TASK_ID.get()
        )
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
            task_id=_TASK_ID.get(),
            request_sources=[],
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
                access=resolved if resolved.kind == "policy" else None,
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
            task_id=_TASK_ID.get(),
            request_sources=[],
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
                access=resolved if resolved.kind == "policy" else None,
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
        gate = self._read_access(
            root, "handoff", None, owner, action=action, task_id=_TASK_ID.get()
        )
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
            root,
            "handoff",
            session_allowlist,
            owner,
            action=action,
            task_id=_TASK_ID.get(),
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
        gate = self._read_access(root, "receive", None, owner, task_id=_TASK_ID.get())
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
        resolved = self._read_access(
            root, "delete", None, owner, apply=apply, task_id=_TASK_ID.get()
        )
        if isinstance(resolved, RouteDenial):
            return self._denied(started, "delete", resolved)
        owner = _write_owner(owner, resolved)
        hidden = _hidden_targets(
            resolved,
            artifact_ids,
            lambda: TypedArtifactStore.open_readonly_view(resolved.storage_root),
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
                view, view_state = TypedArtifactStore.open_readonly_view(
                    resolved.storage_root
                )
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
                    store = TypedArtifactStore(resolved.storage_root)
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
        resolved = self._read_access(
            root, operation, None, owner, apply=apply, task_id=_TASK_ID.get()
        )
        if isinstance(resolved, RouteDenial):
            return self._denied(started, operation, resolved)
        owner = _write_owner(owner, resolved)
        hidden = _hidden_targets(
            resolved,
            [artifact_id],
            lambda: TypedArtifactStore.open_readonly_view(resolved.storage_root),
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
                    resolved.storage_root,
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
                        result = TypedArtifactStore(resolved.storage_root).archive(
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


def _valid_task_id(task_id: Any) -> bool:
    """§3.11: a non-empty string with no Cc (incl. NUL), Cf or lone surrogate."""
    import unicodedata

    return (
        type(task_id) is str
        and bool(task_id)
        and all(unicodedata.category(ch) not in {"Cc", "Cf", "Cs"} for ch in task_id)
    )


def _overlay_owner_named(owner_scope: Any, request: Any) -> OwnerScope | None:
    """The personal-overlay owner when the call's `owner_scope` (argument or
    request field) is it (D25 owner equality; malformed owners are not), else
    `None`."""
    from ..memory.retrieval import is_overlay_owner

    candidates = [owner_scope]
    if isinstance(request, dict):
        candidates.append(request.get("owner_scope"))
    for value in candidates:
        if value is None:
            continue
        try:
            owner = OwnerScope.from_value(value)
        except (TypeError, ValueError):
            continue
        if is_overlay_owner(owner, None):
            return owner
    return None


# --- 73-T02 policy-denial guidance -------------------------------------------


@dataclasses.dataclass(frozen=True)
class _PolicyDenial(RouteDenial):
    """A `RouteDenial` whose reason came from a policy decision (a denied resolve or
    a D1 `unavailable` reason), with the denied call's own inputs."""

    project_root: Path = Path()
    operations: tuple[str, ...] = ()
    owner_scope: OwnerScope | None = None
    requested_sources: tuple[str, ...] = ()


def _recheck_denial(access: MemoryAccess) -> RouteDenial | None:
    """`recheck_failure` as a denial: a policy access the fresh resolve denies is a
    policy denial with the re-resolve's inputs."""
    failure = recheck_failure(access)
    if failure is None:
        return None
    if access.kind != "policy" or failure[0] != "E_PERMISSION":
        return RouteDenial(*failure)
    return _PolicyDenial(
        *failure,
        project_root=access.project_root,
        operations=tuple(access.required_operations_order),
        owner_scope=access.owner_scope,
        requested_sources=tuple(access.requested_sources),
    )


_NEXT_ACTION_CODES = frozenset({"E_PERMISSION", "E_OWNER", "E_SCOPE"})
_GRANULAR_CODES = {"owner_not_granted": "E_OWNER", "source_not_granted": "E_SCOPE"}


def _granular_code(denial: RouteDenial) -> RouteDenial:
    """Plan section 2.1 item 3 codes for a policy denial of v1 `maintain` (which always
    names its owner): `owner_not_granted` -> `E_OWNER`, `source_not_granted` ->
    `E_SCOPE`. The v1 compact read paths keep `E_PERMISSION`."""
    code = _GRANULAR_CODES.get(denial.reason)
    if code is None or not isinstance(denial, _PolicyDenial):
        return denial
    return dataclasses.replace(denial, code=code)


def _attach_policy_next_action(
    result: ToolResult,
    *,
    reason: str,
    project_root: Path,
    operations: Any,
    owner_scope: OwnerScope | None,
    requested_sources: Any,
    budget: tuple[str, int, int] | None = None,
) -> None:
    """D19: a policy denial's `raw.next_action` (`memory_next_action` of the denied
    call's inputs) and the ` Next: <command or text>` summary suffix. An existing
    `next_action` is never replaced. 72-T02 decisions.md:30: on a budgeted response
    (`budget` = encoding, max_bytes, max_tokens) both are optional-if-fits, measured
    on the exact frame the transport emits, and absent when that frame would not fit."""
    from ..memory.authorization import memory_next_action

    raw = result.get("raw")
    if not isinstance(raw, dict) or "next_action" in raw:
        return
    data = raw.get("data")
    code = raw.get("code")
    if code not in _NEXT_ACTION_CODES and not (
        code == "E_INPUT"
        and isinstance(data, dict)
        and data.get("field") == "owner_scope"
    ):
        return
    action = memory_next_action(
        reason=reason,
        project_root=project_root,
        operations=list(operations),
        owner_scope=owner_scope,
        requested_sources=list(requested_sources),
    )
    suffix = f" Next: {action['command'] or action['text']}"
    frame = compact.MEMORY_FRAME.get()
    if budget is not None and (frame is not None or raw.get("schema_version") == 2):
        encoding, max_bytes, max_tokens = budget
        trial = cast(ToolResult, copy.deepcopy(dict(result)))
        trial_raw = cast(dict[str, Any], trial["raw"])
        trial_raw["next_action"] = action
        trial["summary"] = f"{trial['summary']}{suffix}"
        if frame is None:
            # Outside a transport frame a v2 cap measures the canonical v2 raw
            # (`_v2_budget_floor`); inside one it measures the emitted frame (D35).
            used_bytes, used_tokens = _v2_measure(trial_raw, encoding)
        else:
            framed = compact.frame_bytes(
                frame,
                attach_memory_attribution(
                    trial,
                    _memory_attribution(
                        project_root, str(raw.get("operation")), trial, []
                    ),
                ),
            )
            used_bytes = len(framed)
            used_tokens = (
                used_bytes
                if used_bytes <= max_tokens
                else _frame_tokens(framed, encoding)
            )
        if used_bytes > max_bytes or used_tokens > max_tokens:
            return
    raw["next_action"] = action
    result["summary"] = f"{result['summary']}{suffix}"


def _personal_layer_guidance(result: Any, root: Path) -> None:
    """decisions.md:24: an OK preference resolve whose personal layer is denied
    names the overlay grant that fixes it (`list` + `overlay_read`)."""
    from ..memory.authorization import memory_next_action, user_overlay_owner_scope

    raw = result.get("raw") if isinstance(result, dict) else None
    if not isinstance(raw, dict) or raw.get("code") != "OK":
        return
    data = raw.get("data")
    layers = data.get("layers") if isinstance(data, dict) else None
    personal = layers.get("personal") if isinstance(layers, dict) else None
    if not isinstance(personal, dict) or personal.get("state") != "denied":
        return
    reason = str(personal.get("reason"))
    try:
        overlay = user_overlay_owner_scope()
    except Exception:  # noqa: BLE001 - no overlay owner: text-only guidance
        personal.setdefault(
            "next_action",
            {"text": f"memory access denied ({reason})", "command": None},
        )
        return
    guided = memory_next_action(
        reason=reason,
        project_root=root,
        operations=("list", "overlay_read"),
        owner_scope=overlay,
    )
    # A reason with no command (e.g. `revoked`) keeps 72-T05's truthful layer text.
    if guided["command"] is not None or "next_action" not in personal:
        personal["next_action"] = guided


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
        yield _recheck_denial(access)


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


def _canonical_root(root: Path) -> Path:
    """72-T04 G4: the on-disk spelling of an existing project root (a case variant
    on a case-insensitive file system names the same registered project)."""
    from ..memory.store import _binding_root_text

    return Path(_binding_root_text(root)) if root.is_dir() else root


def _literal_id(value: Any) -> bool:
    """72-T04 G4: a reviewed artifact ID is a non-empty string with no control,
    format or lone-surrogate character."""
    return (
        isinstance(value, str)
        and bool(value)
        and not any(unicodedata.category(ch) in {"Cc", "Cf", "Cs"} for ch in value)
    )


def _revision_ok(value: Any) -> bool:
    """A reviewed revision: a positive int (never a bool) SQLite can store."""
    return type(value) is int and value >= 1 and sqlite_integer_in_range(value)


def _candidate_refs_ok(refs: Any) -> bool:
    """72-T04 D8: 1-64 reviewed corroborators, each exactly `{id, version,
    source}` with a literal ID, a reviewed revision and a literal source label."""
    from ..memory.authorization import literal_source_is_valid

    return (
        isinstance(refs, list)
        and 1 <= len(refs) <= 64
        and all(
            isinstance(ref, dict)
            and set(ref) == {"id", "version", "source"}
            and _literal_id(ref["id"])
            and _revision_ok(ref["version"])
            and literal_source_is_valid(ref["source"])
            for ref in refs
        )
    )


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
    if operation == "preference":
        keys = {"id_key": "artifact_id", "version_key": "artifact_version"}
        refs: list[_Ref] = []
        for item in data.get("preferences") or []:
            if isinstance(item, dict):
                selected = _ref(item.get("selected"), **keys)
                refs += [selected] if selected is not None else []
                refs += _refs(item.get("applied_refs"), **keys)
                refs += _refs(item.get("advice"), **keys)
        return refs
    return []


def _read_refs(operation: str, result: ToolResult) -> list[_Ref]:
    if result.get("status") not in ("ok", "warn"):
        return []
    raw = result.get("raw")
    if isinstance(raw, dict) and raw.get("schema_version") == 2:
        return _refs(raw.get("items"))
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


# --- 72-T06: schema_version 2 helpers -----------------------------------------------


def _storage_root(access: MemoryAccess) -> Path:
    """D25 (72-T05 `MemoryAccess.storage_root`): the store an access reads and
    writes -- the project store, or the user overlay store."""
    root = getattr(access, "storage_root", None)
    return Path(root) if root is not None else access.project_root


def _v2_denial(owner: OwnerScope | None, reason: str) -> tuple[str, dict[str, Any]]:
    """§3.3: a resolve or D1 denial reason as a v2 code and `data`."""
    if owner is None and reason == "owner_required":
        return "E_INPUT", {"field": "owner_scope", "reason": reason}
    if owner is not None and reason == "owner_not_granted":
        return "E_OWNER", {"reason": reason}
    if reason == "source_not_granted":
        return "E_SCOPE", {"reason": reason}
    return "E_PERMISSION", {"reason": reason}


def _non_v2_rejection(operation: str) -> dict[str, Any]:
    """`schema_version` 2 sent to an operation that has no v2 form."""
    msg = "schema_version 2 applies only to the v2 memory operations"
    details: list[dict[str, Any]] = [
        {"loc": ["request", "schema_version"], "type": "extra_forbidden", "msg": msg}
    ]
    message = f"invalid request: request.schema_version: {msg}"
    return _v2_raw(operation, "E_INPUT", data={"message": message, "details": details})


def _v2_failure(exc: BaseException) -> tuple[str, dict[str, Any]] | None:
    """§3.3: an exception from access, a store or a reader as a v2 code and `data`
    (`None`: not a mapped failure)."""
    from ..memory.authorization import MemoryPolicyError

    if isinstance(exc, MemoryPolicyError):
        data: dict[str, Any] = {"message": str(exc), "reason": exc.reason}
        if exc.reason == "representation_unavailable":
            data["alternatives"] = ["base64"]
        return exc.code, data
    if isinstance(exc, (MemoryAccessChanged, MemoryWriteDenied)):
        return exc.code, {"reason": exc.reason, "message": str(exc)}
    if isinstance(exc, MemoryMigrationRequiredError):
        data = {"message": str(exc)}
        reason = getattr(exc, "reason", None)
        refs = getattr(exc, "refs", ())
        if reason:
            data["reason"] = reason
        if refs:
            data["refs"] = [dict(ref) for ref in refs]
        return "E_MIGRATION", data
    if isinstance(exc, MemoryStoreUnreadableError):
        return exc.code, {"message": str(exc)}
    for kind, code in (
        (OwnerScopeError, "E_OWNER"),
        (MemoryScopeError, "E_SCOPE"),
        (VersionConflictError, "E_VERSION"),
        (KeyError, "E_NOT_VISIBLE"),
    ):
        if isinstance(exc, kind):
            return code, {"message": str(exc)}
    return None


def _v2_measure(raw: dict[str, Any], encoding: str) -> tuple[int, int]:
    """`(bytes, tokens)` of one raw as compact JSON."""
    text = json.dumps(raw, ensure_ascii=False, separators=(",", ":"))
    return len(text.encode("utf-8", "surrogatepass")), _count_tokens(text, encoding)


@functools.lru_cache(maxsize=64)
def _v2_overhead(operation: str, encoding: str) -> tuple[int, int]:
    """What the v2 envelope adds to a retrieval page of the same items."""
    empty = _measure_page([], None, True, encoding)
    raw = _v2_raw(
        operation,
        "OK",
        complete=True,
        data={"tokens": empty[1], "bytes": empty[0], "encoding": encoding},
    )
    size = _v2_measure(raw, encoding)
    return max(0, size[0] - empty[0]), max(0, size[1] - empty[1])


@functools.lru_cache(maxsize=64)
def _v2_budget_floor(operation: str, encoding: str) -> tuple[int, int]:
    """The smallest caps admitted: the complete canonical v2 `E_BUDGET` raw (with
    its `required` sizes) and the retrieval page's own floor plus the envelope."""
    need = (0, 0)
    for _ in range(8):
        size = _v2_measure(
            _v2_raw(
                operation,
                "E_BUDGET",
                data={"required": {"max_bytes": need[0], "max_tokens": need[1]}},
            ),
            encoding,
        )
        if size[0] <= need[0] and size[1] <= need[1]:
            break
        need = (max(need[0], size[0]), max(need[1], size[1]))
    overhead = _v2_overhead(operation, encoding)
    page = recall_admission(limit=1, max_bytes=1, max_tokens=1, encoding=encoding)
    required = (page or {}).get("required") or {"max_bytes": 0, "max_tokens": 0}
    return (
        max(need[0], int(required["max_bytes"]) + overhead[0]),
        max(need[1], int(required["max_tokens"]) + overhead[1]),
    )


def _v2_request_digest(operation: str, access: MemoryAccess, req: Any) -> str:
    """D29: the reviewed request (receipt ids excluded) bound to its store."""
    body = {
        "operation": operation,
        "root": str(_storage_root(access)),
        "request": req.model_dump(mode="json", exclude={"invocation_id", "effect_id"}),
    }
    # ASCII escapes: content may legally hold a lone surrogate.
    text = json.dumps(body, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(text.encode("ascii")).hexdigest()


def _v2_task_binding(
    access: MemoryAccess, task_id: str | None
) -> tuple[str, str, str] | None:
    """72-T06 D31: the `(project_id, worktree_id, task_id)` a v2 write or edit stamps on
    the version it commits, or `None` outside a task context (the new version then
    copies the stored row's binding)."""
    ids = (access.project_id, access.worktree_id, task_id)
    if access.kind != "policy" or not all(isinstance(i, str) and i for i in ids):
        return None
    return cast(tuple[str, str, str], ids)


def _v2_binding(access: MemoryAccess, sources: set[str]) -> dict[str, Any]:
    owner = access.owner_scope
    return {
        "project_id": access.project_id,
        "worktree_id": access.worktree_id,
        "owner_scope": owner.as_dict() if owner is not None else None,
        "sources": sorted(sources),
    }


def _jsonable(value: Any) -> Any:
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        value = dataclasses.asdict(value)
    return json.loads(json.dumps(value, default=str))


def _v2_record(binding: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
    """The v2 receipt payload: binding, result refs (write order) and result."""
    return cast(
        dict[str, Any],
        _jsonable(
            {
                "binding": binding,
                "result_refs": list(payload.get("result_refs") or ()),
                "result": payload.get("result") or {},
            }
        ),
    )


def _v2_mutation_raw(
    operation: str, record: dict[str, Any], invocation_id: str, effect_id: str
) -> dict[str, Any]:
    """One pure function for the first response and every replay of an effect."""
    refs = [ref for ref in record.get("result_refs") or () if isinstance(ref, dict)]
    items = [
        {
            "reference": {
                "artifact_id": ref.get("artifact_id"),
                "artifact_version": ref.get("artifact_version"),
            }
        }
        for ref in refs
    ]
    data = {
        "receipt": {
            "invocation_id": invocation_id,
            "effect_id": effect_id,
            "operation_id": v2_operation_id(invocation_id, effect_id),
        },
        "result": record.get("result") or {},
    }
    return _v2_raw(operation, "OK", items=items, complete=True, data=data)


def _ref_visible(
    store: TypedArtifactStore, access: MemoryAccess, ref: Any, *, deleted: bool
) -> bool:
    """A recorded result ref the access may still see: its current row, or (only a
    reviewed delete's tombstones) the recorded version's source."""
    from ..memory.authorization import source_granted

    if not isinstance(ref, dict) or not isinstance(ref.get("artifact_id"), str):
        return False
    current = store.get_current_row(ref["artifact_id"])
    if current is not None:
        return _access_allows(store, current, access, "inspect")
    if not deleted:
        return False
    with store._connect() as conn:
        row = conn.execute(
            "SELECT source FROM memory_artifact_versions "
            "WHERE artifact_id = ? AND artifact_version = ?",
            (ref["artifact_id"], ref.get("artifact_version")),
        ).fetchone()
    return row is not None and source_granted(row["source"], access.sources)


_Bucket = dict[tuple[str, int], dict[str, Any]]


def _bucket_add(bucket: _Bucket, decision: Any, via: tuple[str, str]) -> None:
    reference = v2_reference(decision)
    key = (str(reference["artifact_id"]), int(reference["artifact_version"]))
    entry = bucket.setdefault(key, {"reference": reference, "via": set()})
    entry["via"].add(via)


def _bucket_list(bucket: _Bucket) -> list[dict[str, Any]]:
    """Sorted by `(artifact_id, artifact_version)`, deduplicated, `via` merged."""
    return [
        {
            "reference": entry["reference"],
            "via": [
                {"kind": kind, "direction": direction}
                for kind, direction in sorted(entry["via"])
            ],
        }
        for _key, entry in sorted(bucket.items())
    ]


def _explain_buckets(
    view: TypedArtifactStore,
    access: MemoryAccess,
    mode: Literal["inspect", "historical"],
    targets: list[tuple[sqlite3.Row, Any]],
    *,
    memo: SourceValidationMemo,
) -> dict[str, _Bucket]:
    """D38 one-hop buckets for every target. A neighbor counts only when its
    current row is visible under the same access and mode."""
    buckets: dict[str, _Bucket] = {
        name: {} for name in ("supporting", "contrary", "attempted", "affected")
    }
    root = view.project_root

    def decide(row: sqlite3.Row | None) -> Any:
        if row is None:
            return None
        decision = evaluate_artifact_visibility(
            view, row, access=access, mode=mode, memo=memo
        )
        return decision if decision.visible else None

    with view._connect() as conn:
        for target, _decision in targets:
            target_id = target["id"]
            edges = conn.execute(
                "SELECT source_id, target_id, kind FROM memory_relations "
                "WHERE source_id = ? OR target_id = ? ORDER BY sequence",
                (target_id, target_id),
            ).fetchall()
            for edge in edges:
                outgoing = edge["source_id"] == target_id
                other = edge["target_id"] if outgoing else edge["source_id"]
                if other == target_id:
                    continue
                neighbor = view.get_current_row(other)
                decision = decide(neighbor)
                if neighbor is None or decision is None:
                    continue
                kind = str(edge["kind"])
                via = (kind, "outgoing" if outgoing else "incoming")
                _bucket_add(buckets["affected"], decision, via)
                if outgoing and kind in _SUPPORTING_KINDS:
                    _bucket_add(buckets["supporting"], decision, via)
                if kind == "contradicts" or (kind == "supersedes" and not outgoing):
                    _bucket_add(buckets["contrary"], decision, via)
                if neighbor["subject"] in _ATTEMPT_SUBJECTS:
                    _bucket_add(buckets["attempted"], decision, via)
            if target["symbol_ref"] is not None:
                owner = owner_scope_for_row(target, root)
                for other_row in conn.execute(
                    "SELECT * FROM memory_artifacts "
                    "WHERE subject = ? AND symbol_ref = ? AND id != ?",
                    (target["subject"], target["symbol_ref"], target_id),
                ).fetchall():
                    if owner_scope_for_row(other_row, root) != owner:
                        continue
                    decision = decide(other_row)
                    if decision is None:
                        continue
                    try:
                        verdict = evaluate_conflict(
                            _row_to_artifact(other_row), _row_to_artifact(target)
                        )
                    except (TypeError, ValueError):
                        continue
                    if verdict == "delete":
                        _bucket_add(buckets["contrary"], decision, ("conflict", "none"))
            try:
                summaries = conn.execute(
                    "SELECT * FROM memory_artifacts WHERE json_valid(content) "
                    "AND json_extract(content, '$.kind') = "
                    "'consolidated_episode_summary'"
                ).fetchall()
            except sqlite3.OperationalError:
                summaries = []
            for summary in summaries:
                try:
                    members = json.loads(summary["content"]).get("member_versions")
                except (TypeError, ValueError, AttributeError):
                    continue
                if isinstance(members, dict) and target_id in members:
                    decision = decide(summary)
                    if decision is not None:
                        _bucket_add(
                            buckets["affected"], decision, ("summarizes", "incoming")
                        )
    return buckets


def _reserved_receipt_field(
    operation: str,
    request: dict[str, Any] | None,
    receipt_operation_ids: dict[str, str] | None,
) -> str | None:
    """D29: a legacy receipt id in the reserved `v2:` namespace (its field name)."""

    def reserved(value: Any) -> bool:
        return isinstance(value, str) and value.startswith("v2:")

    if (
        operation == "promote"
        and isinstance(receipt_operation_ids, dict)
        and any(reserved(v) for v in receipt_operation_ids.values())
    ):
        return "receipt_operation_ids"
    if operation in ("delete", "edit", "archive") and isinstance(request, dict):
        if reserved(request.get("receipt_operation_id")):
            return "receipt_operation_id"
        many = request.get("receipt_operation_ids")
        if isinstance(many, dict) and any(reserved(v) for v in many.values()):
            return "receipt_operation_ids"
    return None


def _bridge_filter(value: Any, granted: frozenset[str]) -> Any:
    """D22: drop every artifact reference outside the session's selected ids."""
    if isinstance(value, dict):
        return {key: _bridge_filter(item, granted) for key, item in value.items()}
    if isinstance(value, list):
        kept = []
        for item in value:
            if isinstance(item, dict):
                ident = item.get("id", item.get("artifact_id"))
                if isinstance(ident, str) and ident not in granted:
                    continue
            kept.append(_bridge_filter(item, granted))
        return kept
    return value


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
