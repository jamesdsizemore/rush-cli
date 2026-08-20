"""Phase 07.A7 sloppylint reference adapter fake-process matrix."""

from __future__ import annotations

import subprocess
from pathlib import Path

from rush.engines import sloppylint
from rush.engines.sloppylint import SloppylintEngine
from rush.tools import common


def test_sloppylint_runs_json_argv(monkeypatch, tmp_path: Path) -> None:
    calls: list[list[str]] = []

    def fake_run(
        argv: list[str], **_kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        calls.append(argv)
        return subprocess.CompletedProcess(argv, 0, stdout='{"issues": []}', stderr="")

    monkeypatch.setattr(
        sloppylint, "resolve_binary", lambda _binary: "C:/bin/sloppylint"
    )
    monkeypatch.setattr(sloppylint, "run_subprocess", fake_run)

    raw = SloppylintEngine().run(tmp_path, [str(tmp_path / "main.py")], cwd=tmp_path)

    assert raw["exit_code"] == 0
    assert calls == [
        [
            "C:/bin/sloppylint",
            "--format",
            "json",
            str(tmp_path / "main.py"),
        ]
    ]


def test_sloppylint_normalizes_clean_and_findings(monkeypatch, tmp_path: Path) -> None:
    engine = SloppylintEngine()
    monkeypatch.setattr(SloppylintEngine, "version", lambda _self: "0.2.0")

    clean = engine.normalize(
        {"exit_code": 0, "stdout": '{"issues": []}'}, tmp_path, "slop"
    )
    stdout_json = '{"issues": [{"file": "src/example.py", "line": 12, "pattern_id": "verbose-comment", "severity": "warning", "message": "Comment repeats the code"}]}'
    finding = engine.normalize(
        {"exit_code": 0, "stdout": stdout_json},
        tmp_path,
        "slop",
    )

    assert clean["status"] == "ok"
    assert clean["tool"] == "slop"
    assert finding["status"] == "warn"
    assert len(finding["findings"]) == 1
    assert finding["findings"][0]["rule"] == "verbose-comment"
    assert finding["findings"][0]["line"] == 12


def test_sloppylint_missing_and_timeout(monkeypatch, tmp_path: Path) -> None:
    engine = SloppylintEngine()
    monkeypatch.setattr(common, "engine_on_path", lambda _binary: False)
    missing = common.run_engine(engine, tmp_path, tool_name="slop")

    monkeypatch.setattr(common, "engine_on_path", lambda _binary: True)
    monkeypatch.setattr(
        sloppylint,
        "run_subprocess",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            subprocess.TimeoutExpired("sloppylint", 120)
        ),
    )
    timeout = common.run_engine(engine, tmp_path, tool_name="slop")

    assert missing["status"] == "skipped"
    assert timeout["status"] == "error"
    assert timeout["metadata"]["terminal_reason"] == "timeout"
