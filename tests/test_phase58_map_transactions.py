"""Contract tests for Phase 58: Map Transactions and Concurrency (P58.3)."""

from __future__ import annotations

import hashlib
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

import pytest

from rush.memory.invariant_graph import InvariantGraph
from rush.memory.merkle_invalidator import MerkleInvalidator
from rush.memory.preference_store import PreferenceStore
from rush.memory.transactions import (
    CASConflictError,
    CASMapTransaction,
    StoreCorruptionError,
    StoreError,
    StoreIOError,
    StoreNotFoundError,
    StoreValidationError,
)


def test_invariant_preference_and_merkle_maps_preserve_concurrent_updates(
    tmp_path: Path,
) -> None:
    """T-58.08: Parallel CAS updates across stores preserve monotonic versioning without lost updates."""
    pref = PreferenceStore(tmp_path)
    inv = InvariantGraph(tmp_path)
    merkle = MerkleInvalidator(tmp_path)

    n_workers = 15

    def update_pref(idx: int) -> None:
        pref.set(f"pref_key_{idx}", f"pref_val_{idx}")

    def update_inv(idx: int) -> None:
        inv.add_invariant(f"INV_{idx:03d}", f"desc_{idx}", f"rationale_{idx}")

    def update_merkle(idx: int) -> None:
        changed = merkle.check_and_update(f"sym_{idx}", f"code_content_{idx}")
        assert changed is True

    futures = []
    with ThreadPoolExecutor(max_workers=8) as pool:
        for i in range(n_workers):
            futures.append(pool.submit(update_pref, i))
            futures.append(pool.submit(update_inv, i))
            futures.append(pool.submit(update_merkle, i))

        for f in as_completed(futures):
            f.result()

    # PreferenceStore assertions
    pref_all = pref.list_all()
    assert len(pref_all) == n_workers
    for i in range(n_workers):
        assert pref.get(f"pref_key_{i}") == f"pref_val_{i}"
    pref_snap = pref.tx.read()
    assert pref_snap.version == n_workers
    assert len(pref_snap.content_hash) == 64

    # InvariantGraph assertions
    inv_all = inv.get_all()
    assert len(inv_all) == n_workers
    for i in range(n_workers):
        assert f"INV_{i:03d}" in inv_all
        assert inv_all[f"INV_{i:03d}"]["description"] == f"desc_{i}"
    inv_snap = inv.tx.read()
    assert inv_snap.version == n_workers
    assert len(inv_snap.content_hash) == 64

    # MerkleInvalidator assertions
    merkle_data = merkle._read()
    assert len(merkle_data) == n_workers
    for i in range(n_workers):
        expected_hash = merkle.hash_content(f"code_content_{i}")
        assert merkle_data[f"sym_{i}"] == expected_hash
    merkle_snap = merkle.tx.read()
    assert merkle_snap.version == n_workers
    assert len(merkle_snap.content_hash) == 64


