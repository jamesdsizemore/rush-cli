"""FastMCP server — stdio transport, 35 registered catalog tools.

Architecture §5, §6.

Tool naming: rush_<verb>_<noun>  (matches Graft's verb_noun pattern;
avoids collisions with other MCP servers in multi-server agent sessions).
"""

from __future__ import annotations

from pathlib import Path

from .catalog import TOOL_SPECS
from .contracts.results import ToolResultV1
from .logging import get_logger
from .permissions import ExecutionPermissions
from .tools import ALL_TOOLS

SERVER_NAME = "rush"


def build_server_instructions() -> str:
    """Describe the live catalog without duplicating a fixed tool list."""
    tool_names = ", ".join(f"rush_{name.replace('-', '_')}" for name in TOOL_SPECS)
    maturity = "; ".join(
        f"rush_{name.replace('-', '_')}={spec.maturity}"
        for name, spec in TOOL_SPECS.items()
    )

    return (
        "rush — code-quality tools for coding agents. "
        f"Available tools: {tool_names}. "
        "Each takes a path (file or directory) and returns a structured JSON "
        "with status (ok|warn|fail|error|skipped), findings, and summary. "
        "If status='skipped', the underlying engine is not installed; install it "
        "or pick a different path. Pairs well with `npx @nanonets/graft` for "
        f"context-graph queries. Maturity: {maturity}."
    )


def build_server(memory_session: str | None = None):
    """Construct and return the FastMCP server with all catalog tools registered.

    Does NOT start serving — caller decides transport. See ``run_stdio``.

    MC11: when `memory_session` is given, this is a *restricted receiver* -- it registers
    only the single `rush_memory` bridge tool (receive/expand/related/resume) bound to that
    one handoff session, and nothing else. The capability travels only through the
    `RUSH_MEMORY_CAPABILITY` environment variable, never a CLI argument. This is the only
    path that ever narrows the server below its full catalog; the default (`memory_session
    =None`) is unchanged and still registers every catalog tool.
    """
    from mcp.server.fastmcp import FastMCP

    if memory_session is not None:
        import os

        from .mcp_support.tool_registry import register_memory_bridge_tool

        capability = os.environ.get("RUSH_MEMORY_CAPABILITY", "")
        server = FastMCP(
            SERVER_NAME,
            instructions=(
                "Restricted rush memory handoff receiver. Only rush_memory "
                "(receive/expand/related/resume) is available in this session."
            ),
        )
        register_memory_bridge_tool(
            server,
            root=Path.cwd(),
            session_id=memory_session,
            capability=capability,
        )
        return server

    server = FastMCP(SERVER_NAME, instructions=build_server_instructions())
    _register_tools(server)
    return server


# Phase 41 Tools
def rush_ship_clean(
    path: Path = Path("."),
    apply: bool = False,
    allow_artifact_write: bool = False,
) -> dict[str, object]:
    from rush.tools.ship.cleaner import ScratchCleaner

    return ScratchCleaner(path).clean(
        apply=apply,
        permissions=ExecutionPermissions(artifact_write=allow_artifact_write),
    )


def rush_ship_env() -> str:
    from rush.tools.ship.env_linter import EnvParityLinter

    linter = EnvParityLinter()
    res = linter.lint()
    if res["passed"]:
        return "All environment variables declared in .env.example."
    return (
        f"Missing declarations in .env.example: {', '.join(res['missing_in_example'])}"
    )


# Phase 42 Tools
def rush_ship_gate() -> str:
    from rush.tools.ship.cockpit import ShipCockpit

    cockpit = ShipCockpit()
    verdict = cockpit.evaluate_gate()
    return f"Ship Gate {'PASSED' if verdict.all_passed else 'FAILED'} ({verdict.score_pct}%)"


