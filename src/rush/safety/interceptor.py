"""Destructive shell command interceptor."""

from __future__ import annotations

import re

DANGEROUS_COMMAND_PATTERNS = [
    (
        re.compile(r"\bgit\s+reset\s+--hard\b"),
        "Blocked destructive command 'git reset --hard'.",
    ),
    (
        re.compile(r"\bgit\s+clean\s+-[a-zA-Z]*f"),
        "Blocked destructive command 'git clean -f'.",
    ),
    (
        re.compile(r"\bgit\s+push\s+.*--force\b"),
        "Blocked destructive command 'git push --force'.",
    ),
    (
        re.compile(r"\bgit\s+push\s+.*-f\b"),
        "Blocked destructive command 'git push -f'.",
    ),
    (
        re.compile(r"\brm\s+-[a-zA-Z]*r[a-zA-Z]*f\s+[\/\.]"),
        "Blocked destructive root/directory recursive deletion.",
    ),
    (
        re.compile(r"\bdrop\s+database\b", re.IGNORECASE),
        "Blocked destructive SQL 'DROP DATABASE' command.",
    ),
    (
        re.compile(r"\bchmod\s+777\b"),
        "Blocked insecure permission escalation 'chmod 777'.",
    ),
]


class DangerousCommandInterceptor:
    """Inspects shell command strings and blocks destructive operations."""

    @staticmethod
    def inspect_command(command_line: str) -> tuple[bool, str | None]:
        cmd_clean = command_line.strip()
        for pattern, reason in DANGEROUS_COMMAND_PATTERNS:
            if pattern.search(cmd_clean):
                return False, reason
        return True, None
