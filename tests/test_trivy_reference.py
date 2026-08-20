"""Phase 07.C Trivy reference adapter fake-process matrix."""

from __future__ import annotations

import subprocess
from pathlib import Path

from rush.engines import trivy
from rush.engines.trivy import TrivyEngine
from rush.tools import common


def test_trivy_runs_offline_fs_argv(monkeypatch, tmp_path: Path) -> None:
    calls: list[list[str]] = []

    def fake_run(
        argv: list[str], **_kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        calls.append(argv)
        return subprocess.CompletedProcess(argv, 0, stdout='{"Results": []}', stderr="")

    monkeypatch.setattr(trivy, "resolve_binary", lambda _binary: "C:/bin/trivy")
    monkeypatch.setattr(trivy, "run_subprocess", fake_run)

    raw = TrivyEngine().run(tmp_path, [], cwd=tmp_path)

    assert raw["exit_code"] == 0
    assert calls == [
        [
            "C:/bin/trivy",
            "fs",
            "--format",
            "json",
            "--offline-scan",
            "--quiet",
            str(tmp_path),
        ]
    ]


def test_trivy_normalizes_clean_and_findings(monkeypatch, tmp_path: Path) -> None:
    engine = TrivyEngine()
    monkeypatch.setattr(TrivyEngine, "version", lambda _self: "0.55.0")

    clean = engine.normalize({"exit_code": 0, "findings": []}, tmp_path, "security")
    finding = engine.normalize(
        {
            "exit_code": 1,
            "findings": [
                {
                    "target": "requirements.txt",
                    "vuln_id": "CVE-2024-1234",
                    "pkg_name": "urllib3",
                    "installed_version": "1.26.4",
                    "fixed_version": "1.26.5",
                    "severity": "HIGH",
                    "title": "Proxy bypass vulnerability",
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
    assert finding["findings"][0]["rule"] == "CVE-2024-1234"
    assert finding["findings"][0]["severity"] == "error"


def test_trivy_missing_and_timeout(monkeypatch, tmp_path: Path) -> None:
    engine = TrivyEngine()
    monkeypatch.setattr(common, "engine_on_path", lambda _binary: False)
    missing = common.run_engine(engine, tmp_path, tool_name="security")

    monkeypatch.setattr(common, "engine_on_path", lambda _binary: True)
    monkeypatch.setattr(
        trivy,
        "run_subprocess",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            subprocess.TimeoutExpired("trivy", 180)
        ),
    )
    timeout = common.run_engine(engine, tmp_path, tool_name="security")

    assert missing["status"] == "skipped"
    assert timeout["status"] == "error"
    assert timeout["metadata"]["terminal_reason"] == "timeout"
