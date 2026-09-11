"""MC13.2 public benchmark dataset adapters.

Adapts LongMemEval, MemoryAgentBench, SWE-bench Verified and LongMemEval-V2
records for Rush's memory benchmark suite (`docs/reports/memory-capabilities-
benchmark-strategy.md`). Every adapter strips gold-only fields (answers,
expected patches, `has_answer` labels) before a record may reach an evaluated
agent; native prediction schemas are preserved exactly as each benchmark's
own official evaluator expects.

Each dataset section is bound to a manifest (`url`, `revision`, `sha256`,
`license_or_terms`, `split`); a missing manifest field or a records-payload
hash mismatch raises `FixtureError` before any record is returned, never a
partial or best-effort load.
"""

from __future__ import annotations

import hashlib
import json
import tempfile
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import tiktoken

from rush.permissions import ExecutionPermissions
from rush.tools.memory import MemoryTool

from .contracts import FixtureError
from .fixtures import fixture_path

_LONGMEMEVAL_GOLD_KEYS = frozenset({"answer", "answer_session_ids"})
_TURN_GOLD_KEY = "has_answer"
_MEMORY_AGENT_BENCH_GOLD_KEYS = frozenset({"expected_output", "gold"})
_LONGMEMEVAL_V2_GOLD_KEYS = frozenset({"gold_trajectory", "expected_next_action"})

_REQUIRED_MANIFEST_KEYS = frozenset(
    {"dataset", "url", "revision", "sha256", "license_or_terms", "split"}
)

_ENCODING = "cl100k_base"

CaseOutcome = Literal["scored", "timeout", "budget_exhausted"]


@dataclass(frozen=True)
class DatasetManifest:
    """Provenance a dataset section must declare before its records may be used."""

    dataset: str
    url: str
    revision: str
    sha256: str
    license_or_terms: str
    split: str


@dataclass(frozen=True)
class DatasetCaseResult:
    """One independent dataset case's outcome. `outcome` values other than
    `"scored"` (timeout, budget exhaustion) still carry `case_id` and
    `total_tokens` -- callers must count every result toward their
    denominator, never drop unsuccessful cases silently."""

    case_id: str
    outcome: CaseOutcome
    prediction: dict[str, str] | None
    total_tokens: int


