"""Supply-chain tool safety contracts."""

from __future__ import annotations

from pathlib import Path

from rush.engines.gitleaks import GitleaksEngine
from rush.tools.sbom import SbomTool
from rush.tools.secrets import SecretsTool


def test_secrets_skip_when_gitleaks_is_unavailable(monkeypatch, tmp_path: Path) -> None:
    source = tmp_path / "config.py"
    source.write_text("token = 'fixture'\n")
    monkeypatch.setattr("rush.tools.common.resolve_binary", lambda binary: None)

    result = SecretsTool().run(tmp_path)

    assert result["status"] == "skipped"
    assert "fixture" not in result["summary"]
    assert result["findings"] == []


def test_gitleaks_normalization_never_exposes_report_values() -> None:
    result = GitleaksEngine().normalize(
        {
            "exit_code": 1,
            "stdout": '[{"File":"src/config.py","StartLine":12,"RuleID":"generic-api-key"}]',
        },
        Path("."),
        "secrets",
    )

    assert result["findings"] == [
        {
            "path": "src/config.py",
            "line": 12,
            "rule": "generic-api-key",
            "severity": "error",
            "message": "Potential secret detected",
        }
    ]
    assert result["raw"] is None


def test_sbom_refuses_to_overwrite_without_explicit_flag(tmp_path: Path) -> None:
    output = tmp_path / "bom.json"
    output.write_text("existing")

    result = SbomTool().run(tmp_path, output_path=output)

    assert result["status"] == "error"
    assert output.read_text() == "existing"
