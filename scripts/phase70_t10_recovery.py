"""Phase 70 T10 recovery: inventory, back up and quarantine one stray `.rush`.

Usage (inventory only; changes nothing):

    python scripts/phase70_t10_recovery.py --root <checkout> --source <checkout>/<...>/.rush \
        --recovery <recovery-dir>

Add `--execute` to also back up (byte-exact copy, SHA-256 verified) into
`<recovery>/backup/.rush` and quarantine (move, SHA-256 verified) into
`<recovery>/quarantine/.rush`, then print the exact restore command. Nothing is
ever deleted, merged or rewritten; `<recovery>/manifest.json` records the
inventory, both copies' hashes and the restore command.

Refuses (exit 2, nothing changed) when: the source is not a real directory named
`.rush` strictly inside `--root`; any component from `--root` to the source, or
any entry under the source, is a symlink or not a regular file/directory; the
recovery directory lies inside `--root` or the source (or the source inside it);
a backup/quarantine target already exists; or, with `--execute`, a process holds
a file under the source open (`lsof +D`).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shlex
import shutil
import sqlite3
import stat
import subprocess
import sys
import urllib.parse
from pathlib import Path
from typing import Any


class RecoveryRefused(Exception):
    """A precondition failed; nothing was changed."""


def _sha256(path: Path) -> str:
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def _is_within(child: Path, parent: Path) -> bool:
    return child == parent or parent in child.parents


def validate(root: Path, source: Path, recovery: Path) -> tuple[Path, Path, Path]:
    """Absolute, link-free paths, or `RecoveryRefused`. Never follows a link."""
    root, source, recovery = (
        Path(os.path.abspath(p)) for p in (root, source, recovery)
    )
    if not root.is_dir() or root.is_symlink():
        raise RecoveryRefused(f"root is not a real directory: {root}")
    if source.name != ".rush":
        raise RecoveryRefused(f"source is not a `.rush` directory: {source}")
    if source == root or not _is_within(source, root):
        raise RecoveryRefused(f"source {source} is outside root {root}")
    current = root
    for part in source.relative_to(root).parts:
        current = current / part
        st = os.lstat(current) if os.path.lexists(current) else None
        if st is None:
            raise RecoveryRefused(f"source does not exist: {source}")
        if stat.S_ISLNK(st.st_mode) or not stat.S_ISDIR(st.st_mode):
            raise RecoveryRefused(f"not a real directory on the source path: {current}")
    if _is_within(recovery, root) or _is_within(recovery, source):
        raise RecoveryRefused(f"recovery {recovery} lies inside root or source")
    if _is_within(source, recovery):
        raise RecoveryRefused(f"source {source} lies inside recovery {recovery}")
    if os.path.lexists(recovery) and (
        os.path.islink(recovery) or not recovery.is_dir()
    ):
        raise RecoveryRefused(f"recovery is not a real directory: {recovery}")
    return root, source, recovery


def _sqlite_integrity(path: Path) -> str:
    uri = f"file:{urllib.parse.quote(str(path))}?mode=ro&immutable=1"
    try:
        conn = sqlite3.connect(uri, uri=True)
        try:
            return str(conn.execute("PRAGMA integrity_check").fetchone()[0])
        finally:
            conn.close()
    except sqlite3.DatabaseError as exc:
        return f"error: {exc}"


def _git_provenance(root: Path, source: Path) -> str:
    try:
        completed = subprocess.run(
            ["git", "-C", str(root), "log", "--all", "--oneline", "--", str(source)],
            capture_output=True,
            text=True,
            check=False,
            timeout=60,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return f"unavailable: {exc}"
    if completed.returncode != 0:
        return f"unavailable: {completed.stderr.strip()}"
    return completed.stdout.strip() or "untracked (no commit touches this path)"


def open_handles(source: Path) -> list[str]:
    """Processes holding files under `source` open (`lsof +D`); lsof exits 1
    when there are none."""
    try:
        completed = subprocess.run(
            ["lsof", "+D", str(source)],
            capture_output=True,
            text=True,
            check=False,
            timeout=120,
        )
    except FileNotFoundError as exc:
        raise RecoveryRefused("lsof is required to prove no file is open") from exc
    return completed.stdout.strip().splitlines()[1:]


def inventory(root: Path, source: Path) -> dict[str, Any]:
    """Read-only: every file's size, mtime and SHA-256, WAL sidecars, SQLite
    integrity (opened `immutable=1`, so nothing is created), git provenance."""
    files: list[dict[str, Any]] = []
    for dirpath, dirnames, filenames in os.walk(source, followlinks=False):
        for name in sorted(dirnames + filenames):
            path = Path(dirpath) / name
            st = os.lstat(path)
            if stat.S_ISDIR(st.st_mode):
                continue
            if not stat.S_ISREG(st.st_mode):
                raise RecoveryRefused(f"not a regular file (link or special): {path}")
            entry: dict[str, Any] = {
                "path": path.relative_to(source).as_posix(),
                "size": st.st_size,
                "mtime_ns": st.st_mtime_ns,
                "sha256": _sha256(path),
                "sidecar": name.endswith(("-wal", "-shm", "-journal")),
            }
            if name.endswith(".db"):
                entry["integrity"] = _sqlite_integrity(path)
            files.append(entry)
    files.sort(key=lambda f: f["path"])
    return {
        "source": str(source),
        "files": files,
        "git_provenance": _git_provenance(root, source),
    }


def _hashes(tree: Path) -> dict[str, str]:
    return {
        p.relative_to(tree).as_posix(): _sha256(p)
        for p in tree.rglob("*")
        if p.is_file() and not p.is_symlink()
    }


def restore_command(source: Path, recovery: Path) -> str:
    quarantined = recovery / "quarantine" / ".rush"
    return f"mv -n {shlex.quote(str(quarantined))} {shlex.quote(str(source))}"


def execute(root: Path, source: Path, recovery: Path) -> dict[str, Any]:
    """Inventory, byte-exact backup, verified quarantine. Refuses before any
    change when a precondition fails; stops (never deletes) on a hash mismatch."""
    root, source, recovery = validate(root, source, recovery)
    report = inventory(root, source)
    expected = {f["path"]: f["sha256"] for f in report["files"]}
    backup = recovery / "backup" / ".rush"
    quarantine = recovery / "quarantine" / ".rush"
    for target in (backup, quarantine, recovery / "manifest.json"):
        if os.path.lexists(target):
            raise RecoveryRefused(f"refusing to overwrite existing {target}")
    handles = open_handles(source)
    if handles:
        raise RecoveryRefused(f"files under {source} are open: {handles}")

    backup.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(source, backup, symlinks=True, copy_function=shutil.copy2)
    if _hashes(backup) != expected:
        raise RecoveryRefused(f"backup hash mismatch; source untouched at {source}")

    quarantine.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(source), str(quarantine))
    if _hashes(quarantine) != expected:
        raise RecoveryRefused(
            f"quarantine hash mismatch; backup intact at {backup}, "
            f"quarantined copy at {quarantine}"
        )
    report.update(
        backup=str(backup),
        quarantine=str(quarantine),
        verified="sha256 equal across original, backup and quarantine",
        restore_command=restore_command(source, recovery),
    )
    (recovery / "manifest.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--recovery", type=Path, required=True)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.execute:
            report = execute(args.root, args.source, args.recovery)
        else:
            root, source, _ = validate(args.root, args.source, args.recovery)
            report = inventory(root, source)
    except RecoveryRefused as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(report, indent=2, sort_keys=True))
    if args.execute:
        print(f"RESTORE: {report['restore_command']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
