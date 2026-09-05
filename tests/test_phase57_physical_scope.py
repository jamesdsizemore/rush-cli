"""Tests for Phase 57 Physical Scope boundaries and target immutability.

Contracts:
- T-57.04: Target states and selection provenance are immutable (frozen dataclass, content_hash).
- T-57.05: Link, junction, and swap cannot widen scope (ScopeWideningError fail-closed).
- T-57.06: Undeclared host input refuses execution (UndeclaredInputError fail-closed).
"""

from __future__ import annotations

import hashlib
import os
import stat
from dataclasses import FrozenInstanceError
from pathlib import Path

try:
    import _winapi
except ImportError:
    _winapi = None  # type: ignore[assignment]

import pytest

from rush.invocation.models import (
    PhysicalTarget,
    ScopeWideningError,
    UndeclaredInputError,
)
from rush.invocation.targets import build_physical_targets, resolve_target


def test_target_states_and_selection_provenance_are_immutable(tmp_path: Path) -> None:
    """T-57.04: Verify physical targets across states and provenances are frozen and compute exact content hashes."""
    workspace = tmp_path.resolve()

    # 1. State 'present' with 'explicit' provenance
    file_present = workspace / "module.py"
    present_content = b"def calculate(x: int) -> int:\n    return x * 2\n"
    file_present.write_bytes(present_content)
    expected_hash = hashlib.sha256(present_content).hexdigest()

    target_present = resolve_target(
        workspace, "module.py", provenance="explicit", capability="read"
    )
    assert isinstance(target_present, PhysicalTarget)
    assert target_present.relative_path == Path("module.py")
    assert target_present.state == "present"
    assert target_present.provenance == "explicit"
    assert target_present.capability == "read"
    assert target_present.content_hash == expected_hash
    assert len(target_present.content_hash) == 64

    # 2. State 'deleted' with 'git-staged' provenance (target does not exist on disk)
    target_deleted = resolve_target(
        workspace, "removed_file.py", provenance="git-staged", capability="read"
    )
    assert target_deleted.relative_path == Path("removed_file.py")
    assert target_deleted.state == "deleted"
    assert target_deleted.provenance == "git-staged"
    assert target_deleted.capability == "read"
    assert target_deleted.content_hash == ""

    # 3. State 'renamed' with 'git-changed' provenance
    file_renamed = workspace / "new_module_name.py"
    renamed_content = b"# renamed file content\n"
    file_renamed.write_bytes(renamed_content)
    expected_renamed_hash = hashlib.sha256(renamed_content).hexdigest()

    target_renamed = resolve_target(
        workspace,
        "new_module_name.py",
        provenance="git-changed",
        capability="write",
        state="renamed",
    )
    assert target_renamed.relative_path == Path("new_module_name.py")
    assert target_renamed.state == "renamed"
    assert target_renamed.provenance == "git-changed"
    assert target_renamed.capability == "write"
    assert target_renamed.content_hash == expected_renamed_hash

    # 4. Provenance 'glob' via build_physical_targets
    targets_glob = build_physical_targets(
        workspace, ["module.py"], provenance="glob", capability="read"
    )
    assert len(targets_glob) == 1
    assert targets_glob[0].provenance == "glob"
    assert targets_glob[0].state == "present"
    assert targets_glob[0].content_hash == expected_hash

    # 5. Strict dataclass immutability verification
    for target in (target_present, target_deleted, target_renamed, targets_glob[0]):
        with pytest.raises(FrozenInstanceError):
            target.state = "deleted"  # type: ignore[misc]
        with pytest.raises(FrozenInstanceError):
            target.relative_path = Path("other.py")  # type: ignore[misc]
        with pytest.raises(FrozenInstanceError):
            target.provenance = "tampered"  # type: ignore[misc]
        with pytest.raises(FrozenInstanceError):
            target.content_hash = "tampered_hash"  # type: ignore[misc]
        with pytest.raises(FrozenInstanceError):
            target.capability = "execute"  # type: ignore[misc]


