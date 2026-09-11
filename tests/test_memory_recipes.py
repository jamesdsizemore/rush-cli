"""MC08 (Phase 63) recipes: an adaptation pattern resolved against *current* project source
and dependencies (docs/phase-plans/MC08.md).

Exercises `rush.memory.recipes` directly and through `rush.tools.memory.MemoryTool`
(operation="recipe"). The CSV-export fixture is plan §9.0's fixed contract: an existing
`csv.writer`/`io.StringIO(newline="")` helper over rows `[["id","total"],["I-1","12.50"]]`
must produce exact text `id,total` + CRLF, `I-1,12.50` + CRLF; an unauthorized caller is
rejected; the dependency manifest is unchanged. One real adaptation, verified through MC05's
`verify_attempt` sandbox route, never proves the recipe universally applicable.
"""

from __future__ import annotations

import hashlib
import sqlite3
import subprocess
import sys
from pathlib import Path
from typing import Any

from rush.memory.recipes import (
    record_recipe,
    record_recipe_outcome,
    resolve_recipe,
    resolve_symbol_source,
)
from rush.memory.store import TypedArtifactStore
from rush.memory.verification import verify_attempt
from rush.patch.contracts import PatchContract, VerifierCommandPlan
from rush.patch_generator import generate_unified_diff
from rush.permissions import ExecutionPermissions
from rush.tools.memory import MemoryTool

_CSV_HELPER_ORIGINAL = (
    "import csv\n"
    "import io\n"
    "\n"
    "\n"
    'def export_rows(rows, caller="system"):\n'
    '    if caller != "system":\n'
    '        raise PermissionError(f"unauthorized caller: {caller}")\n'
    '    buf = io.StringIO(newline="")\n'
    "    writer = csv.writer(buf)\n"
    "    for row in rows:\n"
    "        writer.writerow(row)\n"
    "    return buf.getvalue()\n"
)

_CSV_HELPER_API_CHANGED = (
    "import csv\n"
    "import io\n"
    "\n"
    "\n"
    'def export_rows(rows, caller="system", strict=True):\n'
    '    if strict and caller != "system":\n'
    '        raise PermissionError(f"unauthorized caller: {caller}")\n'
    '    buf = io.StringIO(newline="")\n'
    "    writer = csv.writer(buf)\n"
    "    for row in rows:\n"
    "        writer.writerow(row)\n"
    "    return buf.getvalue()\n"
)

_EXPECTED_INVOICE_CSV = "id,total\r\nI-1,12.50\r\n"

_MANIFEST_CONTENT = '{"parser": "1.0"}\n'

_CHECK_INVOICE = (
    "import csv_helper\n\n"
    'invoice_rows = [["id", "total"], ["I-1", "12.50"]]\n'
    "assert csv_helper.export_invoice_csv(invoice_rows) == "
    f"{_EXPECTED_INVOICE_CSV!r}\n"
    "try:\n"
    '    csv_helper.export_invoice_csv(invoice_rows, caller="untrusted")\n'
    '    raise AssertionError("expected PermissionError for unauthorized caller")\n'
    "except PermissionError:\n"
    "    pass\n"
    'print("OK")\n'
)

_INVOICE_WRAPPER = (
    "\n\n"
    'def export_invoice_csv(rows, caller="system"):\n'
    "    return export_rows(rows, caller=caller)\n"
)

_HELPER_REF = {"path": "csv_helper.py", "symbol": "export_rows"}
_CHECKS = [
    {"kind": "authorization", "description": "rejects a non-system caller"},
    {
        "kind": "error_handling",
        "description": "raises PermissionError, never swallows it",
    },
]
_EXCEPTIONS = [
    "unauthorized caller must raise PermissionError, never return partial rows"
]


def _write_csv_project(
    root: Path, *, helper_source: str = _CSV_HELPER_ORIGINAL
) -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / "csv_helper.py").write_text(helper_source, encoding="utf-8")
    (root / "manifest.json").write_text(_MANIFEST_CONTENT, encoding="utf-8")


def _run_git(args: list[str], cwd: Path) -> str:
    proc = subprocess.run(
        ["git", *args], cwd=cwd, capture_output=True, text=True, check=True
    )
    return proc.stdout.strip()


