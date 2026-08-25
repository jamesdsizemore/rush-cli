"""Consumer hardware profiling, local runtime benchmarking, and Ollama exclusion probe."""

from __future__ import annotations

import datetime
import hashlib
import json
import os
import platform
import shutil
import subprocess
import time
import urllib.request
from pathlib import Path
from typing import Any

from .contracts import (
    FixtureError,
    HardwareProfile,
    Outcome,
    ProbeResult,
    Scenario,
    SourceEvidence,
)
from .fixtures import load_local_candidates


def capture_hardware_profile() -> HardwareProfile:
    """Detects and captures local host hardware capabilities."""
    os_name = f"{platform.system()} {platform.release()}"
    cpu_name = platform.processor() or platform.machine() or "Unknown CPU"

    # Detect RAM in GB
    ram_gb = 16.0
    try:
        if (
            hasattr(os, "sysconf")
            and "SC_PAGE_SIZE" in os.sysconf_names
            and "SC_PHYS_PAGES" in os.sysconf_names
        ):
            ram_gb = round(
                (os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES")) / (1024**3),
                1,
            )
        elif platform.system() == "Windows":
            import ctypes

            class MEMORYSTATUSEX(ctypes.Structure):
                _fields_ = [
                    ("dwLength", ctypes.c_ulong),
                    ("dwMemoryLoad", ctypes.c_ulong),
                    ("ullTotalPhys", ctypes.c_ulonglong),
                    ("ullAvailPhys", ctypes.c_ulonglong),
                    ("ullTotalPageFile", ctypes.c_ulonglong),
                    ("ullAvailPageFile", ctypes.c_ulonglong),
                    ("ullTotalVirtual", ctypes.c_ulonglong),
                    ("ullAvailVirtual", ctypes.c_ulonglong),
                    ("sullAvailExtendedVirtual", ctypes.c_ulonglong),
                ]

            stat = MEMORYSTATUSEX()
            stat.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
            ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat))
            ram_gb = round(stat.ullTotalPhys / (1024**3), 1)
    except Exception:  # noqa: BLE001
        ram_gb = 16.0

    # Free disk in GB
    free_disk_gb = 0.0
    try:
        usage = shutil.disk_usage(Path.cwd())
        free_disk_gb = round(usage.free / (1024**3), 1)
    except Exception:  # noqa: BLE001
        free_disk_gb = 50.0

    # Profile classification
    if ram_gb <= 8.5:
        profile_id = "C0"
    elif ram_gb <= 18.0:
        profile_id = "C1"
    else:
        profile_id = "C2"

    return HardwareProfile(
        os=os_name,
        cpu=cpu_name,
        ram_gb=ram_gb,
        gpu="Standard GPU/Integrated",
        vram_gb=0.0,
        free_disk_gb=free_disk_gb,
        runtime_version="llama.cpp/onnx-runtime",
        profile_id=profile_id,
    )


def validate_local_runtime_command(
    command: Any, model_cache: Path | None = None
) -> list[str]:
    """Validates an explicit llama.cpp or ONNX Runtime argument array."""
    if not isinstance(command, list) or not all(
        isinstance(arg, str) for arg in command
    ):
        raise FixtureError(
            "command must be a list of argument strings, not a shell string"
        )
    if not command:
        raise FixtureError("command array cannot be empty")

    exe_name = Path(command[0]).name.lower()
    if "ollama" in exe_name:
        raise FixtureError(
            "ollama runtime forbidden: use llama.cpp or onnxruntime argument arrays"
        )
    if "llama" not in exe_name and "onnxruntime" not in exe_name:
        raise FixtureError("local runtime must be llama.cpp or onnxruntime")

    if model_cache is not None:
        cache_resolved = model_cache.resolve()
        repo_root = Path.cwd().resolve()
        if repo_root in cache_resolved.parents or cache_resolved == repo_root:
            raise FixtureError(
                f"model cache inside repository denied: {cache_resolved}"
            )
    return command


