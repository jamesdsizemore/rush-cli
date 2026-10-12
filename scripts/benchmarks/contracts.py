"""Benchmark harness contracts, dataclasses, and validation functions."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import StrEnum
from typing import Any

SCHEMA_VERSION = 1


class Outcome(StrEnum):
    PASS = "pass"
    FAIL = "fail"
    INCONCLUSIVE = "inconclusive"
    DEFERRED = "deferred"
    SKIPPED = "skipped"


class FixtureError(ValueError):
    """Raised when a benchmark fixture is malformed or violates security boundaries."""


@dataclass(frozen=True)
class SourceEvidence:
    url: str
    retrieved_at: str
    revision: str = ""
    license_or_terms: str = ""


@dataclass(frozen=True)
class Scenario:
    scenario_id: str
    probe: str
    category: str
    input: dict[str, Any]
    required_facts: tuple[str, ...]
    expected_outcome: Outcome


@dataclass(frozen=True)
class ProbeResult:
    scenario_id: str
    probe: str
    outcome: Outcome
    started_at: str
    duration_ms: int
    metrics: dict[str, int | float | str]
    evidence: tuple[SourceEvidence, ...] = ()
    redactions: tuple[str, ...] = ()
    fallback: str = ""
    reproduction: str = ""
    schema_version: int = SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["outcome"] = self.outcome.value
        data["evidence"] = [asdict(item) for item in self.evidence]
        return data


REQUIRED_RESULT_KEYS = frozenset(ProbeResult.__dataclass_fields__)


@dataclass(frozen=True)
class RouteDescriptor:
    provider_id: str
    route_id: str
    mode: str  # "fixture" | "api" | "oauth_cli" | "cli"
    command: list[str]
    official_docs_url: str
    terms_url: str
    privacy_url: str
    credential_boundary: str
    redaction_patterns: list[str] = field(default_factory=list)
    timeout_s: float = 30.0
    # Phase 72 D13a: fixture-owned hermetic decision contract
    # (`format`, `argv` per decision kind, `help_args`); `None` keeps a route
    # a presence probe only, never a decision route.
    decision_protocol: dict[str, Any] | None = None


@dataclass
class DecisionBudget:
    """Live decision budget for one case x seed (Phase 72 D13).

    `max_total_tokens` is E = min(--max-total-tokens, case max_total_tokens);
    provider model tokens are charged once per call, local tool results never.
    """

    max_total_tokens: int
    output_reserve_tokens: int
    route_overhead_tokens: int
    model_tokens: int = 0

    def admits(self, prompt_tokens: int) -> bool:
        return (
            self.model_tokens
            + self.route_overhead_tokens
            + prompt_tokens
            + self.output_reserve_tokens
        ) <= self.max_total_tokens

    def charge(self, tokens: int) -> bool:
        self.model_tokens += tokens
        return self.model_tokens <= self.max_total_tokens


@dataclass(frozen=True)
class DecisionResult:
    """Outcome of one `providers.run_memory_decision` call.

    `reason is None` means a well-formed, budget-admitted decision; any other
    value is the first failing step and `decision` is then `None`.
    """

    reason: str | None = None
    decision: dict[str, Any] | None = None
    text: str | None = None
    model_tokens: int = 0
    tool_items: int = 0
    usage: dict[str, Any] = field(default_factory=dict)
    model: list[str] = field(default_factory=list)
    provider_ids: list[str] = field(default_factory=list)
    returncode: int | None = None
    stdout: str = ""
    stderr: str = ""


@dataclass(frozen=True)
class HardwareProfile:
    os: str
    cpu: str
    ram_gb: float
    gpu: str = ""
    vram_gb: float = 0.0
    free_disk_gb: float = 0.0
    runtime_version: str = ""
    profile_id: str = ""


@dataclass(frozen=True)
class CandidateBinary:
    name: str
    version: str = ""
    license: str = ""
    bounds: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class DecisionRecord:
    decision_id: str
    title: str
    status: Outcome
    unblocked_task: str
    fixture_ids: list[str]
    result_path: str
    evidence: list[SourceEvidence]
    fallback: str
    reproduction: str


def require_exact_keys(payload: dict[str, Any], keys: frozenset[str]) -> None:
    """Validates that payload contains exactly the expected keys and no extra keys."""
    missing = keys - payload.keys()
    unknown = payload.keys() - keys
    if missing or unknown:
        raise FixtureError(f"missing={sorted(missing)} unknown={sorted(unknown)}")
