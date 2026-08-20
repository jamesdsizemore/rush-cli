"""Phase 07.A8 djLint reference adapter fake-process matrix."""

from __future__ import annotations

import subprocess
from pathlib import Path

from rush.engines import text_lint
from rush.engines.djlint import DjlintEngine
from rush.tools import common


def test_djlint_runs_check_argv(monkeypatch, tmp_path: Path) -> None:
    calls: list[list[str]] = []

    def fake_run(
        argv: list[str], **_kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        calls.append(argv)
        return subprocess.CompletedProcess(argv, 0, stdout="", stderr="")

    monkeypatch.setattr(text_lint, "resolve_binary", lambda _binary: "C:/bin/djlint")
    monkeypatch.setattr(text_lint, "run_subprocess", fake_run)

    raw = DjlintEngine().run(tmp_path, [str(tmp_path / "index.html")], cwd=tmp_path)

    assert raw["exit_code"] == 0
    assert calls == [
        [
            "C:/bin/djlint",
            "--check",
            str(tmp_path / "index.html"),
        ]
    ]


def test_djlint_normalizes_clean_and_findings(monkeypatch, tmp_path: Path) -> None:
    engine = DjlintEngine()
    monkeypatch.setattr(DjlintEngine, "version", lambda _self: "1.34.1")

    clean = engine.normalize({"exit_code": 0, "stdout": ""}, tmp_path, "templates")
    finding = engine.normalize(
        {
            "exit_code": 1,
            "stdout": "index.html:1:1: H025 Tag is unclosed: <div>\n",
        },
        tmp_path,
        "templates",
    )

    assert clean["status"] == "ok"
    assert clean["tool"] == "templates"
    assert finding["status"] == "warn"
    assert len(finding["findings"]) == 1
    assert finding["findings"][0]["rule"] == "djlint"
    assert "H025" in finding["findings"][0]["message"]


def test_djlint_missing_and_timeout(monkeypatch, tmp_path: Path) -> None:
    engine = DjlintEngine()
    monkeypatch.setattr(common, "engine_on_path", lambda _binary: False)
    missing = common.run_engine(engine, tmp_path, tool_name="templates")

    monkeypatch.setattr(common, "engine_on_path", lambda _binary: True)
    monkeypatch.setattr(
        text_lint,
        "run_subprocess",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            subprocess.TimeoutExpired("djlint", 120)
        ),
    )
    timeout = common.run_engine(engine, tmp_path, tool_name="templates")

    assert missing["status"] == "skipped"
    assert timeout["status"] == "error"
    assert timeout["metadata"]["terminal_reason"] == "timeout"