def _onnx_performance_metrics(output_file: Path) -> dict[str, int | float]:
    """Extract the summary latency values emitted by onnxruntime_perf_test."""
    metrics: dict[str, int | float] = {"benchmark_samples": 0}
    for line in output_file.read_text(encoding="utf-8").splitlines():
        if "," in line and line.count(",") == 4:
            metrics["benchmark_samples"] += 1
        if not line.endswith(" s") or " Latency: " not in line:
            continue
        label, value = line.removesuffix(" s").split(" Latency: ", maxsplit=1)
        metrics[f"latency_{label.lower()}_seconds"] = float(value)
    if not metrics["benchmark_samples"] or "latency_p50_seconds" not in metrics:
        raise FixtureError("onnxruntime benchmark output omitted latency metrics")
    return metrics


def _llama_bench_metrics(output: str) -> dict[str, int | float | str]:
    """Validate JSON emitted by llama-bench and retain numeric measurements."""
    try:
        payload = json.loads(output)
    except json.JSONDecodeError as error:
        raise FixtureError("llama-bench did not emit JSON") from error
    rows = payload if isinstance(payload, list) else payload.get("benchmarks", [])
    if not isinstance(rows, list) or not rows or not isinstance(rows[0], dict):
        raise FixtureError("llama-bench JSON omitted benchmark rows")
    metrics: dict[str, int | float | str] = {"benchmark_samples": len(rows)}
    for key, value in rows[0].items():
        if isinstance(value, int | float):
            metrics[f"llama_bench_{key}"] = value
    if len(metrics) == 1:
        raise FixtureError("llama-bench JSON omitted numeric measurements")
    return metrics


def _runtime_command(
    candidate: dict[str, Any],
    weight_file: Path,
    runtime_executable: Path | list[Path] | None = None,
) -> tuple[list[str] | None, str, str]:
    """Returns an installed, format-compatible runtime command or its defer reason."""
    is_onnx = (
        weight_file.suffix.lower() == ".onnx"
        or candidate.get("quantization", "").upper() == "ONNX"
    )
    executables = (
        runtime_executable
        if isinstance(runtime_executable, list)
        else [runtime_executable]
        if runtime_executable is not None
        else []
    )
    if is_onnx:
        selected_runtime = next(
            (path for path in executables if "onnxruntime" in path.name.lower()), None
        )
        runtime_bin = (
            str(selected_runtime)
            if selected_runtime is not None
            else shutil.which("onnxruntime_perf_test")
        )
        if not runtime_bin:
            return None, "onnxruntime_perf_test", "onnxruntime-perf-test-missing"
        if selected_runtime is not None and not selected_runtime.is_file():
            return None, "onnxruntime_perf_test", "onnxruntime-perf-executable-invalid"
        return (
            [
                runtime_bin,
                "-e",
                "cpu",
                "-m",
                "times",
                "-r",
                "20",
                "-I",
                "-s",
                "-x",
                "1",
                "-y",
                "1",
                str(weight_file),
                str(weight_file.with_suffix(".benchmark.csv")),
            ],
            "onnxruntime_perf_test",
            "",
        )

    selected_runtime = next(
        (path for path in executables if "llama" in path.name.lower()), None
    )
    runtime_bin = (
        str(selected_runtime)
        if selected_runtime is not None
        else shutil.which("llama-cli") or shutil.which("llama-bench")
    )
    if not runtime_bin:
        return None, "llama.cpp", "llama-cpp-runtime-missing"
    if selected_runtime is not None and (
        not selected_runtime.is_file() or "llama" not in selected_runtime.name.lower()
    ):
        return None, "llama.cpp", "llama-cpp-executable-invalid"
    if "llama-bench" in Path(runtime_bin).name.lower():
        return (
            [
                runtime_bin,
                "-m",
                str(weight_file),
                "--offline",
                "-r",
                "3",
                "-p",
                "64",
                "-n",
                "8",
                "-ngl",
                "0",
                "-o",
                "json",
            ],
            "llama-bench",
            "",
        )
    return (
        [
            runtime_bin,
            "-m",
            str(weight_file),
            "-p",
            "Rush verification probe",
            "-n",
            "8",
        ],
        "llama.cpp",
        "",
    )


