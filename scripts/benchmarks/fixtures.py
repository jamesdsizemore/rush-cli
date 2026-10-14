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


_SCENARIO_CONTRACT_KEYS = frozenset(
    {"scenario_id", "probe", "category", "input", "required_facts", "expected_outcome"}
)


def load_scenarios() -> dict[str, Scenario]:
    """Loads and validates scenarios from tests/fixtures/benchmarks/scenarios.json,
    merged with memory benchmark cases loaded via load_memory_cases()."""
    raw = json.loads(fixture_path("scenarios.json").read_text(encoding="utf-8"))
    items = [*raw.get("scenarios", []), *load_memory_cases()]
    scenarios: dict[str, Scenario] = {}
    for item in items:
        require_exact_keys(item, _SCENARIO_CONTRACT_KEYS)
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


_ROUTE_KEYS = frozenset(
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
)
_DECISION_PROTOCOL_KEYS = frozenset(
    {"format", "help_args", "argv", "instruction_files"}
)
_DECISION_FORMATS = frozenset({"codex_exec_jsonl", "claude_print_json"})
_DECISION_KINDS = frozenset({"dataset_answer", "episode"})
_INSTRUCTION_FILES = frozenset({"$CODEX_HOME/AGENTS.md"})


def _is_str_list(value: Any) -> bool:
    return isinstance(value, list) and all(isinstance(v, str) for v in value)


def _validate_decision_protocol(route_id: Any, protocol: Any) -> dict[str, Any]:
    """D13a: a decision route's fixture-owned hermetic contract, strict at
    every level; any other shape is a `FixtureError`."""
    valid = (
        isinstance(protocol, dict)
        and set(protocol) == _DECISION_PROTOCOL_KEYS
        and isinstance(protocol["format"], str)
        and protocol["format"] in _DECISION_FORMATS
        and _is_str_list(protocol["help_args"])
        and len(protocol["help_args"]) > 0
        and isinstance(protocol["argv"], dict)
        and set(protocol["argv"]) == _DECISION_KINDS
        and all(_is_str_list(v) for v in protocol["argv"].values())
        and _is_str_list(protocol["instruction_files"])
        and set(protocol["instruction_files"]) <= _INSTRUCTION_FILES
    )
    if not valid:
        raise FixtureError(f"decision_protocol invalid: {route_id}")
    return protocol


def load_provider_routes() -> dict[str, RouteDescriptor]:
    """Loads provider route descriptors from provider_routes.json. A route
    may carry an optional `decision_protocol` (D13a); without one it stays a
    presence probe only."""
    raw = json.loads(fixture_path("provider_routes.json").read_text(encoding="utf-8"))
    routes: dict[str, RouteDescriptor] = {}
    for item in raw.get("routes", []):
        if not isinstance(item, dict):
            raise FixtureError("route entry is not an object")
        keys = set(item)
        missing = _ROUTE_KEYS - keys
        unknown = keys - _ROUTE_KEYS - {"decision_protocol"}
        if missing or unknown:
            raise FixtureError(f"missing={sorted(missing)} unknown={sorted(unknown)}")
        protocol = (
            _validate_decision_protocol(item["route_id"], item["decision_protocol"])
            if "decision_protocol" in item
            else None
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
            decision_protocol=protocol,
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


def load_memory_cases(name: str = "memory_cases.json") -> list[dict[str, Any]]:
    """Load deterministic memory benchmark descriptors under fixture containment."""
    raw = json.loads(fixture_path(name).read_text(encoding="utf-8"))
    cases = raw.get("cases")
    if not isinstance(cases, list):
        raise FixtureError("memory benchmark fixture cases must be a list")
    for case in cases:
        if not isinstance(case, dict) or not isinstance(case.get("scenario_id"), str):
            raise FixtureError("memory benchmark case is malformed")
        require_exact_keys(case, _SCENARIO_CONTRACT_KEYS)
    return cases


def load_local_candidates() -> list[dict[str, Any]]:
    """Loads approved local model candidates from local_candidates.json."""
    raw = json.loads(fixture_path("local_candidates.json").read_text(encoding="utf-8"))
    return list(raw.get("candidates", []))
