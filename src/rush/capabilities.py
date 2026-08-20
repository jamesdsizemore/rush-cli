"""Read-only capability detection for scan planning and user diagnostics."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import TypedDict

from .catalog import ENGINE_SPECS, TOOL_SPECS
from .config import RushConfig, load_config
from .tools.routing import detect_project_languages

_REPORTS: tuple[tuple[str, str], ...] = (
    ("coverage.json", "coverage"),
    ("coverage.xml", "coverage"),
    ("lcov.info", "coverage"),
    ("codeql.sarif", "codeql"),
    ("junit.xml", "flaky"),
    ("pact.json", "contract"),
    ("mutation.json", "mutation"),
    ("snapshot.json", "snapshot"),
    ("fuzz.json", "fuzz"),
    ("load.json", "load"),
    ("property.json", "pbt"),
)


class Capability(TypedDict):
    maturity: str
    state: str
    reason: str


_PLAN_PROFILES: dict[str, tuple[str, ...]] = {
    "default": ("review", "lint", "security", "coverage", "flaky", "contract"),
    "nonbrowser": tuple(
        name
        for name, spec in TOOL_SPECS.items()
        if spec.maturity in {"real_adapter", "importer", "feasibility_gated"}
    ),
}


def _plan_prerequisites(name: str) -> list[str]:
    """Return stable, descriptive prerequisites without inspecting an engine."""
    reports = sorted(report for report, tool in _REPORTS if tool == name)
    if len(reports) == 1:
        return [f"local report: {reports[0]}"]
    if reports:
        return [f"one local report: {', '.join(reports)}"]

    spec = TOOL_SPECS[name]
    engines = sorted(
        ENGINE_SPECS[engine_name].binary
        for engine_name in spec.engine_names
        if engine_name in ENGINE_SPECS
    )
    return [f"one local engine: {', '.join(engines)}"] if engines else []


def inspect_capabilities(path: Path, *, config: RushConfig | None = None) -> dict:
    """Inspect local markers and report artifacts without executing an engine."""
    root = path if path.is_dir() else path.parent
    config = config or load_config(start=root)
    languages = detect_project_languages(root)
    reports = sorted(name for name, _ in _REPORTS if (root / name).is_file())
    report_tools = {tool for name, tool in _REPORTS if name in reports}
    tools: dict[str, Capability] = {}
    for name, spec in TOOL_SPECS.items():
        if spec.maturity == "browser_runtime":
            tools[name] = {
                "maturity": spec.maturity,
                "state": "blocked",
                "reason": "reserved for explicit browser evidence work",
            }
        elif spec.maturity == "importer":
            state = "applicable" if name in report_tools else "missing"
            tools[name] = {
                "maturity": spec.maturity,
                "state": state,
                "reason": "local report found"
                if state == "applicable"
                else "local report not found",
            }
        elif spec.maturity == "feasibility_gated":
            tools[name] = {
                "maturity": spec.maturity,
                "state": "blocked",
                "reason": "no contained adapter fixture contract",
            }
        elif name in config.tools:
            tools[name] = {
                "maturity": spec.maturity,
                "state": "configured",
                "reason": "configured in local rush.toml",
            }
        else:
            installed = sorted(
                ENGINE_SPECS[engine_name].binary
                for engine_name in spec.engine_names
                if engine_name in ENGINE_SPECS
                and shutil.which(ENGINE_SPECS[engine_name].binary)
            )
            if installed:
                tools[name] = {
                    "maturity": spec.maturity,
                    "state": "installed",
                    "reason": f"local engine on PATH: {', '.join(installed)}",
                }
            elif not spec.engine_names:
                tools[name] = {
                    "maturity": spec.maturity,
                    "state": "applicable",
                    "reason": "contained implementation requires no external engine",
                }
            else:
                tools[name] = {
                    "maturity": spec.maturity,
                    "state": "missing",
                    "reason": "no configured local engine found on PATH",
                }
    return {
        "path": str(root),
        "languages": languages,
        "reports": reports,
        "tools": tools,
    }


def build_plan(path: Path, profile: str = "default") -> dict:
    """Return a deterministic non-executing plan for completed capabilities."""
    if profile not in _PLAN_PROFILES:
        raise ValueError(f"unknown plan profile: {profile}")
    capabilities = inspect_capabilities(path)
    steps = []
    for name in _PLAN_PROFILES[profile]:
        capability = capabilities["tools"][name]
        state = capability["state"]
        steps.append(
            {
                "tool": name,
                "state": state,
                "reason": capability["reason"],
                "prerequisites": _plan_prerequisites(name),
                "selected": state in {"applicable", "configured", "installed"},
            }
        )
    return {"path": capabilities["path"], "profile": profile, "steps": steps}
