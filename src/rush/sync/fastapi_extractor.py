"""Static AST route extractor for FastAPI applications without runtime imports."""

from __future__ import annotations

import ast
from dataclasses import dataclass
from typing import ClassVar


@dataclass(frozen=True)
class DiscoveredEndpoint:
    http_method: str
    path: str
    function_name: str
    line_number: int


class FastApiAstExtractor:
    """Extracts FastAPI route signatures statically using the Python AST."""

    HTTP_METHODS: ClassVar[set[str]] = {
        "get",
        "post",
        "put",
        "delete",
        "patch",
        "options",
        "head",
    }

    @staticmethod
    def extract_endpoints_from_source(source_code: str) -> list[DiscoveredEndpoint]:
        try:
            tree = ast.parse(source_code)
        except SyntaxError:
            return []

        endpoints = []

        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                for decorator in node.decorator_list:
                    if isinstance(decorator, ast.Call) and isinstance(
                        decorator.func, ast.Attribute
                    ):
                        method_candidate = decorator.func.attr.lower()
                        if method_candidate in FastApiAstExtractor.HTTP_METHODS:
                            route_path = "/"
                            if decorator.args and isinstance(
                                decorator.args[0], ast.Constant
                            ):
                                route_path = str(decorator.args[0].value)
                            endpoints.append(
                                DiscoveredEndpoint(
                                    http_method=method_candidate.upper(),
                                    path=route_path,
                                    function_name=node.name,
                                    line_number=node.lineno,
                                )
                            )

        return endpoints
