"""Contract tests for Public Routes, Admin Adapters, and CLI Hardening.

Architecture §8, Phase 56 Workstream P56.5.
Contract Test Ledger:
- T-56.14: test_plugin_run_cannot_reach_legacy_loader_execute_path
- T-56.15: test_allow_untrusted_is_not_public
- T-56.16: test_plugin_output_uses_admin_result_adapter_and_sanitizer
"""

from __future__ import annotations

import inspect
import sys
from pathlib import Path
from unittest.mock import MagicMock

import click
import pytest
from click.testing import CliRunner

from rush.cli import cli
from rush.contracts.operations import AdminOperationAdapter
from rush.contracts.results import FindingV1, ToolResultV1, validate_tool_result
from rush.plugins.closure import build_plugin_closure
from rush.plugins.executor import HardenedPluginExecutor
from rush.plugins.loader import PluginSpec
from rush.plugins.snapshot_store import PluginSnapshotStore
from rush.plugins.trust_store import PluginTrustStore
from rush.tools.common import exit_code_for


def test_plugin_run_cannot_reach_legacy_loader_execute_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """T-56.14: Asserts rush plugin run exclusively invokes HardenedPluginExecutor.execute,

    and never calls legacy loader.execute_plugin.
    """
    repo_root = tmp_path / "repo"
    repo_root.mkdir(parents=True)
    plugin_dir = repo_root / "plugins" / "sample_plugin"
    plugin_dir.mkdir(parents=True)
    script_path = plugin_dir / "main.py"
    script_path.write_text(
        "import json\n"
        "print(json.dumps({\n"
        "    'schema_version': '1.0.0',\n"
        "    'tool': 'plugin',\n"
        "    'engine': 'sample_plugin',\n"
        "    'engine_version': '1.0.0',\n"
        "    'status': 'ok',\n"
        "    'duration_ms': 5,\n"
        "    'summary': 'Execution completed',\n"
        "    'findings': [],\n"
        "}))\n",
        encoding="utf-8",
    )
    rush_toml = repo_root / "rush.toml"
    rush_toml.write_text(
        f"[plugins.sample_plugin]\n"
        f"command = ['{sys.executable}', 'plugins/sample_plugin/main.py']\n"
        f"description = 'Test plugin'\n",
        encoding="utf-8",
    )

    # Setup spy / mocks
    mock_legacy_execute = MagicMock()
    monkeypatch.setattr("rush.plugins.loader.execute_plugin", mock_legacy_execute)

    mock_hardened_execute = MagicMock(
        return_value=ToolResultV1(
            schema_version="1.0.0",
            tool="plugin",
            engine="sample_plugin",
            engine_version="1.0.0",
            status="ok",
            duration_ms=5,
            summary="Execution completed",
            findings=[],
        )
    )
    monkeypatch.setattr(HardenedPluginExecutor, "execute", mock_hardened_execute)

    runner = CliRunner()
    result = runner.invoke(cli, ["plugin", "run", "sample_plugin", str(repo_root)])
    assert result.exit_code == 0

    assert mock_hardened_execute.called, (
        "HardenedPluginExecutor.execute was not invoked"
    )
    assert not mock_legacy_execute.called, (
        "Legacy loader.execute_plugin was invoked! Public route must not use legacy executor."
    )


def test_allow_untrusted_is_not_public() -> None:
    """T-56.15: Asserts --allow-untrusted option is completely absent from public CLI parameters,

    and HardenedPluginExecutor.execute has no allow_untrusted parameter.
    """
    # 1. Inspect Click CLI command options
    disallowed_options = {"--allow-untrusted", "--allow-untrusted-plugins"}

    def check_command(cmd: click.Command, cmd_path: str) -> None:
        for param in cmd.params:
            if isinstance(param, click.Option):
                for opt in (*param.opts, *param.secondary_opts):
                    assert opt not in disallowed_options, (
                        f"Disallowed security-bypass option '{opt}' found on {cmd_path}"
                    )
        if isinstance(cmd, click.Group):
            for sub_name, sub_cmd in cmd.commands.items():
                check_command(sub_cmd, f"{cmd_path} {sub_name}")

    # Inspect plugin_run, plugin group, and trust command
    plugin_cmd = cli.commands.get("plugin")
    assert plugin_cmd is not None, "rush plugin command group missing"
    check_command(plugin_cmd, "rush plugin")

    trust_cmd = cli.commands.get("trust")
    assert trust_cmd is not None, "rush trust command missing"
    check_command(trust_cmd, "rush trust")

    # Also check full cli commands
    check_command(cli, "rush")

    # 2. Inspect HardenedPluginExecutor.execute signature
    sig = inspect.signature(HardenedPluginExecutor.execute)
    assert "allow_untrusted" not in sig.parameters, (
        "HardenedPluginExecutor.execute must not accept allow_untrusted parameter"
    )
    assert "allow_untrusted_plugins" not in sig.parameters, (
        "HardenedPluginExecutor.execute must not accept allow_untrusted_plugins parameter"
    )