def rush_token_outline(path: str, focus_symbol: str = "") -> str:
    from rush.token_economy.ast_skeletonizer import AstSkeletonizer

    skeletonizer = AstSkeletonizer()
    p = Path(path)
    if not p.exists():
        return f"Error: {path} not found"
    code = p.read_text(encoding="utf-8", errors="ignore")
    return skeletonizer.skeletonize(code, focus_symbol=focus_symbol or None)


# Phase 43 Tools
def rush_context_retrieve(chunk_hash: str, path: str = ".") -> dict:
    from rush.tools.continuity import SessionContinuityTool

    result = SessionContinuityTool().run(
        Path(path), operation="context_retrieve", context_handle=chunk_hash
    )
    return result.to_dict() if isinstance(result, ToolResultV1) else dict(result)


def rush_hallu_guard(path: str = "") -> str:
    from rush.tools.hallu_guard import HalluGuard

    guard = HalluGuard()
    if path:
        violations = guard.check_file(Path(path))
        return "Grounded" if not violations else f"Violations: {', '.join(violations)}"
    res = guard.audit_codebase()
    return (
        "All imports grounded"
        if res["passed"]
        else f"Found {res['findings_count']} ungrounded imports"
    )


def rush_context_mistakes_check() -> str:
    from rush.memory.mistake_miner import MistakeMiner

    miner = MistakeMiner()
    mistakes = miner.mine_mistakes()
    return f"Loaded {len(mistakes)} mistake guardrails"


# Phase 44 Tools
def rush_context_pack(
    path: str,
    symbol: str = "",
    budget: int = 4000,
    allow_cache_write: bool = False,
) -> dict:
    from rush.permissions import ExecutionPermissions
    from rush.tools.continuity import SessionContinuityTool

    target = Path(path)
    result = SessionContinuityTool().run(
        target.parent if target.is_absolute() else Path.cwd(),
        operation="context_pack",
        context_path=target.name if target.is_absolute() else path,
        target_symbol=symbol,
        token_budget=budget,
        permissions=ExecutionPermissions(cache_write=allow_cache_write),
    )
    return result.to_dict() if isinstance(result, ToolResultV1) else dict(result)


# Phase 45 Tools
def rush_context_gain_stats() -> str:
    import json

    from rush.token_economy.telemetry import TelemetryStore

    store = TelemetryStore()
    return json.dumps(store.get_summary(), indent=2)


# Phase 46 Tools
def rush_blast_radius(path: str, depth: int = 5) -> str:
    from rush.tools.blast_radius import BlastRadiusAnalyzer

    analyzer = BlastRadiusAnalyzer()
    report = analyzer.analyze([Path(path)], max_depth=depth)
    return report.model_dump_json(indent=2)


def rush_arch_guard() -> str:
    from rush.tools.arch_guard import ArchGuard

    guard = ArchGuard()
    res = guard.evaluate_boundaries()
    return (
        "All boundaries respected"
        if res["passed"]
        else f"Found {res['violations_count']} layer violations"
    )


# Phase 47 Tools
def rush_test_heal(
    target: str,
    runs: int = 20,
    seed: int = 0,
    dry_run: bool = True,
    allow_slow: bool = False,
    allow_artifact_write: bool = False,
    allow_build: bool = False,
) -> str:
    import json

    from rush.tools.test_heal import TestHealer

    healer = TestHealer()
    res = healer(
        target,
        runs=runs,
        seed=seed,
        dry_run=dry_run,
        allow_slow=allow_slow,
        allow_artifact_write=allow_artifact_write,
        allow_build=allow_build,
    )
    return json.dumps(res, indent=2)


def rush_api_diff(base: str = "main") -> str:
    import json

    from rush.tools.api_diff import ApiDiffer

    differ = ApiDiffer()
    res = differ.diff_public_api(base_ref=base)
    return json.dumps(res, indent=2)


# Phase 48 Tools
def rush_db_drift() -> str:
    import json

    from rush.tools.db_drift import DbDriftAuditor

    auditor = DbDriftAuditor()
    res = auditor.audit_drift()
    return json.dumps(res, indent=2)


