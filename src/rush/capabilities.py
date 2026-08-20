"""Read-only capability detection for scan planning and user diagnostics."""

from __future__ import annotations

from pathlib import Path
from typing import TypedDict

from .catalog import TOOL_SPECS
from .tools.routing import detect_project_languages

_REPORTS: tuple[tuple[str, str], ...] = (
    ("coverage.json", "coverage"),
    ("coverage.xml", "coverage"),
    ("lcov.info", "coverage"),
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


def inspect_capabilities(path: Path) -> dict:
    """Inspect local markers and report artifacts without executing an engine."""
    root = path if path.is_dir() else path.parent
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
        else:
            tools[name] = {
                "maturity": spec.maturity,
                "state": "configured" if name in TOOL_SPECS else "missing",
                "reason": "catalogued; engine execution/version probing is not part of capability detection",
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
                "selected": state in {"applicable", "configured"},
            }
        )
    return {"path": capabilities["path"], "profile": profile, "steps": steps}
