"""Phase 19 Dockle reference adapter fake-process matrix."""

from __future__ import annotations

import subprocess
from pathlib import Path

from rush.engines import dockle
from rush.engines.dockle import DockleEngine


def test_dockle_runs_isolated_argv(monkeypatch, tmp_path: Path) -> None:
    calls: list[list[str]] = []

    def fake_run(
        argv: list[str], **_kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        calls.append(argv)
        return subprocess.CompletedProcess(argv, 0, stdout="{}", stderr="")

    monkeypatch.setattr(dockle, "resolve_binary", lambda _binary: "C:/bin/dockle")
    monkeypatch.setattr(dockle, "run_subprocess", fake_run)

    raw = DockleEngine().run(tmp_path, [], cwd=tmp_path)

    assert raw["exit_code"] == 0
    assert calls == [
        [
            "C:/bin/dockle",
            "--format",
            "json",
            str(tmp_path),
        ]
    ]


def test_dockle_normalizes_clean_and_findings(monkeypatch, tmp_path: Path) -> None:
    engine = DockleEngine()
    monkeypatch.setattr(DockleEngine, "version", lambda _self: "0.4.14")

    clean = engine.normalize({"exit_code": 0, "findings": []}, tmp_path, "security")
    assert clean["status"] == "ok"
    assert clean["findings"] == []

    failing = engine.normalize(
        {
            "exit_code": 1,
            "findings": [
                {
                    "code": "CIS-DI-0001",
                    "level": "WARN",
                    "title": "Create a user for the container",
                }
            ],
        },
        tmp_path,
        "security",
    )
    assert failing["status"] == "fail"
    assert len(failing["findings"]) == 1
    assert "dockle/CIS-DI-0001" in failing["findings"][0]["rule"]
