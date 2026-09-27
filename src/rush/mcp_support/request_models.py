"""Phase 70 T6: strict request models for `rush_project`, `rush_scan`, `rush_memory`.

One set of Pydantic models per tool drives both the published MCP `inputSchema`
(`published_schema`) and the validation every `tools/call` passes before dispatch
(`validate_and_normalize`). Every model is `extra="forbid"` and strict: no bool-as-int,
no string booleans, no float versions (X3: `schema_version` is `StrictInt` bounded to 1,
never `Literal[1]`, which accepts `True`/`1.0`).

Published schemas stay a top-level `{"type": "object"}` with no top-level combinator
(X2): project/scan publish the legacy `request` envelope (a nested `oneOf`) next to the
flattened named fields; memory publishes its flat arguments plus typed per-operation
fields. Conditional requirements live in the nested `request` schema and in each named
field's description. The models are validation only: grants stay runtime authority.
"""

from __future__ import annotations

import copy
import functools
import inspect
import json
import operator
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import Annotated, Any, Literal, get_args

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Discriminator,
    Field,
    StrictBool,
    StrictInt,
    StrictStr,
    Tag,
    TypeAdapter,
    ValidationError,
    create_model,
    model_validator,
)
from pydantic.json_schema import models_json_schema

from rush.delivery import compact
from rush.mcp_support.tool_registry import _PROJECT_DESCRIPTION
from rush.safety.redactor import sanitize_value

# Via `rush.tools.memory` (not `rush.memory.*` directly): importing
# `rush.memory.maintenance` first is a circular import through `rush.tools`.
from rush.tools.memory import MaintenanceTask, MemorySubject, MemoryTool, SourceKind

REQUEST_MODEL_TOOLS = frozenset({"rush_project", "rush_scan", "rush_memory"})

_REQUIRED: Any = ...
_OPTIONAL: Any = None
_STRICT = ConfigDict(extra="forbid", strict=True)

SchemaVersion = Annotated[StrictInt, Field(ge=1, le=1)]
NonEmptyStr = Annotated[StrictStr, Field(min_length=1)]
NonNegativeInt = Annotated[StrictInt, Field(ge=0)]
StrList = list[StrictStr]
AnyDict = dict[str, Any]
AnyList = list[Any]
# `ProjectTool._require_valid_uuid`: a version-4 UUID (RFC 4122 variant) string.
UUID4Str = Annotated[
    StrictStr,
    Field(
        pattern=r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-4[0-9a-fA-F]{3}-[89abAB][0-9a-fA-F]{3}"
        r"-[0-9a-fA-F]{12}$"
    ),
]
PathStr = Annotated[StrictStr, Field(json_schema_extra={"format": "path"})]


def _union(members: Iterable[Any]) -> Any:
    """`A | B | ...` over a runtime-built member list."""
    return functools.reduce(operator.or_, members)


def _bounded(minimum: int, maximum: int) -> Any:
    return Annotated[StrictInt, Field(ge=minimum, le=maximum)]


def _no_path_separators(value: str) -> str:
    # `MemoryTool._run_delete`/`_edit_or_archive`: an ID never carries a path.
    if "/" in value or "\\" in value or ".." in value:
        raise ValueError("must be a non-empty ID with no path separators")
    return value


ArtifactId = Annotated[
    StrictStr, Field(min_length=1), AfterValidator(_no_path_separators)
]

_GRANT_FIELDS = (
    "allow_network",
    "allow_download",
    "allow_cache_write",
    "allow_build",
    "allow_slow",
    "allow_artifact_write",
    "allow_browser",
)
_GRANTS: dict[str, Any] = {name: (StrictBool, _OPTIONAL) for name in _GRANT_FIELDS}


def _drop_default(schema: dict[str, Any]) -> None:
    schema.pop("default", None)


def _model(
    name: str, fields: Mapping[str, Any], defaults: Mapping[str, Any] | None = None
) -> Any:
    """A strict model. An optional field takes its public default from `defaults`;
    one that cannot be null publishes no `default: null` placeholder."""
    built: dict[str, Any] = {}
    for key, (annotation, default) in fields.items():
        if default is _OPTIONAL:
            default = (defaults or {}).get(key)
            if default is None and type(None) not in get_args(annotation):
                default = Field(default=None, json_schema_extra=_drop_default)
        built[key] = (annotation, default)
    return create_model(name, __config__=_STRICT, **built)


# --- rush_project ------------------------------------------------------------
# Fields: `ProjectTool._REQUEST_FIELDS` per operation (select gains its grants).

