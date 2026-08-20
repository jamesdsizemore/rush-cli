"""Phase 19 Buf reference adapter fake-process matrix."""

from __future__ import annotations

import subprocess
from pathlib import Path

from rush.engines import buf
from rush.engines.buf import BufEngine


def test_buf_runs_isolated_argv(monkeypatch, tmp_path: Path) -> None:
    calls: list[list[str]] = []

    def fake_run(
        argv: list[str], **_kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        calls.append(argv)
        return subprocess.CompletedProcess(argv, 0, stdout="", stderr="")

    monkeypatch.setattr(buf, "resolve_binary", lambda _binary: "C:/bin/buf")
    monkeypatch.setattr(buf, "run_subprocess", fake_run)

    raw = BufEngine().run(tmp_path, [], cwd=tmp_path)

    assert raw["exit_code"] == 0
    assert calls == [
        [
            "C:/bin/buf",
            "lint",
            "--error-format=json",
        ]
    ]


def test_buf_normalizes_clean_and_findings(monkeypatch, tmp_path: Path) -> None:
    engine = BufEngine()
    monkeypatch.setattr(BufEngine, "version", lambda _self: "1.40.0")

    clean = engine.normalize({"exit_code": 0, "findings": []}, tmp_path, "lint")
    assert clean["status"] == "ok"
    assert clean["findings"] == []

    failing = engine.normalize(
        {
            "exit_code": 1,
            "findings": [
                {
                    "path": "service.proto",
                    "start_line": 8,
                    "start_column": 1,
                    "type": "FIELD_LOWER_SNAKE_CASE",
                    "message": "Field name 'userId' must be lower_snake_case",
                }
            ],
        },
        tmp_path,
        "lint",
    )
    assert failing["status"] == "fail"
    assert len(failing["findings"]) == 1
    assert "buf/FIELD_LOWER_SNAKE_CASE" in failing["findings"][0]["rule"]
