"""Phase 16 Pitest reference adapter fake-process matrix."""

from __future__ import annotations

import subprocess
from pathlib import Path

from rush.engines import pitest
from rush.engines.pitest import PitestEngine


def test_pitest_runs_isolated_argv(monkeypatch, tmp_path: Path) -> None:
    calls: list[list[str]] = []

    def fake_run(
        argv: list[str], **_kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        calls.append(argv)
        return subprocess.CompletedProcess(argv, 0, stdout="", stderr="")

    monkeypatch.setattr(pitest, "resolve_binary", lambda _binary: "C:/bin/mvn")
    monkeypatch.setattr(pitest, "run_subprocess", fake_run)

    raw = PitestEngine().run(tmp_path, [], cwd=tmp_path)

    assert raw["exit_code"] == 0
    assert calls == [
        [
            "C:/bin/mvn",
            "org.pitest:pitest-maven:mutationCoverage",
            "-DoutputFormats=JSON",
        ]
    ]


def test_pitest_normalizes_clean_and_findings(monkeypatch, tmp_path: Path) -> None:
    engine = PitestEngine()
    monkeypatch.setattr(PitestEngine, "version", lambda _self: "1.15.0")

    clean = engine.normalize({"exit_code": 0, "findings": []}, tmp_path, "mutation")
    assert clean["status"] == "ok"
    assert clean["findings"] == []

    failing = engine.normalize(
        {
            "exit_code": 0,
            "findings": [
                {
                    "sourceFile": "UserService.java",
                    "lineNumber": 104,
                    "mutatedClass": "com.example.UserService",
                    "mutator": "org.pitest.mutationtest.engine.gregor.mutators.ConditionalsBoundaryMutator",
                    "description": "changed conditional boundary",
                }
            ],
        },
        tmp_path,
        "mutation",
    )
    assert failing["status"] == "warn"
    assert len(failing["findings"]) == 1
    assert "pitest/ConditionalsBoundaryMutator" in failing["findings"][0]["rule"]
