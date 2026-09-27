"""AgentConnectionTool -- single result-contract entry point over agent connection.

Phase 65 P65-05 (F35). Wraps `rush.integrations.agents` so CLI and (once
`src/rush/mcp.py` registers `rush_agent_connection` in a follow-up packet)
MCP share one list/connect/doctor implementation, mirroring
`rush.tools.project.ProjectTool`'s canonical envelope
(`handle_request` -> `ToolResult.raw={"schema_version":1,"operation":...,
"data":...,"error":...}`, plan §6.1).

`list`/`doctor` are read-only. `connect` mutates a third-party agent's own
config file (or invokes its native registration command) and requires
explicit cache-write + artifact-write permission, matching the write gate
`ProjectTool` uses for `add`/`create`.

Phase 70 T3: `connect` also previews the project instruction block
(`CLAUDE.md`/`AGENTS.md`) and writes it only with separate guidance consent
(`install_guidance=True`, or an interactive `confirm_guidance` prompt);
memory consent, grants and `acknowledge` never imply it. Every file write of
the transaction is journaled and undone on a later failure. `disconnect`
removes only Rush-owned, unchanged components recorded in the ownership
ledger.

MCP registration (`rush_agent_connection` in `src/rush/mcp.py`) is out of
this task's allowed files -- see this packet's own receipt for the exact
disclosed gap; a follow-up task registers it against this same tool.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from time import monotonic
from typing import Any, Literal

from rush.integrations.agents import (
    MCP_PROFILES,
    AgentConnectionError,
    AgentTransactionError,
    GuidanceConsent,
    OwnedResource,
    ProfileConsent,
    agent_readiness,
    connect_agent,
    disconnect_agent,
    discover_agents,
    read_agent_memory_state,
)
from rush.permissions import ExecutionPermissions, check_permissions

from .base import Finding, ToolFn, ToolResult, ToolStatus

AgentAction = Literal["list", "connect", "doctor", "disconnect"]

_CONNECT_PERMISSION = ExecutionPermissions(cache_write=True, artifact_write=True)

_DISCONNECT_FIELDS = frozenset(
    {
        "schema_version",
        "operation",
        "agent_id",
        "project_root",
        "allow_cache_write",
        "allow_artifact_write",
    }
)


class AgentConnectionTool(ToolFn):
    """Discover, connect, disconnect, and diagnose local MCP-capable coding agents."""

    name = "agent_connection"

    @property
    def mcp_description(self) -> str:
        return (
            "Discover/connect/disconnect local coding agents. "
            "action=list|connect|doctor|disconnect. Returns {status, findings[], "
            "summary, raw}. connect/disconnect need cache+artifact write grants."
        )

    def __call__(
        self,
        agent_id: str | None = None,
        action: AgentAction = "list",
        session_id: str | None = None,
        rush_binary: str | None = None,
        consent: bool = False,
        acknowledge: bool = False,
        install_guidance: bool = False,
        allow_cache_write: bool = False,
        allow_artifact_write: bool = False,
    ) -> ToolResult:
        return self.run(
            agent_id,
            action=action,
            session_id=session_id,
            rush_binary=rush_binary,
            consent=consent,
            acknowledge=acknowledge,
            install_guidance=install_guidance,
            permissions=ExecutionPermissions(
                cache_write=allow_cache_write, artifact_write=allow_artifact_write
            ),
        )

    def run(
        self,
        agent_id: str | None,
        *,
        action: AgentAction = "list",
        session_id: str | None = None,
        rush_binary: str | None = None,
        consent: bool = False,
        acknowledge: bool = False,
        install_guidance: bool = False,
        confirm_guidance: GuidanceConsent | None = None,
        project_root: Path | None = None,
        permissions: ExecutionPermissions | None = None,
        home: Path | None = None,
        data_root: Path | None = None,
        resources: Sequence[OwnedResource] = (),
        profile: str | None = None,
        confirm_profile: ProfileConsent = False,
    ) -> ToolResult:
        started = monotonic()
        granted = permissions or ExecutionPermissions()

        if action == "connect":
            allowed, missing = check_permissions(_CONNECT_PERMISSION, granted)
            if not allowed:
                return self._result(
                    started, "skipped", f"agent connect requires {', '.join(missing)}."
                )

        try:
            raw = self._dispatch(
                action,
                agent_id=agent_id,
                session_id=session_id,
                rush_binary=rush_binary,
                consent=consent,
                acknowledge=acknowledge,
                guidance_consent=(
                    True if install_guidance else (confirm_guidance or False)
                ),
                project_root=project_root,
                home=home,
                data_root=data_root,
                resources=resources,
                profile=profile,
                confirm_profile=confirm_profile,
            )
        except AgentTransactionError as exc:
            return self._result(
                started,
                "error",
                f"agent {action}: {exc}",
                raw={"error": str(exc), "recovery_required": exc.recovery},
            )
        except AgentConnectionError as exc:
            return self._result(started, "error", f"agent {action}: {exc}")
        except ValueError as exc:
            return self._result(started, "error", f"agent {action}: {exc}")

        if action == "connect":
            return self._connect_result(started, raw)
        if action == "disconnect":
            status: ToolStatus = "ok" if raw["status"] == "ok" else "warn"
            return self._result(
                started,
                status,
                f"agent disconnect: {raw['status']}; removed "
                f"{len(raw['removed'])}, conflicts {len(raw['conflicts'])}",
                raw=raw,
            )
        return self._result(started, "ok", f"agent {action}: ok", raw=raw)

    def _connect_result(self, started: float, raw: dict[str, Any]) -> ToolResult:
        """T4: a profile migration that wrote nothing is `skipped` (preview
        only, declined, conflict, or a failed native add whose prior entry was
        restored); one needing a manual restore is `error`."""
        migration = raw.get("migration")
        if migration is None:
            guidance_state = raw["guidance"]["state"]
            return self._result(
                started, "ok", f"agent connect: ok; guidance: {guidance_state}", raw=raw
            )
        state = migration["state"]
        if state == "applied":
            return self._result(
                started,
                "ok",
                f"agent connect: ok; profile migration applied "
                f"({migration['profile']}); guidance: {raw['guidance']['state']}",
                raw=raw,
            )
        if state in ("pending", "declined"):
            summary = (
                f"agent connect: profile migration {state}; preview only, nothing "
                "written. Rerun with --yes (MCP: confirm_profile_migration) to apply."
            )
        elif state == "conflict":
            summary = (
                f"agent connect: profile migration conflict: {migration['config_path']} "
                "changed since the preview; nothing written."
            )
        elif state == "failed":
            summary = (
                "agent connect: profile migration failed and the previous entry "
                f"is unchanged: {raw['apply']['error']}"
            )
        else:
            return self._result(
                started,
                "error",
                "agent connect: profile migration failed and restoring the previous "
                f"entry failed too; recovery_required: {raw['apply']['recovery_required']}",
                raw=raw,
            )
        return self._result(started, "skipped", summary, raw=raw)

    def _dispatch(
        self,
        action: AgentAction,
        *,
        agent_id: str | None,
        session_id: str | None,
        rush_binary: str | None,
        consent: bool,
        acknowledge: bool,
        guidance_consent: GuidanceConsent,
        project_root: Path | None,
        home: Path | None,
        data_root: Path | None,
        resources: Sequence[OwnedResource] = (),
        profile: str | None = None,
        confirm_profile: ProfileConsent = False,
    ) -> Any:
        if action == "list":
            return agent_readiness(home=home, rush_binary=rush_binary)

        if action == "connect":
            if not agent_id:
                raise ValueError("connect requires agent_id")
            if not session_id:
                raise ValueError("connect requires session_id")
            return connect_agent(
                agent_id,
                session_id=session_id,
                rush_binary=rush_binary,
                consent=consent,
                acknowledge=acknowledge,
                guidance_consent=guidance_consent,
                project_root=project_root,
                home=home,
                data_root=data_root,
                resources=resources,
                profile=profile,
                profile_consent=confirm_profile,
            )

        if action == "disconnect":
            if not agent_id:
                raise ValueError("disconnect requires agent_id")
            return disconnect_agent(
                agent_id, project_root=project_root, data_root=data_root, home=home
            ).to_dict()

        if action == "doctor":
            statuses = discover_agents(home=home, rush_binary=rush_binary)
            memory_states: dict[str, Any] = {}
            if session_id:
                for status in statuses:
                    memory_states[status.agent_id] = read_agent_memory_state(
                        status.agent_id,
                        session_id,
                        project_root=project_root,
                        data_root=data_root,
                    )
            return {
                "agents": [status.to_dict() for status in statuses],
                "memory": memory_states,
            }

        raise ValueError(f"unknown agent action: {action}")

    def handle_request(self, request: dict[str, Any]) -> ToolResult:
        """Canonical envelope call boundary (plan §6.1), mirroring `ProjectTool`."""
        started = monotonic()
        operation = request.get("operation") if isinstance(request, dict) else None

        try:
            data = self._handle_request_unsafe(request)
        except AgentConnectionError as exc:
            return self._envelope_result(
                started, str(operation), status="error", error=exc
            )
        except _AgentInvalidRequestError as exc:
            return self._envelope_result(
                started, str(operation), status="error", error=exc
            )
        except _ScopeDenied as denied:
            return self._envelope_result(
                started, str(operation), status="skipped", error=denied
            )

        return self._envelope_result(started, str(operation), status="ok", data=data)

    def _handle_request_unsafe(self, request: dict[str, Any]) -> Any:
        if not isinstance(request, dict):
            raise _AgentInvalidRequestError("request must be an object")
        if request.get("schema_version") != 1:
            raise _AgentInvalidRequestError("schema_version must be 1")

        operation = request.get("operation")
        if operation not in ("list", "connect", "doctor", "disconnect"):
            raise _AgentInvalidRequestError(f"unknown operation: {operation!r}")

        if operation == "disconnect":
            return self._handle_disconnect_request(request)

        install_guidance = request.get("install_guidance", False)
        if type(install_guidance) is not bool:
            raise _AgentInvalidRequestError("install_guidance must be a boolean")
        profile, confirm_profile = _profile_fields(request, operation)

        if operation == "connect":
            granted = ExecutionPermissions(
                cache_write=bool(request.get("allow_cache_write", False)),
                artifact_write=bool(request.get("allow_artifact_write", False)),
            )
            allowed, missing = check_permissions(_CONNECT_PERMISSION, granted)
            if not allowed:
                raise _ScopeDenied(f"missing permission(s): {', '.join(missing)}")

        return self._dispatch(
            operation,
            agent_id=request.get("agent_id"),
            session_id=request.get("session_id"),
            rush_binary=request.get("rush_binary"),
            consent=bool(request.get("consent", False)),
            acknowledge=bool(request.get("acknowledge", False)),
            guidance_consent=install_guidance,
            project_root=Path(request["project_root"])
            if request.get("project_root")
            else None,
            home=None,
            data_root=None,
            profile=profile,
            confirm_profile=confirm_profile,
        )

    def _handle_disconnect_request(self, request: dict[str, Any]) -> Any:
        """Strict fields: unknown keys, wrong types and non-bool grants are rejected."""
        unknown = sorted(set(request) - _DISCONNECT_FIELDS)
        if unknown:
            raise _AgentInvalidRequestError(
                f"unknown field(s) for disconnect: {', '.join(unknown)}"
            )
        agent_id = request.get("agent_id")
        if not isinstance(agent_id, str) or not agent_id:
            raise _AgentInvalidRequestError("disconnect requires a string agent_id")
        project_root = request.get("project_root")
        if project_root is not None and (
            not isinstance(project_root, str) or not project_root
        ):
            raise _AgentInvalidRequestError(
                "project_root must be a non-empty string or null"
            )
        grants = {
            key: request.get(key, False)
            for key in ("allow_cache_write", "allow_artifact_write")
        }
        if any(type(value) is not bool for value in grants.values()):
            raise _AgentInvalidRequestError("permission grants must be booleans")
        allowed, missing = check_permissions(
            _CONNECT_PERMISSION,
            ExecutionPermissions(
                cache_write=grants["allow_cache_write"],
                artifact_write=grants["allow_artifact_write"],
            ),
        )
        if not allowed:
            raise _ScopeDenied(f"missing permission(s): {', '.join(missing)}")
        return disconnect_agent(
            agent_id,
            project_root=Path(project_root) if project_root else None,
        ).to_dict()

    def _envelope_result(
        self,
        started: float,
        operation: str,
        *,
        status: ToolStatus,
        data: Any = None,
        error: Exception | None = None,
    ) -> ToolResult:
        error_payload: dict[str, Any] | None = None
        if error is not None:
            code = getattr(error, "code", "INVALID_REQUEST")
            retryable = bool(getattr(error, "retryable", False))
            error_payload = {
                "code": code,
                "message": str(error),
                "retryable": retryable,
            }
        raw = {
            "schema_version": 1,
            "operation": operation,
            "data": data,
            "error": error_payload,
        }
        summary = (
            f"agent_connection {operation}: ok"
            if error is None
            else f"agent_connection {operation}: {error}"
        )
        return self._result(started, status, summary, raw=raw)

    def _result(
        self, started: float, status: ToolStatus, summary: str, *, raw: Any = None
    ) -> ToolResult:
        findings: list[Finding] = []
        return ToolResult(
            tool=self.name,
            engine=None,
            engine_version=None,
            status=status,
            duration_ms=int((monotonic() - started) * 1000),
            summary=summary,
            findings=findings,
            raw=raw,
        )


def _profile_fields(request: dict[str, Any], operation: str) -> tuple[str | None, bool]:
    """T4: strict `profile` (null, "core" or "full") and
    `confirm_profile_migration` (bool), accepted only on connect."""
    profile = request.get("profile")
    confirm = request.get("confirm_profile_migration", False)
    if type(confirm) is not bool:
        raise _AgentInvalidRequestError("confirm_profile_migration must be a boolean")
    if profile is not None and (
        type(profile) is not str or profile not in MCP_PROFILES
    ):
        raise _AgentInvalidRequestError(
            f"profile must be null or one of: {', '.join(MCP_PROFILES)}"
        )
    if operation != "connect" and (profile is not None or confirm):
        raise _AgentInvalidRequestError(
            "profile and confirm_profile_migration are only valid for connect"
        )
    if confirm and profile is None:
        raise _AgentInvalidRequestError("confirm_profile_migration requires profile")
    return profile, confirm


class _AgentInvalidRequestError(AgentConnectionError):
    code = "INVALID_REQUEST"
    retryable = False


class _ScopeDenied(AgentConnectionError):
    code = "SCOPE_DENIED"
    retryable = False


__all__ = ["AgentConnectionTool"]
