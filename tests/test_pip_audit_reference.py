"""Phase 03 contained pip-audit reference contracts."""

from __future__ import annotations

import subprocess
from pathlib import Path

from rush.engines import pip_audit
from rush.engines.pip_audit import PipAuditEngine


def test_pip_audit_requires_explicit_requirements_input(
    monkeypatch, tmp_path: Path
) -> None:
    requirements = tmp_path / "requirements.txt"
    requirements.write_text("requests==2.0\n")
    calls: list[list[str]] = []

    def fake_run(
        argv: list[str], **_kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        calls.append(argv)
        return subprocess.CompletedProcess(argv, 0, stdout="[]", stderr="")

    monkeypatch.setattr(pip_audit, "resolve_binary", lambda _binary: "C:/bin/pip-audit")
    monkeypatch.setattr(pip_audit, "run_subprocess", fake_run)

    raw = PipAuditEngine().run(tmp_path, [], cwd=tmp_path)

    assert raw["parsed"] == []
    assert calls == [
        [
            "C:/bin/pip-audit",
            "--format=json",
            "--strict",
            "--requirement",
            str(requirements),
        ]
    ]


def test_pip_audit_rejects_malformed_clean_output(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(PipAuditEngine, "version", lambda _self: "fixture")

    result = PipAuditEngine().normalize(
        {"exit_code": 0, "stdout": "not-json", "parsed": None, "findings": []},
        tmp_path,
        "security",
    )

    assert result["status"] == "error"


def test_pip_audit_project_mode_targets_root_with_no_requirement_flag(
    monkeypatch, tmp_path: Path
) -> None:
    """T14 (R14.1/S14.3): `--project-mode` drops `--requirement` entirely and
    targets the audited project's own root -- pyproject-declared dependencies,
    never Rush's interpreter, never an implicit requirements.txt lookup."""
    calls: list[list[str]] = []

    def fake_run(
        argv: list[str], **_kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        calls.append(argv)
        return subprocess.CompletedProcess(
            argv, 0, stdout='{"dependencies": []}', stderr=""
        )

    monkeypatch.setattr(pip_audit, "resolve_binary", lambda _binary: "pip-audit")
    monkeypatch.setattr(pip_audit, "run_subprocess", fake_run)

    raw = PipAuditEngine().run(tmp_path, ["--project-mode"], cwd=tmp_path)

    assert raw["parsed"] == {"dependencies": []}
    assert calls == [
        [
            "pip-audit",
            "--format=json",
            "--strict",
            "--progress-spinner=off",
            str(tmp_path),
        ]
    ]
