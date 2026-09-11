"""MC05 (Phase 63): `verify-attempt` real sandbox patch verification.

Exercises the real `PatchSandboxManager` -> `PatchApplier` -> `PatchVerifier`
route through `rush.memory.verification.verify_attempt`, and its wiring into
`MemoryTool` (`rush.tools.memory.MemoryTool`, operation="verify_attempt").
Never promotes, never mutates the source checkout, and never records a
"completed" observation without at least one real executed command.
"""

from __future__ import annotations

import json
import sqlite3
import subprocess
import sys
from pathlib import Path

from rush.memory.verification import parse_patch_contract, verify_attempt
from rush.patch.contracts import PatchContract, VerifierCommandPlan
from rush.permissions import ExecutionPermissions
from rush.tools.memory import MemoryTool

_UPLOAD_BUGGY = (
    "def upload(size_bytes: int, elapsed_seconds: float) -> bool:\n"
    "    if elapsed_seconds > 30:\n"
    "        return True\n"
    "    if size_bytes > 1_000_000:\n"
    "        return True\n"
    "    return True\n"
)

_CHECK_UPLOAD = (
    "import upload\n\n"
    'assert upload.upload(0, 999) is False, "expected timeout rejected"\n'
    'assert upload.upload(2_000_000, 0) is False, "expected oversized upload rejected"\n'
    'print("OK")\n'
)

_PATCH_TIMEOUT_ONLY = """--- a/upload.py
+++ b/upload.py
@@ -1,6 +1,6 @@
 def upload(size_bytes: int, elapsed_seconds: float) -> bool:
     if elapsed_seconds > 30:
-        return True
+        return False
     if size_bytes > 1_000_000:
         return True
     return True
"""

_PATCH_TIMEOUT_AND_SIZE_LIMIT = """--- a/upload.py
+++ b/upload.py
@@ -1,6 +1,6 @@
 def upload(size_bytes: int, elapsed_seconds: float) -> bool:
     if elapsed_seconds > 30:
-        return True
+        return False
     if size_bytes > 1_000_000:
-        return True
+        return False
     return True
"""


def _run_git(args: list[str], cwd: Path) -> str:
    proc = subprocess.run(
        ["git", *args], cwd=cwd, capture_output=True, text=True, check=True
    )
    return proc.stdout.strip()


def _init_upload_repo(root: Path) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    _run_git(["init", "-b", "main"], root)
    _run_git(["config", "user.name", "RushTester"], root)
    _run_git(["config", "user.email", "rush@example.com"], root)
    (root / ".gitignore").write_text(".rush/\n", encoding="utf-8")
    (root / "upload.py").write_text(_UPLOAD_BUGGY, encoding="utf-8")
    (root / "check_upload.py").write_text(_CHECK_UPLOAD, encoding="utf-8")
    _run_git(["add", "."], root)
    _run_git(["commit", "-m", "initial upload module with two known bugs"], root)
    return root


def _head_and_tree(root: Path) -> tuple[str, str]:
    return _run_git(["rev-parse", "HEAD"], root), _run_git(
        ["rev-parse", "HEAD^{tree}"], root
    )


def _observations(root: Path, source_prefix: str) -> list[dict]:
    db = root / ".rush" / "memory.db"
    if not db.exists():
        return []
    with sqlite3.connect(db) as conn:
        rows = conn.execute(
            "SELECT content FROM memory_artifacts WHERE family='experience' "
            "AND subject='episodic' AND source LIKE ?",
            (f"{source_prefix}%",),
        ).fetchall()
    return [json.loads(row[0]) for row in rows]


def _check_command_plan() -> VerifierCommandPlan:
    return VerifierCommandPlan(
        command=(sys.executable, "check_upload.py"), expected_exit_code=0
    )


