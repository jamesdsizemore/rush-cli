"""Supply-chain tool safety contracts."""

from __future__ import annotations

from pathlib import Path

import pytest

from rush.engines.gitleaks import GitleaksEngine
from rush.tools.sbom import SbomTool
from rush.tools.secrets import SecretsTool
from rush.tools.security import SecurityTool


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


def test_sbom_rejects_an_output_path_outside_the_target(tmp_path: Path) -> None:
    target = tmp_path / "project"
    target.mkdir()

    result = SbomTool().run(target, output_path=tmp_path / "outside.json")

    assert result["status"] == "error"
    assert "outside target" in result["summary"]


def test_security_adds_offline_osv_for_an_explicit_lockfile(
    monkeypatch, tmp_path: Path
) -> None:
    (tmp_path / "Cargo.lock").write_text("fixture")
    calls: list[tuple[str, Path]] = []

    def fake_run(engine, path: Path, args, *, tool_name: str):
        calls.append((engine.name, path))
        return {
            "tool": tool_name,
            "engine": engine.name,
            "engine_version": "fixture",
            "status": "ok",
            "duration_ms": 0,
            "summary": "fixture",
            "findings": [],
            "raw": None,
        }

    monkeypatch.setattr("rush.tools.security.run_engine", fake_run)

    result = SecurityTool().run(tmp_path)

    assert result["status"] == "ok"
    assert calls == [("osv-scanner", tmp_path / "Cargo.lock")]


def test_security_does_not_run_networked_npm_audit(monkeypatch, tmp_path: Path) -> None:
    (tmp_path / "package.json").write_text("{}")
    monkeypatch.setattr(
        "rush.tools.security.run_engine",
        lambda *_args, **_kwargs: pytest.fail("networked audit must not run"),
    )

    result = SecurityTool().run(tmp_path)

    assert result["status"] == "skipped"


def test_security_uses_offline_npm_audit_only_for_a_lockfile(
    monkeypatch, tmp_path: Path
) -> None:
    (tmp_path / "package.json").write_text("{}")
    (tmp_path / "package-lock.json").write_text("{}")
    calls: list[str] = []

    def fake_run(engine, path: Path, args, *, tool_name: str):
        calls.append(engine.name)
        return {
            "tool": tool_name,
            "engine": engine.name,
            "engine_version": "fixture",
            "status": "ok",
            "duration_ms": 0,
            "summary": "fixture",
            "findings": [],
            "raw": None,
        }

    monkeypatch.setattr("rush.tools.security.run_engine", fake_run)

    result = SecurityTool().run(tmp_path)

    assert result["status"] == "ok"
    assert calls == ["npm-audit", "osv-scanner"]