_ProjectSettings = _model(
    "ProjectSettings",
    {
        "exclude_tools": (StrList, _OPTIONAL),
        "severity": (Literal["info", "warn", "error"], _OPTIONAL),
        "concurrency": (_bounded(1, 8), _OPTIONAL),
        "timeout_seconds": (_bounded(1, 3600), _OPTIONAL),
        "memory_record": (StrictBool, _OPTIONAL),
        "agent_ids": (StrList, _OPTIONAL),
    },
)
_ACTIVE_PROJECT = {
    "project": (StrictStr | None, _OPTIONAL),
    "session_id": (StrictStr | None, _OPTIONAL),
}
PROJECT_FIELDS: dict[str, dict[str, Any]] = {
    "list": {
        "limit": (_bounded(1, 200), _OPTIONAL),
        "cursor": (StrictStr | None, _OPTIONAL),
    },
    "add": {
        "path": (NonEmptyStr, _REQUIRED),
        "name": (StrictStr | None, _OPTIONAL),
        **_GRANTS,
    },
    "show": dict(_ACTIVE_PROJECT),
    "snapshot": dict(_ACTIVE_PROJECT),
    "select": {
        "project": (UUID4Str, _REQUIRED),
        "session_id": (NonEmptyStr, _REQUIRED),
        **_GRANTS,
    },
    "create": {
        "parent": (NonEmptyStr, _REQUIRED),
        "name": (NonEmptyStr, _REQUIRED),
        "git_init": (StrictBool, _OPTIONAL),
        **_GRANTS,
    },
    "relink": {
        "project": (UUID4Str, _REQUIRED),
        "path": (NonEmptyStr, _REQUIRED),
        "expected_revision": (NonNegativeInt, _REQUIRED),
        **_GRANTS,
    },
    "configure": {
        "project": (UUID4Str, _REQUIRED),
        "settings": (_ProjectSettings | None, _OPTIONAL),
        "expected_revision": (NonNegativeInt, _OPTIONAL),
        "apply": (StrictBool, _OPTIONAL),
        "plan_id": (StrictStr, _OPTIONAL),
        **_GRANTS,
    },
    "artifacts": {
        **_ACTIVE_PROJECT,
        "categories": (StrList, _OPTIONAL),
        "limit": (_bounded(1, 1000), _OPTIONAL),
        "offset": (NonNegativeInt, _OPTIONAL),
    },
}

# --- rush_scan ---------------------------------------------------------------
# Fields: `ScanTool._REQUEST_FIELDS` plus the direct cancel/resume operations
# (`mcp._scan_direct_allowed_fields`). `full`/`install`/`after_sequence` are
# accepted-but-ignored compatibility fields (no effect, disclosed in metadata).

SCAN_COMPATIBILITY_FIELDS = ("full", "install", "after_sequence")
_RUN_REF = {"project": (NonEmptyStr, _REQUIRED), "run_id": (NonEmptyStr, _REQUIRED)}
SCAN_FIELDS: dict[str, dict[str, Any]] = {
    "plan": {
        "project": (NonEmptyStr, _REQUIRED),
        "exclude": (StrList, _OPTIONAL),
        "targets": (dict[StrictStr, AnyDict], _OPTIONAL),
        "severity": (Literal["info", "warn", "error"], _OPTIONAL),
        "concurrency": (_bounded(1, 8), _OPTIONAL),
        "timeout_seconds": (_bounded(1, 3600), _OPTIONAL),
        "full": (StrictBool, _OPTIONAL),
    },
    "run": {
        "project": (NonEmptyStr, _REQUIRED),
        "plan_id": (NonEmptyStr, _REQUIRED),
        "install": (StrictBool, _OPTIONAL),
        **_GRANTS,
    },
    "status": {
        **_RUN_REF,
        "limit": (_bounded(1, 200), _OPTIONAL),
        "cursor": (StrictStr | None, _OPTIONAL),
        "after_sequence": (NonNegativeInt, _OPTIONAL),
    },
    "rescan": {**_RUN_REF, **_GRANTS},
    "cancel": dict(_RUN_REF),
    "resume": {**_RUN_REF, **_GRANTS},
}

# --- rush_memory nested `request` models ---------------------------------------
# Key sets equal `rush.tools.memory._*_REQUEST_KEYS`; required keys and types mirror
# each handler's own `E_INPUT` checks (element types stay open where the handler
# checks only the container).


class MemoryOwnerScope(BaseModel):
    """`OwnerScope.from_value`: exactly `kind` and a non-blank `id`."""

    model_config = _STRICT

    kind: Literal["user", "project", "session", "agent"]
    id: Annotated[StrictStr, Field(pattern=r"\S")]


class MemoryCheckRef(BaseModel):
    """`_plan_checks`: an object with a non-empty string `id` (other keys kept)."""

    model_config = ConfigDict(extra="allow", strict=True)

    id: NonEmptyStr


class MemorySelectedRef(BaseModel):
    """`_handoff` prepare: an object with a non-empty `id` and an integer `version`."""

    model_config = ConfigDict(extra="allow", strict=True)

    id: NonEmptyStr
    version: StrictInt


