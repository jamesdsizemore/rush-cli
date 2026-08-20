"""Phase 11 Pip-licenses reference adapter fake-process matrix."""

from __future__ import annotations

import subprocess
from pathlib import Path

from rush.engines import pip_licenses
from rush.engines.pip_licenses import PipLicensesEngine


def test_pip_licenses_runs_isolated_argv(monkeypatch, tmp_path: Path) -> None:
    calls: list[list[str]] = []

    def fake_run(
        argv: list[str], **_kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        calls.append(argv)
        return subprocess.CompletedProcess(argv, 0, stdout="[]", stderr="")

    monkeypatch.setattr(
        pip_licenses, "resolve_binary", lambda _binary: "C:/bin/pip-licenses"
    )
    monkeypatch.setattr(pip_licenses, "run_subprocess", fake_run)

    raw = PipLicensesEngine().run(tmp_path, [], cwd=tmp_path)

    assert raw["exit_code"] == 0
    assert calls == [
        [
            "C:/bin/pip-licenses",
            "--format=json",
        ]
    ]


def test_pip_licenses_normalizes_clean_and_findings(
    monkeypatch, tmp_path: Path
) -> None:
    engine = PipLicensesEngine()
    monkeypatch.setattr(PipLicensesEngine, "version", lambda _self: "4.3.0")

    clean = engine.normalize({"exit_code": 0, "findings": []}, tmp_path, "sbom")
    assert clean["status"] == "ok"
    assert clean["findings"] == []

    failing = engine.normalize(
        {
            "exit_code": 0,
            "findings": [
                {
                    "Name": "gpl-package",
                    "Version": "1.0.0",
                    "License": "GNU General Public License v3 (GPLv3)",
                }
            ],
        },
        tmp_path,
        "sbom",
    )
    assert failing["status"] == "warn"
    assert len(failing["findings"]) == 1
    assert "gpl" in failing["findings"][0]["rule"]
