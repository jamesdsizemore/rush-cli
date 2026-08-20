"""Phase 15 HTML-Validate reference adapter fake-process matrix."""

from __future__ import annotations

import subprocess
from pathlib import Path

from rush.engines import html_validate
from rush.engines.html_validate import HtmlValidateEngine


def test_html_validate_runs_isolated_argv(monkeypatch, tmp_path: Path) -> None:
    calls: list[list[str]] = []

    def fake_run(
        argv: list[str], **_kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        calls.append(argv)
        return subprocess.CompletedProcess(argv, 0, stdout="[]", stderr="")

    monkeypatch.setattr(
        html_validate, "resolve_binary", lambda _binary: "C:/bin/html-validate"
    )
    monkeypatch.setattr(html_validate, "run_subprocess", fake_run)

    raw = HtmlValidateEngine().run(tmp_path, [], cwd=tmp_path)

    assert raw["exit_code"] == 0
    assert calls == [
        [
            "C:/bin/html-validate",
            "--formatter",
            "json",
            str(tmp_path),
        ]
    ]


def test_html_validate_normalizes_clean_and_findings(
    monkeypatch, tmp_path: Path
) -> None:
    engine = HtmlValidateEngine()
    monkeypatch.setattr(HtmlValidateEngine, "version", lambda _self: "8.19.0")

    clean = engine.normalize({"exit_code": 0, "findings": []}, tmp_path, "templates")
    assert clean["status"] == "ok"
    assert clean["findings"] == []

    failing = engine.normalize(
        {
            "exit_code": 1,
            "findings": [
                {
                    "filePath": "index.html",
                    "line": 15,
                    "column": 5,
                    "ruleId": "element-required-attributes",
                    "severity": 2,
                    "message": "<img> is missing required alt attribute",
                }
            ],
        },
        tmp_path,
        "templates",
    )
    assert failing["status"] == "fail"
    assert len(failing["findings"]) == 1
    assert failing["findings"][0]["rule"] == "html-validate/element-required-attributes"
