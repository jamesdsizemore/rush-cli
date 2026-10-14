"""Phase 07.A4 TypeScript compiler reference adapter fake-process matrix."""

from __future__ import annotations

import subprocess
from pathlib import Path

from rush.engines import tsc
from rush.engines.tsc import TscEngine
from rush.tools import common


def test_tsc_runs_noemit_argv(monkeypatch, tmp_path: Path) -> None:
    """T12 A9.5: one `tsc -p <scoped> --noEmit --listFiles --pretty false`
    per owner, cwd the owner directory (no-config: the root), with the
    scoped config in the owned temporary directory, removed afterwards."""
    root = tmp_path.resolve()
    (root / "main.ts").write_text("export const x = 1;\n", encoding="utf-8")
    calls: list[tuple[list[str], object]] = []

    def fake_run(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        calls.append((argv, kwargs.get("cwd")))
        return subprocess.CompletedProcess(argv, 0, stdout="", stderr="")

    monkeypatch.setattr(tsc, "resolve_binary", lambda _binary: "C:/bin/tsc")
    monkeypatch.setattr(tsc, "run_subprocess", fake_run)

    raw = TscEngine().run(root / "main.ts", [])

    assert raw["exit_code"] == 0
    [(argv, cwd)] = calls
    assert argv[:2] == ["C:/bin/tsc", "-p"]
    assert argv[3:] == ["--noEmit", "--listFiles", "--pretty", "false"]
    scoped = Path(argv[2])
    assert scoped.name == "g0.tsconfig.json"
    assert scoped.parent.parent == root / ".rush" / "tmp"
    assert scoped.parent.name.startswith("tsc-")
    assert cwd == root
    assert list((root / ".rush" / "tmp").iterdir()) == []


def test_tsc_normalizes_clean_and_findings(monkeypatch, tmp_path: Path) -> None:
    engine = TscEngine()
    monkeypatch.setattr(TscEngine, "version", lambda _self: "5.5.4")

    clean = engine.normalize(
        {"exit_code": 0, "stdout": "", "stderr": ""},
        tmp_path,
        "typecheck",
    )
    findings_stdout = "src/example.ts(7,3): error TS2322: Type 'string' is not assignable to type 'number'.\n"
    finding = engine.normalize(
        {"exit_code": 2, "stdout": findings_stdout, "stderr": ""},
        tmp_path,
        "typecheck",
    )
    error = engine.normalize(
        {"exit_code": 1, "stdout": "", "stderr": "Cannot find tsconfig.json"},
        tmp_path,
        "typecheck",
    )

    assert clean["status"] == "ok"
    assert clean["tool"] == "typecheck"
    assert finding["status"] == "fail"
    assert len(finding["findings"]) == 1
    assert finding["findings"][0]["rule"] == "TS2322"
    assert finding["findings"][0]["line"] == 7
    assert finding["findings"][0]["column"] == 3
    assert error["status"] == "error"


def test_tsc_missing_and_timeout(monkeypatch, tmp_path: Path) -> None:
    # T12: tsc only spawns when there is a TypeScript file to analyze.
    (tmp_path / "main.ts").write_text("export const x = 1;\n", encoding="utf-8")
    engine = TscEngine()
    monkeypatch.setattr(common, "engine_on_path", lambda _binary: False)
    missing = common.run_engine(engine, tmp_path, tool_name="typecheck")

    monkeypatch.setattr(common, "engine_on_path", lambda _binary: True)
    monkeypatch.setattr(
        tsc,
        "run_subprocess",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            subprocess.TimeoutExpired("tsc", 120)
        ),
    )
    timeout = common.run_engine(engine, tmp_path, tool_name="typecheck")

    assert missing["status"] == "skipped"
    assert timeout["status"] == "error"
    assert timeout["metadata"]["terminal_reason"] == "timeout"
    assert list((tmp_path / ".rush" / "tmp").iterdir()) == []
