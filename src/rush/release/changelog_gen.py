"""Conventional Commits semantic changelog generator."""

from __future__ import annotations

import re
from collections import defaultdict
from pathlib import Path
from rush.tools.common import run_subprocess

CONVENTIONAL_REGEX = re.compile(
    r"^(?P<type>feat|fix|docs|style|refactor|perf|test|build|ci|chore|revert)"
    r"(?:\((?P<scope>[\w\-\.]+)\))?!"
    r":\s+(?P<description>.+)$"
)


class SemanticChangelogGenerator:
    """Generates structured Markdown changelogs from Git Conventional Commits."""

    def __init__(self, repo_root: Path) -> None:
        self.repo_root = repo_root.resolve()

    def generate_changelog(self, version: str, since_tag: str | None = None) -> str:
        git_args = ["git", "log", "--pretty=format:%s"]
        if since_tag:
            git_args.append(f"{since_tag}..HEAD")
        else:
            git_args.extend(["-n", "100"])

        proc = run_subprocess(git_args, cwd=self.repo_root)
        if proc.returncode != 0:
            return f"## [{version}]\n\nNo commit history discovered.\n"

        categories: dict[str, list[str]] = defaultdict(list)
        for line in proc.stdout.splitlines():
            line_clean = line.strip()
            if not line_clean:
                continue
            match = CONVENTIONAL_REGEX.match(line_clean)
            if match:
                c_type = match.group("type")
                scope = match.group("scope")
                desc = match.group("description")
                scope_str = f"**{scope}**: " if scope else ""
                categories[c_type].append(f"{scope_str}{desc}")
            else:
                categories["other"].append(line_clean)

        lines = [f"## [{version}]\n"]
        type_headers = {
            "feat": "### 🚀 Features & Enhancements",
            "fix": "### 🐛 Bug Fixes & Patches",
            "perf": "### ⚡ Performance Improvements",
            "refactor": "### ♻️ Code Refactoring",
            "docs": "### 📚 Documentation",
            "ci": "### 👷 CI/CD & Automation",
            "chore": "### 🧹 Maintenance & Chores",
            "other": "### 📦 Other Changes",
        }

        for cat_key, header in type_headers.items():
            if cat_key in categories and categories[cat_key]:
                lines.append(f"{header}\n")
                for item in categories[cat_key]:
                    lines.append(f"- {item}")
                lines.append("")

        return "\n".join(lines)
