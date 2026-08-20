"""Phase 18 Squawk reference adapter fake-process matrix."""

from __future__ import annotations

import subprocess
from pathlib import Path

from rush.engines import squawk
from rush.engines.squawk import SquawkEngine


def test_squawk_runs_isolated_argv(monkeypatch, tmp_path: Path) -> None:
    calls: list[list[str]] = []

    def fake_run(
        argv: list[str], **_kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        calls.append(argv)
        return subprocess.CompletedProcess(argv, 0, stdout="[]", stderr="")

    monkeypatch.setattr(squawk, "resolve_binary", lambda _binary: "C:/bin/squawk")
    monkeypatch.setattr(squawk, "run_subprocess", fake_run)

    raw = SquawkEngine().run(tmp_path, [], cwd=tmp_path)

    assert raw["exit_code"] == 0
    assert calls == [
        [
            "C:/bin/squawk",
            "--format=json",
            str(tmp_path),
        ]
    ]


def test_squawk_normalizes_clean_and_findings(monkeypatch, tmp_path: Path) -> None:
    engine = SquawkEngine()
    monkeypatch.setattr(SquawkEngine, "version", lambda _self: "0.27.0")

    clean = engine.normalize({"exit_code": 0, "findings": []}, tmp_path, "sql")
    assert clean["status"] == "ok"
    assert clean["findings"] == []

    failing = engine.normalize(
        {
            "exit_code": 1,
            "findings": [
                {
                    "file": "migration.sql",
                    "line": 4,
                    "rule": "ban-drop-table",
                    "message": "Dropping a table requires an ACCESS EXCLUSIVE lock",
                }
            ],
        },
        tmp_path,
        "sql",
    )
    assert failing["status"] == "warn"
    assert len(failing["findings"]) == 1
    assert "squawk/ban-drop-table" in failing["findings"][0]["rule"]
