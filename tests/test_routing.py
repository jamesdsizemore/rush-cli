"""Shared v0.2 routing and aggregation contracts."""

from __future__ import annotations

from pathlib import Path

from rush.tools.routing import aggregate_results, build_finding_baseline, collect_files


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


def test_aggregate_results_preserves_child_provenance_without_caller_order() -> None:
    security_finding = {
        "path": "src/auth.py",
        "line": 8,
        "rule": "GITLEAKS-001",
        "message": "secret-like value",
    }
    security = {
        "tool": "secrets",
        "engine": "gitleaks",
        "engine_version": "8.30.1",
        "status": "fail",
        "duration_ms": 3,
        "summary": "secrets: finding",
        "findings": [security_finding],
        "raw": None,
    }
    quality = _result(
        "ruff",
        "warn",
        [{"path": "src/auth.py", "line": 2, "rule": "F401", "message": "unused"}],
    )

    forward = aggregate_results("review", [security, quality])
    reverse = aggregate_results("review", [quality, security])

    assert forward == reverse
    assert forward["engine"] == "ruff+gitleaks"
    assert [item["provenance"] for item in forward["findings"]] == [
        "lint/ruff",
        "secrets/gitleaks",
    ]
    assert "provenance" not in security_finding


def test_review_aggregation_deduplicates_fingerprint_and_retains_provenance() -> None:
    duplicate = {
        "path": "src/auth.py",
        "line": 8,
        "column": 1,
        "rule": "shared-rule",
        "severity": "warn",
        "message": "shared issue",
        "fingerprint": "shared",
    }

    result = aggregate_results(
        "review",
        [
            _result("engine-a", "warn", [duplicate]),
            _result("engine-b", "warn", [duplicate]),
        ],
    )

    assert len(result["findings"]) == 1
    assert result["findings"][0]["provenance"] == "lint/engine-a;lint/engine-b"


def test_review_aggregation_assigns_a_deterministic_fingerprint_when_missing() -> None:
    finding = {
        "path": "src/auth.py",
        "line": 8,
        "column": 1,
        "rule": "shared-rule",
        "severity": "warn",
        "message": "shared issue",
    }

    forward = aggregate_results("review", [_result("engine-a", "warn", [finding])])
    reverse = aggregate_results("review", [_result("engine-a", "warn", [finding])])

    assert (
        forward["findings"][0]["fingerprint"] == reverse["findings"][0]["fingerprint"]
    )
    assert len(forward["findings"][0]["fingerprint"]) == 64


def test_review_aggregation_records_partial_child_evidence_and_baseline_freshness() -> (
    None
):
    finding = {
        "path": "src/auth.py",
        "line": 8,
        "rule": "shared-rule",
        "severity": "warn",
        "message": "shared issue",
    }
    initial = aggregate_results("review", [_result("engine-a", "warn", [finding])])
    baseline = build_finding_baseline(initial["findings"])
    result = aggregate_results(
        "review",
        [
            _result("engine-a", "warn", [finding]),
            _result("engine-b", "skipped", []),
        ],
        baseline_fingerprints=baseline,
    )

    assert result["findings"][0]["freshness"] == "existing"
    assert result["metadata"] == {
        "aggregation": {
            "mode": "serial",
            "partial": True,
            "children": [
                {"tool": "lint", "engine": "engine-a", "status": "warn"},
                {"tool": "lint", "engine": "engine-b", "status": "skipped"},
            ],
        },
        "baseline": "provided",
    }


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
