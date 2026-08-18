"""Tests for tools/base.py — TypedDict shapes + ToolFn ABC contract."""

from __future__ import annotations

from rush.tools import ALL_TOOLS
from rush.tools.base import (
    Severity,
    ToolName,
    ToolResult,
    ToolStatus,
)
from rush.tools.common import (
    elapsed_ms,
    engine_on_path,
    error_result,
    exit_code_for,
    normalize_findings,
    now_ms,
    resolve_binary,
    skipped_result,
)


def test_tool_status_literal():
    assert ToolStatus.__args__ == ("ok", "warn", "fail", "error", "skipped")


def test_tool_name_is_extensible_string_identifier():
    assert ToolName is str


def test_severity_literal():
    assert Severity.__args__ == ("info", "warn", "error")


def test_all_tools_have_unique_names():
    names = [t.name for t in ALL_TOOLS]
    assert len(names) == len(set(names)), f"duplicate tool names: {names}"


def test_each_tool_has_mcp_description():
    for t in ALL_TOOLS:
        assert isinstance(t.mcp_description, str)
        assert len(t.mcp_description) >= 20
        assert len(t.mcp_description) < 200


def test_exit_code_map():
    assert (
        exit_code_for(
            ToolResult(status="ok", tool="x", summary="", findings=[], duration_ms=0)
        )
        == 0
    )
    assert (
        exit_code_for(
            ToolResult(
                status="skipped", tool="x", summary="", findings=[], duration_ms=0
            )
        )
        == 0
    )
    assert (
        exit_code_for(
            ToolResult(status="warn", tool="x", summary="", findings=[], duration_ms=0)
        )
        == 1
    )
    assert (
        exit_code_for(
            ToolResult(status="fail", tool="x", summary="", findings=[], duration_ms=0)
        )
        == 1
    )
    assert (
        exit_code_for(
            ToolResult(status="error", tool="x", summary="", findings=[], duration_ms=0)
        )
        == 2
    )


def test_skipped_result_shape():
    r = skipped_result("lint", "ruff", "ruff not on PATH")
    assert r["tool"] == "lint"
    assert r["engine"] == "ruff"
    assert r["status"] == "skipped"
    assert r["duration_ms"] == 0
    assert r["findings"] == []
    assert "not on PATH" in r["summary"]


def test_error_result_shape():
    r = error_result("lint", "ruff", "engine crashed", duration_ms=42)
    assert r["status"] == "error"
    assert r["duration_ms"] == 42


def test_normalize_findings_filters_invalid():
    """Test data uses flat 'line' field; ruff-style nested 'location.row' is
    a separate code path tested in engines."""
    raw = [
        {"filename": "a.py", "message": "ok", "line": 1, "column": 1, "rule": "E501"},
        {
            "filename": "b.py",
            "message": "",
            "line": 1,
            "column": 1,
            "rule": "E502",
        },  # no message → skip
        {"path": "c.py", "message": "no location"},
    ]
    out = normalize_findings(raw)
    assert len(out) == 2  # the empty-message one is dropped
    assert out[0]["path"] == "a.py"
    assert out[0]["line"] == 1
    assert out[0]["rule"] == "E501"
    assert out[0]["severity"] == "warn"  # default


def test_normalize_findings_accepts_nested_location():
    """ruff's JSON output uses location.row instead of flat line."""
    raw = [
        {
            "filename": "a.py",
            "message": "ok",
            "location": {"row": 42, "column": 8},
            "code": "E501",
        },
    ]
    out = normalize_findings(raw)
    assert out[0]["line"] == 42
    assert out[0]["rule"] == "E501"


def test_normalize_findings_severity_fallback():
    raw = [{"filename": "x.py", "message": "hi", "severity": "bogus"}]
    out = normalize_findings(raw)
    assert out[0]["severity"] == "warn"  # falls back


def test_now_ms_and_elapsed_ms():
    start = now_ms()
    e = elapsed_ms(start)
    assert e >= 0
    assert elapsed_ms(0) == 0  # sentinel
    assert elapsed_ms(-1) == 0  # sentinel


def test_engine_on_path_uses_venv_scripts():
    import os

    """ruff is installed in the project venv — should be findable even when
    PATH doesn't include .venv/Scripts/."""
    from rush.tools.common import _venv_scripts_dir

    # If ruff is in the project venv, engine_on_path should find it.
    scripts = _venv_scripts_dir()
    if (
        scripts is not None
        and (scripts / ("ruff.exe" if os.name == "nt" else "ruff")).exists()
    ):
        assert engine_on_path("ruff")


def test_resolve_binary_returns_path_when_found():
    import os

    from rush.tools.common import _venv_scripts_dir

    if (_venv_scripts_dir() / ("ruff.exe" if os.name == "nt" else "ruff")).exists():
        path = resolve_binary("ruff")
        assert path is not None
        assert path.endswith(("ruff", "ruff.exe"))


def test_resolve_binary_returns_none_for_missing():
    assert resolve_binary("definitely-not-a-real-binary-xyz123") is None
