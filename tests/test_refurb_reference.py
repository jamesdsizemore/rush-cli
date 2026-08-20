"""Phase 14 Refurb reference adapter fake-process matrix."""

from __future__ import annotations

import subprocess
from pathlib import Path

from rush.engines import refurb
from rush.engines.refurb import RefurbEngine


def test_refurb_runs_isolated_argv(monkeypatch, tmp_path: Path) -> None:
    calls: list[list[str]] = []

    def fake_run(
        argv: list[str], **_kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        calls.append(argv)
        return subprocess.CompletedProcess(argv, 0, stdout="[]", stderr="")

    monkeypatch.setattr(refurb, "resolve_binary", lambda _binary: "C:/bin/refurb")
    monkeypatch.setattr(refurb, "run_subprocess", fake_run)

    raw = RefurbEngine().run(tmp_path, [], cwd=tmp_path)

    assert raw["exit_code"] == 0
    assert calls == [
        [
            "C:/bin/refurb",
            "--format",
            "json",
            str(tmp_path),
        ]
    ]


def test_refurb_normalizes_clean_and_findings(monkeypatch, tmp_path: Path) -> None:
    engine = RefurbEngine()
    monkeypatch.setattr(RefurbEngine, "version", lambda _self: "2.0.0")

    clean = engine.normalize({"exit_code": 0, "findings": []}, tmp_path, "lint")
    assert clean["status"] == "ok"
    assert clean["findings"] == []

    failing = engine.normalize(
        {
            "exit_code": 0,
            "findings": [
                {
                    "path": "app.py",
                    "line": 10,
                    "column": 4,
                    "code": "FURB101",
                    "message": "Use `pathlib.Path.read_text()` instead of `open()`",
                }
            ],
        },
        tmp_path,
        "lint",
    )
    assert failing["status"] == "warn"
    assert len(failing["findings"]) == 1
    assert failing["findings"][0]["rule"] == "refurb/FURB101"