_CompactRequest = _model(
    "MemoryCompactRequest",
    {
        "view": (Literal["compact"], _REQUIRED),
        "limit": (StrictInt, _OPTIONAL),
        "max_tokens": (StrictInt, _OPTIONAL),
        "max_bytes": (StrictInt, _OPTIONAL),
        "encoding": (StrictStr, _OPTIONAL),
        "cursor": (StrictStr | None, _OPTIONAL),
        "retrieval": (Literal["lexical", "hybrid"], _OPTIONAL),
        "embedding_endpoint": (StrictStr | None, _OPTIONAL),
        "embedding_model": (StrictStr | None, _OPTIONAL),
        "embedding_model_digest": (StrictStr | None, _OPTIONAL),
        "embedding_chunking_version": (StrictStr | None, _OPTIONAL),
    },
)
_BUDGET = {
    "max_tokens": (StrictInt, _OPTIONAL),
    "max_bytes": (StrictInt, _OPTIONAL),
    "encoding": (StrictStr, _OPTIONAL),
}
_ARTIFACT_VERSION = {"id": (NonEmptyStr, _REQUIRED), "version": (StrictInt, _REQUIRED)}


class MemoryDeleteRequest(BaseModel):
    """`MemoryTool._run_delete`: 1-100 unique IDs, revisions for exactly those IDs."""

    model_config = _STRICT

    artifact_ids: Annotated[list[ArtifactId], Field(min_length=1, max_length=100)]
    expected_revisions: dict[str, StrictInt]
    scope: MemorySubject
    owner_scope: MemoryOwnerScope | None = None
    apply: StrictBool = False
    receipt_operation_id: StrictStr | None = None
    receipt_operation_ids: dict[str, StrictStr] | None = None

    @model_validator(mode="after")
    def _ids_match_revisions(self) -> MemoryDeleteRequest:
        if len(set(self.artifact_ids)) != len(self.artifact_ids):
            raise ValueError("artifact_ids must be unique")
        if set(self.expected_revisions) != set(self.artifact_ids):
            raise ValueError(
                "expected_revisions must map exactly the given artifact_ids"
            )
        return self


_MUTATION = {
    "scope": (MemorySubject, _REQUIRED),
    "id": (ArtifactId, _REQUIRED),
    "expected_version": (StrictInt, _REQUIRED),
    "owner_scope": (MemoryOwnerScope | None, _OPTIONAL),
    "apply": (StrictBool, _OPTIONAL),
    "receipt_operation_id": (StrictStr | None, _OPTIONAL),
}

_INTENT_KEYS = {
    "intent_id": (NonEmptyStr, _REQUIRED),
    "behavior_id": (StrictStr | None, _OPTIONAL),
    "statement_ref": (AnyDict | None, _OPTIONAL),
    "new_statement_ref": (AnyDict | None, _OPTIONAL),
    "new_behavior_id": (StrictStr | None, _OPTIONAL),
    "source_refs": (AnyList | None, _OPTIONAL),
    "check_refs": (AnyList | None, _OPTIONAL),
    "exceptions": (AnyList | None, _OPTIONAL),
    "expected_version": (StrictInt | None, _OPTIONAL),
    "current_revision": (StrictStr | None, _OPTIONAL),
}
_INTENT_REQUIRED: dict[str, dict[str, Any]] = {
    "create": {},
    "check": {},
    "confirm": {"expected_version": (StrictInt, _REQUIRED)},
    "supersede": {
        "expected_version": (StrictInt, _REQUIRED),
        "new_statement_ref": (Annotated[AnyDict, Field(min_length=1)], _REQUIRED),
    },
}
_RECIPE_KEYS = {
    "recipe_id": (NonEmptyStr, _REQUIRED),
    "purpose": (StrictStr | None, _OPTIONAL),
    "helper_ref": (AnyDict | None, _OPTIONAL),
    "required_symbols": (AnyList | None, _OPTIONAL),
    "required_dependencies": (AnyDict | None, _OPTIONAL),
    "required_config_digest": (StrictStr | None, _OPTIONAL),
    "checks": (AnyList | None, _OPTIONAL),
    "exceptions": (AnyList | None, _OPTIONAL),
    "expected_version": (StrictInt | None, _OPTIONAL),
    "current_dependencies": (AnyDict | None, _OPTIONAL),
    "current_config_digest": (StrictStr | None, _OPTIONAL),
    "recipe_version": (StrictInt | None, _OPTIONAL),
    "patch_hash": (StrictStr | None, _OPTIONAL),
    "verifier_receipt_ref": (AnyDict | None, _OPTIONAL),
}
_RECIPE_REQUIRED: dict[str, dict[str, Any]] = {
    "record": {},
    "resolve": {},
    "outcome": {
        "recipe_version": (StrictInt, _REQUIRED),
        "patch_hash": (NonEmptyStr, _REQUIRED),
        "verifier_receipt_ref": (AnyDict, _REQUIRED),
    },
}
_HANDOFF_KEYS = {
    "receiver_namespace": (StrictStr | None, _OPTIONAL),
    "receiver_audience": (StrictStr | None, _OPTIONAL),
    "goal": (StrictStr | None, _OPTIONAL),
    "constraints": (AnyDict | None, _OPTIONAL),
    "unresolved_decisions": (AnyList | None, _OPTIONAL),
    "selected_refs": (AnyList | None, _OPTIONAL),
    "handoff_id": (StrictStr | None, _OPTIONAL),
}
_HANDOFF_REQUIRED: dict[str, dict[str, Any]] = {
    "prepare": {
        "receiver_audience": (NonEmptyStr, _REQUIRED),
        "goal": (NonEmptyStr, _REQUIRED),
        "selected_refs": (
            Annotated[list[MemorySelectedRef], Field(min_length=1)],
            _REQUIRED,
        ),
    },
    "dispatch": {},
    "status": {},
}


