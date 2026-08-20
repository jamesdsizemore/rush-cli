"""Phase 08 Playwright reference adapter fake-process matrix."""

from __future__ import annotations

import subprocess
from pathlib import Path

from rush.engines import playwright
from rush.engines.playwright import PlaywrightEngine
from rush.tools import common


def test_playwright_runs_json_reporter_argv(monkeypatch, tmp_path: Path) -> None:
    calls: list[list[str]] = []

    def fake_run(
        argv: list[str], **_kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        calls.append(argv)
        return subprocess.CompletedProcess(argv, 0, stdout='{"suites": []}', stderr="")

    monkeypatch.setattr(
        playwright, "resolve_binary", lambda _binary: "C:/bin/playwright"
    )
    monkeypatch.setattr(playwright, "run_subprocess", fake_run)

    raw = PlaywrightEngine().run(tmp_path, [], cwd=tmp_path)

    assert raw["exit_code"] == 0
    assert calls == [
        [
            "C:/bin/playwright",
            "test",
            "--reporter=json",
            str(tmp_path),
        ]
    ]


def test_playwright_normalizes_clean_and_findings(monkeypatch, tmp_path: Path) -> None:
    engine = PlaywrightEngine()
    monkeypatch.setattr(PlaywrightEngine, "version", lambda _self: "1.46.0")

    clean = engine.normalize({"exit_code": 0, "findings": []}, tmp_path, "e2e")
    finding = engine.normalize(
        {
            "exit_code": 1,
            "findings": [
                {
                    "title": "homepage loads correctly",
                    "file": "tests/e2e/home.spec.ts",
                    "line": 12,
                    "message": "Timed out 5000ms waiting for expect(locator).toBeVisible()",
                }
            ],
        },
        tmp_path,
        "e2e",
    )

    assert clean["status"] == "ok"
    assert clean["tool"] == "e2e"
    assert finding["status"] == "fail"
    assert len(finding["findings"]) == 1
    assert finding["findings"][0]["rule"] == "playwright-test-failed"
    assert finding["findings"][0]["line"] == 12


def test_playwright_missing_and_timeout(monkeypatch, tmp_path: Path) -> None:
    engine = PlaywrightEngine()
    monkeypatch.setattr(common, "engine_on_path", lambda _binary: False)
    missing = common.run_engine(engine, tmp_path, tool_name="e2e")

    monkeypatch.setattr(common, "engine_on_path", lambda _binary: True)
    monkeypatch.setattr(
        playwright,
        "run_subprocess",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            subprocess.TimeoutExpired("playwright", 300)
        ),
    )
    timeout = common.run_engine(engine, tmp_path, tool_name="e2e")

    assert missing["status"] == "skipped"
    assert timeout["status"] == "error"
    assert timeout["metadata"]["terminal_reason"] == "timeout"