def run_local_probe(
    scenario: Scenario,
    *,
    allow_model_download: str | None = None,
    model_cache: Path | None = None,
    output_root: Path | None = None,
    **kwargs: Any,
) -> ProbeResult:
    """Executes local candidate verification and hardware profiling."""
    start_time = datetime.datetime.now(datetime.UTC).isoformat()
    t0 = time.perf_counter()

    inp = scenario.input
    candidate_id = inp.get("candidate_id", scenario.scenario_id)
    is_fixture_mode = inp.get("mode") == "fixture"

    # Capture hardware profile and optionally save hardware-profile.json
    hw = capture_hardware_profile()
    if output_root:
        hw_file = output_root / "hardware-profile.json"
        hw_file.parent.mkdir(parents=True, exist_ok=True)
        hw_file.write_text(
            json.dumps(
                {
                    "os": hw.os,
                    "cpu": hw.cpu,
                    "ram_gb": hw.ram_gb,
                    "gpu": hw.gpu,
                    "vram_gb": hw.vram_gb,
                    "free_disk_gb": hw.free_disk_gb,
                    "runtime_version": hw.runtime_version,
                    "profile_id": hw.profile_id,
                },
                indent=2,
            ),
            encoding="utf-8",
        )

    # 1. Candidate lookup in local_candidates.json
    candidates = load_local_candidates()
    cand = next((c for c in candidates if c.get("candidate_id") == candidate_id), None)
    if not cand:
        duration_ms = int((time.perf_counter() - t0) * 1000)
        return ProbeResult(
            scenario_id=scenario.scenario_id,
            probe="local",
            outcome=Outcome.DEFERRED,
            started_at=start_time,
            duration_ms=duration_ms,
            metrics={"candidate_found": False},
            fallback="unapproved-candidate-deferred",
            reproduction=f"python -m scripts.benchmarks.run --scenario {scenario.scenario_id}",
        )

    evidence = (
        SourceEvidence(
            url=f"https://huggingface.co/{cand.get('hf_repo')}",
            retrieved_at=datetime.datetime.now(datetime.UTC).date().isoformat(),
            revision=cand.get("revision", "main"),
            license_or_terms=cand.get("license", "Apache-2.0"),
        ),
    )

    # Candidate metadata and a hardware profile are planning evidence only.
    # A local benchmark requires a verified runtime invocation and model artifact.
    if is_fixture_mode or (not allow_model_download and not model_cache):
        duration_ms = int((time.perf_counter() - t0) * 1000)
        return ProbeResult(
            scenario_id=scenario.scenario_id,
            probe="local",
            outcome=Outcome.INCONCLUSIVE,
            started_at=start_time,
            duration_ms=duration_ms,
            metrics={
                "candidate_id": candidate_id,
                "target_profile": cand.get("target_profile", "C0"),
                "host_profile": hw.profile_id,
                "host_ram_gb": hw.ram_gb,
                "evidence_mode": "fixture",
            },
            evidence=evidence,
            fallback="fixture-candidate-cannot-satisfy-local-gate",
            reproduction=f"python -m scripts.benchmarks.run --scenario {scenario.scenario_id}",
        )

    # 3. Live Model Download & Execution
    if not allow_model_download or allow_model_download != candidate_id:
        duration_ms = int((time.perf_counter() - t0) * 1000)
        return ProbeResult(
            scenario_id=scenario.scenario_id,
            probe="local",
            outcome=Outcome.SKIPPED,
            started_at=start_time,
            duration_ms=duration_ms,
            metrics={"download_authorized": False},
            fallback="model-download-not-authorized",
            reproduction=f"python -m scripts.benchmarks.run --scenario {scenario.scenario_id} --allow-model-download {candidate_id}",
        )

    # Validate external model cache
    if model_cache is None:
        duration_ms = int((time.perf_counter() - t0) * 1000)
        return ProbeResult(
            scenario_id=scenario.scenario_id,
            probe="local",
            outcome=Outcome.FAIL,
            started_at=start_time,
            duration_ms=duration_ms,
            metrics={"cache_error": "missing --model-cache"},
            fallback="missing-model-cache",
            reproduction=f"python -m scripts.benchmarks.run --scenario {scenario.scenario_id} --allow-model-download {candidate_id} --model-cache <dir>",
        )

    try:
        validate_local_runtime_command(
            ["onnxruntime_perf_test", "--help"], model_cache=model_cache
        )
    except FixtureError as err:
        duration_ms = int((time.perf_counter() - t0) * 1000)
        return ProbeResult(
            scenario_id=scenario.scenario_id,
            probe="local",
            outcome=Outcome.FAIL,
            started_at=start_time,
            duration_ms=duration_ms,
            metrics={"cache_error": str(err)},
            fallback="invalid-model-cache",
            reproduction=f"python -m scripts.benchmarks.run --scenario {scenario.scenario_id}",
        )

    cand_cache = model_cache / candidate_id
    weight_file = cand_cache / cand.get("weight_file", "model.gguf")
    runtime_executable = kwargs.get("local_runtime_executable")
    cmd, runtime_kind, missing_runtime_fallback = _runtime_command(
        cand,
        weight_file,
        runtime_executable=runtime_executable,
    )
    exec_metrics: dict[str, int | float | str] = {
        "candidate_id": candidate_id,
        "target_profile": cand.get("target_profile", "C0"),
        "host_profile": hw.profile_id,
        "host_ram_gb": hw.ram_gb,
        "disk_size_mb": cand.get("disk_size_mb", 0),
        "runtime_kind": runtime_kind,
        "weight_file": str(weight_file),
        "benchmark_scope": "runtime-latency",
        "input_mode": (
            "runtime-generated-synthetic"
            if runtime_kind == "onnxruntime_perf_test"
            else "fixed-text-prompt"
        ),
    }
    runtime_timeout_s = min(900, max(30, int(cand.get("runtime_timeout_s", 120))))
    exec_metrics["runtime_timeout_s"] = runtime_timeout_s

    if cmd is None:
        duration_ms = int((time.perf_counter() - t0) * 1000)
        exec_metrics["download_ok"] = "not-attempted"
        return ProbeResult(
            scenario_id=scenario.scenario_id,
            probe="local",
            outcome=Outcome.DEFERRED,
            started_at=start_time,
            duration_ms=duration_ms,
            metrics=exec_metrics,
            evidence=evidence,
            fallback=missing_runtime_fallback,
            reproduction=f"python -m scripts.benchmarks.run --scenario {scenario.scenario_id} --allow-model-download {candidate_id} --model-cache {model_cache}",
        )

    cand_cache.mkdir(parents=True, exist_ok=True)
    expected_sha = cand.get("sha256", "")
    expected_size = cand.get("expected_size_bytes", 0)
    artifact_url = cand.get("artifact_url", "")
    if not expected_sha or not expected_size or not artifact_url:
        duration_ms = int((time.perf_counter() - t0) * 1000)
        return ProbeResult(
            scenario_id=scenario.scenario_id,
            probe="local",
            outcome=Outcome.INCONCLUSIVE,
            started_at=start_time,
            duration_ms=duration_ms,
            metrics=exec_metrics | {"evidence_mode": "candidate-manifest-incomplete"},
            evidence=evidence,
            fallback="candidate-integrity-manifest-incomplete",
            reproduction=f"python -m scripts.benchmarks.run --scenario {scenario.scenario_id}",
        )

    # The exact candidate opt-in is the network/download authorization. Requiring
    # an unrelated environment toggle made an authorized detached job silently defer.
    allow_network = allow_model_download == candidate_id
    if not weight_file.exists():
        if not allow_network:
            duration_ms = int((time.perf_counter() - t0) * 1000)
            return ProbeResult(
                scenario_id=scenario.scenario_id,
                probe="local",
                outcome=Outcome.DEFERRED,
                started_at=start_time,
                duration_ms=duration_ms,
                metrics=exec_metrics | {"download_ok": "not-attempted"},
                evidence=evidence,
                fallback="model-weight-missing-network-disabled",
                reproduction=f"python -m scripts.benchmarks.run --scenario {scenario.scenario_id} --allow-model-download {candidate_id} --model-cache {model_cache}",
            )
        temp_file = weight_file.with_suffix(f"{weight_file.suffix}.partial")
        try:
            digest = hashlib.sha256()
            with (
                urllib.request.urlopen(
                    urllib.request.Request(
                        artifact_url, headers={"User-Agent": "Rush-Benchmark/1.0"}
                    ),
                    timeout=30.0,
                ) as response,
                temp_file.open("wb") as target,
            ):
                if response.status != 200:
                    raise FixtureError(
                        f"model download returned HTTP {response.status}"
                    )
                while chunk := response.read(1024 * 1024):
                    digest.update(chunk)
                    target.write(chunk)
            if (
                temp_file.stat().st_size != expected_size
                or digest.hexdigest() != expected_sha
            ):
                raise FixtureError(
                    "downloaded artifact failed pinned size or sha256 verification"
                )
            temp_file.replace(weight_file)
        except Exception as err:  # noqa: BLE001
            temp_file.unlink(missing_ok=True)
            duration_ms = int((time.perf_counter() - t0) * 1000)
            return ProbeResult(
                scenario_id=scenario.scenario_id,
                probe="local",
                outcome=Outcome.DEFERRED,
                started_at=start_time,
                duration_ms=duration_ms,
                metrics=exec_metrics
                | {"download_ok": "failed", "download_error": type(err).__name__},
                evidence=evidence,
                fallback="model-download-or-integrity-verification-failed",
                reproduction=f"python -m scripts.benchmarks.run --scenario {scenario.scenario_id} --allow-model-download {candidate_id} --model-cache {model_cache}",
            )

    observed_sha = hashlib.file_digest(weight_file.open("rb"), "sha256").hexdigest()
    observed_size = weight_file.stat().st_size
    if observed_size != expected_size or observed_sha != expected_sha:
        duration_ms = int((time.perf_counter() - t0) * 1000)
        return ProbeResult(
            scenario_id=scenario.scenario_id,
            probe="local",
            outcome=Outcome.FAIL,
            started_at=start_time,
            duration_ms=duration_ms,
            metrics=exec_metrics
            | {"weight_size_bytes": observed_size, "weight_sha256": observed_sha},
            evidence=evidence,
            fallback="cached-model-integrity-verification-failed",
            reproduction=f"python -m scripts.benchmarks.run --scenario {scenario.scenario_id} --allow-model-download {candidate_id} --model-cache {model_cache}",
        )
    exec_metrics |= {
        "download_ok": True,
        "cache_path": str(cand_cache),
        "weight_size_bytes": observed_size,
        "weight_sha256": observed_sha,
    }

    try:
        validate_local_runtime_command(cmd, model_cache=model_cache)
        if runtime_kind == "onnxruntime_perf_test":
            Path(cmd[-1]).unlink(missing_ok=True)
        proc = subprocess.run(
            cmd,
            shell=False,
            capture_output=True,
            text=True,
            timeout=float(runtime_timeout_s),
            check=False,
        )
        exec_metrics["returncode"] = proc.returncode
        exec_metrics["runtime_bin"] = cmd[0]
        output_file = Path(cmd[-1]) if runtime_kind == "onnxruntime_perf_test" else None
        if proc.returncode != 0:
            outcome = Outcome.FAIL
            fallback = f"runtime-process-failed: exit {proc.returncode}"
            exec_metrics["stderr"] = proc.stderr[:500]
        elif output_file is not None and (
            not output_file.is_file() or output_file.stat().st_size == 0
        ):
            outcome = Outcome.FAIL
            fallback = "runtime-missing-benchmark-output"
        else:
            outcome = Outcome.PASS
            fallback = "none"
            if output_file is not None:
                exec_metrics["benchmark_output"] = str(output_file)
                exec_metrics["benchmark_output_bytes"] = output_file.stat().st_size
                exec_metrics["benchmark_output_sha256"] = hashlib.file_digest(
                    output_file.open("rb"), "sha256"
                ).hexdigest()
                exec_metrics |= _onnx_performance_metrics(output_file)
            elif runtime_kind == "llama-bench":
                exec_metrics["benchmark_output_sha256"] = hashlib.sha256(
                    proc.stdout.encode("utf-8")
                ).hexdigest()
                exec_metrics |= _llama_bench_metrics(proc.stdout)
    except Exception as err:  # noqa: BLE001
        exec_metrics["runtime_error"] = str(err)
        outcome = Outcome.FAIL
        fallback = f"runtime-execution-error: {err}"

    duration_ms = int((time.perf_counter() - t0) * 1000)
    return ProbeResult(
        scenario_id=scenario.scenario_id,
        probe="local",
        outcome=outcome,
        started_at=start_time,
        duration_ms=duration_ms,
        metrics=exec_metrics,
        evidence=evidence,
        fallback=fallback,
        reproduction=f"python -m scripts.benchmarks.run --scenario {scenario.scenario_id} --allow-model-download {candidate_id} --model-cache {model_cache}",
    )
