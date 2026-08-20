"""Sanitized Toolchain Installer & Setup Wizard.

Architecture §8, Phase 23.
Enforces Control 3: Shell Injection Elimination via typed argument lists and regex sanitization.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from rush.discovery.stack import detect_project_stacks
from rush.logging import get_logger, log_subsystem
from rush.tools.common import run_subprocess

logger = get_logger("tools.setup_wizard")

# Strict package name pattern allowing letters, numbers, @, _, -, ., /
PACKAGE_NAME_REGEX = re.compile(r"^[a-zA-Z0-9@_./-]+$")


def install_engine_package(
    package_manager: str, package_name: str, cwd: Path | None = None
) -> bool:
    """Safely install an engine toolchain package via typed argument lists."""
    if not PACKAGE_NAME_REGEX.match(package_name):
        log_subsystem(
            "setup", "ERROR", f"Invalid package specification: {package_name}"
        )
        raise ValueError(
            f"Security Error: Invalid or hostile package name '{package_name}'"
        )

    cwd_path = cwd or Path.cwd()

    cmd_map: dict[str, list[str]] = {
        "uv": ["uv", "tool", "install", package_name],
        "npm": ["npm", "install", "-g", package_name],
        "pnpm": ["pnpm", "add", "-g", package_name],
        "brew": ["brew", "install", package_name],
        "cargo": ["cargo", "install", package_name],
        "winget": ["winget", "install", "--exact", package_name],
    }

    cmd = cmd_map.get(package_manager)
    if not cmd:
        log_subsystem(
            "setup", "WARN", f"Unsupported package manager: {package_manager}"
        )
        return False

    proc = run_subprocess(cmd, cwd=cwd_path)
    return proc.returncode == 0


def run_setup_wizard(root: Path, non_interactive: bool = True) -> dict[str, Any]:
    """Inspect repository stacks and recommend/install quality engines."""
    stacks = detect_project_stacks(root)
    results: dict[str, Any] = {
        "stacks": [s.language for s in stacks],
        "installed": [],
        "skipped": [],
    }

    log_subsystem("setup", "INFO", f"Detected project stacks: {results['stacks']}")

    for stack in stacks:
        pm = stack.package_manager or "npm"
        for engine in stack.suggested_engines:
            if non_interactive:
                results["skipped"].append(engine)
            else:
                try:
                    ok = install_engine_package(pm, engine, cwd=root)
                    if ok:
                        results["installed"].append(engine)
                    else:
                        results["skipped"].append(engine)
                except Exception as exc:  # noqa: BLE001
                    log_subsystem(
                        "setup", "ERROR", f"Failed to install {engine}: {exc}"
                    )
                    results["skipped"].append(engine)

    return results