def rush_simplify(file: str, max_complexity: int = 10) -> str:
    import json

    from rush.tools.simplify import ComplexityDecomposer

    decomposer = ComplexityDecomposer()
    res = decomposer.decompose_file(Path(file), max_complexity=max_complexity)
    return json.dumps(res, indent=2)


def rush_strictify(file: str) -> str:
    import json

    from rush.tools.strictify import TypeSynthesizer

    synth = TypeSynthesizer()
    res = synth.audit_and_synthesize(Path(file))
    return json.dumps(res, indent=2)


# Phase 49 Tools
def rush_trace() -> str:
    import json

    from rush.tools.trace import TraceScanner

    scanner = TraceScanner()
    res = scanner.scan_traceability()
    return json.dumps(res, indent=2)


def rush_mesh_acquire_lock(
    path: str, agent_id: str, capability: str | None = None
) -> bool:
    """Acquire non-blocking multi-agent file lock using caller capability."""
    from rush.mcp_mesh.capabilities import LockCapabilityInput
    from rush.mcp_mesh.lock_manager import MeshLockManager

    cap_input = (
        LockCapabilityInput(
            token=capability, agent_id=agent_id, channel_type="mcp_sensitive"
        )
        if capability is not None
        else None
    )
    mgr = MeshLockManager()
    res = mgr.acquire(Path(path), agent_id=agent_id, capability=cap_input)
    return bool(res[0] if isinstance(res, tuple) else res)


rush_mesh_acquire_lock.__dict__["_sensitive_params"] = ("capability",)


def rush_mesh_release_lock(
    path: str, agent_id: str, capability: str | None = None
) -> bool:
    """Release multi-agent file lock using caller capability."""
    from rush.mcp_mesh.capabilities import LockCapabilityInput
    from rush.mcp_mesh.lock_manager import MeshLockManager

    cap_input = (
        LockCapabilityInput(
            token=capability, agent_id=agent_id, channel_type="mcp_sensitive"
        )
        if capability is not None
        else None
    )
    mgr = MeshLockManager()
    return mgr.release(Path(path), capability=cap_input, agent_id=agent_id)


rush_mesh_release_lock.__dict__["_sensitive_params"] = ("capability",)


def rush_swarm_merge(base_code: str, ours_code: str, theirs_code: str) -> str:
    import json

    from rush.tools.swarm_merge import SwarmMergeSolver

    solver = SwarmMergeSolver()
    res = solver.merge_3way(base_code, ours_code, theirs_code)
    return json.dumps(res, indent=2)


# P65-03.3 CONNECT (Phase 65 §3.2): one `rush_project` MCP tool over `ProjectTool`,
# matching the CLI's `project` group. `select` binds a project to the caller-supplied
# `session_id` explicitly -- never a global cwd guessed by this server.
#
# Plan §6.1: "Every new MCP entry accepts exactly one request: dict with
# schema_version: 1 and operation-specific fields." Dispatches through the
# canonical envelope call boundary (`handle_request`), not the legacy
# flat-kwarg `.run()` path.
def rush_project(request: dict[str, object]) -> dict[str, object]:
    from rush.tools.project import ProjectTool

    result = ProjectTool().handle_request(dict(request))
    return dict(result)


