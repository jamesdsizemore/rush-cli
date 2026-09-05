"""Contract tests for Pre-Spawn Reverification and Non-Substitutable Launch Identity.

Architecture §8, Phase 56 Workstream P56.4.
Contract Test Ledger:
- T-56.12: test_snapshot_runtime_dependency_and_link_replacement_yields_approved_bytes_or_no_child
- T-56.13: test_failed_verification_creates_no_child
"""

from __future__ import annotations

import hashlib
import os
import subprocess
import sys
from pathlib import Path

import pytest

from rush.contracts.results import ToolResultV1
from rush.io.physical_paths import ContainmentError
from rush.plugins.closure import (
    ClosureTamperedError,
    PluginClosureManifest,
    build_plugin_closure,
)
from rush.plugins.executor import HardenedPluginExecutor
from rush.plugins.loader import PluginSpec
from rush.plugins.snapshot_store import PluginSnapshotStore
from rush.plugins.trust_store import (
    PluginTrustError,
    PluginTrustStore,
)


def _build_test_plugin(plugin_dir: Path) -> tuple[Path, Path]:
    plugin_dir.mkdir(parents=True, exist_ok=True)
    main_py = plugin_dir / "main.py"
    dep_py = plugin_dir / "dep.py"

    main_py.write_text(
        "import json\n"
        "import dep\n"
        "result = {\n"
        "    'schema_version': '1.0.0',\n"
        "    'tool': 'plugin',\n"
        "    'engine': 'sample_plugin',\n"
        "    'engine_version': '1.0.0',\n"
        "    'status': 'ok',\n"
        "    'duration_ms': 5,\n"
        "    'summary': 'Plugin completed',\n"
        "    'findings': [{\n"
        "        'path': 'test.py',\n"
        "        'line': 1,\n"
        "        'column': 1,\n"
        "        'rule_id': 'VERIFIED_RUN',\n"
        "        'severity': 'info',\n"
        "        'message': dep.get_message(),\n"
        "        'fingerprint': '0' * 64,\n"
        "    }],\n"
        "}\n"
        "print(json.dumps(result))\n",
        encoding="utf-8",
    )

    dep_py.write_text(
        "def get_message() -> str:\n    return 'APPROVED_BYTES'\n",
        encoding="utf-8",
    )
    return main_py, dep_py


