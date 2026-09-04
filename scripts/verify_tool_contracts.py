"""Mechanical verification of tool contracts, AST invariant enforcement, and zero-stub policies.

Bans:
- Returning or assigning placeholder strings ("unknown", "deferred") in tool results or metrics.
- Permissive test assertions (e.g. assert x == "unknown", assert status in ("ok", "warn", "skipped")).
- Fake fallback injection (e.g. 'if not all_actions: all_actions = ...').
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

BANNED_STRINGS = {"unknown", "deferred"}


class ASTContractVisitor(ast.NodeVisitor):
    def __init__(self, filename: str, is_test: bool = False):
        self.filename = filename
        self.is_test = is_test
        self.errors: list[str] = []

    def visit_Constant(self, node: ast.Constant) -> None:
        if isinstance(node.value, str):
            val_lower = node.value.strip().lower()
            if val_lower in BANNED_STRINGS and not self.is_test:
                self.errors.append(
                    f"{self.filename}:{node.lineno}: Banned placeholder string '{node.value}' found in production code."
                )
        self.generic_visit(node)

    def visit_Assert(self, node: ast.Assert) -> None:
        # Check assertions for tautological / placeholder testing
        test = node.test
        if isinstance(test, ast.Compare):
            # Check for: assert x == "unknown" or assert "unknown" == x
            for comparator in test.comparators:
                if (
                    isinstance(comparator, ast.Constant)
                    and str(comparator.value).lower() in BANNED_STRINGS
                ):
                    self.errors.append(
                        f"{self.filename}:{node.lineno}: Banned tautological assertion testing for '{comparator.value}'."
                    )
            if (
                isinstance(test.left, ast.Constant)
                and str(test.left.value).lower() in BANNED_STRINGS
            ):
                self.errors.append(
                    f"{self.filename}:{node.lineno}: Banned tautological assertion testing for '{test.left.value}'."
                )

            # Check for permissive membership: assert status in ("ok", "warn", "skipped")
            for op, comparator in zip(test.ops, test.comparators):
                if isinstance(op, ast.In) and isinstance(
                    comparator, (ast.Tuple, ast.List, ast.Set)
                ):
                    values = {
                        elt.value
                        for elt in comparator.elts
                        if isinstance(elt, ast.Constant) and isinstance(elt.value, str)
                    }
                    if {"ok", "warn", "skipped"}.issubset(values) or {
                        "ok",
                        "warn",
                    }.issubset(values):
                        self.errors.append(
                            f"{self.filename}:{node.lineno}: Permissive assertion allows any status ({values}); must assert exact deterministic status."
                        )
        self.generic_visit(node)

    def visit_If(self, node: ast.If) -> None:
        # Check for fake fallback injection like: if not all_actions: all_actions = {...}
        if isinstance(node.test, ast.UnaryOp) and isinstance(node.test.op, ast.Not):
            operand = node.test.operand
            if isinstance(operand, ast.Name):
                for stmt in node.body:
                    if isinstance(stmt, ast.Assign):
                        for target in stmt.targets:
                            if isinstance(target, ast.Name) and target.id == operand.id:
                                self.errors.append(
                                    f"{self.filename}:{stmt.lineno}: Fake fallback injection detected for variable '{operand.id}'."
                                )
        self.generic_visit(node)


def verify_source(
    source: str, filename: str = "<test>", is_test: bool = False
) -> list[str]:
    try:
        tree = ast.parse(source, filename=filename)
    except SyntaxError as e:
        return [f"{filename}:{e.lineno}: Syntax error parsing AST: {e.msg}"]
    visitor = ASTContractVisitor(filename, is_test=is_test)
    visitor.visit(tree)
    return visitor.errors


def verify_file(path: Path, is_test: bool) -> list[str]:
    try:
        source = path.read_text(encoding="utf-8")
    except OSError as e:
        return [f"{path}: Failed to read file: {e}"]
    return verify_source(source, filename=str(path), is_test=is_test)


def main() -> int:
    repo_root = Path(__file__).resolve().parent.parent
    tools_dir = repo_root / "src" / "rush" / "tools"
    tests_dir = repo_root / "tests"

    args = sys.argv[1:]
    phase50_only = "--phase50" in args

    phase50_tools = {
        "license_matrix.py",
        "iam_audit.py",
        "provenance_ai.py",
        "dead_asset.py",
        "pr_synthesize.py",
        "attest.py",
        "offline_runner.py",
        "mem_profile.py",
        "cold_start.py",
        "benchmark.py",
    }
    phase50_tests = {
        "test_license_matrix.py",
        "test_iam_audit.py",
        "test_provenance_ai.py",
        "test_dead_asset.py",
        "test_pr_synthesize.py",
        "test_phase50b_integration.py",
        "test_attest.py",
        "test_offline_runner.py",
        "test_mem_profile.py",
        "test_cold_start.py",
        "test_benchmark.py",
        "test_phase50c_integration.py",
        "test_phase50_slsa_attestation.py",
    }

    errors: list[str] = []

    if args and not phase50_only:
        for arg in args:
            p = Path(arg)
            if p.is_file():
                is_test = "test" in p.name
                errors.extend(verify_file(p, is_test=is_test))
    else:
        # Check tools
        for py_file in sorted(tools_dir.glob("*.py")):
            if py_file.name == "schemas.py":
                continue
            if phase50_only and py_file.name not in phase50_tools:
                continue
            errors.extend(verify_file(py_file, is_test=False))

        # Check tests
        for py_file in sorted(tests_dir.glob("*.py")):
            if phase50_only and py_file.name not in phase50_tests:
                continue
            errors.extend(verify_file(py_file, is_test=True))

    if errors:
        print("=" * 70, file=sys.stderr)
        print(
            f"FAILED: {len(errors)} contract / spec-integrity violations found:",
            file=sys.stderr,
        )
        print("=" * 70, file=sys.stderr)
        for err in errors:
            print(f"  - {err}", file=sys.stderr)
        print("=" * 70, file=sys.stderr)
        return 1

    print("SUCCESS: All tool contracts and tests adhere to zero-stub invariant.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