def test_link_junction_and_swap_cannot_widen_scope(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """T-57.05: Verify symlinks, directory junctions, parent traversals, and swaps fail-closed with ScopeWideningError."""
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    outside_jail = tmp_path / "outside_jail"
    outside_jail.mkdir()

    secret_file = outside_jail / "secret.env"
    secret_file.write_text(
        "DATABASE_URL=postgres://admin:secret@host/db\n", encoding="utf-8"
    )

    outside_sub = outside_jail / "confidential_dir"
    outside_sub.mkdir()
    (outside_sub / "key.pem").write_text("PRIVATE_KEY_DATA\n", encoding="utf-8")

    # 1. Parent traversal attempts must raise ScopeWideningError fail-closed
    traversal_paths = [
        "../escape.txt",
        "../../escape.txt",
        "nested/../../escape.txt",
        "sub/dir/../../../secret.env",
    ]
    for traversal in traversal_paths:
        with pytest.raises(ScopeWideningError):
            resolve_target(workspace, traversal)
        with pytest.raises(ScopeWideningError):
            build_physical_targets(workspace, [traversal])

    # 2. File and directory symlinks pointing outside workspace
    file_symlink = workspace / "link_to_secret.env"
    try:
        os.symlink(secret_file, file_symlink)
        can_symlink_file = True
    except (OSError, NotImplementedError):
        can_symlink_file = False

    if can_symlink_file:
        with pytest.raises(ScopeWideningError):
            resolve_target(workspace, "link_to_secret.env")
        with pytest.raises(ScopeWideningError):
            build_physical_targets(workspace, ["link_to_secret.env"])

    dir_symlink = workspace / "link_to_dir"
    try:
        os.symlink(outside_sub, dir_symlink, target_is_directory=True)
        can_symlink_dir = True
    except (OSError, NotImplementedError):
        can_symlink_dir = False

    if can_symlink_dir:
        with pytest.raises(ScopeWideningError):
            resolve_target(workspace, "link_to_dir/key.pem")
        with pytest.raises(ScopeWideningError):
            build_physical_targets(workspace, ["link_to_dir/key.pem"])

    # 3. Real Windows directory junctions (if available on Windows)
    if _winapi is not None and hasattr(_winapi, "CreateJunction"):
        junction_path = workspace / "junction_escape"
        try:
            _winapi.CreateJunction(str(outside_jail), str(junction_path))
            with pytest.raises(ScopeWideningError):
                resolve_target(workspace, "junction_escape/secret.env")
            with pytest.raises(ScopeWideningError):
                build_physical_targets(workspace, ["junction_escape/secret.env"])
        except OSError:
            pass

    # 4. Simulated reparse point attribute (for guaranteed coverage on any platform)
    sim_junction = workspace / "simulated_junction"
    sim_junction.mkdir()
    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    orig_lstat = os.lstat

    class MockStatResult:
        def __init__(self, orig: os.stat_result) -> None:
            self._orig = orig
            self.st_file_attributes = (
                getattr(orig, "st_file_attributes", 0) | reparse_flag
            )
            self.st_mode = orig.st_mode

        def __getattr__(self, name: str) -> object:
            return getattr(self._orig, name)

    def mock_lstat(
        path: os.PathLike[str] | str, *args: object, **kwargs: object
    ) -> object:
        st = orig_lstat(path, *args, **kwargs)
        if Path(path) == sim_junction:
            return MockStatResult(st)
        return st

    monkeypatch.setattr(os, "lstat", mock_lstat)
    with pytest.raises(ScopeWideningError):
        resolve_target(workspace, "simulated_junction/payload.txt")
    with pytest.raises(ScopeWideningError):
        build_physical_targets(workspace, ["simulated_junction/payload.txt"])
    monkeypatch.undo()

    # 5. Parent target swap race condition simulation (candidate resolves outside workspace)
    orig_resolve = Path.resolve

    def fake_resolve(self: Path, *args: object, **kwargs: object) -> Path:
        if "normal_file" in str(self):
            return outside_jail / "swapped.txt"
        return orig_resolve(self, *args, **kwargs)

    monkeypatch.setattr(Path, "resolve", fake_resolve)
    with pytest.raises(ScopeWideningError):
        resolve_target(workspace, "normal_file.txt")
    with pytest.raises(ScopeWideningError):
        build_physical_targets(workspace, ["normal_file.txt"])
    monkeypatch.undo()


def test_undeclared_host_input_refuses(tmp_path: Path) -> None:
    """T-57.06: Verify undeclared host inputs and unlisted candidates fail-closed with UndeclaredInputError."""
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    outside = tmp_path / "outside_host"
    outside.mkdir()

    external_file = outside / "host_sensitive.txt"
    external_file.write_text("HOST_DATA\n", encoding="utf-8")

    declared_file = workspace / "declared_target.py"
    declared_file.write_text("print('declared')\n", encoding="utf-8")

    untracked_file = workspace / "untracked_target.py"
    untracked_file.write_text("print('untracked')\n", encoding="utf-8")

    # 1. Absolute host path outside workspace raises UndeclaredInputError fail-closed
    with pytest.raises(UndeclaredInputError):
        resolve_target(workspace, external_file)

    with pytest.raises(UndeclaredInputError):
        resolve_target(workspace, str(external_file))

    with pytest.raises(UndeclaredInputError):
        build_physical_targets(workspace, [external_file])

    # Universal host paths outside workspace
    for disallowed_host in (
        "/etc/passwd",
        "C:/Windows/System32/drivers/etc/hosts",
        "D:\\external.py",
    ):
        with pytest.raises(UndeclaredInputError):
            resolve_target(workspace, disallowed_host)

    # 2. Declared inputs policy: untracked candidates not in declared_inputs raise UndeclaredInputError
    declared_set = ("declared_target.py",)

    # Declared target resolves successfully
    target = resolve_target(
        workspace, "declared_target.py", declared_inputs=declared_set
    )
    assert target.relative_path == Path("declared_target.py")
    assert target.state == "present"

    # Untracked target raises UndeclaredInputError
    with pytest.raises(UndeclaredInputError):
        resolve_target(workspace, "untracked_target.py", declared_inputs=declared_set)

    with pytest.raises(UndeclaredInputError):
        build_physical_targets(
            workspace, ["untracked_target.py"], declared_inputs=declared_set
        )

    with pytest.raises(UndeclaredInputError):
        build_physical_targets(
            workspace,
            ["declared_target.py", "untracked_target.py"],
            declared_inputs=declared_set,
        )
