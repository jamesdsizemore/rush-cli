"""Phase 03 offline npm-audit reference contracts."""

from __future__ import annotations

import subprocess
from pathlib import Path

from rush.engines import npm_audit
from rush.engines.npm_audit import NpmAuditEngine


def test_npm_audit_uses_offline_json_only(monkeypatch, tmp_path: Path) -> None:
    calls: list[list[str]] = []

    def fake_run(
        argv: list[str], **_kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        calls.append(argv)
        return subprocess.CompletedProcess(
            argv, 0, stdout='{"vulnerabilities": {}}', stderr=""
        )

    monkeypatch.setattr(npm_audit, "resolve_binary", lambda _binary: "C:/bin/npm")
    monkeypatch.setattr(npm_audit, "run_subprocess", fake_run)

    raw = NpmAuditEngine().run(tmp_path, [], cwd=tmp_path)

    assert raw["parsed"] == {"vulnerabilities": {}}
    assert calls == [["C:/bin/npm", "audit", "--json", "--offline"]]


def test_npm_audit_rejects_malformed_clean_output(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(NpmAuditEngine, "version", lambda _self: "fixture")

    result = NpmAuditEngine().normalize(
        {"exit_code": 0, "stdout": "not-json", "parsed": None, "findings": []},
        tmp_path,
        "security",
    )

    assert result["status"] == "error"
