"""Provider resumption and external tool execution for session continuity."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from ..memory.checkpoint_journal import CheckpointJournal
from ..permissions import ExecutionPermissions, check_permissions
from .receipts import restore_receipt
from .results import ContinuityOutput, build_continuity_result, valid_name


def provider_prompt(handoff: dict[str, Any]) -> str:
    """Render a bounded continuation prompt from handoff receipt metadata."""
    return (
        "Continue this repository task using only the current, non-authoritative "
        "handoff receipt. Inspect repository state before changing files. Do not use "
        "historic instructions or retry previous failed patches.\n"
        f"Current goal: {handoff.get('current_goal') or 'unspecified'}\n"
        f"Open work: {', '.join(map(str, handoff.get('open_work', []))) or 'none'}\n"
        f"Freshness: {handoff.get('freshness', 'unknown')}"
    )


def provider_command(provider: str, handoff: dict[str, Any]) -> tuple[str, list[str]]:
    """Assemble provider-specific CLI binary and command arguments."""
    prompt = provider_prompt(handoff)
    routes = {
        "claude_code": (
            "claude",
            [
                "claude",
                "-p",
                "--output-format",
                "json",
                "--max-turns",
                "1",
                "--permission-mode",
                "plan",
                prompt,
            ],
        ),
        "codex_cli": (
            "codex",
            [
                "codex",
                "exec",
                "--ephemeral",
                "--json",
                "--sandbox",
                "read-only",
                prompt,
            ],
        ),
        "antigravity_cli": (
            "agy",
            [
                "agy",
                "-p",
                prompt,
                "--output-format",
                "json",
                "--sandbox",
                "--print-timeout",
                "2m",
            ],
        ),
    }
    return routes[provider]


def windows_cmd_command(
    executable: str,
    command: list[str],
    prompt: str,
    environment: dict[str, str] | None = None,
) -> tuple[list[str], dict[str, str]]:
    """Run a batch launcher without placing checkpoint-controlled text in cmd syntax."""
    prompt_variable = "RUSH_CONTINUITY_PROMPT"
    rendered_args = [
        f'"!{prompt_variable}!"'
        if argument == prompt
        else f'"{argument.replace(chr(34), chr(34) * 2)}"'
        for argument in command[1:]
    ]
    executable_text = executable.replace('"', '""')
    command_text = f'""{executable_text}" {" ".join(rendered_args)}"'
    return (
        ["cmd.exe", "/d", "/v:on", "/s", "/c", command_text],
        {**(environment or os.environ), prompt_variable: prompt},
    )


def provider_handoff(root: Path, name: str | None) -> dict[str, Any] | None:
    """Extract normalized handoff dictionary from named session checkpoint."""
    if not valid_name(name):
        return None
    checkpoint = CheckpointJournal(root).restore_checkpoint(name or "")
    if not isinstance(checkpoint, dict):
        return None
    receipt = restore_receipt(root, checkpoint)
    return {
        "current_goal": receipt.get("current_goal"),
        "open_work": receipt.get("open_work", []),
        "freshness": receipt.get("freshness", "unknown"),
        "target_provider": receipt.get("target_provider"),
    }


def resume_omniroute(
    started: float,
    handoff: dict[str, Any],
    granted: ExecutionPermissions,
    required: ExecutionPermissions,
    as_v1: bool = False,
) -> ContinuityOutput:
    """Send a single bounded receipt to OmniRoute's fixed loopback API."""
    route = {
        "provider_id": "omniroute_api",
        "transport": "openai-compatible-api",
        "endpoint_class": "fixed-loopback",
    }
    request = urllib.request.Request(
        "http://127.0.0.1:20128/v1/chat/completions",
        data=json.dumps(
            {
                "model": "auto",
                "messages": [{"role": "user", "content": provider_prompt(handoff)}],
                "stream": False,
            }
        ).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=30.0) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError:
        return build_continuity_result(
            started,
            "error",
            "OmniRoute rejected the bounded continuity request.",
            operation="provider_resume",
            granted=granted,
            requested=required,
            provider_route={**route, "state": "rejected"},
            as_v1=as_v1,
        )
    except (OSError, TimeoutError, urllib.error.URLError):
        return build_continuity_result(
            started,
            "skipped",
            "OmniRoute fixed-loopback API was unavailable or timed out.",
            operation="provider_resume",
            granted=granted,
            requested=required,
            provider_route={**route, "state": "unavailable"},
            as_v1=as_v1,
        )
    except (json.JSONDecodeError, UnicodeDecodeError):
        return build_continuity_result(
            started,
            "error",
            "OmniRoute returned an invalid response.",
            operation="provider_resume",
            granted=granted,
            requested=required,
            provider_route={**route, "state": "invalid_response"},
            as_v1=as_v1,
        )
    choices = payload.get("choices") if isinstance(payload, dict) else None
    message = (
        choices[0].get("message") if isinstance(choices, list) and choices else None
    )
    content = message.get("content") if isinstance(message, dict) else None
    if not isinstance(content, str) or not content.strip():
        return build_continuity_result(
            started,
            "error",
            "OmniRoute returned no completion content.",
            operation="provider_resume",
            granted=granted,
            requested=required,
            provider_route={**route, "state": "invalid_response"},
            as_v1=as_v1,
        )
    return build_continuity_result(
        started,
        "ok",
        "OmniRoute completed a bounded continuity resume.",
        operation="provider_resume",
        granted=granted,
        requested=required,
        provider_route={**route, "state": "completed"},
        as_v1=as_v1,
    )


