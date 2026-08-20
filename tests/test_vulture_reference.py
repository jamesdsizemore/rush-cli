"""Phase 07.A5 Vulture reference adapter fake-process matrix."""

from __future__ import annotations

import subprocess
from pathlib import Path

from rush.engines import vulture
from rush.engines.vulture import VultureEngine
from rush.tools import common


def test_vulture_runs_bounded_argv(monkeypatch, tmp_path: Path) -> None:
    calls: list[list[str]] = []

    def fake_run(
        argv: list[str], **_kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        calls.append(argv)
        return subprocess.CompletedProcess(argv, 0, stdout="", stderr="")

    monkeypatch.setattr(vulture, "resolve_binary", lambda _binary: "C:/bin/vulture")
    monkeypatch.setattr(vulture, "run_subprocess", fake_run)

    raw = VultureEngine().run(tmp_path, [str(tmp_path / "main.py")], cwd=tmp_path)

    assert raw["exit_code"] == 0
    assert calls == [
        [
            "C:/bin/vulture",
            str(tmp_path / "main.py"),
        ]
    ]


def test_vulture_normalizes_clean_and_findings(monkeypatch, tmp_path: Path) -> None:
    engine = VultureEngine()
    monkeypatch.setattr(VultureEngine, "version", lambda _self: "2.11")

    clean = engine.normalize({"exit_code": 0, "stdout": ""}, tmp_path, "dead")
    finding = engine.normalize(
        {
            "exit_code": 0,
            "stdout": "src/example.py:9: unused function 'unused_helper' (60% confidence)\n",
        },
        tmp_path,
        "dead",
    )

    assert clean["status"] == "ok"
    assert clean["tool"] == "dead"
    assert finding["status"] == "warn"
    assert len(finding["findings"]) == 1
    assert finding["findings"][0]["rule"] == "vulture"
    assert finding["findings"][0]["line"] == 9


def test_vulture_missing_and_timeout(monkeypatch, tmp_path: Path) -> None:
    engine = VultureEngine()
    monkeypatch.setattr(common, "engine_on_path", lambda _binary: False)
    missing = common.run_engine(engine, tmp_path, tool_name="dead")

    monkeypatch.setattr(common, "engine_on_path", lambda _binary: True)
    monkeypatch.setattr(
        vulture,
        "run_subprocess",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            subprocess.TimeoutExpired("vulture", 120)
        ),
    )
    timeout = common.run_engine(engine, tmp_path, tool_name="dead")

    assert missing["status"] == "skipped"
    assert timeout["status"] == "error"
    assert timeout["metadata"]["terminal_reason"] == "timeout"
