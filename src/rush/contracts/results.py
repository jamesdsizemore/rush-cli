"""Canonical ToolResultV1 and FindingV1 contracts, validation, and serialization."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Literal

from rush.safety.redactor import sanitize_value

FindingSeverity = Literal["info", "warning", "error"]
ToolStatus = Literal["ok", "warn", "fail", "error", "skipped"]

VALID_SEVERITIES: frozenset[str] = frozenset({"info", "warning", "error"})
VALID_STATUSES: frozenset[str] = frozenset({"ok", "warn", "fail", "error", "skipped"})

TOOL_RESULT_KEYS: frozenset[str] = frozenset(
    {
        "schema_version",
        "tool",
        "engine",
        "engine_version",
        "status",
        "duration_ms",
        "summary",
        "findings",
        "raw",
        "extensions",
    }
)

FINDING_KEYS: frozenset[str] = frozenset(
    {
        "path",
        "line",
        "column",
        "rule_id",
        "severity",
        "message",
        "fingerprint",
        "rule",
        "fix",
        "remediation",
        "evidence",
        "provenance",
        "freshness",
        "patch",
        "suggested_fix",
        "extensions",
    }
)


@dataclass(frozen=True)
class ValidationErrorV1(Exception):
    """Structured validation error indicating an exact contract schema violation."""

    code: str
    message: str
    path: str
    invalid_value: Any = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "error": "validation_error",
            "code": self.code,
            "message": self.message,
            "path": self.path,
            "invalid_value": (
                self.invalid_value
                if isinstance(self.invalid_value, (str, int, float, bool, type(None)))
                else str(self.invalid_value)
            ),
        }

    def __str__(self) -> str:
        return f"[{self.code}] at '{self.path}': {self.message}"


def _ensure_json_safe(val: Any, path: str) -> None:
    """Recursively check that a value consists solely of JSON-safe data types."""
    if val is None or isinstance(val, (bool, int, float, str)):
        return
    if isinstance(val, dict):
        for k, v in val.items():
            if not isinstance(k, str):
                raise ValidationErrorV1(
                    code="NON_JSON_SAFE_VALUE",
                    message=f"Dictionary key at '{path}' is not a string",
                    path=path,
                    invalid_value=k,
                )
            sub_path = f"{path}.{k}" if path else k
            _ensure_json_safe(v, sub_path)
        return
    if isinstance(val, (list, tuple)):
        for idx, item in enumerate(val):
            _ensure_json_safe(item, f"{path}[{idx}]")
        return
    raise ValidationErrorV1(
        code="NON_JSON_SAFE_VALUE",
        message=f"Value at '{path}' of type '{type(val).__name__}' is not JSON safe",
        path=path,
        invalid_value=val,
    )


@dataclass(frozen=True)
class FindingV1:
    path: str
    line: int
    column: int
    rule_id: str
    severity: FindingSeverity
    message: str
    fingerprint: str
    rule: str | None = None
    fix: dict[str, Any] | None = None
    remediation: dict[str, Any] | str | None = None
    evidence: dict[str, Any] | str | None = None
    provenance: str | None = None
    freshness: str | None = None
    patch: str | None = None
    suggested_fix: str | None = None
    extensions: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "line": self.line,
            "column": self.column,
            "rule_id": self.rule_id,
            "severity": self.severity,
            "message": self.message,
            "fingerprint": self.fingerprint,
            "rule": self.rule,
            "fix": self.fix,
            "remediation": self.remediation,
            "evidence": self.evidence,
            "provenance": self.provenance,
            "freshness": self.freshness,
            "patch": self.patch,
            "suggested_fix": self.suggested_fix,
            "extensions": self.extensions,
        }

    def __getitem__(self, item: str) -> Any:
        try:
            return getattr(self, item)
        except AttributeError:
            raise KeyError(item) from None

    def get(self, item: str, default: Any = None) -> Any:
        return getattr(self, item, default)


@dataclass(frozen=True)
class ToolResultV1:
    schema_version: Literal["1.0.0"]
    tool: str
    engine: str | None
    engine_version: str | None
    status: ToolStatus
    duration_ms: int
    summary: str
    findings: list[FindingV1]
    raw: Any | None = None
    extensions: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "tool": self.tool,
            "engine": self.engine,
            "engine_version": self.engine_version,
            "status": self.status,
            "duration_ms": self.duration_ms,
            "summary": self.summary,
            "findings": [f.to_dict() for f in self.findings],
            "raw": self.raw,
            "extensions": self.extensions,
        }

    def __getitem__(self, item: str) -> Any:
        try:
            return getattr(self, item)
        except AttributeError:
            raise KeyError(item) from None

    def get(self, item: str, default: Any = None) -> Any:
        return getattr(self, item, default)


def validate_finding(data: Any, path_prefix: str = "findings") -> FindingV1:
    """Validate raw mapping or object against FindingV1 contract."""
    if isinstance(data, FindingV1):
        raw_dict = data.to_dict()
    elif isinstance(data, dict):
        raw_dict = data
    else:
        raise ValidationErrorV1(
            code="INVALID_TYPE",
            message=f"Finding must be a dictionary or FindingV1, got {type(data).__name__}",
            path=path_prefix,
            invalid_value=data,
        )

    # Check for unknown top-level keys
    for k in raw_dict:
        if k not in FINDING_KEYS:
            sub_path = f"{path_prefix}.{k}" if path_prefix else k
            raise ValidationErrorV1(
                code="UNKNOWN_TOP_LEVEL_KEY",
                message=f"Unknown key '{k}' in finding",
                path=sub_path,
                invalid_value=k,
            )

    # Required fields check
    for req_field in (
        "path",
        "line",
        "column",
        "rule_id",
        "severity",
        "message",
        "fingerprint",
    ):
        if req_field not in raw_dict:
            sub_path = f"{path_prefix}.{req_field}" if path_prefix else req_field
            raise ValidationErrorV1(
                code="MISSING_REQUIRED_FIELD",
                message=f"Missing required finding field '{req_field}'",
                path=sub_path,
            )

    # Path check
    path_val = raw_dict["path"]
    if not isinstance(path_val, str):
        raise ValidationErrorV1(
            code="INVALID_TYPE",
            message=f"Finding path must be a string, got {type(path_val).__name__}",
            path=f"{path_prefix}.path",
            invalid_value=path_val,
        )

    # Line & column checks
    line_val = raw_dict["line"]
    if not isinstance(line_val, int) or isinstance(line_val, bool) or line_val < 0:
        raise ValidationErrorV1(
            code="INVALID_TYPE",
            message=f"Finding line must be a non-negative integer, got {line_val!r}",
            path=f"{path_prefix}.line",
            invalid_value=line_val,
        )

    col_val = raw_dict["column"]
    if not isinstance(col_val, int) or isinstance(col_val, bool) or col_val < 0:
        raise ValidationErrorV1(
            code="INVALID_TYPE",
            message=f"Finding column must be a non-negative integer, got {col_val!r}",
            path=f"{path_prefix}.column",
            invalid_value=col_val,
        )

    # Rule_id check
    rule_id_val = raw_dict["rule_id"]
    if not isinstance(rule_id_val, str) or not rule_id_val.strip():
        raise ValidationErrorV1(
            code="INVALID_TYPE",
            message="Finding rule_id must be a non-empty string",
            path=f"{path_prefix}.rule_id",
            invalid_value=rule_id_val,
        )

    # Severity check
    sev_val = raw_dict["severity"]
    if sev_val not in VALID_SEVERITIES:
        raise ValidationErrorV1(
            code="INVALID_SEVERITY",
            message=f"Finding severity '{sev_val}' is invalid; must be one of {sorted(VALID_SEVERITIES)}",
            path=f"{path_prefix}.severity",
            invalid_value=sev_val,
        )

    # Message check
    msg_val = raw_dict["message"]
    if not isinstance(msg_val, str):
        raise ValidationErrorV1(
            code="INVALID_TYPE",
            message=f"Finding message must be a string, got {type(msg_val).__name__}",
            path=f"{path_prefix}.message",
            invalid_value=msg_val,
        )

    # Fingerprint check
    fp_val = raw_dict["fingerprint"]
    if not isinstance(fp_val, str):
        raise ValidationErrorV1(
            code="INVALID_TYPE",
            message=f"Finding fingerprint must be a string, got {type(fp_val).__name__}",
            path=f"{path_prefix}.fingerprint",
            invalid_value=fp_val,
        )

    # Extensions check
    ext_val = raw_dict.get("extensions")
    if ext_val is not None:
        if not isinstance(ext_val, dict):
            raise ValidationErrorV1(
                code="INVALID_TYPE",
                message=f"Finding extensions must be a dictionary, got {type(ext_val).__name__}",
                path=f"{path_prefix}.extensions",
                invalid_value=ext_val,
            )
        _ensure_json_safe(ext_val, f"{path_prefix}.extensions")
    else:
        ext_val = {}

    return FindingV1(
        path=path_val,
        line=line_val,
        column=col_val,
        rule_id=rule_id_val,
        severity=sev_val,
        message=msg_val,
        fingerprint=fp_val,
        rule=raw_dict.get("rule"),
        fix=raw_dict.get("fix"),
        remediation=raw_dict.get("remediation"),
        evidence=raw_dict.get("evidence"),
        provenance=raw_dict.get("provenance"),
        freshness=raw_dict.get("freshness"),
        patch=raw_dict.get("patch"),
        suggested_fix=raw_dict.get("suggested_fix"),
        extensions=ext_val,
    )


def validate_tool_result(data: Any) -> ToolResultV1:
    """Validate raw mapping or object against ToolResultV1 contract."""
    if isinstance(data, ToolResultV1):
        raw_dict = data.to_dict()
    elif isinstance(data, dict):
        raw_dict = data
    else:
        raise ValidationErrorV1(
            code="INVALID_TYPE",
            message=f"ToolResult must be a dictionary or ToolResultV1, got {type(data).__name__}",
            path="",
            invalid_value=data,
        )

    # Check for unknown top-level keys
    for k in raw_dict:
        if k not in TOOL_RESULT_KEYS:
            raise ValidationErrorV1(
                code="UNKNOWN_TOP_LEVEL_KEY",
                message=f"Unknown key '{k}' in ToolResult",
                path=k,
                invalid_value=k,
            )

    # Required fields check
    for req_field in (
        "schema_version",
        "tool",
        "status",
        "duration_ms",
        "summary",
        "findings",
    ):
        if req_field not in raw_dict:
            raise ValidationErrorV1(
                code="MISSING_REQUIRED_FIELD",
                message=f"Missing required ToolResult field '{req_field}'",
                path=req_field,
            )

    # Schema version check
    sv = raw_dict["schema_version"]
    if sv != "1.0.0":
        raise ValidationErrorV1(
            code="INVALID_SCHEMA_VERSION",
            message=f"schema_version must be '1.0.0', got '{sv}'",
            path="schema_version",
            invalid_value=sv,
        )

    # Tool check
    tool_val = raw_dict["tool"]
    if not isinstance(tool_val, str) or not tool_val.strip():
        raise ValidationErrorV1(
            code="INVALID_TYPE",
            message="ToolResult tool must be a non-empty string",
            path="tool",
            invalid_value=tool_val,
        )

    # Status check
    status_val = raw_dict["status"]
    if status_val not in VALID_STATUSES:
        raise ValidationErrorV1(
            code="INVALID_STATUS",
            message=f"ToolResult status '{status_val}' is invalid; must be one of {sorted(VALID_STATUSES)}",
            path="status",
            invalid_value=status_val,
        )

    # Duration check
    dur_val = raw_dict["duration_ms"]
    if not isinstance(dur_val, int) or isinstance(dur_val, bool) or dur_val < 0:
        raise ValidationErrorV1(
            code="INVALID_TYPE",
            message=f"ToolResult duration_ms must be a non-negative integer, got {dur_val!r}",
            path="duration_ms",
            invalid_value=dur_val,
        )

    # Summary check
    summary_val = raw_dict["summary"]
    if not isinstance(summary_val, str):
        raise ValidationErrorV1(
            code="INVALID_TYPE",
            message=f"ToolResult summary must be a string, got {type(summary_val).__name__}",
            path="summary",
            invalid_value=summary_val,
        )

    # Findings check
    findings_val = raw_dict["findings"]
    if not isinstance(findings_val, list):
        raise ValidationErrorV1(
            code="INVALID_TYPE",
            message=f"ToolResult findings must be a list, got {type(findings_val).__name__}",
            path="findings",
            invalid_value=findings_val,
        )

    validated_findings: list[FindingV1] = []
    for idx, raw_f in enumerate(findings_val):
        validated_findings.append(
            validate_finding(raw_f, path_prefix=f"findings[{idx}]")
        )

    # Extensions check
    ext_val = raw_dict.get("extensions")
    if ext_val is not None:
        if not isinstance(ext_val, dict):
            raise ValidationErrorV1(
                code="INVALID_TYPE",
                message=f"ToolResult extensions must be a dictionary, got {type(ext_val).__name__}",
                path="extensions",
                invalid_value=ext_val,
            )
        _ensure_json_safe(ext_val, "extensions")
    else:
        ext_val = {}

    # Raw check
    raw_val = raw_dict.get("raw")
    if raw_val is not None:
        _ensure_json_safe(raw_val, "raw")

    return ToolResultV1(
        schema_version="1.0.0",
        tool=tool_val,
        engine=raw_dict.get("engine"),
        engine_version=raw_dict.get("engine_version"),
        status=status_val,
        duration_ms=dur_val,
        summary=summary_val,
        findings=validated_findings,
        raw=raw_val,
        extensions=ext_val,
    )


def serialize_tool_result(result: ToolResultV1 | dict[str, Any]) -> str:
    """Sanitize, validate, and serialize ToolResultV1 to byte-deterministic JSON string.

    Applies Phase 53 sanitization, then strict V1 validation, then deterministic
    sorted-key JSON encoding with compact separators.
    """
    as_dict: dict[str, Any]
    if isinstance(result, ToolResultV1):
        as_dict = result.to_dict()
    elif isinstance(result, dict):
        as_dict = result
    else:
        raise ValidationErrorV1(
            code="INVALID_TYPE",
            message=f"Expected ToolResultV1 or dict, got {type(result).__name__}",
            path="",
            invalid_value=result,
        )

    # 1. Sanitize via Phase 53 kernel to guarantee secrets redaction
    sanitized = sanitize_value(as_dict).value

    # 2. Validate against ToolResultV1 schema
    validated = validate_tool_result(sanitized)

    # 3. Serialize deterministically
    return json.dumps(
        validated.to_dict(),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )


LEGACY_SEVERITY_MAP: dict[str, FindingSeverity] = {
    "info": "info",
    "warn": "warning",
    "warning": "warning",
    "error": "error",
    "fail": "error",
}


def adapt_legacy_finding(legacy: dict[str, Any]) -> FindingV1:
    """Convert a legacy Finding dictionary into a canonical FindingV1 instance."""
    if not isinstance(legacy, dict):
        raise ValidationErrorV1(
            code="INVALID_TYPE",
            message=f"Expected legacy finding dict, got {type(legacy).__name__}",
            path="findings",
            invalid_value=legacy,
        )

    sev_raw = legacy.get("severity")
    if not isinstance(sev_raw, str) or sev_raw not in LEGACY_SEVERITY_MAP:
        raise ValidationErrorV1(
            code="INVALID_SEVERITY",
            message=f"Legacy finding severity {sev_raw!r} cannot be adapted; must be one of {sorted(LEGACY_SEVERITY_MAP)}",
            path="severity",
            invalid_value=sev_raw,
        )
    canonical_severity = LEGACY_SEVERITY_MAP[sev_raw]

    path = str(legacy.get("path") or legacy.get("filename") or "")
    line = legacy.get("line")
    line_val = (
        int(line)
        if isinstance(line, (int, float)) and not isinstance(line, bool) and line >= 0
        else 0
    )
    col = legacy.get("column") or legacy.get("col")
    col_val = (
        int(col)
        if isinstance(col, (int, float)) and not isinstance(col, bool) and col >= 0
        else 0
    )
    rule_id = str(legacy.get("rule_id") or legacy.get("rule") or "UNKNOWN")
    message = str(legacy.get("message") or "")

    fp = legacy.get("fingerprint")
    if (
        isinstance(fp, str)
        and len(fp) == 64
        and all(c in "0123456789abcdef" for c in fp.lower())
    ):
        fingerprint = fp.lower()
    else:
        seed = f"{path}:{line_val}:{col_val}:{rule_id}:{canonical_severity}:{message}".encode()
        fingerprint = hashlib.sha256(seed).hexdigest()

    extensions: dict[str, Any] = dict(legacy.get("extensions") or {})
    known_keys = FINDING_KEYS
    for k, v in legacy.items():
        if k not in known_keys and k not in ("filename", "col", "rule_id", "severity"):
            extensions[k] = v

    return FindingV1(
        path=path,
        line=line_val,
        column=col_val,
        rule_id=rule_id,
        severity=canonical_severity,
        message=message,
        fingerprint=fingerprint,
        rule=legacy.get("rule"),
        fix=legacy.get("fix"),
        remediation=legacy.get("remediation"),
        evidence=legacy.get("evidence"),
        provenance=legacy.get("provenance"),
        freshness=legacy.get("freshness"),
        patch=legacy.get("patch"),
        suggested_fix=legacy.get("suggested_fix"),
        extensions=extensions,
    )


def adapt_legacy_tool_result(legacy: dict[str, Any]) -> ToolResultV1:
    """Convert a legacy ToolResult dictionary into a canonical ToolResultV1 instance."""
    if not isinstance(legacy, dict):
        raise ValidationErrorV1(
            code="INVALID_TYPE",
            message=f"Expected legacy tool result dict, got {type(legacy).__name__}",
            path="",
            invalid_value=legacy,
        )

    tool_val = str(legacy.get("tool") or "")
    if not tool_val:
        raise ValidationErrorV1(
            code="MISSING_REQUIRED_FIELD",
            message="Missing required field 'tool'",
            path="tool",
        )

    status_val = legacy.get("status")
    if status_val not in VALID_STATUSES:
        raise ValidationErrorV1(
            code="INVALID_STATUS",
            message=f"Status '{status_val}' is invalid; must be one of {sorted(VALID_STATUSES)}",
            path="status",
            invalid_value=status_val,
        )

    dur = legacy.get("duration_ms", 0)
    dur_val = (
        int(dur)
        if isinstance(dur, (int, float)) and not isinstance(dur, bool) and dur >= 0
        else 0
    )
    summary_val = str(legacy.get("summary") or "")

    raw_findings = legacy.get("findings") or []
    if not isinstance(raw_findings, list):
        raise ValidationErrorV1(
            code="INVALID_TYPE",
            message=f"Findings must be a list, got {type(raw_findings).__name__}",
            path="findings",
            invalid_value=raw_findings,
        )
    findings = [adapt_legacy_finding(f) for f in raw_findings]

    extensions: dict[str, Any] = dict(legacy.get("extensions") or {})
    known_keys = TOOL_RESULT_KEYS
    for k, v in legacy.items():
        if k not in known_keys and k not in ("schema_version",):
            extensions[k] = v

    return ToolResultV1(
        schema_version="1.0.0",
        tool=tool_val,
        engine=legacy.get("engine"),
        engine_version=legacy.get("engine_version"),
        status=status_val,
        duration_ms=dur_val,
        summary=summary_val,
        findings=findings,
        raw=legacy.get("raw"),
        extensions=extensions,
    )