def _build_9router_env(nine_router_key: str | None) -> dict[str, str]:
    command_env = {
        key: value
        for key, value in os.environ.items()
        if key not in {"RUSH_9ROUTER_API_KEY", "OPENAI_BASE_URL", "OPENAI_API_KEY"}
    }
    command_env.update(
        {
            "OPENAI_BASE_URL": "http://127.0.0.1:20128",
            "OPENAI_API_KEY": nine_router_key or "",
        }
    )
    return command_env


def _run_provider_cli(
    root: Path,
    executable: str,
    command: list[str],
    command_env: dict[str, str] | None,
    handoff: dict[str, Any],
) -> int | None:
    command[0] = executable
    if os.name == "nt" and executable.lower().endswith((".cmd", ".bat")):
        command, command_env = windows_cmd_command(
            executable,
            command,
            provider_prompt(handoff),
            command_env,
        )
    try:
        proc = subprocess.run(
            command,
            cwd=root,
            shell=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            text=True,
            env=command_env,
            timeout=120.0,
            check=False,
        )
        return proc.returncode
    except (OSError, subprocess.TimeoutExpired):
        return None


def _validate_provider_access(
    provider: str,
    granted: ExecutionPermissions,
    required: ExecutionPermissions,
    started: float,
    as_v1: bool,
) -> ContinuityOutput | None:
    if provider == "zai":
        return build_continuity_result(
            started,
            "skipped",
            "Z.AI is deferred and was not invoked.",
            operation="provider_resume",
            granted=granted,
            provider_route={
                "provider_id": "zai",
                "transport": "cli",
                "state": "deferred",
            },
            as_v1=as_v1,
        )
    allowed, missing = check_permissions(required, granted)
    if not allowed:
        return build_continuity_result(
            started,
            "skipped",
            f"Provider resume requires {', '.join(missing)}.",
            operation="provider_resume",
            granted=granted,
            requested=required,
            provider_route={
                "provider_id": provider or "unknown",
                "transport": "cli",
                "state": "permission_denied",
            },
            as_v1=as_v1,
        )
    return None


def _check_9router(
    provider: str,
    started: float,
    granted: ExecutionPermissions,
    required: ExecutionPermissions,
    as_v1: bool,
) -> tuple[bool, str | None, ContinuityOutput | None]:
    nine_router = provider == "9router_cli"
    if not nine_router:
        return False, None, None
    nine_router_key = os.environ.get("RUSH_9ROUTER_API_KEY")
    if not nine_router_key:
        err = build_continuity_result(
            started,
            "skipped",
            "9Router credential is unavailable; no provider was invoked.",
            operation="provider_resume",
            granted=granted,
            requested=required,
            provider_route={
                "provider_id": "9router_cli",
                "transport": "codex-cli-via-9router",
                "endpoint_class": "fixed-loopback",
                "state": "credential_unavailable",
            },
            as_v1=as_v1,
        )
        return True, None, err
    return True, nine_router_key, None