def test_map_absent_corrupt_invalid_io_are_distinct(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """T-58.09: Injects absent, corrupt, invalid schema, and disk fault errors.

    Asserts all 4 are distinct typed exceptions and corrupt files are NEVER treated as empty dicts.
    """
    # 1. Assert all typed exceptions are distinct subclasses of StoreError
    exceptions = [
        StoreNotFoundError,
        StoreCorruptionError,
        StoreValidationError,
        StoreIOError,
        CASConflictError,
    ]
    assert len(set(exceptions)) == 5
    for exc_cls in exceptions:
        assert issubclass(exc_cls, StoreError)
        for other_cls in exceptions:
            if exc_cls is not other_cls:
                assert not issubclass(exc_cls, other_cls)

    # 2. Absent file handling
    absent_file = tmp_path / ".rush" / "absent.json"
    tx_absent = CASMapTransaction(file_path=absent_file, root_path=tmp_path)
    with pytest.raises(StoreNotFoundError):
        tx_absent.read(allow_missing=False)

    snapshot_empty = tx_absent.read(allow_missing=True)
    assert snapshot_empty.version == 0
    assert snapshot_empty.data == {}
    assert snapshot_empty.content_hash == ""

    # 3. Corrupt garbage bytes handling
    corrupt_file = tmp_path / ".rush" / "corrupt.json"
    corrupt_bytes = b"\x00\xff\xfeBadUtf8\x80\x81\x00NotJson"
    corrupt_file.parent.mkdir(parents=True, exist_ok=True)
    corrupt_file.write_bytes(corrupt_bytes)

    expected_digest = hashlib.sha256(corrupt_bytes).hexdigest()
    tx_corrupt = CASMapTransaction(file_path=corrupt_file, root_path=tmp_path)

    with pytest.raises(StoreCorruptionError) as corrupt_exc:
        tx_corrupt.read(allow_missing=True)
    assert corrupt_exc.value.raw_bytes == corrupt_bytes
    assert corrupt_exc.value.digest == expected_digest

    # Corrupt store file must NEVER be treated as an empty dict by memory stores
    pref_store = PreferenceStore(tmp_path)
    pref_store.store_file.write_bytes(corrupt_bytes)
    with pytest.raises(StoreCorruptionError):
        pref_store.get("some_key")
    with pytest.raises(StoreCorruptionError):
        pref_store.list_all()

    inv_store = InvariantGraph(tmp_path)
    inv_store.graph_file.write_bytes(corrupt_bytes)
    with pytest.raises(StoreCorruptionError):
        inv_store.get_all()

    merkle_store = MerkleInvalidator(tmp_path)
    merkle_store.cache_file.write_bytes(corrupt_bytes)
    with pytest.raises(StoreCorruptionError):
        merkle_store.check_and_update("sym", "content")

    # 4. Invalid schema handling
    invalid_schema_file = tmp_path / ".rush" / "invalid_schema.json"
    # Case A: valid JSON but missing version and data
    invalid_schema_file.write_text(json.dumps({"arbitrary": "data"}), encoding="utf-8")
    tx_invalid = CASMapTransaction(file_path=invalid_schema_file, root_path=tmp_path)
    with pytest.raises(StoreValidationError):
        tx_invalid.read(allow_missing=True)

    # Case B: version is not an integer
    invalid_schema_file.write_text(
        json.dumps({"version": "v1", "data": {}}), encoding="utf-8"
    )
    with pytest.raises(StoreValidationError):
        tx_invalid.read(allow_missing=True)

    # Case C: data is not a dict
    invalid_schema_file.write_text(
        json.dumps({"version": 1, "data": ["item1", "item2"]}), encoding="utf-8"
    )
    with pytest.raises(StoreValidationError):
        tx_invalid.read(allow_missing=True)

    # 5. Disk fault / I/O error handling
    io_file = tmp_path / ".rush" / "io_target.json"
    tx_io = CASMapTransaction(file_path=io_file, root_path=tmp_path)
    tx_io.write({"initial": True}, expected_version=0)

    # Read disk fault
    def fail_read_bytes(*args: Any, **kwargs: Any) -> bytes:
        raise OSError("Simulated hardware sector read failure")

    monkeypatch.setattr(Path, "read_bytes", fail_read_bytes)
    with pytest.raises(StoreIOError):
        tx_io.read()
    monkeypatch.undo()

    # Write disk fault
    def fail_write_json(*args: Any, **kwargs: Any) -> Path:
        raise OSError("Simulated disk full write failure")

    monkeypatch.setattr("rush.io.atomic_file.AtomicFile.write_json", fail_write_json)
    with pytest.raises(StoreIOError):
        tx_io.write({"updated": True}, expected_version=1)


def test_cas_conflict_retries_and_fails_closed(tmp_path: Path) -> None:
    """T-58.10: CAS version conflicts trigger bounded retries and fail-closed on exhaustion."""
    store_file = tmp_path / ".rush" / "cas_conflict.json"
    tx = CASMapTransaction(file_path=store_file, root_path=tmp_path)

    # Initial write
    snap1 = tx.write({"count": 1}, expected_version=0)
    assert snap1.version == 1
    assert snap1.data == {"count": 1}

    # Direct mismatched expected_version raises CASConflictError
    with pytest.raises(CASConflictError):
        tx.write({"count": 2}, expected_version=0)  # current is 1

    # State remains unmodified (fail-closed)
    assert tx.read().version == 1
    assert tx.read().data == {"count": 1}

    # Verify bounded retries up to max_retries and fail-closed CASConflictError on exhaustion
    attempts = 0

    def always_conflicting_mutator(d: dict[str, Any]) -> dict[str, Any]:
        nonlocal attempts
        attempts += 1
        # Simulate concurrent write before this update writes
        concurrent_tx = CASMapTransaction(file_path=store_file, root_path=tmp_path)
        cur = concurrent_tx.read()
        concurrent_tx.write(
            {"count": cur.data["count"] + 10}, expected_version=cur.version
        )
        d["count"] += 1
        return d

    with pytest.raises(CASConflictError):
        tx.update(always_conflicting_mutator, max_retries=3)

    assert attempts == 3

    # Verify that a transient conflict within max_retries succeeds
    retry_count = 0

    def retry_once_mutator(d: dict[str, Any]) -> dict[str, Any]:
        nonlocal retry_count
        retry_count += 1
        if retry_count == 1:
            # Cause a single concurrent conflict on the first attempt
            concurrent_tx = CASMapTransaction(file_path=store_file, root_path=tmp_path)
            cur = concurrent_tx.read()
            concurrent_tx.write({"count": 500}, expected_version=cur.version)
        d["count"] += 1
        return d

    recovered = tx.update(retry_once_mutator, max_retries=3)
    assert retry_count == 2
    assert recovered.data["count"] == 501
