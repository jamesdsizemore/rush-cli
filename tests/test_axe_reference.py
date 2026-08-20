"""Phase 08 Axe-core reference adapter fake-process matrix."""

from __future__ import annotations

import subprocess
from pathlib import Path

from rush.engines import axe
from rush.engines.axe import AxeEngine
from rush.tools import common


def test_axe_runs_stdout_json_argv(monkeypatch, tmp_path: Path) -> None:
    calls: list[list[str]] = []

    def fake_run(
        argv: list[str], **_kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        calls.append(argv)
        return subprocess.CompletedProcess(
            argv, 0, stdout='[{"violations": []}]', stderr=""
        )

    monkeypatch.setattr(axe, "resolve_binary", lambda _binary: "C:/bin/axe")
    monkeypatch.setattr(axe, "run_subprocess", fake_run)

    raw = AxeEngine().run(tmp_path / "index.html", [], cwd=tmp_path)

    assert raw["exit_code"] == 0
    assert calls == [
        [
            "C:/bin/axe",
            str(tmp_path / "index.html"),
            "--save",
            "--stdout",
        ]
    ]


def test_axe_normalizes_clean_and_findings(monkeypatch, tmp_path: Path) -> None:
    engine = AxeEngine()
    monkeypatch.setattr(AxeEngine, "version", lambda _self: "4.9.0")

    clean = engine.normalize(
        {"exit_code": 0, "findings": []}, tmp_path, "semantic-drift"
    )
    finding = engine.normalize(
        {
            "exit_code": 1,
            "findings": [
                {
                    "id": "color-contrast",
                    "impact": "serious",
                    "help": "Elements must have sufficient color contrast",
                    "description": "Ensures the contrast between foreground and background colors meets WCAG 2 AA thresholds",
                }
            ],
        },
        tmp_path,
        "semantic-drift",
    )

    assert clean["status"] == "ok"
    assert clean["tool"] == "semantic-drift"
    assert finding["status"] == "fail"
    assert len(finding["findings"]) == 1
    assert finding["findings"][0]["rule"] == "color-contrast"
    assert finding["findings"][0]["severity"] == "error"


def test_axe_missing_and_timeout(monkeypatch, tmp_path: Path) -> None:
    engine = AxeEngine()
    monkeypatch.setattr(common, "engine_on_path", lambda _binary: False)
    missing = common.run_engine(engine, tmp_path, tool_name="semantic-drift")

    monkeypatch.setattr(common, "engine_on_path", lambda _binary: True)
    monkeypatch.setattr(
        axe,
        "run_subprocess",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            subprocess.TimeoutExpired("axe", 120)
        ),
    )
    timeout = common.run_engine(engine, tmp_path, tool_name="semantic-drift")

    assert missing["status"] == "skipped"
    assert timeout["status"] == "error"
    assert timeout["metadata"]["terminal_reason"] == "timeout"
