"""Immutable governance rulebook and protected path firewall."""

from __future__ import annotations

from pathlib import Path

PROTECTED_GOVERNANCE_FILES = {
    "AGENTS.md",
    "CLAUDE.md",
    ".cursorrules",
    ".windsurfrules",
    "rush.toml",
    ".rush/trust.json",
    ".rush/hooks.json",
    "SECURITY.md",
}


class AgentSafetyGuard:
    """Blocks autonomous AI coding agents from modifying protected governance files."""

    def __init__(self, repo_root: Path) -> None:
        self.repo_root = repo_root.resolve()

    def is_file_protected(self, target_path: Path | str) -> bool:
        if isinstance(target_path, str):
            path_str = target_path.replace("\\", "/")
        else:
            try:
                rel = target_path.resolve().relative_to(self.repo_root)
                path_str = rel.as_posix()
            except ValueError:
                return True

        if path_str in PROTECTED_GOVERNANCE_FILES:
            return True

        return bool(path_str.startswith(".git/"))

    def validate_write_target(self, target_path: Path | str) -> None:
        if self.is_file_protected(target_path):
            raise PermissionError(
                f"Agent mutation blocked: '{target_path}' is an immutable governance file."
            )
