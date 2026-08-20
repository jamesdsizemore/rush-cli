"""Phase 19 Statoscope reference adapter fake-process matrix."""

from __future__ import annotations

import subprocess
from pathlib import Path

from rush.engines import statoscope
from rush.engines.statoscope import StatoscopeEngine


def test_statoscope_runs_isolated_argv(monkeypatch, tmp_path: Path) -> None:
    calls: list[list[str]] = []

    def fake_run(
        argv: list[str], **_kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        calls.append(argv)
        return subprocess.CompletedProcess(argv, 0, stdout='{"rules": []}', stderr="")

    monkeypatch.setattr(
        statoscope, "resolve_binary", lambda _binary: "C:/bin/statoscope"
    )
    monkeypatch.setattr(statoscope, "run_subprocess", fake_run)

    raw = StatoscopeEngine().run(tmp_path, [], cwd=tmp_path)

    assert raw["exit_code"] == 0
    assert calls == [
        [
            "C:/bin/statoscope",
            "validate",
            "--input",
            str(tmp_path),
            "--format",
            "json",
        ]
    ]


def test_statoscope_normalizes_clean_and_findings(monkeypatch, tmp_path: Path) -> None:
    engine = StatoscopeEngine()
    monkeypatch.setattr(StatoscopeEngine, "version", lambda _self: "5.28.0")

    clean = engine.normalize({"exit_code": 0, "findings": []}, tmp_path, "metrics")
    assert clean["status"] == "ok"
    assert clean["findings"] == []

    failing = engine.normalize(
        {
            "exit_code": 1,
            "findings": [
                {
                    "name": "duplicate-packages",
                    "status": "error",
                    "message": "Duplicate package lodash included 3 times in bundle",
                }
            ],
        },
        tmp_path,
        "metrics",
    )
    assert failing["status"] == "fail"
    assert len(failing["findings"]) == 1
    assert "statoscope/duplicate-packages" in failing["findings"][0]["rule"]