def _init_csv_repo(root: Path) -> Path:
    _write_csv_project(root)
    (root / "check_invoice.py").write_text(_CHECK_INVOICE, encoding="utf-8")
    _run_git(["init", "-b", "main"], root)
    _run_git(["config", "user.name", "RushTester"], root)
    _run_git(["config", "user.email", "rush@example.com"], root)
    (root / ".gitignore").write_text(".rush/\n", encoding="utf-8")
    _run_git(["add", "."], root)
    _run_git(["commit", "-m", "csv helper with invoice check pending adaptation"], root)
    return root


def _head_and_tree(root: Path) -> tuple[str, str]:
    return _run_git(["rev-parse", "HEAD"], root), _run_git(
        ["rev-parse", "HEAD^{tree}"], root
    )


def _find_receipt(root: Path, source_prefix: str) -> dict[str, Any]:
    """Looks up the real `sandbox_verification` observation `verify_attempt()` wrote,
    mirroring `test_memory_verify_attempt.py`'s own raw-sqlite lookup precedent -- the
    artifact ID is server-generated (`uuid4()`), so the test cannot know it ahead of time."""
    db = root / ".rush" / "memory.db"
    with sqlite3.connect(db) as conn:
        row = conn.execute(
            "SELECT id, artifact_version FROM memory_artifacts WHERE family='experience' "
            "AND subject='episodic' AND source LIKE ? ORDER BY created_at DESC LIMIT 1",
            (f"{source_prefix}%",),
        ).fetchone()
    assert row is not None, f"no observation found for source prefix {source_prefix!r}"
    return {"id": row[0], "version": row[1]}


def test_csv_export_recipe_uses_current_project_implementation(tmp_path: Path) -> None:
    _write_csv_project(tmp_path)

    created = record_recipe(
        project_root=tmp_path,
        recipe_id="invoice-csv",
        purpose="export invoice rows through the existing csv.writer helper",
        helper_ref=_HELPER_REF,
        checks=_CHECKS,
        exceptions=_EXCEPTIONS,
    )
    assert created["code"] == "OK"

    resolved = resolve_recipe(project_root=tmp_path, recipe_id="invoice-csv")
    assert resolved["code"] == "OK"
    assert resolved["usable"] is True
    expected_source, expected_hash = resolve_symbol_source(tmp_path, _HELPER_REF)
    assert resolved["current_helper"]["source"] == expected_source
    assert resolved["current_helper"]["source_hash"] == expected_hash
    assert "def export_rows" in resolved["current_helper"]["source"]
    assert resolved["checks"] == _CHECKS
    assert resolved["exceptions"] == _EXCEPTIONS

    # Same route through MemoryTool (operation="recipe") -- confirms the wiring, not just
    # the bare recipes.py functions.
    granted = ExecutionPermissions(cache_write=True)
    tool_created = MemoryTool().run(
        tmp_path,
        operation="recipe",
        permissions=granted,
        request={
            "action": "record",
            "recipe_id": "invoice-csv-via-tool",
            "helper_ref": _HELPER_REF,
            "checks": _CHECKS,
            "exceptions": _EXCEPTIONS,
        },
    )
    assert tool_created["status"] == "ok"

    tool_resolved = MemoryTool().run(
        tmp_path,
        operation="recipe",
        request={"action": "resolve", "recipe_id": "invoice-csv-via-tool"},
    )
    assert tool_resolved["status"] == "ok"
    assert tool_resolved["raw"]["data"]["usable"] is True
    assert "def export_rows" in tool_resolved["raw"]["data"]["current_helper"]["source"]


def test_api_change_rejects_stale_recipe(tmp_path: Path) -> None:
    _write_csv_project(tmp_path)
    created = record_recipe(
        project_root=tmp_path,
        recipe_id="invoice-csv",
        helper_ref=_HELPER_REF,
        checks=_CHECKS,
        exceptions=_EXCEPTIONS,
    )
    assert created["code"] == "OK"

    still_current = resolve_recipe(project_root=tmp_path, recipe_id="invoice-csv")
    assert still_current["usable"] is True

    # The helper's real API changes (a new parameter, changed authorization semantics) --
    # resolve_recipe reads the file fresh every call, so this is caught immediately.
    (tmp_path / "csv_helper.py").write_text(_CSV_HELPER_API_CHANGED, encoding="utf-8")

    stale = resolve_recipe(project_root=tmp_path, recipe_id="invoice-csv")
    assert stale["code"] == "OK"
    assert stale["usable"] is False
    assert "source changed" in stale["reason"]
    assert stale["current_helper"] is None
    # Checks/exceptions are still surfaced even though the recipe is unusable.
    assert stale["checks"] == _CHECKS
    assert stale["exceptions"] == _EXCEPTIONS


