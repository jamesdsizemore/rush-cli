"""Phase 17 A11yWatch reference adapter fake-process matrix."""

from __future__ import annotations

import subprocess
from pathlib import Path

from rush.engines import a11ywatch
from rush.engines.a11ywatch import A11ywatchEngine


def test_a11ywatch_runs_isolated_argv(monkeypatch, tmp_path: Path) -> None:
    calls: list[list[str]] = []

    def fake_run(
        argv: list[str], **_kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        calls.append(argv)
        return subprocess.CompletedProcess(argv, 0, stdout='{"data": []}', stderr="")

    monkeypatch.setattr(a11ywatch, "resolve_binary", lambda _binary: "C:/bin/a11ywatch")
    monkeypatch.setattr(a11ywatch, "run_subprocess", fake_run)

    raw = A11ywatchEngine().run(tmp_path, [], cwd=tmp_path)

    assert raw["exit_code"] == 0
    assert calls == [
        [
            "C:/bin/a11ywatch",
            "scan",
            "--url",
            "http://localhost:3000",
            "--json",
        ]
    ]


def test_a11ywatch_normalizes_clean_and_findings(monkeypatch, tmp_path: Path) -> None:
    engine = A11ywatchEngine()
    monkeypatch.setattr(A11ywatchEngine, "version", lambda _self: "0.10.0")

    clean = engine.normalize({"exit_code": 0, "findings": []}, tmp_path, "security")
    assert clean["status"] == "ok"
    assert clean["findings"] == []

    failing = engine.normalize(
        {
            "exit_code": 0,
            "findings": [
                {
                    "pageUrl": "http://localhost:3000/dashboard",
                    "code": "WCAG2AA.Principle4.Guideline4_1.4_1_2.H91.InputText.Name",
                    "type": "error",
                    "message": "Input element does not have a name available to an accessibility API",
                }
            ],
        },
        tmp_path,
        "security",
    )
    assert failing["status"] == "fail"
    assert len(failing["findings"]) == 1
    assert "a11ywatch/WCAG2AA" in failing["findings"][0]["rule"]
