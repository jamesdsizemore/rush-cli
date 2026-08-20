"""Tests for Phase 28: Extensible Plugin Execution & Validation.

Verifies:
- Executing declarative script plugins in Python/Node/Shell
- Validating plugin JSON output against ToolResult shape
- Rejecting malformed or invalid plugin responses
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from rush.plugins.loader import CustomPlugin, execute_plugin
from rush.plugins.validator import validate_plugin_output


def test_validate_plugin_output_success() -> None:
    valid_payload = json.dumps(
        {
            "tool": "custom-linter",
            "status": "ok",
            "duration_ms": 12,
            "summary": "custom-linter: passed cleanly",
            "findings": [],
        }
    )
    res = validate_plugin_output(valid_payload, plugin_name="custom-linter")
    assert res["status"] == "ok"
    assert res["tool"] == "custom-linter"


def test_validate_plugin_output_malformed_json() -> None:
    res = validate_plugin_output("not-json-content", plugin_name="broken")
    assert res["status"] == "error"
    assert "Invalid JSON" in res["summary"]


def test_validate_plugin_output_missing_fields() -> None:
    res = validate_plugin_output('{"unknown": 123}', plugin_name="missing-fields")
    assert res["status"] == "error"
    assert "Missing required keys" in res["summary"]


def test_execute_python_script_plugin(tmp_path: Path) -> None:
    plugin_script = tmp_path / "my_plugin.py"
    plugin_script.write_text(
        """import json, sys
print(json.dumps({
    "tool": "my_plugin",
    "status": "ok",
    "duration_ms": 5,
    "summary": "my_plugin: check completed",
    "findings": []
}))
""",
        encoding="utf-8",
    )

    plugin = CustomPlugin(
        name="my_plugin",
        command=[sys.executable, str(plugin_script)],
        description="Demo test plugin",
    )

    res = execute_plugin(plugin, target_path=tmp_path, is_trusted=True)
    assert res["status"] == "ok"
    assert res["tool"] == "my_plugin"


def test_execute_plugin_blocked_when_untrusted(tmp_path: Path) -> None:
    plugin = CustomPlugin(
        name="untrusted_plugin",
        command=[sys.executable, "-c", "print('hello')"],
        description="Untrusted demo plugin",
    )

    res = execute_plugin(plugin, target_path=tmp_path, is_trusted=False)
    assert res["status"] == "skipped"
    assert "trust required" in res["summary"].lower()
