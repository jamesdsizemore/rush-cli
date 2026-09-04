"""Unit tests for strict Pydantic schemas and placeholder rejection."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from rush.tools.schemas import (
    IamAuditMetrics,
    LicenseMatrixMetrics,
    ProvenanceMetrics,
    StrictToolResult,
    validate_strict_result,
)


def test_provenance_metrics_accepts_valid_bounds() -> None:
    metrics = ProvenanceMetrics(
        survival_rate_30d=0.85,
        survival_rate_60d=0.72,
        survival_rate_90d=0.65,
        defect_correlation=-0.12,
        churn_rate=0.25,
    )
    assert metrics.survival_rate_30d == 0.85
    assert metrics.defect_correlation == -0.12


def test_provenance_metrics_rejects_string_placeholders() -> None:
    with pytest.raises(ValidationError):
        ProvenanceMetrics(
            survival_rate_30d="unknown",  # type: ignore[arg-type]
            survival_rate_60d=0.5,
            survival_rate_90d=0.5,
            defect_correlation=0.0,
            churn_rate=0.1,
        )


def test_provenance_metrics_rejects_out_of_bounds() -> None:
    with pytest.raises(ValidationError):
        ProvenanceMetrics(
            survival_rate_30d=1.5,  # > 1.0
            survival_rate_60d=0.5,
            survival_rate_90d=0.5,
            defect_correlation=0.0,
            churn_rate=0.1,
        )

    with pytest.raises(ValidationError):
        ProvenanceMetrics(
            survival_rate_30d=0.5,
            survival_rate_60d=0.5,
            survival_rate_90d=0.5,
            defect_correlation=-1.5,  # < -1.0
            churn_rate=0.1,
        )


def test_license_matrix_metrics_bounds() -> None:
    metrics = LicenseMatrixMetrics(
        compliance_score=1.0,
        packages_audited=10,
        incompatible_count=0,
        unresolved_count=0,
    )
    assert metrics.compliance_score == 1.0

    with pytest.raises(ValidationError):
        LicenseMatrixMetrics(
            compliance_score=1.1,  # > 1.0
            packages_audited=10,
            incompatible_count=0,
            unresolved_count=0,
        )


def test_iam_audit_metrics_bounds() -> None:
    metrics = IamAuditMetrics(
        risk_score=0.45,
        total_statements=5,
        wildcard_actions_count=1,
        privilege_escalation_paths=0,
    )
    assert metrics.risk_score == 0.45

    with pytest.raises(ValidationError):
        IamAuditMetrics(
            risk_score=-0.1,  # < 0.0
            total_statements=5,
            wildcard_actions_count=1,
            privilege_escalation_paths=0,
        )


def test_strict_tool_result_rejects_string_in_metrics() -> None:
    bad_payload = {
        "tool": "provenance_ai",
        "status": "ok",
        "duration_ms": 100,
        "summary": "analysis done",
        "findings": [],
        "metrics": {"survival_rate_30d": "unknown"},
    }
    with pytest.raises(ValidationError) as exc_info:
        StrictToolResult.model_validate(bad_payload)
    assert "Input should be a valid number" in str(exc_info.value)


def test_strict_tool_result_rejects_placeholder_in_metadata() -> None:
    bad_payload = {
        "tool": "provenance_ai",
        "status": "ok",
        "duration_ms": 100,
        "summary": "analysis done",
        "findings": [],
        "metadata": {"survival_states": {"30d": "unknown"}},
    }
    with pytest.raises(ValidationError) as exc_info:
        StrictToolResult.model_validate(bad_payload)
    assert "contains banned placeholder 'unknown'" in str(exc_info.value)


def test_validate_strict_result_success() -> None:
    good_payload = {
        "tool": "provenance_ai",
        "status": "ok",
        "duration_ms": 150,
        "summary": "computed real metrics",
        "findings": [],
        "metrics": {
            "survival_rate_30d": 0.9,
            "survival_rate_60d": 0.8,
            "survival_rate_90d": 0.7,
            "defect_correlation": 0.05,
            "churn_rate": 0.15,
        },
        "metadata": {"algorithm": "git-blame-line-survival"},
    }
    validated = validate_strict_result(good_payload, metric_schema=ProvenanceMetrics)
    assert validated.tool == "provenance_ai"
    assert validated.metrics is not None
    assert validated.metrics["survival_rate_30d"] == 0.9
