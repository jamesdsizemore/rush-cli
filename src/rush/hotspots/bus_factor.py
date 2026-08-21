"""Author ownership entropy & knowledge silos (Bus Factor)."""

from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from rush.tools.common import run_subprocess


@dataclass(frozen=True)
class FileKnowledgeOwnership:
    file_path: str
    primary_owner: str
    ownership_percent: float
    total_authors: int
    author_entropy: float


class BusFactorAssessor:
    """Calculates author ownership concentration and identifies high-risk knowledge silos."""

    def __init__(self, repo_root: Path) -> None:
        self.repo_root = repo_root.resolve()

    def assess_ownership(self) -> list[FileKnowledgeOwnership]:
        proc = run_subprocess(
            ["git", "--no-pager", "log", "-n300", "--numstat", "--format=COMMIT|%an"],
            cwd=self.repo_root,
        )
        if proc.returncode != 0:
            return []

        file_authors: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
        current_author = "unknown"

        for line in proc.stdout.splitlines():
            line = line.strip()
            if not line:
                continue
            if line.startswith("COMMIT|"):
                current_author = line.split("|", 1)[1]
                continue

            parts = line.split("\t")
            if len(parts) == 3:
                f_path = parts[2]
                file_authors[f_path][current_author] += 1

        results = []
        for fp, authors_map in file_authors.items():
            total_edits = sum(authors_map.values())
            if total_edits == 0:
                continue

            sorted_authors = sorted(authors_map.items(), key=lambda x: x[1], reverse=True)
            primary_name, primary_count = sorted_authors[0]
            owner_pct = (primary_count / total_edits) * 100.0

            entropy = 0.0
            for a_name, count in authors_map.items():
                p = count / total_edits
                if p > 0:
                    entropy += - p * math.log2(p)

            results.append(
                FileKnowledgeOwnership(
                    file_path=fp,
                    primary_owner=primary_name,
                    ownership_percent=round(owner_pct, 1),
                    total_authors=len(authors_map),
                    author_entropy=round(entropy, 2),
                )
            )

        return sorted(results, key=lambda x: x.ownership_percent, reverse=True)