def test_verify_attempt_runs_real_command_in_sandbox(tmp_path: Path) -> None:
    repo = _init_upload_repo(tmp_path / "repo")
    base_commit, base_tree = _head_and_tree(repo)
    orig_content = (repo / "upload.py").read_text(encoding="utf-8")
    granted = ExecutionPermissions(cache_write=True, artifact_write=True, build=True)

    # First attempt: partial fix (timeout only) -> real check command exits 1.
    contract_partial = PatchContract(
        base_commit=base_commit,
        base_tree_digest=base_tree,
        patch_content_digest="patch-1",
        sandbox_path=repo,
        required_commands=(_check_command_plan(),),
        config_digest="cfg-1",
        review_class="standard",
    )
    outcome_partial = verify_attempt(
        attempt_id="attempt-timeout-only",
        behavior_ids=("upload-timeout-fixed",),
        repo_root=repo,
        contract=contract_partial,
        patch=_PATCH_TIMEOUT_ONLY,
        granted=granted,
    )
    assert outcome_partial.outcome == "failed"
    assert outcome_partial.result is not None
    assert len(outcome_partial.result.executed_commands) == 1
    executed_partial = outcome_partial.result.executed_commands[0]
    assert executed_partial["exit_code"] != 0
    assert executed_partial["passed"] is False

    # Second attempt (fresh sandbox from the same unmodified repo): full fix ->
    # real check command exits 0.
    contract_full = PatchContract(
        base_commit=base_commit,
        base_tree_digest=base_tree,
        patch_content_digest="patch-2",
        sandbox_path=repo,
        required_commands=(_check_command_plan(),),
        config_digest="cfg-2",
        review_class="standard",
    )
    outcome_full = verify_attempt(
        attempt_id="attempt-timeout-and-size-limit",
        behavior_ids=("upload-timeout-fixed", "upload-size-limit-fixed"),
        repo_root=repo,
        contract=contract_full,
        patch=_PATCH_TIMEOUT_AND_SIZE_LIMIT,
        granted=granted,
    )
    assert outcome_full.outcome == "completed"
    assert outcome_full.result is not None
    executed_full = outcome_full.result.executed_commands[0]
    assert executed_full["exit_code"] == 0
    assert executed_full["passed"] is True
    assert "OK" in executed_full["stdout"]

    # Source checkout is untouched by either attempt (only the sandbox worktree
    # was ever patched), and the sandbox worktrees are cleaned up (no leaked
    # git worktrees / children left behind).
    assert (repo / "upload.py").read_text(encoding="utf-8") == orig_content
    current_head, current_tree = _head_and_tree(repo)
    assert (current_head, current_tree) == (base_commit, base_tree)
    assert _run_git(["status", "--porcelain"], repo) == ""
    worktree_list = _run_git(["worktree", "list"], repo)
    assert "sandbox_" not in worktree_list

    # Both attempts finalized a truthful observation with exact receipt identity.
    obs = _observations(repo, "verify_attempt:")
    by_attempt = {o["attempt_id"]: o for o in obs}
    assert by_attempt["attempt-timeout-only"]["outcome"] == "failed"
    assert by_attempt["attempt-timeout-and-size-limit"]["outcome"] == "completed"
    assert by_attempt["attempt-timeout-and-size-limit"]["behavior_ids"] == [
        "upload-timeout-fixed",
        "upload-size-limit-fixed",
    ]

    # Wiring through MemoryTool.run(operation="verify_attempt") produces the
    # same real, non-promoting route (a third, independent attempt/sandbox).
    tool_result = MemoryTool().run(
        repo,
        operation="verify_attempt",
        permissions=granted,
        request={
            "attempt_id": "attempt-via-memory-tool",
            "behavior_ids": ["upload-timeout-fixed", "upload-size-limit-fixed"],
            "contract": {
                "base_commit": base_commit,
                "base_tree_digest": base_tree,
                "patch_content_digest": "patch-3",
                "required_commands": [{"command": [sys.executable, "check_upload.py"]}],
                "config_digest": "cfg-3",
                "review_class": "standard",
            },
            "patch": _PATCH_TIMEOUT_AND_SIZE_LIMIT,
        },
    )
    assert tool_result["status"] == "ok"
    assert tool_result["raw"]["outcome"] == "completed"
    assert (repo / "upload.py").read_text(encoding="utf-8") == orig_content


