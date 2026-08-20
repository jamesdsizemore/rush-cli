"""Phase 18 Prisma-lint reference adapter fake-process matrix."""

from __future__ import annotations

import subprocess
from pathlib import Path

from rush.engines import prisma_lint
from rush.engines.prisma_lint import PrismaLintEngine


def test_prisma_lint_runs_isolated_argv(monkeypatch, tmp_path: Path) -> None:
    calls: list[list[str]] = []

    def fake_run(
        argv: list[str], **_kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        calls.append(argv)
        return subprocess.CompletedProcess(argv, 0, stdout="[]", stderr="")

    monkeypatch.setattr(
        prisma_lint, "resolve_binary", lambda _binary: "C:/bin/prisma-lint"
    )
    monkeypatch.setattr(prisma_lint, "run_subprocess", fake_run)

    raw = PrismaLintEngine().run(tmp_path, [], cwd=tmp_path)

    assert raw["exit_code"] == 0
    assert calls == [
        [
            "C:/bin/prisma-lint",
            "--format=json",
            str(tmp_path),
        ]
    ]


def test_prisma_lint_normalizes_clean_and_findings(monkeypatch, tmp_path: Path) -> None:
    engine = PrismaLintEngine()
    monkeypatch.setattr(PrismaLintEngine, "version", lambda _self: "0.8.0")

    clean = engine.normalize({"exit_code": 0, "findings": []}, tmp_path, "lint")
    assert clean["status"] == "ok"
    assert clean["findings"] == []

    failing = engine.normalize(
        {
            "exit_code": 1,
            "findings": [
                {
                    "file": "schema.prisma",
                    "line": 12,
                    "rule": "field-name-mapping-snake-case",
                    "message": "Field names must use camelCase with @map to snake_case",
                }
            ],
        },
        tmp_path,
        "lint",
    )
    assert failing["status"] == "warn"
    assert len(failing["findings"]) == 1
    assert "prisma-lint/field-name-mapping-snake-case" in failing["findings"][0]["rule"]
