"""Phase 70 T28-E review round 1 (Kiara) regressions, part A: export and Git.

Each test is a repro from `.orchestrator/kiara_repro.py` (r1, r2, r3, r4, r8,
r9, r10) plus the streaming-export requirement, run against the real
`rush.workflows.projects` helpers, the real TUI handlers and real temporary
Git repositories under `tmp_path`.
"""

from __future__ import annotations

import base64
import os
from pathlib import Path
from typing import Any

import pytest
from test_phase70_tui_usability_ef import (
    _captured_item,
    _commit,
    _cursor,
    _git,
    _keys,
    _register,
    _render,
    _section,
    _settle,
    _state,
    _write_attempt,
)

from rush import tui
from rush.io.physical_paths import ContainmentError
from rush.permissions import ExecutionPermissions
from rush.workflows import projects as wp

_GRANT = ExecutionPermissions(artifact_write=True)


def _data_root(tmp_path: Path) -> Path:
    data_root = tmp_path / "data"
    data_root.mkdir()
    return data_root


def _artifact_state(
    tmp_path: Path, data: bytes, rel_path: str = "r.txt"
) -> tuple[str, Path, Path, tui.TuiState, tui.ScanActions, dict[str, Any]]:
    data_root = _data_root(tmp_path)
    project_id, root = _register(tmp_path, "p", data_root)
    item = _captured_item(
        root,
        run_id="run-a",
        attempt_id="run-a-attempt-1",
        candidate_id="t",
        rel_path=rel_path,
        data=data,
    )
    _write_attempt(
        root,
        run_id="run-a",
        attempt_id="run-a-attempt-1",
        project_id=project_id,
        scheduled=[item],
    )
    actions = tui.default_scan_actions(ExecutionPermissions())
    state = _state(root, project_id, data_root)
    _section(state, actions, "7")
    _settle(state, actions, "artifacts")
    return project_id, root, data_root, state, actions, item


def _export(project_id: str, data_root: Path, destination: Path) -> dict[str, Any]:
    return wp.export_project_artifact(
        project_id,
        run_id="run-a",
        attempt_id="run-a-attempt-1",
        tool_id="t",
        path="r.txt",
        destination=destination,
        permissions=_GRANT,
        data_root=data_root,
    )


# --------------------------------------------------------------------------
# r4: a destination that appears at publish time is never overwritten
# --------------------------------------------------------------------------


def _appear_at_publish(
    monkeypatch: pytest.MonkeyPatch, destination: Path, data: bytes
) -> None:
    """Create `destination` right before whichever publish primitive the
    export uses (`os.link` or `os.replace`), i.e. after every absence check."""
    for name in ("link", "replace"):
        real = getattr(os, name)

        def publish(*args: Any, _real: Any = real, **kwargs: Any) -> Any:
            if not destination.exists():
                destination.write_bytes(data)
            return _real(*args, **kwargs)

        monkeypatch.setattr(os, name, publish)