def test_plugin_output_uses_admin_result_adapter_and_sanitizer(tmp_path: Path) -> None:
    """T-56.16: Executes plugin emitting findings via HardenedPluginExecutor.execute,

    verifies ToolResultV1 with FindingV1 conforming to Phase 54 schema,
    and validates exit code through AdminOperationAdapter(operation_id='cli.plugin_run', target_contract_id='ClickExitCode').
    """
    repo_root = tmp_path / "repo"
    repo_root.mkdir(parents=True)
    plugin_dir = repo_root / "plugins" / "finding_plugin"
    plugin_dir.mkdir(parents=True)
    main_py = plugin_dir / "main.py"
    main_py.write_text(
        "import json\n"
        "result = {\n"
        "    'schema_version': '1.0.0',\n"
        "    'tool': 'plugin',\n"
        "    'engine': 'finding_plugin',\n"
        "    'engine_version': '1.0.0',\n"
        "    'status': 'warn',\n"
        "    'duration_ms': 12,\n"
        "    'summary': 'Security warning detected',\n"
        "    'findings': [{\n"
        "        'path': 'sensitive.py',\n"
        "        'line': 42,\n"
        "        'column': 1,\n"
        "        'rule_id': 'RULE_INSECURE_PERM',\n"
        "        'severity': 'warning',\n"
        "        'message': 'Permissive file permissions',\n"
        "        'fingerprint': 'e' * 64,\n"
        "    }],\n"
        "}\n"
        "print(json.dumps(result))\n",
        encoding="utf-8",
    )

    target_file = repo_root / "sensitive.py"
    target_file.write_text("# code\n", encoding="utf-8")

    closure = build_plugin_closure(
        plugin_root=plugin_dir,
        entrypoint=main_py,
        config={"name": "finding_plugin", "command": [sys.executable, "main.py"]},
        plugin_name="finding_plugin",
    )

    snapshots_root = tmp_path / "user_home" / ".rush" / "snapshots"
    snapshot_store = PluginSnapshotStore(snapshots_root=snapshots_root)
    snapshot_dir = snapshot_store.materialize_snapshot(
        closure=closure, plugin_root=plugin_dir
    )

    ledger_path = tmp_path / "user_home" / ".rush" / "plugin_trust_ledger.json"
    trust_store = PluginTrustStore(repo_root=repo_root, ledger_path=ledger_path)
    trust_store.grant_trust("finding_plugin", closure.closure_digest, snapshot_dir)

    executor = HardenedPluginExecutor(
        repo_root=repo_root,
        trust_store=trust_store,
        snapshot_store=snapshot_store,
    )

    plugin_spec = PluginSpec(
        name="finding_plugin",
        executable_path=main_py,
        command=[sys.executable, "main.py"],
        closure=closure,
    )

    result = executor.execute(plugin_spec, [target_file])

    # 1. Assert result is instance of ToolResultV1 conforming to Phase 54 schema
    assert isinstance(result, ToolResultV1)
    assert result.schema_version == "1.0.0"
    assert result.tool == "plugin"
    assert result.engine == "finding_plugin"
    assert result.status == "warn"
    assert len(result.findings) == 1

    finding = result.findings[0]
    assert isinstance(finding, FindingV1)
    assert finding.path == "sensitive.py"
    assert finding.line == 42
    assert finding.rule_id == "RULE_INSECURE_PERM"
    assert finding.severity == "warning"
    assert finding.fingerprint == "e" * 64

    # Ensure to_dict() validates strictly under validate_tool_result
    validated = validate_tool_result(result.to_dict())
    assert validated.tool == result.tool
    assert validated.status == result.status
    assert len(validated.findings) == 1

    # 2. Assert exit code conforms to Phase 54 AdminOperationAdapter
    adapter = AdminOperationAdapter(
        operation_id="cli.plugin_run",
        target_contract_id="ClickExitCode",
    )
    raw_exit_code = exit_code_for(result.status)
    validated_exit_code = adapter.validate_output(raw_exit_code)
    assert validated_exit_code == 1
    assert isinstance(validated_exit_code, int)
    assert not isinstance(validated_exit_code, bool)
