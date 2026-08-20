"""Phase 13 Schemathesis reference adapter fake-process matrix."""

from __future__ import annotations

import subprocess
from pathlib import Path

from rush.engines import schemathesis
from rush.engines.schemathesis import SchemathesisEngine


def test_schemathesis_runs_isolated_argv(monkeypatch, tmp_path: Path) -> None:
    calls: list[list[str]] = []

    def fake_run(
        argv: list[str], **_kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        calls.append(argv)
        return subprocess.CompletedProcess(argv, 0, stdout="", stderr="")

    monkeypatch.setattr(
        schemathesis, "resolve_binary", lambda _binary: "C:/bin/schemathesis"
    )
    monkeypatch.setattr(schemathesis, "run_subprocess", fake_run)

    raw = SchemathesisEngine().run(tmp_path, [], cwd=tmp_path)

    assert raw["exit_code"] == 0
    assert calls == [
        [
            "C:/bin/schemathesis",
            "run",
            str(tmp_path),
            "--report=junit",
            "--output-path=schemathesis-report.xml",
            "--dry-run",
        ]
    ]


def test_schemathesis_normalizes_clean_and_failures(
    monkeypatch, tmp_path: Path
) -> None:
    engine = SchemathesisEngine()
    monkeypatch.setattr(SchemathesisEngine, "version", lambda _self: "3.36.0")

    clean = engine.normalize({"exit_code": 0, "findings": []}, tmp_path, "contract")
    assert clean["status"] == "ok"
    assert clean["findings"] == []

    failing = engine.normalize(
        {
            "exit_code": 1,
            "findings": [
                {
                    "code": "status_code_conformance",
                    "message": "Returned 500 on valid generated payload",
                }
            ],
        },
        tmp_path,
        "contract",
    )
    assert failing["status"] == "fail"
    assert len(failing["findings"]) == 1
    assert failing["findings"][0]["rule"] == "status_code_conformance"
