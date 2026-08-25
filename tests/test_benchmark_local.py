"""Tests for consumer hardware profiling, local runtime benchmarking, and Ollama rejection."""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts.benchmarks.contracts import (
    FixtureError,
    HardwareProfile,
    Outcome,
    Scenario,
)
from scripts.benchmarks.fixtures import load_local_candidates
from scripts.benchmarks.local import (
    _llama_bench_metrics,
    _onnx_performance_metrics,
    _runtime_command,
    capture_hardware_profile,
    run_local_probe,
    validate_local_runtime_command,
)


def test_onnx_performance_output_requires_samples_and_latency(tmp_path: Path):
    output = tmp_path / "result.csv"
    output.write_text(
        "model,0.0100000,1,1,0\n\nP50 Latency: 0.0100000 s\n",
        encoding="utf-8",
    )
    assert _onnx_performance_metrics(output) == {
        "benchmark_samples": 1,
        "latency_p50_seconds": 0.01,
    }


def test_llama_bench_output_requires_numeric_rows():
    assert _llama_bench_metrics('[{"avg_ts": 12.5, "n_gen": 8}]') == {
        "benchmark_samples": 1,
        "llama_bench_avg_ts": 12.5,
        "llama_bench_n_gen": 8,
    }
    with pytest.raises(FixtureError, match="omitted benchmark rows"):
        _llama_bench_metrics("[]")


def test_explicit_onnx_runtime_generates_times_mode_output(tmp_path: Path):
    runtime = tmp_path / "onnxruntime_perf_test.exe"
    runtime.touch()
    command, kind, fallback = _runtime_command(
        {"quantization": "ONNX"}, tmp_path / "model.onnx", runtime
    )
    assert kind == "onnxruntime_perf_test"
    assert fallback == ""
    assert command is not None
    assert command[1:11] == [
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
    ]
    assert command[-1].endswith("model.benchmark.csv")


def test_explicit_llama_bench_generates_offline_latency_command(tmp_path: Path):
    runtime = tmp_path / "llama-bench.exe"
    runtime.touch()
    command, kind, fallback = _runtime_command({}, tmp_path / "model.gguf", runtime)
    assert kind == "llama-bench"
    assert fallback == ""
    assert command is not None
    assert command[1:] == [
        "-m",
        str(tmp_path / "model.gguf"),
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
    ]


def test_runtime_selection_uses_matching_executable_from_explicit_list(
    tmp_path: Path,
):
    onnx = tmp_path / "onnxruntime_perf_test.exe"
    bench = tmp_path / "llama-bench.exe"
    onnx.touch()
    bench.touch()
    onnx_command, onnx_kind, _ = _runtime_command(
        {"quantization": "ONNX"}, tmp_path / "model.onnx", [bench, onnx]
    )
    llama_command, llama_kind, _ = _runtime_command(
        {}, tmp_path / "model.gguf", [onnx, bench]
    )
    assert onnx_kind == "onnxruntime_perf_test"
    assert onnx_command is not None and onnx_command[0] == str(onnx)
    assert llama_kind == "llama-bench"
    assert llama_command is not None and llama_command[0] == str(bench)


def test_hardware_profile_capture():
    profile = capture_hardware_profile()
    assert isinstance(profile, HardwareProfile)
    assert profile.os != ""
    assert profile.cpu != ""
    assert profile.ram_gb > 0.0
    assert profile.profile_id != ""


def test_unapproved_candidate_does_not_invoke_subprocess():
    scenario = Scenario(
        scenario_id="local-unapproved-candidate",
        probe="local",
        category="recovery",
        input={"candidate_id": "unapproved-random-model"},
        required_facts=(),
        expected_outcome=Outcome.DEFERRED,
    )
    res = run_local_probe(scenario, allow_model_download=None)
    assert res.outcome == Outcome.DEFERRED
    assert res.fallback == "unapproved-candidate-deferred"


def test_shell_string_and_ollama_rejected(tmp_path: Path):
    # Reject shell string
    with pytest.raises(FixtureError, match="command must be a list"):
        validate_local_runtime_command("ollama run llama3", model_cache=tmp_path)

    # Reject ollama executable
    with pytest.raises(FixtureError, match="ollama runtime forbidden"):
        validate_local_runtime_command(
            ["ollama", "run", "llama3"], model_cache=tmp_path
        )

    # Reject repo-local cache directory
    repo_local_cache = Path.cwd() / "my_models"
    with pytest.raises(FixtureError, match="model cache inside repository denied"):
        validate_local_runtime_command(
            ["llama-cli", "-m", "model.gguf"], model_cache=repo_local_cache
        )


