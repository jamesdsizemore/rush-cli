"""Algebraic type narrowing and runtime type guard synthesizer."""

import ast
from pathlib import Path
from typing import Any

_GUARD_TYPES = {
    "int": int,
    "str": str,
    "float": float,
    "bool": bool,
    "dict": dict,
    "list": list,
    "tuple": tuple,
    "bytes": bytes,
}


class TypeSynthesizer:
    """Inspect signatures and emit only statically supported guards."""

    def __init__(self, project_root: Path | None = None):
        self.project_root = project_root or Path.cwd()

    def audit_and_synthesize(self, file_path: Path) -> dict[str, Any]:
        if not file_path.exists():
            return {"error": f"File not found: {file_path}"}

        code = file_path.read_text(encoding="utf-8", errors="ignore")
        tree = ast.parse(code)
        shadowed = self._bound_names(tree)

        untyped_args: list[dict[str, Any]] = []
        findings: list[dict[str, Any]] = []
        guards: dict[str, dict[str, str]] = {}
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                args = [*node.args.posonlyargs, *node.args.args, *node.args.kwonlyargs]
                if node.args.vararg:
                    args.append(node.args.vararg)
                if node.args.kwarg:
                    args.append(node.args.kwarg)
                fn_guards: dict[str, str] = {}
                for arg in args:
                    if arg.arg in {"self", "cls"}:
                        continue
                    annotation = ast.unparse(arg.annotation) if arg.annotation else None
                    constraint = self._constraint(node, arg.arg, annotation, shadowed)
                    guard = None
                    if (
                        annotation in _GUARD_TYPES
                        and annotation not in shadowed
                        and not {"isinstance", "all"} & shadowed
                    ):
                        runtime_type = (
                            "(int, float)" if annotation == "float" else annotation
                        )
                        if arg is node.args.vararg:
                            guard = f"assert all(isinstance(item, {runtime_type}) for item in {arg.arg}), 'Expected {annotation} items'"
                        elif arg is node.args.kwarg:
                            guard = f"assert all(isinstance(item, {runtime_type}) for item in {arg.arg}.values()), 'Expected {annotation} values'"
                        else:
                            guard = f"assert isinstance({arg.arg}, {runtime_type}), 'Expected {annotation} for {arg.arg}'"
                        fn_guards[arg.arg] = guard
                    if constraint == "conflicting constraints":
                        findings.append(
                            {
                                "function": node.name,
                                "line": node.lineno,
                                "argument": arg.arg,
                                "reason": "conflicting constraints; no arbitrary guard synthesized",
                                "suggested_guard": None,
                            }
                        )
                        fn_guards.pop(arg.arg, None)
                    if arg.annotation is None:
                        item = {
                            "function": node.name,
                            "argument": arg.arg,
                            "line": arg.lineno,
                            "suggested_guard": guard,
                        }
                        if constraint:
                            item["constraint"] = constraint
                        untyped_args.append(item)
                if fn_guards:
                    guards[node.name] = fn_guards

        return {
            "file": str(
                file_path.relative_to(self.project_root)
                if file_path.is_relative_to(self.project_root)
                else file_path
            ),
            "untyped_count": len(untyped_args),
            "untyped_arguments": untyped_args,
            "findings": findings,
            "guards": guards,
        }

    @staticmethod
    def _bound_names(tree: ast.AST) -> set[str]:
        names: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
                names.add(node.id)
            elif isinstance(
                node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
            ):
                names.add(node.name)
            elif isinstance(node, ast.arg):
                names.add(node.arg)
            elif isinstance(node, ast.alias):
                names.add(node.asname or node.name.split(".")[0])
        return names

    @staticmethod
    def _constraint(
        function: ast.FunctionDef | ast.AsyncFunctionDef,
        name: str,
        annotation: str | None = None,
        shadowed: set[str] | None = None,
    ) -> str | None:
        shadowed = shadowed or set()
        if annotation in shadowed:
            annotation = None
        found_sum = False
        asserted_types: set[str] = set()
        arithmetic: set[str] = set()
        pending = list(function.body)
        while pending:
            child = pending.pop()
            if isinstance(
                child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda)
            ):
                continue
            pending.extend(ast.iter_child_nodes(child))
            if (
                isinstance(child, ast.Call)
                and isinstance(child.func, ast.Name)
                and child.func.id == "sum"
                and "sum" not in shadowed
                and child.args
                and isinstance(child.args[0], ast.Name)
                and child.args[0].id == name
            ):
                found_sum = True
            if isinstance(child, ast.Assert):
                test = child.test
                if (
                    isinstance(test, ast.Call)
                    and isinstance(test.func, ast.Name)
                    and test.func.id == "isinstance"
                    and "isinstance" not in shadowed
                    and len(test.args) == 2
                    and isinstance(test.args[0], ast.Name)
                    and test.args[0].id == name
                    and isinstance(test.args[1], ast.Name)
                    and test.args[1].id not in shadowed
                    and test.args[1].id
                    in {"int", "str", "float", "bool", "dict", "list", "tuple", "bytes"}
                ):
                    asserted_types.add(test.args[1].id)
            if isinstance(child, ast.BinOp):
                for operand, other in (
                    (child.left, child.right),
                    (child.right, child.left),
                ):
                    if not TypeSynthesizer._uses_operand(operand, name):
                        continue
                    if isinstance(other, ast.Constant):
                        if isinstance(child.op, ast.Add) and isinstance(
                            other.value, str
                        ):
                            arithmetic.add("string")
                        elif isinstance(
                            child.op, (ast.Add, ast.Sub, ast.Div, ast.FloorDiv, ast.Pow)
                        ) and isinstance(other.value, (int, float, complex)):
                            arithmetic.add("numeric")
        if (
            len(arithmetic) > 1
            or ("string" in arithmetic and annotation in {"int", "float", "bool"})
            or (
                "numeric" in arithmetic
                and annotation in {"str", "bytes", "dict", "list", "tuple"}
            )
        ):
            return "conflicting constraints"
        if asserted_types:
            compatible = set(_GUARD_TYPES.values())
            for required in asserted_types:
                compatible = {
                    kind
                    for kind in compatible
                    if issubclass(kind, _GUARD_TYPES[required])
                }
            if annotation in _GUARD_TYPES:
                expected = (
                    (int, float) if annotation == "float" else _GUARD_TYPES[annotation]
                )
                compatible = {kind for kind in compatible if issubclass(kind, expected)}
            if not compatible:
                return "conflicting constraints"
        if found_sum:
            return "unresolved numeric-iterable constraint"
        if arithmetic:
            return f"unresolved {next(iter(arithmetic))} operation constraint"
        return None

    @staticmethod
    def _uses_operand(node: ast.AST, name: str) -> bool:
        if isinstance(node, ast.Name):
            return node.id == name
        if isinstance(node, ast.BinOp):
            return TypeSynthesizer._uses_operand(
                node.left, name
            ) or TypeSynthesizer._uses_operand(node.right, name)
        return False