# P65-04.3 CONNECT (Phase 65 §3.2): one `rush_scan` MCP tool over `ScanTool`,
# matching `rush_project`'s wiring mechanism and the CLI's `scan` command.
# `plan`/`run`/`status`/`rescan` are implemented on `ScanTool` (§6.1).
#
# P65-08.3 CONNECT (Phase 65 §3.2, F35, T216): `cancel`/`resume` reach
# `rush.workflows.project_run.cancel_scan_run`/`resume_scan_run` directly --
# `ScanTool` (`src/rush/tools/scan.py`) is outside this packet's allowed
# files and cannot register these two operations itself, so `rush_scan`
# intercepts them here before ever delegating to `ScanTool`, mirroring the
# `rescan`-direct-call precedent the CLI already uses for
# `rescan_project_run`. Registering a NEW operation string on an already-
# registered MCP tool name never changes the set of advertised MCP tool
# names itself, so this needs no new `governance/public-operations.toml`
# entry (only a brand-new CLI leaf command does -- see `cli.py`'s `scan
# cancel`/`scan resume` docstrings for that separately-flagged gap).
_SCAN_DIRECT_OPERATIONS = frozenset({"cancel", "resume"})


def rush_scan(request: dict[str, object]) -> dict[str, object]:
    from rush.tools.scan import ScanTool

    operation = request.get("operation") if isinstance(request, dict) else None
    if operation in _SCAN_DIRECT_OPERATIONS:
        return _rush_scan_direct_operation(dict(request), str(operation))

    result = ScanTool().handle_request(dict(request))
    return dict(result)


def _scan_direct_envelope(
    operation: str,
    started: float,
    status: str,
    *,
    data: object = None,
    error: dict[str, object] | None = None,
) -> dict[str, object]:
    from time import monotonic

    return {
        "tool": "scan",
        "engine": None,
        "engine_version": None,
        "status": status,
        "duration_ms": int((monotonic() - started) * 1000),
        "summary": (
            f"scan {operation}: ok" if status == "ok" else f"scan {operation}: error"
        ),
        "findings": [],
        "raw": {
            "schema_version": 1,
            "operation": operation,
            "data": data,
            "error": error,
        },
    }


def _scan_direct_error(
    operation: str, started: float, code: str, message: str
) -> dict[str, object]:
    return _scan_direct_envelope(
        operation,
        started,
        "error",
        error={"code": code, "message": message, "retryable": False},
    )


def _scan_direct_allowed_fields(operation: str) -> set[str]:
    allowed = {"schema_version", "operation", "project", "run_id"}
    if operation == "resume":
        allowed |= {
            "allow_network",
            "allow_download",
            "allow_cache_write",
            "allow_build",
            "allow_slow",
            "allow_artifact_write",
            "allow_browser",
        }
    return allowed


def _validate_scan_direct_request(
    request: dict[str, object], operation: str
) -> tuple[str, str] | None:
    """Returns an `(code, message)` error pair, or `None` if valid."""
    if request.get("schema_version") != 1:
        return "INVALID_REQUEST", "schema_version must be 1"
    project = request.get("project")
    run_id = request.get("run_id")
    if not isinstance(project, str) or not project:
        return "INVALID_REQUEST", f"{operation} requires project"
    if not isinstance(run_id, str) or not run_id:
        return "INVALID_REQUEST", f"{operation} requires run_id"
    unknown = set(request) - _scan_direct_allowed_fields(operation)
    if unknown:
        return "INVALID_REQUEST", f"unknown request field(s): {sorted(unknown)}"
    return None


def _permissions_from_scan_direct_request(
    request: dict[str, object],
) -> ExecutionPermissions:
    return ExecutionPermissions(
        network=bool(request.get("allow_network", False)),
        download=bool(request.get("allow_download", False)),
        cache_write=bool(request.get("allow_cache_write", False)),
        build=bool(request.get("allow_build", False)),
        slow=bool(request.get("allow_slow", False)),
        artifact_write=bool(request.get("allow_artifact_write", False)),
        browser=bool(request.get("allow_browser", False)),
    )