def _action_union(
    prefix: str, keys: Mapping[str, Any], required: Mapping[str, Mapping[str, Any]]
) -> Any:
    """A nested `request` discriminated by `action`: every branch accepts the whole
    allowlist (as the handler does); each branch tightens its own required keys."""
    branches = tuple(
        _model(
            f"{prefix}{action.title()}Request",
            {"action": (Literal[action], _REQUIRED), **keys, **extra},
        )
        for action, extra in required.items()
    )
    return Annotated[_union(branches), Field(discriminator="action")]


_REQUEST_MODELS: dict[str, Any] = {
    "expand": _model(
        "MemoryExpandRequest",
        {**_ARTIFACT_VERSION, "offset": (StrictInt, _OPTIONAL), **_BUDGET},
    ),
    "link": _model(
        "MemoryLinkRequest",
        {
            "source_id": (NonEmptyStr, _REQUIRED),
            "source_version": (StrictInt, _REQUIRED),
            "target_id": (NonEmptyStr, _REQUIRED),
            "target_version": (StrictInt, _REQUIRED),
            "kind": (StrictStr, _REQUIRED),
            "origin_ref": (StrictStr | None, _OPTIONAL),
        },
    ),
    "related": _model(
        "MemoryRelatedRequest",
        {
            **_ARTIFACT_VERSION,
            "depth": (StrictInt, _OPTIONAL),
            "max_nodes": (StrictInt, _OPTIONAL),
            **_BUDGET,
        },
    ),
    "consolidate": _model(
        "MemoryConsolidateRequest", {"symptom": (NonEmptyStr, _REQUIRED)}
    ),
    "verify_attempt": _model(
        "MemoryVerifyAttemptRequest",
        {
            "attempt_id": (NonEmptyStr, _REQUIRED),
            "behavior_ids": (Annotated[AnyList, Field(min_length=1)], _REQUIRED),
            "contract": (AnyDict, _REQUIRED),
            "patch": (NonEmptyStr, _REQUIRED),
            "declared_permissions": (StrList, _OPTIONAL),
        },
    ),
    "prepare": _model(
        "MemoryPrepareRequest",
        {
            "task": (NonEmptyStr, _REQUIRED),
            "conditions": (AnyDict, _REQUIRED),
            "behavior_ids": (StrList, _OPTIONAL),
            "query": (StrictStr, _OPTIONAL),
        },
    ),
    "intent": _action_union("MemoryIntent", _INTENT_KEYS, _INTENT_REQUIRED),
    "recipe": _action_union("MemoryRecipe", _RECIPE_KEYS, _RECIPE_REQUIRED),
    "plan_checks": _model(
        "MemoryPlanChecksRequest",
        {
            "changed_targets": (list[MemoryCheckRef], _REQUIRED),
            "required_checks": (
                Annotated[list[MemoryCheckRef], Field(min_length=1)],
                _REQUIRED,
            ),
            "environment": (AnyDict, _OPTIONAL),
        },
    ),
    "last_success_diagnose": _model(
        "MemoryLastSuccessDiagnoseRequest",
        {
            "behavior_id": (NonEmptyStr, _REQUIRED),
            "conditions": (AnyDict, _REQUIRED),
            "historical": (StrictBool, _OPTIONAL),
        },
    ),
    "handoff": _action_union("MemoryHandoff", _HANDOFF_KEYS, _HANDOFF_REQUIRED),
    "receive": _model(
        "MemoryReceiveRequest",
        {
            "session_id": (NonEmptyStr, _REQUIRED),
            "capability": (NonEmptyStr, _REQUIRED),
            "cursor": (StrictStr | None, _OPTIONAL),
            "page_size": (StrictInt, _OPTIONAL),
            "ack": (AnyList | None, _OPTIONAL),
        },
    ),
    "delete": MemoryDeleteRequest,
    "edit": _model("MemoryEditRequest", {**_MUTATION, "content": (AnyDict, _REQUIRED)}),
    "archive": _model(
        "MemoryArchiveRequest", {**_MUTATION, "archived": (StrictBool, _OPTIONAL)}
    ),
}
_REQUEST_MODELS["resume"] = _REQUEST_MODELS["prepare"]
_NESTED_ACTIONS = {
    "intent": frozenset(_INTENT_REQUIRED),
    "recipe": frozenset(_RECIPE_REQUIRED),
    "handoff": frozenset(_HANDOFF_REQUIRED),
}

# --- rush_memory top-level operation fields -------------------------------------
# Common to every operation: `MemoryTool.__call__`'s path, grants, and attribution
# (`project_id` doubles as the T8 declared root). Everything else is consumed only
# by the operations below (`MemoryTool.run`'s dispatch table); any other top-level
# field is rejected for that operation.

