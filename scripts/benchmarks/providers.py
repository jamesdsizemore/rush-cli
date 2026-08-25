"""Provider, OAuth/CLI, and router probe runner."""

from __future__ import annotations

import datetime
import hashlib
import json
import os
import re
import shutil
import subprocess
import time
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from .contracts import (
    Outcome,
    ProbeResult,
    RouteDescriptor,
    Scenario,
    SourceEvidence,
)
from .fixtures import load_provider_routes, load_routers


def redact_text(text: str, patterns: list[str]) -> tuple[str, list[str]]:
    """Redacts secret patterns from text and returns cleaned text with list of redacted labels."""
    redactions: list[str] = []
    cleaned = text
    for pat in patterns:
        for match in re.finditer(pat, text):
            matched_str = match.group(0)
            redactions.append(matched_str[:4] + "***")
            cleaned = cleaned.replace(matched_str, "[REDACTED]")
    return cleaned, redactions


def _router_environment_key(router_name: str, suffix: str) -> str:
    normalized = re.sub(r"[^A-Za-z0-9]", "_", router_name).upper()
    return f"RUSH_BENCHMARK_{normalized}_{suffix}"


def _authorized_route_ids(
    allow_live_route: str | list[str] | tuple[str, ...] | None,
) -> set[str]:
    """Normalize repeated explicit live-route authorizations."""
    if allow_live_route is None:
        return set()
    if isinstance(allow_live_route, str):
        return {allow_live_route}
    return set(allow_live_route)


def _cli_invocation(command: list[str]) -> list[str]:
    """Use the Windows command interpreter only for npm .cmd shims."""
    executable_path = Path(shutil.which(command[0]) or command[0])
    if os.name == "nt":
        cmd_shim = executable_path.with_suffix(".cmd")
        if executable_path.suffix.lower() in {".bat", ".cmd"}:
            return ["cmd.exe", "/d", "/c", *command]
        if not executable_path.suffix and cmd_shim.is_file():
            command = [str(cmd_shim), *command[1:]]
            return ["cmd.exe", "/d", "/c", *command]
    return command


def _cli_error_category(stderr: str) -> str:
    """Expose a safe, non-secret CLI failure category in benchmark evidence."""
    lowered = stderr.lower()
    if "unexpected argument" in lowered or "invalid value" in lowered:
        return "cli-argument-error"
    if "config" in lowered:
        return "cli-config-error"
    if "auth" in lowered or "login" in lowered:
        return "cli-authentication-error"
    if "not recognized" in lowered or "not found" in lowered:
        return "cli-command-error"
    return "cli-nonzero-exit"


def _run_deepseek_api_probe(
    scenario: Scenario, route: RouteDescriptor, start_time: str, t0: float
) -> ProbeResult:
    """Run the official DeepSeek OpenAI-compatible API only with its local key."""
    api_key = os.environ.get("DEEPSEEK_API_KEY")
    reproduction = (
        f"python -m scripts.benchmarks.run --scenario {scenario.scenario_id} "
        f"--allow-live-route {route.route_id}"
    )
    if not api_key:
        return ProbeResult(
            scenario_id=scenario.scenario_id,
            probe="provider",
            outcome=Outcome.DEFERRED,
            started_at=start_time,
            duration_ms=int((time.perf_counter() - t0) * 1000),
            metrics={
                "evidence_mode": "api-key-not-configured",
                "route_id": route.route_id,
            },
            fallback="deepseek-api-key-not-configured",
            reproduction=reproduction,
        )
    request_body = json.dumps(
        {
            "model": "deepseek-chat",
            "messages": [
                {
                    "role": "user",
                    "content": "Reply with exactly BENCHMARK_OK. Do not use tools or modify state.",
                }
            ],
            "max_tokens": 8,
        }
    ).encode("utf-8")
    try:
        request = urllib.request.Request(
            "https://api.deepseek.com/v1/chat/completions",
            data=request_body,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=90.0) as response:
            response_body = response.read().decode("utf-8")
            marker_present = response.status == 200 and "BENCHMARK_OK" in response_body
    except Exception as error:  # noqa: BLE001
        return ProbeResult(
            scenario_id=scenario.scenario_id,
            probe="provider",
            outcome=Outcome.FAIL,
            started_at=start_time,
            duration_ms=int((time.perf_counter() - t0) * 1000),
            metrics={"route_id": route.route_id, "error_type": type(error).__name__},
            fallback="deepseek-api-request-failed",
            reproduction=reproduction,
        )
    return ProbeResult(
        scenario_id=scenario.scenario_id,
        probe="provider",
        outcome=Outcome.PASS if marker_present else Outcome.INCONCLUSIVE,
        started_at=start_time,
        duration_ms=int((time.perf_counter() - t0) * 1000),
        metrics={
            "evidence_mode": "live-api",
            "route_id": route.route_id,
            "response_marker_present": marker_present,
            "response_fingerprint": hashlib.sha256(response_body.encode()).hexdigest(),
        },
        evidence=(
            SourceEvidence(
                url=route.official_docs_url,
                retrieved_at=datetime.datetime.now(datetime.UTC).date().isoformat(),
                license_or_terms=route.terms_url,
            ),
        ),
        fallback="none" if marker_present else "response-marker-missing",
        reproduction=reproduction,
    )


