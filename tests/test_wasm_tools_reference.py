"""Phase 19 wasm-tools reference adapter fake-process matrix."""

from __future__ import annotations

import subprocess
from pathlib import Path

from rush.engines import wasm_tools
from rush.engines.wasm_tools import WasmToolsEngine


def test_wasm_tools_runs_isolated_argv(monkeypatch, tmp_path: Path) -> None:
    calls: list[list[str]] = []

    def fake_run(
        argv: list[str], **_kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        calls.append(argv)
        return subprocess.CompletedProcess(argv, 0, stdout="", stderr="")

    monkeypatch.setattr(
        wasm_tools, "resolve_binary", lambda _binary: "C:/bin/wasm-tools"
    )
    monkeypatch.setattr(wasm_tools, "run_subprocess", fake_run)

    raw = WasmToolsEngine().run(tmp_path, [], cwd=tmp_path)

    assert raw["exit_code"] == 0
    assert calls == [
        [
            "C:/bin/wasm-tools",
            "validate",
            str(tmp_path),
        ]
    ]


def test_wasm_tools_normalizes_clean_and_findings(monkeypatch, tmp_path: Path) -> None:
    engine = WasmToolsEngine()
    monkeypatch.setattr(WasmToolsEngine, "version", lambda _self: "1.218.0")

    clean = engine.normalize({"exit_code": 0, "findings": []}, tmp_path, "lint")
    assert clean["status"] == "ok"
    assert clean["findings"] == []

    failing = engine.normalize(
        {
            "exit_code": 1,
            "findings": [
                {
                    "file": "module.wasm",
                    "error": "unexpected end of section 1 (code)",
                }
            ],
        },
        tmp_path,
        "lint",
    )
    assert failing["status"] == "fail"
    assert len(failing["findings"]) == 1
    assert "wasm-tools/validate" in failing["findings"][0]["rule"]
