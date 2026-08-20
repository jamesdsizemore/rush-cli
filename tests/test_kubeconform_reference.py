"""Phase 07.C Kubeconform reference adapter fake-process matrix."""

from __future__ import annotations

import subprocess
from pathlib import Path

from rush.engines import kubeconform
from rush.engines.kubeconform import KubeconformEngine
from rush.tools import common


def test_kubeconform_runs_json_argv(monkeypatch, tmp_path: Path) -> None:
    calls: list[list[str]] = []

    def fake_run(
        argv: list[str], **_kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        calls.append(argv)
        return subprocess.CompletedProcess(argv, 0, stdout="", stderr="")

    monkeypatch.setattr(
        kubeconform, "resolve_binary", lambda _binary: "C:/bin/kubeconform"
    )
    monkeypatch.setattr(kubeconform, "run_subprocess", fake_run)

    raw = KubeconformEngine().run(tmp_path / "deployment.yaml", [], cwd=tmp_path)

    assert raw["exit_code"] == 0
    assert calls == [
        [
            "C:/bin/kubeconform",
            "-output",
            "json",
            "-summary",
            str(tmp_path / "deployment.yaml"),
        ]
    ]


def test_kubeconform_normalizes_clean_and_findings(monkeypatch, tmp_path: Path) -> None:
    engine = KubeconformEngine()
    monkeypatch.setattr(KubeconformEngine, "version", lambda _self: "0.6.7")

    clean = engine.normalize({"exit_code": 0, "findings": []}, tmp_path, "iac")
    finding = engine.normalize(
        {
            "exit_code": 1,
            "findings": [
                {
                    "filename": "deployment.yaml",
                    "kind": "Deployment",
                    "status": "invalid",
                    "msg": "spec.replicas: Invalid type. Expected: integer, given: string",
                }
            ],
        },
        tmp_path,
        "iac",
    )

    assert clean["status"] == "ok"
    assert clean["tool"] == "iac"
    assert finding["status"] == "fail"
    assert len(finding["findings"]) == 1
    assert finding["findings"][0]["rule"] == "Deployment"


def test_kubeconform_missing_and_timeout(monkeypatch, tmp_path: Path) -> None:
    engine = KubeconformEngine()
    monkeypatch.setattr(common, "engine_on_path", lambda _binary: False)
    missing = common.run_engine(engine, tmp_path, tool_name="iac")

    monkeypatch.setattr(common, "engine_on_path", lambda _binary: True)
    monkeypatch.setattr(
        kubeconform,
        "run_subprocess",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            subprocess.TimeoutExpired("kubeconform", 120)
        ),
    )
    timeout = common.run_engine(engine, tmp_path, tool_name="iac")

    assert missing["status"] == "skipped"
    assert timeout["status"] == "error"
    assert timeout["metadata"]["terminal_reason"] == "timeout"
