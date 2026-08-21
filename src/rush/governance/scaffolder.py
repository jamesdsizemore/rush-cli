"""Repository governance scaffolder."""

from __future__ import annotations

from pathlib import Path


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
            agents_file.write_text(DEFAULT_AGENTS_MD, encoding="utf-8")
            created.append(agents_file)

        rush_toml = repo_root / "rush.toml"
        if not rush_toml.exists():
            rush_toml.write_text('[rush]\nversion = "0.2.0"\n', encoding="utf-8")
            created.append(rush_toml)

        return created