_MEMORY_COMMON: dict[str, Any] = {
    "path": (PathStr, _REQUIRED),
    **_GRANTS,
    "invocation_id": (StrictStr | None, _OPTIONAL),
    # T8 5.2: `project_id` is also this call's declared root; keep its description.
    "project_id": (
        StrictStr | None,
        Field(
            default=None,
            description="Also serves as this call's declared root. "
            + _PROJECT_DESCRIPTION,
        ),
    ),
    "run_id": (StrictStr | None, _OPTIONAL),
    "agent_id": (StrictStr | None, _OPTIONAL),
    "session_id": (StrictStr | None, _OPTIONAL),
    # Phase 70 T16 (R16.5/finding 1): the shared result-view parameters. The
    # values pass through unchanged so `rush.delivery.compact` applies the
    # one validation (RESULT_VIEW_INVALID) every transport shares.
    "result_view": (compact.ResultViewParam, None),
    "limit": (compact.LimitParam, None),
    "max_bytes": (compact.MaxBytesParam, None),
    "no_cache": (StrictBool, False),
}
_ALLOWLIST_REQUIRED = (Annotated[StrList, Field(min_length=1)], _REQUIRED)
_ALLOWLIST_OPTIONAL = (StrList | None, _OPTIONAL)
_QUERY = {
    "subject": (MemorySubject, _REQUIRED),
    "query": (NonEmptyStr, _REQUIRED),
    "session_allowlist": _ALLOWLIST_REQUIRED,
}
_WRITE = {
    "subject": (MemorySubject, _REQUIRED),
    "content": (AnyDict, _REQUIRED),
    "source": (NonEmptyStr, _REQUIRED),
    "symbol_ref": (StrictStr | None, _OPTIONAL),
    "source_kind": (SourceKind, _OPTIONAL),
    "owner_scope": (MemoryOwnerScope | None, _OPTIONAL),
}


def _request_field(operation: str) -> dict[str, Any]:
    return {"request": (_REQUEST_MODELS[operation], _REQUIRED)}


# Model tag -> (operation, fields). `list:compact` is `list` with a compact `request`
# (query optional, `include_archived` not consumed); plain `list` is the `_query` path.
MEMORY_FIELDS: dict[str, tuple[str, dict[str, Any]]] = {
    "ask": ("ask", {**_QUERY, "request": (_CompactRequest | None, _OPTIONAL)}),
    "recall": ("recall", {**_QUERY, "request": (_CompactRequest | None, _OPTIONAL)}),
    "list": ("list", {**_QUERY, "include_archived": (StrictBool, _OPTIONAL)}),
    "list:compact": (
        "list",
        {
            "subject": (MemorySubject, _REQUIRED),
            "query": (StrictStr, _OPTIONAL),
            "session_allowlist": _ALLOWLIST_REQUIRED,
            "request": (_CompactRequest, _REQUIRED),
        },
    ),
    "write": ("write", dict(_WRITE)),
    "promote": (
        "promote",
        {
            **_WRITE,
            "user_stated": (StrictBool, _OPTIONAL),
            "candidate_sources": (StrList | None, _OPTIONAL),
        },
    ),
    "maintain": (
        "maintain",
        {
            "task": (MaintenanceTask, _REQUIRED),
            "owner_scope": (MemoryOwnerScope, _REQUIRED),
            "batch_size": (StrictInt, _OPTIONAL),
        },
    ),
    **{
        op: (op, {**_request_field(op), "session_allowlist": _ALLOWLIST_OPTIONAL})
        for op in ("expand", "related", "consolidate", "prepare", "resume")
    },
    **{
        op: (op, _request_field(op))
        for op in (
            "link",
            "verify_attempt",
            "intent",
            "recipe",
            "plan_checks",
            "last_success_diagnose",
            "handoff",
            "receive",
            "delete",
            "edit",
            "archive",
        )
    },
}


# --- model construction --------------------------------------------------------


def _camel(value: str) -> str:
    return "".join(part.title() for part in value.replace(":", "_").split("_"))


def _operation_model(
    prefix: str,
    operation: str,
    fields: Mapping[str, Any],
    *,
    extra: Mapping[str, Any],
    tag: str | None = None,
    defaults: Mapping[str, Any] | None = None,
) -> Any:
    op_default = "ask" if (prefix == "Memory" and operation == "ask") else _REQUIRED
    return _model(
        f"{prefix}{_camel(tag or operation)}",
        {"operation": (Literal[operation], op_default), **extra, **fields},
        defaults,
    )


def _tagged(operation: str, model: Any) -> Any:
    return Annotated[model, Tag(operation)]


@dataclass(frozen=True)
class _ToolSpec:
    tool: str  # ToolResult `tool` name
    named: dict[str, Any]  # tag -> named-form model
    legacy: dict[str, Any] = field(default_factory=dict)  # tag -> legacy model
    tag_operation: dict[str, str] = field(default_factory=dict)
    named_adapter: Any = None
    legacy_adapter: Any = None


