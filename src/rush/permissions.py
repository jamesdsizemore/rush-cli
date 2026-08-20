"""Execution permissions and evidence metadata model.

Architecture Phase 07.0 foundation.
Rush defaults to bounded, transparent, denied-by-default effects.
A user may explicitly authorize network, download, cache write, build,
slow execution, artifact writing, or browser runtime for a particular
CLI or MCP invocation.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Literal

ExecutionMode = Literal["executed", "imported", "artifact"]

PERMISSION_FLAG_MAP: dict[str, str] = {
    "network": "--allow-network",
    "download": "--allow-download",
    "cache_write": "--allow-cache-write",
    "build": "--allow-build",
    "slow": "--allow-slow",
    "artifact_write": "--allow-artifact-write",
    "browser": "--allow-browser",
}


@dataclass(frozen=True)
class ExecutionPermissions:
    """Immutable per-invocation permission grants. Denied by default."""

    network: bool = False
    download: bool = False
    cache_write: bool = False
    build: bool = False
    slow: bool = False
    artifact_write: bool = False
    browser: bool = False

    def to_dict(self) -> dict[str, bool]:
        return asdict(self)


def check_permissions(
    required: ExecutionPermissions | None,
    granted: ExecutionPermissions | None,
) -> tuple[bool, list[str]]:
    """Check if all required permissions are granted.

    Returns (is_satisfied, list_of_missing_cli_flags).
    """
    if required is None:
        return True, []
    if granted is None:
        granted = ExecutionPermissions()

    missing: list[str] = []
    for field_name, flag in PERMISSION_FLAG_MAP.items():
        if getattr(required, field_name) and not getattr(granted, field_name):
            missing.append(flag)

    return len(missing) == 0, missing


def build_execution_metadata(
    mode: ExecutionMode,
    *,
    requested: ExecutionPermissions | None = None,
    granted: ExecutionPermissions | None = None,
    producer: str | None = None,
    producer_version: str | None = None,
    declared_artifact: str | None = None,
    report_path: str | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build canonical execution metadata for ToolResult['metadata']['execution']."""
    req_dict = (requested or ExecutionPermissions()).to_dict()
    grant_dict = (granted or ExecutionPermissions()).to_dict()

    metadata: dict[str, Any] = {
        "mode": mode,
        "requested_permissions": req_dict,
        "granted_permissions": grant_dict,
    }
    if producer is not None:
        metadata["producer"] = producer
    if producer_version is not None:
        metadata["producer_version"] = producer_version
    if declared_artifact is not None:
        metadata["declared_artifact"] = declared_artifact
    if report_path is not None:
        metadata["report_path"] = report_path
    if extra:
        metadata.update(extra)

    return metadata
