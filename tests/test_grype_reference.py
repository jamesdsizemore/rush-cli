"""Phase 07.C Grype reference adapter fake-process matrix."""

from __future__ import annotations

import subprocess
from pathlib import Path

from rush.engines import grype
from rush.engines.grype import GrypeEngine
from rush.tools import common


def test_grype_runs_offline_dir_argv(monkeypatch, tmp_path: Path) -> None:
    calls: list[list[str]] = []

    def fake_run(
        argv: list[str], **_kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        calls.append(argv)
        return subprocess.CompletedProcess(argv, 0, stdout='{"matches": []}', stderr="")

    monkeypatch.setattr(grype, "resolve_binary", lambda _binary: "C:/bin/grype")
    monkeypatch.setattr(grype, "run_subprocess", fake_run)

    raw = GrypeEngine().run(tmp_path, [], cwd=tmp_path)

    assert raw["exit_code"] == 0
    assert calls == [
        [
            "C:/bin/grype",
            "dir:.",
            "--output",
            "json",
            "-q",
        ]
    ]


def test_grype_normalizes_clean_and_findings(monkeypatch, tmp_path: Path) -> None:
    engine = GrypeEngine()
    monkeypatch.setattr(GrypeEngine, "version", lambda _self: "0.79.0")

    clean = engine.normalize({"exit_code": 0, "findings": []}, tmp_path, "security")
    finding = engine.normalize(
        {
            "exit_code": 1,
            "findings": [
                {
                    "vulnerability": {
                        "id": "GHSA-1234",
                        "severity": "Critical",
                        "description": "Remote code execution",
                    },
                    "artifact": {"name": "lodash", "version": "4.17.15"},
                }
            ],
        },
        tmp_path,
        "security",
    )

    assert clean["status"] == "ok"
    assert clean["tool"] == "security"
    assert finding["status"] == "fail"
    assert len(finding["findings"]) == 1
    assert finding["findings"][0]["rule"] == "GHSA-1234"
    assert finding["findings"][0]["severity"] == "error"


def test_grype_missing_and_timeout(monkeypatch, tmp_path: Path) -> None:
    engine = GrypeEngine()
    monkeypatch.setattr(common, "engine_on_path", lambda _binary: False)
    missing = common.run_engine(engine, tmp_path, tool_name="security")

    monkeypatch.setattr(common, "engine_on_path", lambda _binary: True)
    monkeypatch.setattr(
        grype,
        "run_subprocess",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            subprocess.TimeoutExpired("grype", 180)
        ),
    )
    timeout = common.run_engine(engine, tmp_path, tool_name="security")

    assert missing["status"] == "skipped"
    assert timeout["status"] == "error"
    assert timeout["metadata"]["terminal_reason"] == "timeout"
