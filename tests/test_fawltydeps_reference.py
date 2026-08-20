"""Phase 14 FawltyDeps reference adapter fake-process matrix."""

from __future__ import annotations

import subprocess
from pathlib import Path

from rush.engines import fawltydeps
from rush.engines.fawltydeps import FawltydepsEngine


def test_fawltydeps_runs_isolated_argv(monkeypatch, tmp_path: Path) -> None:
    calls: list[list[str]] = []

    def fake_run(
        argv: list[str], **_kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        calls.append(argv)
        return subprocess.CompletedProcess(
            argv, 0, stdout='{"undeclared_deps": [], "unused_deps": []}', stderr=""
        )

    monkeypatch.setattr(
        fawltydeps, "resolve_binary", lambda _binary: "C:/bin/fawltydeps"
    )
    monkeypatch.setattr(fawltydeps, "run_subprocess", fake_run)

    raw = FawltydepsEngine().run(tmp_path, [], cwd=tmp_path)

    assert raw["exit_code"] == 0
    assert calls == [
        [
            "C:/bin/fawltydeps",
            "--json",
            "--detailed",
            "--code",
            str(tmp_path),
        ]
    ]


def test_fawltydeps_normalizes_clean_and_findings(monkeypatch, tmp_path: Path) -> None:
    engine = FawltydepsEngine()
    monkeypatch.setattr(FawltydepsEngine, "version", lambda _self: "0.15.0")

    clean = engine.normalize({"exit_code": 0, "findings": []}, tmp_path, "dead")
    assert clean["status"] == "ok"
    assert clean["findings"] == []

    failing = engine.normalize(
        {
            "exit_code": 1,
            "findings": [
                {
                    "type": "undeclared",
                    "dep": {"name": "requests"},
                }
            ],
        },
        tmp_path,
        "dead",
    )
    assert failing["status"] == "fail"
    assert len(failing["findings"]) == 1
    assert "fawltydeps/undeclared-dependency" in failing["findings"][0]["rule"]
