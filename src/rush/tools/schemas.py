"""Strict schema validation models for Rush tool results, metrics, and contracts.

Enforces:
- Hard numeric bounds (ge=0.0, le=1.0) on ratios, probabilities, and scores.
- Zero string placeholders ("unknown", "deferred") in metrics or computed fields.
- Runtime traceback / ValidationError if stubs are returned.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class StrictBaseModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class ProvenanceMetrics(StrictBaseModel):
    """Provenance AI metrics with exact numeric boundaries."""

    survival_rate_30d: float | None = Field(
        ..., ge=0.0, le=1.0, description="30-day line survival rate"
    )
    survival_rate_60d: float | None = Field(
        ..., ge=0.0, le=1.0, description="60-day line survival rate"
    )
    survival_rate_90d: float | None = Field(
        ..., ge=0.0, le=1.0, description="90-day line survival rate"
    )
    defect_correlation: float | None = Field(
        ..., ge=-1.0, le=1.0, description="Phi coefficient for observed fix linkage"
    )
    churn_rate: float | None = Field(
        ..., ge=0.0, le=1.0, description="30-day lost cohort fraction"
    )
    churn_rate_30d: float | None = Field(default=None, ge=0.0, le=1.0)
    churn_rate_60d: float | None = Field(default=None, ge=0.0, le=1.0)
    churn_rate_90d: float | None = Field(default=None, ge=0.0, le=1.0)
    total_commits: int = Field(default=0, ge=0, description="Total commits audited")
    ai_generated_count: int = Field(
        default=0, ge=0, description="AI generated commits count"
    )
    ai_assisted_count: int = Field(
        default=0, ge=0, description="AI assisted commits count"
    )
    human_count: int = Field(
        default=0, ge=0, description="Human authored commits count"
    )
    shallow_history: bool = Field(default=False, description="Shallow clone indicator")


class LicenseMatrixMetrics(StrictBaseModel):
    """License Matrix metrics with exact numeric boundaries."""

    compliance_score: float = Field(
        ..., ge=0.0, le=1.0, description="SPDX compliance ratio"
    )
    packages_audited: int = Field(..., ge=0, description="Total packages audited")
    incompatible_count: int = Field(
        ..., ge=0, description="Count of incompatible licenses"
    )
    unresolved_count: int = Field(
        ..., ge=0, description="Count of unresolved license expressions"
    )
    total_packages: int = Field(
        default=0, ge=0, description="Total packages discovered"
    )
    copyleft_violations_count: int = Field(
        default=0, ge=0, description="Total copyleft violations count"
    )


class IamAuditMetrics(StrictBaseModel):
    """IAM audit metrics with exact numeric boundaries."""

    risk_score: float = Field(
        ..., ge=0.0, le=1.0, description="Normalized IAM risk score"
    )
    total_statements: int = Field(
        ..., ge=0, description="Total policy statements parsed"
    )
    wildcard_actions_count: int = Field(
        ..., ge=0, description="Count of wildcard actions (*)"
    )
    privilege_escalation_paths: int = Field(
        ..., ge=0, description="Count of privilege escalation paths"
    )
    actions_count: int = Field(
        default=0, ge=0, description="Count of actions discovered"
    )
    files_scanned: int = Field(default=0, ge=0, description="Count of files scanned")


class FindingModel(StrictBaseModel):
    path: str
    line: int | None = None
    column: int | None = None
    message: str
    severity: Literal["error", "warn", "info"]
    rule_id: str | None = None


class StrictToolResult(StrictBaseModel):
    """Enforced ToolResult contract that rejects placeholder strings and unvalidated payloads."""

    tool: str
    engine: str | None = None
    engine_version: str | None = None
    status: Literal["ok", "warn", "fail", "error", "skipped"]
    duration_ms: int = Field(..., ge=0)
    summary: str
    findings: list[FindingModel] = Field(default_factory=list)
    raw: Any | None = None
    metrics: dict[str, float | int] | None = None
    metadata: dict[str, Any] | None = None

    @field_validator("metrics")
    @classmethod
    def validate_metrics_no_placeholders(
        cls, v: dict[str, float | int] | None
    ) -> dict[str, float | int] | None:
        if v is None:
            return v
        for k, val in v.items():
            if isinstance(val, str):
                raise TypeError(
                    f"Metric '{k}' cannot be a string placeholder '{val}'; must be numeric."
                )
        return v

    @field_validator("metadata")
    @classmethod
    def validate_metadata_no_placeholders(
        cls, v: dict[str, Any] | None
    ) -> dict[str, Any] | None:
        if v is None:
            return v
        banned = {"unknown", "deferred", "simulated", "placeholder"}

        def _check(obj: Any, path: str = "") -> None:
            if isinstance(obj, str) and obj.lower() in banned:
                raise ValueError(
                    f"Metadata field '{path}' contains banned placeholder '{obj}'."
                )
            elif isinstance(obj, dict):
                for sub_k, sub_v in obj.items():
                    _check(sub_v, f"{path}.{sub_k}" if path else sub_k)
            elif isinstance(obj, list):
                for i, item in enumerate(obj):
                    _check(item, f"{path}[{i}]")

        _check(v)
        return v


def validate_strict_result(
    result: dict[str, Any], metric_schema: type[StrictBaseModel] | None = None
) -> StrictToolResult:
    """Validates a tool result against StrictToolResult and optional tool-specific metric schema.

    Raises:
        pydantic.ValidationError: If bounds are violated, types mismatch, or placeholders are found.
    """
    validated = StrictToolResult.model_validate(result)
    if metric_schema and validated.metrics:
        metric_schema.model_validate(validated.metrics)
    return validated
