"""Reference adapter tests for aislop."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

from rush.engines import aislop
from rush.engines.aislop import AislopEngine
from rush.tools import common


def test_aislop_runs_isolated_argv(monkeypatch, tmp_path: Path) -> None:
    calls: list[list[str]] = []

    def fake_run(
        argv: list[str], **_kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        calls.append(argv)
        return subprocess.CompletedProcess(argv, 0, stdout="[]", stderr="")

    monkeypatch.setattr(aislop, "resolve_binary", lambda _binary: "C:/bin/aislop")
    monkeypatch.setattr(aislop, "run_subprocess", fake_run)

    raw = AislopEngine().run(tmp_path, [], cwd=tmp_path)
    assert raw["exit_code"] == 0
    assert calls == [["C:/bin/aislop", "scan", "--format=json", str(tmp_path)]]


def test_aislop_normalizes_clean(tmp_path: Path) -> None:
    engine = AislopEngine()
    fixture = json.loads(
        (Path(__file__).parent / "fixtures/engine_reports/aislop/clean.json").read_text(
            encoding="utf-8"
        )
    )
    res = engine.normalize(
        {"exit_code": 0, "findings": fixture, "parsed": fixture}, tmp_path, "slop"
    )
    assert res["status"] == "ok"
    assert res["findings"] == []


def test_aislop_normalizes_findings(tmp_path: Path) -> None:
    engine = AislopEngine()
    fixture = json.loads(
        (
            Path(__file__).parent / "fixtures/engine_reports/aislop/findings.json"
        ).read_text(encoding="utf-8")
    )
    res = engine.normalize(
        {"exit_code": 1, "findings": fixture, "parsed": fixture}, tmp_path, "slop"
    )
    assert res["status"] == "fail"
    assert len(res["findings"]) == 1
    assert res["findings"][0]["severity"] == "error"
    assert res["findings"][0]["rule"] == "aislop/hallucinated-import"


def test_aislop_normalizes_malformed(tmp_path: Path) -> None:
    engine = AislopEngine()
    res = engine.normalize(
        {"exit_code": 1, "findings": [], "parsed": None}, tmp_path, "slop"
    )
    assert res["status"] == "error"


def test_aislop_missing_binary(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(common, "engine_on_path", lambda _b: False)
    res = common.run_engine(AislopEngine(), tmp_path)
    assert res["status"] == "skipped"


# -- aislop 0.16.1: directory scan, `diagnostics` report ----------------------

FIXTURE_0161 = (
    Path(__file__).parent / "fixtures/engine_reports/aislop/diagnostics-0.16.1.json"
)
SLOPPY_SOURCE = (
    "import os\n\n\ndef foo(x):\n    # This function returns x\n"
    "    try:\n        return x\n    except:\n        pass\n    return None\n"
)


def _run_and_normalize(
    monkeypatch, target: Path, stdout: str, returncode: int, stderr: str = ""
):
    calls: list[tuple[list[str], object]] = []

    def fake_run(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        calls.append((argv, kwargs.get("cwd")))
        return subprocess.CompletedProcess(argv, returncode, stdout, stderr)

    monkeypatch.setattr(aislop, "resolve_binary", lambda _binary: "/bin/aislop")
    monkeypatch.setattr(aislop, "run_subprocess", fake_run)
    engine = AislopEngine()
    monkeypatch.setattr(engine, "version", lambda **_kw: "0.16.1")
    raw = engine.run(target, [])
    return engine.normalize(raw, target, "slop"), calls


def test_aislop_file_target_scans_parent_with_single_include(
    monkeypatch, tmp_path: Path
) -> None:
    source = tmp_path / "pkg" / "a.py"
    source.parent.mkdir()
    source.write_text(SLOPPY_SOURCE)

    _res, calls = _run_and_normalize(monkeypatch, source, '{"diagnostics": []}', 0)

    assert calls == [
        (
            [
                "/bin/aislop",
                "scan",
                "--format=json",
                "--include",
                "a.py",
                str(source.parent),
            ],
            source.parent,
        )
    ]


def test_aislop_directory_target_runs_in_the_scanned_directory(
    monkeypatch, tmp_path: Path
) -> None:
    (tmp_path / "a.py").write_text(SLOPPY_SOURCE)

    _res, calls = _run_and_normalize(monkeypatch, tmp_path, '{"diagnostics": []}', 0)

    assert calls == [
        (["/bin/aislop", "scan", "--format=json", str(tmp_path)], tmp_path)
    ]


def test_slop_passes_no_file_positionals_to_the_aislop_binary(
    monkeypatch, tmp_path: Path
) -> None:
    """Fake `aislop` executable on PATH: the real dispatch spawns exactly one
    positional (the directory) -- aislop 0.16.1 rejects any more."""
    from rush.tools.common import clear_binary_cache
    from rush.tools.slop import SlopTool

    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    log = tmp_path / "argv.log"
    fake = bin_dir / "aislop"
    fake.write_text(
        "#!/bin/sh\n"
        'if [ "$1" = "--version" ]; then echo 0.16.1; exit 0; fi\n'
        f'for a in "$@"; do echo "$a" >> "{log}"; done\n'
        "echo '{\"diagnostics\": []}'\n"
    )
    fake.chmod(0o755)
    project = tmp_path / "proj"
    (project / "pkg").mkdir(parents=True)
    (project / "pkg" / "a.py").write_text(SLOPPY_SOURCE)
    (project / "b.py").write_text("def ok() -> int:\n    return 1\n")
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ['PATH']}")
    # The runtime venv bin is searched before PATH; CI installs the real
    # aislop there, which would shadow the fake.
    monkeypatch.setattr(common, "_venv_scripts_dir", lambda: None)
    clear_binary_cache()
    try:
        result = SlopTool().run(project)
    finally:
        clear_binary_cache()

    assert result["engine"] == "aislop"
    assert result["status"] == "ok", result["summary"]
    assert log.read_text().splitlines() == ["scan", "--format=json", str(project)]
    metadata = result["metadata"]
    assert metadata is not None
    scope = metadata["engines"][0]["scope"]
    assert scope["reason"] == "engine_discovers_directory_contents"


def test_aislop_parses_recorded_0161_diagnostics(monkeypatch, tmp_path: Path) -> None:
    res, _calls = _run_and_normalize(
        monkeypatch, tmp_path, FIXTURE_0161.read_text(encoding="utf-8"), 1
    )

    source = str(tmp_path / "pkg" / "a.py")
    assert res["status"] == "fail"
    assert res["findings"] == [
        {
            "path": source,
            "line": 1,
            "column": 8,
            "rule": "aislop/lint/ruff/F401",
            "severity": "error",
            "message": "`os` imported but unused",
            "fix": None,
            "remediation": None,
        },
        {
            "path": source,
            "line": 6,
            "column": 0,
            "rule": "aislop/ai-slop/ai-slop/trivial-comment",
            "severity": "warn",
            "message": "Trivial comment that restates the code",
            "fix": None,
            "remediation": "Remove comments that don't add information beyond "
            "what the code already expresses",
        },
        {
            "path": source,
            "line": 9,
            "column": 0,
            "rule": "aislop/ai-slop/ai-slop/swallowed-exception",
            "severity": "error",
            "message": "Bare except with pass swallows errors silently",
            "fix": None,
            "remediation": "Handle errors explicitly: log with context, "
            "rethrow, or return an error value",
        },
    ]


def test_aislop_exit_one_with_warning_diagnostics_is_warn(
    monkeypatch, tmp_path: Path
) -> None:
    report = json.loads(FIXTURE_0161.read_text(encoding="utf-8"))
    report["diagnostics"] = [
        d for d in report["diagnostics"] if d["severity"] == "warning"
    ]

    res, _calls = _run_and_normalize(monkeypatch, tmp_path, json.dumps(report), 1)

    assert res["status"] == "warn"
    assert [f["severity"] for f in res["findings"]] == ["warn"]


@pytest.mark.parametrize("returncode", [0, 1])
def test_aislop_zero_diagnostics_is_ok(
    monkeypatch, tmp_path: Path, returncode: int
) -> None:
    report = json.loads(FIXTURE_0161.read_text(encoding="utf-8"))
    report["diagnostics"] = []

    res, _calls = _run_and_normalize(
        monkeypatch, tmp_path, json.dumps(report), returncode
    )

    assert res["status"] == "ok"
    assert res["findings"] == []


def test_aislop_unparseable_output_is_error_with_stderr(
    monkeypatch, tmp_path: Path
) -> None:
    stderr = "error: too many arguments for 'scan'. Expected 1 argument but got 2."

    res, _calls = _run_and_normalize(monkeypatch, tmp_path, "", 1, stderr)

    assert res["status"] == "error"
    assert "exit 1" in res["summary"]
    assert stderr in res["summary"]


@pytest.mark.needs_aislop
def test_slop_real_aislop_scans_python_project(tmp_path: Path) -> None:
    """Real-engine acceptance against the installed aislop binary."""
    from rush.tools.common import clear_binary_cache
    from rush.tools.slop import SlopTool

    clear_binary_cache()
    (tmp_path / "pkg").mkdir()
    sloppy = tmp_path / "pkg" / "a.py"
    sloppy.write_text(SLOPPY_SOURCE)
    clean = tmp_path / "b.py"
    clean.write_text("def ok() -> int:\n    return 1\n")

    project = SlopTool().run(tmp_path)
    single_sloppy = SlopTool().run(sloppy)
    single_clean = SlopTool().run(clean)

    assert project["engine"] == "aislop"
    assert project["status"] == "fail", project["summary"]
    rules = {f["rule"] for f in project["findings"]}
    assert "aislop/ai-slop/ai-slop/swallowed-exception" in rules
    assert {f["path"] for f in project["findings"]} == {str(sloppy)}
    assert single_sloppy["status"] == "fail", single_sloppy["summary"]
    assert {f["path"] for f in single_sloppy["findings"]} == {str(sloppy)}
    assert single_clean["status"] == "ok", single_clean["summary"]
