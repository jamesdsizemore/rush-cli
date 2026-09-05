from __future__ import annotations

import ast
import json
import tempfile
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from rush.io.atomic_file import (
    AtomicFile,
    AtomicWriteError,
    SanitizedBytes,
    SanitizedJsonValue,
)
from rush.io.physical_paths import PhysicalRoot
from rush.safety.redactor import SanitizationResult


def test_atomic_file_accepts_only_sanitized_contracts(tmp_path: Path) -> None:
    """T-55.01: Asserts write_bytes and write_json accept only sanitized contracts and reject raw types."""
    phy_root = PhysicalRoot(tmp_path)
    atomic = AtomicFile(phy_root)

    # 1. Raw types must fail-closed with TypeError
    # write_bytes:
    with pytest.raises(TypeError, match=r"sanitized contracts"):
        atomic.write_bytes("dest.bin", b"raw unredacted bytes")  # type: ignore[arg-type]

    with pytest.raises(TypeError, match=r"sanitized contracts"):
        atomic.write_bytes("dest.bin", "raw unredacted string")  # type: ignore[arg-type]

    with pytest.raises(TypeError, match=r"sanitized contracts"):
        atomic.write_bytes("dest.bin", {"untrusted": "dict"})  # type: ignore[arg-type]

    # write_json:
    with pytest.raises(TypeError, match=r"sanitized contracts"):
        atomic.write_json("dest.json", b"raw unredacted bytes")  # type: ignore[arg-type]

    with pytest.raises(TypeError, match=r"sanitized contracts"):
        atomic.write_json("dest.json", "raw unredacted string")  # type: ignore[arg-type]

    with pytest.raises(TypeError, match=r"sanitized contracts"):
        atomic.write_json("dest.json", {"untrusted": "dict"})  # type: ignore[arg-type]

    # 2. Sanitized contracts must be accepted and written correctly
    sanitized_bytes = SanitizedBytes.from_bytes(b"safe bytes")
    assert isinstance(sanitized_bytes, SanitizedBytes)
    sanitization_res_bytes = SanitizationResult(value="safe text")
    sanitized_json = SanitizedJsonValue.from_value({"safe": "value"})
    assert isinstance(sanitized_json, SanitizedJsonValue)
    sanitization_res_json = SanitizationResult(value={"safe": "value"})

    p1 = atomic.write_bytes("dest_bytes.bin", sanitized_bytes)
    assert p1.read_bytes() == b"safe bytes"

    p2 = atomic.write_bytes("dest_san_bytes.bin", sanitization_res_bytes)
    assert p2.read_bytes() == b"safe text"

    p3 = atomic.write_json("dest_json.json", sanitized_json)
    assert json.loads(p3.read_text(encoding="utf-8")) == {"safe": "value"}

    p4 = atomic.write_json("dest_san_json.json", sanitization_res_json)
    assert json.loads(p4.read_text(encoding="utf-8")) == {"safe": "value"}


def test_atomic_file_has_one_implementation_owner() -> None:
    """T-55.02: Scans AST across src/rush/ asserting AtomicFile is defined exclusively in src/rush/io/atomic_file.py."""
    src_rush = Path(__file__).resolve().parent.parent / "src" / "rush"
    assert src_rush.is_dir(), f"src/rush not found at {src_rush}"

    definitions: list[Path] = []
    for py_file in src_rush.rglob("*.py"):
        try:
            tree = ast.parse(py_file.read_text(encoding="utf-8"), filename=str(py_file))
        except (SyntaxError, UnicodeDecodeError):
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef) and node.name == "AtomicFile":
                definitions.append(py_file.resolve())

    expected_file = (src_rush / "io" / "atomic_file.py").resolve()
    assert len(definitions) == 1, (
        f"AtomicFile must be defined in exactly one place, found in: {definitions}"
    )
    assert definitions[0] == expected_file, (
        f"AtomicFile defined at unexpected location: {definitions[0]}, expected {expected_file}"
    )


