"""Phase 00 shared local-subprocess safety contract."""

from __future__ import annotations

import subprocess
from pathlib import Path

from rush.tools import common


def test_run_subprocess_uses_a_bounded_redacted_no_shell_process(
    monkeypatch, tmp_path: Path
) -> None:
    calls: list[tuple[list[str], dict[str, object]]] = []

    def fake_run(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        calls.append((argv, kwargs))
        return subprocess.CompletedProcess(
            argv,
            0,
            stdout="token=super-secret " + ("x" * 200),
            stderr="password=hunter2",
        )

    monkeypatch.setattr(common.subprocess, "run", fake_run)
    monkeypatch.setattr(common, "MAX_SUBPROCESS_OUTPUT_CHARS", 64)

    result = common.run_subprocess(
        ["fixture-engine", "--json"], cwd=tmp_path, timeout=7
    )

    assert calls == [
        (
            ["fixture-engine", "--json"],
            {
                "cwd": str(tmp_path),
                "timeout": 7,
                "stdin": subprocess.DEVNULL,
                "capture_output": True,
                "text": True,
                "env": None,
                "check": False,
                "shell": False,
            },
        )
    ]
    assert result.stdout.endswith("[TRUNCATED]")
    assert "super-secret" not in result.stdout
    assert "hunter2" not in result.stderr
    assert "[REDACTED]" in result.stderr
