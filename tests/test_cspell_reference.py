"""Phase 19 CSpell reference adapter fake-process matrix."""

from __future__ import annotations

import subprocess
from pathlib import Path

from rush.engines import cspell
from rush.engines.cspell import CspellEngine


def test_cspell_runs_isolated_argv(monkeypatch, tmp_path: Path) -> None:
    calls: list[list[str]] = []

    def fake_run(
        argv: list[str], **_kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        calls.append(argv)
        return subprocess.CompletedProcess(argv, 0, stdout="{}", stderr="")

    monkeypatch.setattr(cspell, "resolve_binary", lambda _binary: "C:/bin/cspell")
    monkeypatch.setattr(cspell, "run_subprocess", fake_run)

    raw = CspellEngine().run(tmp_path, [], cwd=tmp_path)

    assert raw["exit_code"] == 0
    assert calls == [
        [
            "C:/bin/cspell",
            "lint",
            "--reporter",
            "@cspell/cspell-json-reporter",
            str(tmp_path),
        ]
    ]


def test_cspell_normalizes_clean_and_findings(monkeypatch, tmp_path: Path) -> None:
    engine = CspellEngine()
    monkeypatch.setattr(CspellEngine, "version", lambda _self: "8.13.0")

    clean = engine.normalize({"exit_code": 0, "findings": []}, tmp_path, "lint")
    assert clean["status"] == "ok"
    assert clean["findings"] == []

    failing = engine.normalize(
        {
            "exit_code": 1,
            "findings": [
                {
                    "uri": "src/app.ts",
                    "row": 14,
                    "col": 8,
                    "text": "unknwonIdentifier",
                }
            ],
        },
        tmp_path,
        "lint",
    )
    assert failing["status"] == "warn"
    assert len(failing["findings"]) == 1
    assert "cspell/unknown-word" in failing["findings"][0]["rule"]
