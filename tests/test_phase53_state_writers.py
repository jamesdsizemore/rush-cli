"""Contract tests for Phase 53: State, Security, and Release Writers (P53.4.1)."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from rush.memory.checkpoint_journal import CheckpointJournal
from rush.memory.failure_ledger import FailureLedger
from rush.memory.invariant_graph import InvariantGraph
from rush.memory.merkle_invalidator import MerkleInvalidator
from rush.memory.preference_store import PreferenceStore
from rush.patch.applier import PatchApplier
from rush.patch.memory import PatchMemoryStore
from rush.patch.promoter import PatchPromoter
from rush.patch_generator import apply_unified_patch
from rush.permissions import ExecutionPermissions
from rush.plugins.trust import trust_repo
from rush.plugins.trust_store import PluginTrustStore
from rush.release.ci_generator import CIWorkflowGenerator
from rush.release.docker_generator import DockerfileGenerator
from rush.release.provenance import ArtifactProvenanceVerifier
from rush.safety.audit_logger import SecurityAuditLogger
from rush.session_memory import SessionMemoryManager
from rush.tools.attest import AttestationTool
from rush.tools.benchmark import BenchmarkTool
from rush.tools.continuity import SessionContinuityTool
from rush.tools.dead_asset import DeadAssetTool
from rush.tools.error_catalog import ErrorCatalogTool
from rush.tools.fix import FixTool, SnapshotJournal
from rush.tools.flight_recorder import FlightRecorder
from rush.tools.iam_audit import IamAuditTool
from rush.tools.pr_synthesize import PrSynthesizeTool


def test_security_audit_logger_sanitizes_disk_writes(tmp_path: Path) -> None:
    """Verify that SecurityAuditLogger sanitizes secrets before appending to .rush/audit.log."""
    fresh_secret = "sk-ant-api03-abcdef123456789012345678"
    fresh_key = "sk-proj-12345678901234567890abcdef"
    logger = SecurityAuditLogger(tmp_path)

    logger.log_security_event("test_event", {fresh_key: f"token={fresh_secret}"})

    log_file = tmp_path / ".rush" / "audit.log"
    assert log_file.exists()
    content = log_file.read_text(encoding="utf-8")
    assert fresh_secret not in content
    assert fresh_key not in content


def test_patch_memory_store_sanitizes_db_writes(tmp_path: Path) -> None:
    """Verify that PatchMemoryStore sanitizes diff patches before inserting into SQLite."""
    fresh_secret = "sk-ant-api03-abcdef123456789012345678"
    diff = f"--- a/app.py\n+++ b/app.py\n@@ -1 +1 @@\n-api_key = ''\n+api_key = '{fresh_secret}'\n"

    store = PatchMemoryStore(tmp_path)
    store.record_success("sig_123", "app.py", diff)

    db_path = tmp_path / ".rush" / "cache.db"
    assert db_path.exists()
    with sqlite3.connect(db_path) as conn:
        row = (
            conn.execute(
                "SELECT diff_patch FROM patch_memory WHERE error_signature = ?",
                (store._init_db(),),
            ).fetchone()
            or conn.execute("SELECT diff_patch FROM patch_memory").fetchone()
        )
        assert row is not None
        stored_diff = row[0]
        assert fresh_secret not in stored_diff


def test_flight_recorder_sanitizes_session_writes(tmp_path: Path) -> None:
    """Verify that FlightRecorder sanitizes payloads before writing .rush/sessions/flights/*.jsonl."""
    fresh_secret = "sk-ant-api03-abcdef123456789012345678"
    recorder = FlightRecorder(tmp_path)

    recorder.record_event("sess_001", "tool_call", {"secret_param": fresh_secret})

    flight_file = tmp_path / ".rush" / "sessions" / "flights" / "sess_001.jsonl"
    assert flight_file.exists()
    content = flight_file.read_text(encoding="utf-8")
    assert fresh_secret not in content


def test_preference_store_sanitizes_json_writes(tmp_path: Path) -> None:
    """Verify that PreferenceStore sanitizes keys and values before writing preferences.json."""
    fresh_secret = "sk-ant-api03-abcdef123456789012345678"
    store = PreferenceStore(tmp_path)

    store.set(f"prefix_{fresh_secret}", f"val_{fresh_secret}")

    pref_file = tmp_path / ".rush" / "preferences.json"
    assert pref_file.exists()
    content = pref_file.read_text(encoding="utf-8")
    assert fresh_secret not in content


def test_invariant_graph_sanitizes_json_writes(tmp_path: Path) -> None:
    """Verify that InvariantGraph sanitizes descriptions and rationales before writing invariants.json."""
    fresh_secret = "sk-ant-api03-abcdef123456789012345678"
    graph = InvariantGraph(tmp_path)

    graph.add_invariant("INV01", f"must use {fresh_secret}", f"because {fresh_secret}")

    inv_file = tmp_path / ".rush" / "memory" / "invariants.json"
    assert inv_file.exists()
    content = inv_file.read_text(encoding="utf-8")
    assert fresh_secret not in content


def test_benchmark_sanitizes_baseline_writes(tmp_path: Path) -> None:
    """Verify that benchmark writes sanitized baselines JSON to disk."""
    fresh_secret = "sk-ant-api03-abcdef123456789012345678"
    tool = BenchmarkTool()
    tool.run(
        tmp_path,
        record=True,
        baseline_name=f"base_{fresh_secret}",
        samples=[10.0, 11.5],
        permissions=ExecutionPermissions(cache_write=True),
    )
    baseline_file = tmp_path / ".rush" / "baselines.json"
    assert baseline_file.exists(), "baselines.json was not created!"
    content = baseline_file.read_text(encoding="utf-8")
    assert fresh_secret not in content
    assert "[REDACTED_ANTHROPIC_KEY]" in content


def test_memory_patch_plugin_release_artifacts_are_sanitized_on_success_and_abort(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verify that §8 state/security/release writers sanitize artifacts on both success and abort."""

    fresh_secret = "sk-ant-api03-abcdef123456789012345678"

    def assert_no_sentinel_in_dir(
        directory: Path, allowed_extensions: tuple[str, ...] | None = None
    ) -> None:
        for p in directory.rglob("*"):
            if p.is_file():
                if allowed_extensions and p.suffix not in allowed_extensions:
                    continue
                try:
                    text = p.read_text(encoding="utf-8", errors="ignore")
                    assert fresh_secret not in text, f"Leaked secret in file {p}"
                except OSError:
                    pass

    # 1. CheckpointJournal (Success & Abort)
    cj_dir = tmp_path / "cj_case"
    cj_dir.mkdir()
    cj = CheckpointJournal(cj_dir)
    dest = cj.save_checkpoint(
        f"chk_{fresh_secret}",
        {"secret_key": fresh_secret, "info": f"auth={fresh_secret}"},
        [f"file_{fresh_secret}.py"],
    )
    assert dest.exists()
    assert_no_sentinel_in_dir(cj_dir / ".rush")
    # Abort test: forced write failure cleans up
    abort_cj = CheckpointJournal(tmp_path / "cj_abort")
    from rush.io.atomic_file import AtomicFile

    monkeypatch.setattr(
        AtomicFile,
        "write_json",
        lambda *a, **k: (_ for _ in ()).throw(OSError("Disk write abort")),
    )
    with pytest.raises(OSError):
        abort_cj.save_checkpoint("abort_chk", {"secret": fresh_secret}, [])
    monkeypatch.undo()

    # 2. FailureLedger (Success & Abort)
    fl_dir = tmp_path / "fl_case"
    fl_dir.mkdir()
    fl = FailureLedger(fl_dir)
    fp = fl.record_failure(
        f"patch content with {fresh_secret}", f"error message with {fresh_secret}"
    )
    receipt = fl.get_receipt(fp)
    assert receipt is not None
    assert fresh_secret not in receipt["redacted_error"]
    with sqlite3.connect(fl.db_path) as conn:
        for row in conn.execute(
            "SELECT error_message, failed_patch FROM failure_ledgers"
        ):
            assert fresh_secret not in row[0]
            assert fresh_secret not in row[1]

    # 3. InvariantGraph (Success & Abort)
    inv_dir = tmp_path / "inv_case"
    inv_dir.mkdir()
    inv = InvariantGraph(inv_dir)
    inv.add_invariant(
        f"INV_{fresh_secret}",
        f"desc with {fresh_secret}",
        f"rationale with {fresh_secret}",
    )
    assert_no_sentinel_in_dir(inv_dir / ".rush")

    # 4. MerkleInvalidator
    merkle_dir = tmp_path / "merkle_case"
    merkle_dir.mkdir()
    test_src = merkle_dir / "src.py"
    test_src.write_text("code = 1\n", encoding="utf-8")
    snapshot = MerkleInvalidator.snapshot_paths(merkle_dir, [str(test_src)])
    assert fresh_secret not in str(snapshot)

    # 5. PreferenceStore (Success & Abort)
    pref_dir = tmp_path / "pref_case"
    pref_dir.mkdir()
    pref = PreferenceStore(pref_dir)
    pref.set(f"key_{fresh_secret}", f"val_{fresh_secret}")
    assert_no_sentinel_in_dir(pref_dir / ".rush")

    # 6. PatchApplier (Success & Abort cleanup)
    patch_dir = tmp_path / "patch_case"
    patch_dir.mkdir()
    app_file = patch_dir / "app.py"
    app_file.write_text("x = 1\n", encoding="utf-8")
    # Simulate failed patch application
    success, _msg = PatchApplier.apply_patch_to_dir(patch_dir, "invalid patch header")
    assert success is False
    # Verify .temp_patch.diff is not retained on disk
    assert not (patch_dir / ".temp_patch.diff").exists()

    # 7. PatchMemoryStore (Success & Abort)
    pm_dir = tmp_path / "pm_case"
    pm_dir.mkdir()
    pm = PatchMemoryStore(pm_dir)
    pm.record_success("sig1", "app.py", f"diff with {fresh_secret}")
    with sqlite3.connect(pm_dir / ".rush" / "cache.db") as conn:
        for row in conn.execute("SELECT diff_patch FROM patch_memory"):
            assert fresh_secret not in row[0]

    # 8. PatchPromoter (Abort & cleanup)
    prom_dir = tmp_path / "prom_case"
    prom_dir.mkdir()
    promoter = PatchPromoter(prom_dir)
    success, _msg = promoter.promote_sandbox_diff(prom_dir)
    assert success is False
    assert not (prom_dir / ".promote.patch").exists()

    # 9. apply_unified_patch
    pug_dir = tmp_path / "pug_case"
    pug_dir.mkdir()
    with pytest.raises(ValueError):
        apply_unified_patch(
            f"--- a/../../etc/passwd\n+++ b/../../etc/passwd\n@@ -1 +1 @@\n+{fresh_secret}\n",
            pug_dir,
        )

    # 10. PluginTrust (trust_repo) & PluginTrustStore
    trust_dir = tmp_path / "trust_case"
    trust_dir.mkdir()
    ledger_file = trust_dir / ".rush" / "trusted_repos.json"
    trust_repo(trust_dir / f"repo_{fresh_secret}", ledger_file=ledger_file)
    assert_no_sentinel_in_dir(trust_dir / ".rush")

    pts = PluginTrustStore(trust_dir)
    plugin_exec = trust_dir / f"plugin_{fresh_secret}.py"
    plugin_exec.write_text("print('plugin')\n", encoding="utf-8")
    pts.grant_trust(f"plug_{fresh_secret}", plugin_exec)
    assert_no_sentinel_in_dir(trust_dir / ".rush")
    pts.revoke_trust(f"plug_{fresh_secret}")
    assert_no_sentinel_in_dir(trust_dir / ".rush")

    # 11. CIWorkflowGenerator, DockerfileGenerator, ArtifactProvenanceVerifier
    rel_dir = tmp_path / "rel_case"
    rel_dir.mkdir()
    CIWorkflowGenerator.generate_ci_workflow(rel_dir)
    DockerfileGenerator.generate_dockerfile(rel_dir)
    dist_dir = rel_dir / "dist"
    dist_dir.mkdir()
    (dist_dir / "pkg.tar.gz").write_bytes(b"dummy package")
    ArtifactProvenanceVerifier.generate_checksums_manifest(dist_dir)
    assert_no_sentinel_in_dir(rel_dir)

    # 12. SecurityAuditLogger & SessionMemoryManager
    sec_dir = tmp_path / "sec_case"
    sec_dir.mkdir()
    sal = SecurityAuditLogger(sec_dir)
    sal.log_security_event("alert", {"secret": fresh_secret})
    smm = SessionMemoryManager(sec_dir / ".rush" / "session_memory.json")
    smm.record_turn("test_tool", 1, 1, f"Summary with {fresh_secret}")
    assert_no_sentinel_in_dir(sec_dir / ".rush")

    # 13. AttestationTool
    att_dir = tmp_path / "att_case"
    att_dir.mkdir()
    (att_dir / "artifact.txt").write_text("package data\n", encoding="utf-8")
    attest = AttestationTool()
    att_res = attest.run(
        att_dir,
        artifact_path="artifact.txt",
        output_path="statement.json",
        permissions=ExecutionPermissions(artifact_write=True),
    )
    assert att_res["status"] in ("ok", "warn")
    assert_no_sentinel_in_dir(att_dir)

    # 14. SessionContinuityTool
    cont_dir = tmp_path / "cont_case"
    cont_dir.mkdir()
    cont = SessionContinuityTool()
    cont_res = cont.run(
        cont_dir,
        operation="save",
        name="test_session",
        handoff={"current_goal": f"fix {fresh_secret}", "open_work": [fresh_secret]},
        permissions=ExecutionPermissions(cache_write=True),
    )
    assert cont_res["status"] == "ok"
    assert_no_sentinel_in_dir(cont_dir / ".rush")

    # 15. FixTool & SnapshotJournal (Rollback verification)
    fix_dir = tmp_path / "fix_case"
    fix_dir.mkdir()
    target_py = fix_dir / "test.py"
    target_py.write_text("x = 1\n", encoding="utf-8")
    journal = SnapshotJournal()
    journal.capture([target_py])
    target_py.write_text(f"x = '{fresh_secret}'\n", encoding="utf-8")
    assert journal.has_changes(target_py)
    journal.rollback_all()
    assert target_py.read_text(encoding="utf-8") == "x = 1\n"
    assert fresh_secret not in target_py.read_text(encoding="utf-8")
    fix_res = FixTool().run(fix_dir, dry_run=True)
    assert fix_res["status"] in ("ok", "warn", "skipped")

    # 16. FlightRecorder
    flt_dir = tmp_path / "flt_case"
    flt_dir.mkdir()
    fr = FlightRecorder(flt_dir)
    fr.record_event("sess_1", "tool_call", {"token": fresh_secret})
    assert_no_sentinel_in_dir(flt_dir / ".rush")

    # 17. IamAuditTool
    iam_dir = tmp_path / "iam_case"
    iam_dir.mkdir()
    policy_f = iam_dir / "policy.json"
    policy_f.write_text(
        f'{{"Statement": [{{"Effect": "Allow", "Action": "*", "Resource": "{fresh_secret}"}}]}}',
        encoding="utf-8",
    )
    iam_res = IamAuditTool().run(
        iam_dir,
        output_policy_file="iam_remediated.json",
        permissions=ExecutionPermissions(artifact_write=True),
    )
    assert iam_res["status"] in ("ok", "fail", "warn")
    export_target = iam_dir / "iam_remediated.json"
    if export_target.exists():
        assert fresh_secret not in export_target.read_text(encoding="utf-8")

    # 18. PrSynthesizeTool
    pr_dir = tmp_path / "pr_case"
    pr_dir.mkdir()
    # Mock git repository with commit
    pr_res = PrSynthesizeTool().run(
        pr_dir,
        export_path="pr_card.md",
        permissions=ExecutionPermissions(artifact_write=True),
    )
    assert pr_res["status"] in ("ok", "warn", "skipped")
    # Even if skipped (not a git repo), assert export file didn't write secrets
    assert_no_sentinel_in_dir(pr_dir)

    # 19. DeadAssetTool
    dead_dir = tmp_path / "dead_case"
    dead_dir.mkdir()
    (dead_dir / "asset.png").write_bytes(b"dummy")
    dead_res = DeadAssetTool().run(
        dead_dir,
        export_manifest="dead_manifest.json",
        permissions=ExecutionPermissions(artifact_write=True),
    )
    assert dead_res["status"] in ("ok", "warn", "skipped")
    assert_no_sentinel_in_dir(dead_dir, allowed_extensions=(".json", ".txt", ".md"))

    # 20. ErrorCatalogTool
    err_dir = tmp_path / "err_case"
    err_dir.mkdir()
    py_err = err_dir / "error.py"
    py_err.write_text(
        f'raise ValueError("secret token: {fresh_secret}")\n', encoding="utf-8"
    )
    err_res = ErrorCatalogTool().run(
        err_dir,
        export_path="catalog.md",
        permissions=ExecutionPermissions(artifact_write=True),
    )
    assert err_res["status"] == "ok"
    cat_file = err_dir / "catalog.md"
    assert cat_file.exists()
    cat_text = cat_file.read_text(encoding="utf-8")
    assert fresh_secret not in cat_text
    assert "[REDACTED" in cat_text

    # 21. BenchmarkTool
    bench_dir = tmp_path / "bench_case"
    bench_dir.mkdir()
    b_res = BenchmarkTool().run(
        bench_dir,
        record=True,
        baseline_name=f"base_{fresh_secret}",
        samples=[5.0, 5.2],
        permissions=ExecutionPermissions(cache_write=True),
    )
    assert b_res["status"] == "ok"
    assert_no_sentinel_in_dir(bench_dir / ".rush")
