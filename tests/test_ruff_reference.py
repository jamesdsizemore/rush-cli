"""Phase 07.A1 Ruff reference adapter fake-process matrix."""

from __future__ import annotations

import subprocess
from pathlib import Path

from rush.engines import ruff
from rush.engines.ruff import RuffEngine
from rush.tools import common


def test_ruff_uses_json_argv_without_cache(monkeypatch, tmp_path: Path) -> None:
    calls: list[list[str]] = []

    def fake_run(
        argv: list[str], **_kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        calls.append(argv)
        return subprocess.CompletedProcess(argv, 0, stdout="[]", stderr="")

    monkeypatch.setattr(ruff, "resolve_binary", lambda _binary: "C:/bin/ruff")
    monkeypatch.setattr(ruff, "run_subprocess", fake_run)

    raw = RuffEngine().run(tmp_path, [str(tmp_path / "main.py")], cwd=tmp_path)

    assert raw["exit_code"] == 0
    assert raw["stdout"] == "[]"
    assert calls == [
        [
            "C:/bin/ruff",
            "check",
            "--output-format=json",
            "--no-cache",
            str(tmp_path),
            str(tmp_path / "main.py"),
        ]
    ]


def test_ruff_normalizes_clean_and_findings(monkeypatch, tmp_path: Path) -> None:
    engine = RuffEngine()
    monkeypatch.setattr(RuffEngine, "version", lambda _self: "0.6.9")

    clean = engine.normalize(
        {"exit_code": 0, "stdout": "[]", "findings": []}, tmp_path, "lint"
    )
    findings_raw = [
        {
            "code": "F401",
            "message": "`os` imported but unused",
            "location": {"row": 1, "column": 1},
            "filename": str(tmp_path / "main.py"),
            "fix": None,
        }
    ]
    finding = engine.normalize(
        {"exit_code": 1, "stdout": "...", "findings": findings_raw}, tmp_path, "lint"
    )
    error = engine.normalize(
        {"exit_code": 2, "stdout": "", "stderr": "Invalid configuration"},
        tmp_path,
        "lint",
    )

    assert clean["status"] == "ok"
    assert clean["tool"] == "lint"
    assert finding["status"] == "fail"
    assert len(finding["findings"]) == 1
    assert finding["findings"][0]["rule"] == "F401"
    assert finding["findings"][0]["severity"] == "error"
    assert error["status"] == "error"
    assert "config error" in error["summary"]


def test_ruff_missing_and_timeout(monkeypatch, tmp_path: Path) -> None:
    engine = RuffEngine()
    monkeypatch.setattr(common, "engine_on_path", lambda _binary: False)
    missing = common.run_engine(engine, tmp_path, tool_name="lint")

    monkeypatch.setattr(common, "engine_on_path", lambda _binary: True)
    monkeypatch.setattr(
        ruff,
        "run_subprocess",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            subprocess.TimeoutExpired("ruff", 120)
        ),
    )
    timeout = common.run_engine(engine, tmp_path, tool_name="lint")

    assert missing["status"] == "skipped"
    assert timeout["status"] == "error"
    assert timeout["metadata"]["terminal_reason"] == "timeout"
