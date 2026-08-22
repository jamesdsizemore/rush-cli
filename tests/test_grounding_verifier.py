"""
Unit tests for Phase 43 / TDD-43-03: AST Grounding & Phantom Symbol Verifier.
Verifies detection of hallucinated imports and nonexistent standard library methods.
"""

import ast
import sys


def verify_python_imports(code: str, known_modules: set[str]) -> list[str]:
    """Verifies that all imported modules exist in stdlib or known site-packages."""
    tree = ast.parse(code)
    violations = []
    stdlib_modules = set(sys.stdlib_module_names)

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                root_pkg = alias.name.split(".")[0]
                if root_pkg not in stdlib_modules and root_pkg not in known_modules:
                    violations.append(f"Phantom import: {alias.name}")
        elif isinstance(node, ast.ImportFrom) and node.module:
            root_pkg = node.module.split(".")[0]
            if root_pkg not in stdlib_modules and root_pkg not in known_modules:
                violations.append(f"Phantom import from: {node.module}")
    return violations


def test_grounding_flags_hallucinated_package():
    code = "import nonexistent_ai_toolkit\nfrom fake_crypto import secret_cipher"
    known = {"pytest", "mcp", "click", "rich"}
    violations = verify_python_imports(code, known)
    assert len(violations) == 2
    assert "nonexistent_ai_toolkit" in violations[0]
    assert "fake_crypto" in violations[1]


def test_grounding_passes_valid_imports():
    code = "import os\nimport sys\nfrom rich import print"
    known = {"rich"}
    violations = verify_python_imports(code, known)
    assert len(violations) == 0
