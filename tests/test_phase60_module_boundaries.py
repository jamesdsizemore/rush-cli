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


def test_review_modules_own_exact_symbols() -> None:
    """T-60.14: Review submodules own collection, heuristics, llm egress, and results directly."""
    from rush.review import collection, llm, results

    # File collection
    found_collect = None
    for sym in ("collect_reviewable_files", "_collect_reviewable_files"):
        if hasattr(collection, sym):
            found_collect = getattr(collection, sym)
            break
    assert found_collect is not None, (
        "Neither collect_reviewable_files nor _collect_reviewable_files found in rush.review.collection"
    )
    assert callable(found_collect), f"{found_collect} is not callable"
    assert found_collect.__module__ == "rush.review.collection", (
        f"{found_collect} not defined in rush.review.collection"
    )

    # Safe reading
    found_read = None
    for sym in ("read_file_safely", "_read_file_safely"):
        if hasattr(collection, sym):
            found_read = getattr(collection, sym)
            break
    assert found_read is not None, (
        "Neither read_file_safely nor _read_file_safely found in rush.review.collection"
    )
    assert callable(found_read), f"{found_read} is not callable"
    assert found_read.__module__ == "rush.review.collection", (
        f"{found_read} not defined in rush.review.collection"
    )

    # Heuristic checks / filters
    for sym_options in (
        ("file_size_heuristic", "_file_size_heuristic", "_check_large_file_heuristic"),
        ("todo_density_heuristic", "_todo_density_heuristic", "_check_todo_heuristic"),
        ("missing_docstrings_heuristic", "_missing_docstrings_heuristic"),
        ("naming_heuristic", "_naming_heuristic"),
        (
            "scaffold_marker_heuristic",
            "_scaffold_marker_heuristic",
            "_check_scaffold_heuristic",
        ),
        (
            "is_source_policy_excluded",
            "_is_source_policy_excluded",
            "_check_source_policy_exclusions",
        ),
    ):
        found_fn = None
        for sym in sym_options:
            if hasattr(collection, sym):
                found_fn = getattr(collection, sym)
                break
        assert found_fn is not None, (
            f"None of {', '.join(sym_options)} found in rush.review.collection"
        )
        assert callable(found_fn), f"{found_fn} is not callable"
        assert found_fn.__module__ == "rush.review.collection", (
            f"{found_fn} not defined in rush.review.collection"
        )

    # LLM egress
    found_llm = None
    for sym in ("maybe_call_llm", "_maybe_call_llm"):
        if hasattr(llm, sym):
            found_llm = getattr(llm, sym)
            break
    assert found_llm is not None, (
        "Neither maybe_call_llm nor _maybe_call_llm found in rush.review.llm"
    )
    assert callable(found_llm), f"{found_llm} is not callable"
    assert found_llm.__module__ == "rush.review.llm", (
        f"{found_llm} not defined in rush.review.llm"
    )

    # Results assembly
    assert hasattr(results, "assemble_review_result"), (
        "assemble_review_result missing from rush.review.results"
    )
    assert callable(results.assemble_review_result), (
        "assemble_review_result is not callable"
    )
    assert results.assemble_review_result.__module__ == "rush.review.results", (
        "assemble_review_result not defined in rush.review.results"
    )


def test_runtime_modules_own_exact_symbols() -> None:
    """T-60.15: Runtime modules own binaries, subprocesses, and result_helpers directly."""
    from rush.runtime import binaries, result_helpers, subprocesses

    for sym in (
        "_venv_scripts_dir",
        "_resolve_binary_cached",
        "clear_binary_cache",
        "resolve_binary",
        "engine_on_path",
    ):
        assert hasattr(binaries, sym), f"{sym} missing from rush.runtime.binaries"
        fn = getattr(binaries, sym)
        assert callable(fn), f"{sym} is not callable"
        assert fn.__module__ == "rush.runtime.binaries", (
            f"{sym} not defined in rush.runtime.binaries"
        )

    for sym in (
        "_bounded_redacted_output",
        "run_subprocess",
        "run_engine",
        "_install_hint",
    ):
        assert hasattr(subprocesses, sym), (
            f"{sym} missing from rush.runtime.subprocesses"
        )
        fn = getattr(subprocesses, sym)
        assert callable(fn), f"{sym} is not callable"
        assert fn.__module__ == "rush.runtime.subprocesses", (
            f"{sym} not defined in rush.runtime.subprocesses"
        )

    for sym in (
        "skipped_result",
        "error_result",
        "_redact_finding_message",
        "finding_fingerprint",
        "normalize_findings",
        "exit_code_for",
        "now_ms",
        "elapsed_ms",
    ):
        assert hasattr(result_helpers, sym), (
            f"{sym} missing from rush.runtime.result_helpers"
        )
        fn = getattr(result_helpers, sym)
        assert callable(fn), f"{sym} is not callable"
        assert fn.__module__ == "rush.runtime.result_helpers", (
            f"{sym} not defined in rush.runtime.result_helpers"
        )


def test_common_is_compatibility_reexport_without_duplicate_definitions() -> None:
    """T-60.16: common.py is a pure compatibility re-export facade with zero duplicate definitions."""
    import ast
    from pathlib import Path

    import rush.runtime.binaries
    import rush.runtime.result_helpers
    import rush.runtime.subprocesses
    import rush.tools.common

    common_file = Path(rush.tools.common.__file__).resolve()
    tree = ast.parse(common_file.read_text(encoding="utf-8"))

    for node in ast.walk(tree):
        assert not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)), (
            f"Found forbidden function definition '{node.name}' in rush.tools.common"
        )
        assert not isinstance(node, ast.ClassDef), (
            f"Found forbidden class definition '{node.name}' in rush.tools.common"
        )

    assert rush.tools.common.resolve_binary is rush.runtime.binaries.resolve_binary
    assert rush.tools.common.run_subprocess is rush.runtime.subprocesses.run_subprocess
    assert rush.tools.common.run_engine is rush.runtime.subprocesses.run_engine
    assert (
        rush.tools.common.skipped_result is rush.runtime.result_helpers.skipped_result
    )
    assert rush.tools.common.error_result is rush.runtime.result_helpers.error_result
    assert rush.tools.common.exit_code_for is rush.runtime.result_helpers.exit_code_for