def _envelope_spec(
    tool: str, prefix: str, table: Mapping[str, Mapping[str, Any]]
) -> _ToolSpec:
    named = {
        op: _operation_model(
            prefix, op, fields, extra={"schema_version": (SchemaVersion, _OPTIONAL)}
        )
        for op, fields in table.items()
    }
    legacy = {
        op: _operation_model(
            f"{prefix}Legacy",
            op,
            fields,
            extra={"schema_version": (SchemaVersion, _REQUIRED)},
        )
        for op, fields in table.items()
    }

    def adapter(models: Mapping[str, Any]) -> Any:
        return TypeAdapter(
            Annotated[_union(models.values()), Field(discriminator="operation")]
        )

    return _ToolSpec(
        tool=tool,
        named=named,
        legacy=legacy,
        tag_operation={op: op for op in table},
        named_adapter=adapter(named),
        legacy_adapter=adapter(legacy),
    )


def _memory_tag(value: Any) -> Any:
    if not isinstance(value, dict):
        return None
    operation = value.get("operation", "ask")
    if operation == "list" and value.get("request") is not None:
        return "list:compact"
    return operation


def _memory_spec() -> _ToolSpec:
    # Plan: memory models keep `MemoryTool.__call__`'s public signature defaults.
    defaults = {
        name: parameter.default
        for name, parameter in inspect.signature(MemoryTool.__call__).parameters.items()
        if parameter.default is not inspect.Parameter.empty
    }
    named = {
        tag: _operation_model(
            "Memory", op, fields, extra=_MEMORY_COMMON, tag=tag, defaults=defaults
        )
        for tag, (op, fields) in MEMORY_FIELDS.items()
    }
    union = _union(_tagged(tag, model) for tag, model in named.items())
    return _ToolSpec(
        tool="memory",
        named=named,
        tag_operation={tag: op for tag, (op, _) in MEMORY_FIELDS.items()},
        named_adapter=TypeAdapter(Annotated[union, Discriminator(_memory_tag)]),
    )


_SPECS: dict[str, _ToolSpec] = {
    "rush_project": _envelope_spec("project", "Project", PROJECT_FIELDS),
    "rush_scan": _envelope_spec("scan", "Scan", SCAN_FIELDS),
    "rush_memory": _memory_spec(),
}


def project_model_tags() -> set[str]:
    return set(_SPECS["rush_project"].tag_operation.values())


def scan_model_tags() -> set[str]:
    return set(_SPECS["rush_scan"].tag_operation.values())


def memory_model_tags() -> set[str]:
    return set(_SPECS["rush_memory"].tag_operation.values())


def memory_request_model_keys(operation: str) -> set[str]:
    """The nested `request` key set a memory operation's model accepts."""
    annotation = _REQUEST_MODELS[operation]
    models = (
        get_args(get_args(annotation)[0])
        if operation in _NESTED_ACTIONS
        else (annotation,)
    )
    keys: set[str] = set()
    for model in models:
        keys |= set(model.model_fields)
    return keys


# --- published schema ---------------------------------------------------------


def _strip(node: Any) -> Any:
    """Drop OpenAPI-only `discriminator` keys (plain JSON Schema is published)."""
    if isinstance(node, dict):
        return {
            key: _strip(value) for key, value in node.items() if key != "discriminator"
        }
    if isinstance(node, list):
        return [_strip(item) for item in node]
    return node


def _refs(node: Any) -> set[str]:
    if isinstance(node, dict):
        found = {node["$ref"].rsplit("/", 1)[-1]} if "$ref" in node else set()
        for value in node.values():
            found |= _refs(value)
        return found
    if isinstance(node, list):
        return set().union(*(_refs(item) for item in node)) if node else set()
    return set()


def _prune_defs(schema: dict[str, Any], defs: dict[str, Any]) -> dict[str, Any]:
    keep: set[str] = set()
    pending = _refs(schema["properties"])
    while pending:
        name = pending.pop()
        if name not in keep:
            keep.add(name)
            pending |= _refs(defs[name])
    if keep:
        schema["$defs"] = {name: defs[name] for name in sorted(keep)}
    return schema


def _usage_text(usage: Mapping[str, str], total: int) -> str:
    """`usage`: operation -> required | conditional | optional."""
    groups: dict[str, list[str]] = {}
    for op in sorted(usage):
        groups.setdefault(usage[op], []).append(op)
    if len(usage) == total and len(groups) == 1:
        return f"{next(iter(groups)).capitalize()} for every operation."
    labels = {
        "required": "Required for operation(s)",
        # Only memory `list` has two forms: plain needs `query`, compact `request`.
        "conditional": "Required by one form (plain: query; compact: request) of "
        "operation(s)",
        "optional": "Optional for operation(s)",
    }
    parts = [
        f"{labels[kind]}: {', '.join(groups[kind])}."
        for kind in labels
        if kind in groups
    ]
    if len(usage) < total:
        parts.append("Rejected for every other operation.")
    return " ".join(parts)


