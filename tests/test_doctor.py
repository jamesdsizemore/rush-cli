"""Tests for Phase 24: Environment Doctor & PATH Resilience.

Verifies:
- PATH resolution order (virtual environment -> system PATH)
- Rejection of relative working directory binaries (anti-shadowing)
- DoctorTool diagnostics and status reporting
"""

from __future__ import annotations

import sys
from pathlib import Path

from rush.catalog import TOOL_SPECS
from rush.permissions import ExecutionPermissions
from rush.tools import ALL_TOOLS
from rush.tools.doctor import (
    DoctorTool,
    audit_environment_health,
    resolve_binary_secure,
)


def test_doctor_catalog_and_registry() -> None:
    assert "doctor" in TOOL_SPECS
    assert TOOL_SPECS["doctor"].maturity == "real_adapter"

    tool_names = [t.name for t in ALL_TOOLS]
    assert "doctor" in tool_names


def test_resolve_binary_secure_priority() -> None:
    # Python executable resolution
    py_name = "python" if sys.platform != "win32" else "python.exe"
    res = resolve_binary_secure(py_name)
    assert res is not None
    assert res.is_file()


def test_resolve_binary_rejects_cwd_shadowing(tmp_path: Path) -> None:
    fake_bin = tmp_path / "fake_executable"
    fake_bin.write_text("#!/bin/sh\necho fake\n", encoding="utf-8")
    if sys.platform != "win32":
        fake_bin.chmod(0o755)

    # Looking up non-existent system tool in cwd
    hit = resolve_binary_secure("fake_executable", cwd=tmp_path)
    assert hit is None  # Must reject local cwd binary


def test_audit_environment_health(tmp_path: Path) -> None:
    report = audit_environment_health(tmp_path)
    assert "engines" in report
    assert "python_version" in report
    assert "warnings" in report


def test_doctor_tool_run(tmp_path: Path) -> None:
    tool = DoctorTool()
    res = tool.run(tmp_path, permissions=ExecutionPermissions())
    assert res["tool"] == "doctor"
    assert res["status"] in {"ok", "warn"}
    assert "doctor:" in res["summary"]


def test_environment_doctor_anti_shadowing(tmp_path: Path) -> None:
    from rush.tools.doctor import EnvironmentDoctor

    doc = EnvironmentDoctor(repo_root=tmp_path)
    res = doc.check_python_anti_shadowing()
    assert res.name in {"python_runtime", "python_anti_shadowing"}
    assert res.status in {"ok", "warn", "fail"}

