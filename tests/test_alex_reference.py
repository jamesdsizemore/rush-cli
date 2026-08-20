"""Phase 19 Alex reference adapter fake-process matrix."""

from __future__ import annotations

import subprocess
from pathlib import Path

from rush.engines import alex
from rush.engines.alex import AlexEngine


def test_alex_runs_isolated_argv(monkeypatch, tmp_path: Path) -> None:
    calls: list[list[str]] = []

    def fake_run(
        argv: list[str], **_kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        calls.append(argv)
        return subprocess.CompletedProcess(argv, 0, stdout="[]", stderr="")

    monkeypatch.setattr(alex, "resolve_binary", lambda _binary: "C:/bin/alex")
    monkeypatch.setattr(alex, "run_subprocess", fake_run)

    raw = AlexEngine().run(tmp_path, [], cwd=tmp_path)

    assert raw["exit_code"] == 0
    assert calls == [
        [
            "C:/bin/alex",
            "--json",
            str(tmp_path),
        ]
    ]


def test_alex_normalizes_clean_and_findings(monkeypatch, tmp_path: Path) -> None:
    engine = AlexEngine()
    monkeypatch.setattr(AlexEngine, "version", lambda _self: "11.0.1")

    clean = engine.normalize({"exit_code": 0, "findings": []}, tmp_path, "lint")
    assert clean["status"] == "ok"
    assert clean["findings"] == []

    failing = engine.normalize(
        {
            "exit_code": 1,
            "findings": [
                {
                    "filePath": "docs/guide.md",
                    "line": 8,
                    "column": 2,
                    "ruleId": "master-slave",
                    "message": "Consider using 'primary-replica' instead of 'master-slave'",
                }
            ],
        },
        tmp_path,
        "lint",
    )
    assert failing["status"] == "warn"
    assert len(failing["findings"]) == 1
    assert "alex/master-slave" in failing["findings"][0]["rule"]