def test_r4_destination_created_after_absence_check_is_never_overwritten(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project_id, _root, data_root, _st, _a, _item = _artifact_state(
        tmp_path, b"captured\n"
    )
    destination = tmp_path / "dest.txt"
    _appear_at_publish(monkeypatch, destination, b"OTHER WRITER DATA\n")

    with pytest.raises(FileExistsError):
        _export(project_id, data_root, destination)

    assert destination.read_bytes() == b"OTHER WRITER DATA\n"
    assert not list(tmp_path.glob("dest.txt*.partial"))


def test_r4_identical_destination_appearing_at_publish_is_noop(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project_id, _root, data_root, _st, _a, _item = _artifact_state(
        tmp_path, b"captured\n"
    )
    destination = tmp_path / "dest.txt"
    _appear_at_publish(monkeypatch, destination, b"captured\n")

    result = _export(project_id, data_root, destination)

    assert result["noop"] is True
    assert destination.read_bytes() == b"captured\n"
    assert not list(tmp_path.glob("dest.txt*.partial"))


def test_export_interrupted_at_publish_removes_only_its_own_partial(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project_id, _root, data_root, _st, _a, _item = _artifact_state(
        tmp_path, b"captured\n"
    )
    destination = tmp_path / "interrupted.txt"
    other_partial = tmp_path / "unrelated.txt.partial"
    other_partial.write_bytes(b"another export in flight")

    def boom(*_args: Any, **_kwargs: Any) -> None:
        raise OSError("simulated interruption at publish")

    monkeypatch.setattr(os, "link", boom)
    monkeypatch.setattr(os, "replace", boom)
    with pytest.raises(OSError):
        _export(project_id, data_root, destination)

    assert not destination.exists()
    assert not list(tmp_path.glob("interrupted.txt*.partial"))
    assert other_partial.read_bytes() == b"another export in flight"


# --------------------------------------------------------------------------
# streaming: the partial grows page by page
# --------------------------------------------------------------------------


def test_export_streams_each_page_into_the_partial(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    page = wp._MAX_ARTIFACT_PAGE_BYTES
    data = bytes(range(256)) * ((page * 5 // 2) // 256 + 1)
    project_id, _root, data_root, _st, _a, _item = _artifact_state(tmp_path, data)
    destination = tmp_path / "streamed.bin"
    real_read = wp.read_project_artifact_page
    observed: list[int] = []

    def read_page(*args: Any, **kwargs: Any) -> dict[str, Any]:
        partials = list(tmp_path.glob("streamed.bin*.partial"))
        observed.append(partials[0].stat().st_size if partials else -1)
        return real_read(*args, **kwargs)

    monkeypatch.setattr(wp, "read_project_artifact_page", read_page)

    result = _export(project_id, data_root, destination)

    assert destination.read_bytes() == data
    assert result["size"] == len(data)
    pages = -(-len(data) // page)
    assert pages == 3
    # Before page n is read, exactly the n previous pages are on disk.
    assert observed == [0, page, 2 * page], observed


# --------------------------------------------------------------------------
# r3: a symlinked .rush/exports never writes outside the project root
# --------------------------------------------------------------------------


def test_r3_symlinked_exports_dir_refused_before_review(tmp_path: Path) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    _pid, root, _dr, state, actions, _item = _artifact_state(tmp_path, b"hello\n")
    (root / ".rush" / "exports").symlink_to(outside)

    tui._artifact_export_review(state, actions)

    assert state.overlay != "grant_review"
    assert state.pending_grant is None
    assert "outside" in state.message and "root" in state.message, state.message
    assert list(outside.iterdir()) == []


def test_r3_symlink_swapped_in_after_review_refuses_the_export(
    tmp_path: Path,
) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    _pid, root, _dr, state, actions, _item = _artifact_state(tmp_path, b"hello\n")
    tui._artifact_export_review(state, actions)
    grant = state.pending_grant
    assert grant is not None
    (root / ".rush" / "exports").symlink_to(outside)

    tui._export_artifact(state, grant)

    assert state.message.startswith("export failed"), state.message
    assert list(outside.iterdir()) == []


def test_r3_backend_refuses_destination_escaping_the_root(tmp_path: Path) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    project_id, root, data_root, _st, _a, _item = _artifact_state(tmp_path, b"hello\n")
    (root / ".rush" / "exports").symlink_to(outside)

    with pytest.raises(ContainmentError):
        _export(project_id, data_root, root / ".rush" / "exports" / "r.txt")

    assert list(outside.iterdir()) == []


# --------------------------------------------------------------------------
# r2 / r2b / r8 / r9: Git dirty diff kinds, Latin-1, unborn HEAD
# --------------------------------------------------------------------------


def _git_project(tmp_path: Path) -> tuple[str, Path, Path]:
    data_root = _data_root(tmp_path)
    project_id, root = _register(tmp_path, "g", data_root, init_git=True)
    _commit(root, "a.txt", "one\n", "first")
    return project_id, root, data_root


def test_r2_staged_untracked_and_spaced_paths_each_return_their_diff(
    tmp_path: Path,
) -> None:
    project_id, root, data_root = _git_project(tmp_path)
    (root / "b c.txt").write_text("x\n")
    _git(root, "add", "b c.txt")
    _git(root, "commit", "-q", "-m", "sp")
    (root / "a.txt").write_text("staged change\n")
    _git(root, "add", "a.txt")
    (root / "new.txt").write_text("untracked content\n")
    (root / "b c.txt").write_text("y changed\n")

    listed = {e["path"]: e["status"] for e in wp._git_dirty_files(root)}
    assert {"a.txt", "new.txt", "b c.txt"} <= set(listed), listed

    expected = {
        "a.txt": "+staged change",
        "new.txt": "+untracked content",
        "b c.txt": "+y changed",
    }
    for path, added in expected.items():
        diff = wp.project_git_dirty_diff(project_id, path, data_root=data_root)
        assert diff.get("error") is None, (path, diff)
        assert added in diff["lines"], (path, diff)


def test_r2b_staged_and_unstaged_changes_to_one_path_are_both_shown(
    tmp_path: Path,
) -> None:
    project_id, root, data_root = _git_project(tmp_path)
    (root / "a.txt").write_text("staged\n")
    _git(root, "add", "a.txt")
    (root / "a.txt").write_text("staged\nunstaged\n")

    diff = wp.project_git_dirty_diff(project_id, "a.txt", data_root=data_root)

    assert "+staged" in diff["lines"], diff
    assert "+unstaged" in diff["lines"], diff


def test_r8_latin1_diff_returns_lines_not_an_exception(tmp_path: Path) -> None:
    project_id, root, data_root = _git_project(tmp_path)
    (root / "a.txt").write_bytes(b"caf\xe9 latin1\n")

    diff = wp.project_git_dirty_diff(project_id, "a.txt", data_root=data_root)

    assert diff.get("error") is None, diff
    assert "+caf� latin1" in diff["lines"], diff


def test_r9_repository_without_commits_is_empty_not_failed(tmp_path: Path) -> None:
    data_root = _data_root(tmp_path)
    project_id, root = _register(tmp_path, "e", data_root, init_git=True)
    (root / "staged.txt").write_text("first file\n")
    _git(root, "add", "staged.txt")

    summary = wp._git_summary(root)
    assert summary["state"] == "empty", summary
    assert summary["has_git"] is True
    assert summary["head"] is None
    diff = wp.project_git_dirty_diff(project_id, "staged.txt", data_root=data_root)
    assert "+first file" in diff["lines"], diff

    actions = tui.default_scan_actions(ExecutionPermissions())
    state = _state(root, project_id, data_root)
    _section(state, actions, "6")
    _settle(state, actions, "git")
    text = _render(state)
    assert "Git read failed" not in text
    assert "No Git repository" not in text
    assert "no commits yet" in text


# --------------------------------------------------------------------------
# r10: an offset past the end is an invalid cursor
# --------------------------------------------------------------------------


def test_r10_offset_past_end_is_invalid_cursor(tmp_path: Path) -> None:
    project_id, _root, data_root, _st, _a, item = _artifact_state(tmp_path, b"abc")
    sha = item["artifact_snapshots"]["r.txt"]["sha256"]
    identity = {
        "project_id": project_id,
        "run_id": "run-a",
        "attempt_id": "run-a-attempt-1",
        "tool_id": "t",
        "path": "r.txt",
        "sha256": sha,
    }

    past = wp.read_project_artifact_page(
        project_id, _cursor(**identity, offset=999), data_root=data_root
    )
    assert past["error"] == "invalid_cursor", past

    at_end = wp.read_project_artifact_page(
        project_id, _cursor(**identity, offset=3), data_root=data_root
    )
    assert at_end.get("error") is None, at_end
    assert base64.b64decode(at_end["content_base64"]) == b""
    assert at_end["next_cursor"] is None


# --------------------------------------------------------------------------
# r1: a 0-byte captured artifact is empty content, not a read failure
# --------------------------------------------------------------------------


def test_r1_zero_byte_artifact_inspects_as_empty_content(tmp_path: Path) -> None:
    _pid, _root, _dr, state, actions, _item = _artifact_state(
        tmp_path, b"", rel_path="empty.log"
    )

    _keys(state, actions, "i")
    text = _render(state)

    assert "read failed" not in state.message, state.message
    assert "read failed" not in text
    assert "empty captured content" in text
