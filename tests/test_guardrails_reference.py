"""Phase 09 Guardrails reference adapter fake-process matrix."""

from __future__ import annotations

import subprocess
from pathlib import Path

from rush.engines import guardrails
from rush.engines.guardrails import GuardrailsEngine


def test_guardrails_runs_isolated_argv(monkeypatch, tmp_path: Path) -> None:
    calls: list[list[str]] = []

    def fake_run(
        argv: list[str], **_kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        calls.append(argv)
        return subprocess.CompletedProcess(
            argv, 0, stdout='{"violations": []}', stderr=""
        )

    monkeypatch.setattr(
        guardrails, "resolve_binary", lambda _binary: "C:/bin/guardrails"
    )
    monkeypatch.setattr(guardrails, "run_subprocess", fake_run)

    raw = GuardrailsEngine().run(tmp_path, [], cwd=tmp_path)

    assert raw["exit_code"] == 0
    assert calls == [
        [
            "C:/bin/guardrails",
            "validate",
            "--format",
            "json",
            str(tmp_path),
        ]
    ]


def test_guardrails_normalizes_clean_and_violations(
    monkeypatch, tmp_path: Path
) -> None:
    engine = GuardrailsEngine()
    monkeypatch.setattr(GuardrailsEngine, "version", lambda _self: "0.5.0")

    clean = engine.normalize({"exit_code": 0, "findings": []}, tmp_path, "ai-eval")
    assert clean["status"] == "ok"
    assert clean["findings"] == []

    failing = engine.normalize(
        {
            "exit_code": 1,
            "findings": [
                {
                    "file": "config/rails.co",
                    "line": 12,
                    "column": 4,
                    "rule": "unreachable-flow",
                    "severity": "error",
                    "message": "Unreachable conversation branch detected",
                }
            ],
        },
        tmp_path,
        "ai-eval",
    )
    assert failing["status"] == "fail"
    assert len(failing["findings"]) == 1
    assert failing["findings"][0]["rule"] == "unreachable-flow"
