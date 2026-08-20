"""Phase 02 SQLFluff v4.3.0 contained-reference contracts."""

from __future__ import annotations

import subprocess
from pathlib import Path

from rush.engines import sqlfluff
from rush.engines.sqlfluff import SqlfluffEngine


def test_sqlfluff_uses_owned_config_raw_templater_and_json(
    monkeypatch, tmp_path: Path
) -> None:
    source = tmp_path / "query.sql"
    source.write_text("select 1")
    calls: list[tuple[list[str], dict[str, object]]] = []

    def fake_run(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        calls.append((argv, kwargs))
        return subprocess.CompletedProcess(argv, 0, stdout="[]", stderr="")

    monkeypatch.setattr(sqlfluff, "resolve_binary", lambda _binary: "C:/bin/sqlfluff")
    monkeypatch.setattr(sqlfluff, "run_subprocess", fake_run)
    monkeypatch.setattr(SqlfluffEngine, "version", lambda _self: "4.3.0")

    result = SqlfluffEngine().run(source, [str(source)], cwd=tmp_path)

    assert result["exit_code"] == 0
    assert calls == [
        (
            [
                "C:/bin/sqlfluff",
                "lint",
                "--ignore-local-config",
                "--config",
                str(sqlfluff.DEFAULT_CONFIG),
                "--dialect",
                "ansi",
                "--templater",
                "raw",
                "--format",
                "json",
                "--processes",
                "1",
                str(source),
            ],
            {"cwd": tmp_path, "timeout": 120},
        )
    ]


def test_sqlfluff_normalizes_json_findings_and_exit_codes(
    monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(SqlfluffEngine, "version", lambda _self: "4.3.0")
    result = SqlfluffEngine().normalize(
        {
            "exit_code": 1,
            "stdout": '[{"filepath":"query.sql","violations":[{"code":"LT01","description":"Unexpected whitespace","line_no":2,"line_pos":3,"warning":false}]}]',
            "stderr": "",
        },
        tmp_path,
        "sql",
    )
    assert result["status"] == "warn"
    assert result["findings"][0] == {
        "rule": "LT01",
        "severity": "warn",
        "message": "Unexpected whitespace",
        "path": str(tmp_path / "query.sql"),
        "line": 2,
        "column": 3,
    }


def test_sqlfluff_rejects_malformed_or_inconsistent_json(
    monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(SqlfluffEngine, "version", lambda _self: "4.3.0")
    malformed = SqlfluffEngine().normalize(
        {"exit_code": 1, "stdout": "not json", "stderr": ""}, tmp_path, "sql"
    )
    inconsistent = SqlfluffEngine().normalize(
        {
            "exit_code": 0,
            "stdout": '[{"filepath":"q.sql","violations":[{"code":"LT01","description":"x","line_no":1,"line_pos":1,"warning":false}]}]',
            "stderr": "",
        },
        tmp_path,
        "sql",
    )
    assert malformed["metadata"]["terminal_reason"] == "malformed_output"
    assert inconsistent["metadata"]["terminal_reason"] == "nonzero_exit"
