"""Temporal commit co-change coupling analyzer."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

from rush.tools.common import run_subprocess


@dataclass(frozen=True)
class CoChangePair:
    file_a: str
    file_b: str
    co_change_count: int
    coupling_percent: float


class TemporalCouplingAnalyzer:
    """Detects implicit architectural coupling between files frequently changed together."""

    def __init__(self, repo_root: Path) -> None:
        self.repo_root = repo_root.resolve()

    def analyze_coupling(self, min_co_changes: int = 2) -> list[CoChangePair]:
        proc = run_subprocess(
            ["git", "--no-pager", "log", "-n200", "--name-only", "--format=COMMIT"],
            cwd=self.repo_root,
        )
        if proc.returncode != 0:
            return []

        commits: list[list[str]] = []
        current_commit_files: list[str] = []

        for line in proc.stdout.splitlines():
            line = line.strip()
            if not line:
                continue
            if line == "COMMIT":
                if current_commit_files:
                    commits.append(current_commit_files)
                    current_commit_files = []
            else:
                current_commit_files.append(line)

        if current_commit_files:
            commits.append(current_commit_files)

        pair_counts: dict[tuple[str, str], int] = defaultdict(int)
        file_counts: dict[str, int] = defaultdict(int)

        for files in commits:
            unique_files = sorted(set(files))
            for f in unique_files:
                file_counts[f] += 1
            for i in range(len(unique_files)):
                for j in range(i + 1, len(unique_files)):
                    pair = (unique_files[i], unique_files[j])
                    pair_counts[pair] += 1

        results = []
        for (f_a, f_b), count in pair_counts.items():
            if count >= min_co_changes:
                max_single = max(file_counts[f_a], file_counts[f_b])
                pct = (count / max_single) * 100.0 if max_single > 0 else 0.0
                results.append(
                    CoChangePair(
                        file_a=f_a,
                        file_b=f_b,
                        co_change_count=count,
                        coupling_percent=round(pct, 1),
                    )
                )

        return sorted(results, key=lambda p: p.co_change_count, reverse=True)