def run_router_probe(
    scenario: Scenario,
    *,
    allow_live_route: str | list[str] | tuple[str, ...] | None = None,
    router_urls: list[str] | None = None,
) -> ProbeResult:
    """Probe one explicitly configured OpenAI-compatible router endpoint."""
    start_time = datetime.datetime.now(datetime.UTC).isoformat()
    t0 = time.perf_counter()
    router_name = str(scenario.input["router_id"])
    router = load_routers().get(router_name)
    route_id = router.get("route_id") if router else None
    reproduction = (
        f"python -m scripts.benchmarks.run --scenario {scenario.scenario_id} "
        f"--allow-live-route {route_id}"
    )
    if not router or not route_id:
        return ProbeResult(
            scenario_id=scenario.scenario_id,
            probe="provider",
            outcome=Outcome.FAIL,
            started_at=start_time,
            duration_ms=int((time.perf_counter() - t0) * 1000),
            metrics={"router_name": router_name},
            fallback="router-descriptor-missing",
            reproduction=reproduction,
        )
    if route_id not in _authorized_route_ids(allow_live_route):
        return ProbeResult(
            scenario_id=scenario.scenario_id,
            probe="provider",
            outcome=Outcome.SKIPPED,
            started_at=start_time,
            duration_ms=int((time.perf_counter() - t0) * 1000),
            metrics={"router_name": router_name, "live_skipped": True},
            fallback="router-live-route-not-authorized",
            reproduction=reproduction,
        )
    cli_metrics: dict[str, Any] = {}
    cli_redactions: list[str] = []
    cli_command = router.get("cli_command")
    cli_marker = router.get("cli_marker")
    if cli_command and cli_marker:
        try:
            cli_proc = subprocess.run(
                _cli_invocation(list(cli_command)),
                shell=False,
                capture_output=True,
                text=True,
                timeout=30.0,
                check=False,
            )
        except OSError as error:
            return ProbeResult(
                scenario_id=scenario.scenario_id,
                probe="provider",
                outcome=Outcome.FAIL,
                started_at=start_time,
                duration_ms=int((time.perf_counter() - t0) * 1000),
                metrics={
                    "router_name": router_name,
                    "error_type": type(error).__name__,
                },
                fallback="router-cli-invocation-failed",
                reproduction=reproduction,
            )
        cli_output, cli_redactions = redact_text(
            cli_proc.stdout + cli_proc.stderr, [r"sk-[A-Za-z0-9_-]{20,}"]
        )
        if cli_proc.returncode or cli_marker not in cli_output:
            return ProbeResult(
                scenario_id=scenario.scenario_id,
                probe="provider",
                outcome=Outcome.FAIL if cli_proc.returncode else Outcome.INCONCLUSIVE,
                started_at=start_time,
                duration_ms=int((time.perf_counter() - t0) * 1000),
                metrics={
                    "router_name": router_name,
                    "cli_exit_code": cli_proc.returncode,
                    "cli_marker_present": cli_marker in cli_output,
                },
                redactions=tuple(cli_redactions),
                fallback="router-cli-command-failed",
                reproduction=reproduction,
            )
        cli_metrics = {"cli_marker_present": True, "cli_exit_code": cli_proc.returncode}
        if not router.get("endpoint_required", True):
            return ProbeResult(
                scenario_id=scenario.scenario_id,
                probe="provider",
                outcome=Outcome.PASS,
                started_at=start_time,
                duration_ms=int((time.perf_counter() - t0) * 1000),
                metrics={
                    "router_name": router_name,
                    "route_id": route_id,
                    "evidence_mode": "live-router-cli",
                    "cli_marker_present": True,
                },
                redactions=tuple(cli_redactions),
                fallback="none",
                reproduction=reproduction,
            )
    configured_urls = {}
    for item in router_urls or []:
        name, separator, url = item.partition("=")
        if separator and name and url:
            configured_urls[name] = url
    endpoint = configured_urls.get(
        router_name, os.environ.get(_router_environment_key(router_name, "URL"), "")
    ).rstrip("/")
    if not endpoint:
        return ProbeResult(
            scenario_id=scenario.scenario_id,
            probe="provider",
            outcome=Outcome.DEFERRED,
            started_at=start_time,
            duration_ms=int((time.perf_counter() - t0) * 1000),
            metrics={
                "router_name": router_name,
                "evidence_mode": "endpoint-not-configured",
            },
            fallback="router-endpoint-not-configured",
            reproduction=reproduction,
        )
    parsed = urllib.parse.urlsplit(endpoint)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return ProbeResult(
            scenario_id=scenario.scenario_id,
            probe="provider",
            outcome=Outcome.FAIL,
            started_at=start_time,
            duration_ms=int((time.perf_counter() - t0) * 1000),
            metrics={"router_name": router_name},
            fallback="router-endpoint-invalid",
            reproduction=reproduction,
        )
    headers = {"Accept": "application/json"}
    api_key = os.environ.get(_router_environment_key(router_name, "API_KEY"))
    if router_name == "OmniRoute":
        api_key = (
            api_key
            or os.environ.get("OMNIROUTE_API_KEY")
            or os.environ.get("ROUTER_API_KEY")
        )
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    try:
        with urllib.request.urlopen(
            urllib.request.Request(f"{endpoint}/v1/models", headers=headers),
            timeout=15.0,
        ) as response:
            payload = json.loads(response.read().decode("utf-8"))
            models = payload.get("data", [])
            if response.status != 200 or not isinstance(models, list) or not models:
                raise ValueError("router models response was empty or malformed")
    except Exception as error:  # noqa: BLE001
        return ProbeResult(
            scenario_id=scenario.scenario_id,
            probe="provider",
            outcome=Outcome.FAIL,
            started_at=start_time,
            duration_ms=int((time.perf_counter() - t0) * 1000),
            metrics={"router_name": router_name, "error_type": type(error).__name__},
            fallback="router-live-probe-failed",
            reproduction=reproduction,
        )
    evidence = (
        SourceEvidence(
            url=router["evidence_url"],
            retrieved_at=datetime.datetime.now(datetime.UTC).date().isoformat(),
            license_or_terms=router["terms_url"],
        ),
    )
    return ProbeResult(
        scenario_id=scenario.scenario_id,
        probe="provider",
        outcome=Outcome.PASS,
        started_at=start_time,
        duration_ms=int((time.perf_counter() - t0) * 1000),
        metrics={
            "router_name": router_name,
            "route_id": route_id,
            "evidence_mode": "live-router",
            "endpoint": f"{parsed.scheme}://{parsed.netloc}{parsed.path}",
            "model_count": len(models),
            **cli_metrics,
        },
        evidence=evidence,
        redactions=tuple(cli_redactions),
        fallback="none",
        reproduction=reproduction,
    )


