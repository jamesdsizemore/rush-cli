"""Phase 00 Gitleaks reference-adapter fake-process matrix."""

from __future__ import annotations

import subprocess
from pathlib import Path

from rush.engines import base as engine_base
from rush.engines import gitleaks
from rush.engines.gitleaks import GitleaksEngine
from rush.tools import common


def test_gitleaks_fake_process_uses_json_only_local_argv(
    monkeypatch, tmp_path: Path
) -> None:
    calls: list[list[str]] = []

    def fake_run(
        argv: list[str], **_kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        calls.append(argv)
        return subprocess.CompletedProcess(argv, 0, stdout="[]", stderr="")

    monkeypatch.setattr(gitleaks, "resolve_binary", lambda _binary: "C:/bin/gitleaks")
    monkeypatch.setattr(gitleaks, "run_subprocess", fake_run)

    raw = GitleaksEngine().run(tmp_path, [], cwd=tmp_path)

    assert raw == {"exit_code": 0, "stdout": "[]", "stderr": ""}
    assert calls == [
        [
            "C:/bin/gitleaks",
            "detect",
            "--source",
            str(tmp_path),
            "--report-format",
            "json",
            "--report-path",
            "-",
            "--no-banner",
        ]
    ]


def test_gitleaks_normalizes_clean_findings_and_malformed_output(
    monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(GitleaksEngine, "version", lambda _self: "8.30.1")
    engine = GitleaksEngine()

    clean = engine.normalize({"exit_code": 0, "stdout": "[]"}, tmp_path, "secrets")
    finding = engine.normalize(
        {
            "exit_code": 1,
            "stdout": '[{"File":".env","StartLine":2,"RuleID":"api-key","Secret":"token=abc"}]',
        },
        tmp_path,
        "secrets",
    )
    malformed = engine.normalize(
        {"exit_code": 2, "stdout": "not-json"}, tmp_path, "secrets"
    )
    command_failure = engine.normalize(
        {"exit_code": 2, "stdout": "[]", "stderr": "fatal: fixture failure"},
        tmp_path,
        "secrets",
    )

    assert clean["status"] == "ok"
    assert finding["status"] == "fail"
    assert finding["findings"][0]["message"] == "Potential secret detected"
    assert "abc" not in str(finding)
    assert malformed["status"] == "error"
    assert malformed["metadata"]["terminal_reason"] == "malformed_output"
    assert command_failure["status"] == "error"
    assert command_failure["metadata"]["terminal_reason"] == "nonzero_exit"


def test_gitleaks_missing_and_timeout_are_structured(
    monkeypatch, tmp_path: Path
) -> None:
    engine = GitleaksEngine()
    monkeypatch.setattr(common, "engine_on_path", lambda _binary: False)
    missing = common.run_engine(engine, tmp_path, tool_name="secrets")

    monkeypatch.setattr(common, "engine_on_path", lambda _binary: True)
    monkeypatch.setattr(
        gitleaks,
        "run_subprocess",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            subprocess.TimeoutExpired("gitleaks", 120)
        ),
    )
    timeout = common.run_engine(engine, tmp_path, tool_name="secrets")

    assert missing["status"] == "skipped"
    assert timeout["status"] == "error"
    assert timeout["metadata"]["terminal_reason"] == "timeout"


def test_gitleaks_version_probe_failure_returns_none(monkeypatch) -> None:
    monkeypatch.setattr(
        engine_base, "resolve_binary", lambda _binary: "C:/bin/gitleaks"
    )
    monkeypatch.setattr(
        engine_base,
        "run_subprocess",
        lambda argv, **_kwargs: subprocess.CompletedProcess(
            argv, 2, stdout="", stderr="error"
        ),
    )

    assert GitleaksEngine().version() is None
