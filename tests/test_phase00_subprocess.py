"""Phase 00 subprocess-boundary tests."""

from __future__ import annotations

import subprocess
from pathlib import Path

from rush.engines import base as engine_base


class _VersionEngine(engine_base.Engine):
    name = "fixture-engine"
    binary = "fixture-engine"
    file_extensions = ()

    def run(
        self, path: Path, args: list[str], cwd: Path | None = None
    ) -> engine_base.EngineResult:
        return {"exit_code": 0}


def test_engine_version_uses_shared_bounded_subprocess(monkeypatch) -> None:
    calls: list[tuple[list[str], int]] = []

    def fake_run_subprocess(argv: list[str], *, timeout: int, **_kwargs):
        calls.append((argv, timeout))
        return subprocess.CompletedProcess(
            argv, 0, stdout="fixture-engine v1.2.3\n", stderr=""
        )

    monkeypatch.setattr(
        engine_base, "resolve_binary", lambda _binary: "C:/bin/fixture-engine"
    )
    monkeypatch.setattr(engine_base, "run_subprocess", fake_run_subprocess)

    assert _VersionEngine().version() == "1.2.3"
    assert calls == [(["C:/bin/fixture-engine", "--version"], 10)]
