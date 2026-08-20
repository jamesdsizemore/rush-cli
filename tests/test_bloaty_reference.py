"""Phase 19 Bloaty reference adapter fake-process matrix."""

from __future__ import annotations

import subprocess
from pathlib import Path

from rush.engines import bloaty
from rush.engines.bloaty import BloatyEngine


def test_bloaty_runs_isolated_argv(monkeypatch, tmp_path: Path) -> None:
    calls: list[list[str]] = []

    def fake_run(
        argv: list[str], **_kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        calls.append(argv)
        return subprocess.CompletedProcess(argv, 0, stdout="", stderr="")

    monkeypatch.setattr(bloaty, "resolve_binary", lambda _binary: "C:/bin/bloaty")
    monkeypatch.setattr(bloaty, "run_subprocess", fake_run)

    raw = BloatyEngine().run(tmp_path, [], cwd=tmp_path)

    assert raw["exit_code"] == 0
    assert calls == [
        [
            "C:/bin/bloaty",
            "-d",
            "compileunits,symbols",
            "--csv",
            str(tmp_path),
        ]
    ]


def test_bloaty_normalizes_clean_and_findings(monkeypatch, tmp_path: Path) -> None:
    engine = BloatyEngine()
    monkeypatch.setattr(BloatyEngine, "version", lambda _self: "1.1.0")

    clean = engine.normalize({"exit_code": 0, "findings": []}, tmp_path, "metrics")
    assert clean["status"] == "ok"
    assert clean["findings"] == []

    failing = engine.normalize(
        {
            "exit_code": 0,
            "findings": [
                {
                    "unit": "src/parser.o",
                    "symbol": "parse_ast_node",
                    "vmsize": "40960",
                    "filesize": "40960",
                }
            ],
        },
        tmp_path,
        "metrics",
    )
    assert failing["status"] == "warn"
    assert len(failing["findings"]) == 1
    assert "bloaty/binary-footprint" in failing["findings"][0]["rule"]
