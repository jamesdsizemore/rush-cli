"""Phase 02 Hadolint v2.15.1 reference-adapter contracts."""

from __future__ import annotations

import subprocess
from pathlib import Path

from rush.engines import hadolint
from rush.engines.hadolint import HadolintEngine


def test_hadolint_uses_json_and_rush_owned_empty_config(
    monkeypatch, tmp_path: Path
) -> None:
    source = tmp_path / "Dockerfile"
    source.write_text("FROM alpine:3.20\n")
    calls: list[tuple[list[str], dict[str, object]]] = []

    def fake_run(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        calls.append((argv, kwargs))
        return subprocess.CompletedProcess(argv, 0, stdout="[]", stderr="")

    monkeypatch.setattr(hadolint, "resolve_binary", lambda _binary: "C:/bin/hadolint")
    monkeypatch.setattr(hadolint, "run_subprocess", fake_run)
    monkeypatch.setenv("HADOLINT_FORMAT", "tty")

    raw = HadolintEngine().run(source, [str(source)], cwd=tmp_path)

    assert raw == {"exit_code": 0, "stdout": "[]", "stderr": ""}
    assert calls[0][0] == [
        "C:/bin/hadolint",
        "--config",
        str(hadolint.DEFAULT_CONFIG),
        "--format",
        "json",
        "--no-color",
        str(source),
    ]
    environment = calls[0][1]["env"]
    assert isinstance(environment, dict)
    assert "HADOLINT_FORMAT" not in environment


def test_hadolint_normalizes_json_findings_and_exit_codes(
    monkeypatch, tmp_path: Path
) -> None:
    source = tmp_path / "Dockerfile"
    source.write_text("FROM alpine:3.20\nUSER root\n")
    monkeypatch.setattr(HadolintEngine, "version", lambda _self: "2.15.1")

    result = HadolintEngine().normalize(
        {
            "exit_code": 1,
            "stdout": '[{"code":"DL3002","column":1,"file":"Dockerfile","level":"warning","line":2,"message":"Last user should not be root"}]',
            "stderr": "",
        },
        tmp_path,
        "containerfile",
    )

    assert result["status"] == "warn"
    assert result["findings"] == [
        {
            "rule": "DL3002",
            "severity": "warn",
            "message": "Last user should not be root",
            "path": str(source),
            "line": 2,
            "column": 1,
        }
    ]


def test_hadolint_rejects_malformed_or_inconsistent_json(tmp_path: Path) -> None:
    engine = HadolintEngine()
    malformed = engine.normalize(
        {"exit_code": 1, "stdout": "not-json", "stderr": ""}, tmp_path, "containerfile"
    )
    inconsistent = engine.normalize(
        {
            "exit_code": 0,
            "stdout": '[{"code":"DL3002","file":"Dockerfile","level":"warning","line":2,"message":"Last user should not be root"}]',
            "stderr": "",
        },
        tmp_path,
        "containerfile",
    )

    assert malformed["status"] == "error"
    assert malformed["metadata"]["terminal_reason"] == "malformed_output"
    assert inconsistent["status"] == "error"
    assert inconsistent["metadata"]["terminal_reason"] == "nonzero_exit"
