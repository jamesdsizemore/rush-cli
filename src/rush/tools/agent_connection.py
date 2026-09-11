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

MCP registration (`rush_agent_connection` in `src/rush/mcp.py`) is out of
this task's allowed files -- see this packet's own receipt for the exact
disclosed gap; a follow-up task registers it against this same tool.
"""

from __future__ import annotations

from pathlib import Path
from time import monotonic
from typing import Any, Literal

from rush.integrations.agents import (
    AgentConnectionError,
    acknowledge_agent_connection,
    agent_readiness,
    apply_agent_registration,
    discover_agents,
    initialize_agent_memory,
    plan_agent_registration,
    probe_agent_connection,
    read_agent_memory_state,
    resolve_rush_binary,
)
from rush.permissions import ExecutionPermissions, check_permissions

from .base import Finding, ToolFn, ToolResult, ToolStatus

AgentAction = Literal["list", "connect", "doctor"]

_CONNECT_PERMISSION = ExecutionPermissions(cache_write=True, artifact_write=True)


class AgentConnectionTool(ToolFn):
    """Discover, connect, and diagnose local MCP-capable coding agents."""

    name = "agent_connection"

    @property
    def mcp_description(self) -> str:
        return (
            "Discover and connect local coding agents. action=list|connect|doctor. "
            "Returns {status, findings[], summary, raw}. `connect` requires explicit "
            "cache-write and artifact-write permission; status='skipped' means denied."
        )

    def __call__(
        self,
        agent_id: str | None = None,
        action: AgentAction = "list",
        session_id: str | None = None,
        rush_binary: str | None = None,
        consent: bool = False,
        acknowledge: bool = False,
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
        project_root: Path | None = None,
        permissions: ExecutionPermissions | None = None,
        home: Path | None = None,
        data_root: Path | None = None,
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
                project_root=project_root,
                home=home,
                data_root=data_root,
            )
        except AgentConnectionError as exc:
            return self._result(started, "error", f"agent {action}: {exc}")
        except ValueError as exc:
            return self._result(started, "error", f"agent {action}: {exc}")

        return self._result(started, "ok", f"agent {action}: ok", raw=raw)

    def _dispatch(
        self,
        action: AgentAction,
        *,
        agent_id: str | None,
        session_id: str | None,
        rush_binary: str | None,
        consent: bool,
        acknowledge: bool,
        project_root: Path | None,
        home: Path | None,
        data_root: Path | None,
    ) -> Any:
        if action == "list":
            return agent_readiness(home=home, rush_binary=rush_binary)

        if action == "connect":
            if not agent_id:
                raise ValueError("connect requires agent_id")
            if not session_id:
                raise ValueError("connect requires session_id")
            binary = resolve_rush_binary(rush_binary)
            plan = plan_agent_registration(agent_id, rush_binary=binary, home=home)
            applied = apply_agent_registration(plan)
            memory_entry = initialize_agent_memory(
                agent_id,
                session_id,
                project_root=project_root,
                data_root=data_root,
                consent=consent,
            )
            if applied.ok and acknowledge:
                memory_entry = acknowledge_agent_connection(
                    agent_id, session_id, project_root=project_root, data_root=data_root
                )
            probe = probe_agent_connection(agent_id, home=home, rush_binary=binary)
            return {
                "apply": applied.to_dict(),
                "probe": probe.to_dict(),
                "memory": memory_entry,
            }

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
        if operation not in ("list", "connect", "doctor"):
            raise _AgentInvalidRequestError(f"unknown operation: {operation!r}")

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
            project_root=Path(request["project_root"])
            if request.get("project_root")
            else None,
            home=None,
            data_root=None,
        )

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


class _AgentInvalidRequestError(AgentConnectionError):
    code = "INVALID_REQUEST"
    retryable = False


class _ScopeDenied(AgentConnectionError):
    code = "SCOPE_DENIED"
    retryable = False


__all__ = ["AgentConnectionTool"]
