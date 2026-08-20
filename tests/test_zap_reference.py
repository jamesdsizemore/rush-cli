"""Phase 15 OWASP ZAP reference adapter fake-process matrix."""

from __future__ import annotations

import subprocess
from pathlib import Path

from rush.engines import zap
from rush.engines.zap import ZapEngine


def test_zap_runs_isolated_argv(monkeypatch, tmp_path: Path) -> None:
    calls: list[list[str]] = []

    def fake_run(
        argv: list[str], **_kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        calls.append(argv)
        return subprocess.CompletedProcess(argv, 0, stdout="{}", stderr="")

    monkeypatch.setattr(zap, "resolve_binary", lambda _binary: "C:/bin/zap-cli")
    monkeypatch.setattr(zap, "run_subprocess", fake_run)

    raw = ZapEngine().run(tmp_path, [], cwd=tmp_path)

    assert raw["exit_code"] == 0
    assert calls == [
        [
            "C:/bin/zap-cli",
            "quick-scan",
            "--self-contained",
            "--format",
            "json",
            "http://localhost:8080",
        ]
    ]


def test_zap_normalizes_clean_and_findings(monkeypatch, tmp_path: Path) -> None:
    engine = ZapEngine()
    monkeypatch.setattr(ZapEngine, "version", lambda _self: "2.14.0")

    clean = engine.normalize({"exit_code": 0, "findings": []}, tmp_path, "security")
    assert clean["status"] == "ok"
    assert clean["findings"] == []

    failing = engine.normalize(
        {
            "exit_code": 1,
            "findings": [
                {
                    "pluginId": "10020",
                    "alert": "Anti-CSRF Header Not Set",
                    "risk": "High",
                    "url": "http://localhost:8080/api/v1/update",
                }
            ],
        },
        tmp_path,
        "security",
    )
    assert failing["status"] == "fail"
    assert len(failing["findings"]) == 1
    assert "zap/10020" in failing["findings"][0]["rule"]
