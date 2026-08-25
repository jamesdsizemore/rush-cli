"""Benchmark fixture loading and path containment validation."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .contracts import (
    FixtureError,
    Outcome,
    RouteDescriptor,
    Scenario,
    require_exact_keys,
)

_PACKAGE_FIXTURE_ROOT = Path(__file__).resolve().parent / "fixtures"
_SOURCE_FIXTURE_ROOT = (
    Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "benchmarks"
)
FIXTURE_ROOT = (
    _PACKAGE_FIXTURE_ROOT if _PACKAGE_FIXTURE_ROOT.is_dir() else _SOURCE_FIXTURE_ROOT
).resolve()


def fixture_path(name: str) -> Path:
    """Resolves and validates that fixture path is securely contained inside tests/fixtures/benchmarks."""
    path = (FIXTURE_ROOT / name).resolve()
    if FIXTURE_ROOT not in path.parents or path.suffix != ".json":
        raise FixtureError(f"fixture path denied: {name}")
    return path


def load_scenarios() -> dict[str, Scenario]:
    """Loads and validates scenarios from tests/fixtures/benchmarks/scenarios.json."""
    raw = json.loads(fixture_path("scenarios.json").read_text(encoding="utf-8"))
    scenarios: dict[str, Scenario] = {}
    for item in raw.get("scenarios", []):
        require_exact_keys(
            item,
            frozenset(
                {
                    "scenario_id",
                    "probe",
                    "category",
                    "input",
                    "required_facts",
                    "expected_outcome",
                }
            ),
        )
        scenario = Scenario(
            scenario_id=item["scenario_id"],
            probe=item["probe"],
            category=item["category"],
            input=item["input"],
            required_facts=tuple(item["required_facts"]),
            expected_outcome=Outcome(item["expected_outcome"]),
        )
        if scenario.scenario_id in scenarios:
            raise FixtureError(f"duplicate scenario: {scenario.scenario_id}")
        scenarios[scenario.scenario_id] = scenario
    return scenarios


def load_provider_routes() -> dict[str, RouteDescriptor]:
    """Loads provider route descriptors from provider_routes.json."""
    raw = json.loads(fixture_path("provider_routes.json").read_text(encoding="utf-8"))
    routes: dict[str, RouteDescriptor] = {}
    for item in raw.get("routes", []):
        require_exact_keys(
            item,
            frozenset(
                {
                    "provider_id",
                    "route_id",
                    "mode",
                    "command",
                    "official_docs_url",
                    "terms_url",
                    "privacy_url",
                    "credential_boundary",
                    "redaction_patterns",
                    "timeout_s",
                }
            ),
        )
        route = RouteDescriptor(
            provider_id=item["provider_id"],
            route_id=item["route_id"],
            mode=item["mode"],
            command=list(item["command"]),
            official_docs_url=item["official_docs_url"],
            terms_url=item["terms_url"],
            privacy_url=item["privacy_url"],
            credential_boundary=item["credential_boundary"],
            redaction_patterns=list(item.get("redaction_patterns", [])),
            timeout_s=float(item.get("timeout_s", 30.0)),
        )
        routes[route.route_id] = route
    return routes


def load_routers() -> dict[str, Any]:
    """Loads 9Router and OmniRoute configuration from routers.json."""
    return json.loads(fixture_path("routers.json").read_text(encoding="utf-8"))


def load_protocol_cases() -> list[dict[str, Any]]:
    """Loads protocol envelope test cases from protocol_cases.json."""
    raw = json.loads(fixture_path("protocol_cases.json").read_text(encoding="utf-8"))
    return list(raw.get("cases", []))


def load_privacy_cases() -> list[dict[str, Any]]:
    """Loads synthetic secret and parser safety cases from privacy_cases.json."""
    raw = json.loads(fixture_path("privacy_cases.json").read_text(encoding="utf-8"))
    return list(raw.get("cases", []))


def load_context_cases() -> list[dict[str, Any]]:
    """Loads context budgeting and retrieval cases from context_cases.json."""
    raw = json.loads(fixture_path("context_cases.json").read_text(encoding="utf-8"))
    return list(raw.get("cases", []))


def load_coordination_cases() -> list[dict[str, Any]]:
    """Loads coordination, journal, and lock cases from coordination_cases.json."""
    raw = json.loads(
        fixture_path("coordination_cases.json").read_text(encoding="utf-8")
    )
    return list(raw.get("cases", []))


def load_local_candidates() -> list[dict[str, Any]]:
    """Loads approved local model candidates from local_candidates.json."""
    raw = json.loads(fixture_path("local_candidates.json").read_text(encoding="utf-8"))
    return list(raw.get("candidates", []))
