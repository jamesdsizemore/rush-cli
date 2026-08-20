"""Phase 07.A1 ESLint reference adapter fake-process matrix."""

from __future__ import annotations

import subprocess
from pathlib import Path

from rush.engines import eslint
from rush.engines.eslint import EslintEngine
from rush.tools import common


def test_eslint_uses_json_argv_without_error_on_unmatched(
    monkeypatch, tmp_path: Path
) -> None:
    calls: list[list[str]] = []

    def fake_run(
        argv: list[str], **_kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        calls.append(argv)
        return subprocess.CompletedProcess(argv, 0, stdout="[]", stderr="")

    monkeypatch.setattr(eslint, "resolve_binary", lambda _binary: "C:/bin/eslint")
    monkeypatch.setattr(eslint, "run_subprocess", fake_run)

    raw = EslintEngine().run(tmp_path, [str(tmp_path / "main.ts")], cwd=tmp_path)

    assert raw["exit_code"] == 0
    assert calls == [
        [
            "C:/bin/eslint",
            str(tmp_path),
            "--format=json",
            "--no-error-on-unmatched-pattern",
            str(tmp_path / "main.ts"),
        ]
    ]


def test_eslint_normalizes_clean_and_findings(monkeypatch, tmp_path: Path) -> None:
    engine = EslintEngine()
    monkeypatch.setattr(EslintEngine, "version", lambda _self: "8.57.0")

    clean = engine.normalize(
        {"exit_code": 0, "stdout": "[]", "findings": []}, tmp_path, "lint"
    )
    findings_raw = [
        {
            "filePath": str(tmp_path / "main.ts"),
            "messages": [
                {
                    "ruleId": "no-unused-vars",
                    "severity": 2,
                    "message": "'x' is defined but never used",
                    "line": 5,
                    "column": 7,
                    "fix": None,
                }
            ],
        }
    ]
    finding = engine.normalize(
        {"exit_code": 1, "stdout": "...", "findings": findings_raw}, tmp_path, "lint"
    )
    error = engine.normalize(
        {"exit_code": 2, "stdout": "", "stderr": "Fatal configuration error"},
        tmp_path,
        "lint",
    )

    assert clean["status"] == "ok"
    assert clean["tool"] == "lint"
    assert finding["status"] == "fail"
    assert len(finding["findings"]) == 1
    assert finding["findings"][0]["rule"] == "no-unused-vars"
    assert finding["findings"][0]["severity"] == "error"
    assert error["status"] == "error"


def test_eslint_missing_and_timeout(monkeypatch, tmp_path: Path) -> None:
    engine = EslintEngine()
    monkeypatch.setattr(common, "engine_on_path", lambda _binary: False)
    missing = common.run_engine(engine, tmp_path, tool_name="lint")

    monkeypatch.setattr(common, "engine_on_path", lambda _binary: True)
    monkeypatch.setattr(
        eslint,
        "run_subprocess",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            subprocess.TimeoutExpired("eslint", 120)
        ),
    )
    timeout = common.run_engine(engine, tmp_path, tool_name="lint")

    assert missing["status"] == "skipped"
    assert timeout["status"] == "error"
    assert timeout["metadata"]["terminal_reason"] == "timeout"