def _rush_scan_direct_operation(
    request: dict[str, object], operation: str
) -> dict[str, object]:
    """`rush_scan` `cancel`/`resume`: mirrors `ScanTool._envelope_result`'s
    `{schema_version, operation, data, error}` `raw` shape so callers see
    one consistent `rush_scan` contract regardless of which operation
    dispatched."""
    from time import monotonic

    from rush.workflows.project_run import ScanError, cancel_scan_run, resume_scan_run

    started = monotonic()
    invalid = _validate_scan_direct_request(request, operation)
    if invalid is not None:
        return _scan_direct_error(operation, started, *invalid)

    project = str(request["project"])
    run_id = str(request["run_id"])
    try:
        if operation == "cancel":
            data: object = cancel_scan_run(project, run_id)
        else:
            permissions = _permissions_from_scan_direct_request(request)
            if not (permissions.cache_write and permissions.artifact_write):
                return _scan_direct_error(
                    operation,
                    started,
                    "SCOPE_DENIED",
                    "resume requires allow_cache_write and allow_artifact_write",
                )
            data = resume_scan_run(project, run_id, permissions=permissions).to_dict()
    except ScanError as exc:
        return _scan_direct_error(
            operation, started, getattr(exc, "code", "INVALID_REQUEST"), str(exc)
        )

    return _scan_direct_envelope(operation, started, "ok", data=data)


# P65-05.3 CONNECT (Phase 65 §3.2): one `rush_agent_connection` MCP tool over
# `AgentConnectionTool`, matching `rush_project`/`rush_scan`'s wiring mechanism
# and the CLI's `agent list/connect/doctor` commands.
def rush_agent_connection(request: dict[str, object]) -> dict[str, object]:
    from rush.tools.agent_connection import AgentConnectionTool

    result = AgentConnectionTool().handle_request(dict(request))
    return dict(result)


# P65-06.3 CONNECT (Phase 65 §3.2, F35): one `rush_scan_handoff` MCP tool over
# `ScanHandoffTool`, matching `rush_project`/`rush_scan`'s wiring mechanism and
# the CLI's `scan handoff` subcommand. Operations: prepare/dispatch/status/
# acknowledge/complete (plan §6.1). An agent-ready response's `data` always
# carries `state` (the real, non-fabricated lifecycle state) so a caller's
# next operation is unambiguous. `rush_scan`'s `rescan` operation (plan §6.1)
# is implemented via `ScanTool`; see `rush.workflows.project_run.rescan_project_run`.
def rush_scan_handoff(request: dict[str, object]) -> dict[str, object]:
    from rush.tools.scan_handoff import ScanHandoffTool

    result = ScanHandoffTool().handle_request(dict(request))
    return dict(result)


# Backward compatibility aliases
mcp_rush_ship_clean = rush_ship_clean
mcp_rush_ship_env = rush_ship_env
mcp_rush_ship_gate = rush_ship_gate
mcp_rush_token_outline = rush_token_outline
mcp_rush_context_retrieve = rush_context_retrieve
mcp_rush_hallu_guard = rush_hallu_guard
mcp_rush_context_mistakes_check = rush_context_mistakes_check
mcp_rush_context_pack = rush_context_pack
mcp_rush_context_gain_stats = rush_context_gain_stats
mcp_rush_blast_radius = rush_blast_radius
mcp_rush_arch_guard = rush_arch_guard
mcp_rush_test_heal = rush_test_heal
mcp_rush_api_diff = rush_api_diff
mcp_rush_db_drift = rush_db_drift
mcp_rush_simplify = rush_simplify
mcp_rush_strictify = rush_strictify
mcp_rush_trace = rush_trace
mcp_rush_mesh_acquire_lock = rush_mesh_acquire_lock
mcp_rush_mesh_release_lock = rush_mesh_release_lock
mcp_rush_swarm_merge = rush_swarm_merge
mcp_rush_project = rush_project
mcp_rush_scan = rush_scan
mcp_rush_agent_connection = rush_agent_connection
mcp_rush_scan_handoff = rush_scan_handoff

_attest_tool = next((t for t in ALL_TOOLS if t.name == "attest"), None)
rush_attest_generate = _attest_tool.__call__ if _attest_tool else None


