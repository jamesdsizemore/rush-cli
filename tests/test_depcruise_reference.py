"""Phase 14 Dependency-Cruiser reference adapter fake-process matrix."""

from __future__ import annotations

import subprocess
from pathlib import Path

from rush.engines import depcruise
from rush.engines.depcruise import DepcruiseEngine


def test_depcruise_runs_isolated_argv(monkeypatch, tmp_path: Path) -> None:
    calls: list[list[str]] = []

    def fake_run(
        argv: list[str], **_kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        calls.append(argv)
        return subprocess.CompletedProcess(
            argv, 0, stdout='{"summary": {"violations": []}}', stderr=""
        )

    monkeypatch.setattr(depcruise, "resolve_binary", lambda _binary: "C:/bin/depcruise")
    monkeypatch.setattr(depcruise, "run_subprocess", fake_run)

    raw = DepcruiseEngine().run(tmp_path, [], cwd=tmp_path)

    assert raw["exit_code"] == 0
    assert calls == [
        [
            "C:/bin/depcruise",
            "--output-type",
            "json",
            str(tmp_path),
        ]
    ]


def test_depcruise_normalizes_clean_and_findings(monkeypatch, tmp_path: Path) -> None:
    engine = DepcruiseEngine()
    monkeypatch.setattr(DepcruiseEngine, "version", lambda _self: "16.4.0")

    clean = engine.normalize({"exit_code": 0, "findings": []}, tmp_path, "complexity")
    assert clean["status"] == "ok"
    assert clean["findings"] == []

    failing = engine.normalize(
        {
            "exit_code": 1,
            "findings": [
                {
                    "from": "src/controllers/auth.ts",
                    "to": "src/database/direct.ts",
                    "rule": {
                        "name": "no-controller-to-db",
                        "severity": "error",
                    },
                }
            ],
        },
        tmp_path,
        "complexity",
    )
    assert failing["status"] == "fail"
    assert len(failing["findings"]) == 1
    assert "depcruise/no-controller-to-db" in failing["findings"][0]["rule"]
