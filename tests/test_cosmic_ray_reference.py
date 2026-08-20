"""Phase 16 Cosmic Ray reference adapter fake-process matrix."""

from __future__ import annotations

import subprocess
from pathlib import Path

from rush.engines import cosmic_ray
from rush.engines.cosmic_ray import CosmicRayEngine


def test_cosmic_ray_runs_isolated_argv(monkeypatch, tmp_path: Path) -> None:
    calls: list[list[str]] = []

    def fake_run(
        argv: list[str], **_kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        calls.append(argv)
        return subprocess.CompletedProcess(argv, 0, stdout="", stderr="")

    monkeypatch.setattr(
        cosmic_ray, "resolve_binary", lambda _binary: "C:/bin/cosmic-ray"
    )
    monkeypatch.setattr(cosmic_ray, "run_subprocess", fake_run)

    raw = CosmicRayEngine().run(tmp_path, [], cwd=tmp_path)

    assert raw["exit_code"] == 0
    assert calls == [
        [
            "C:/bin/cosmic-ray",
            "dump",
            "cosmic-ray.sqlite",
        ]
    ]


def test_cosmic_ray_normalizes_clean_and_findings(monkeypatch, tmp_path: Path) -> None:
    engine = CosmicRayEngine()
    monkeypatch.setattr(CosmicRayEngine, "version", lambda _self: "8.3.0")

    clean = engine.normalize({"exit_code": 0, "findings": []}, tmp_path, "mutation")
    assert clean["status"] == "ok"
    assert clean["findings"] == []

    failing = engine.normalize(
        {
            "exit_code": 0,
            "findings": [
                {
                    "module_path": "rush/core.py",
                    "line_number": 42,
                    "operator_name": "core/ReplaceComparisonWithFalse",
                    "description": "replaced comparison with False",
                }
            ],
        },
        tmp_path,
        "mutation",
    )
    assert failing["status"] == "warn"
    assert len(failing["findings"]) == 1
    assert (
        "cosmic-ray/core/ReplaceComparisonWithFalse" in failing["findings"][0]["rule"]
    )
