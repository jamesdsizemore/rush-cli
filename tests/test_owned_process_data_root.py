"""An owned execution binds its data root once, when it starts.

An owned child's `.procs` record must land under the data root that was in
force when the owner's execution began -- never under whatever
`default_data_root()` happens to return later, when the child is actually
recorded or released (e.g. on a background scan thread that outlives the
resolver it started under).
"""

from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from rush.runtime import subprocesses
from rush.setup import provision as provision_module


def _procs(root: Path, owner: str) -> Path:
    return root / "owners" / f"{owner}.procs"


def test_owned_process_record_uses_the_data_root_bound_at_owner_start(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root_a = tmp_path / "root-a"
    root_b = tmp_path / "root-b"
    monkeypatch.setattr(provision_module, "default_data_root", lambda: root_a)

    with subprocesses.owned_execution_scope("owner-bound", "run-bound"):
        monkeypatch.setattr(provision_module, "default_data_root", lambda: root_b)
        subprocesses._record_owned_process("owner-bound", "run-bound", 4242)

        assert _procs(root_a, "owner-bound").exists()
        assert not _procs(root_b, "owner-bound").exists()
        records = subprocesses.read_owned_process_records("owner-bound")
        assert [r["pgid"] for r in records] == [4242]

        subprocesses._clear_owned_process_record("owner-bound", 4242)
        assert not _procs(root_a, "owner-bound").exists()
        assert not _procs(root_b, "owner-bound").exists()

    # Outside an owned execution the resolver is still consulted lazily.
    subprocesses._record_owned_process("owner-bound", "run-after", 4343)
    assert _procs(root_b, "owner-bound").exists()
    assert not _procs(root_a, "owner-bound").exists()


def test_owned_process_record_never_resolves_the_default_root_late(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root_a = tmp_path / "root-a"
    root_b = tmp_path / "root-b"
    resolved = {"root": root_a}
    monkeypatch.setattr(provision_module, "default_data_root", lambda: resolved["root"])
    started = threading.Event()
    resolver_changed = threading.Event()

    def owner_worker() -> None:
        with subprocesses.owned_execution_scope("owner-late", "run-late"):
            started.set()
            assert resolver_changed.wait(timeout=10)
            subprocesses._record_owned_process("owner-late", "run-late", 5151)

    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(owner_worker)
        try:
            assert started.wait(timeout=10)
            resolved["root"] = root_b
        finally:
            resolver_changed.set()
        future.result(timeout=10)  # re-raises any worker failure here

    assert _procs(root_a, "owner-late").exists()
    assert not _procs(root_b, "owner-late").exists()
    assert not (root_b / "owners").exists()
