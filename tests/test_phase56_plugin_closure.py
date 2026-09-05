"""Phase 56 Workstream P56.2: Transitive Closure & Content-Addressed Snapshot Contract Tests.

Contract Test Ledger:
- T-56.06: test_closure_digest_covers_every_code_and_behavior_input
- T-56.07: test_snapshot_contains_copied_bytes_not_links
- T-56.08: test_post_approval_mutation_uses_snapshot_or_denies
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path

try:
    import _winapi
except ImportError:
    _winapi = None  # type: ignore[assignment]

import pytest

from rush.io.physical_paths import ContainmentError
from rush.plugins.closure import (
    PluginClosureManifest,
    build_plugin_closure,
)
from rush.plugins.snapshot_store import PluginSnapshotStore


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def test_closure_digest_covers_every_code_and_behavior_input(tmp_path: Path) -> None:
    """T-56.06: Mutates (a) helper script, (b) asset file, (c) config dict, (d) env names, (e) runtime.

    Asserts build_plugin_closure() produces unique, differing digests for each mutation.
    """
    plugin_root = tmp_path / "my_plugin"
    plugin_root.mkdir()

    entrypoint = plugin_root / "main.py"
    entrypoint.write_bytes(b"print('main')\n")

    helper = plugin_root / "helper.py"
    helper.write_bytes(b"def run(): return 'original_helper'\n")

    assets_dir = plugin_root / "assets"
    assets_dir.mkdir()
    asset_file = assets_dir / "rules.json"
    asset_file.write_bytes(b'{"status": "active"}\n')

    base_config = {
        "command": ["python", "main.py"],
        "timeout_seconds": 30,
        "patterns": ["*.py"],
    }
    base_env = ["RUSH_ENV_A", "RUSH_ENV_B"]
    base_secrets = ["secret:TOKEN_A"]
    base_runtime = "python3.12:bin_hash_base"
    base_platform = "win32-x86_64"

    # 1. Baseline closure computation
    base_closure = build_plugin_closure(
        plugin_root=plugin_root,
        entrypoint=entrypoint,
        config=base_config,
        allowed_env_names=base_env,
        declared_secret_refs=base_secrets,
        runtime_identity=base_runtime,
        platform_identity=base_platform,
    )

    assert isinstance(base_closure, PluginClosureManifest)
    assert base_closure.schema_version == "1.0.0"
    assert base_closure.plugin_name == "my_plugin"
    assert base_closure.entrypoint == "main.py"
    assert base_closure.file_manifest["main.py"] == _sha256(b"print('main')\n")
    assert base_closure.file_manifest["helper.py"] == _sha256(
        b"def run(): return 'original_helper'\n"
    )
    assert base_closure.file_manifest["assets/rules.json"] == _sha256(
        b'{"status": "active"}\n'
    )
    assert base_closure.allowed_env_names == ("RUSH_ENV_A", "RUSH_ENV_B")
    assert base_closure.declared_secret_refs == ("secret:TOKEN_A",)
    assert base_closure.runtime_identity == base_runtime
    assert base_closure.platform_identity == base_platform
    assert len(base_closure.closure_digest) == 64

    # 2. Mutation (a): mutate helper script
    helper.write_bytes(b"def run(): return 'mutated_helper'\n")
    closure_mut_helper = build_plugin_closure(
        plugin_root=plugin_root,
        entrypoint=entrypoint,
        config=base_config,
        allowed_env_names=base_env,
        declared_secret_refs=base_secrets,
        runtime_identity=base_runtime,
        platform_identity=base_platform,
    )
    assert closure_mut_helper.closure_digest != base_closure.closure_digest
    # Restore helper
    helper.write_bytes(b"def run(): return 'original_helper'\n")

    # 3. Mutation (b): mutate asset file
    asset_file.write_bytes(b'{"status": "tampered"}\n')
    closure_mut_asset = build_plugin_closure(
        plugin_root=plugin_root,
        entrypoint=entrypoint,
        config=base_config,
        allowed_env_names=base_env,
        declared_secret_refs=base_secrets,
        runtime_identity=base_runtime,
        platform_identity=base_platform,
    )
    assert closure_mut_asset.closure_digest != base_closure.closure_digest
    # Restore asset
    asset_file.write_bytes(b'{"status": "active"}\n')

    # 4. Mutation (c): mutate config dict
    mut_config = {
        "command": ["python", "main.py"],
        "timeout_seconds": 60,
        "patterns": ["*.py"],
    }
    closure_mut_config = build_plugin_closure(
        plugin_root=plugin_root,
        entrypoint=entrypoint,
        config=mut_config,
        allowed_env_names=base_env,
        declared_secret_refs=base_secrets,
        runtime_identity=base_runtime,
        platform_identity=base_platform,
    )
    assert closure_mut_config.closure_digest != base_closure.closure_digest

    # 5. Mutation (d): mutate allowed env names
    mut_env = ["RUSH_ENV_A", "RUSH_ENV_MUTATED"]
    closure_mut_env = build_plugin_closure(
        plugin_root=plugin_root,
        entrypoint=entrypoint,
        config=base_config,
        allowed_env_names=mut_env,
        declared_secret_refs=base_secrets,
        runtime_identity=base_runtime,
        platform_identity=base_platform,
    )
    assert closure_mut_env.closure_digest != base_closure.closure_digest

    # 6. Mutation (e): mutate runtime identity
    mut_runtime = "python3.12:bin_hash_swapped"
    closure_mut_runtime = build_plugin_closure(
        plugin_root=plugin_root,
        entrypoint=entrypoint,
        config=base_config,
        allowed_env_names=base_env,
        declared_secret_refs=base_secrets,
        runtime_identity=mut_runtime,
        platform_identity=base_platform,
    )
    assert closure_mut_runtime.closure_digest != base_closure.closure_digest

    # 7. Assert every single mutation produced a pairwise distinct, unique digest
    all_digests = [
        base_closure.closure_digest,
        closure_mut_helper.closure_digest,
        closure_mut_asset.closure_digest,
        closure_mut_config.closure_digest,
        closure_mut_env.closure_digest,
        closure_mut_runtime.closure_digest,
    ]
    assert len(set(all_digests)) == 6


def test_snapshot_contains_copied_bytes_not_links(tmp_path: Path) -> None:
    """T-56.07: Materializes snapshot; asserts symlinks and junctions are rejected with ContainmentError.

    Asserts files in snapshot directory are independent physical byte copies (not symlinks or hardlinks).
    """
    plugin_root = tmp_path / "valid_plugin"
    plugin_root.mkdir()

    entry = plugin_root / "entry.py"
    entry.write_text("print('valid entry')\n", encoding="utf-8")

    sub_dir = plugin_root / "subdir"
    sub_dir.mkdir()
    lib_file = sub_dir / "lib.py"
    lib_file.write_text("LIB_VALUE = 42\n", encoding="utf-8")

    closure = build_plugin_closure(
        plugin_root=plugin_root,
        entrypoint=entry,
        config={"name": "valid_plugin", "command": ["python", "entry.py"]},
    )

    snapshots_root = tmp_path / "snapshots"
    store = PluginSnapshotStore(snapshots_root=snapshots_root)

    # 1. Materialize snapshot
    snapshot_dir = store.materialize_snapshot(closure=closure, plugin_root=plugin_root)
    assert snapshot_dir.exists()
    assert snapshot_dir == snapshots_root / closure.closure_digest

    # 2. Verify all files in snapshot are pure physical byte copies, not symlinks or hardlinks
    for rel_path, expected_hash in closure.file_manifest.items():
        snap_file = snapshot_dir / rel_path
        assert snap_file.exists(), f"Snapshot missing file: {rel_path}"
        assert snap_file.is_file()
        assert not snap_file.is_symlink(), f"Snapshot file is a symlink: {snap_file}"

        st = os.lstat(snap_file)
        # Verify nlink == 1 (never a hardlink)
        assert st.st_nlink == 1, (
            f"Snapshot file has hardlinks (nlink={st.st_nlink}): {snap_file}"
        )

        file_bytes = snap_file.read_bytes()
        assert _sha256(file_bytes) == expected_hash

    # 3. Verify independence: mutating source file does not affect snapshot bytes
    entry.write_text("print('MUTATED_SOURCE')\n", encoding="utf-8")
    assert (snapshot_dir / "entry.py").read_text(
        encoding="utf-8"
    ) == "print('valid entry')\n"

    # 4. Reject symlink in plugin root fail-closed with ContainmentError
    symlink_root = tmp_path / "symlink_plugin"
    symlink_root.mkdir()
    (symlink_root / "entry.py").write_text("print('entry')\n", encoding="utf-8")

    outside_file = tmp_path / "outside_target.py"
    outside_file.write_text("MALICIOUS = True\n", encoding="utf-8")

    symlink_target = symlink_root / "evil_link.py"
    try:
        os.symlink(outside_file, symlink_target)
        symlink_created = True
    except OSError:
        symlink_created = False

    if symlink_created:
        with pytest.raises(ContainmentError) as exc_sym:
            build_plugin_closure(
                plugin_root=symlink_root,
                entrypoint=symlink_root / "entry.py",
                config={},
            )
        assert exc_sym.value.code == "SYMLINK_DISALLOWED"

        # Also verify materialize_snapshot rejects symlink
        with pytest.raises(ContainmentError):
            store.materialize_snapshot(closure=closure, plugin_root=symlink_root)

    # 5. Reject directory junction in plugin root fail-closed with ContainmentError
    if _winapi is not None and hasattr(_winapi, "CreateJunction"):
        junc_root = tmp_path / "junc_plugin"
        junc_root.mkdir()
        (junc_root / "entry.py").write_text("print('entry')\n", encoding="utf-8")

        outside_dir = tmp_path / "outside_dir"
        outside_dir.mkdir()
        (outside_dir / "evil.py").write_text("print('evil')", encoding="utf-8")

        junction_dest = junc_root / "junc_sub"
        _winapi.CreateJunction(str(outside_dir), str(junction_dest))

        with pytest.raises(ContainmentError) as exc_junc:
            build_plugin_closure(
                plugin_root=junc_root,
                entrypoint=junc_root / "entry.py",
                config={},
            )
        assert exc_junc.value.code == "REPARSE_POINT_DISALLOWED"

        with pytest.raises(ContainmentError):
            store.materialize_snapshot(closure=closure, plugin_root=junc_root)

    # 6. Reject hardlink in plugin root fail-closed with ContainmentError
    hardlink_root = tmp_path / "hardlink_plugin"
    hardlink_root.mkdir()
    source_file = hardlink_root / "entry.py"
    source_file.write_text("print('hardlink')\n", encoding="utf-8")
    hardlink_file = hardlink_root / "linked.py"
    os.link(source_file, hardlink_file)

    with pytest.raises(ContainmentError) as exc_hard:
        build_plugin_closure(
            plugin_root=hardlink_root,
            entrypoint=source_file,
            config={},
        )
    assert exc_hard.value.code == "HARDLINK_DISALLOWED"


def test_post_approval_mutation_uses_snapshot_or_denies(tmp_path: Path) -> None:
    """T-56.08: Mutates source repo file after snapshot materialization.

    Verifies snapshot file bytes remain intact and verify_snapshot() confirms integrity against closure manifest.
    """
    plugin_root = tmp_path / "repo_plugin"
    plugin_root.mkdir()

    main_script = plugin_root / "main.py"
    main_script.write_text("import lib; print(lib.safe())\n", encoding="utf-8")

    sub_script = plugin_root / "lib.py"
    sub_script.write_text("def safe(): return 'APPROVED_CODE'\n", encoding="utf-8")

    closure = build_plugin_closure(
        plugin_root=plugin_root,
        entrypoint=main_script,
        config={"name": "repo_plugin", "command": ["python", "main.py"]},
    )

    store = PluginSnapshotStore(snapshots_root=tmp_path / "snapshots")
    snapshot_path = store.materialize_snapshot(closure=closure, plugin_root=plugin_root)

    # Pre-condition: Snapshot is intact and verified
    assert store.verify_snapshot(closure) is True

    # TOCTOU attack simulation: Attacker mutates source repo files post-approval
    sub_script.write_text("def safe(): return 'EXPLOIT_PAYLOAD'\n", encoding="utf-8")
    main_script.write_text("import os; os.system('calc')\n", encoding="utf-8")

    # 1. Snapshot file bytes MUST remain completely unchanged
    assert (snapshot_path / "lib.py").read_text(
        encoding="utf-8"
    ) == "def safe(): return 'APPROVED_CODE'\n"
    assert (snapshot_path / "main.py").read_text(
        encoding="utf-8"
    ) == "import lib; print(lib.safe())\n"

    # 2. Snapshot store still verifies snapshot against original closure
    assert store.verify_snapshot(closure) is True

    # 3. New closure built from mutated source produces a DIFFERENT digest
    mutated_closure = build_plugin_closure(
        plugin_root=plugin_root,
        entrypoint=main_script,
        config={"name": "repo_plugin", "command": ["python", "main.py"]},
    )
    assert mutated_closure.closure_digest != closure.closure_digest

    # 4. If snapshot directory itself is tampered, verify_snapshot() returns False
    (snapshot_path / "lib.py").write_text("CORRUPTED_IN_SNAPSHOT", encoding="utf-8")
    assert store.verify_snapshot(closure) is False

    # 5. If snapshot file is deleted, verify_snapshot() returns False
    (snapshot_path / "lib.py").unlink()
    assert store.verify_snapshot(closure) is False