def _register_tools(server) -> None:
    """Register each tool function as an MCP tool, routing via resolve_invocation and InvocationExecutor."""
    from rush.invocation import InvocationExecutor
    from rush.mcp_support.tool_registry import (
        register_all_tools,
        register_custom_tools,
    )

    executor = InvocationExecutor()
    register_all_tools(server, executor, ALL_TOOLS)

    # 2. Register custom phase tools
    custom_tools = [
        (
            rush_ship_clean,
            "rush_ship_clean",
            "Clean scratch directories and build caches before release",
        ),
        (
            rush_ship_env,
            "rush_ship_env",
            "Audit codebase environment variable usage against .env.example",
        ),
        (
            rush_ship_gate,
            "rush_ship_gate",
            "Run 7-vector pre-flight release readiness cockpit",
        ),
        (
            rush_token_outline,
            "rush_token_outline",
            "Generate token-efficient AST skeleton outline of a code file",
        ),
        (
            rush_context_retrieve,
            "rush_context_retrieve",
            "Retrieve uncompressed content from CCR chunk store by hash",
        ),
        (
            rush_hallu_guard,
            "rush_hallu_guard",
            "Audit code imports against installed packages and stdlib",
        ),
        (
            rush_context_mistakes_check,
            "rush_context_mistakes_check",
            "Check git revert history for past mistakes and anti-patterns",
        ),
        (
            rush_context_pack,
            "rush_context_pack",
            "Pack graph-pruned context outline under a strict token budget",
        ),
        (
            rush_context_gain_stats,
            "rush_context_gain_stats",
            "Get real-time token economy savings and cost metrics",
        ),
        (
            rush_blast_radius,
            "rush_blast_radius",
            "Calculate downstream transitive blast radius for a changed file",
        ),
        (
            rush_arch_guard,
            "rush_arch_guard",
            "Validate codebase against clean architecture layer boundaries",
        ),
        (
            rush_test_heal,
            "rush_test_heal",
            "Diagnose flaky test race conditions and suggest fixes",
        ),
        (
            rush_api_diff,
            "rush_api_diff",
            "Detect breaking public API changes against base Git ref",
        ),
        (
            rush_db_drift,
            "rush_db_drift",
            "Audit ORM models against migrations to detect schema drift",
        ),
        (
            rush_simplify,
            "rush_simplify",
            "Decompose high-complexity functions into modular helpers",
        ),
        (
            rush_strictify,
            "rush_strictify",
            "Synthesize runtime type guards for unvalidated parameters",
        ),
        (
            rush_trace,
            "rush_trace",
            "Scan codebase and specs to output requirement traceability matrix",
        ),
        (
            rush_mesh_acquire_lock,
            "rush_mesh_acquire_lock",
            "Acquire non-blocking multi-agent file lock",
        ),
        (
            rush_mesh_release_lock,
            "rush_mesh_release_lock",
            "Release multi-agent file lock",
        ),
        (
            rush_swarm_merge,
            "rush_swarm_merge",
            "Execute 3-way AST merge conflict resolution",
        ),
        (
            rush_project,
            "rush_project",
            "Register, discover, select, and configure Rush projects",
        ),
        (
            rush_scan,
            "rush_scan",
            "Plan, run, and check status of a full-project scan",
        ),
        (
            rush_agent_connection,
            "rush_agent_connection",
            "Discover, connect, and diagnose local coding agents",
        ),
        (
            rush_scan_handoff,
            "rush_scan_handoff",
            "Prepare, dispatch, and acknowledge a bounded agent handoff of scan findings",
        ),
    ]

    register_custom_tools(server, executor, custom_tools)


mcp_server = build_server()


async def run_stdio(memory_session: str | None = None) -> None:
    """Entry point for ``rush mcp serve``. Blocks until stdin closes."""
    server = build_server(memory_session)
    get_logger("mcp").debug("starting rush stdio MCP server")
    await server.run_stdio_async()
