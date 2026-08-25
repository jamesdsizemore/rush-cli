"""Detached, durable benchmark job execution for Windows and POSIX hosts."""

from __future__ import annotations

import datetime
import json
import os
import subprocess
import sys
import time
import uuid
from pathlib import Path
from typing import Any

JOB_SCHEMA_VERSION = 1
_WINDOWS_DETACH_FLAGS = (
    0x00000008 | 0x00000200
)  # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP


def _utc_now() -> str:
    return datetime.datetime.now(datetime.UTC).isoformat()


def _write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8"
    )
    os.replace(temporary, path)


def _read_job(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def create_job(
    *,
    job_root: Path,
    argv: list[str],
    output: Path,
    working_directory: Path | None = None,
) -> Path:
    """Persist a benchmark request before any child process is launched."""
    job_id = f"benchmark-{uuid.uuid4().hex}"
    job_path = job_root.resolve() / f"{job_id}.json"
    payload = {
        "schema_version": JOB_SCHEMA_VERSION,
        "job_id": job_id,
        "state": "queued",
        "created_at": _utc_now(),
        "updated_at": _utc_now(),
        "argv": list(argv),
        "output": str(output.resolve()),
        "working_directory": str((working_directory or Path.cwd()).resolve()),
        "log_path": str(job_root.resolve() / f"{job_id}.log"),
    }
    _write_json_atomic(job_path, payload)
    return job_path


def launch_job(job_path: Path) -> dict[str, Any]:
    """Launch a worker without retaining a pipe, handle, or monitoring loop."""
    job_path = job_path.resolve()
    job = _read_job(job_path)
    log_path = Path(job["log_path"]).resolve()
    log_path.parent.mkdir(parents=True, exist_ok=True)
    creationflags = _WINDOWS_DETACH_FLAGS if os.name == "nt" else 0
    with log_path.open("ab", buffering=0) as log_file:
        process = subprocess.Popen(
            [sys.executable, "-m", "scripts.benchmarks.worker", "--job", str(job_path)],
            cwd=job["working_directory"],
            stdin=subprocess.DEVNULL,
            stdout=log_file,
            stderr=subprocess.STDOUT,
            close_fds=True,
            creationflags=creationflags,
            start_new_session=os.name != "nt",
        )
    # The worker waits for this persisted PID before executing. That handshake
    # prevents a fast worker from being overwritten back to `started`.
    job.update({"state": "started", "pid": process.pid, "updated_at": _utc_now()})
    _write_json_atomic(job_path, job)
    return job


def start_job(
    *,
    job_root: Path,
    argv: list[str],
    output: Path,
    working_directory: Path | None = None,
) -> dict[str, Any]:
    """Create then immediately detach a benchmark worker process."""
    job_path = create_job(
        job_root=job_root,
        argv=argv,
        output=output,
        working_directory=working_directory,
    )
    return launch_job(job_path)


def run_job(job_path: Path, *, wait_for_pid: bool = False) -> int:
    """Worker entrypoint; writes terminal state even when benchmark execution fails."""
    job_path = job_path.resolve()
    job = _read_job(job_path)
    if wait_for_pid:
        for _ in range(200):
            job = _read_job(job_path)
            if isinstance(job.get("pid"), int):
                break
            time.sleep(0.05)
        else:
            job.update(
                {
                    "state": "failed",
                    "exit_code": 1,
                    "error": "worker-launch-handshake-timeout",
                    "completed_at": _utc_now(),
                    "updated_at": _utc_now(),
                }
            )
            _write_json_atomic(job_path, job)
            return 1
    job.update({"state": "running", "started_at": _utc_now(), "updated_at": _utc_now()})
    _write_json_atomic(job_path, job)
    try:
        from .run import main as benchmark_main

        exit_code = benchmark_main(list(job["argv"]))
        job.update(
            {
                "state": "completed" if exit_code == 0 else "failed",
                "exit_code": exit_code,
                "completed_at": _utc_now(),
                "updated_at": _utc_now(),
            }
        )
        _write_json_atomic(job_path, job)
        return exit_code
    except Exception as error:  # noqa: BLE001
        job.update(
            {
                "state": "failed",
                "exit_code": 1,
                "error": f"{type(error).__name__}: {error}",
                "completed_at": _utc_now(),
                "updated_at": _utc_now(),
            }
        )
        _write_json_atomic(job_path, job)
        return 1


def read_job(job_path: Path) -> dict[str, Any]:
    """Read durable job state only; never attaches to a child process."""
    return _read_job(job_path.resolve())
