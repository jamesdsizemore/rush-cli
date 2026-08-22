"""AST Import and Symbol Grounding Verifier checking package existence and preventing hallucinations."""

import ast
import importlib.metadata
import sys
from pathlib import Path


class GroundingVerifier:
    """Verifies that imports in AST trees exist in standard library or installed distribution packages."""

    def __init__(self, project_root: Path | None = None):
        self.project_root = project_root or Path.cwd()
        self.stdlib_modules = set(sys.stdlib_module_names)
        self._installed_pkgs: set[str] | None = None

    @property
    def installed_packages(self) -> set[str]:
        if self._installed_pkgs is None:
            pkgs = set()
            for dist in importlib.metadata.distributions():
                pkgs.add(dist.metadata["Name"].lower().replace("-", "_"))
                if dist.files:
                    for f in dist.files:
                        top = str(f).split("/")[0].split("\\")[0]
                        if top.endswith(".py"):
                            pkgs.add(top[:-3].lower())
                        elif not top.endswith((".dist-info", ".egg-info")):
                            pkgs.add(top.lower())
            self._installed_pkgs = pkgs
        return self._installed_pkgs

    def verify_code(self, code: str) -> list[str]:
        violations: list[str] = []
        try:
            tree = ast.parse(code)
        except Exception as e:  # noqa: BLE001
            return [f"Syntax error: {e}"]

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    root_pkg = alias.name.split(".")[0].lower()
                    if (
                        root_pkg not in self.stdlib_modules
                        and root_pkg not in self.installed_packages
                        and root_pkg != "rush"
                    ):
                        violations.append(
                            f"Phantom import: '{alias.name}' (root package '{root_pkg}' not installed or in stdlib)"
                        )
            elif isinstance(node, ast.ImportFrom) and node.module:
                root_pkg = node.module.split(".")[0].lower()
                if (
                    root_pkg not in self.stdlib_modules
                    and root_pkg not in self.installed_packages
                    and root_pkg != "rush"
                ):
                    violations.append(
                        f"Phantom import: '{node.module}' (root package '{root_pkg}' not installed or in stdlib)"
                    )

        return violations
