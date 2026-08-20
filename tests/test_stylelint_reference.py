"""Phase 17 Stylelint reference adapter fake-process matrix."""

from __future__ import annotations

import subprocess
from pathlib import Path

from rush.engines import stylelint
from rush.engines.stylelint import StylelintEngine


def test_stylelint_runs_isolated_argv(monkeypatch, tmp_path: Path) -> None:
    calls: list[list[str]] = []

    def fake_run(
        argv: list[str], **_kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        calls.append(argv)
        return subprocess.CompletedProcess(argv, 0, stdout="[]", stderr="")

    monkeypatch.setattr(stylelint, "resolve_binary", lambda _binary: "C:/bin/stylelint")
    monkeypatch.setattr(stylelint, "run_subprocess", fake_run)

    raw = StylelintEngine().run(tmp_path, [], cwd=tmp_path)

    assert raw["exit_code"] == 0
    assert calls == [
        [
            "C:/bin/stylelint",
            "--formatter",
            "json",
            str(tmp_path),
        ]
    ]


def test_stylelint_normalizes_clean_and_findings(monkeypatch, tmp_path: Path) -> None:
    engine = StylelintEngine()
    monkeypatch.setattr(StylelintEngine, "version", lambda _self: "16.8.0")

    clean = engine.normalize({"exit_code": 0, "findings": []}, tmp_path, "lint")
    assert clean["status"] == "ok"
    assert clean["findings"] == []

    failing = engine.normalize(
        {
            "exit_code": 2,
            "findings": [
                {
                    "source": "src/styles.css",
                    "line": 24,
                    "column": 3,
                    "rule": "color-no-invalid-hex",
                    "severity": "error",
                    "text": "Unexpected invalid hex color '#gggggg' (color-no-invalid-hex)",
                }
            ],
        },
        tmp_path,
        "lint",
    )
    assert failing["status"] == "fail"
    assert len(failing["findings"]) == 1
    assert "stylelint/color-no-invalid-hex" in failing["findings"][0]["rule"]
