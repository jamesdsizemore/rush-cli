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
    tool_names = ", ".join(f"rush_{name}" for name in TOOL_SPECS)
    maturity = "; ".join(
        f"rush_{name}={spec.maturity}" for name, spec in TOOL_SPECS.items()
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


def _register_tools(server) -> None:
    """Register each tool function as an MCP tool."""
    for tool in ALL_TOOLS:
        server.add_tool(
            fn=tool.__call__,
            name=f"rush_{tool.name}",
            description=tool.mcp_description,
        )

    # Phase 41 Tools
    def mcp_rush_session_save(name: str, files: list[str]) -> str:
        from rush.memory.checkpoint_journal import CheckpointJournal

        journal = CheckpointJournal()
        dest = journal.save_checkpoint(name, {}, files)
        return f"Session saved: {dest}"

    def mcp_rush_ship_clean(dry_run: bool = False) -> str:
        from rush.tools.ship.cleaner import ScratchCleaner

        cleaner = ScratchCleaner()
        res = cleaner.clean(dry_run=dry_run)
        return (
            f"Cleaned {res['removed_count']} items ({res['bytes_freed']} bytes freed)."
        )

    def mcp_rush_ship_env() -> str:
        from rush.tools.ship.env_linter import EnvParityLinter

        linter = EnvParityLinter()
        res = linter.lint()
        if res["passed"]:
            return "All environment variables declared in .env.example."
        return f"Missing declarations in .env.example: {', '.join(res['missing_in_example'])}"

    # Phase 42 Tools
    def mcp_rush_ship_gate() -> str:
        from rush.tools.ship.cockpit import ShipCockpit

        cockpit = ShipCockpit()
        verdict = cockpit.evaluate_gate()
        return f"Ship Gate {'PASSED' if verdict.all_passed else 'FAILED'} ({verdict.score_pct}%)"

    def mcp_rush_token_outline(path: str, focus_symbol: str = "") -> str:
        from rush.token_economy.ast_skeletonizer import AstSkeletonizer

        skeletonizer = AstSkeletonizer()
        p = Path(path)
        if not p.exists():
            return f"Error: {path} not found"
        code = p.read_text(encoding="utf-8", errors="ignore")
        return skeletonizer.skeletonize(code, focus_symbol=focus_symbol or None)

    # Phase 43 Tools
    def mcp_rush_context_retrieve(chunk_hash: str) -> str:
        from rush.token_economy.ccr_store import CCRStore

        store = CCRStore()
        content = store.retrieve_chunk(chunk_hash)
        return content or f"Error: Chunk {chunk_hash} not found"

    def mcp_rush_hallu_guard(path: str = "") -> str:
        from rush.tools.hallu_guard import HalluGuard

        guard = HalluGuard()
        if path:
            violations = guard.check_file(Path(path))
            return (
                "Grounded" if not violations else f"Violations: {', '.join(violations)}"
            )
        res = guard.audit_codebase()
        return (
            "All imports grounded"
            if res["passed"]
            else f"Found {res['findings_count']} ungrounded imports"
        )

    def mcp_rush_context_mistakes_check() -> str:
        from rush.memory.mistake_miner import MistakeMiner

        miner = MistakeMiner()
        mistakes = miner.mine_mistakes()
        return f"Loaded {len(mistakes)} mistake guardrails"

    server.add_tool(
        fn=mcp_rush_session_save,
        name="rush_session_save",
        description="Save developer context snapshot to .rush/sessions/",
    )
    server.add_tool(
        fn=mcp_rush_ship_clean,
        name="rush_ship_clean",
        description="Clean scratch directories and build caches before release",
    )
    server.add_tool(
        fn=mcp_rush_ship_env,
        name="rush_ship_env",
        description="Audit codebase environment variable usage against .env.example",
    )
    server.add_tool(
        fn=mcp_rush_ship_gate,
        name="rush_ship_gate",
        description="Run 7-vector pre-flight release readiness cockpit",
    )
    server.add_tool(
        fn=mcp_rush_token_outline,
        name="rush_token_outline",
        description="Generate token-efficient AST skeleton outline of a code file",
    )
    server.add_tool(
        fn=mcp_rush_context_retrieve,
        name="rush_context_retrieve",
        description="Retrieve uncompressed content from CCR chunk store by hash",
    )
    server.add_tool(
        fn=mcp_rush_hallu_guard,
        name="rush_hallu_guard",
        description="Audit code imports against installed packages and stdlib",
    )
    server.add_tool(
        fn=mcp_rush_context_mistakes_check,
        name="rush_context_mistakes_check",
        description="Check git revert history for past mistakes and anti-patterns",
    )

    # Phase 44 Tools
    def mcp_rush_context_pack(path: str, symbol: str = "", budget: int = 4000) -> str:
        from rush.codegraph.context_packer import ContextPacker

        packer = ContextPacker()
        res = packer.pack(Path(path), target_symbol=symbol, max_tokens=budget)
        if "error" in res:
            return f"Error: {res['error']}"
        return res["packed_text"]

    server.add_tool(
        fn=mcp_rush_context_pack,
        name="rush_context_pack",
        description="Pack graph-pruned context outline under a strict token budget",
    )

    # Phase 45 Tools
    def mcp_rush_context_gain_stats() -> str:
        import json

        from rush.token_economy.telemetry import TelemetryStore

        store = TelemetryStore()
        return json.dumps(store.get_summary(), indent=2)

    server.add_tool(
        fn=mcp_rush_context_gain_stats,
        name="rush_context_gain_stats",
        description="Get real-time token economy savings and cost metrics",
    )

    # Phase 46 Tools
    def mcp_rush_blast_radius(path: str, depth: int = 5) -> str:
        from rush.tools.blast_radius import BlastRadiusAnalyzer

        analyzer = BlastRadiusAnalyzer()
        report = analyzer.analyze([Path(path)], max_depth=depth)
        return report.model_dump_json(indent=2)

    def mcp_rush_arch_guard() -> str:
        from rush.tools.arch_guard import ArchGuard

        guard = ArchGuard()
        res = guard.evaluate_boundaries()
        return (
            "All boundaries respected"
            if res["passed"]
            else f"Found {res['violations_count']} layer violations"
        )

    server.add_tool(
        fn=mcp_rush_blast_radius,
        name="rush_blast_radius",
        description="Calculate downstream transitive blast radius for a changed file",
    )
    server.add_tool(
        fn=mcp_rush_arch_guard,
        name="rush_arch_guard",
        description="Validate codebase against clean architecture layer boundaries",
    )


async def run_stdio() -> None:
    """Entry point for ``rush mcp serve``. Blocks until stdin closes."""
    server = build_server()
    get_logger("mcp").debug("starting rush stdio MCP server")
    await server.run_stdio_async()
