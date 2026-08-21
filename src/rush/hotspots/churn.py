"""Git numstat churn extractor & commit parser."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from rush.tools.common import run_subprocess


@dataclass(frozen=True)
class FileChurnStats:
    file_path: str
    commit_count: int
    insertions: int
    deletions: int
    total_churn: int
    unique_authors: set[str]


class GitChurnExtractor:
    """Parses Git commit history to calculate churn metrics per file."""

    def __init__(self, repo_root: Path) -> None:
        self.repo_root = repo_root.resolve()

    def extract_churn(self, max_commits: int = 500) -> dict[str, FileChurnStats]:
        proc = run_subprocess(
            ["git", "--no-pager", "log", f"-n{max_commits}", "--numstat", "--format=COMMIT|%an|%s"],
            cwd=self.repo_root,
        )
        if proc.returncode != 0:
            return {}

        file_data: dict[str, dict] = {}
        current_author = "unknown"

        for line in proc.stdout.splitlines():
            line = line.strip()
            if not line:
                continue
            if line.startswith("COMMIT|"):
                parts = line.split("|", 2)
                current_author = parts[1] if len(parts) > 1 else "unknown"
                continue

            numstat_parts = line.split("\t")
            if len(numstat_parts) == 3:
                ins_str, del_str, file_p = numstat_parts
                try:
                    ins = int(ins_str)
                    dels = int(del_str)
                except ValueError:
                    continue

                if file_p not in file_data:
                    file_data[file_p] = {"commits": 0, "ins": 0, "dels": 0, "authors": set()}

                file_data[file_p]["commits"] += 1
                file_data[file_p]["ins"] += ins
                file_data[file_p]["dels"] += dels
                file_data[file_p]["authors"].add(current_author)

        result = {}
        for fp, d in file_data.items():
            result[fp] = FileChurnStats(
                file_path=fp,
                commit_count=d["commits"],
                insertions=d["ins"],
                deletions=d["dels"],
                total_churn=d["ins"] + d["dels"],
                unique_authors=d["authors"],
            )
        return result