def test_verify_attempt_rejects_drift_and_missing_permissions(tmp_path: Path) -> None:
    repo = _init_upload_repo(tmp_path / "repo")
    base_commit, base_tree = _head_and_tree(repo)
    orig_content = (repo / "upload.py").read_text(encoding="utf-8")

    # -- missing permissions: refuses before ever creating a sandbox. --
    contract = PatchContract(
        base_commit=base_commit,
        base_tree_digest=base_tree,
        patch_content_digest="patch-x",
        sandbox_path=repo,
        required_commands=(_check_command_plan(),),
        config_digest="cfg-x",
        review_class="standard",
    )
    outcome_denied = verify_attempt(
        attempt_id="attempt-denied",
        behavior_ids=("upload-timeout-fixed",),
        repo_root=repo,
        contract=contract,
        patch=_PATCH_TIMEOUT_AND_SIZE_LIMIT,
        granted=ExecutionPermissions(),  # nothing granted
    )
    assert outcome_denied.outcome == "denied"
    assert outcome_denied.result is None
    assert not (repo / ".rush" / "worktrees").exists()
    assert _observations(repo, "verify_attempt:") == []

    # -- drift: contract's base commit no longer matches the real sandbox HEAD. --
    granted = ExecutionPermissions(cache_write=True, artifact_write=True, build=True)
    drifted_contract = PatchContract(
        base_commit="0" * 40,
        base_tree_digest=base_tree,
        patch_content_digest="patch-y",
        sandbox_path=repo,
        required_commands=(_check_command_plan(),),
        config_digest="cfg-y",
        review_class="standard",
    )
    outcome_drift = verify_attempt(
        attempt_id="attempt-drift",
        behavior_ids=("upload-timeout-fixed",),
        repo_root=repo,
        contract=drifted_contract,
        patch=_PATCH_TIMEOUT_AND_SIZE_LIMIT,
        granted=granted,
    )
    assert outcome_drift.outcome == "failed"
    assert (
        "drift" in outcome_drift.summary.lower()
        or "rejected" in outcome_drift.summary.lower()
    )
    assert outcome_drift.result is None
    # No fabricated "completed"/"ok" evidence for a rejected drift attempt.
    assert _observations(repo, "verify_attempt:attempt-drift") == []

    # Source checkout remains completely unchanged across both refusals.
    assert (repo / "upload.py").read_text(encoding="utf-8") == orig_content
    current_head, current_tree = _head_and_tree(repo)
    assert (current_head, current_tree) == (base_commit, base_tree)
    assert _run_git(["status", "--porcelain"], repo) == ""


def test_unavailable_check_never_records_success(tmp_path: Path) -> None:
    repo = _init_upload_repo(tmp_path / "repo")
    base_commit, base_tree = _head_and_tree(repo)
    granted = ExecutionPermissions(cache_write=True, artifact_write=True, build=True)

    # No declared commands and no auto-detectable project markers in the sandbox
    # (no pytest.ini/tests/, package.json, Cargo.toml) -> zero executed commands.
    contract = PatchContract(
        base_commit=base_commit,
        base_tree_digest=base_tree,
        patch_content_digest="patch-z",
        sandbox_path=repo,
        required_commands=(),
        config_digest="cfg-z",
        review_class="standard",
    )
    outcome = verify_attempt(
        attempt_id="attempt-unavailable",
        behavior_ids=("upload-timeout-fixed",),
        repo_root=repo,
        contract=contract,
        patch=_PATCH_TIMEOUT_AND_SIZE_LIMIT,
        granted=granted,
    )

    assert outcome.outcome == "unavailable"
    assert outcome.result is not None
    assert outcome.result.executed_commands == ()
    assert outcome.result.passed_count == 0

    obs = _observations(repo, "verify_attempt:attempt-unavailable")
    assert len(obs) == 1
    assert obs[0]["outcome"] == "unavailable"
    assert obs[0]["outcome"] != "completed"
    assert not (repo / ".rush" / "worktrees" / "sandbox_placeholder").exists()


def test_verify_attempt_rejects_unknown_contract_field(tmp_path: Path) -> None:
    """`parse_patch_contract` never infers a field it wasn't given; malformed
    command payloads raise instead of silently producing an empty plan."""
    repo = tmp_path / "repo"
    repo.mkdir()
    try:
        parse_patch_contract({"required_commands": [{}]}, default_sandbox_path=repo)
    except KeyError:
        pass
    else:
        raise AssertionError(
            "expected KeyError for a command payload missing 'command'"
        )