def test_raw_secret_wrapper_is_rejected(tmp_path: Path) -> None:
    """T-55.03: Asserts that mock or custom wrappers attempting to bypass sanitized contracts cannot be passed."""

    class FakeBytesWrapper:
        def __init__(self) -> None:
            self.data = b"secret_bytes"
            self.redaction_count = 0

    class FakeJsonWrapper:
        def __init__(self) -> None:
            self.value = {"unredacted_key": "unredacted_secret"}
            self.redaction_count = 0

    class CustomBypass:
        def __init__(self, data: Any) -> None:
            self.data = data
            self.value = data

    phy_root = PhysicalRoot(tmp_path)
    atomic = AtomicFile(phy_root)

    with pytest.raises(TypeError, match=r"sanitized contracts"):
        atomic.write_bytes("dest.bin", FakeBytesWrapper())  # type: ignore[arg-type]

    with pytest.raises(TypeError, match=r"sanitized contracts"):
        atomic.write_json("dest.json", FakeJsonWrapper())  # type: ignore[arg-type]

    with pytest.raises(TypeError, match=r"sanitized contracts"):
        atomic.write_bytes("dest.bin", CustomBypass(b"raw"))  # type: ignore[arg-type]

    with pytest.raises(TypeError, match=r"sanitized contracts"):
        atomic.write_json("dest.json", CustomBypass({"raw": 1}))  # type: ignore[arg-type]

    with pytest.raises(TypeError, match=r"sanitized contracts"):
        atomic.write_bytes("dest.bin", MagicMock())  # type: ignore[arg-type]

    with pytest.raises(TypeError, match=r"sanitized contracts"):
        atomic.write_json("dest.json", MagicMock())  # type: ignore[arg-type]


def test_each_injected_fault_leaves_old_or_new_valid_destination(
    tmp_path: Path,
) -> None:
    """T-55.04: Injects faults at write, flush, fsync, and replace; asserts old or new valid destination invariant."""
    root = tmp_path / "workspace"
    root.mkdir()
    phy_root = PhysicalRoot(root)
    atomic = AtomicFile(phy_root)

    target_rel = "data/target.txt"
    target_full = root / target_rel
    target_full.parent.mkdir(parents=True, exist_ok=True)

    initial_content = b"ORIGINAL_VALID_PAYLOAD_V1"
    new_content = SanitizedBytes.from_bytes(b"NEW_VALID_PAYLOAD_V2")

    class FaultyTempFile:
        def __init__(self, real_f: Any, fail_on: str) -> None:
            self._real = real_f
            self.name = real_f.name
            self._fail_on = fail_on

        def write(self, b: bytes) -> int:
            if self._fail_on == "write":
                raise OSError("Simulated disk write fault")
            return self._real.write(b)

        def flush(self) -> None:
            if self._fail_on == "flush":
                raise OSError("Simulated flush fault")
            self._real.flush()

        def fileno(self) -> int:
            return self._real.fileno()

        def close(self) -> None:
            self._real.close()

        def __enter__(self) -> Any:
            return self

        def __exit__(self, exc_type: object, exc_val: object, exc_tb: object) -> Any:
            return self._real.__exit__(exc_type, exc_val, exc_tb)

        def __getattr__(self, name: str) -> Any:
            return getattr(self._real, name)

    # Fault 1: Error during write
    target_full.write_bytes(initial_content)
    orig_ntf = tempfile.NamedTemporaryFile
    with (
        patch(
            "tempfile.NamedTemporaryFile",
            side_effect=lambda *args, **kwargs: FaultyTempFile(
                orig_ntf(*args, **kwargs), fail_on="write"
            ),
        ),
        pytest.raises(AtomicWriteError),
    ):
        atomic.write_bytes(target_rel, new_content)
    assert target_full.read_bytes() == initial_content
    temp_files = list(target_full.parent.glob(".rush_tmp_*"))
    assert temp_files == [], f"Found leaked temp files after write fault: {temp_files}"

    # Fault 2: Error during flush
    target_full.write_bytes(initial_content)
    with (
        patch(
            "tempfile.NamedTemporaryFile",
            side_effect=lambda *args, **kwargs: FaultyTempFile(
                orig_ntf(*args, **kwargs), fail_on="flush"
            ),
        ),
        pytest.raises(AtomicWriteError),
    ):
        atomic.write_bytes(target_rel, new_content)
    assert target_full.read_bytes() == initial_content
    temp_files = list(target_full.parent.glob(".rush_tmp_*"))
    assert temp_files == [], f"Found leaked temp files after flush fault: {temp_files}"

    # Fault 3: Error during fsync
    target_full.write_bytes(initial_content)
    with (
        patch("os.fsync", side_effect=OSError("Simulated fsync durability fault")),
        pytest.raises(AtomicWriteError),
    ):
        atomic.write_bytes(target_rel, new_content)
    assert target_full.read_bytes() == initial_content
    temp_files = list(target_full.parent.glob(".rush_tmp_*"))
    assert temp_files == [], f"Found leaked temp files after fsync fault: {temp_files}"

    # Fault 4: Error during replace
    target_full.write_bytes(initial_content)
    with (
        patch("os.replace", side_effect=OSError("Simulated replace swap fault")),
        pytest.raises(AtomicWriteError),
    ):
        atomic.write_bytes(target_rel, new_content)
    assert target_full.read_bytes() == initial_content
    temp_files = list(target_full.parent.glob(".rush_tmp_*"))
    assert temp_files == [], (
        f"Found leaked temp files after replace fault: {temp_files}"
    )

    # Non-existent target file: fault leaves no partial file
    non_existent_rel = "data/non_existent.txt"
    non_existent_full = root / non_existent_rel
    with (
        patch("os.replace", side_effect=OSError("Simulated replace fault on create")),
        pytest.raises(AtomicWriteError),
    ):
        atomic.write_bytes(non_existent_rel, new_content)
    assert not non_existent_full.exists(), (
        "Partial destination file must not exist on failure"
    )
    temp_files = list(non_existent_full.parent.glob(".rush_tmp_*"))
    assert temp_files == [], f"Found leaked temp files: {temp_files}"


