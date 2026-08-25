"""Main entrypoint and scenario dispatcher for Rush benchmark harness."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path

from .contracts import FixtureError, Outcome, ProbeResult
from .fixtures import load_scenarios
from .reporting import write_result

# Probe registry forward references (imported lazily or dynamically)
_PROBE_MAP: dict[str, Callable[..., ProbeResult]] = {}


def register_probe(name: str, fn: Callable[..., ProbeResult]) -> None:
    """Registers a probe runner function for a scenario probe category."""
    _PROBE_MAP[name] = fn


def get_probe_runner(probe_name: str) -> Callable[..., ProbeResult]:
    """Retrieves probe runner for category or lazy-loads probe modules."""
    if probe_name not in _PROBE_MAP:
        if probe_name == "provider":
            from . import providers

            _PROBE_MAP["provider"] = providers.run_provider_probe
        elif probe_name == "protocol":
            from . import protocol

            _PROBE_MAP["protocol"] = protocol.run_protocol_probe
        elif probe_name == "privacy":
            from . import privacy

            _PROBE_MAP["privacy"] = privacy.run_privacy_probe
        elif probe_name == "context":
            from . import context

            _PROBE_MAP["context"] = context.run_context_probe
        elif probe_name == "coordination":
            from . import coordination

            _PROBE_MAP["coordination"] = coordination.run_coordination_probe
        elif probe_name == "local":
            from . import local

            _PROBE_MAP["local"] = local.run_local_probe
        else:
            raise FixtureError(f"unknown probe: {probe_name}")
    return _PROBE_MAP[probe_name]


def build_parser() -> argparse.ArgumentParser:
    """Builds the strict argument parser for benchmark harness execution."""
    parser = argparse.ArgumentParser(
        description="Rush Deterministic Benchmark Harness",
        prog="python -m scripts.benchmarks.run",
    )
    parser.add_argument(
        "--scenario",
        type=str,
        help="Single scenario ID to execute (from scenarios.json)",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Execute all declared scenarios in scenarios.json",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("research/benchmark/run"),
        help="Destination directory for benchmark result JSON files",
    )
    parser.add_argument(
        "--model-cache",
        type=Path,
        default=None,
        help="External model cache directory for local model benchmarks (must resolve outside repo)",
    )
    parser.add_argument(
        "--allow-live-route",
        type=str,
        action="append",
        default=[],
        help="Explicit opt-in route ID for live provider invocation; repeat as needed",
    )
    parser.add_argument(
        "--provider-executable",
        type=Path,
        default=None,
        help="Explicit executable path for the selected live provider CLI",
    )
    parser.add_argument(
        "--router-url",
        action="append",
        default=[],
        help="Explicit router endpoint as NAME=URL; repeat for multiple routers",
    )
    parser.add_argument(
        "--local-runtime-executable",
        type=Path,
        action="append",
        default=[],
        help="Explicit external llama.cpp and/or onnxruntime_perf_test executable; repeat as needed",
    )
    parser.add_argument(
        "--allow-model-download",
        type=str,
        action="append",
        default=[],
        help="Explicit candidate ID for downloading local model weights into external model cache",
    )
    return parser


def run_scenario(
    scenario_id: str,
    output_root: Path,
    *,
    model_cache: Path | None = None,
    allow_live_route: list[str] | tuple[str, ...] | str | None = None,
    allow_model_download: list[str] | None = None,
    provider_executable: Path | None = None,
    local_runtime_executable: list[Path] | None = None,
    router_urls: list[str] | None = None,
) -> ProbeResult:
    """Executes a single scenario by ID and writes atomic output JSON."""
    scenarios = load_scenarios()
    if scenario_id not in scenarios:
        raise FixtureError(f"unknown scenario: {scenario_id}")

    scenario = scenarios[scenario_id]
    allowed_model_downloads = set(allow_model_download or [])
    allowed_candidate = scenario.input.get("candidate_id") in allowed_model_downloads
    if scenario.probe == "local" and allowed_candidate:
        live_input = dict(scenario.input)
        live_input.pop("mode", None)
        scenario = replace(scenario, input=live_input)
    live_route_ids = (
        (allow_live_route,)
        if isinstance(allow_live_route, str)
        else tuple(allow_live_route or [])
    )
    allowed_live_routes = set(live_route_ids)
    if scenario.probe == "provider" and "router_id" not in scenario.input:
        from .fixtures import load_provider_routes

        routes = load_provider_routes()
        provider_ids = (
            str(scenario.input.get("source_provider", "")),
            str(scenario.input.get("target_provider", "")),
        )
        selected_route = next(
            (
                route_id
                for provider_id in provider_ids
                for route_id in live_route_ids
                if route_id in routes and routes[route_id].provider_id == provider_id
            ),
            None,
        )
    else:
        selected_route = None
    if selected_route:
        live_input = dict(scenario.input)
        live_input.pop("router_id", None)
        live_input["route_id"] = selected_route
        scenario = replace(scenario, input=live_input)
    probe_fn = get_probe_runner(scenario.probe)
    result = probe_fn(
        scenario,
        model_cache=model_cache,
        allow_live_route=allowed_live_routes,
        allow_model_download=(
            scenario.input.get("candidate_id") if allowed_candidate else None
        ),
        output_root=output_root,
        provider_executable=provider_executable,
        local_runtime_executable=local_runtime_executable,
        router_urls=router_urls,
    )
    write_result(output_root, result)
    return result


def main(argv: list[str] | None = None) -> int:
    """CLI entrypoint."""
    parser = build_parser()
    args = parser.parse_args(argv)

    if not args.scenario and not args.all:
        parser.print_help()
        return 1

    try:
        scenarios = load_scenarios()
        target_ids = list(scenarios.keys()) if args.all else [args.scenario]
        results: list[ProbeResult] = []

        sys.stdout.write(f"\nRunning {len(target_ids)} benchmark scenario(s)...\n\n")
        header = f"{'Scenario ID':<48} {'Probe':<14} {'Outcome':<10} {'Duration':<10}"
        sys.stdout.write(header + "\n")
        sys.stdout.write("-" * len(header) + "\n")

        for sc_id in target_ids:
            res = run_scenario(
                sc_id,
                args.output,
                model_cache=args.model_cache,
                allow_live_route=args.allow_live_route,
                allow_model_download=args.allow_model_download,
                provider_executable=args.provider_executable,
                local_runtime_executable=args.local_runtime_executable,
                router_urls=args.router_url,
            )
            results.append(res)
            line = f"{res.scenario_id:<48} {res.probe:<14} {res.outcome.value:<10} {res.duration_ms}ms"
            sys.stdout.write(line + "\n")

        passed = sum(1 for r in results if r.outcome == Outcome.PASS)
        skipped = sum(1 for r in results if r.outcome == Outcome.SKIPPED)
        failed = sum(1 for r in results if r.outcome == Outcome.FAIL)
        inconclusive = sum(1 for r in results if r.outcome == Outcome.INCONCLUSIVE)

        # Generate formal gate decisions and final-handoff.md
        from .reporting import generate_and_write_decisions

        generate_and_write_decisions(results, args.output)

        sys.stdout.write("-" * len(header) + "\n")
        sys.stdout.write(
            f"Benchmark Summary: Total={len(results)} | Passed={passed} | Skipped={skipped} | Failed={failed} | Inconclusive={inconclusive}\n"
        )
        sys.stdout.write(f"Results & Handoff written to: {args.output.resolve()}\n\n")
        return 0 if failed == 0 else 1
    except Exception as err:  # noqa: BLE001
        sys.stderr.write(f"Benchmark error: {err}\n")
        return 1


if __name__ == "__main__":
    sys.exit(main())