def _flatten(
    spec: _ToolSpec, defs: dict[str, Any], *, skip: frozenset[str] = frozenset()
) -> dict[str, Any]:
    """Union of every named branch's properties. A field whose shape differs across
    branches becomes a nested `anyOf` of the distinct shapes."""
    shapes: dict[str, list[Any]] = {}
    # field -> operation -> [branches allowing it, branches requiring it]
    counts: dict[str, dict[str, list[int]]] = {}
    tags_per_op: dict[str, int] = {}
    for tag, model in spec.named.items():
        op = spec.tag_operation[tag]
        tags_per_op[op] = tags_per_op.get(op, 0) + 1
        body = defs[model.__name__]
        for name, prop in body["properties"].items():
            if name in skip:
                continue
            shape = {k: v for k, v in prop.items() if k != "title"}
            bucket = shapes.setdefault(name, [])
            if shape not in bucket:
                bucket.append(shape)
            tally = counts.setdefault(name, {}).setdefault(op, [0, 0])
            tally[0] += 1
            tally[1] += name in body.get("required", [])
    usages: dict[str, dict[str, str]] = {
        name: {
            op: "optional"
            if required == 0
            else ("required" if required == tags_per_op[op] else "conditional")
            for op, (_, required) in per_op.items()
        }
        for name, per_op in counts.items()
    }
    properties: dict[str, Any] = {}
    for name, bucket in shapes.items():
        prop = bucket[0] if len(bucket) == 1 else {"anyOf": bucket}
        usage = _usage_text(usages[name], len(tags_per_op))
        own = prop.get("description")
        prop["description"] = f"{own} {usage}" if own else usage
        if name in SCAN_COMPATIBILITY_FIELDS and spec.tool == "scan":
            prop["deprecated"] = True
            prop["description"] += (
                " Deprecated compatibility field: accepted and ignored (no effect), "
                "disclosed in metadata.compatibility."
            )
        properties[name] = prop
    return properties


@functools.cache
def _published(tool_name: str) -> dict[str, Any]:
    spec = _SPECS[tool_name]
    models = [*spec.named.values(), *spec.legacy.values()]
    _, top = models_json_schema(
        [(model, "validation") for model in models], ref_template="#/$defs/{model}"
    )
    defs = _strip(top["$defs"])
    operations = sorted(set(spec.tag_operation.values()))
    properties = _flatten(spec, defs, skip=frozenset({"operation", "schema_version"}))
    operation: dict[str, Any] = {
        "type": "string",
        "enum": operations,
        "description": "Operation to run; selects which other fields apply.",
    }
    if spec.legacy:
        properties = {
            "request": {
                "description": "Legacy versioned envelope ({schema_version: 1, "
                "operation, ...operation fields}). Send either `request` alone or "
                "the named fields, never both.",
                "oneOf": [
                    {"$ref": f"#/$defs/{model.__name__}"}
                    for model in spec.legacy.values()
                ],
            },
            "operation": operation,
            "schema_version": {
                "type": "integer",
                "minimum": 1,
                "maximum": 1,
                "description": "Envelope version; optional with named fields "
                "(defaults to 1).",
            },
            **properties,
        }
        required: list[str] = []
    else:
        operation["default"] = "ask"
        properties = {"operation": operation, **properties}
        required = ["path"]
    schema = {
        "type": "object",
        "properties": properties,
        "required": required,
        "additionalProperties": False,
    }
    return _prune_defs(schema, defs)


def published_schema(tool_name: str) -> dict[str, Any]:
    """The `inputSchema` `tools/list` publishes for one T6 tool (a fresh copy)."""
    return copy.deepcopy(_published(tool_name))


# --- validation --------------------------------------------------------------


@dataclass(frozen=True)
class ValidationOutcome:
    """`arguments` to dispatch when accepted; otherwise the tool's own rejection
    `result` envelope and its `error` part (project/scan: `raw.error`; memory: the
    MC02 `raw` envelope)."""

    arguments: dict[str, Any] | None = None
    result: dict[str, Any] | None = None
    error: dict[str, Any] | None = None

    @property
    def rejected(self) -> bool:
        return self.result is not None


@functools.cache
def _container_keys(tool_name: str) -> frozenset[str]:
    """Top-level fields whose schema is an object or array (JSON-string decode set)."""
    keys = set()
    for name, prop in _published(tool_name)["properties"].items():
        options = prop.get("anyOf") or prop.get("oneOf") or [prop]
        if any(
            "$ref" in option or option.get("type") in ("object", "array")
            for option in options
        ):
            keys.add(name)
    return frozenset(keys)