def test_dependency_or_applicability_mismatch_explained(tmp_path: Path) -> None:
    _write_csv_project(tmp_path)
    (tmp_path / "other_helper.py").write_text(
        "def helper_two():\n    return True\n", encoding="utf-8"
    )
    created = record_recipe(
        project_root=tmp_path,
        recipe_id="invoice-csv",
        helper_ref=_HELPER_REF,
        required_symbols=[{"path": "other_helper.py", "symbol": "helper_two"}],
        required_dependencies={"parser": "1.0"},
        checks=_CHECKS,
        exceptions=_EXCEPTIONS,
    )
    assert created["code"] == "OK"

    # Baseline: matching dependencies, present required symbol -- usable.
    baseline = resolve_recipe(
        project_root=tmp_path,
        recipe_id="invoice-csv",
        current_dependencies={"parser": "1.0"},
    )
    assert baseline["usable"] is True

    # Case A: dependency version drift -- named, distinct reason.
    dependency_mismatch = resolve_recipe(
        project_root=tmp_path,
        recipe_id="invoice-csv",
        current_dependencies={"parser": "2.0"},
    )
    assert dependency_mismatch["usable"] is False
    assert "dependency mismatch" in dependency_mismatch["reason"]
    assert "parser" in dependency_mismatch["reason"]

    # Case B: a required symbol disappears -- a different, equally named reason.
    (tmp_path / "other_helper.py").unlink()
    symbol_mismatch = resolve_recipe(
        project_root=tmp_path,
        recipe_id="invoice-csv",
        current_dependencies={"parser": "1.0"},
    )
    assert symbol_mismatch["usable"] is False
    assert "missing required symbol" in symbol_mismatch["reason"]

    assert dependency_mismatch["reason"] != symbol_mismatch["reason"]
    # Neither applicability failure drops the declared safety checks.
    assert dependency_mismatch["checks"] == _CHECKS
    assert symbol_mismatch["checks"] == _CHECKS


def test_recipe_keeps_authorization_and_error_handling_checks(tmp_path: Path) -> None:
    _write_csv_project(tmp_path)
    created = record_recipe(
        project_root=tmp_path,
        recipe_id="invoice-csv",
        helper_ref=_HELPER_REF,
        required_dependencies={"parser": "1.0"},
        checks=_CHECKS,
        exceptions=_EXCEPTIONS,
    )
    assert created["code"] == "OK"

    usable = resolve_recipe(
        project_root=tmp_path,
        recipe_id="invoice-csv",
        current_dependencies={"parser": "1.0"},
    )
    assert usable["usable"] is True
    assert usable["checks"] == _CHECKS
    assert usable["exceptions"] == _EXCEPTIONS

    unusable = resolve_recipe(
        project_root=tmp_path,
        recipe_id="invoice-csv",
        current_dependencies={"parser": "9.9"},
    )
    assert unusable["usable"] is False
    # Identical checks/exceptions whether the recipe currently applies or not.
    assert unusable["checks"] == usable["checks"] == _CHECKS
    assert unusable["exceptions"] == usable["exceptions"] == _EXCEPTIONS


