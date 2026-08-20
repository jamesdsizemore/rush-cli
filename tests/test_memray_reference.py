"""Phase 19 Memray reference adapter fake-process matrix."""

from __future__ import annotations

import subprocess
from pathlib import Path

from rush.engines import memray
from rush.engines.memray import MemrayEngine


def test_memray_runs_isolated_argv(monkeypatch, tmp_path: Path) -> None:
    calls: list[list[str]] = []

    def fake_run(
        argv: list[str], **_kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        calls.append(argv)
        return subprocess.CompletedProcess(argv, 0, stdout="[]", stderr="")

    monkeypatch.setattr(memray, "resolve_binary", lambda _binary: "C:/bin/memray")
    monkeypatch.setattr(memray, "run_subprocess", fake_run)

    raw = MemrayEngine().run(tmp_path, [], cwd=tmp_path)

    assert raw["exit_code"] == 0
    assert calls == [
        [
            "C:/bin/memray",
            "summary",
            "--json",
            "memray-profile.bin",
        ]
    ]


def test_memray_normalizes_clean_and_findings(monkeypatch, tmp_path: Path) -> None:
    engine = MemrayEngine()
    monkeypatch.setattr(MemrayEngine, "version", lambda _self: "1.13.4")

    clean = engine.normalize({"exit_code": 0, "findings": []}, tmp_path, "metrics")
    assert clean["status"] == "ok"
    assert clean["findings"] == []

    failing = engine.normalize(
        {
            "exit_code": 0,
            "findings": [
                {
                    "name": "load_heavy_cache",
                    "location": "src/cache.py",
                    "line": 45,
                    "total_bytes": 104857600,
                }
            ],
        },
        tmp_path,
        "metrics",
    )
    assert failing["status"] == "warn"
    assert len(failing["findings"]) == 1
    assert "memray/high-memory-allocation" in failing["findings"][0]["rule"]
