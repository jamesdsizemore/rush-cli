"""Unit tests for Phase 43 CCR Store, GroundingVerifier, and HalluGuard."""

from pathlib import Path

from src.rush.codegraph.grounding_verifier import GroundingVerifier
from src.rush.token_economy.ccr_store import CCRStore
from src.rush.tools.hallu_guard import HalluGuard


def test_ccr_store_roundtrip(tmp_path: Path):
    store = CCRStore(project_root=tmp_path)
    large_payload = "def calculate():\n    return 42\n" * 50

    tag = store.store_chunk(large_payload)
    assert tag.startswith("<!-- ccr:chunk:")
    assert tag.endswith(" -->")

    chunk_hash = tag.split("<!-- ccr:chunk:")[1].split(" -->")[0]
    retrieved = store.retrieve_chunk(chunk_hash)
    assert retrieved == large_payload

    assert store.retrieve_chunk("nonexistent_hash") is None


def test_grounding_verifier_flags_phantom():
    verifier = GroundingVerifier()

    # Valid code with stdlib
    valid_code = "import json\nimport sys\nimport os\n"
    assert verifier.verify_code(valid_code) == []

    # Hallucinated package
    phantom_code = "import totally_fake_nonexistent_hallucinated_package\n"
    violations = verifier.verify_code(phantom_code)
    assert len(violations) >= 1
    assert "totally_fake_nonexistent_hallucinated_package" in violations[0]


def test_hallu_guard_file_check(tmp_path: Path):
    target = tmp_path / "valid.py"
    target.write_text("import math\nimport pathlib\n", encoding="utf-8")

    guard = HalluGuard(project_root=tmp_path)
    assert guard.check_file(target) == []
