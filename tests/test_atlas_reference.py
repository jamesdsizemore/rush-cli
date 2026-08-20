"""Phase 18 Atlas reference adapter fake-process matrix."""

from __future__ import annotations

import subprocess
from pathlib import Path

from rush.engines import atlas
from rush.engines.atlas import AtlasEngine


def test_atlas_runs_isolated_argv(monkeypatch, tmp_path: Path) -> None:
    calls: list[list[str]] = []

    def fake_run(
        argv: list[str], **_kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        calls.append(argv)
        return subprocess.CompletedProcess(argv, 0, stdout="{}", stderr="")

    monkeypatch.setattr(atlas, "resolve_binary", lambda _binary: "C:/bin/atlas")
    monkeypatch.setattr(atlas, "run_subprocess", fake_run)

    raw = AtlasEngine().run(tmp_path, [], cwd=tmp_path)

    assert raw["exit_code"] == 0
    assert calls == [
        [
            "C:/bin/atlas",
            "migrate",
            "lint",
            "--dir",
            f"file://{tmp_path}",
            "--format",
            "{{ json . }}",
        ]
    ]


def test_atlas_normalizes_clean_and_findings(monkeypatch, tmp_path: Path) -> None:
    engine = AtlasEngine()
    monkeypatch.setattr(AtlasEngine, "version", lambda _self: "0.26.0")

    clean = engine.normalize({"exit_code": 0, "findings": []}, tmp_path, "sql")
    assert clean["status"] == "ok"
    assert clean["findings"] == []

    failing = engine.normalize(
        {
            "exit_code": 1,
            "findings": [
                {
                    "file": "20240820_init.sql",
                    "Text": "destructive table drop detected",
                    "Level": "ERROR",
                }
            ],
        },
        tmp_path,
        "sql",
    )
    assert failing["status"] == "fail"
    assert len(failing["findings"]) == 1
    assert "atlas/destructive-table-drop-detected" in failing["findings"][0]["rule"]
