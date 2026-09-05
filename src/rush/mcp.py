"""FastMCP server — stdio transport, 35 registered catalog tools.

Architecture §5, §6.

Tool naming: rush_<verb>_<noun>  (matches Graft's verb_noun pattern;
avoids collisions with other MCP servers in multi-server agent sessions).
"""

from __future__ import annotations

from pathlib import Path

from .catalog import TOOL_SPECS
from .logging import get_logger
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


def build_server():
    """Construct and return the FastMCP server with all catalog tools registered.

    Does NOT start serving — caller decides transport. See ``run_stdio``.
    """
    from mcp.server.fastmcp import FastMCP

    server = FastMCP(SERVER_NAME, instructions=build_server_instructions())
    _register_tools(server)
    return server


# Phase 41 Tools
def rush_ship_clean(dry_run: bool = False) -> str:
    from rush.tools.ship.cleaner import ScratchCleaner

    cleaner = ScratchCleaner()
    res = cleaner.clean(dry_run=dry_run)
    return f"Cleaned {res['removed_count']} items ({res['bytes_freed']} bytes freed)."


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

    return SessionContinuityTool().run(
        Path(path), operation="context_retrieve", context_handle=chunk_hash
    )


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
    return SessionContinuityTool().run(
        target.parent if target.is_absolute() else Path.cwd(),
        operation="context_pack",
        context_path=target.name if target.is_absolute() else path,
        target_symbol=symbol,
        token_budget=budget,
        permissions=ExecutionPermissions(cache_write=allow_cache_write),
    )


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
def rush_test_heal(target: str, runs: int = 5) -> str:
    import json

    from rush.tools.test_heal import TestHealer

    healer = TestHealer()
    res = healer.diagnose_and_heal(target, runs=runs)
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


rush_mesh_acquire_lock._sensitive_params = ("capability",)


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


rush_mesh_release_lock._sensitive_params = ("capability",)


def rush_swarm_merge(base_code: str, ours_code: str, theirs_code: str) -> str:
    import json

    from rush.tools.swarm_merge import SwarmMergeSolver

    solver = SwarmMergeSolver()
    res = solver.merge_3way(base_code, ours_code, theirs_code)
    return json.dumps(res, indent=2)


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

_attest_tool = next((t for t in ALL_TOOLS if t.name == "attest"), None)
rush_attest_generate = _attest_tool.__call__ if _attest_tool else None


def _register_tools(server) -> None:
    """Register each tool function as an MCP tool, routing via resolve_invocation and InvocationExecutor."""
    import functools
    import inspect

    from rush.invocation import InvocationExecutor, resolve_invocation
    from rush.invocation.executor import _parse_ordered_args

    executor = InvocationExecutor()

    # 1. Register ALL_TOOLS
    for tool in ALL_TOOLS:
        executor.register(tool.name, tool.__call__)

        def _make_tool_wrapper(t):
            @functools.wraps(t.__call__)
            def tool_mcp_wrapper(*args, **kwargs):
                bound = inspect.signature(t.__call__).bind(*args, **kwargs)
                bound.apply_defaults()
                call_args = bound.arguments
                path_val = call_args.get("path", ".")
                p = Path(path_val).resolve()
                root = p if p.is_dir() else p.parent
                req = {
                    "operation_id": t.name,
                    "path": str(p),
                    **{
                        k: v
                        for k, v in call_args.items()
                        if k != "path" and v is not None
                    },
                }
                context = resolve_invocation(req, transport="mcp", workspace_root=root)
                return executor.execute(context)

            tool_mcp_wrapper.__self__ = t
            return tool_mcp_wrapper

        server.add_tool(
            fn=_make_tool_wrapper(tool),
            name=f"rush_{tool.name.replace('-', '_')}",
            description=tool.mcp_description,
        )

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
    ]

    for fn, name, desc in custom_tools:

        def _make_handler(target_fn):
            def handler(context):
                kwargs = _parse_ordered_args(context.ordered_args)
                sig = inspect.signature(target_fn)
                for p_name in ("path", "file", "target"):
                    if p_name in sig.parameters and p_name not in kwargs:
                        target_p = (
                            context.workspace_root / context.targets[0].relative_path
                            if context.targets
                            else context.workspace_root
                        )
                        param_type = sig.parameters[p_name].annotation
                        kwargs[p_name] = (
                            target_p if param_type is Path else str(target_p)
                        )
                for p_name in sig.parameters:
                    if p_name.startswith("allow_") and p_name not in kwargs:
                        perm_name = p_name[6:]
                        kwargs[p_name] = perm_name in context.permissions
                return target_fn(**kwargs)

            return handler

        executor.register(name, _make_handler(fn))

        def _make_custom_wrapper(f, tool_id):
            @functools.wraps(f)
            def custom_mcp_wrapper(*args, **kwargs):
                bound = inspect.signature(f).bind(*args, **kwargs)
                bound.apply_defaults()
                call_args = bound.arguments
                path_val = call_args.get(
                    "path", call_args.get("file", call_args.get("target", "."))
                )
                try:
                    p = Path(path_val).resolve()
                    root = p if p.is_dir() else p.parent
                except Exception:  # noqa: BLE001
                    root = Path.cwd().resolve()
                req = {
                    "operation_id": tool_id,
                    **call_args,
                }
                context = resolve_invocation(req, transport="mcp", workspace_root=root)
                return executor.execute(context)

            return custom_mcp_wrapper

        server.add_tool(
            fn=_make_custom_wrapper(fn, name),
            name=name,
            description=desc,
        )

    # Backward compatibility alias for rush_attest
    for tool in ALL_TOOLS:
        if tool.name == "attest":
            server.add_tool(
                fn=_make_tool_wrapper(tool),
                name="rush_attest_generate",
                description="Deprecated alias for rush_attest",
            )
            break


mcp_server = build_server()


async def run_stdio() -> None:
    """Entry point for ``rush mcp serve``. Blocks until stdin closes."""
    server = build_server()
    get_logger("mcp").debug("starting rush stdio MCP server")
    await server.run_stdio_async()
