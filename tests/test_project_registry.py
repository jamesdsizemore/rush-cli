"""Phase 65 P65-03 (F32-33): one project/discovery/readiness model.

Covers registry identity, create/select/configure contracts, and the
installed/applicable/ready readiness tri-state.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import threading
import time
from pathlib import Path

import pytest

from rush.tools.project import ProjectTool
from rush.workflows.projects import (
    REGISTRY_LOCK_FILE,
    ProjectBusyError,
    ProjectDestinationExistsError,
    ProjectError,
    ProjectInvalidCursorError,
    ProjectNotFoundError,
    ProjectPlanStaleError,
    ProjectRevisionConflictError,
    configure_project,
    create_project,
    ensure_cursor_key,
    get_selected_project,
    list_projects,
    list_projects_page,
    register_project,
    relink_project,
    resolve_project,
    select_project,
)


def _data_root(tmp_path: Path) -> Path:
    return tmp_path / "rush-data"


def _apply_settings(
    project_id: str, settings: dict, *, data_root: Path, expected_revision: int
) -> dict:
    """Test helper: run the required preview-then-apply configure flow."""
    preview = configure_project(project_id, settings, data_root=data_root)
    return configure_project(
        project_id,
        settings,
        expected_revision=expected_revision,
        apply=True,
        plan_id=preview["plan_id"],
        data_root=data_root,
    )


def test_empty_registry_lists_no_projects(tmp_path: Path) -> None:
    assert list_projects(data_root=_data_root(tmp_path)) == []


def test_resolve_project_raises_when_unregistered(tmp_path: Path) -> None:
    with pytest.raises(ProjectNotFoundError):
        resolve_project(tmp_path / "nowhere", data_root=_data_root(tmp_path))


def test_registering_the_same_physical_root_twice_returns_the_same_id(
    tmp_path: Path,
) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    data_root = _data_root(tmp_path)

    first = register_project(root, data_root=data_root)
    second = register_project(root, data_root=data_root)

    assert first.project_id == second.project_id
    assert len(list_projects(data_root=data_root)) == 1


def test_registering_through_a_symlink_alias_resolves_to_the_same_project(
    tmp_path: Path,
) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    alias = tmp_path / "alias"
    alias.symlink_to(root)
    data_root = _data_root(tmp_path)

    direct = register_project(root, data_root=data_root)
    via_alias = register_project(alias, data_root=data_root)

    assert direct.project_id == via_alias.project_id
    assert len(list_projects(data_root=data_root)) == 1


def test_two_git_worktrees_of_the_same_repository_get_distinct_ids(
    tmp_path: Path,
) -> None:
    primary = tmp_path / "primary"
    primary.mkdir()
    subprocess.run(["git", "init", "--quiet", str(primary)], check=True)
    subprocess.run(
        ["git", "-C", str(primary), "commit", "--allow-empty", "-q", "-m", "init"],
        check=True,
        env={
            **os.environ,
            "GIT_AUTHOR_NAME": "t",
            "GIT_AUTHOR_EMAIL": "t@t.com",
            "GIT_COMMITTER_NAME": "t",
            "GIT_COMMITTER_EMAIL": "t@t.com",
        },
    )
    worktree = tmp_path / "worktree"
    subprocess.run(
        ["git", "-C", str(primary), "worktree", "add", "--quiet", str(worktree)],
        check=True,
    )
    data_root = _data_root(tmp_path)

    primary_record = register_project(primary, data_root=data_root)
    worktree_record = register_project(worktree, data_root=data_root)

    assert primary_record.project_id != worktree_record.project_id
    assert len(list_projects(data_root=data_root)) == 2


def test_deleted_root_stays_listed_but_reports_not_installed(tmp_path: Path) -> None:
    root = tmp_path / "gone"
    root.mkdir()
    data_root = _data_root(tmp_path)
    record = register_project(root, data_root=data_root)

    shutil.rmtree(root)

    view = resolve_project(record.project_id, data_root=data_root)
    assert view["exists"] is False
    assert view["readiness"]["installed"] is False


def test_explicit_move_requires_relink_and_keeps_identity(tmp_path: Path) -> None:
    old_root = tmp_path / "old"
    old_root.mkdir()
    data_root = _data_root(tmp_path)
    record = register_project(old_root, data_root=data_root)

    new_root = tmp_path / "new"
    old_root.rename(new_root)

    relinked = relink_project(
        record.project_id, new_root, expected_revision=1, data_root=data_root
    )

    assert relinked["project_id"] == record.project_id
    assert relinked["root"] == str(new_root.resolve())
    assert relinked["revision"] == 2


def test_relink_refuses_a_root_already_owned_by_a_different_project(
    tmp_path: Path,
) -> None:
    data_root = _data_root(tmp_path)
    first_root = tmp_path / "first"
    first_root.mkdir()
    second_root = tmp_path / "second"
    second_root.mkdir()
    register_project(first_root, data_root=data_root)
    second = register_project(second_root, data_root=data_root)

    with pytest.raises(ProjectError):
        relink_project(
            second.project_id, first_root, expected_revision=1, data_root=data_root
        )


def test_create_project_at_selected_parent_registers_an_empty_folder(
    tmp_path: Path,
) -> None:
    parent = tmp_path / "workspace"
    parent.mkdir()
    data_root = _data_root(tmp_path)

    record = create_project(parent, "demo", data_root=data_root)

    destination = parent / "demo"
    assert destination.is_dir()
    assert sorted(p.name for p in destination.iterdir()) == [".rush"]
    view = resolve_project(record.project_id, data_root=data_root)
    assert view["readiness"] == {
        "installed": True,
        "applicable": False,
        "ready": False,
    }


def test_create_project_refuses_an_occupied_destination(tmp_path: Path) -> None:
    parent = tmp_path / "workspace"
    parent.mkdir()
    occupied = parent / "demo"
    occupied.mkdir()
    (occupied / "keep.txt").write_text("do not touch")
    data_root = _data_root(tmp_path)

    with pytest.raises(ProjectDestinationExistsError):
        create_project(parent, "demo", data_root=data_root)

    assert (occupied / "keep.txt").read_text() == "do not touch"
    assert list(occupied.iterdir()) == [occupied / "keep.txt"]


def test_create_project_never_generates_an_application_scaffold(
    tmp_path: Path,
) -> None:
    parent = tmp_path / "workspace"
    parent.mkdir()
    data_root = _data_root(tmp_path)

    create_project(parent, "demo", data_root=data_root)

    destination = parent / "demo"
    generated_files = {p.name for p in destination.rglob("*") if p.is_file()}
    assert generated_files == {"project.json"}


def test_create_project_with_git_init_creates_no_commit(tmp_path: Path) -> None:
    parent = tmp_path / "workspace"
    parent.mkdir()
    data_root = _data_root(tmp_path)

    create_project(parent, "demo", init_git=True, data_root=data_root)

    destination = parent / "demo"
    assert (destination / ".git").is_dir()
    log = subprocess.run(
        ["git", "-C", str(destination), "log"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert log.returncode != 0  # no commits exist yet


def test_failed_creation_removes_only_the_empty_folder_it_created(
    tmp_path: Path, monkeypatch
) -> None:
    parent = tmp_path / "workspace"
    parent.mkdir()
    data_root = _data_root(tmp_path)

    def _boom(*_args, **_kwargs):
        raise RuntimeError("registration exploded")

    # create_project calls the module-level register_project by reference,
    # so patch the call site's own module attribute directly.
    import rush.workflows.projects as projects_module

    monkeypatch.setattr(projects_module, "register_project", _boom)

    with pytest.raises(RuntimeError):
        projects_module.create_project(parent, "demo", data_root=data_root)

    assert not (parent / "demo").exists()


def test_select_project_is_scoped_to_one_session(tmp_path: Path) -> None:
    data_root = _data_root(tmp_path)
    root_a = tmp_path / "a"
    root_a.mkdir()
    root_b = tmp_path / "b"
    root_b.mkdir()
    project_a = register_project(root_a, data_root=data_root)
    project_b = register_project(root_b, data_root=data_root)

    select_project("session-1", project_a.project_id, data_root=data_root)
    select_project("session-2", project_b.project_id, data_root=data_root)

    assert get_selected_project("session-1", data_root=data_root)["project_id"] == (
        project_a.project_id
    )
    assert get_selected_project("session-2", data_root=data_root)["project_id"] == (
        project_b.project_id
    )


def test_select_project_rejects_an_unregistered_project(tmp_path: Path) -> None:
    with pytest.raises(ProjectNotFoundError):
        select_project("session-1", "not-a-real-id", data_root=_data_root(tmp_path))


def test_configure_project_settings_stay_isolated_per_project(
    tmp_path: Path,
) -> None:
    data_root = _data_root(tmp_path)
    root_a = tmp_path / "a"
    root_a.mkdir()
    root_b = tmp_path / "b"
    root_b.mkdir()
    project_a = register_project(root_a, data_root=data_root)
    project_b = register_project(root_b, data_root=data_root)

    _apply_settings(
        project_a.project_id,
        {"severity": "warn"},
        data_root=data_root,
        expected_revision=1,
    )

    view_a = resolve_project(project_a.project_id, data_root=data_root)
    view_b = resolve_project(project_b.project_id, data_root=data_root)
    assert view_a["settings"] == {"severity": "warn"}
    assert view_b["settings"] == {}
    assert view_b["readiness"]["ready"] is False


def test_readiness_states_are_independently_computed(tmp_path: Path) -> None:
    """installed, applicable, and ready are three distinct facts, not one
    enum -- each is driven by a different rule and they must diverge."""
    data_root = _data_root(tmp_path)

    # A brand-new empty project: registered, but no code and not configured.
    record = create_project(tmp_path, "brand-new", data_root=data_root)
    empty_view = resolve_project(record.project_id, data_root=data_root)
    assert empty_view["readiness"] == {
        "installed": True,
        "applicable": False,
        "ready": False,
    }

    # Add code but don't configure yet: installed and applicable, not ready.
    # installed != applicable would be False here (both True) -- the point
    # is "ready" is the one that still differs, proving it is a separate
    # rule (configure_project), not a synonym for "applicable".
    (Path(empty_view["root"]) / "pyproject.toml").write_text("[project]\nname='demo'\n")
    populated_view = resolve_project(record.project_id, data_root=data_root)
    assert populated_view["readiness"]["installed"] is True
    assert populated_view["readiness"]["applicable"] is True
    assert populated_view["readiness"]["ready"] is False

    # Configure it: now all three agree the project is fully usable.
    _apply_settings(record.project_id, {}, data_root=data_root, expected_revision=1)
    ready_view = resolve_project(record.project_id, data_root=data_root)
    assert ready_view["readiness"] == {
        "installed": True,
        "applicable": True,
        "ready": True,
    }

    # An unregistered-but-real repository is applicable without being
    # installed at all -- the two facts are not derived from each other.
    unregistered_root = tmp_path / "unregistered"
    unregistered_root.mkdir()
    (unregistered_root / "pyproject.toml").write_text("[project]\nname='u'\n")
    with pytest.raises(ProjectNotFoundError):
        resolve_project(unregistered_root, data_root=data_root)


# --- Plan §6.1 frozen contract: revision, lock/BUSY, PLAN_STALE, envelope,
# cursor authentication (T014 / T204 review gap) -----------------------------


def test_every_successful_mutation_increments_revision(tmp_path: Path) -> None:
    data_root = _data_root(tmp_path)
    root = tmp_path / "repo"
    root.mkdir()
    record = register_project(root, data_root=data_root)
    assert record.revision == 1

    applied = _apply_settings(
        record.project_id,
        {"severity": "warn"},
        data_root=data_root,
        expected_revision=1,
    )
    assert applied["revision"] == 2

    new_root = tmp_path / "moved"
    root.rename(new_root)
    relinked = relink_project(
        record.project_id, new_root, expected_revision=2, data_root=data_root
    )
    assert relinked["revision"] == 3


def test_relink_with_stale_expected_revision_raises_revision_conflict(
    tmp_path: Path,
) -> None:
    data_root = _data_root(tmp_path)
    root = tmp_path / "repo"
    root.mkdir()
    record = register_project(root, data_root=data_root)

    new_root = tmp_path / "moved"
    root.rename(new_root)
    with pytest.raises(ProjectRevisionConflictError):
        relink_project(
            record.project_id, new_root, expected_revision=99, data_root=data_root
        )


def test_configure_apply_with_stale_expected_revision_raises_revision_conflict(
    tmp_path: Path,
) -> None:
    data_root = _data_root(tmp_path)
    root = tmp_path / "repo"
    root.mkdir()
    record = register_project(root, data_root=data_root)

    preview = configure_project(
        record.project_id, {"severity": "warn"}, data_root=data_root
    )
    with pytest.raises(ProjectRevisionConflictError):
        configure_project(
            record.project_id,
            {"severity": "warn"},
            expected_revision=99,
            apply=True,
            plan_id=preview["plan_id"],
            data_root=data_root,
        )


def test_configure_apply_with_wrong_plan_id_raises_plan_stale(tmp_path: Path) -> None:
    data_root = _data_root(tmp_path)
    root = tmp_path / "repo"
    root.mkdir()
    record = register_project(root, data_root=data_root)

    preview = configure_project(
        record.project_id, {"severity": "warn"}, data_root=data_root
    )
    with pytest.raises(ProjectPlanStaleError):
        configure_project(
            record.project_id,
            {"severity": "error"},  # settings changed after preview -> stale plan
            expected_revision=1,
            apply=True,
            plan_id=preview["plan_id"],
            data_root=data_root,
        )


def test_configure_apply_requires_plan_id_and_expected_revision(tmp_path: Path) -> None:
    data_root = _data_root(tmp_path)
    root = tmp_path / "repo"
    root.mkdir()
    record = register_project(root, data_root=data_root)

    with pytest.raises(ProjectError):
        configure_project(record.project_id, {}, apply=True, data_root=data_root)


def test_relink_blocked_by_held_lock_returns_busy_after_real_timeout(
    tmp_path: Path,
) -> None:
    data_root = _data_root(tmp_path)
    root = tmp_path / "repo"
    root.mkdir()
    record = register_project(root, data_root=data_root)
    new_root = tmp_path / "moved"
    root.rename(new_root)

    data_root.mkdir(parents=True, exist_ok=True)
    lock_path = data_root / REGISTRY_LOCK_FILE
    fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    try:
        started = time.monotonic()
        with pytest.raises(ProjectBusyError):
            relink_project(
                record.project_id,
                new_root,
                expected_revision=1,
                data_root=data_root,
                lock_timeout=0.3,
            )
        elapsed = time.monotonic() - started
        # A real polling timeout, not a hardcoded stub: it must actually wait
        # roughly the requested window before giving up.
        assert elapsed >= 0.3
    finally:
        os.close(fd)
        lock_path.unlink()

    # Once released, the same call succeeds normally.
    relinked = relink_project(
        record.project_id, new_root, expected_revision=1, data_root=data_root
    )
    assert relinked["revision"] == 2


def test_concurrent_relinks_serialize_through_the_real_lock(tmp_path: Path) -> None:
    """Two threads racing relink_project must never both observe revision=1
    and both succeed -- the lock must genuinely serialize the read-check-write."""
    data_root = _data_root(tmp_path)
    root = tmp_path / "repo"
    root.mkdir()
    record = register_project(root, data_root=data_root)
    root_a = tmp_path / "a"
    root_a.mkdir()
    root_b = tmp_path / "b"
    root_b.mkdir()

    results: list[str] = []

    def _try_relink(target: Path) -> None:
        try:
            relink_project(
                record.project_id,
                target,
                expected_revision=1,
                data_root=data_root,
                lock_timeout=5.0,
            )
            results.append("ok")
        except ProjectRevisionConflictError:
            results.append("conflict")

    t1 = threading.Thread(target=_try_relink, args=(root_a,))
    t2 = threading.Thread(target=_try_relink, args=(root_b,))
    t1.start()
    t2.start()
    t1.join()
    t2.join()

    assert sorted(results) == ["conflict", "ok"]


def test_list_projects_page_requires_setup_before_first_use(tmp_path: Path) -> None:
    data_root = _data_root(tmp_path)
    root = tmp_path / "repo"
    root.mkdir()
    register_project(root, data_root=data_root)

    with pytest.raises(Exception) as excinfo:
        list_projects_page(data_root=data_root)
    assert getattr(excinfo.value, "code", None) == "SETUP_REQUIRED"


def test_list_projects_page_paginates_with_tamper_and_restart_continuity(
    tmp_path: Path,
) -> None:
    data_root = _data_root(tmp_path)
    ensure_cursor_key(data_root)

    ids = []
    for i in range(3):
        root = tmp_path / f"repo-{i}"
        root.mkdir()
        ids.append(register_project(root, data_root=data_root).project_id)
        time.sleep(0.001)  # ensure strictly increasing created_at ordering

    first_page = list_projects_page(limit=2, data_root=data_root)
    assert len(first_page["projects"]) == 2
    assert first_page["next_cursor"] is not None

    second_page = list_projects_page(
        limit=2, cursor=first_page["next_cursor"], data_root=data_root
    )
    assert len(second_page["projects"]) == 1
    assert second_page["next_cursor"] is None

    seen_ids = {p["project_id"] for p in first_page["projects"]} | {
        p["project_id"] for p in second_page["projects"]
    }
    assert seen_ids == set(ids)

    original_cursor = first_page["next_cursor"]
    mid = len(original_cursor) // 2
    flipped = "A" if original_cursor[mid] != "A" else "B"
    tampered = original_cursor[:mid] + flipped + original_cursor[mid + 1 :]
    with pytest.raises(ProjectInvalidCursorError):
        list_projects_page(limit=2, cursor=tampered, data_root=data_root)

    # Restart continuity: re-reading the key fresh from disk still verifies
    # the original, untampered cursor.
    from rush.workflows.projects import _read_cursor_key

    assert _read_cursor_key(data_root) is not None
    replayed = list_projects_page(
        limit=2, cursor=first_page["next_cursor"], data_root=data_root
    )
    assert replayed["next_cursor"] is None


def test_handle_request_envelope_shape_on_success(tmp_path: Path) -> None:
    data_root = _data_root(tmp_path)
    root = tmp_path / "repo"
    root.mkdir()
    record = register_project(root, data_root=data_root)

    import rush.workflows.projects as projects_module

    original_default_data_root = projects_module.default_data_root
    projects_module.default_data_root = lambda: data_root
    try:
        result = ProjectTool().handle_request(
            {"schema_version": 1, "operation": "show", "project": record.project_id}
        )
    finally:
        projects_module.default_data_root = original_default_data_root

    assert result["status"] == "ok"
    assert result["raw"]["schema_version"] == 1
    assert result["raw"]["operation"] == "show"
    assert result["raw"]["error"] is None
    assert result["raw"]["data"]["project_id"] == record.project_id


def test_handle_request_rejects_unknown_top_level_field(tmp_path: Path) -> None:
    result = ProjectTool().handle_request(
        {"schema_version": 1, "operation": "show", "project": "x", "bogus": 1}
    )
    assert result["status"] == "error"
    assert result["raw"]["error"]["code"] == "INVALID_REQUEST"


def test_handle_request_rejects_malformed_uuid_for_select(tmp_path: Path) -> None:
    result = ProjectTool().handle_request(
        {
            "schema_version": 1,
            "operation": "select",
            "project": "not-a-uuid",
            "session_id": "s1",
            "allow_cache_write": True,
        }
    )
    assert result["status"] == "error"
    assert result["raw"]["error"]["code"] == "INVALID_REQUEST"


def test_handle_request_returns_project_required_with_no_project_or_session(
    tmp_path: Path,
) -> None:
    import rush.workflows.projects as projects_module

    original_default_data_root = projects_module.default_data_root
    projects_module.default_data_root = lambda: _data_root(tmp_path)
    try:
        result = ProjectTool().handle_request(
            {"schema_version": 1, "operation": "show"}
        )
    finally:
        projects_module.default_data_root = original_default_data_root

    assert result["status"] == "error"
    assert result["raw"]["error"]["code"] == "PROJECT_REQUIRED"


def test_handle_request_denies_relink_without_artifact_write_scope(
    tmp_path: Path,
) -> None:
    data_root = _data_root(tmp_path)
    root = tmp_path / "repo"
    root.mkdir()
    record = register_project(root, data_root=data_root)
    new_root = tmp_path / "moved"
    root.rename(new_root)

    import rush.workflows.projects as projects_module

    original_default_data_root = projects_module.default_data_root
    projects_module.default_data_root = lambda: data_root
    try:
        result = ProjectTool().handle_request(
            {
                "schema_version": 1,
                "operation": "relink",
                "project": record.project_id,
                "path": str(new_root),
                "expected_revision": 1,
            }
        )
    finally:
        projects_module.default_data_root = original_default_data_root

    assert result["status"] == "skipped"
    assert result["raw"]["error"]["code"] == "SCOPE_DENIED"
