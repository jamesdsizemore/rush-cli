"""Phase 60 Module Boundary Tests.

Validates architectural decomposition and symbol ownership across CLI and MCP
transport boundaries (T-60.10, T-60.11, T-60.12).
"""

from __future__ import annotations


def test_cli_support_modules_own_exact_symbols() -> None:
    """T-60.10: CLI support modules own the extracted implementations directly."""
    from rush.cli_support import catalog_commands, options, rendering

    assert hasattr(options, "_extract_permissions")
    assert callable(options._extract_permissions)
    assert options._extract_permissions.__module__ == "rush.cli_support.options"

    assert hasattr(options, "permission_options")
    assert callable(options.permission_options)
    assert options.permission_options.__module__ == "rush.cli_support.options"

    assert hasattr(catalog_commands, "build_catalog_path_command")
    assert callable(catalog_commands.build_catalog_path_command)
    assert (
        catalog_commands.build_catalog_path_command.__module__
        == "rush.cli_support.catalog_commands"
    )

    assert hasattr(rendering, "_run_tool")
    assert callable(rendering._run_tool)
    assert rendering._run_tool.__module__ == "rush.cli_support.rendering"

    assert hasattr(rendering, "_render_session_result")
    assert callable(rendering._render_session_result)
    assert rendering._render_session_result.__module__ == "rush.cli_support.rendering"


def test_cli_compatibility_names_resolve_to_extracted_implementations() -> None:
    """T-60.11: cli.py maintains backwards-compatible re-exports matching extracted objects via identity."""
    import rush.cli
    import rush.cli_support.catalog_commands
    import rush.cli_support.options
    import rush.cli_support.rendering

    assert (
        rush.cli._extract_permissions is rush.cli_support.options._extract_permissions
    )
    assert rush.cli.permission_options is rush.cli_support.options.permission_options
    assert (
        rush.cli.build_catalog_path_command
        is rush.cli_support.catalog_commands.build_catalog_path_command
    )
    assert rush.cli._run_tool is rush.cli_support.rendering._run_tool
    assert (
        rush.cli._render_session_result
        is rush.cli_support.rendering._render_session_result
    )


def test_mcp_support_modules_own_exact_symbols() -> None:
    """T-60.12: mcp_support.tool_registry defines registration and wrapper helpers."""
    from rush.mcp_support import tool_registry

    for sym in (
        "register_all_tools",
        "register_custom_tools",
        "make_tool_wrapper",
        "make_custom_wrapper",
    ):
        assert hasattr(tool_registry, sym), f"{sym} missing from tool_registry"
        fn = getattr(tool_registry, sym)
        assert callable(fn), f"{sym} is not callable"
        assert fn.__module__ == "rush.mcp_support.tool_registry", (
            f"{sym} not defined in tool_registry"
        )


def test_continuity_modules_own_exact_symbols() -> None:
    """T-60.13: Continuity submodules own context, coordination, providers, and receipts operations directly."""
    from rush.continuity import context, coordination, providers, receipts

    # Context operations
    for sym_options in (
        ("pack_context", "_context_pack"),
        ("retrieve_context", "_context_retrieve"),
    ):
        found_fn = None
        for sym in sym_options:
            if hasattr(context, sym):
                found_fn = getattr(context, sym)
                break
        assert found_fn is not None, (
            f"Neither {' or '.join(sym_options)} found in context"
        )
        assert callable(found_fn), f"{found_fn} is not callable"
        assert found_fn.__module__ == "rush.continuity.context", (
            f"{found_fn} not defined in rush.continuity.context"
        )

    # Coordination operations
    for sym in ("check_coordination", "preview_merge", "recover_coordination"):
        assert hasattr(coordination, sym), f"{sym} missing from coordination"
        fn = getattr(coordination, sym)
        assert callable(fn), f"{sym} is not callable"
        assert fn.__module__ == "rush.continuity.coordination", (
            f"{sym} not defined in rush.continuity.coordination"
        )

    # Provider operations
    for sym in (
        "resume_provider",
        "resume_omniroute",
        "provider_handoff",
        "windows_cmd_command",
        "provider_command",
        "provider_prompt",
    ):
        assert hasattr(providers, sym), f"{sym} missing from providers"
        fn = getattr(providers, sym)
        assert callable(fn), f"{sym} is not callable"
        assert fn.__module__ == "rush.continuity.providers", (
            f"{sym} not defined in rush.continuity.providers"
        )

    # Receipts operations
    for sym in ("save_receipt", "restore_receipt"):
        assert hasattr(receipts, sym), f"{sym} missing from receipts"
        fn = getattr(receipts, sym)
        assert callable(fn), f"{sym} is not callable"
        assert fn.__module__ == "rush.continuity.receipts", (
            f"{sym} not defined in rush.continuity.receipts"
        )
