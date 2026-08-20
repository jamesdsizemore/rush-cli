"""Phase 17 BackstopJS reference adapter fake-process matrix."""

from __future__ import annotations

import subprocess
from pathlib import Path

from rush.engines import backstop
from rush.engines.backstop import BackstopEngine


def test_backstop_runs_isolated_argv(monkeypatch, tmp_path: Path) -> None:
    calls: list[list[str]] = []

    def fake_run(
        argv: list[str], **_kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        calls.append(argv)
        return subprocess.CompletedProcess(argv, 0, stdout='{"tests": []}', stderr="")

    monkeypatch.setattr(backstop, "resolve_binary", lambda _binary: "C:/bin/backstop")
    monkeypatch.setattr(backstop, "run_subprocess", fake_run)

    raw = BackstopEngine().run(tmp_path, [], cwd=tmp_path)

    assert raw["exit_code"] == 0
    assert calls == [
        [
            "C:/bin/backstop",
            "test",
            "--reporter=json",
        ]
    ]


def test_backstop_normalizes_clean_and_findings(monkeypatch, tmp_path: Path) -> None:
    engine = BackstopEngine()
    monkeypatch.setattr(BackstopEngine, "version", lambda _self: "6.3.0")

    clean = engine.normalize({"exit_code": 0, "findings": []}, tmp_path, "visual")
    assert clean["status"] == "ok"
    assert clean["findings"] == []

    failing = engine.normalize(
        {
            "exit_code": 1,
            "findings": [
                {
                    "pair": {
                        "label": "Homepage Hero",
                        "viewportLabel": "phone",
                        "url": "http://localhost:3000",
                    }
                }
            ],
        },
        tmp_path,
        "visual",
    )
    assert failing["status"] == "fail"
    assert len(failing["findings"]) == 1
    assert "backstop/viewport-mismatch" in failing["findings"][0]["rule"]
