"""Phase 19 Diff-Cover reference adapter fake-process matrix."""

from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

from rush.engines import diff_cover
from rush.engines.diff_cover import DiffCoverEngine


def test_diff_cover_runs_isolated_argv(monkeypatch, tmp_path: Path) -> None:
    calls: list[list[str]] = []

    def fake_run(
        argv: list[str], **_kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        calls.append(argv)
        return subprocess.CompletedProcess(argv, 0, stdout="{}", stderr="")

    monkeypatch.setattr(
        diff_cover, "resolve_binary", lambda _binary: "C:/bin/diff-cover"
    )
    monkeypatch.setattr(diff_cover, "run_subprocess", fake_run)

    raw = DiffCoverEngine().run(tmp_path, [], cwd=tmp_path)

    assert raw["exit_code"] == 0
    assert calls == [
        [
            "C:/bin/diff-cover",
            "coverage.xml",
            "--compare-branch=main",
            "--json-report=diff-cover.json",
        ]
    ]


def test_diff_cover_normalizes_clean_and_findings(monkeypatch, tmp_path: Path) -> None:
    engine = DiffCoverEngine()
    monkeypatch.setattr(DiffCoverEngine, "version", lambda _self: "9.1.1")

    clean = engine.normalize({"exit_code": 0, "findings": []}, tmp_path, "metrics")
    assert clean["status"] == "ok"
    assert clean["findings"] == []

    failing = engine.normalize(
        {
            "exit_code": 0,
            "findings": [
                {
                    "file": "src/rush/cli.py",
                    "percent": 65.5,
                    "missing": [45, 46, 50],
                }
            ],
        },
        tmp_path,
        "metrics",
    )
    assert failing["status"] == "warn"
    assert len(failing["findings"]) == 1
    assert "diff-cover/under-threshold" in failing["findings"][0]["rule"]


# --- T049: M19 §12-named regression tests -----------------------------------


def _rush_diff_cover_tempdirs() -> set[str]:
    base = Path(tempfile.gettempdir())
    return {
        entry.name
        for entry in base.iterdir()
        if entry.is_dir() and entry.name.startswith("rush-diff-cover-")
    }


def test_stale_live_report_with_no_fresh_output_fails_honestly_rather_than_reusing_old_bytes(
    monkeypatch, tmp_path: Path
) -> None:
    """M19 bullet 2: a stale `diff-cover.json` already on disk before this
    invocation must never be read as this run's output -- when the real
    process produces no fresh report, the run fails honestly instead of
    silently reusing old bytes."""
    (tmp_path / "diff-cover.json").write_text(
        '{"src_stats": {"stale.py": {"percent_covered": 10}}}', encoding="utf-8"
    )

    def fake_run(
        argv: list[str], **_kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(argv, 0, stdout="", stderr="")

    monkeypatch.setattr(diff_cover, "resolve_binary", lambda _b: "/bin/diff-cover")
    monkeypatch.setattr(diff_cover, "run_subprocess", fake_run)

    raw = DiffCoverEngine().run(tmp_path, [], cwd=tmp_path)

    assert raw["parsed"] is None
    assert raw["findings"] == []
    assert raw["exit_code"] == 1
    assert "no fresh report produced" in raw["summary"]


def test_conflicting_positional_or_option_args_are_rejected_and_the_binary_is_not_launched(
    monkeypatch, tmp_path: Path
) -> None:
    """M19 bullet 2: a caller arg that adds another coverage positional
    input, or overrides `--compare-branch`/`--json-report`, is rejected
    before this invocation's own pinned identity is ever built -- the real
    binary (and the git subprocess calls) must never launch."""
    calls: list[list[str]] = []

    def fake_run(
        argv: list[str], **_kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        calls.append(argv)
        return subprocess.CompletedProcess(argv, 0, stdout="{}", stderr="")

    monkeypatch.setattr(diff_cover, "resolve_binary", lambda _b: "/bin/diff-cover")
    monkeypatch.setattr(diff_cover, "run_subprocess", fake_run)

    override = DiffCoverEngine().run(
        tmp_path, ["--compare-branch=other"], cwd=tmp_path
    )
    assert override["exit_code"] == 1
    assert "rejected caller override" in override["summary"]

    extra_positional = DiffCoverEngine().run(
        tmp_path, ["another-report.xml"], cwd=tmp_path
    )
    assert extra_positional["exit_code"] == 1
    assert "rejected extra positional" in extra_positional["summary"]

    assert calls == [], "the binary must never be launched when args are rejected"


def test_temp_directory_is_cleaned_up_on_success_error_timeout_and_cancellation(
    monkeypatch, tmp_path: Path
) -> None:
    """M19 bullet 1: the `TemporaryDirectory` this invocation scopes around
    the coverage copy/report path is cleaned up whether the call succeeds,
    the process errors, times out, or is cancelled -- never left behind."""
    from rush.runtime.subprocesses import SubprocessCancelled

    monkeypatch.setattr(diff_cover, "resolve_binary", lambda _b: "/bin/diff-cover")
    before = _rush_diff_cover_tempdirs()

    monkeypatch.setattr(
        diff_cover,
        "run_subprocess",
        lambda argv, **_k: subprocess.CompletedProcess(
            argv, 0, stdout="{}", stderr=""
        ),
    )
    DiffCoverEngine().run(tmp_path, [], cwd=tmp_path)
    assert _rush_diff_cover_tempdirs() == before

    def _raiser(exc: Exception):
        def _fake(
            argv: list[str], **_k: object
        ) -> subprocess.CompletedProcess[str]:
            raise exc

        return _fake

    for exc in (
        OSError("boom"),
        subprocess.TimeoutExpired(cmd=["diff-cover"], timeout=120),
        SubprocessCancelled(["diff-cover"], 1234),
    ):
        monkeypatch.setattr(diff_cover, "run_subprocess", _raiser(exc))
        try:
            DiffCoverEngine().run(tmp_path, [], cwd=tmp_path)
        except type(exc):
            pass
        assert _rush_diff_cover_tempdirs() == before


def test_changed_coverage_bytes_alone_change_the_folded_provenance_identity(
    monkeypatch, tmp_path: Path
) -> None:
    """M19 bullet 3: the diff-cover engine's own combined provenance digest
    (folded into the candidate's repository-state evidence by
    `_run_candidates`) must change when only the coverage input bytes
    change -- never stay pinned to the diff identity alone."""
    monkeypatch.setattr(diff_cover, "resolve_binary", lambda _b: "/bin/diff-cover")
    monkeypatch.setattr(
        diff_cover,
        "run_subprocess",
        lambda argv, **_k: subprocess.CompletedProcess(
            argv, 0, stdout="{}", stderr=""
        ),
    )

    (tmp_path / "coverage.xml").write_text(
        '<coverage version="a"/>', encoding="utf-8"
    )
    first = DiffCoverEngine().run(tmp_path, [], cwd=tmp_path)

    (tmp_path / "coverage.xml").write_text(
        '<coverage version="b"/>', encoding="utf-8"
    )
    second = DiffCoverEngine().run(tmp_path, [], cwd=tmp_path)

    assert first["provenance"]["digest"] is not None
    assert second["provenance"]["digest"] is not None
    assert first["provenance"]["digest"] != second["provenance"]["digest"]
    assert (
        first["provenance"]["coverage_digest"]
        != second["provenance"]["coverage_digest"]
    )
