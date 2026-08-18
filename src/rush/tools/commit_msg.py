"""Conventional commit validation without history mutation."""

from __future__ import annotations

import re
from pathlib import Path

from .base import ToolFn, ToolResult
from .common import elapsed_ms, now_ms

_PATTERN = re.compile(
    r"^(?:feat|fix|docs|test|refactor|perf|build|ci|chore)(?:\([^)\n]+\))?!?: .+"
)


class CommitMsgTool(ToolFn):
    name = "commit-msg"

    @property
    def mcp_description(self) -> str:
        return "Validate supplied Conventional Commit messages without modifying Git history."

    def __call__(self, path: Path) -> ToolResult:
        return self.run(path)

    def run(self, path: Path, *, message: str = "", config=None) -> ToolResult:
        start = now_ms()
        valid = bool(_PATTERN.fullmatch(message))
        findings = (
            []
            if valid
            else [
                {
                    "rule": "conventional-commit",
                    "severity": "error",
                    "message": "Message must use Conventional Commits: type: description",
                }
            ]
        )
        return ToolResult(
            tool=self.name,
            engine="builtin",
            engine_version=None,
            status="ok" if valid else "fail",
            duration_ms=elapsed_ms(start),
            summary="commit message is valid" if valid else "commit message is invalid",
            findings=findings,
            raw=None,
            artifacts=[],
        )
