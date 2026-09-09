"""Measured deterministic probes against Rush's existing MemoryTool."""

from __future__ import annotations

import datetime
import hashlib
import json
import tempfile
import time
from dataclasses import asdict
from pathlib import Path
from typing import Any

import tiktoken

from rush.permissions import ExecutionPermissions
from rush.tools.memory import MemoryTool

from .contracts import FixtureError, Outcome, ProbeResult, Scenario
from .fixtures import load_memory_cases


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _scenario_hash(scenario: Scenario) -> str:
    contract = asdict(scenario)
    contract["expected_outcome"] = scenario.expected_outcome.value
    payload = json.dumps(
        contract,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return _sha256(payload)


def _case_description(scenario: Scenario) -> str:
    cases = load_memory_cases(str(scenario.input.get("fixture", "memory_cases.json")))
    case_id = scenario.input.get("case_id", scenario.scenario_id)
    for case in cases:
        if case.get("scenario_id") == case_id:
            return str(case.get("input", {}).get("label", ""))
    raise FixtureError(f"unknown memory benchmark case: {case_id}")


def _content(index: int) -> str:
    prefix = f"memory benchmark artifact A{index:03d} matching retrieval evidence "
    return (prefix + ("x" * 512))[:512]


def run_memory_probe(
    scenario: Scenario, *, output_root: Path | None = None, **_: Any
) -> ProbeResult:
    """Measure actual legacy MemoryTool writes and defended recall."""
    started_at = datetime.datetime.now(datetime.UTC).isoformat()
    t0 = time.perf_counter()
    if any(token in scenario.scenario_id for token in ("/", "\\", "..")):
        raise FixtureError(f"scenario path denied: {scenario.scenario_id}")
    description = _case_description(scenario)
    workspace_parent = (output_root or Path.cwd()).resolve()
    workspace_parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(
        prefix="memory-", dir=workspace_parent
    ) as workspace:
        root = Path(workspace)
        permissions = ExecutionPermissions(cache_write=True)
        tool = MemoryTool()
        source_records = [
            {"id": "D1", "text": "DENIED_SECRET benchmark artifact"},
            *[{"id": f"A{index}", "text": _content(index)} for index in range(1, 101)],
        ]
        source_path = root / "memory-source.json"
        source_path.write_text(
            json.dumps(source_records, ensure_ascii=True, separators=(",", ":")),
            encoding="ascii",
        )
        source_hash = _sha256(source_path.read_bytes())

        denied = tool.run(
            root,
            operation="write",
            subject="domain_knowledge",
            content={"id": "D1", "text": "DENIED_SECRET benchmark artifact"},
            source="denied",
            permissions=permissions,
        )
        if denied["status"] != "ok":
            raise FixtureError(f"memory fixture write failed: {denied['summary']}")
        for record in source_records[1:]:
            written = tool.run(
                root,
                operation="write",
                subject="domain_knowledge",
                content=record,
                source="allowed",
                permissions=permissions,
            )
            if written["status"] != "ok":
                raise FixtureError(f"memory fixture write failed: {written['summary']}")

        recalled = tool.run(
            root,
            operation="ask",
            subject="domain_knowledge",
            query="benchmark",
            session_allowlist=["allowed"],
        )
        if recalled["status"] != "ok":
            raise FixtureError(f"memory recall failed: {recalled['summary']}")
        artifacts = recalled["raw"]
        if not isinstance(artifacts, list):
            raise FixtureError("memory recall returned malformed artifacts")
        serialized = json.dumps(recalled, ensure_ascii=False, separators=(",", ":"))
        token_count = len(tiktoken.get_encoding("cl100k_base").encode(serialized))
        elapsed_ms = int((time.perf_counter() - t0) * 1000)
        visible_ids = {
            item.get("content", {}).get("id")
            for item in artifacts
            if isinstance(item, dict)
        }
        visible_sources = {
            item.get("source") for item in artifacts if isinstance(item, dict)
        }
        denied_visible = "D1" in visible_ids or "denied" in visible_sources
        return ProbeResult(
            scenario_id=scenario.scenario_id,
            probe="memory",
            outcome=Outcome.FAIL if denied_visible else Outcome.PASS,
            started_at=started_at,
            duration_ms=elapsed_ms,
            metrics={
                "case_description": description,
                "artifact_count": len(artifacts),
                "serialized_bytes": len(serialized.encode("utf-8")),
                "token_count": token_count,
                "token_method": "tiktoken:cl100k_base",
                "elapsed_ms": elapsed_ms,
                "payload_truncated": False,
                "denied_id_visible": "D1" in visible_ids,
                "denied_source_visible": "denied" in visible_sources,
                "evidence_mode": str(
                    scenario.input.get("evidence_mode", "legacy-baseline")
                ),
                "operation_mode": str(
                    scenario.input.get("operation_mode", "current-ask")
                ),
                "source_hash": source_hash,
                "scenario_hash": _scenario_hash(scenario),
            },
            reproduction=f"python -m scripts.benchmarks.run --scenario {scenario.scenario_id}",
        )
