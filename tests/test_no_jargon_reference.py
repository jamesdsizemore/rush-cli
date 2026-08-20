"""Phase 19 No-Jargon reference adapter fake-process matrix."""

from __future__ import annotations

import subprocess
from pathlib import Path

from rush.engines import no_jargon
from rush.engines.no_jargon import NoJargonEngine


def test_no_jargon_runs_isolated_argv(monkeypatch, tmp_path: Path) -> None:
    calls: list[list[str]] = []

    def fake_run(
        argv: list[str], **_kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        calls.append(argv)
        return subprocess.CompletedProcess(argv, 0, stdout="[]", stderr="")

    monkeypatch.setattr(no_jargon, "resolve_binary", lambda _binary: "C:/bin/no-jargon")
    monkeypatch.setattr(no_jargon, "run_subprocess", fake_run)

    raw = NoJargonEngine().run(tmp_path, [], cwd=tmp_path)

    assert raw["exit_code"] == 0
    assert calls == [
        [
            "C:/bin/no-jargon",
            "--json",
            str(tmp_path),
        ]
    ]


def test_no_jargon_normalizes_clean_and_findings(monkeypatch, tmp_path: Path) -> None:
    engine = NoJargonEngine()
    monkeypatch.setattr(NoJargonEngine, "version", lambda _self: "0.2.0")

    clean = engine.normalize({"exit_code": 0, "findings": []}, tmp_path, "lint")
    assert clean["status"] == "ok"
    assert clean["findings"] == []

    failing = engine.normalize(
        {
            "exit_code": 0,
            "findings": [
                {
                    "file": "README.md",
                    "line": 4,
                    "col": 12,
                    "word": "synergize",
                    "suggestion": "combine",
                }
            ],
        },
        tmp_path,
        "lint",
    )
    assert failing["status"] == "warn"
    assert len(failing["findings"]) == 1
    assert "no-jargon/buzzword" in failing["findings"][0]["rule"]
