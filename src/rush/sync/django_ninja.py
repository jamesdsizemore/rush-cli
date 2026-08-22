"""Django Ninja static route and controller AST extractor."""

from __future__ import annotations

import ast
from dataclasses import dataclass


@dataclass(frozen=True)
class DjangoNinjaEndpoint:
    http_method: str
    path: str
    handler_name: str


class DjangoNinjaAstExtractor:
    """Extracts Django Ninja API router endpoints without importing Django runtime."""

    @staticmethod
    def extract_ninja_routes(source_code: str) -> list[DjangoNinjaEndpoint]:
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
                        method = decorator.func.attr.lower()
                        if method in {"get", "post", "put", "delete", "patch"}:
                            route = "/"
                            if decorator.args and isinstance(
                                decorator.args[0], ast.Constant
                            ):
                                route = str(decorator.args[0].value)
                            endpoints.append(
                                DjangoNinjaEndpoint(
                                    http_method=method.upper(),
                                    path=route,
                                    handler_name=node.name,
                                )
                            )
        return endpoints
