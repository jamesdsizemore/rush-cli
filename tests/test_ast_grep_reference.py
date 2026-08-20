"""Phase 18 ast-grep reference adapter fake-process matrix."""

from __future__ import annotations

import subprocess
from pathlib import Path

from rush.engines import ast_grep
from rush.engines.ast_grep import AstGrepEngine


def test_ast_grep_runs_isolated_argv(monkeypatch, tmp_path: Path) -> None:
    calls: list[list[str]] = []

    def fake_run(
        argv: list[str], **_kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        calls.append(argv)
        return subprocess.CompletedProcess(argv, 0, stdout="[]", stderr="")

    monkeypatch.setattr(ast_grep, "resolve_binary", lambda _binary: "C:/bin/ast-grep")
    monkeypatch.setattr(ast_grep, "run_subprocess", fake_run)

    raw = AstGrepEngine().run(tmp_path, [], cwd=tmp_path)

    assert raw["exit_code"] == 0
    assert calls == [
        [
            "C:/bin/ast-grep",
            "scan",
            "--json=compact",
            str(tmp_path),
        ]
    ]


def test_ast_grep_normalizes_clean_and_findings(monkeypatch, tmp_path: Path) -> None:
    engine = AstGrepEngine()
    monkeypatch.setattr(AstGrepEngine, "version", lambda _self: "0.25.0")

    clean = engine.normalize({"exit_code": 0, "findings": []}, tmp_path, "lint")
    assert clean["status"] == "ok"
    assert clean["findings"] == []

    failing = engine.normalize(
        {
            "exit_code": 1,
            "findings": [
                {
                    "file": "src/query.py",
                    "ruleId": "no-eval-call",
                    "severity": "error",
                    "message": "Dangerous eval invocation detected in AST",
                    "range": {"start": {"line": 20, "column": 4}},
                }
            ],
        },
        tmp_path,
        "lint",
    )
    assert failing["status"] == "fail"
    assert len(failing["findings"]) == 1
    assert "ast-grep/no-eval-call" in failing["findings"][0]["rule"]