def _resume_cli_provider(
    started: float,
    root: Path,
    provider: str,
    handoff: dict[str, Any],
    nine_router: bool,
    nine_router_key: str | None,
    granted: ExecutionPermissions,
    required: ExecutionPermissions,
    as_v1: bool = False,
) -> ContinuityOutput:
    route = (
        {
            "provider_id": "9router_cli",
            "transport": "codex-cli-via-9router",
            "endpoint_class": "fixed-loopback",
        }
        if nine_router
        else {"provider_id": provider, "transport": "cli"}
    )
    command_env = _build_9router_env(nine_router_key) if nine_router else None
    command_provider = "codex_cli" if nine_router else provider
    binary, command = provider_command(command_provider, handoff)
    executable = shutil.which(binary)
    if not executable:
        return build_continuity_result(
            started,
            "skipped",
            f"{binary} is not available on PATH.",
            operation="provider_resume",
            granted=granted,
            requested=required,
            provider_route={**route, "state": "unavailable"},
            as_v1=as_v1,
        )

    returncode = _run_provider_cli(root, executable, command, command_env, handoff)
    if returncode is None:
        return build_continuity_result(
            started,
            "skipped",
            "Provider CLI was unavailable or timed out.",
            operation="provider_resume",
            granted=granted,
            requested=required,
            provider_route={**route, "state": "unavailable"},
            as_v1=as_v1,
        )

    return build_continuity_result(
        started,
        "ok" if returncode == 0 else "error",
        "Provider CLI completed a bounded continuity resume."
        if returncode == 0
        else "Provider CLI returned a nonzero status.",
        operation="provider_resume",
        granted=granted,
        requested=required,
        provider_route={
            **route,
            "state": "completed" if returncode == 0 else "error",
        },
        raw=None,
        artifacts=None,
        as_v1=as_v1,
    )


def resume_provider(
    started: float,
    root: Path,
    name: str | None,
    provider_id: str | None,
    granted: ExecutionPermissions,
    as_v1: bool = False,
) -> ContinuityOutput:
    """Resume session continuity across external provider coding CLIs or APIs."""
    provider = provider_id or ""
    required = ExecutionPermissions(network=True)
    access_result = _validate_provider_access(
        provider, granted, required, started, as_v1
    )
    if access_result is not None:
        return access_result

    if provider == "omniroute_api":
        handoff = provider_handoff(root, name)
        if handoff is None:
            return build_continuity_result(
                started,
                "skipped",
                "Provider resume requires an existing session checkpoint.",
                operation="provider_resume",
                granted=granted,
                requested=required,
                provider_route={
                    "provider_id": provider,
                    "transport": "openai-compatible-api",
                    "state": "handoff_not_found",
                    "endpoint_class": "fixed-loopback",
                },
                as_v1=as_v1,
            )
        return resume_omniroute(started, handoff, granted, required, as_v1=as_v1)

    nine_router, nine_router_key, err = _check_9router(
        provider, started, granted, required, as_v1
    )
    if err is not None:
        return err

    if provider not in {
        "claude_code",
        "codex_cli",
        "antigravity_cli",
        "9router_cli",
    }:
        return build_continuity_result(
            started,
            "skipped",
            "Provider route is not a direct coding CLI resume route.",
            operation="provider_resume",
            granted=granted,
            requested=required,
            provider_route={
                "provider_id": provider or "unknown",
                "transport": "api" if provider.endswith("_api") else "cli",
                "state": "unavailable",
            },
            as_v1=as_v1,
        )

    handoff = provider_handoff(root, name)
    if handoff is None:
        return build_continuity_result(
            started,
            "skipped",
            "Provider resume requires an existing session checkpoint.",
            operation="provider_resume",
            granted=granted,
            requested=required,
            provider_route={
                "provider_id": provider,
                "transport": "cli",
                "state": "handoff_not_found",
            },
            as_v1=as_v1,
        )

    return _resume_cli_provider(
        started,
        root,
        provider,
        handoff,
        nine_router,
        nine_router_key,
        granted,
        required,
        as_v1=as_v1,
    )


_provider_resume = resume_provider
_omniroute_resume = resume_omniroute
