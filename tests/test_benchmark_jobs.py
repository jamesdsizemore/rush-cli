"""Tests for detached benchmark job persistence and execution boundaries."""

from __future__ import annotations

import json
from pathlib import Path

from scripts.benchmarks import jobs


def test_start_job_persists_request_and_uses_detached_worker(
    tmp_path: Path, monkeypatch
) -> None:
    captured: dict[str, object] = {}

    class Process:
        pid = 4242

    def fake_popen(*args, **kwargs):
        captured["args"] = args
        captured["kwargs"] = kwargs
        return Process()

    monkeypatch.setattr(jobs.subprocess, "Popen", fake_popen)
    job = jobs.start_job(
        job_root=tmp_path / "jobs",
        argv=["--scenario", "local-qwen2.5-coder-7b-c2"],
        output=tmp_path / "output",
        working_directory=tmp_path,
    )

    assert job["state"] == "started"
    assert job["pid"] == 4242
    assert captured["args"] == (
        [
            jobs.sys.executable,
            "-m",
            "scripts.benchmarks.worker",
            "--job",
            str((tmp_path / "jobs" / f"{job['job_id']}.json").resolve()),
        ],
    )
    kwargs = captured["kwargs"]
    assert kwargs["stdin"] == jobs.subprocess.DEVNULL
    assert kwargs["stderr"] == jobs.subprocess.STDOUT
    assert kwargs["close_fds"] is True
    persisted = json.loads((tmp_path / "jobs" / f"{job['job_id']}.json").read_text())
    assert persisted["state"] == "started"
    assert persisted["argv"] == ["--scenario", "local-qwen2.5-coder-7b-c2"]


def test_worker_writes_terminal_state(tmp_path: Path, monkeypatch) -> None:
    job_path = jobs.create_job(
        job_root=tmp_path / "jobs",
        argv=["--scenario", "local-bge-small-c0"],
        output=tmp_path / "output",
    )
    monkeypatch.setattr("scripts.benchmarks.run.main", lambda _argv: 0)

    assert jobs.run_job(job_path) == 0
    assert jobs.read_job(job_path)["state"] == "completed"
    assert jobs.read_job(job_path)["exit_code"] == 0
