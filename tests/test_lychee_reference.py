"""Phase 07.C Lychee reference adapter fake-process matrix."""

from __future__ import annotations

import subprocess
from pathlib import Path

from rush.engines import lychee
from rush.engines.lychee import LycheeEngine
from rush.tools import common


def test_lychee_runs_offline_argv_by_default(monkeypatch, tmp_path: Path) -> None:
    calls: list[list[str]] = []

    def fake_run(
        argv: list[str], **_kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        calls.append(argv)
        return subprocess.CompletedProcess(
            argv, 0, stdout='{"fail_map": {}}', stderr=""
        )

    monkeypatch.setattr(lychee, "resolve_binary", lambda _binary: "C:/bin/lychee")
    monkeypatch.setattr(lychee, "run_subprocess", fake_run)

    raw = LycheeEngine().run(tmp_path, [], cwd=tmp_path)

    assert raw["exit_code"] == 0
    assert calls == [
        [
            "C:/bin/lychee",
            "--output",
            "json",
            "--offline",
            str(tmp_path),
        ]
    ]


def test_lychee_normalizes_clean_and_findings(monkeypatch, tmp_path: Path) -> None:
    engine = LycheeEngine()
    monkeypatch.setattr(LycheeEngine, "version", lambda _self: "0.15.0")

    clean = engine.normalize({"exit_code": 0, "findings": []}, tmp_path, "markdown")
    finding = engine.normalize(
        {
            "exit_code": 1,
            "findings": [
                {
                    "file": "README.md",
                    "url": "https://broken.link/example",
                    "status": "404 Not Found",
                }
            ],
        },
        tmp_path,
        "markdown",
    )

    assert clean["status"] == "ok"
    assert clean["tool"] == "markdown"
    assert finding["status"] == "warn"
    assert len(finding["findings"]) == 1
    assert finding["findings"][0]["rule"] == "broken-link"


def test_lychee_missing_and_timeout(monkeypatch, tmp_path: Path) -> None:
    engine = LycheeEngine()
    monkeypatch.setattr(common, "engine_on_path", lambda _binary: False)
    missing = common.run_engine(engine, tmp_path, tool_name="markdown")

    monkeypatch.setattr(common, "engine_on_path", lambda _binary: True)
    monkeypatch.setattr(
        lychee,
        "run_subprocess",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            subprocess.TimeoutExpired("lychee", 120)
        ),
    )
    timeout = common.run_engine(engine, tmp_path, tool_name="markdown")

    assert missing["status"] == "skipped"
    assert timeout["status"] == "error"
    assert timeout["metadata"]["terminal_reason"] == "timeout"
