"""Black-box contracts for the packaged benchmark CLI surface."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from click.testing import CliRunner

from rush.cli import cli


def test_benchmark_group_and_run_are_registered() -> None:
    result = CliRunner().invoke(cli, ["benchmark", "run", "--help"])

    assert result.exit_code == 0
    assert "--local-runtime-executable" in result.output
    assert "--allow-model-download" in result.output


def test_benchmark_run_forwards_explicit_execution_arguments(
    tmp_path: Path, monkeypatch
) -> None:
    captured: list[str] = []

    def fake_main(argv: list[str]) -> int:
        captured.extend(argv)
        return 0

    monkeypatch.setattr("scripts.benchmarks.run.main", fake_main)
    result = CliRunner().invoke(
        cli,
        [
            "benchmark",
            "run",
            "--scenario",
            "local-granite-278m-c0",
            "--output",
            str(tmp_path / "results"),
            "--model-cache",
            str(tmp_path / "cache"),
            "--allow-model-download",
            "granite-278m-embedding",
            "--allow-model-download",
            "bge-small-en-v1.5",
            "--local-runtime-executable",
            str(tmp_path / "onnxruntime_perf_test.exe"),
            "--foreground",
        ],
    )

    assert result.exit_code == 0
    assert captured == [
        "--output",
        str(tmp_path / "results"),
        "--model-cache",
        str(tmp_path / "cache"),
        "--scenario",
        "local-granite-278m-c0",
        "--allow-model-download",
        "granite-278m-embedding",
        "--allow-model-download",
        "bge-small-en-v1.5",
        "--local-runtime-executable",
        str(tmp_path / "onnxruntime_perf_test.exe"),
    ]


def test_benchmark_status_reads_durable_result_artifacts(tmp_path: Path) -> None:
    (tmp_path / "local.json").write_text(
        json.dumps(
            {
                "scenario_id": "local-granite-278m-c0",
                "outcome": "pass",
                "duration_ms": 42,
            }
        ),
        encoding="utf-8",
    )

    result = CliRunner().invoke(cli, ["benchmark", "status", "--output", str(tmp_path)])

    assert result.exit_code == 0
    assert result.output == "local-granite-278m-c0: pass (42ms)\n"


def test_installed_rush_launcher_runs_benchmark_outside_repository(
    tmp_path: Path,
) -> None:
    launcher = Path(sys.executable).with_name("rush.exe" if os.name == "nt" else "rush")
    assert launcher.is_file(), "the installed CLI launcher is required"
    output = tmp_path / "results"
    cache = tmp_path / "model-cache"

    result = subprocess.run(
        [
            str(launcher),
            "benchmark",
            "run",
            "--foreground",
            "--scenario",
            "local-granite-278m-c0",
            "--output",
            str(output),
            "--model-cache",
            str(cache),
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "local-granite-278m-c0" in result.stdout
    assert (output / "local-granite-278m-c0.json").is_file()
