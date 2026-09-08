"""Zero-server Public API signature diff & breaking change contract detector."""

import ast
from pathlib import Path
from typing import Any

from .common import run_subprocess


class ApiDiffer:
    """Compares AST public functions/classes across Git revisions to flag breaking API changes."""

    def __init__(self, project_root: Path | None = None):
        self.project_root = project_root or Path.cwd()

    def _extract_public_signatures(self, code: str) -> dict[str, list[str]]:
        signatures: dict[str, list[str]] = {}
        try:
            tree = ast.parse(code)
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    if not node.name.startswith("_"):
                        params = [arg.arg for arg in node.args.args]
                        signatures[node.name] = params
                elif isinstance(node, ast.ClassDef) and not node.name.startswith("_"):
                    for item in node.body:
                        if isinstance(
                            item, (ast.FunctionDef, ast.AsyncFunctionDef)
                        ) and not item.name.startswith("_"):
                            params = [arg.arg for arg in item.args.args]
                            signatures[f"{node.name}.{item.name}"] = params
        except Exception:  # noqa: BLE001, S110
            pass
        return signatures

    def diff_file(
        self, file_path: Path, base_ref: str = "main"
    ) -> list[dict[str, Any]]:
        rel_path = str(
            file_path.relative_to(self.project_root)
            if file_path.is_relative_to(self.project_root)
            else file_path
        ).replace("\\", "/")

        # Get base version from git
        res = run_subprocess(
            ["git", "show", f"{base_ref}:{rel_path}"], cwd=self.project_root
        )
        if res.returncode != 0 or not res.stdout:
            return []  # New file, no breaking changes against base

        old_sigs = self._extract_public_signatures(res.stdout)
        new_code = file_path.read_text(encoding="utf-8", errors="ignore")
        new_sigs = self._extract_public_signatures(new_code)

        breaking: list[dict[str, Any]] = []
        for sym_name, old_params in old_sigs.items():
            if sym_name not in new_sigs:
                breaking.append(
                    {
                        "symbol": sym_name,
                        "type": "REMOVED_SYMBOL",
                        "details": f"Public symbol '{sym_name}' was removed.",
                    }
                )
            else:
                new_params = new_sigs[sym_name]
                removed = set(old_params) - set(new_params)
                if removed:
                    breaking.append(
                        {
                            "symbol": sym_name,
                            "type": "REMOVED_PARAMETERS",
                            "details": f"Parameters {sorted(removed)} removed from '{sym_name}'.",
                        }
                    )

        return breaking

    def diff_symbol(
        self, file_path: Path, symbol: str, base_ref: str = "main"
    ) -> dict[str, Any] | str | None:
        """Per-symbol wrapper around `diff_file()`'s comparison logic (§6.5 Invariant 5).

        Returns the breaking-change dict for `symbol` if broken, `None` if not broken
        (including when the file/symbol is genuinely new at `base_ref`), or the string
        `"unknown"` when `base_ref` (or the file at `base_ref`) is unavailable for any
        other git reason (missing branch, detached HEAD, shallow clone) — callers must
        never treat `"unknown"` as evidence the symbol is fresh.
        """
        rel_path = str(
            file_path.relative_to(self.project_root)
            if file_path.is_relative_to(self.project_root)
            else file_path
        ).replace("\\", "/")

        res = run_subprocess(
            ["git", "show", f"{base_ref}:{rel_path}"], cwd=self.project_root
        )
        if res.returncode != 0 or not res.stdout:
            stderr = (res.stderr or "").lower()
            if "does not exist in" in stderr or "exists on disk, but not in" in stderr:
                old_sigs: dict[str, list[str]] = {}
            else:
                return "unknown"
        else:
            old_sigs = self._extract_public_signatures(res.stdout)

        if symbol not in old_sigs:
            return None

        new_code = file_path.read_text(encoding="utf-8", errors="ignore")
        new_sigs = self._extract_public_signatures(new_code)

        if symbol not in new_sigs:
            return {
                "symbol": symbol,
                "type": "REMOVED_SYMBOL",
                "details": f"Public symbol '{symbol}' was removed.",
            }

        removed = set(old_sigs[symbol]) - set(new_sigs[symbol])
        if removed:
            return {
                "symbol": symbol,
                "type": "REMOVED_PARAMETERS",
                "details": f"Parameters {sorted(removed)} removed from '{symbol}'.",
            }
        return None

    def diff_public_api(self, base_ref: str = "main") -> dict[str, Any]:
        all_breaking: list[dict[str, Any]] = []
        for py_file in (self.project_root / "src").glob("**/*.py"):
            breaking = self.diff_file(py_file, base_ref=base_ref)
            for b in breaking:
                b["file"] = str(py_file.relative_to(self.project_root))
                all_breaking.append(b)

        return {
            "base_ref": base_ref,
            "passed": len(all_breaking) == 0,
            "breaking_changes_count": len(all_breaking),
            "breaking_changes": all_breaking,
        }
