"""Repository governance scaffolder."""

from __future__ import annotations

from pathlib import Path

from rush import __version__

DEFAULT_AGENTS_MD = """# Agent Governance & Repository Instructions

## Operational Invariants
- Python 3.12 managed with uv.
- All CLI and MCP tool commands share unified implementations.
- No destructive commands (e.g., rm -rf, drop table, hard resets).
- Test-driven development is strictly required for all changes.
"""


class RepoScaffolder:
    """Initializes new repositories with canonical AI governance files."""

    @staticmethod
    def init_repository(repo_root: Path) -> list[Path]:
        created = []
        agents_file = repo_root / "AGENTS.md"
        if not agents_file.exists():
            from rush.safety.redactor import sanitize_value

            agents_file.write_text(
                sanitize_value(DEFAULT_AGENTS_MD).value, encoding="utf-8"
            )
            created.append(agents_file)

        rush_toml = repo_root / "rush.toml"
        if not rush_toml.exists():
            from rush.safety.redactor import sanitize_value

            rush_toml.write_text(
                sanitize_value(f'[rush]\nversion = "{__version__}"\n').value,
                encoding="utf-8",
            )
            created.append(rush_toml)

        return created
