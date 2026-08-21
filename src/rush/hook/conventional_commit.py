"""Conventional Commits 1.0 message syntax validator."""

from __future__ import annotations

import re

CONVENTIONAL_PATTERN = re.compile(
    r"^(feat|fix|docs|style|refactor|perf|test|build|ci|chore|revert)(\([a-zA-Z0-9_\-\./]+\))?(!)?:\s+[a-zA-Z0-9].+"
)


class ConventionalCommitValidator:
    """Ensures commit messages conform to the Conventional Commits specification."""

    @staticmethod
    def validate_message(msg: str) -> tuple[bool, str | None]:
        first_line = msg.strip().splitlines()[0] if msg.strip() else ""
        if not first_line:
            return False, "Commit message cannot be empty."

        if not CONVENTIONAL_PATTERN.match(first_line):
            return (
                False,
                f"Commit message does not follow Conventional Commits format (e.g. 'feat(scope): message'). Received: '{first_line}'",
            )
        return True, None
