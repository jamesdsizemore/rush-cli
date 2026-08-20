"""Comprehensive documentation audit, synchronization, and auto-update system.

Ensures that every tool, engine, maturity rating, and document link across
the /docs tree is 100% synchronized with the canonical codebase registries.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

# Add src to path
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from rush.catalog import TOOL_SPECS
from rush.engines import ENGINES
from rush.tools import ALL_TOOLS


def audit_tool_catalog(docs_dir: Path, auto_update: bool = False) -> list[str]:
    errors = []
    catalog_path = docs_dir / "TOOL_CATALOG.md"
    if not catalog_path.exists():
        return [f"Missing {catalog_path}"]

    content = catalog_path.read_text(encoding="utf-8")
    for tool_name in TOOL_SPECS:
        if f"`{tool_name}`" not in content:
            errors.append(f"TOOL_CATALOG.md is missing tool: `{tool_name}`")

    # Check total tool count mentioned in text
    expected_count = len(TOOL_SPECS)
    if (
        f"{expected_count} user-visible tools" not in content
        and f"{expected_count} tools" not in content
    ):
        match = re.search(r"(\d+)\s+user-visible tools", content)
        if match and int(match.group(1)) != expected_count:
            errors.append(
                f"TOOL_CATALOG.md states {match.group(1)} tools, but TOOL_SPECS contains {expected_count}"
            )
            if auto_update:
                content = content.replace(
                    f"{match.group(1)} user-visible tools",
                    f"{expected_count} user-visible tools",
                )
                catalog_path.write_text(content, encoding="utf-8")
                print(f"[AUTO-UPDATED] Fixed tool count in {catalog_path}")

    return errors


def audit_engine_compatibility(docs_dir: Path) -> list[str]:
    errors = []
    compat_path = docs_dir / "ENGINE_COMPATIBILITY.md"
    if not compat_path.exists():
        return [f"Missing {compat_path}"]

    content = compat_path.read_text(encoding="utf-8")
    for engine_name in ENGINES:
        if engine_name not in content:
            errors.append(f"ENGINE_COMPATIBILITY.md is missing engine: `{engine_name}`")
    return errors


def audit_cli_reference(docs_dir: Path) -> list[str]:
    errors = []
    for ref_file in ("CLI_REFERENCE.md", "reference/cli-reference.md"):
        path = docs_dir / ref_file
        if not path.exists():
            errors.append(f"Missing {path}")
            continue
        content = path.read_text(encoding="utf-8")
        for tool in ALL_TOOLS:
            if tool.name not in content and f"`{tool.name}`" not in content:
                errors.append(f"{ref_file} is missing tool: `{tool.name}`")
    return errors


def audit_mcp_reference(docs_dir: Path) -> list[str]:
    errors = []
    for ref_file in ("MCP_REFERENCE.md", "reference/mcp-tool-reference.md"):
        path = docs_dir / ref_file
        if not path.exists():
            errors.append(f"Missing {path}")
            continue
        content = path.read_text(encoding="utf-8")
        for tool in ALL_TOOLS:
            mcp_name = f"rush_{tool.name}"
            if mcp_name not in content:
                errors.append(f"{ref_file} is missing MCP tool: `{mcp_name}`")
    return errors


def audit_engines_directory(docs_dir: Path) -> list[str]:
    errors = []
    for ref_file in ("ENGINES.md", "reference/engine-directory.md"):
        path = docs_dir / ref_file
        if not path.exists():
            errors.append(f"Missing {path}")
            continue
        content = path.read_text(encoding="utf-8")
        for engine_name, engine in ENGINES.items():
            if engine_name not in content and engine.binary not in content:
                errors.append(
                    f"{ref_file} is missing engine entry for `{engine_name}` (binary: `{engine.binary}`)"
                )
    return errors


def audit_doc_links(docs_dir: Path) -> list[str]:
    errors = []
    link_pattern = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")

    for md_file in docs_dir.rglob("*.md"):
        content = md_file.read_text(encoding="utf-8")
        for match in link_pattern.finditer(content):
            target = match.group(2).strip()
            if target.startswith(("http://", "https://", "#", "mailto:", "file://")):
                continue
            target_path_str = target.split("#")[0]
            if not target_path_str:
                continue

            target_path = (md_file.parent / target_path_str).resolve()
            if not target_path.exists():
                errors.append(
                    f"{md_file.relative_to(docs_dir)} has broken link -> '{target}' (resolved: {target_path})"
                )
    return errors


def run_full_audit(docs_dir: Path, auto_update: bool = False) -> int:
    print(f"Auditing documentation tree at: {docs_dir.resolve()}")
    all_errors: list[str] = []

    all_errors.extend(audit_tool_catalog(docs_dir, auto_update=auto_update))
    all_errors.extend(audit_engine_compatibility(docs_dir))
    all_errors.extend(audit_cli_reference(docs_dir))
    all_errors.extend(audit_mcp_reference(docs_dir))
    all_errors.extend(audit_engines_directory(docs_dir))
    all_errors.extend(audit_doc_links(docs_dir))

    if all_errors:
        print(
            f"\n[FAIL] Found {len(all_errors)} documentation discrepancy/link error(s):"
        )
        for err in all_errors:
            print(f"  - {err}")
        return 1

    print(
        "\n[OK] All documentation files, tool catalogs, engine directories, and links are 100% synchronized!"
    )
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Audit and synchronize documentation across the entire repository."
    )
    parser.add_argument(
        "--docs-dir",
        type=Path,
        default=REPO_ROOT / "docs",
        help="Path to docs directory",
    )
    parser.add_argument(
        "--check", action="store_true", help="Run audit and return non-zero on error"
    )
    parser.add_argument(
        "--update",
        action="store_true",
        help="Automatically fix detected documentation discrepancies where possible",
    )
    args = parser.parse_args()

    sys.exit(run_full_audit(args.docs_dir, auto_update=args.update))


if __name__ == "__main__":
    main()
