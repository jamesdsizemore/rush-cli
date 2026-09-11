"""Sanitized Toolchain Installer & Setup Wizard.

Architecture §8, Phase 23. Phase 65 §6.2 wires the wizard's install path
into the declarative `rush.setup.engine_packages` registry and the
`rush.setup.provision` plan builder/applier, so recommended engines install
under their canonical registry package identity (e.g. `@biomejs/biome`,
`typescript`), never a bare executable name, and any engine outside the
declared allowlist is silently excluded from installation.
Enforces Control 3: Shell Injection Elimination via typed argument lists and regex sanitization.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from rush.discovery.stack import detect_project_stacks
from rush.logging import get_logger, log_subsystem
from rush.permissions import ExecutionPermissions
from rush.setup.engine_packages import ENGINE_PACKAGES
from rush.setup.provision import (
    Downloader,
    HttpGet,
    Prober,
    ProvisionPlan,
    Runner,
    apply_provision_plan,
    build_provision_plan,
    default_data_root,
)
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


def run_setup_wizard(
    root: Path,
    non_interactive: bool = True,
    *,
    install: bool = False,
    permissions: ExecutionPermissions | None = None,
    project_id: str | None = None,
    data_root: Path | None = None,
    http_get: HttpGet | None = None,
    downloader: Downloader | None = None,
    runner: Runner | None = None,
    prober: Prober | None = None,
) -> dict[str, Any]:
    """Inspect repository stacks and recommend/install quality engines.

    ``install=False`` (the default) preserves the original stack-detection
    and interactive-vs-skip behavior unchanged. ``install=True`` builds and
    applies a §6.2 provision plan through `rush.setup.provision` instead:
    every recommended engine is resolved to its canonical registry package
    identity (e.g. `@biomejs/biome`, not `biome`) and any suggested engine
    outside the declared `ENGINE_PACKAGES` allowlist is excluded from the
    plan entirely, never attempted as an arbitrary package name. A failed
    probe or checksum mismatch is reported in ``provision.failed`` and is
    never added to ``installed``.
    """
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

    if install:
        suggested = {e for stack in stacks for e in stack.suggested_engines}
        known_engine_ids = sorted(e for e in suggested if e in ENGINE_PACKAGES)
        results["unsupported_engines"] = sorted(suggested - set(known_engine_ids))
        plan: ProvisionPlan = build_provision_plan(root, known_engine_ids)
        results["plan_id"] = plan.plan_id
        if permissions is not None:
            kwargs: dict[str, Any] = {}
            if http_get is not None:
                kwargs["http_get"] = http_get
            if downloader is not None:
                kwargs["downloader"] = downloader
            if runner is not None:
                kwargs["runner"] = runner
            if prober is not None:
                kwargs["prober"] = prober
            provision_result = apply_provision_plan(
                plan,
                permissions,
                project_id=project_id or str(root.resolve()),
                data_root=data_root or default_data_root(),
                **kwargs,
            )
            results["provision"] = {
                "applied": sorted(provision_result.applied),
                "failed": provision_result.failed,
                "permission_blocked": provision_result.permission_blocked,
                "requires_input": provision_result.requires_input,
            }
        else:
            results["provision"] = {"plan_only": True}

    return results
