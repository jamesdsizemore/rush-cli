"""Phase 11 GUAC reference adapter fake-process matrix."""

from __future__ import annotations

import subprocess
from pathlib import Path

from rush.engines import guac
from rush.engines.guac import GuacEngine


def test_guac_runs_isolated_argv(monkeypatch, tmp_path: Path) -> None:
    calls: list[list[str]] = []

    def fake_run(
        argv: list[str], **_kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        calls.append(argv)
        return subprocess.CompletedProcess(
            argv, 0, stdout='{"vulnerabilities": []}', stderr=""
        )

    monkeypatch.setattr(guac, "resolve_binary", lambda _binary: "C:/bin/guacone")
    monkeypatch.setattr(guac, "run_subprocess", fake_run)

    raw = GuacEngine().run(tmp_path, [], cwd=tmp_path)

    assert raw["exit_code"] == 0
    assert calls == [
        [
            "C:/bin/guacone",
            "collect",
            "files",
            "--format",
            "json",
            str(tmp_path),
        ]
    ]


def test_guac_normalizes_clean_and_findings(monkeypatch, tmp_path: Path) -> None:
    engine = GuacEngine()
    monkeypatch.setattr(GuacEngine, "version", lambda _self: "0.8.0")

    clean = engine.normalize({"exit_code": 0, "findings": []}, tmp_path, "sbom")
    assert clean["status"] == "ok"
    assert clean["findings"] == []

    failing = engine.normalize(
        {
            "exit_code": 0,
            "findings": [
                {
                    "path": "pkg:npm/left-pad@1.3.0",
                    "vuln_id": "GHSA-xxxx-yyyy",
                    "description": "Transitive dependency vulnerability",
                }
            ],
        },
        tmp_path,
        "sbom",
    )
    assert failing["status"] == "warn"
    assert len(failing["findings"]) == 1
    assert failing["findings"][0]["rule"] == "GHSA-xxxx-yyyy"
