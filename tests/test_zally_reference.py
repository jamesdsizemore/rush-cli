"""Phase 13 Zally reference adapter fake-process matrix."""

from __future__ import annotations

import subprocess
from pathlib import Path

from rush.engines import zally
from rush.engines.zally import ZallyEngine


def test_zally_runs_isolated_argv(monkeypatch, tmp_path: Path) -> None:
    calls: list[list[str]] = []

    def fake_run(
        argv: list[str], **_kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        calls.append(argv)
        return subprocess.CompletedProcess(
            argv, 0, stdout='{"violations": []}', stderr=""
        )

    monkeypatch.setattr(zally, "resolve_binary", lambda _binary: "C:/bin/zally")
    monkeypatch.setattr(zally, "run_subprocess", fake_run)

    raw = ZallyEngine().run(tmp_path, [], cwd=tmp_path)

    assert raw["exit_code"] == 0
    assert calls == [
        [
            "C:/bin/zally",
            "lint",
            str(tmp_path),
            "--format",
            "json",
        ]
    ]


def test_zally_normalizes_clean_and_findings(monkeypatch, tmp_path: Path) -> None:
    engine = ZallyEngine()
    monkeypatch.setattr(ZallyEngine, "version", lambda _self: "2.1.0")

    clean = engine.normalize({"exit_code": 0, "findings": []}, tmp_path, "yaml")
    assert clean["status"] == "ok"
    assert clean["findings"] == []

    failing = engine.normalize(
        {
            "exit_code": 1,
            "findings": [
                {
                    "rule_title": "Use Snake Case For Query Params",
                    "violation_type": "MUST",
                    "description": "Query parameter camelCaseParam must use snake_case",
                    "pointer": "/paths/~1users/get/parameters/0",
                    "line_number": 25,
                }
            ],
        },
        tmp_path,
        "yaml",
    )
    assert failing["status"] == "fail"
    assert len(failing["findings"]) == 1
    assert "zally/use-snake-case-for-query-params" in failing["findings"][0]["rule"]
