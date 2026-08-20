"""Phase 07.A6 jscpd reference adapter fake-process matrix."""

from __future__ import annotations

import subprocess
from pathlib import Path

from rush.engines import jscpd
from rush.engines.jscpd import JscpdEngine
from rush.tools import common


def test_jscpd_runs_bounded_argv(monkeypatch, tmp_path: Path) -> None:
    calls: list[list[str]] = []

    def fake_run(
        argv: list[str], **_kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        calls.append(argv)
        return subprocess.CompletedProcess(argv, 0, stdout="", stderr="")

    monkeypatch.setattr(jscpd, "resolve_binary", lambda _binary: "C:/bin/jscpd")
    monkeypatch.setattr(jscpd, "run_subprocess", fake_run)

    raw = JscpdEngine().run(tmp_path, [str(tmp_path / "main.ts")], cwd=tmp_path)

    assert raw["exit_code"] == 0
    assert calls == [
        [
            "C:/bin/jscpd",
            str(tmp_path / "main.ts"),
        ]
    ]


def test_jscpd_normalizes_clean_and_findings(monkeypatch, tmp_path: Path) -> None:
    engine = JscpdEngine()
    monkeypatch.setattr(JscpdEngine, "version", lambda _self: "3.5.10")

    clean = engine.normalize({"exit_code": 0, "stdout": ""}, tmp_path, "complexity")
    finding = engine.normalize(
        {
            "exit_code": 1,
            "stdout": "src/example.ts:10-20 - duplicate block\n",
        },
        tmp_path,
        "complexity",
    )

    assert clean["status"] == "ok"
    assert clean["tool"] == "complexity"
    assert finding["status"] == "warn"
    assert len(finding["findings"]) == 1
    assert finding["findings"][0]["rule"] == "jscpd"
    assert finding["findings"][0]["line"] == 10


def test_jscpd_missing_and_timeout(monkeypatch, tmp_path: Path) -> None:
    engine = JscpdEngine()
    monkeypatch.setattr(common, "engine_on_path", lambda _binary: False)
    missing = common.run_engine(engine, tmp_path, tool_name="complexity")

    monkeypatch.setattr(common, "engine_on_path", lambda _binary: True)
    monkeypatch.setattr(
        jscpd,
        "run_subprocess",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            subprocess.TimeoutExpired("jscpd", 120)
        ),
    )
    timeout = common.run_engine(engine, tmp_path, tool_name="complexity")

    assert missing["status"] == "skipped"
    assert timeout["status"] == "error"
    assert timeout["metadata"]["terminal_reason"] == "timeout"
