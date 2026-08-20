"""Phase 16 Cargo-mutants reference adapter fake-process matrix."""

from __future__ import annotations

import subprocess
from pathlib import Path

from rush.engines import cargo_mutants
from rush.engines.cargo_mutants import CargoMutantsEngine


def test_cargo_mutants_runs_isolated_argv(monkeypatch, tmp_path: Path) -> None:
    calls: list[list[str]] = []

    def fake_run(
        argv: list[str], **_kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        calls.append(argv)
        return subprocess.CompletedProcess(argv, 0, stdout="", stderr="")

    monkeypatch.setattr(
        cargo_mutants, "resolve_binary", lambda _binary: "C:/bin/cargo-mutants"
    )
    monkeypatch.setattr(cargo_mutants, "run_subprocess", fake_run)

    raw = CargoMutantsEngine().run(tmp_path, [], cwd=tmp_path)

    assert raw["exit_code"] == 0
    assert calls == [
        [
            "C:/bin/cargo-mutants",
            "mutants",
            "--json",
            "--no-shuffle",
        ]
    ]


def test_cargo_mutants_normalizes_clean_and_findings(
    monkeypatch, tmp_path: Path
) -> None:
    engine = CargoMutantsEngine()
    monkeypatch.setattr(CargoMutantsEngine, "version", lambda _self: "24.7.0")

    clean = engine.normalize({"exit_code": 0, "findings": []}, tmp_path, "mutation")
    assert clean["status"] == "ok"
    assert clean["findings"] == []

    failing = engine.normalize(
        {
            "exit_code": 0,
            "findings": [
                {
                    "filename": "src/parser.rs",
                    "line": 45,
                    "function": "parse_header",
                    "genre": "BinaryOperator",
                    "replacement": "a != b",
                    "summary": "MISSED",
                }
            ],
        },
        tmp_path,
        "mutation",
    )
    assert failing["status"] == "warn"
    assert len(failing["findings"]) == 1
    assert "cargo-mutants/BinaryOperator" in failing["findings"][0]["rule"]
