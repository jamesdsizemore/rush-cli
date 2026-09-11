"""MC15 (Phase 63 plan 9, MC15.1): one real end-to-end acceptance scenario assembling
MC01-MC14 together -- confirmed intent, a failed repair attempt, a verified sandbox repair,
a recipe tied to that same verified receipt, ranked check evidence, and a real restricted
handoff receiver (a live `rush mcp serve --memory-session` subprocess speaking the real MCP
protocol) -- against one shared project store. Every step drives real production code
(`rush.tools.memory.MemoryTool`, `rush.memory.intent`, `rush.memory.recipes`,
`rush.memory.verification`, `rush.memory.handoff`); nothing here is a hand-rolled stand-in
for a live call.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import os
import sqlite3
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import pytest

from rush.memory.experience import write_observation
from rush.memory.handoff import prepare_handoff
from rush.memory.intent import check_intent
from rush.memory.recipes import record_recipe, record_recipe_outcome, resolve_recipe
from rush.memory.store import MemoryArtifact, TypedArtifactStore
from rush.memory.trust import default_entry_tier
from rush.memory.verification import plan_checks
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

_BEHAVIOR_ID = "upload-timeout-and-size-limit-fixed"
_INTENT_ID = "upload-guard-intent"
_RECIPE_ID = "upload-guard-recipe"
_ATTEMPT_FAILED = "attempt-partial-fix"
_ATTEMPT_VERIFIED = "attempt-full-fix"


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


def _find_receipt(root: Path, source: str) -> dict[str, Any]:
    """Looks up the real, server-generated `sandbox_verification` observation
    `verify_attempt()` wrote (its artifact id is `uuid4()`, unknowable ahead of time)."""
    db = root / ".rush" / "memory.db"
    with sqlite3.connect(db) as conn:
        row = conn.execute(
            "SELECT id, artifact_version, content FROM memory_artifacts "
            "WHERE family='experience' AND subject='episodic' AND source=? "
            "ORDER BY created_at DESC LIMIT 1",
            (source,),
        ).fetchone()
    assert row is not None, f"no observation found for source {source!r}"
    return {"id": row[0], "version": row[1], "content": json.loads(row[2])}


def _digest(store: TypedArtifactStore, artifact_id: str, version: int) -> str:
    content = store.get_version_content(artifact_id, version)
    assert content is not None
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _rush_bin() -> str:
    same_env = Path(sys.executable).with_name("rush")
    assert same_env.exists(), (
        "expected a sibling rush console script for this interpreter"
    )
    return str(same_env)


def _stated_statement(repo: Path, statement_id: str) -> dict[str, Any]:
    store = TypedArtifactStore(repo)
    store.write(
        MemoryArtifact(
            id=statement_id,
            family="memory",
            subject="architectural_decision",
            trust_tier=default_entry_tier("local_tool"),
            content={"statement": "reject overlong and oversized uploads"},
            source="user:cli",
            created_at=time.time(),
        )
    )
    artifact, decision = store.promote(statement_id, user_stated=True)
    assert decision.promoted, decision.denial_reason
    return {"id": artifact.id, "version": artifact.artifact_version}


def _run_check_command_plan(check_id: str) -> dict[str, Any]:
    return {
        "id": check_id,
        "argv": [sys.executable, "check_upload.py"],
        "cwd": ".",
        "expected_exit": 0,
        "timeout_seconds": 30,
        "permissions": [],
    }


def test_end_to_end_intent_repair_recipe_check_and_real_receiver(
    tmp_path: Path,
) -> None:
    """MC15.1: a single assembled scenario -- confirmed intent, a real failed repair
    attempt, a real verified sandbox repair, a recipe carrying that receipt as evidence,
    ranked required-check evidence, and a real restricted handoff receiver reading the
    result back through the actual MCP-bridge subprocess."""
    pytest.importorskip("mcp.client.stdio")
    from mcp import ClientSession
    from mcp.client.stdio import StdioServerParameters, stdio_client

    repo = _init_upload_repo(tmp_path / "repo")
    base_commit, base_tree = _head_and_tree(repo)
    orig_upload_source = (repo / "upload.py").read_text(encoding="utf-8")
    granted = ExecutionPermissions(cache_write=True, artifact_write=True, build=True)
    tool = MemoryTool()

    # -- 1. A confirmed user statement backing this behavior's requirement. --
    statement = _stated_statement(repo, "req-upload-guard")

    # -- 2. Failed repair: a partial patch (timeout guard only) -- real check exits 1. --
    failed_result = tool.run(
        repo,
        operation="verify_attempt",
        permissions=granted,
        request={
            "attempt_id": _ATTEMPT_FAILED,
            "behavior_ids": [_BEHAVIOR_ID],
            "contract": {
                "base_commit": base_commit,
                "base_tree_digest": base_tree,
                "patch_content_digest": "patch-partial",
                "required_commands": [{"command": [sys.executable, "check_upload.py"]}],
                "config_digest": "cfg-partial",
                "review_class": "standard",
            },
            "patch": _PATCH_TIMEOUT_ONLY,
        },
    )
    assert failed_result["status"] == "fail"
    assert failed_result["raw"]["outcome"] == "failed"
    failed_executed = failed_result["raw"]["result"]["executed_commands"][0]
    assert failed_executed["exit_code"] != 0
    assert failed_executed["passed"] is False

    # -- 3. Verified sandbox repair: the full patch -- real check exits 0. --
    verified_result = tool.run(
        repo,
        operation="verify_attempt",
        permissions=granted,
        request={
            "attempt_id": _ATTEMPT_VERIFIED,
            "behavior_ids": [_BEHAVIOR_ID],
            "contract": {
                "base_commit": base_commit,
                "base_tree_digest": base_tree,
                "patch_content_digest": "patch-full",
                "required_commands": [{"command": [sys.executable, "check_upload.py"]}],
                "config_digest": "cfg-full",
                "review_class": "standard",
            },
            "patch": _PATCH_TIMEOUT_AND_SIZE_LIMIT,
        },
    )
    assert verified_result["status"] == "ok"
    assert verified_result["raw"]["outcome"] == "completed"
    verified_executed = verified_result["raw"]["result"]["executed_commands"][0]
    assert verified_executed["exit_code"] == 0
    assert verified_executed["passed"] is True
    assert "OK" in verified_executed["stdout"]

    # Real receipt artifact identities for the recipe/intent/handoff legs below.
    receipt_ref = _find_receipt(repo, f"verify_attempt:{_ATTEMPT_VERIFIED}")
    assert receipt_ref["content"]["evidence_kind"] == "sandbox_verification"
    assert receipt_ref["content"]["outcome"] == "completed"

    # -- 4. Recipe evidence: current source resolved fresh, then tied to the real receipt. --
    created_recipe = record_recipe(
        project_root=repo,
        recipe_id=_RECIPE_ID,
        purpose="apply the timeout+size guard pattern to upload()",
        helper_ref={"path": "upload.py", "symbol": "upload"},
        checks=[
            {"kind": "behavioral", "description": "rejects overlong/oversized uploads"}
        ],
        exceptions=["never silently allow an oversized or overlong upload"],
    )
    assert created_recipe["code"] == "OK"
    resolved_recipe = resolve_recipe(project_root=repo, recipe_id=_RECIPE_ID)
    assert resolved_recipe["code"] == "OK"
    assert resolved_recipe["usable"] is True
    assert "def upload" in resolved_recipe["current_helper"]["source"]

    patch_hash = hashlib.sha256(
        _PATCH_TIMEOUT_AND_SIZE_LIMIT.encode("utf-8")
    ).hexdigest()
    recorded_outcome = record_recipe_outcome(
        project_root=repo,
        recipe_id=_RECIPE_ID,
        recipe_version=created_recipe["version"],
        patch_hash=patch_hash,
        verifier_receipt_ref={
            "id": receipt_ref["id"],
            "version": receipt_ref["version"],
        },
    )
    assert recorded_outcome["code"] == "OK"
    assert recorded_outcome["passed"] is True
    assert recorded_outcome["outcomes_count"] == 1
    recipe_version = recorded_outcome["version"]

    # -- 5. Check evidence: a real regression finding ranks its own check first, without
    # dropping the unrelated required check. --
    write_observation(
        evidence_kind="tests_contracts",
        operation_id="contract",
        source="test:acceptance-regression",
        content={
            "check_id": "check-upload",
            "targets": ["upload.upload"],
            "status": "fail",
        },
        project_root=repo,
    )
    plan_result = tool.run(
        repo,
        operation="plan_checks",
        request={
            "changed_targets": [{"id": "upload.upload", "version": None}],
            "required_checks": [
                _run_check_command_plan("check-upload"),
                {
                    "id": "check-unrelated",
                    "argv": ["true"],
                    "cwd": ".",
                    "expected_exit": 0,
                    "timeout_seconds": 5,
                    "permissions": [],
                },
            ],
            "environment": {},
        },
    )
    assert plan_result["status"] == "ok"
    plan_data = plan_result["raw"]["data"]
    assert plan_data["checks"][0]["ids"] == ["check-upload"]
    assert sorted(plan_data["required_ids"]) == ["check-unrelated", "check-upload"]
    # The ranked check's own argv is the exact command the verified attempt just executed.
    assert list(verified_executed["command"]) == [sys.executable, "check_upload.py"]

    # Cross-checked directly too, mirroring MC09's own contract (never trust only the tool
    # wrapper's envelope).
    bare_plan = plan_checks(
        project_root=repo,
        changed_targets=[{"id": "upload.upload", "version": None}],
        required_checks=[
            _run_check_command_plan("check-upload"),
            {"id": "check-unrelated", "argv": ["true"], "cwd": "."},
        ],
        environment={},
    )
    assert bare_plan["checks"][0]["ids"] == ["check-upload"]

    # -- 6. Confirmed intent, bound to the real receipt and the exact current revision. --
    intent_result = tool.run(
        repo,
        operation="intent",
        permissions=ExecutionPermissions(cache_write=True),
        request={
            "action": "create",
            "intent_id": _INTENT_ID,
            "behavior_id": _BEHAVIOR_ID,
            "statement_ref": statement,
            "check_refs": [
                {"id": receipt_ref["id"], "version": receipt_ref["version"]}
            ],
        },
    )
    assert intent_result["status"] == "ok"
    assert intent_result["raw"]["data"]["status"] == "confirmed"

    check_result = check_intent(
        project_root=repo, intent_id=_INTENT_ID, current_revision=base_commit
    )
    assert check_result["code"] == "OK"
    assert check_result["passed"] is True

    # -- 7. Real local receiver: a bounded handoff session carrying the intent, the
    # verified receipt and the recipe -- pulled through a real, spawned
    # `rush mcp serve --memory-session` subprocess speaking the real MCP protocol. --
    store = TypedArtifactStore(repo)
    granted_ids = [_INTENT_ID, receipt_ref["id"], _RECIPE_ID]
    session_allowlist = [
        f"intent:{_INTENT_ID}",
        f"verify_attempt:{_ATTEMPT_VERIFIED}",
        f"recipe:{_RECIPE_ID}",
    ]
    session, capability, initial_delta = prepare_handoff(
        store,
        root=repo,
        audience="acceptance-receiver",
        granted_ids=granted_ids,
        session_allowlist=session_allowlist,
        constraints={"goal": "assembled MC15 acceptance handoff"},
    )
    assert {change["id"] for change in initial_delta["changes"]} == set(granted_ids)

    row_count_before = _artifact_version_row_count(repo)

    async def _run_receiver() -> tuple[
        list[str], dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]
    ]:
        params = StdioServerParameters(
            command=_rush_bin(),
            args=["mcp", "serve", "--memory-session", session.session_id],
            env={
                "RUSH_MEMORY_CAPABILITY": capability,
                "PATH": os.environ.get("PATH", ""),
            },
            cwd=str(repo),
        )
        async with (
            stdio_client(params) as (read, write),
            ClientSession(read, write) as client,
        ):
            await client.initialize()
            tools = await client.list_tools()

            received = await client.call_tool(
                "rush_memory", {"operation": "receive", "request": {}}
            )
            received_data = json.loads(received.content[0].text)["data"]

            expanded: dict[str, dict[str, Any]] = {}
            for artifact_id in granted_ids:
                version = next(
                    c["version"]
                    for c in received_data["changes"]
                    if c["id"] == artifact_id
                )
                expand_result = await client.call_tool(
                    "rush_memory",
                    {
                        "operation": "expand",
                        "request": {"id": artifact_id, "version": version},
                    },
                )
                expanded[artifact_id] = json.loads(expand_result.content[0].text)[
                    "data"
                ]

            ack = [
                {
                    "id": artifact_id,
                    "version": next(
                        c["version"]
                        for c in received_data["changes"]
                        if c["id"] == artifact_id
                    ),
                    "digest": _digest(
                        store,
                        artifact_id,
                        next(
                            c["version"]
                            for c in received_data["changes"]
                            if c["id"] == artifact_id
                        ),
                    ),
                }
                for artifact_id in granted_ids
            ]
            acked = await client.call_tool(
                "rush_memory",
                {"operation": "receive", "request": {"ack": ack}},
            )
            acked_data = json.loads(acked.content[0].text)["data"]

            replay = await client.call_tool(
                "rush_memory",
                {"operation": "receive", "request": {"ack": ack}},
            )
            replay_data = json.loads(replay.content[0].text)["data"]

            return (
                [t.name for t in tools.tools],
                received_data,
                expanded,
                acked_data,
                replay_data,
            )

    tool_names, received_data, expanded, acked_data, replay_data = asyncio.run(
        _run_receiver()
    )

    assert tool_names == ["rush_memory"]
    assert {c["id"] for c in received_data["changes"]} == set(granted_ids)

    # The receiver expanded exact stored versions -- byte-identical to the sender's store.
    for artifact_id, exp in expanded.items():
        version = next(
            c["version"] for c in received_data["changes"] if c["id"] == artifact_id
        )
        expected_bytes = store.get_version_content(artifact_id, version)
        assert base64.b64decode(exp["content_base64"]).decode("utf-8") == expected_bytes

    # Read-back advanced the cursor exactly once per artifact -- a bare receive/expand never
    # does, and acking twice never duplicates authority or rows.
    assert store.get_handoff_receipts(session.session_id) == {
        artifact_id: next(
            c["version"] for c in received_data["changes"] if c["id"] == artifact_id
        )
        for artifact_id in granted_ids
    }
    assert acked_data["changes"] == []
    assert replay_data["changes"] == []
    assert _artifact_version_row_count(repo) == row_count_before

    # -- 8. Assert actual end state (MC15.2). --
    # Source checkout is completely unchanged by any sandbox attempt.
    assert (repo / "upload.py").read_text(encoding="utf-8") == orig_upload_source
    current_head, current_tree = _head_and_tree(repo)
    assert (current_head, current_tree) == (base_commit, base_tree)
    assert _run_git(["status", "--porcelain"], repo) == ""

    # The original confirmed intent is retained, unmutated by the handoff read.
    still_confirmed = check_intent(
        project_root=repo, intent_id=_INTENT_ID, current_revision=base_commit
    )
    assert still_confirmed["passed"] is True

    # The failed attempt's observation is still recorded as failed -- immutable evidence.
    failed_receipt = _find_receipt(repo, f"verify_attempt:{_ATTEMPT_FAILED}")
    assert failed_receipt["content"]["outcome"] == "failed"

    # The recipe still carries its one real passing outcome at its final version.
    final_recipe = store.get_current(_RECIPE_ID)
    assert final_recipe is not None
    assert final_recipe.artifact_version == recipe_version
    assert final_recipe.content["outcomes"][-1]["passed"] is True


def _artifact_version_row_count(repo: Path) -> int:
    db = repo / ".rush" / "memory.db"
    with sqlite3.connect(db) as conn:
        return conn.execute("SELECT COUNT(*) FROM memory_artifact_versions").fetchone()[
            0
        ]