def test_cleanup_removes_only_owned_temp_identity(tmp_path: Path) -> None:
    """T-55.05: Asserts cleanup on failure unlinks ONLY manager-owned temp file, leaving adjacent unowned files intact."""
    root = tmp_path / "cleanup_workspace"
    root.mkdir()
    phy_root = PhysicalRoot(root)
    atomic = AtomicFile(phy_root)

    target_rel = "config.json"
    target_full = root / target_rel
    initial_json = b'{"version": 1}'
    target_full.write_bytes(initial_json)

    # Place unowned files in directory matching temp pattern and ordinary siblings
    unowned_temp1 = root / ".rush_tmp_other_agent_12345.tmp"
    unowned_temp1.write_bytes(b"unowned temporary data from other process")

    unowned_temp2 = root / ".rush_tmp_prior_run.tmp"
    unowned_temp2.write_bytes(b"prior unowned temp")

    sibling_file = root / "unrelated_file.txt"
    sibling_file.write_text("do not delete me", encoding="utf-8")

    # Inject failure during atomic replace
    with (
        patch("os.replace", side_effect=OSError("Simulated replace failure")),
        pytest.raises(AtomicWriteError),
    ):
        atomic.write_json(
            target_rel,
            SanitizedJsonValue.from_value({"version": 2}),
        )

    # Verify destination file is preserved
    assert target_full.read_bytes() == initial_json

    # Verify unowned temporary files were NOT deleted
    assert unowned_temp1.exists(), "Unowned temp file 1 must not be deleted"
    assert unowned_temp1.read_bytes() == b"unowned temporary data from other process"

    assert unowned_temp2.exists(), "Unowned temp file 2 must not be deleted"
    assert unowned_temp2.read_bytes() == b"prior unowned temp"

    # Verify unrelated sibling was NOT deleted
    assert sibling_file.exists(), "Unrelated sibling file must not be deleted"
    assert sibling_file.read_text(encoding="utf-8") == "do not delete me"

    # Verify no leaked manager-owned temp files remain
    current_temps = set(root.glob(".rush_tmp_*"))
    expected_temps = {unowned_temp1, unowned_temp2}
    assert current_temps == expected_temps, (
        f"Extra leaked temp files found: {current_temps - expected_temps}"
    )
