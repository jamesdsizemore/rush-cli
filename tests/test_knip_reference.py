"""Phase 07.A5 Knip reference adapter fake-process matrix."""

from __future__ import annotations

import subprocess
from pathlib import Path

from rush.engines import knip
from rush.engines.knip import KnipEngine
from rush.tools import common


def test_knip_runs_no_exit_code_argv(monkeypatch, tmp_path: Path) -> None:
    calls: list[list[str]] = []

    def fake_run(
        argv: list[str], **_kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        calls.append(argv)
        return subprocess.CompletedProcess(argv, 0, stdout="", stderr="")

    monkeypatch.setattr(knip, "resolve_binary", lambda _binary: "C:/bin/knip")
    monkeypatch.setattr(knip, "run_subprocess", fake_run)

    raw = KnipEngine().run(tmp_path, [str(tmp_path / "main.ts")], cwd=tmp_path)

    assert raw["exit_code"] == 0
    assert calls == [
        [
            "C:/bin/knip",
            "--no-exit-code",
            str(tmp_path / "main.ts"),
        ]
    ]


def test_knip_normalizes_clean_and_findings(monkeypatch, tmp_path: Path) -> None:
    engine = KnipEngine()
    monkeypatch.setattr(KnipEngine, "version", lambda _self: "5.27.0")

    clean = engine.normalize({"exit_code": 0, "stdout": ""}, tmp_path, "dead")
    finding = engine.normalize(
        {
            "exit_code": 0,
            "stdout": "Unused export   src/example.ts:3\n",
        },
        tmp_path,
        "dead",
    )

    assert clean["status"] == "ok"
    assert clean["tool"] == "dead"
    assert finding["status"] == "warn"
    assert len(finding["findings"]) == 1
    assert finding["findings"][0]["rule"] == "knip"
    assert finding["findings"][0]["line"] == 3


def test_knip_missing_and_timeout(monkeypatch, tmp_path: Path) -> None:
    engine = KnipEngine()
    monkeypatch.setattr(common, "engine_on_path", lambda _binary: False)
    missing = common.run_engine(engine, tmp_path, tool_name="dead")

    monkeypatch.setattr(common, "engine_on_path", lambda _binary: True)
    monkeypatch.setattr(
        knip,
        "run_subprocess",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            subprocess.TimeoutExpired("knip", 120)
        ),
    )
    timeout = common.run_engine(engine, tmp_path, tool_name="dead")

    assert missing["status"] == "skipped"
    assert timeout["status"] == "error"
    assert timeout["metadata"]["terminal_reason"] == "timeout"
