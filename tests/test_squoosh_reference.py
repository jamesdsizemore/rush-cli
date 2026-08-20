"""Phase 17 Squoosh-CLI reference adapter fake-process matrix."""

from __future__ import annotations

import subprocess
from pathlib import Path

from rush.engines import squoosh
from rush.engines.squoosh import SquooshEngine


def test_squoosh_runs_isolated_argv(monkeypatch, tmp_path: Path) -> None:
    calls: list[list[str]] = []

    def fake_run(
        argv: list[str], **_kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        calls.append(argv)
        return subprocess.CompletedProcess(argv, 0, stdout="", stderr="")

    monkeypatch.setattr(squoosh, "resolve_binary", lambda _binary: "C:/bin/squoosh-cli")
    monkeypatch.setattr(squoosh, "run_subprocess", fake_run)

    raw = SquooshEngine().run(tmp_path, [], cwd=tmp_path)

    assert raw["exit_code"] == 0
    assert calls == [
        [
            "C:/bin/squoosh-cli",
            "--webp",
            "auto",
            "-d",
            "optimized",
            str(tmp_path),
        ]
    ]


def test_squoosh_normalizes_clean_and_findings(monkeypatch, tmp_path: Path) -> None:
    engine = SquooshEngine()
    monkeypatch.setattr(SquooshEngine, "version", lambda _self: "0.7.2")

    clean = engine.normalize({"exit_code": 0, "findings": []}, tmp_path, "format")
    assert clean["status"] == "ok"
    assert clean["findings"] == []

    failing = engine.normalize(
        {
            "exit_code": 0,
            "findings": [{"log": "banner.png (1200KB) -> banner.webp (180KB, -85%)"}],
        },
        tmp_path,
        "format",
    )
    assert failing["status"] == "warn"
    assert len(failing["findings"]) == 1
    assert "squoosh/compression" in failing["findings"][0]["rule"]
