"""Phase 07.A6 Radon reference adapter fake-process matrix."""

from __future__ import annotations

import subprocess
from pathlib import Path

from rush.engines import radon
from rush.engines.radon import RadonEngine
from rush.tools import common


def test_radon_runs_cc_json_argv(monkeypatch, tmp_path: Path) -> None:
    calls: list[list[str]] = []

    def fake_run(
        argv: list[str], **_kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        calls.append(argv)
        return subprocess.CompletedProcess(argv, 0, stdout="{}", stderr="")

    monkeypatch.setattr(radon, "resolve_binary", lambda _binary: "C:/bin/radon")
    monkeypatch.setattr(radon, "run_subprocess", fake_run)

    raw = RadonEngine().run(tmp_path, [str(tmp_path / "main.py")], cwd=tmp_path)

    assert raw["exit_code"] == 0
    assert calls == [
        [
            "C:/bin/radon",
            "cc",
            "--json",
            str(tmp_path / "main.py"),
        ]
    ]


def test_radon_normalizes_clean_and_findings(monkeypatch, tmp_path: Path) -> None:
    engine = RadonEngine()
    monkeypatch.setattr(RadonEngine, "version", lambda _self: "6.0.1")

    clean = engine.normalize({"exit_code": 0, "stdout": "{}"}, tmp_path, "complexity")
    stdout_json = (
        '{"src/example.py": [{"name": "too_complex", "complexity": 12, "lineno": 5}]}'
    )
    finding = engine.normalize(
        {"exit_code": 0, "stdout": stdout_json},
        tmp_path,
        "complexity",
    )

    assert clean["status"] == "ok"
    assert clean["tool"] == "complexity"
    assert finding["status"] == "warn"
    assert len(finding["findings"]) == 1
    assert finding["findings"][0]["rule"] == "radon"
    assert finding["findings"][0]["line"] == 5


def test_radon_missing_and_timeout(monkeypatch, tmp_path: Path) -> None:
    engine = RadonEngine()
    monkeypatch.setattr(common, "engine_on_path", lambda _binary: False)
    missing = common.run_engine(engine, tmp_path, tool_name="complexity")

    monkeypatch.setattr(common, "engine_on_path", lambda _binary: True)
    monkeypatch.setattr(
        radon,
        "run_subprocess",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            subprocess.TimeoutExpired("radon", 120)
        ),
    )
    timeout = common.run_engine(engine, tmp_path, tool_name="complexity")

    assert missing["status"] == "skipped"
    assert timeout["status"] == "error"
    assert timeout["metadata"]["terminal_reason"] == "timeout"
