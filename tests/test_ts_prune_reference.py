"""Phase 14 Ts-prune reference adapter fake-process matrix."""

from __future__ import annotations

import subprocess
from pathlib import Path

from rush.engines import ts_prune
from rush.engines.ts_prune import TsPruneEngine


def test_ts_prune_runs_isolated_argv(monkeypatch, tmp_path: Path) -> None:
    calls: list[list[str]] = []

    def fake_run(
        argv: list[str], **_kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        calls.append(argv)
        return subprocess.CompletedProcess(argv, 0, stdout="[]", stderr="")

    monkeypatch.setattr(ts_prune, "resolve_binary", lambda _binary: "C:/bin/ts-prune")
    monkeypatch.setattr(ts_prune, "run_subprocess", fake_run)

    raw = TsPruneEngine().run(tmp_path, [], cwd=tmp_path)

    assert raw["exit_code"] == 0
    assert calls == [
        [
            "C:/bin/ts-prune",
            "--json",
        ]
    ]


def test_ts_prune_normalizes_clean_and_findings(monkeypatch, tmp_path: Path) -> None:
    engine = TsPruneEngine()
    monkeypatch.setattr(TsPruneEngine, "version", lambda _self: "0.10.3")

    clean = engine.normalize({"exit_code": 0, "findings": []}, tmp_path, "dead")
    assert clean["status"] == "ok"
    assert clean["findings"] == []

    failing = engine.normalize(
        {
            "exit_code": 0,
            "findings": [
                {
                    "file": "src/types.ts",
                    "line": 42,
                    "symbol": "DeprecatedUserRole",
                }
            ],
        },
        tmp_path,
        "dead",
    )
    assert failing["status"] == "warn"
    assert len(failing["findings"]) == 1
    assert "ts-prune/unused-export" in failing["findings"][0]["rule"]
