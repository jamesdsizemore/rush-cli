"""Invocation context resolver for CLI and MCP transports.

Enforces scope boundaries, input parameter normalization, frozen config immutability,
and stable SHA-256 digest computations across dual transports.
"""

from __future__ import annotations

import copy
import hashlib
import json
import os
import sys
from pathlib import Path
from typing import Any, Literal

from rush import __version__
from rush.permissions import ExecutionPermissions

from .models import (
    CachePolicy,
    InvocationContext,
    OperationKind,
    PhysicalTarget,
)
from .targets import build_physical_targets

RESERVED_REQUEST_KEYS: frozenset[str] = frozenset(
    {
        "operation_id",
        "tool",
        "command",
        "operation_kind",
        "path",
        "files",
        "paths",
        "targets",
        "config",
        "permissions",
        "workspace_root",
        "request_id",
        "cache_policy",
        "declared_ignored_inputs",
        "artifact_build_identity",
        "tool_revision",
        "normalizer_revision",
        "args",
        "ordered_args",
        "typed_args",
    }
)


def _compute_config_digest(config: dict[str, Any]) -> str:
    """Compute deterministic SHA-256 digest of config dictionary."""
    serialized = json.dumps(config, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _compute_environment_digest() -> str:
    """Compute deterministic SHA-256 digest of runtime environment."""
    env_payload = {
        "python_version": sys.version_info[:3],
        "platform": sys.platform,
        "rush_env": [
            (k, os.environ[k]) for k in sorted(os.environ) if k.startswith("RUSH_")
        ],
    }
    serialized = json.dumps(
        env_payload, sort_keys=True, separators=(",", ":"), default=str
    )
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _normalize_permissions(
    permissions: list[str] | tuple[str, ...] | ExecutionPermissions | None,
    request: dict[str, Any],
) -> tuple[str, ...]:
    """Extract and sort granted permissions snapshot."""
    granted: set[str] = set()

    if isinstance(permissions, ExecutionPermissions):
        for perm_name, is_granted in permissions.to_dict().items():
            if is_granted:
                granted.add(perm_name)
    elif permissions is not None:
        granted.update(str(p) for p in permissions)
    elif "permissions" in request:
        req_perms = request["permissions"]
        if isinstance(req_perms, ExecutionPermissions):
            for perm_name, is_granted in req_perms.to_dict().items():
                if is_granted:
                    granted.add(perm_name)
        elif isinstance(req_perms, (list, tuple, set)):
            granted.update(str(p) for p in req_perms)

    # Permission flags in request kwargs
    for perm_name in (
        "network",
        "download",
        "cache_write",
        "build",
        "slow",
        "artifact_write",
        "browser",
    ):
        if request.get(f"allow_{perm_name}") or request.get(
            f"--allow-{perm_name.replace('_', '-')}"
        ):
            granted.add(perm_name)

    return tuple(sorted(granted))


def _resolve_targets(
    request: dict[str, Any], workspace_root: Path
) -> tuple[PhysicalTarget, ...]:
    """Resolve and normalize physical targets within workspace root boundary."""
    if "targets" in request and isinstance(request["targets"], (list, tuple)):
        return build_physical_targets(
            workspace_root=workspace_root,
            raw_targets=request["targets"],
            provenance=request.get("provenance", "explicit"),
            capability=request.get("capability", "read"),
            declared_inputs=request.get("declared_inputs"),
        )

    raw_paths: list[str | Path] = []
    if request.get("path"):
        raw_paths.append(request["path"])
    if "files" in request and isinstance(request["files"], (list, tuple)):
        raw_paths.extend(request["files"])
    if "paths" in request and isinstance(request["paths"], (list, tuple)):
        raw_paths.extend(request["paths"])

    return build_physical_targets(
        workspace_root=workspace_root,
        raw_targets=raw_paths,
        provenance=request.get("provenance", "explicit"),
        capability=request.get("capability", "read"),
        declared_inputs=request.get("declared_inputs"),
    )


def _is_typed_argument_name(name: str, request: dict[str, Any]) -> bool:
    """Match canonical request argument namespace for persisted records."""
    return (
        name not in RESERVED_REQUEST_KEYS
        and not name.startswith("allow_")
        and not (
            name == "operation"
            and not request.get("operation_id")
            and not request.get("tool")
        )
    )


def _typed_arguments(request: dict[str, Any]) -> tuple[tuple[str, Any], ...]:
    """Retain transport-native argument values, including explicit null."""
    return tuple(
        (key, copy.deepcopy(request[key]))
        for key in sorted(request)
        if _is_typed_argument_name(key, request)
    )


def _persisted_typed_arguments(
    request: dict[str, Any],
) -> tuple[tuple[str, Any], ...] | None:
    """Restore typed arguments from a persisted invocation record."""
    raw_args = request.get("typed_args")
    if raw_args is None:
        return None
    if not isinstance(raw_args, (list, tuple)):
        raise TypeError("typed_args must be a sequence of name/value pairs")
    try:
        typed_args = tuple((name, copy.deepcopy(value)) for name, value in raw_args)
    except (TypeError, ValueError) as exc:
        raise ValueError("typed_args must be a sequence of name/value pairs") from exc
    if any(
        not isinstance(name, str) or not _is_typed_argument_name(name, request)
        for name, _ in typed_args
    ):
        raise ValueError("typed_args names must be canonical request arguments")
    return typed_args


def _ordered_args_from_typed(
    typed_args: tuple[tuple[str, Any], ...],
) -> tuple[str, ...]:
    """Create a lossless cache identity for new transport-native arguments."""
    return tuple(
        f"--{name}={json.dumps(value, default=str, sort_keys=True, separators=(',', ':'))}"
        for name, value in typed_args
    )


def resolve_invocation(
    request: dict[str, Any] | Any,
    transport: Literal["cli", "mcp"],
    workspace_root: Path | None = None,
    config: dict[str, Any] | None = None,
    permissions: list[str] | tuple[str, ...] | ExecutionPermissions | None = None,
) -> InvocationContext:
    """Resolve an invocation request into a canonical, immutable InvocationContext.

    Ensures zero mutable config leaks, computes stable SHA-256 digests,
    and enforces workspace boundary containment across CLI and MCP transports.
    """
    # Defensive deepcopy of request to ensure caller mutation has zero effect
    if isinstance(request, dict):
        req: dict[str, Any] = copy.deepcopy(request)
    else:
        req = copy.deepcopy(getattr(request, "__dict__", {}))

    # Resolve workspace root
    if workspace_root is not None:
        root = Path(workspace_root).resolve()
    elif req.get("workspace_root"):
        root = Path(req["workspace_root"]).resolve()
    else:
        root = Path.cwd().resolve()

    # Resolve and deepcopy declared configuration
    if config is not None:
        cfg: dict[str, Any] = copy.deepcopy(config)
    elif "config" in req and isinstance(req["config"], dict):
        cfg = copy.deepcopy(req["config"])
    else:
        cfg = {}

    config_digest = _compute_config_digest(cfg)
    env_digest = _compute_environment_digest()
    perms_tuple = _normalize_permissions(permissions, req)
    targets_tuple = _resolve_targets(req, root)

    # Operation identification
    op_id = str(
        req.get("operation_id")
        or req.get("tool")
        or req.get("operation")
        or req.get("command")
        or ""
    )

    op_kind: OperationKind = req.get("operation_kind") or "tool"
    if op_kind not in ("tool", "admin", "service"):
        op_kind = "tool"

    # Argument normalization
    persisted_typed_args = (
        _persisted_typed_arguments(req) if "typed_args" in req else None
    )
    legacy_ordered_args = persisted_typed_args is None and (
        ("ordered_args" in req and isinstance(req["ordered_args"], (list, tuple)))
        or ("args" in req and isinstance(req["args"], (list, tuple)))
    )
    if persisted_typed_args is not None:
        ordered_args = _ordered_args_from_typed(persisted_typed_args)
    elif "ordered_args" in req and isinstance(req["ordered_args"], (list, tuple)):
        ordered_args = tuple(str(a) for a in req["ordered_args"])
    elif "args" in req and isinstance(req["args"], (list, tuple)):
        ordered_args = tuple(str(a) for a in req["args"])
    else:
        typed_source = (
            persisted_typed_args
            if persisted_typed_args is not None
            else _typed_arguments(req)
        )
        ordered_args = _ordered_args_from_typed(typed_source)
    typed_args = (
        persisted_typed_args
        if "typed_args" in req
        else None
        if legacy_ordered_args
        else _typed_arguments(req)
    )

    declared_ignored: tuple[str, ...] = tuple(
        str(i) for i in req.get("declared_ignored_inputs", ())
    )

    cache_policy: CachePolicy = "eligible"
    if req.get("cache_policy") in ("eligible", "bypass"):
        cache_policy = req["cache_policy"]
    elif req.get("no_cache") or req.get("bypass_cache"):
        cache_policy = "bypass"

    build_id = str(req.get("artifact_build_identity") or f"rush@{__version__}")
    tool_rev = str(req.get("tool_revision") or "1.0.0")
    normalizer_rev = str(req.get("normalizer_revision") or "1.0.0")
    req_id = str(req.get("request_id") or "")

    return InvocationContext(
        workspace_root=root,
        transport=transport,
        operation_id=op_id,
        operation_kind=op_kind,
        targets=targets_tuple,
        effective_config_digest=config_digest,
        permissions=perms_tuple,
        ordered_args=ordered_args,
        declared_ignored_inputs=declared_ignored,
        cache_policy=cache_policy,
        artifact_build_identity=build_id,
        tool_revision=tool_rev,
        normalizer_revision=normalizer_rev,
        environment_digest=env_digest,
        request_id=req_id,
        typed_args=typed_args,
    )


__all__ = ["resolve_invocation"]
