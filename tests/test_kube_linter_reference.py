"""Phase 12 KubeLinter reference adapter fake-process matrix."""

from __future__ import annotations

import subprocess
from pathlib import Path

from rush.engines import kube_linter
from rush.engines.kube_linter import KubeLinterEngine


def test_kube_linter_runs_isolated_argv(monkeypatch, tmp_path: Path) -> None:
    calls: list[list[str]] = []

    def fake_run(
        argv: list[str], **_kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        calls.append(argv)
        return subprocess.CompletedProcess(argv, 0, stdout='{"Reports": []}', stderr="")

    monkeypatch.setattr(
        kube_linter, "resolve_binary", lambda _binary: "C:/bin/kube-linter"
    )
    monkeypatch.setattr(kube_linter, "run_subprocess", fake_run)

    raw = KubeLinterEngine().run(tmp_path, [], cwd=tmp_path)

    assert raw["exit_code"] == 0
    assert calls == [
        [
            "C:/bin/kube-linter",
            "lint",
            str(tmp_path),
            "--format",
            "json",
        ]
    ]


def test_kube_linter_normalizes_clean_and_findings(monkeypatch, tmp_path: Path) -> None:
    engine = KubeLinterEngine()
    monkeypatch.setattr(KubeLinterEngine, "version", lambda _self: "0.6.0")

    clean = engine.normalize({"exit_code": 0, "findings": []}, tmp_path, "iac")
    assert clean["status"] == "ok"
    assert clean["findings"] == []

    failing = engine.normalize(
        {
            "exit_code": 1,
            "findings": [
                {
                    "Check": "no-read-only-root-fs",
                    "Object": {"K8sObject": {"Name": "api-server"}},
                    "Remediation": "Set readOnlyRootFilesystem to true",
                }
            ],
        },
        tmp_path,
        "iac",
    )
    assert failing["status"] == "warn"
    assert len(failing["findings"]) == 1
    assert "kube-linter/no-read-only-root-fs" in failing["findings"][0]["rule"]