def _records_digest(records: list[dict[str, Any]]) -> str:
    payload = json.dumps(records, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _validate_section(
    name: str, section: dict[str, Any]
) -> tuple[DatasetManifest, list[dict[str, Any]]]:
    """Pure validator: raises `FixtureError` on a missing manifest field or a
    records-payload hash mismatch before returning anything. Exercised
    directly by tests against tampered in-memory sections, and by
    `load_dataset_section` against the real bundled fixture -- one validation
    path, no divergence between test and production loading."""
    manifest_raw = section.get("manifest")
    records = section.get("records")
    if not isinstance(manifest_raw, dict) or not isinstance(records, list):
        raise FixtureError(f"dataset section {name!r} requires manifest and records")
    missing = _REQUIRED_MANIFEST_KEYS - manifest_raw.keys()
    if missing:
        raise FixtureError(
            f"dataset {name!r} manifest missing field(s): {sorted(missing)}"
        )
    manifest = DatasetManifest(
        **{key: manifest_raw[key] for key in _REQUIRED_MANIFEST_KEYS}
    )
    actual_hash = _records_digest(records)
    if actual_hash != manifest.sha256:
        raise FixtureError(
            f"dataset {name!r} record hash mismatch: manifest declares "
            f"{manifest.sha256}, actual is {actual_hash}"
        )
    return manifest, records


def load_dataset_section(
    name: str, *, fixture_name: str = "memory_datasets.json"
) -> tuple[DatasetManifest, list[dict[str, Any]]]:
    """Loads one manifest-bound dataset section and verifies its declared
    `sha256` against the actual records payload before returning anything."""
    raw = json.loads(fixture_path(fixture_name).read_text(encoding="utf-8"))
    section = raw.get(name)
    if not isinstance(section, dict):
        raise FixtureError(f"unknown dataset section: {name}")
    return _validate_section(name, section)


def strip_longmemeval_gold(
    record: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Splits one LongMemEval-shaped record into `(sanitized, gold)`.
    `sanitized` is exactly what an evaluated agent may see: dates and session
    identifiers are legitimate question context and are retained; `answer`,
    `answer_session_ids` and every per-turn `has_answer` are removed into
    `gold`, for a separate grading process the agent never touches."""
    gold: dict[str, Any] = {
        key: record[key] for key in _LONGMEMEVAL_GOLD_KEYS if key in record
    }
    sanitized = {k: v for k, v in record.items() if k not in _LONGMEMEVAL_GOLD_KEYS}
    gold_turn_flags: list[dict[str, Any]] = []
    sanitized_sessions = []
    for session in sanitized.get("haystack_sessions", []):
        sanitized_turns = []
        for turn_index, turn in enumerate(session.get("turns", [])):
            if _TURN_GOLD_KEY in turn:
                gold_turn_flags.append(
                    {
                        "session_id": session.get("session_id"),
                        "turn_index": turn_index,
                        _TURN_GOLD_KEY: turn[_TURN_GOLD_KEY],
                    }
                )
            sanitized_turns.append(
                {k: v for k, v in turn.items() if k != _TURN_GOLD_KEY}
            )
        sanitized_sessions.append({**session, "turns": sanitized_turns})
    if sanitized_sessions:
        sanitized = {**sanitized, "haystack_sessions": sanitized_sessions}
    if gold_turn_flags:
        gold[_TURN_GOLD_KEY] = gold_turn_flags
    return sanitized, gold


def to_longmemeval_prediction(question_id: str, hypothesis: str) -> dict[str, str]:
    """Native LongMemEval prediction schema: exactly `{question_id,
    hypothesis}`, matching the official evaluator's expected JSONL record."""
    return {"question_id": question_id, "hypothesis": hypothesis}


def to_swe_prediction(
    instance_id: str, model_patch: str, model_name_or_path: str
) -> dict[str, str]:
    """Native SWE-bench `predictions.jsonl` schema: exactly `{instance_id,
    model_patch, model_name_or_path}`, scored only by the official harness."""
    return {
        "instance_id": instance_id,
        "model_patch": model_patch,
        "model_name_or_path": model_name_or_path,
    }


def transform_memory_agent_bench(record: dict[str, Any]) -> dict[str, Any]:
    """MemoryAgentBench compatibility transform: preserves the official task
    partition (`capability`) and strips grader-only `expected_output`/`gold`
    before the record may reach an evaluated agent."""
    return {k: v for k, v in record.items() if k not in _MEMORY_AGENT_BENCH_GOLD_KEYS}


def transform_longmemeval_v2(record: dict[str, Any]) -> dict[str, Any]:
    """LongMemEval-V2 compatibility transform: reuses original LongMemEval's
    gold-stripping contract, additionally removing V2's own `gold_trajectory`
    and `expected_next_action` -- an agent evaluated on V2 must never see the
    graded trajectory it is being compared against."""
    sanitized, _gold = strip_longmemeval_gold(record)
    return {k: v for k, v in sanitized.items() if k not in _LONGMEMEVAL_V2_GOLD_KEYS}


def run_longmemeval_case(
    record: dict[str, Any],
    *,
    decide_fn: Callable[[Path, MemoryTool, ExecutionPermissions, dict[str, Any]], str],
    max_total_tokens: int,
    timeout_seconds: float | None = None,
    workspace_root: Path | None = None,
) -> DatasetCaseResult:
    """Runs one independent LongMemEval case in a freshly created namespace
    (a new temp directory, hence a new SQLite store, per call -- no case can
    see another case's ingested sessions). Ingests every sanitized haystack
    turn as a real `MemoryTool` write, then calls `decide_fn` with the live
    tool/root so it can query its own just-ingested namespace to produce a
    hypothesis. A timeout or a `max_total_tokens` overrun during ingestion
    ends the case early but still returns a `DatasetCaseResult` -- callers
    must keep it in their denominator, never drop it."""
    sanitized, _gold = strip_longmemeval_gold(record)
    case_id = str(sanitized.get("question_id", ""))
    start = time.perf_counter()
    encoder = tiktoken.get_encoding(_ENCODING)
    workspace_parent = (workspace_root or Path.cwd()).resolve()
    workspace_parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="memds-", dir=workspace_parent) as tmp:
        root = Path(tmp)
        tool = MemoryTool()
        permissions = ExecutionPermissions(cache_write=True)
        total_tokens = 0
        for session in sanitized.get("haystack_sessions", []):
            for turn in session.get("turns", []):
                written = tool.run(
                    root,
                    operation="write",
                    subject="episodic",
                    content={
                        "session_id": session.get("session_id"),
                        "date": session.get("date"),
                        **turn,
                    },
                    source=str(session.get("session_id", "session")),
                    permissions=permissions,
                )
                total_tokens += len(
                    encoder.encode(json.dumps(written, separators=(",", ":")))
                )
                if (
                    timeout_seconds is not None
                    and (time.perf_counter() - start) > timeout_seconds
                ):
                    return DatasetCaseResult(
                        case_id=case_id,
                        outcome="timeout",
                        prediction=None,
                        total_tokens=total_tokens,
                    )
                if total_tokens > max_total_tokens:
                    return DatasetCaseResult(
                        case_id=case_id,
                        outcome="budget_exhausted",
                        prediction=None,
                        total_tokens=total_tokens,
                    )
        hypothesis = decide_fn(root, tool, permissions, sanitized)
        total_tokens += len(encoder.encode(hypothesis))
        prediction = to_longmemeval_prediction(case_id, hypothesis)
        return DatasetCaseResult(
            case_id=case_id,
            outcome="scored",
            prediction=prediction,
            total_tokens=total_tokens,
        )


def aggregate_dataset_results(results: list[DatasetCaseResult]) -> dict[str, int]:
    """Aggregates dataset case outcomes. `total` counts every result
    regardless of outcome -- timeout and budget-exhausted cases are never
    excluded from the denominator (plan §"Metrics")."""
    return {
        "total": len(results),
        "scored": sum(1 for r in results if r.outcome == "scored"),
        "timeout": sum(1 for r in results if r.outcome == "timeout"),
        "budget_exhausted": sum(1 for r in results if r.outcome == "budget_exhausted"),
    }
