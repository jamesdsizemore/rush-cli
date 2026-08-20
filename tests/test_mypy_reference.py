"""Phase 07.A4 Mypy reference adapter fake-process matrix."""

from __future__ import annotations

import subprocess
from pathlib import Path

from rush.engines import mypy
from rush.engines.mypy import MypyEngine
from rush.tools import common


def test_mypy_runs_bounded_argv(monkeypatch, tmp_path: Path) -> None:
    calls: list[list[str]] = []

    def fake_run(
        argv: list[str], **_kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        calls.append(argv)
        return subprocess.CompletedProcess(
            argv, 0, stdout="Success: no issues found in 1 source file\n", stderr=""
        )

    monkeypatch.setattr(mypy, "resolve_binary", lambda _binary: "C:/bin/mypy")
    monkeypatch.setattr(mypy, "run_subprocess", fake_run)

    raw = MypyEngine().run(tmp_path, [str(tmp_path / "main.py")], cwd=tmp_path)

    assert raw["exit_code"] == 0
    assert calls == [
        [
            "C:/bin/mypy",
            "--hide-error-context",
            str(tmp_path / "main.py"),
        ]
    ]


def test_mypy_normalizes_clean_and_findings(monkeypatch, tmp_path: Path) -> None:
    engine = MypyEngine()
    monkeypatch.setattr(MypyEngine, "version", lambda _self: "1.11.0")

    clean = engine.normalize(
        {"exit_code": 0, "stdout": "Success: no issues found in 1 source file\n"},
        tmp_path,
        "typecheck",
    )
    findings_stdout = (
        "src/example.py:4: error: Incompatible types in assignment  [assignment]\n"
    )
    finding = engine.normalize(
        {"exit_code": 1, "stdout": findings_stdout},
        tmp_path,
        "typecheck",
    )
    error = engine.normalize(
        {"exit_code": 2, "stdout": "", "stderr": "mypy: internal crash"},
        tmp_path,
        "typecheck",
    )

    assert clean["status"] == "ok"
    assert clean["tool"] == "typecheck"
    assert finding["status"] == "fail"
    assert len(finding["findings"]) == 1
    assert finding["findings"][0]["rule"] == "assignment"
    assert finding["findings"][0]["line"] == 4
    assert error["status"] == "error"


def test_mypy_missing_and_timeout(monkeypatch, tmp_path: Path) -> None:
    engine = MypyEngine()
    monkeypatch.setattr(common, "engine_on_path", lambda _binary: False)
    missing = common.run_engine(engine, tmp_path, tool_name="typecheck")

    monkeypatch.setattr(common, "engine_on_path", lambda _binary: True)
    monkeypatch.setattr(
        mypy,
        "run_subprocess",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            subprocess.TimeoutExpired("mypy", 120)
        ),
    )
    timeout = common.run_engine(engine, tmp_path, tool_name="typecheck")

    assert missing["status"] == "skipped"
    assert timeout["status"] == "error"
    assert timeout["metadata"]["terminal_reason"] == "timeout"