def run_provider_probe(
    scenario: Scenario,
    *,
    allow_live_route: str | list[str] | tuple[str, ...] | None = None,
    custom_route: RouteDescriptor | None = None,
    provider_executable: Path | None = None,
    **kwargs: Any,
) -> ProbeResult:
    """Executes descriptor-driven provider route or returns fixture mode result."""
    start_time = datetime.datetime.now(datetime.UTC).isoformat()
    t0 = time.perf_counter()

    if "router_id" in scenario.input:
        return run_router_probe(
            scenario,
            allow_live_route=allow_live_route,
            router_urls=kwargs.get("router_urls"),
        )

    # 2. Handle provider route evaluation
    route_id = scenario.input.get("route_id") or scenario.scenario_id
    if custom_route:
        route = custom_route
    else:
        routes = load_provider_routes()
        route = routes.get(route_id)

    # Fixture descriptors test parsing only; they are not provider evidence.
    if not route or route.mode == "fixture":
        duration_ms = int((time.perf_counter() - t0) * 1000)
        evidence = (
            SourceEvidence(
                url=route.official_docs_url if route else "https://rush.dev",
                retrieved_at=datetime.datetime.now(datetime.UTC).date().isoformat(),
                license_or_terms=route.terms_url if route else "",
            ),
        )
        return ProbeResult(
            scenario_id=scenario.scenario_id,
            probe="provider",
            outcome=Outcome.INCONCLUSIVE,
            started_at=start_time,
            duration_ms=duration_ms,
            metrics={"evidence_mode": "fixture", "route_found": route is not None},
            evidence=evidence,
            fallback="fixture-route-cannot-satisfy-live-gate",
            reproduction=f"python -m scripts.benchmarks.run --scenario {scenario.scenario_id}",
        )

    # Live execution requires explicit opt-in
    if route.route_id not in _authorized_route_ids(allow_live_route):
        duration_ms = int((time.perf_counter() - t0) * 1000)
        return ProbeResult(
            scenario_id=scenario.scenario_id,
            probe="provider",
            outcome=Outcome.SKIPPED,
            started_at=start_time,
            duration_ms=duration_ms,
            metrics={"mode": route.mode, "live_skipped": True},
            fallback="live-route-not-authorized",
            reproduction=f"python -m scripts.benchmarks.run --scenario {scenario.scenario_id} --allow-live-route {route.route_id}",
        )
    if route.mode == "api" and route.provider_id == "deepseek":
        return _run_deepseek_api_probe(scenario, route, start_time, t0)
    if route.provider_id == "zai" and not (
        os.environ.get("ANTHROPIC_BASE_URL") and os.environ.get("ANTHROPIC_AUTH_TOKEN")
    ):
        return ProbeResult(
            scenario_id=scenario.scenario_id,
            probe="provider",
            outcome=Outcome.DEFERRED,
            started_at=start_time,
            duration_ms=int((time.perf_counter() - t0) * 1000),
            metrics={
                "evidence_mode": "zai-profile-not-configured",
                "route_id": route.route_id,
            },
            fallback="zai-cli-profile-not-configured",
            reproduction=(
                f"python -m scripts.benchmarks.run --scenario {scenario.scenario_id} "
                f"--allow-live-route {route.route_id}"
            ),
        )

    command = list(route.command)
    reproduction = (
        f"python -m scripts.benchmarks.run --scenario {scenario.scenario_id} "
        f"--allow-live-route {route.route_id}"
    )
    if provider_executable is not None:
        resolved_executable = provider_executable.resolve()
        if not resolved_executable.is_file():
            duration_ms = int((time.perf_counter() - t0) * 1000)
            return ProbeResult(
                scenario_id=scenario.scenario_id,
                probe="provider",
                outcome=Outcome.FAIL,
                started_at=start_time,
                duration_ms=duration_ms,
                metrics={"executable": str(resolved_executable)},
                fallback="provider-executable-not-found",
                reproduction=f"python -m scripts.benchmarks.run --scenario {scenario.scenario_id} --allow-live-route {route.route_id} --provider-executable <path>",
            )
        command[0] = str(resolved_executable)
        reproduction += f" --provider-executable {resolved_executable}"
    # Execute only an exact user-authorized argument array; a process exit alone
    # never proves an authenticated model response.
    try:
        proc = subprocess.run(
            _cli_invocation(command),
            shell=False,
            capture_output=True,
            text=True,
            timeout=route.timeout_s,
            check=False,
        )
        duration_ms = int((time.perf_counter() - t0) * 1000)
        stdout_clean, out_redactions = redact_text(
            proc.stdout, route.redaction_patterns
        )
        stderr_clean, err_redactions = redact_text(
            proc.stderr, route.redaction_patterns
        )
        all_redactions = tuple(out_redactions + err_redactions)
        marker_present = "BENCHMARK_OK" in stdout_clean
        if proc.returncode:
            outcome, fallback = Outcome.FAIL, "subprocess-error"
        elif marker_present:
            outcome, fallback = Outcome.PASS, "none"
        else:
            outcome, fallback = Outcome.INCONCLUSIVE, "response-marker-missing"
        evidence = (
            SourceEvidence(
                url=route.official_docs_url,
                retrieved_at=datetime.datetime.now(datetime.UTC).date().isoformat(),
                license_or_terms=route.terms_url,
            ),
        )
        return ProbeResult(
            scenario_id=scenario.scenario_id,
            probe="provider",
            outcome=outcome,
            started_at=start_time,
            duration_ms=duration_ms,
            metrics={
                "evidence_mode": "live-cli",
                "route_id": route.route_id,
                "executable": command[0],
                "exit_code": proc.returncode,
                "response_marker_present": marker_present,
                "response_fingerprint": hashlib.sha256(
                    stdout_clean.encode()
                ).hexdigest(),
                "stderr_len": len(stderr_clean),
                "stderr_category": _cli_error_category(stderr_clean)
                if proc.returncode
                else None,
            },
            evidence=evidence,
            redactions=all_redactions,
            fallback=fallback,
            reproduction=reproduction,
        )
    except Exception as err:  # noqa: BLE001
        duration_ms = int((time.perf_counter() - t0) * 1000)
        return ProbeResult(
            scenario_id=scenario.scenario_id,
            probe="provider",
            outcome=Outcome.FAIL,
            started_at=start_time,
            duration_ms=duration_ms,
            metrics={"error": str(err)},
            fallback="subprocess-exception",
            reproduction=f"python -m scripts.benchmarks.run --scenario {scenario.scenario_id} --allow-live-route {route.route_id}",
        )
