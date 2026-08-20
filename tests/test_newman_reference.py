"""Phase 13 Newman reference adapter fake-process matrix."""

from __future__ import annotations

import subprocess
from pathlib import Path

from rush.engines import newman
from rush.engines.newman import NewmanEngine


def test_newman_runs_isolated_argv(monkeypatch, tmp_path: Path) -> None:
    calls: list[list[str]] = []

    def fake_run(
        argv: list[str], **_kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        calls.append(argv)
        return subprocess.CompletedProcess(
            argv, 0, stdout='{"run": {"failures": []}}', stderr=""
        )

    monkeypatch.setattr(newman, "resolve_binary", lambda _binary: "C:/bin/newman")
    monkeypatch.setattr(newman, "run_subprocess", fake_run)

    raw = NewmanEngine().run(tmp_path, [], cwd=tmp_path)

    assert raw["exit_code"] == 0
    assert calls == [
        [
            "C:/bin/newman",
            "run",
            str(tmp_path),
            "--reporters",
            "json",
            "--reporter-json-export",
            "newman-run.json",
        ]
    ]


def test_newman_normalizes_clean_and_failures(monkeypatch, tmp_path: Path) -> None:
    engine = NewmanEngine()
    monkeypatch.setattr(NewmanEngine, "version", lambda _self: "6.2.0")

    clean = engine.normalize({"exit_code": 0, "findings": []}, tmp_path, "test")
    assert clean["status"] == "ok"
    assert clean["findings"] == []

    failing = engine.normalize(
        {
            "exit_code": 1,
            "findings": [
                {
                    "error": {
                        "test": "Status code is 200",
                        "message": "expected response code 200 but got 404",
                    }
                }
            ],
        },
        tmp_path,
        "test",
    )
    assert failing["status"] == "fail"
    assert len(failing["findings"]) == 1
    assert "newman/status-code-is-200" in failing["findings"][0]["rule"]
