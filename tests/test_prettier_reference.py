"""Phase 07.A2 Prettier reference adapter fake-process matrix."""

from __future__ import annotations

import subprocess
from pathlib import Path

from rush.engines import prettier
from rush.engines.prettier import PrettierEngine
from rush.tools import common


def test_prettier_uses_check_argv(monkeypatch, tmp_path: Path) -> None:
    calls: list[list[str]] = []

    def fake_run(
        argv: list[str], **_kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        calls.append(argv)
        return subprocess.CompletedProcess(argv, 0, stdout="", stderr="")

    monkeypatch.setattr(prettier, "resolve_binary", lambda _binary: "C:/bin/prettier")
    monkeypatch.setattr(prettier, "run_subprocess", fake_run)

    raw = PrettierEngine().run(tmp_path, [str(tmp_path / "main.ts")], cwd=tmp_path)

    assert raw["exit_code"] == 0
    assert calls == [
        [
            "C:/bin/prettier",
            "--check",
            "--log-level=warn",
            str(tmp_path),
            str(tmp_path / "main.ts"),
        ]
    ]


def test_prettier_normalizes_clean_and_findings(monkeypatch, tmp_path: Path) -> None:
    engine = PrettierEngine()
    monkeypatch.setattr(PrettierEngine, "version", lambda _self: "3.2.5")

    clean = engine.normalize(
        {"exit_code": 0, "stdout": "", "findings": []}, tmp_path, "format"
    )
    findings_raw = [
        {
            "path": str(tmp_path / "main.ts"),
            "rule": "formatting",
            "severity": "warn",
            "message": "file would be reformatted by prettier",
        }
    ]
    finding = engine.normalize(
        {"exit_code": 1, "stdout": "main.ts", "findings": findings_raw},
        tmp_path,
        "format",
    )
    error = engine.normalize(
        {"exit_code": 2, "stdout": "", "stderr": "Syntax error in file"},
        tmp_path,
        "format",
    )

    assert clean["status"] == "ok"
    assert clean["tool"] == "format"
    assert finding["status"] == "warn"
    assert len(finding["findings"]) == 1
    assert finding["findings"][0]["rule"] == "formatting"
    assert error["status"] == "error"


def test_prettier_missing_and_timeout(monkeypatch, tmp_path: Path) -> None:
    engine = PrettierEngine()
    monkeypatch.setattr(common, "engine_on_path", lambda _binary: False)
    missing = common.run_engine(engine, tmp_path, tool_name="format")

    monkeypatch.setattr(common, "engine_on_path", lambda _binary: True)
    monkeypatch.setattr(
        prettier,
        "run_subprocess",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            subprocess.TimeoutExpired("prettier", 120)
        ),
    )
    timeout = common.run_engine(engine, tmp_path, tool_name="format")

    assert missing["status"] == "skipped"
    assert timeout["status"] == "error"
    assert timeout["metadata"]["terminal_reason"] == "timeout"
