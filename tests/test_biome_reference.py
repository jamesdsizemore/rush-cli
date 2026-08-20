"""Phase 14 Biome reference adapter fake-process matrix."""

from __future__ import annotations

import subprocess
from pathlib import Path

from rush.engines import biome
from rush.engines.biome import BiomeEngine


def test_biome_runs_isolated_argv(monkeypatch, tmp_path: Path) -> None:
    calls: list[list[str]] = []

    def fake_run(
        argv: list[str], **_kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        calls.append(argv)
        return subprocess.CompletedProcess(
            argv, 0, stdout='{"diagnostics": []}', stderr=""
        )

    monkeypatch.setattr(biome, "resolve_binary", lambda _binary: "C:/bin/biome")
    monkeypatch.setattr(biome, "run_subprocess", fake_run)

    raw = BiomeEngine().run(tmp_path, [], cwd=tmp_path)

    assert raw["exit_code"] == 0
    assert calls == [
        [
            "C:/bin/biome",
            "check",
            "--reporter=json",
            str(tmp_path),
        ]
    ]


def test_biome_normalizes_clean_and_findings(monkeypatch, tmp_path: Path) -> None:
    engine = BiomeEngine()
    monkeypatch.setattr(BiomeEngine, "version", lambda _self: "1.8.0")

    clean = engine.normalize({"exit_code": 0, "findings": []}, tmp_path, "lint")
    assert clean["status"] == "ok"
    assert clean["findings"] == []

    failing = engine.normalize(
        {
            "exit_code": 1,
            "findings": [
                {
                    "category": "lint/style/useConst",
                    "severity": "error",
                    "description": "This variable is never reassigned.",
                    "location": {
                        "path": {"file": "index.ts"},
                        "span": [12],
                    },
                }
            ],
        },
        tmp_path,
        "lint",
    )
    assert failing["status"] == "fail"
    assert len(failing["findings"]) == 1
    assert failing["findings"][0]["rule"] == "biome/lint/style/useConst"
