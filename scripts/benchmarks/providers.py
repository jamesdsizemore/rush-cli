"""Provider, OAuth/CLI, and router probe runner."""

from __future__ import annotations

import datetime
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from rush.delivery.compact import canonical_json
from rush.io.physical_paths import ContainmentError, PhysicalRoot

from .contracts import (
    DecisionBudget,
    DecisionResult,
    FixtureError,
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
    route: RouteDescriptor | None
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
    if route.provider_id == "zai":
        return ProbeResult(
            scenario_id=scenario.scenario_id,
            probe="provider",
            outcome=Outcome.DEFERRED,
            started_at=start_time,
            duration_ms=int((time.perf_counter() - t0) * 1000),
            metrics={
                "evidence_mode": "zai-route-deferred",
                "route_id": route.route_id,
            },
            fallback="zai-route-deferred",
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
        live_metrics: dict[str, Any] = {
            "evidence_mode": "live-cli",
            "route_id": route.route_id,
            "executable": command[0],
            "exit_code": proc.returncode,
            "response_marker_present": marker_present,
            "response_fingerprint": hashlib.sha256(stdout_clean.encode()).hexdigest(),
            "stderr_len": len(stderr_clean),
            "stderr_category": _cli_error_category(stderr_clean)
            if proc.returncode
            else None,
        }
        return ProbeResult(
            scenario_id=scenario.scenario_id,
            probe="provider",
            outcome=outcome,
            started_at=start_time,
            duration_ms=duration_ms,
            metrics=live_metrics,
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


# --- Phase 72 D13/D13a: live decision routes (75-T02/EVALUATOR) --------------

DECISION_PROMPT_PREAMBLE = (
    "You are the agent under evaluation in a Rush memory benchmark. The JSON "
    "request below holds the task, your actual history so far and the "
    "response_schema. Reply with exactly one JSON object that matches "
    "response_schema and nothing else.\n"
)
CODEX_EVENT_TYPES = frozenset(
    {
        "thread.started",
        "turn.started",
        "turn.completed",
        "turn.failed",
        "item.started",
        "item.updated",
        "item.completed",
        "error",
    }
)
CODEX_ITEM_TYPES = frozenset(
    {
        "agent_message",
        "reasoning",
        "command_execution",
        "file_change",
        "mcp_tool_call",
        "web_search",
        "todo_list",
        "collab_tool_call",
        "error",
    }
)
CODEX_TOOL_ITEM_TYPES = frozenset(
    {
        "command_execution",
        "file_change",
        "mcp_tool_call",
        "collab_tool_call",
        "web_search",
    }
)
PREFLIGHT_REQUEST: dict[str, Any] = {
    "schema_version": 1,
    "decision_kind": "preflight",
    "task": 'Reply with the JSON object {"kind": "answer", "text": "ok"}.',
    "response_schema": {"kind": "answer", "text": "<string>"},
}
_DECISION_OUTPUT_LIMIT = 1_048_576
_PREFLIGHT_MARGIN_TOKENS = 2048
_EXCERPT_CHARS = 4096
_PROVIDER_ID_KEYS = frozenset({"session_id", "uuid", "thread_id"})
_CLAUDE_USAGE_KEYS = (
    "input_tokens",
    "cache_creation_input_tokens",
    "cache_read_input_tokens",
    "output_tokens",
)


@dataclass(frozen=True)
class DecisionRoute:
    """A granted, resolved decision route: the fixture-owned protocol and the
    absolute executable. Nothing in it comes from a model decision."""

    route_id: str
    format: str
    executable: Path
    protocol: dict[str, Any]
    timeout_s: float
    redaction_patterns: tuple[str, ...] = ()


@dataclass(frozen=True)
class DecisionInvocation(DecisionResult):
    """`DecisionResult` plus what the invocation record needs: the argv that
    ran, its cwd and duration."""

    argv: tuple[str, ...] = ()
    cwd: str | None = None
    duration_ms: int = 0


def _is_windows_shell_shim(exe: Path, *, os_name: str) -> bool:
    return os_name == "nt" and (
        exe.suffix.lower() in {".cmd", ".bat"}
        or (not exe.suffix and exe.with_suffix(".cmd").is_file())
    )


def resolve_decision_route(
    route_id: str,
    *,
    allow_live_route: str | list[str] | tuple[str, ...] | None,
    provider_executable: Path | str | None,
) -> DecisionRoute:
    """Resolves a live decision route without spawning anything."""
    route = load_provider_routes().get(route_id)
    if route is None or route.decision_protocol is None:
        raise FixtureError(f"not_a_decision_route: {route_id}")
    if route_id not in _authorized_route_ids(allow_live_route):
        raise FixtureError(f"live_route_not_granted: {route_id}")
    if provider_executable is not None:
        exe = Path(provider_executable).resolve()
        if not (exe.is_file() and os.access(exe, os.X_OK)):
            raise FixtureError(f"executable_not_found: {provider_executable}")
    else:
        found = shutil.which(route.command[0])
        if found is None:
            raise FixtureError(f"executable_not_found: {route.command[0]}")
        exe = Path(found).resolve()
    if _is_windows_shell_shim(exe, os_name=os.name):
        raise FixtureError(f"cmd_shim_unsupported: {exe}")
    protocol = route.decision_protocol
    return DecisionRoute(
        route_id=route_id,
        format=str(protocol["format"]),
        executable=exe,
        protocol=protocol,
        timeout_s=float(route.timeout_s),
        redaction_patterns=tuple(route.redaction_patterns),
    )


def build_decision_prompt(request: dict[str, Any]) -> str:
    return DECISION_PROMPT_PREAMBLE + json.dumps(
        request,
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
        default=str,
    )


def decision_argv(decision_route: DecisionRoute, kind: str, prompt: str) -> list[str]:
    return [
        str(decision_route.executable),
        *decision_route.protocol["argv"][kind],
        prompt,
    ]


def _provider_ids(value: Any) -> list[str]:
    """Every string of 8+ characters under a session/uuid/thread key, at any
    depth (iterative, so a deep payload cannot exhaust the stack)."""
    found: list[str] = []
    stack = [value]
    while stack:
        node = stack.pop()
        if isinstance(node, dict):
            for key, inner in node.items():
                if (
                    key in _PROVIDER_ID_KEYS
                    and isinstance(inner, str)
                    and len(inner) >= 8
                ):
                    found.append(inner)
                stack.append(inner)
        elif isinstance(node, list):
            stack.extend(node)
    return sorted(set(found))


def _usage_int(value: Any) -> bool:
    return type(value) is int and value >= 0


def parse_codex_output(stdout: str) -> dict[str, Any]:
    """Codex `exec --json` JSONL -> {reason, text, usage, model_tokens,
    tool_items, model, provider_ids}; the first failing rule sets `reason`."""
    out: dict[str, Any] = {"reason": None, "text": None, "usage": {}, "model_tokens": 0}
    out.update(tool_items=0, model=[], provider_ids=[])
    events: list[dict[str, Any]] = []
    for line in stdout.splitlines():
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except (ValueError, RecursionError):
            return {**out, "reason": "unsupported_event"}
        kind = event.get("type") if isinstance(event, dict) else None
        if not isinstance(kind, str) or kind not in CODEX_EVENT_TYPES:
            return {**out, "reason": "unsupported_event"}
        if kind.startswith("item."):
            item = event.get("item")
            item_type = item.get("type") if isinstance(item, dict) else None
            if not isinstance(item_type, str) or item_type not in CODEX_ITEM_TYPES:
                return {**out, "reason": "unsupported_event"}
        events.append(event)
    out["provider_ids"] = _provider_ids(events)
    if any(e["type"] in {"turn.failed", "error"} for e in events):
        return {**out, "reason": "provider_error"}
    messages = [
        e["item"]
        for e in events
        if e["type"] == "item.completed" and e["item"]["type"] == "agent_message"
    ]
    if not messages or not isinstance(messages[0].get("text"), str):
        return {**out, "reason": "no_agent_message"}
    if len(messages) > 1:
        return {**out, "reason": "two_agent_messages"}
    out["text"] = messages[0]["text"]
    out["tool_items"] = sum(
        1
        for e in events
        if e["type"] == "item.completed" and e["item"]["type"] in CODEX_TOOL_ITEM_TYPES
    )
    completed = [e for e in events if e["type"] == "turn.completed"]
    if not completed:
        return {**out, "reason": "missing_turn_completed"}
    usage = completed[-1].get("usage")
    if not isinstance(usage, dict) or not all(
        _usage_int(usage.get(k)) for k in ("input_tokens", "output_tokens")
    ):
        return {**out, "reason": "provider_usage_unavailable"}
    out["usage"] = usage
    out["model_tokens"] = usage["input_tokens"] + usage["output_tokens"]
    return out


def parse_claude_output(stdout: str) -> dict[str, Any]:
    """Claude `-p --output-format json` result object -> the same shape as
    `parse_codex_output`."""
    out: dict[str, Any] = {"reason": None, "text": None, "usage": {}, "model_tokens": 0}
    out.update(tool_items=0, model=[], provider_ids=[])
    try:
        obj = json.loads(stdout.strip())
    except (ValueError, RecursionError):
        return {**out, "reason": "non_json_stdout"}
    if not isinstance(obj, dict):
        return {**out, "reason": "non_json_stdout"}
    out["provider_ids"] = _provider_ids(obj)
    if obj.get("is_error") is not False:
        return {**out, "reason": "is_error_true"}
    if obj.get("subtype") != "success":
        return {**out, "reason": "non_success_subtype"}
    if not isinstance(obj.get("result"), str):
        return {**out, "reason": "missing_result"}
    out["text"] = obj["result"]
    num_turns = obj.get("num_turns")
    out["tool_items"] = num_turns - 1 if type(num_turns) is int and num_turns > 1 else 0
    model_usage = obj.get("modelUsage")
    out["model"] = sorted(model_usage) if isinstance(model_usage, dict) else []
    usage = obj.get("usage")
    if not isinstance(usage, dict) or not all(
        _usage_int(usage.get(k)) for k in _CLAUDE_USAGE_KEYS
    ):
        return {**out, "reason": "provider_usage_unavailable"}
    out["usage"] = usage
    out["model_tokens"] = sum(usage[k] for k in _CLAUDE_USAGE_KEYS)
    return out


def _reject_constant(name: str) -> Any:
    raise ValueError(f"non-finite constant {name}")


def parse_decision_text(
    text: str, kind: str
) -> tuple[dict[str, Any] | None, str | None]:
    """The model's reply -> (decision, None) or (None, reason)."""
    t = text.strip()
    if t.startswith("```"):
        match = re.fullmatch(r"```(?:json)?[ \t]*\n(.*)\n```", t, re.DOTALL)
        if match is None:
            return None, "malformed_decision_json"
        t = match.group(1)
    try:
        decision = json.loads(t, parse_constant=_reject_constant)
    except (ValueError, RecursionError):
        return None, "malformed_decision_json"
    if not isinstance(decision, dict):
        return None, "malformed_decision_json"
    shape = decision.get("kind")
    if kind == "dataset_answer":
        if set(decision) - {"kind", "text"}:
            return None, "unknown_decision_field"
        if shape != "answer":
            if shape in ("action", "submit"):
                return None, "action_not_permitted"
            return None, "malformed_decision_json"
        if not isinstance(decision.get("text"), str):
            return None, "malformed_decision_json"
        return decision, None
    if shape == "action":
        allowed = {"kind", "operation", "kwargs"}
        if set(decision) - allowed:
            return None, "unknown_decision_field"
        if (
            set(decision) != allowed
            or not isinstance(decision["operation"], str)
            or not isinstance(decision["kwargs"], dict)
        ):
            return None, "malformed_decision_json"
        return decision, None
    if shape == "submit":
        if set(decision) - {"kind", "final"}:
            return None, "unknown_decision_field"
        if "final" not in decision:
            return None, "malformed_decision_json"
        return decision, None
    if shape == "answer":
        return None, "action_not_permitted"
    return None, "malformed_decision_json"


def _containment_reason(root: Path, workspace_root: Path) -> str | None:
    if not os.path.lexists(root):
        return "fixture_missing"
    if Path(root).is_symlink():
        return "root_not_contained"
    rel = os.path.relpath(os.path.abspath(root), os.path.abspath(workspace_root))
    if rel == os.curdir or rel.split(os.sep)[0] == os.pardir or os.path.isabs(rel):
        return "root_not_contained"
    try:
        candidate = PhysicalRoot(workspace_root).open_contained(rel)
    except ContainmentError:
        return "root_not_contained"
    return None if candidate.is_dir() else "fixture_missing"


def run_memory_decision(
    request: dict[str, Any],
    *,
    decision_route: DecisionRoute,
    kind: str,
    root: Path,
    workspace_root: Path,
    budget: DecisionBudget,
    timeout_s: float,
) -> DecisionInvocation:
    """One hermetic provider decision: contained cwd, argv without a shell,
    budget admitted before and charged after the call, strict parsing."""
    from .memory import _count_tokens, _get_encoder

    def done(reason: str | None, **fields: Any) -> DecisionInvocation:
        return DecisionInvocation(reason=reason, **fields)

    reason = _containment_reason(Path(root), Path(workspace_root))
    if reason is not None:
        return done(reason)
    cwd = Path(root)
    if kind == "dataset_answer":
        cwd = Path(root) / "decision-cwd"
        try:
            if not os.path.lexists(cwd):
                cwd.mkdir()
            PhysicalRoot(root).open_contained("decision-cwd")
        except (ContainmentError, OSError):
            return done("root_not_contained")
        if not cwd.is_dir() or cwd.is_symlink():
            return done("root_not_contained")
    prompt = build_decision_prompt(request)
    argv = decision_argv(decision_route, kind, prompt)
    base: dict[str, Any] = {"argv": tuple(argv), "cwd": str(cwd)}
    if not budget.admits(_count_tokens(_get_encoder(), prompt)):
        return done("budget_exhausted", **base)
    t0 = time.perf_counter()
    try:
        proc = subprocess.run(
            argv,
            cwd=cwd,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout_s,
            check=False,
        )
    except subprocess.TimeoutExpired:
        base["duration_ms"] = int((time.perf_counter() - t0) * 1000)
        return done("timeout", **base)
    except OSError:
        base["duration_ms"] = int((time.perf_counter() - t0) * 1000)
        return done("spawn_failed", **base)
    base["duration_ms"] = int((time.perf_counter() - t0) * 1000)
    stdout, stderr = proc.stdout or "", proc.stderr or ""
    base.update(returncode=proc.returncode, stdout=stdout, stderr=stderr)
    # ponytail: post-read bound; a streaming cap if a provider floods within its timeout
    if (
        len(stdout.encode("utf-8")) > _DECISION_OUTPUT_LIMIT
        or len(stderr.encode("utf-8")) > _DECISION_OUTPUT_LIMIT
    ):
        return done("output_too_large", **base)
    if proc.returncode != 0:
        return done("nonzero_exit", **base)
    parser = (
        parse_codex_output
        if decision_route.format == "codex_exec_jsonl"
        else parse_claude_output
    )
    parsed = parser(stdout)
    base.update(
        text=parsed["text"],
        usage=parsed["usage"],
        model=parsed["model"],
        provider_ids=parsed["provider_ids"],
        tool_items=parsed["tool_items"],
    )
    if parsed["reason"] is not None:
        return done(parsed["reason"], **base)
    base["model_tokens"] = parsed["model_tokens"]
    if not budget.charge(parsed["model_tokens"]):
        return done("budget_exhausted", **base)
    if kind == "dataset_answer" and parsed["tool_items"] > 0:
        return done("decision_used_tools", **base)
    decision, reason = parse_decision_text(parsed["text"], kind)
    return done(reason, decision=decision, **base)


def invocation_record(
    result: DecisionResult, *, step: int, route_id: str
) -> dict[str, Any]:
    """The report's invocation record: the prompt is replaced by its digest."""
    argv = list(getattr(result, "argv", ()))
    if argv:
        prompt = argv[-1]
        digest = hashlib.sha256(prompt.encode("utf-8")).hexdigest()
        argv[-1] = f"<prompt sha256={digest} chars={len(prompt)}>"
    decision_sha256 = (
        None
        if result.decision is None
        else hashlib.sha256(canonical_json(result.decision)).hexdigest()
    )
    return {
        "step": step,
        "route_id": route_id,
        "argv": argv,
        "cwd": getattr(result, "cwd", None),
        "exit_code": result.returncode,
        "duration_ms": getattr(result, "duration_ms", 0),
        "reason": result.reason,
        "model_tokens": result.model_tokens,
        "usage": result.usage or None,
        "model": list(result.model),
        "tool_items": result.tool_items,
        "stdout_excerpt": result.stdout[:_EXCERPT_CHARS],
        "stderr_excerpt": result.stderr[:_EXCERPT_CHARS],
        "decision_sha256": decision_sha256,
    }


def _instruction_files(decision_route: DecisionRoute) -> list[dict[str, Any]]:
    from .memory import _count_tokens, _get_encoder

    entries: list[dict[str, Any]] = []
    for name in decision_route.protocol.get("instruction_files", []):
        if name != "$CODEX_HOME/AGENTS.md":
            continue
        codex_home = os.environ.get("CODEX_HOME") or str(Path.home() / ".codex")
        path = Path(codex_home) / "AGENTS.md"
        present = path.is_file()
        data = path.read_bytes() if present else b""
        entries.append(
            {
                "path": str(path),
                "present": present,
                "sha256": hashlib.sha256(data).hexdigest() if present else None,
                "cl100k_tokens": _count_tokens(
                    _get_encoder(), data.decode("utf-8", errors="replace")
                )
                if present
                else None,
            }
        )
    return entries


def _probe_output(
    argv: list[str], cwd: Path, timeout_s: float
) -> tuple[str, str] | None:
    try:
        proc = subprocess.run(
            argv,
            cwd=cwd,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout_s,
            check=False,
        )
    except (subprocess.TimeoutExpired, OSError):
        return None
    return proc.stdout or "", proc.stderr or ""


def preflight_decision_route(
    decision_route: DecisionRoute,
    *,
    workspace_root: Path,
    case_budgets: list[tuple[int, int]],
    max_total_tokens: int | None = None,
) -> dict[str, Any]:
    """Route preflight before any case: hermetic flags on the route's own
    help, `--version`, one parsed preflight decision with usage, and the
    overhead gate against every case's (budget, reserve). `case_budgets`
    entries are (case max_total_tokens or E, output_reserve_tokens); a given
    `max_total_tokens` caps each."""
    exe = str(decision_route.executable)
    protocol = decision_route.protocol
    report: dict[str, Any] = {
        "status": "unavailable",
        "reason": None,
        "version": None,
        "route_overhead_tokens": None,
        "instruction_files": _instruction_files(decision_route),
        "preflight": None,
    }
    workspace_root = Path(workspace_root)
    help_out = _probe_output(
        [exe, *protocol["help_args"]], workspace_root, decision_route.timeout_s
    )
    flags = sorted(
        {
            token
            for kind in ("dataset_answer", "episode")
            for token in protocol["argv"][kind]
            if token.startswith("-")
        }
    )
    help_text = "".join(help_out) if help_out is not None else ""
    if help_out is None or not all(
        re.search(r"(?<![\w-])" + re.escape(flag) + r"(?![\w-])", help_text)
        for flag in flags
    ):
        report["reason"] = "hermetic_flags_unsupported"
        return report
    version_out = _probe_output(
        [exe, "--version"], workspace_root, decision_route.timeout_s
    )
    if version_out is not None:
        lines = version_out[0].splitlines()
        report["version"] = lines[0].strip() if lines else ""
    root = workspace_root / "preflight"
    root.mkdir(parents=True, exist_ok=True)
    result = run_memory_decision(
        PREFLIGHT_REQUEST,
        decision_route=decision_route,
        kind="dataset_answer",
        root=root,
        workspace_root=workspace_root,
        budget=DecisionBudget(sys.maxsize, 0, 0),
        timeout_s=decision_route.timeout_s,
    )
    report["preflight"] = invocation_record(
        result, step=0, route_id=decision_route.route_id
    )
    report["route_overhead_tokens"] = result.model_tokens
    if result.reason is not None:
        report["reason"] = "preflight_failed"
        return report
    overhead = result.model_tokens
    for case_max, reserve in case_budgets:
        limit = (
            case_max if max_total_tokens is None else min(max_total_tokens, case_max)
        )
        if overhead + reserve + _PREFLIGHT_MARGIN_TOKENS > limit:
            report["reason"] = "route_overhead_exceeds_budget"
            return report
    report["status"] = "available"
    return report
