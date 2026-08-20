"""Phase 11 ScanCode reference adapter fake-process matrix."""

from __future__ import annotations

import subprocess
from pathlib import Path

from rush.engines import scancode
from rush.engines.scancode import ScancodeEngine


def test_scancode_runs_isolated_argv(monkeypatch, tmp_path: Path) -> None:
    calls: list[list[str]] = []

    def fake_run(
        argv: list[str], **_kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        calls.append(argv)
        return subprocess.CompletedProcess(argv, 0, stdout='{"files": []}', stderr="")

    monkeypatch.setattr(scancode, "resolve_binary", lambda _binary: "C:/bin/scancode")
    monkeypatch.setattr(scancode, "run_subprocess", fake_run)

    raw = ScancodeEngine().run(tmp_path, [], cwd=tmp_path)

    assert raw["exit_code"] == 0
    assert calls == [
        [
            "C:/bin/scancode",
            "--license",
            "--copyright",
            "--json-pp",
            "scancode-results.json",
            "--quiet",
            str(tmp_path),
        ]
    ]


def test_scancode_normalizes_clean_and_findings(monkeypatch, tmp_path: Path) -> None:
    engine = ScancodeEngine()
    monkeypatch.setattr(ScancodeEngine, "version", lambda _self: "32.1.0")

    clean = engine.normalize({"exit_code": 0, "findings": []}, tmp_path, "sbom")
    assert clean["status"] == "ok"
    assert clean["findings"] == []

    failing = engine.normalize(
        {
            "exit_code": 0,
            "findings": [
                {
                    "path": "vendor/gpl_lib.py",
                    "license": {
                        "spdx_license_key": "GPL-3.0-only",
                        "start_line": 1,
                        "key": "gpl-3.0",
                    },
                }
            ],
        },
        tmp_path,
        "sbom",
    )
    assert failing["status"] == "warn"
    assert len(failing["findings"]) == 1
    assert "license/gpl-3.0-only" in failing["findings"][0]["rule"]
