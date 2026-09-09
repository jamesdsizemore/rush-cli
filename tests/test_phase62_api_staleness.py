"""Contract tests T-62.11, T-62.26 for API-diff staleness (Phase 62 §6.5 Invariant 5)."""

from __future__ import annotations

import subprocess
import time
import uuid
from pathlib import Path

import rush.hook  # noqa: F401 -- resolves pre-existing order-dependent circular import (T010 precedent)
from rush.memory.merkle_invalidator import MerkleInvalidator
from rush.memory.store import MemoryArtifact, TypedArtifactStore
from rush.tools.api_diff import ApiDiffer


def _git(args: list[str], cwd: Path) -> None:
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True)


def _init_repo(tmp_path: Path) -> None:
    _git(["init", "-b", "main"], tmp_path)
    _git(["config", "user.email", "test@example.com"], tmp_path)
    _git(["config", "user.name", "Test"], tmp_path)


def _artifact(**overrides) -> MemoryArtifact:
    defaults = {
        "id": str(uuid.uuid4()),
        "family": "memory",
        "subject": "domain_knowledge",
        "trust_tier": "DERIVED",
        "content": {"note": "default content"},
        "source": "test",
        "created_at": time.time(),
    }
    defaults.update(overrides)
    return MemoryArtifact(**defaults)


def test_signature_break_flags_stale_via_main_diff_when_merkle_baseline_predates_it(
    tmp_path: Path,
):
    _init_repo(tmp_path)
    target = tmp_path / "app.py"

    pre_break = "def public_api(arg1: int, arg2: str) -> bool:\n    return True\n"
    target.write_text(pre_break, encoding="utf-8")
    _git(["add", "app.py"], tmp_path)
    _git(["commit", "-m", "pre-break"], tmp_path)

    post_break = "def public_api(arg1: int) -> bool:\n    return True\n"
    target.write_text(post_break, encoding="utf-8")

    merkle = MerkleInvalidator(project_root=tmp_path)
    symbol_key = "app.py::public_api"
    # Merkle-hash the *current* (post-break) on-disk content -> baseline matches with
    # zero drift going forward, isolating stale=True to the ApiDiffer path only.
    merkle.check_and_update(symbol_key, post_break)
    current_hash = merkle.hash_content(post_break)

    store = TypedArtifactStore(project_root=tmp_path)
    store.write(
        _artifact(
            content={"note": "signaturebreak marker"},
            symbol_ref=symbol_key,
            content_hash=current_hash,
        )
    )

    differ = ApiDiffer(project_root=tmp_path)
    result = differ.diff_symbol(target, "public_api", base_ref="main")
    assert result is not None
    assert result != "unknown"
    assert result["symbol"] == "public_api"

    results = store.recall(
        "domain_knowledge", "signaturebreak", session_allowlist=["test"]
    )
    assert len(results) == 1
    assert results[0].stale is True

    # Merkle baseline already reflects current content -> no drift on a subsequent check,
    # proving the two staleness checks fire independently off different baselines.
    assert merkle.check_and_update(symbol_key, post_break) is False


def test_unavailable_base_ref_reports_unknown_not_fresh(tmp_path: Path):
    _init_repo(tmp_path)
    target = tmp_path / "app.py"

    code = "def public_api(arg1: int) -> bool:\n    return True\n"
    target.write_text(code, encoding="utf-8")
    _git(["add", "app.py"], tmp_path)
    _git(["commit", "-m", "initial"], tmp_path)

    merkle = MerkleInvalidator(project_root=tmp_path)
    current_hash = merkle.hash_content(code)  # matches on-disk content: no merkle drift

    store = TypedArtifactStore(project_root=tmp_path)
    store.write(
        _artifact(
            content={"note": "unknownrefcheck marker"},
            symbol_ref="app.py::public_api",
            content_hash=current_hash,
            stale=True,  # already flagged stale by a prior merkle cycle
        )
    )

    differ = ApiDiffer(project_root=tmp_path)
    result = differ.diff_symbol(target, "public_api", base_ref="nonexistent-branch")
    assert result == "unknown"

    results = store.recall(
        "domain_knowledge", "unknownrefcheck", session_allowlist=["test"]
    )
    assert len(results) == 1
    # Merkle recompute finds no drift and the ApiDiffer result is "unknown" -- neither
    # sets stale=True on its own, but the pre-existing flag must survive unmodified.
    assert results[0].stale is True
