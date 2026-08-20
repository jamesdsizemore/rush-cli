"""Phase 07.C Semgrep reference adapter fake-process matrix."""

from __future__ import annotations

import subprocess
from pathlib import Path

from rush.engines import semgrep
from rush.engines.semgrep import SemgrepEngine
from rush.tools import common


def test_semgrep_runs_isolated_argv(monkeypatch, tmp_path: Path) -> None:
    calls: list[list[str]] = []

    def fake_run(
        argv: list[str], **_kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        calls.append(argv)
        return subprocess.CompletedProcess(argv, 0, stdout='{"results": []}', stderr="")

    monkeypatch.setattr(semgrep, "resolve_binary", lambda _binary: "C:/bin/semgrep")
    monkeypatch.setattr(semgrep, "run_subprocess", fake_run)

    raw = SemgrepEngine().run(tmp_path, [], cwd=tmp_path)

    assert raw["exit_code"] == 0
    assert calls == [
        [
            "C:/bin/semgrep",
            "scan",
            "--json",
            "--metrics=off",
            "--disable-version-check",
            "--config",
            "auto",
            str(tmp_path),
        ]
    ]


def test_semgrep_normalizes_clean_and_findings(monkeypatch, tmp_path: Path) -> None:
    engine = SemgrepEngine()
    monkeypatch.setattr(SemgrepEngine, "version", lambda _self: "1.80.0")

    clean = engine.normalize({"exit_code": 0, "findings": []}, tmp_path, "security")
    finding = engine.normalize(
        {
            "exit_code": 1,
            "findings": [
                {
                    "check_id": "python.lang.security.audit.exec.exec-used",
                    "path": "src/app.py",
                    "start": {"line": 15, "col": 5},
                    "extra": {
                        "severity": "ERROR",
                        "message": "Detected use of exec()",
                    },
                }
            ],
        },
        tmp_path,
        "security",
    )

    assert clean["status"] == "ok"
    assert clean["tool"] == "security"
    assert finding["status"] == "fail"
    assert len(finding["findings"]) == 1
    assert finding["findings"][0]["rule"] == "python.lang.security.audit.exec.exec-used"
    assert finding["findings"][0]["line"] == 15


def test_semgrep_missing_and_timeout(monkeypatch, tmp_path: Path) -> None:
    engine = SemgrepEngine()
    monkeypatch.setattr(common, "engine_on_path", lambda _binary: False)
    missing = common.run_engine(engine, tmp_path, tool_name="security")

    monkeypatch.setattr(common, "engine_on_path", lambda _binary: True)
    monkeypatch.setattr(
        semgrep,
        "run_subprocess",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            subprocess.TimeoutExpired("semgrep", 180)
        ),
    )
    timeout = common.run_engine(engine, tmp_path, tool_name="security")

    assert missing["status"] == "skipped"
    assert timeout["status"] == "error"
    assert timeout["metadata"]["terminal_reason"] == "timeout"
