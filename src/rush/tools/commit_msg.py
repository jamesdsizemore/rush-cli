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

    def __call__(
        self,
        path: Path,
        *,
        message: str = "",
        allow_network: bool = False,
        allow_download: bool = False,
        allow_cache_write: bool = False,
        allow_build: bool = False,
        allow_slow: bool = False,
        allow_artifact_write: bool = False,
        allow_browser: bool = False,
    ) -> ToolResult:
        from ..permissions import ExecutionPermissions

        permissions = ExecutionPermissions(
            network=allow_network,
            download=allow_download,
            cache_write=allow_cache_write,
            build=allow_build,
            slow=allow_slow,
            artifact_write=allow_artifact_write,
            browser=allow_browser,
        )
        return self.run(path, message=message, permissions=permissions)

    def run(
        self,
        path: Path,
        *,
        message: str = "",
        config=None,
        permissions=None,
    ) -> ToolResult:
        from ..permissions import build_execution_metadata

        start = now_ms()
        msg_to_check = message
        if not msg_to_check and path.is_file():
            try:
                msg_to_check = path.read_text(encoding="utf-8").strip()
            except (OSError, UnicodeDecodeError):
                msg_to_check = ""

        first_line = msg_to_check.splitlines()[0] if msg_to_check else ""
        valid = bool(_PATTERN.fullmatch(first_line))
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
            metadata={
                "execution": build_execution_metadata(
                    "executed",
                    granted=permissions,
                    producer="builtin",
                )
            },
        )