def test_adaptation_pass_does_not_prove_universal_recipe(tmp_path: Path) -> None:
    repo = _init_csv_repo(tmp_path / "repo")
    base_commit, base_tree = _head_and_tree(repo)
    granted = ExecutionPermissions(cache_write=True, artifact_write=True, build=True)

    created = record_recipe(
        project_root=repo,
        recipe_id="invoice-csv",
        purpose="export invoice rows through the existing csv.writer helper",
        helper_ref=_HELPER_REF,
        required_dependencies={"parser": "1.0"},
        required_config_digest="cfg-1",
        checks=_CHECKS,
        exceptions=_EXCEPTIONS,
    )
    assert created["code"] == "OK"
    recipe_version = created["version"]

    manifest_before = (repo / "manifest.json").read_text(encoding="utf-8")

    # A bare `passed=True` claim is structurally impossible -- there is no such parameter.
    try:
        record_recipe_outcome(  # type: ignore[call-arg]
            project_root=repo,
            recipe_id="invoice-csv",
            recipe_version=recipe_version,
            patch_hash="deadbeef",
            verifier_receipt_ref={"id": "does-not-exist", "version": 1},
            passed=True,
        )
    except TypeError:
        pass
    else:
        raise AssertionError(
            "record_recipe_outcome accepted an unexpected 'passed' kwarg"
        )

    # A receipt_ref pointing at nothing real is rejected outright.
    fake_receipt_result = record_recipe_outcome(
        project_root=repo,
        recipe_id="invoice-csv",
        recipe_version=recipe_version,
        patch_hash="deadbeef",
        verifier_receipt_ref={"id": "does-not-exist", "version": 1},
    )
    assert fake_receipt_result["code"] == "E_INPUT"

    # Real adaptation: patch adds export_invoice_csv() reusing export_rows(), verified
    # through the existing MC05 sandbox route -- never a second/parallel verification path.
    patched_helper = _CSV_HELPER_ORIGINAL + _INVOICE_WRAPPER
    patch_text = generate_unified_diff(
        _CSV_HELPER_ORIGINAL, patched_helper, "csv_helper.py"
    )
    patch_hash = hashlib.sha256(patch_text.encode("utf-8")).hexdigest()

    contract = PatchContract(
        base_commit=base_commit,
        base_tree_digest=base_tree,
        patch_content_digest=patch_hash,
        sandbox_path=repo,
        required_commands=(
            VerifierCommandPlan(
                command=(sys.executable, "check_invoice.py"), expected_exit_code=0
            ),
        ),
        config_digest="cfg-1",
        review_class="standard",
    )
    outcome = verify_attempt(
        attempt_id="invoice-csv-adaptation",
        behavior_ids=("invoice-csv-export",),
        repo_root=repo,
        contract=contract,
        patch=patch_text,
        granted=granted,
    )
    assert outcome.outcome == "completed", outcome.summary
    assert outcome.result is not None
    executed = outcome.result.executed_commands[0]
    assert executed["passed"] is True
    assert "OK" in executed["stdout"]

    # The real checkout (and its dependency manifest) is untouched -- verify_attempt never
    # merges/promotes the sandbox's patch.
    assert (repo / "manifest.json").read_text(encoding="utf-8") == manifest_before
    assert (repo / "csv_helper.py").read_text(encoding="utf-8") == _CSV_HELPER_ORIGINAL
    current_head, current_tree = _head_and_tree(repo)
    assert (current_head, current_tree) == (base_commit, base_tree)

    receipt_ref = _find_receipt(repo, "verify_attempt:invoice-csv-adaptation")

    recorded_outcome = record_recipe_outcome(
        project_root=repo,
        recipe_id="invoice-csv",
        recipe_version=recipe_version,
        patch_hash=patch_hash,
        verifier_receipt_ref=receipt_ref,
    )
    assert recorded_outcome["code"] == "OK"
    assert recorded_outcome["passed"] is True
    assert recorded_outcome["outcomes_count"] == 1

    # One passing adaptation never widens applicability, drops safety checks, or promotes
    # trust toward STATED.
    store = TypedArtifactStore(repo)
    current_artifact = store.get_current("invoice-csv")
    assert current_artifact is not None
    assert current_artifact.trust_tier != "STATED"
    assert current_artifact.content["required_dependencies"] == {"parser": "1.0"}
    assert current_artifact.content["checks"] == _CHECKS
    assert current_artifact.content["exceptions"] == _EXCEPTIONS

    still_matching = resolve_recipe(
        project_root=repo,
        recipe_id="invoice-csv",
        current_dependencies={"parser": "1.0"},
        current_config_digest="cfg-1",
    )
    assert still_matching["usable"] is True
    assert still_matching["checks"] == _CHECKS

    # A genuinely different environment is still rejected -- the passing outcome proved
    # exactly one patch under one receipt, never a universal recipe.
    different_environment = resolve_recipe(
        project_root=repo,
        recipe_id="invoice-csv",
        current_dependencies={"parser": "2.0"},
        current_config_digest="cfg-1",
    )
    assert different_environment["usable"] is False
    assert "dependency mismatch" in different_environment["reason"]
    assert different_environment["checks"] == _CHECKS
    assert different_environment["exceptions"] == _EXCEPTIONS

    # Recording a second outcome against a now-stale recipe_version is refused (compare-
    # and-swap), never silently accepted against whatever the current version happens to be.
    stale_version_result = record_recipe_outcome(
        project_root=repo,
        recipe_id="invoice-csv",
        recipe_version=recipe_version,
        patch_hash=patch_hash,
        verifier_receipt_ref=receipt_ref,
    )
    assert stale_version_result["code"] == "E_VERSION"
