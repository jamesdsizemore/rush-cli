"""Phase 07.A3 Vitest reference adapter fake-process matrix."""

from __future__ import annotations

import subprocess
from pathlib import Path

from rush.engines import vitest
from rush.engines.vitest import VitestEngine
from rush.tools import common


def test_vitest_uses_json_reporter_argv(monkeypatch, tmp_path: Path) -> None:
    calls: list[list[str]] = []

    def fake_run(
        argv: list[str], **_kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        calls.append(argv)
        return subprocess.CompletedProcess(argv, 0, stdout="[]", stderr="")

    monkeypatch.setattr(vitest, "resolve_binary", lambda _binary: "C:/bin/vitest")
    monkeypatch.setattr(vitest, "run_subprocess", fake_run)

    raw = VitestEngine().run(tmp_path, [], cwd=tmp_path)

    assert raw["exit_code"] == 0
    assert calls == [
        [
            "C:/bin/vitest",
            "run",
            "--reporter=json",
            "--no-color",
            str(tmp_path),
        ]
    ]


def test_vitest_normalizes_clean_and_findings(monkeypatch, tmp_path: Path) -> None:
    engine = VitestEngine()
    monkeypatch.setattr(VitestEngine, "version", lambda _self: "1.6.0")

    clean = engine.normalize(
        {"exit_code": 0, "findings": [{"name": "t1", "status": "passed"}]},
        tmp_path,
        "test",
    )
    failed = engine.normalize(
        {
            "exit_code": 1,
            "findings": [
                {
                    "name": "tests/a.test.ts > suite > test 1",
                    "status": "failed",
                    "failureMessages": ["AssertionError: expected true to be false"],
                }
            ],
        },
        tmp_path,
        "test",
    )
    error = engine.normalize(
        {"exit_code": 2, "stdout": "", "findings": []},
        tmp_path,
        "test",
    )

    assert clean["status"] == "ok"
    assert clean["tool"] == "test"
    assert failed["status"] == "fail"
    assert len(failed["findings"]) == 1
    assert failed["findings"][0]["rule"] == "test-failed"
    assert error["status"] == "error"


def test_vitest_missing_and_timeout(monkeypatch, tmp_path: Path) -> None:
    engine = VitestEngine()
    monkeypatch.setattr(common, "engine_on_path", lambda _binary: False)
    missing = common.run_engine(engine, tmp_path, tool_name="test")

    monkeypatch.setattr(common, "engine_on_path", lambda _binary: True)
    monkeypatch.setattr(
        vitest,
        "run_subprocess",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            subprocess.TimeoutExpired("vitest", 300)
        ),
    )
    timeout = common.run_engine(engine, tmp_path, tool_name="test")

    assert missing["status"] == "skipped"
    assert timeout["status"] == "error"
    assert timeout["metadata"]["terminal_reason"] == "timeout"
