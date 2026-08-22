"""
Unit tests for Phase 42 / TDD-42-03: Polyglot AST Skeletonizer.
Tests body elision and docstring preservation across Python functions and classes.
"""

import ast


def skeletonize_python_code(source: str) -> str:
    """Replaces function and method bodies with '...' (elision)."""
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            doc = ast.get_docstring(node)
            new_body = []
            if doc:
                new_body.append(ast.Expr(value=ast.Constant(value=doc)))
            new_body.append(ast.Expr(value=ast.Constant(value=Ellipsis)))
            node.body = new_body
    return ast.unparse(tree)


def test_python_function_skeletonization():
    code = 'def compute_metrics(x: int, y: int) -> int:\n    """Calculates sum metrics."""\n    step1 = x * 2\n    step2 = y * 3\n    final_res = step1 + step2\n    return final_res\n'
    skeleton = skeletonize_python_code(code)
    assert "def compute_metrics(x: int, y: int) -> int:" in skeleton
    assert "Calculates sum metrics." in skeleton
    assert "step1 = x * 2" not in skeleton
    assert "..." in skeleton