def test_snapshot_runtime_dependency_and_link_replacement_yields_approved_bytes_or_no_child(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """T-56.12: Simulates TOCTOU race mutating workspace or snapshot files right before launch.

    Asserts:
    1. Post-approval mutation in workspace runs unmodified snapshot files, yielding approved bytes.
    2. Post-approval mutation or link substitution in snapshot fails pre-spawn reverification,
       raises ClosureTamperedError, and verifies child process counter strictly equals 0.
    """
    repo_root = tmp_path / "repo"
    repo_root.mkdir(parents=True)
    plugin_dir = repo_root / "plugins" / "sample_plugin"
    main_py, dep_py = _build_test_plugin(plugin_dir)

    target_file = repo_root / "target.py"
    target_file.write_text("# target\n", encoding="utf-8")

    closure = build_plugin_closure(
        plugin_root=plugin_dir,
        entrypoint=main_py,
        config={"name": "sample_plugin", "command": [sys.executable, "main.py"]},
        plugin_name="sample_plugin",
    )

    snapshots_root = tmp_path / "user_home" / ".rush" / "snapshots"
    snapshot_store = PluginSnapshotStore(snapshots_root=snapshots_root)
    snapshot_dir = snapshot_store.materialize_snapshot(
        closure=closure, plugin_root=plugin_dir
    )

    ledger_path = tmp_path / "user_home" / ".rush" / "plugin_trust_ledger.json"
    trust_store = PluginTrustStore(repo_root=repo_root, ledger_path=ledger_path)
    trust_store.grant_trust("sample_plugin", closure.closure_digest, snapshot_dir)

    executor = HardenedPluginExecutor(
        repo_root=repo_root,
        trust_store=trust_store,
        snapshot_store=snapshot_store,
    )

    plugin_spec = PluginSpec(
        name="sample_plugin",
        executable_path=main_py,
        command=[sys.executable, "main.py"],
        closure=closure,
    )

    # Track every spawned child process strictly
    child_spawn_count = 0
    orig_popen = subprocess.Popen

    def counting_popen(*args, **kwargs):
        nonlocal child_spawn_count
        child_spawn_count += 1
        return orig_popen(*args, **kwargs)

    monkeypatch.setattr(subprocess, "Popen", counting_popen)

    # --- Case 1: TOCTOU race in workspace files ---
    # Attacker mutates workspace dependency and entrypoint right before launch
    dep_py.write_text(
        "def get_message() -> str:\n    return 'MUTATED_WORKSPACE_PAYLOAD'\n",
        encoding="utf-8",
    )
    main_py.write_text("import sys; sys.exit(99)\n", encoding="utf-8")

    result = executor.execute(plugin_spec, [target_file])

    # Asserts execution runs from snapshot, yielding approved bytes
    assert isinstance(result, ToolResultV1)
    assert result.status == "ok"
    assert len(result.findings) == 1
    assert result.findings[0].message == "APPROVED_BYTES"
    assert child_spawn_count == 1

    # --- Case 2: TOCTOU race mutating snapshot file directly ---
    child_spawn_count = 0
    snap_dep = snapshot_dir / "dep.py"
    snap_dep.write_text(
        "def get_message() -> str:\n    return 'TAMPERED_SNAPSHOT_EXPLOIT'\n",
        encoding="utf-8",
    )

    with pytest.raises(ClosureTamperedError):
        executor.execute(plugin_spec, [target_file])

    # Strict zero-child invariant: pre-spawn reverification catches hash mismatch
    assert child_spawn_count == 0

    # --- Case 3: TOCTOU race replacing snapshot file with a link or corrupting ---
    child_spawn_count = 0
    snap_dep.unlink()
    outside_tampered = tmp_path / "outside_tampered.py"
    outside_tampered.write_text("MALICIOUS = True\n", encoding="utf-8")

    try:
        os.symlink(outside_tampered, snap_dep)
    except OSError:
        # Fallback for environments without symlink privileges
        snap_dep.write_text("CORRUPTED_BYTES", encoding="utf-8")

    with pytest.raises((ClosureTamperedError, ContainmentError)):
        executor.execute(plugin_spec, [target_file])

    # Strict zero-child invariant: link replacement or missing file aborts before spawn
    assert child_spawn_count == 0


def test_failed_verification_creates_no_child(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """T-56.13: Asserts verification failures (missing trust, corrupt snapshot, runtime mismatch) create zero child processes."""
    repo_root = tmp_path / "repo"
    repo_root.mkdir(parents=True)
    plugin_dir = repo_root / "plugins" / "sample_plugin"
    main_py, _ = _build_test_plugin(plugin_dir)

    target_file = repo_root / "target.py"
    target_file.write_text("# target\n", encoding="utf-8")

    closure = build_plugin_closure(
        plugin_root=plugin_dir,
        entrypoint=main_py,
        config={"name": "sample_plugin", "command": [sys.executable, "main.py"]},
        plugin_name="sample_plugin",
    )

    snapshots_root = tmp_path / "user_home" / ".rush" / "snapshots"
    snapshot_store = PluginSnapshotStore(snapshots_root=snapshots_root)
    snapshot_dir = snapshot_store.materialize_snapshot(
        closure=closure, plugin_root=plugin_dir
    )

    ledger_path = tmp_path / "user_home" / ".rush" / "plugin_trust_ledger.json"
    trust_store = PluginTrustStore(repo_root=repo_root, ledger_path=ledger_path)

    executor = HardenedPluginExecutor(
        repo_root=repo_root,
        trust_store=trust_store,
        snapshot_store=snapshot_store,
    )

    plugin_spec = PluginSpec(
        name="sample_plugin",
        executable_path=main_py,
        command=[sys.executable, "main.py"],
        closure=closure,
    )

    child_spawn_count = 0

    def forbidden_popen(*args, **kwargs):
        nonlocal child_spawn_count
        child_spawn_count += 1
        raise AssertionError(
            "Child process must not be spawned on verification failure!"
        )

    monkeypatch.setattr(subprocess, "Popen", forbidden_popen)

    # 1. Missing Trust failure
    result_untrusted = executor.execute(plugin_spec, [target_file])
    assert isinstance(result_untrusted, ToolResultV1)
    assert result_untrusted.status == "skipped"
    assert any(
        f.rule_id == "untrusted-plugin-execution-blocked"
        for f in result_untrusted.findings
    )
    assert child_spawn_count == 0

    # Grant trust now for subsequent verification tests
    trust_store.grant_trust("sample_plugin", closure.closure_digest, snapshot_dir)

    # 2. Corrupted Snapshot File failure
    (snapshot_dir / "main.py").write_text("CORRUPTED", encoding="utf-8")
    with pytest.raises(PluginTrustError):
        executor.execute(plugin_spec, [target_file])
    assert child_spawn_count == 0

    # 3. Runtime Mismatch failure
    # Restore main.py so snapshot is clean
    (snapshot_dir / "main.py").write_text(main_py.read_text(encoding="utf-8"))

    mismatched_digest = hashlib.sha256(
        b"mismatched_runtime_closure_payload"
    ).hexdigest()
    mismatched_closure = PluginClosureManifest(
        schema_version="1.0.0",
        plugin_name="sample_plugin",
        entrypoint="main.py",
        file_manifest=dict(closure.file_manifest),
        config_digest=closure.config_digest,
        allowed_env_names=closure.allowed_env_names,
        declared_secret_refs=closure.declared_secret_refs,
        runtime_identity="python3.9:foreign_runtime:deadbeefcafebabe0123456789abcdef",
        platform_identity=closure.platform_identity,
        closure_digest=mismatched_digest,
    )
    trust_store.grant_trust("sample_plugin", mismatched_digest, snapshot_dir)
    mismatched_spec = PluginSpec(
        name="sample_plugin",
        executable_path=main_py,
        command=[sys.executable, "main.py"],
        closure=mismatched_closure,
    )

    with pytest.raises(PluginTrustError):
        executor.execute(mismatched_spec, [target_file])
    assert child_spawn_count == 0
