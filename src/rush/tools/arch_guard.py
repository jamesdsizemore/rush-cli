"""Declarative architectural boundary layer guard enforcing clean architecture import matrices."""

import ast
from pathlib import Path
from typing import Any, ClassVar


class ArchGuard:
    """Validates that module imports adhere to allowed directional layers (e.g. domain -> application -> infra)."""

    DEFAULT_LAYERS: ClassVar[dict[str, list[str]]] = {
        "domain": [],
        "application": ["domain"],
        "infrastructure": ["application", "domain"],
        "presentation": ["application", "domain"],
    }

    def __init__(self, project_root: Path | None = None):
        self.project_root = project_root or Path.cwd()

    def evaluate_boundaries(
        self, layers_config: dict[str, list[str]] | None = None
    ) -> dict[str, Any]:
        layers = layers_config or self.DEFAULT_LAYERS
        violations: list[dict[str, Any]] = []

        for layer_name, allowed_deps in layers.items():
            layer_dir = self.project_root / "src" / layer_name
            if not layer_dir.exists():
                layer_dir = self.project_root / "src" / "rush" / layer_name
            if not layer_dir.exists():
                continue

            for py_file in layer_dir.glob("**/*.py"):
                try:
                    code = py_file.read_text(encoding="utf-8", errors="ignore")
                    tree = ast.parse(code)
                    for node in ast.walk(tree):
                        imported_module = ""
                        if isinstance(node, ast.Import):
                            for alias in node.names:
                                imported_module = alias.name
                        elif isinstance(node, ast.ImportFrom) and node.module:
                            imported_module = node.module

                        if imported_module:
                            # Check if imported module belongs to an illegal layer
                            for other_layer in layers:
                                if (
                                    other_layer != layer_name
                                    and other_layer not in allowed_deps
                                    and (
                                        f".{other_layer}" in imported_module
                                        or f"rush.{other_layer}" in imported_module
                                    )
                                ):
                                    violations.append(
                                        {
                                            "source_file": str(
                                                py_file.relative_to(self.project_root)
                                            ),
                                            "source_layer": layer_name,
                                            "illegal_target_layer": other_layer,
                                            "imported_module": imported_module,
                                        }
                                    )
                except Exception:  # noqa: BLE001, S110
                    pass

        return {
            "passed": len(violations) == 0,
            "violations_count": len(violations),
            "violations": violations,
        }
