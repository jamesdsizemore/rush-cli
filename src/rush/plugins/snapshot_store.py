"""Content-addressed physical snapshot store for immutable plugin execution.

Architecture §8, Phase 56: User-Owned Content-Addressed Plugin Trust.
Guarantees:
- Materializes pure independent byte copies of plugin closures into ~/.rush/snapshots/<closure_digest>.
- Strictly rejects symlinks, Windows directory junctions, and hardlinks fail-closed.
- Provides cryptographic snapshot integrity verification against PluginClosureManifest.
"""

from __future__ import annotations

import hashlib
import os
import stat
from pathlib import Path

from rush.io.physical_paths import ContainmentError, PhysicalRoot
from rush.plugins.closure import ClosureTamperedError, PluginClosureManifest


class SnapshotError(Exception):
    """Base exception for plugin snapshot store errors."""


class PluginSnapshotStore:
    """Manages immutable, content-addressed plugin execution snapshots on physical disk."""

    def __init__(self, snapshots_root: Path | None = None) -> None:
        if snapshots_root is None:
            self.snapshots_root = (Path.home() / ".rush" / "snapshots").resolve()
        else:
            self.snapshots_root = Path(snapshots_root).resolve()

    def materialize_snapshot(
        self, closure: PluginClosureManifest, plugin_root: Path
    ) -> Path:
        """Materialize an immutable, content-addressed copy of plugin closure bytes.

        Validates that both source and snapshot trees are strictly contained under PhysicalRoot.
        Rejects symlinks, Windows directory junctions, and hardlinks fail-closed.
        Returns the snapshot directory Path.
        """
        plugin_root_resolved = Path(plugin_root).resolve()
        if not plugin_root_resolved.exists():
            raise SnapshotError(f"Plugin root does not exist: {plugin_root}")
        if not plugin_root_resolved.is_dir():
            raise SnapshotError(f"Plugin root is not a directory: {plugin_root}")

        if Path(plugin_root).is_symlink():
            raise ContainmentError(
                "SYMLINK_DISALLOWED",
                f"Plugin root is a symlink: {plugin_root}",
                str(plugin_root),
            )

        reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
        st_root = os.lstat(plugin_root)
        if (getattr(st_root, "st_file_attributes", 0) & reparse_flag) or (
            os.name == "nt" and getattr(plugin_root, "is_junction", lambda: False)()
        ):
            raise ContainmentError(
                "REPARSE_POINT_DISALLOWED",
                f"Plugin root is a junction: {plugin_root}",
                str(plugin_root),
            )

        src_physical = PhysicalRoot(plugin_root_resolved)

        # Pre-scan plugin_root to reject symlinks, junctions, and hardlinks fail-closed
        for root, dirs, files in os.walk(plugin_root_resolved, followlinks=False):
            current_dir_path = Path(root)
            for d in sorted(dirs):
                sub_dir = current_dir_path / d
                rel_d = sub_dir.relative_to(plugin_root_resolved)
                src_physical.open_contained(rel_d)

            for f in sorted(files):
                file_path = current_dir_path / f
                rel_f = file_path.relative_to(plugin_root_resolved)
                src_physical.open_contained(rel_f)

                st_f = os.lstat(file_path)
                if stat.S_ISREG(st_f.st_mode) and st_f.st_nlink > 1:
                    raise ContainmentError(
                        "HARDLINK_DISALLOWED",
                        f"Hardlink detected at '{file_path}'",
                        str(rel_f),
                    )

        # Prepare snapshots root
        snapshots_root_resolved = self.snapshots_root.resolve()
        snapshots_root_resolved.mkdir(parents=True, exist_ok=True)
        if self.snapshots_root.is_symlink():
            raise ContainmentError(
                "SYMLINK_DISALLOWED",
                f"Snapshots root is a symlink: {self.snapshots_root}",
                str(self.snapshots_root),
            )
        st_snap_root = os.lstat(self.snapshots_root)
        if (getattr(st_snap_root, "st_file_attributes", 0) & reparse_flag) or (
            os.name == "nt"
            and getattr(self.snapshots_root, "is_junction", lambda: False)()
        ):
            raise ContainmentError(
                "REPARSE_POINT_DISALLOWED",
                f"Snapshots root is a junction: {self.snapshots_root}",
                str(self.snapshots_root),
            )

        snapshots_physical = PhysicalRoot(snapshots_root_resolved)
        snapshot_dir = snapshots_physical.open_contained(closure.closure_digest)
        snapshot_dir.mkdir(parents=True, exist_ok=True)

        snapshot_physical = PhysicalRoot(snapshot_dir.resolve())

        # Copy raw physical bytes for each entry in closure file manifest
        for rel_str, expected_sha in closure.file_manifest.items():
            rel_path = Path(rel_str)
            src_file = src_physical.open_contained(rel_path)
            if not src_file.exists() or not src_file.is_file():
                raise SnapshotError(f"Missing source file for snapshot: {rel_str}")
            if src_file.is_symlink():
                raise ContainmentError(
                    "SYMLINK_DISALLOWED",
                    f"Source file is a symlink: {src_file}",
                    rel_str,
                )
            st_src = os.lstat(src_file)
            if stat.S_ISREG(st_src.st_mode) and st_src.st_nlink > 1:
                raise ContainmentError(
                    "HARDLINK_DISALLOWED",
                    f"Hardlink detected at '{src_file}'",
                    rel_str,
                )

            raw_bytes = src_file.read_bytes()
            hasher = hashlib.sha256(raw_bytes)
            if hasher.hexdigest() != expected_sha:
                raise ClosureTamperedError(
                    f"Source file '{rel_str}' hash does not match closure manifest"
                )

            dst_file = snapshot_physical.open_contained(rel_path)
            dst_file.parent.mkdir(parents=True, exist_ok=True)

            if dst_file.is_symlink():
                raise ContainmentError(
                    "SYMLINK_DISALLOWED",
                    f"Destination path is a symlink: {dst_file}",
                    rel_str,
                )

            dst_file.write_bytes(raw_bytes)

            st_dst = os.lstat(dst_file)
            if dst_file.is_symlink():
                raise ContainmentError(
                    "SYMLINK_DISALLOWED",
                    f"Snapshot target became symlink: {dst_file}",
                    rel_str,
                )
            if stat.S_ISREG(st_dst.st_mode) and st_dst.st_nlink > 1:
                raise ContainmentError(
                    "HARDLINK_DISALLOWED",
                    f"Snapshot file has hardlinks: {dst_file}",
                    rel_str,
                )

        return snapshot_dir

    def verify_snapshot(self, closure: PluginClosureManifest) -> bool:
        """Verify the cryptographic integrity of a materialized snapshot directory.

        Re-reads all files in the snapshot directory, asserting every manifest file exists,
        is an unlinked regular file, and its SHA-256 matches closure.file_manifest.
        Returns True if intact, False otherwise.
        """
        try:
            snapshots_root_resolved = self.snapshots_root.resolve()
            if (
                not snapshots_root_resolved.exists()
                or not snapshots_root_resolved.is_dir()
            ):
                return False

            snapshots_physical = PhysicalRoot(snapshots_root_resolved)
            snapshot_dir = snapshots_physical.open_contained(closure.closure_digest)
            if not snapshot_dir.exists() or not snapshot_dir.is_dir():
                return False
            if snapshot_dir.is_symlink():
                return False

            reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
            st_dir = os.lstat(snapshot_dir)
            if (getattr(st_dir, "st_file_attributes", 0) & reparse_flag) or (
                os.name == "nt"
                and getattr(snapshot_dir, "is_junction", lambda: False)()
            ):
                return False

            snapshot_physical = PhysicalRoot(snapshot_dir.resolve())

            for rel_str, expected_sha in closure.file_manifest.items():
                rel_path = Path(rel_str)
                candidate = snapshot_physical.open_contained(rel_path)
                if not candidate.exists() or not candidate.is_file():
                    return False
                if candidate.is_symlink():
                    return False

                st_cand = os.lstat(candidate)
                if (getattr(st_cand, "st_file_attributes", 0) & reparse_flag) or (
                    os.name == "nt"
                    and getattr(candidate, "is_junction", lambda: False)()
                ):
                    return False
                if stat.S_ISREG(st_cand.st_mode) and st_cand.st_nlink > 1:
                    return False

                hasher = hashlib.sha256()
                with open(candidate, "rb") as fp:
                    while chunk := fp.read(65536):
                        hasher.update(chunk)
                if hasher.hexdigest() != expected_sha:
                    return False

            return True
        except (ContainmentError, OSError, ValueError):
            return False
