"""Unified diff parser, security validator, and hunk analyzer."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

DIFF_HEADER_REGEX = re.compile(r"^--- (?:a/)?(.*?)\n\+\+\+ (?:b/)?(.*?)$", re.MULTILINE)
HUNK_HEADER_REGEX = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")

GOVERNANCE_BLOCKED_FILES = {
    "AGENTS.md",
    "CLAUDE.md",
    ".cursorrules",
    ".windsurfrules",
    "rush.toml",
    ".rush/trust.json",
    ".rush/hooks.json",
}


@dataclass(frozen=True)
class DiffHunk:
    old_start: int
    old_lines: int
    new_start: int
    new_lines: int
    lines: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class ParsedFilePatch:
    old_path: str
    new_path: str
    hunks: list[DiffHunk] = field(default_factory=list)


class UnifiedDiffParser:
    """Parses and validates unified diff strings for structural and security compliance."""

    @staticmethod
    def parse_patch(diff_text: str, repo_root: Path) -> list[ParsedFilePatch]:
        patches: list[ParsedFilePatch] = []
        file_chunks = re.split(r"(?=^diff --git|\n--- )", diff_text, flags=re.MULTILINE)

        for chunk in file_chunks:
            chunk = chunk.strip()
            if not chunk:
                continue

            match = DIFF_HEADER_REGEX.search(chunk)
            if not match:
                continue

            old_file = match.group(1).strip()
            new_file = match.group(2).strip()

            # Security validation: Prevent path traversal attacks
            for target_path in (old_file, new_file):
                if target_path and target_path != "/dev/null":
                    resolved = (repo_root / target_path).resolve()
                    if not resolved.is_relative_to(repo_root.resolve()):
                        raise ValueError(f"Path traversal detected in diff header: '{target_path}'")
                    if target_path in GOVERNANCE_BLOCKED_FILES:
                        raise PermissionError(f"Modifying governance file '{target_path}' is strictly forbidden.")

            hunks: list[DiffHunk] = []
            hunk_blocks = re.split(r"(?=^@@ )", chunk, flags=re.MULTILINE)
            for h_block in hunk_blocks:
                h_lines = h_block.splitlines()
                if not h_lines:
                    continue
                h_match = HUNK_HEADER_REGEX.match(h_lines[0])
                if h_match:
                    old_start = int(h_match.group(1))
                    old_len = int(h_match.group(2) or 1)
                    new_start = int(h_match.group(3))
                    new_len = int(h_match.group(4) or 1)
                    hunks.append(
                        DiffHunk(
                            old_start=old_start,
                            old_lines=old_len,
                            new_start=new_start,
                            new_lines=new_len,
                            lines=h_lines[1:],
                        )
                    )

            patches.append(ParsedFilePatch(old_path=old_file, new_path=new_file, hunks=hunks))

        return patches