def _decode_containers(tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    """FastMCP `pre_parse_json` subset: a top-level string that decodes to an object or
    array for an object/array field is decoded; scalar strings never are."""
    decoded = dict(arguments)
    for key in _container_keys(tool_name) & decoded.keys():
        value = decoded[key]
        if isinstance(value, str):
            try:
                parsed = json.loads(value)
            except ValueError:
                continue
            if isinstance(parsed, (dict, list)):
                decoded[key] = parsed
    return decoded


def _details(spec: _ToolSpec, exc: ValidationError, prefix: list[str]) -> list[Any]:
    details = []
    for error in exc.errors(
        include_url=False, include_context=False, include_input=False
    ):
        loc: list[Any] = list(error["loc"])
        msg = error["msg"]
        actions: frozenset[str] = frozenset()
        if loc and isinstance(loc[0], str) and loc[0] in spec.tag_operation:
            actions = _NESTED_ACTIONS.get(spec.tag_operation[loc.pop(0)], frozenset())
            if len(loc) > 1 and loc[0] == "request" and loc[1] in actions:
                del loc[1]
        if error["type"] in ("union_tag_invalid", "union_tag_not_found"):
            # The discriminator itself is missing or unknown: name the field and
            # the public choices (never the internal `list:compact` tag).
            key = "action" if loc else "operation"
            choices = actions if loc else set(spec.tag_operation.values())
            loc.append(key)
            msg = f"{key} must be one of: {', '.join(sorted(choices))}"
        details.append({"loc": prefix + loc, "type": error["type"], "msg": msg})
    return details


def _message(details: list[Any]) -> str:
    return "invalid request: " + "; ".join(
        f"{'.'.join(map(str, d['loc'])) or '<arguments>'}: {d['msg']}" for d in details
    )


def _reject(spec: _ToolSpec, operation: Any, details: list[Any]) -> ValidationOutcome:
    op = str(operation)
    message = _message(details)
    raw: dict[str, Any]
    if spec.tool == "memory":
        raw = {
            "schema_version": 1,
            "operation": op,
            "code": "E_INPUT",
            "data": {"message": message, "details": details},
        }
        summary = f"memory {op} returned E_INPUT."
        extra: dict[str, Any] = {"metadata": {"operation": op}}
    else:
        raw = {
            "schema_version": 1,
            "operation": op,
            "data": None,
            "error": {
                "code": "INVALID_REQUEST",
                "message": message,
                "retryable": False,
                "details": details,
            },
        }
        summary = f"{spec.tool} {op}: {message}"
        extra = {}
    result = sanitize_value(
        {
            "tool": spec.tool,
            "engine": None,
            "engine_version": None,
            "status": "error",
            "duration_ms": 0,
            "summary": summary,
            "findings": [],
            "raw": raw,
            **extra,
        }
    ).value
    error = result["raw"] if spec.tool == "memory" else result["raw"]["error"]
    return ValidationOutcome(result=result, error=error)


def _compatibility(fields: Mapping[str, Any]) -> dict[str, Any] | None:
    ignored = [name for name in SCAN_COMPATIBILITY_FIELDS if name in fields]
    if not ignored:
        return None
    return {"version": 1, "ignored_fields": ignored, "effect": "none"}


def validate_and_normalize(
    tool_name: str, arguments: dict[str, Any]
) -> ValidationOutcome:
    """Validate one `tools/call` against the tool's models, before any dispatch.

    project/scan: legacy `{"request": {...}}` or named fields (never both) normalize
    to the same versioned envelope; named requests get `schema_version: 1`. memory:
    the flat arguments, validated per operation. Omitted versus explicit null is kept
    (`exclude_unset`).
    """
    spec = _SPECS[tool_name]
    default_op = "ask" if spec.tool == "memory" else None
    if not isinstance(arguments, dict):
        details = [
            {"loc": [], "type": "dict_type", "msg": "arguments must be an object"}
        ]
        return _reject(spec, default_op, details)
    args = _decode_containers(tool_name, arguments)
    prefix: list[str] = []
    adapter = spec.named_adapter
    payload: Any = args
    if spec.legacy and "request" in args:
        mixed = sorted(set(args) - {"request"})
        if mixed:
            details = [
                {
                    "loc": [key],
                    "type": "extra_forbidden",
                    "msg": "named fields cannot be combined with the legacy `request` "
                    "envelope",
                }
                for key in mixed
            ]
            return _reject(spec, args.get("operation"), details)
        prefix, adapter, payload = ["request"], spec.legacy_adapter, args["request"]
    operation = (
        payload.get("operation", default_op)
        if isinstance(payload, dict)
        else default_op
    )
    try:
        model = adapter.validate_python(payload)
    except ValidationError as exc:
        return _reject(spec, operation, _details(spec, exc, prefix))
    fields = model.model_dump(exclude_unset=True)
    if spec.tool == "memory":
        return ValidationOutcome(arguments=fields)
    request = {"schema_version": 1, **fields}
    compatibility = _compatibility(fields) if spec.tool == "scan" else None
    if compatibility is not None:
        request["metadata"] = {"compatibility": compatibility}
    return ValidationOutcome(arguments={"request": request})


__all__ = [
    "REQUEST_MODEL_TOOLS",
    "ValidationOutcome",
    "memory_model_tags",
    "memory_request_model_keys",
    "project_model_tags",
    "published_schema",
    "scan_model_tags",
    "validate_and_normalize",
]
