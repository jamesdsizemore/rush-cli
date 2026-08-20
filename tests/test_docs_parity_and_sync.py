"""Automated regression and parity test suite for the /docs tree.

Enforces that:
1. Every tool in TOOL_SPECS is documented in all catalog, CLI, MCP, and configuration docs.
2. Every engine in ENGINES & ENGINE_SPECS is documented in compatibility and directory docs.
3. Every internal relative markdown link across all /docs files resolves to an existing file.
4. Tool counts and schema numbers match the codebase exactly.
"""

from __future__ import annotations

from pathlib import Path

from scripts.sync_docs import (
    audit_cli_reference,
    audit_doc_links,
    audit_engine_compatibility,
    audit_engines_directory,
    audit_mcp_reference,
    audit_tool_catalog,
)

DOCS_DIR = Path(__file__).resolve().parent.parent / "docs"


def test_docs_tool_catalog_parity() -> None:
    """Every registered tool and tool count must be documented in TOOL_CATALOG.md."""
    errors = audit_tool_catalog(DOCS_DIR)
    assert not errors, f"TOOL_CATALOG.md parity errors: {errors}"


def test_docs_engine_compatibility_parity() -> None:
    """Every registered engine adapter must be present in ENGINE_COMPATIBILITY.md."""
    errors = audit_engine_compatibility(DOCS_DIR)
    assert not errors, f"ENGINE_COMPATIBILITY.md parity errors: {errors}"


def test_docs_cli_reference_parity() -> None:
    """Every registered tool must be documented in CLI_REFERENCE.md and reference/cli-reference.md."""
    errors = audit_cli_reference(DOCS_DIR)
    assert not errors, f"CLI reference parity errors: {errors}"


def test_docs_mcp_reference_parity() -> None:
    """Every FastMCP tool mapping must be documented in MCP_REFERENCE.md and reference/mcp-tool-reference.md."""
    errors = audit_mcp_reference(DOCS_DIR)
    assert not errors, f"MCP reference parity errors: {errors}"


def test_docs_engine_directory_parity() -> None:
    """Every engine in ENGINES must be documented in ENGINES.md and reference/engine-directory.md."""
    errors = audit_engines_directory(DOCS_DIR)
    assert not errors, f"Engine directory parity errors: {errors}"


def test_docs_internal_links_resolve() -> None:
    """Every relative markdown link across the entire /docs tree must resolve to an existing file."""
    errors = audit_doc_links(DOCS_DIR)
    assert not errors, "Broken documentation links found:\n" + "\n".join(errors)
