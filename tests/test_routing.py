"""Shared v0.2 routing and aggregation contracts."""

from __future__ import annotations

from pathlib import Path

from rush.tools.routing import aggregate_results, collect_files


def _result(
    engine: str,
    status: str,
    findings: list[dict],
    *,
    metrics: dict | None = None,
    artifacts: list[str] | None = None,
) -> dict:
    return {
        "tool": "lint",
        "engine": engine,
        "engine_version": "1.0",
        "status": status,
        "duration_ms": 5,
        "summary": f"{engine}: {status}",
        "findings": findings,
        "metrics": metrics,
        "artifacts": artifacts,
        "raw": None,
    }


def test_aggregate_results_uses_worst_status_and_stable_finding_order() -> None:
    result = aggregate_results(
        "lint",
        [
            _result(
                "eslint",
                "warn",
                [{"path": "z.ts", "line": 2, "rule": "x", "message": "later"}],
            ),
            _result(
                "ruff",
                "fail",
                [{"path": "a.py", "line": 1, "rule": "F401", "message": "first"}],
            ),
        ],
    )

    assert result["status"] == "fail"
    assert result["engine"] == "eslint+ruff"
    assert [finding["path"] for finding in result["findings"]] == ["a.py", "z.ts"]


def test_aggregate_results_merges_metrics_and_deduplicates_artifacts() -> None:
    result = aggregate_results(
        "coverage",
        [
            _result(
                "coverage",
                "ok",
                [],
                metrics={"line_percent": 84.2},
                artifacts=["coverage.xml"],
            ),
            _result(
                "vitest",
                "ok",
                [],
                metrics={"branch_percent": 76.0},
                artifacts=["coverage.xml", "coverage/lcov.info"],
            ),
        ],
    )

    assert result["metrics"] == {"line_percent": 84.2, "branch_percent": 76.0}
    assert result["artifacts"] == ["coverage.xml", "coverage/lcov.info"]


def test_collect_files_sorts_supported_sources_and_ignores_generated_paths(
    tmp_path: Path,
) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "z.ts").write_text("export {};\n")
    (tmp_path / "src" / "a.py").write_text("pass\n")
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "node_modules" / "ignored.ts").write_text("export {};\n")
    (tmp_path / ".cache").mkdir()
    (tmp_path / ".cache" / "ignored.py").write_text("pass\n")

    files = collect_files(tmp_path, {"py", "ts"})

    assert [file.relative_to(tmp_path).as_posix() for file in files] == [
        "src/a.py",
        "src/z.ts",
    ]
