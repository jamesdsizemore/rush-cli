"""Phase 12 Polaris reference adapter fake-process matrix."""

from __future__ import annotations

import subprocess
from pathlib import Path

from rush.engines import polaris
from rush.engines.polaris import PolarisEngine


def test_polaris_runs_isolated_argv(monkeypatch, tmp_path: Path) -> None:
    calls: list[list[str]] = []

    def fake_run(
        argv: list[str], **_kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        calls.append(argv)
        return subprocess.CompletedProcess(argv, 0, stdout='{"Results": []}', stderr="")

    monkeypatch.setattr(polaris, "resolve_binary", lambda _binary: "C:/bin/polaris")
    monkeypatch.setattr(polaris, "run_subprocess", fake_run)

    raw = PolarisEngine().run(tmp_path, [], cwd=tmp_path)

    assert raw["exit_code"] == 0
    assert calls == [
        [
            "C:/bin/polaris",
            "audit",
            "--audit-path",
            str(tmp_path),
            "--format",
            "json",
        ]
    ]


def test_polaris_normalizes_clean_and_findings(monkeypatch, tmp_path: Path) -> None:
    engine = PolarisEngine()
    monkeypatch.setattr(PolarisEngine, "version", lambda _self: "8.5.0")

    clean = engine.normalize({"exit_code": 0, "findings": []}, tmp_path, "iac")
    assert clean["status"] == "ok"
    assert clean["findings"] == []

    failing = engine.normalize(
        {
            "exit_code": 1,
            "findings": [
                {
                    "target": "web-service",
                    "ID": "readOnlyRootFilesystem",
                    "Message": "Filesystem should be read-only",
                    "Severity": "danger",
                }
            ],
        },
        tmp_path,
        "iac",
    )
    assert failing["status"] == "fail"
    assert len(failing["findings"]) == 1
    assert "polaris/readOnlyRootFilesystem" in failing["findings"][0]["rule"]