def test_local_candidates_fixture():
    candidates = load_local_candidates()
    assert len(candidates) >= 4
    for cand in candidates:
        assert "candidate_id" in cand
        assert "hf_repo" in cand
        assert len(cand["revision"]) == 40
        assert cand["artifact_url"].startswith("https://huggingface.co/")
        assert len(cand["sha256"]) == 64
        assert cand["expected_size_bytes"] > 0
        assert 30 <= cand["runtime_timeout_s"] <= 900
        assert "license" in cand
        assert "target_profile" in cand


def test_benchmark_fixtures_are_independent_of_working_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.chdir(tmp_path)
    assert load_local_candidates()


def test_local_candidate_metadata_never_passes_as_a_benchmark(tmp_path: Path):
    candidate = load_local_candidates()[0]
    result = run_local_probe(
        Scenario(
            scenario_id="local-fixture-metadata",
            probe="local",
            category="recovery",
            input={"candidate_id": candidate["candidate_id"], "mode": "fixture"},
            required_facts=(),
            expected_outcome=Outcome.INCONCLUSIVE,
        ),
        output_root=tmp_path,
    )
    assert result.outcome == Outcome.INCONCLUSIVE
    assert result.metrics["evidence_mode"] == "fixture"
    assert (tmp_path / "hardware-profile.json").exists()


def test_unverified_cached_model_is_rejected_before_runtime_execution(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    candidate = load_local_candidates()[0]
    cache = tmp_path / "external-cache"
    model_dir = cache / candidate["candidate_id"]
    model_dir.mkdir(parents=True)
    (model_dir / candidate["weight_file"]).write_bytes(b"unverified model bytes")
    monkeypatch.setattr("shutil.which", lambda _name: "mock-onnxruntime_perf_test")

    def runtime_must_not_run(*_args: object, **_kwargs: object) -> None:
        raise AssertionError(
            "runtime must not run before artifact integrity verification"
        )

    monkeypatch.setattr("subprocess.run", runtime_must_not_run)
    result = run_local_probe(
        Scenario(
            scenario_id="local-unverified-cache",
            probe="local",
            category="recovery",
            input={"candidate_id": candidate["candidate_id"]},
            required_facts=(),
            expected_outcome=Outcome.FAIL,
        ),
        allow_model_download=candidate["candidate_id"],
        model_cache=cache,
    )
    assert result.outcome == Outcome.FAIL
    assert result.fallback == "cached-model-integrity-verification-failed"


def test_missing_onnx_runtime_defers_without_model_download(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    candidate = load_local_candidates()[0]
    candidate_id = candidate["candidate_id"]
    cache = tmp_path / "external-cache"
    cache.mkdir()

    monkeypatch.setattr("shutil.which", lambda _name: None)

    def fail_if_networked(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("local runtime discovery must precede model download")

    monkeypatch.setattr("urllib.request.urlopen", fail_if_networked)

    result = run_local_probe(
        Scenario(
            scenario_id="local-onnx-runtime-missing",
            probe="local",
            category="recovery",
            input={"candidate_id": candidate_id},
            required_facts=(),
            expected_outcome=Outcome.DEFERRED,
        ),
        allow_model_download=candidate_id,
        model_cache=cache,
    )

    assert result.outcome == Outcome.DEFERRED
    assert result.fallback == "onnxruntime-perf-test-missing"


def test_candidate_opt_in_is_the_download_authorization(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    candidate = load_local_candidates()[0]
    cache = tmp_path / "external-cache"
    monkeypatch.setattr("shutil.which", lambda _name: "mock-onnxruntime_perf_test")

    class Response:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *_args: object) -> None:
            return None

        def read(self, _size: int) -> bytes:
            return b""

    called = False

    def authorize_download(*_args: object, **_kwargs: object) -> Response:
        nonlocal called
        called = True
        return Response()

    monkeypatch.setattr("urllib.request.urlopen", authorize_download)
    result = run_local_probe(
        Scenario(
            scenario_id="local-download-authorized",
            probe="local",
            category="recovery",
            input={"candidate_id": candidate["candidate_id"]},
            required_facts=(),
            expected_outcome=Outcome.DEFERRED,
        ),
        allow_model_download=candidate["candidate_id"],
        model_cache=cache,
    )

    assert called is True
    assert result.fallback == "model-download-or-integrity-verification-failed"
