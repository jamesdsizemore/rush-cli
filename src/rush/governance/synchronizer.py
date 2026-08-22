"""AGENTS.md multi-IDE rule file compiler."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

IDE_TARGETS = {
    ".cursorrules": "Cursor IDE Rule File",
    ".windsurfrules": "Windsurf IDE Rule File",
    ".clinerules": "Cline / Roo-Code Rule File",
    ".github/copilot-instructions.md": "GitHub Copilot Instructions",
    ".gemini/antigravity/rules.md": "Antigravity CLI Rules",
}


@dataclass(frozen=True)
class SyncResult:
    target_path: str
    action: str
    sha256: str


class AgentsMdSynchronizer:
    """Compiles canonical AGENTS.md into multi-IDE governance rule files."""

    def __init__(self, repo_root: Path) -> None:
        self.repo_root = repo_root.resolve()
        self.canonical_file = self.repo_root / "AGENTS.md"

    def sync_all(self) -> list[SyncResult]:
        if not self.canonical_file.exists():
            return []

        canonical_text = self.canonical_file.read_text(encoding="utf-8")
        canonical_sha = hashlib.sha256(canonical_text.encode("utf-8")).hexdigest()

        header = f"<!-- AUTO-GENERATED FROM AGENTS.md (SHA: {canonical_sha[:12]}) - DO NOT EDIT MANUALLY -->\n\n"
        full_content = header + canonical_text

        results = []
        for rel_target in IDE_TARGETS:
            out_p = self.repo_root / rel_target
            out_p.parent.mkdir(parents=True, exist_ok=True)

            action = "updated" if out_p.exists() else "created"
            out_p.write_text(full_content, encoding="utf-8")
            results.append(
                SyncResult(target_path=rel_target, action=action, sha256=canonical_sha)
            )

        return results
