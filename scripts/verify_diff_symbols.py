"""Verification engine for git diffs to prevent stub commits, fake completions, and bypasses.

Enforces:
- Zero added placeholder strings ("unknown", "deferred", "simulated", "placeholder") in added diff lines (+).
- AST / symbol presence verification: ensures expected library calls or imports are actually present.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

BANNED_DIFF_STRINGS = {"unknown", "deferred", "simulated", "placeholder"}


def parse_diff_added_lines(diff_text: str) -> list[tuple[str, int, str]]:
    """Extracts (filename, line_number, line_content) for all added lines (+) in diff."""
    added_lines: list[tuple[str, int, str]] = []
    current_file = ""
    current_lineno = 0

    for line in diff_text.splitlines():
        if line.startswith("+++ b/"):
            current_file = line[6:]
            continue
        if line.startswith("@@"):
            match = re.search(r"\+(\d+)", line)
            if match:
                current_lineno = int(match.group(1))
            continue
        if line.startswith("+") and not line.startswith("+++"):
            content = line[1:]
            added_lines.append((current_file, current_lineno, content))
            current_lineno += 1
        elif not line.startswith("-"):
            current_lineno += 1

    return added_lines


def check_diff_for_banned_tokens(diff_text: str) -> list[str]:
    """Scans added lines in diff for banned placeholder tokens."""
    violations: list[str] = []
    added = parse_diff_added_lines(diff_text)

    for filename, lineno, content in added:
        # Ignore markdown, documentation, plans, and validator/schema engines explicitly checking the banned tokens
        if filename.endswith(".md") or "verify_" in filename or "schemas" in filename:
            continue
        for token in BANNED_DIFF_STRINGS:
            # Match token as standalone string or literal
            if re.search(
                rf'["\']\s*{re.escape(token)}\s*["\']', content, re.IGNORECASE
            ):
                violations.append(
                    f"{filename}:{lineno}: Added banned placeholder '{token}' in diff line: {content.strip()}"
                )
    return violations


def check_diff_for_required_symbols(
    diff_text: str, required_symbols: list[str]
) -> list[str]:
    """Verifies that the diff physically introduces or references mandatory engine symbols."""
    missing: list[str] = []
    for symbol in required_symbols:
        if symbol not in diff_text:
            missing.append(f"Diff lacks required engine symbol or call: '{symbol}'")
    return missing


def get_git_diff(revision_range: str | None = None) -> str:
    cmd = ["git", "diff"]
    if revision_range:
        cmd.append(revision_range)
    else:
        cmd.append("HEAD")
    res = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    return res.stdout


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Verify git diff for banned stubs and required symbols."
    )
    parser.add_argument(
        "--revision", help="Git revision range to diff, e.g. origin/main...HEAD"
    )
    parser.add_argument(
        "--require-symbols",
        nargs="*",
        default=[],
        help="List of symbols that MUST appear in the diff.",
    )
    parser.add_argument(
        "--diff-file", help="Path to a file containing raw diff text to analyze."
    )
    args = parser.parse_args()

    if args.diff_file:
        diff_text = Path(args.diff_file).read_text(encoding="utf-8")
    else:
        diff_text = get_git_diff(args.revision)

    violations = check_diff_for_banned_tokens(diff_text)
    if args.require_symbols:
        violations.extend(
            check_diff_for_required_symbols(diff_text, args.require_symbols)
        )

    if violations:
        print("=" * 70, file=sys.stderr)
        print(
            f"FAILED: {len(violations)} diff verification violations found:",
            file=sys.stderr,
        )
        print("=" * 70, file=sys.stderr)
        for v in violations:
            print(f"  - {v}", file=sys.stderr)
        print("=" * 70, file=sys.stderr)
        return 1

    print("SUCCESS: Diff verification passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
