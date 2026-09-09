"""Sub-second staged file extractor and dispatcher."""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class IndexStage:
    mode: str
    object_id: str
    stage: int


@dataclass(frozen=True)
class StagedIndexEntry:
    path: Path
    relative_path: Path
    content: bytes | None
    status: str
    stages: tuple[IndexStage, ...]


class StagedFileScanner:
    """Discovers files currently staged in Git index for ultra-fast incremental scanning."""

    def __init__(self, repo_root: Path) -> None:
        self.repo_root = repo_root.resolve()

    def _git(self, args: list[str]) -> subprocess.CompletedProcess[bytes]:
        try:
            return subprocess.run(
                ["git", "--no-optional-locks", *args],
                cwd=self.repo_root,
                capture_output=True,
                check=False,
                timeout=30,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise RuntimeError("git staged-index command failed") from exc

    def get_staged_entries(self) -> list[StagedIndexEntry]:
        changed_proc = self._git(
            ["diff", "--cached", "--name-only", "--diff-filter=ACMRTD", "-z"]
        )
        if changed_proc.returncode != 0:
            raise RuntimeError("git staged-path discovery failed")
        changed_paths = [
            Path(os.fsdecode(raw_path))
            for raw_path in changed_proc.stdout.split(b"\0")
            if raw_path
        ]
        unmerged_proc = self._git(["ls-files", "--unmerged", "-z"])
        if unmerged_proc.returncode != 0:
            raise RuntimeError("git unmerged-index discovery failed")
        for record in unmerged_proc.stdout.split(b"\0"):
            if not record:
                continue
            _, raw_path = record.split(b"\t", 1)
            relative_path = Path(os.fsdecode(raw_path))
            if relative_path not in changed_paths:
                changed_paths.append(relative_path)
        if not changed_paths:
            return []

        index_proc = self._git(
            [
                "--literal-pathspecs",
                "ls-files",
                "--stage",
                "-z",
                "--",
                *(os.fspath(path) for path in changed_paths),
            ]
        )
        if index_proc.returncode != 0:
            raise RuntimeError("git staged-index discovery failed")

        indexed: dict[Path, list[IndexStage]] = {}
        for record in index_proc.stdout.split(b"\0"):
            if not record:
                continue
            header, raw_path = record.split(b"\t", 1)
            mode, object_id, stage = header.decode("ascii").split()
            indexed.setdefault(Path(os.fsdecode(raw_path)), []).append(
                IndexStage(mode=mode, object_id=object_id, stage=int(stage))
            )

        entries: list[StagedIndexEntry] = []
        for relative_path in changed_paths:
            stages = tuple(
                sorted(indexed.get(relative_path, []), key=lambda item: item.stage)
            )
            path = self.repo_root / relative_path
            if not stages:
                entries.append(
                    StagedIndexEntry(path, relative_path, None, "deleted", stages)
                )
                continue
            if len(stages) != 1 or stages[0].stage != 0:
                entries.append(
                    StagedIndexEntry(
                        path, relative_path, None, "unmerged_index", stages
                    )
                )
                continue

            content_proc = self._git(
                ["show", "--no-textconv", f":{os.fspath(relative_path)}"]
            )
            entries.append(
                StagedIndexEntry(
                    path,
                    relative_path,
                    content_proc.stdout if content_proc.returncode == 0 else None,
                    "staged" if content_proc.returncode == 0 else "error",
                    stages,
                )
            )
        return entries

    def get_staged_files(self) -> list[Path]:
        return [
            entry.path
            for entry in self.get_staged_entries()
            if entry.status == "staged"
        ]
