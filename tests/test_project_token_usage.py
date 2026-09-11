"""P65-07.1 (plan §6.4): `project_token_usage` separates provider-reported real model
usage, tokenizer-computed handoff-packet counts, recorded cache/memory-reuse event
costs, and the estimated avoided-payload savings ratio. A provider total absent from
every run manifest stays `None` ("unknown"), never coerced to `0`.
"""

from __future__ import annotations

import json
from pathlib import Path

from rush.token_economy.telemetry import TelemetryStore
from rush.workflows.projects import project_token_usage
from tests.test_project_evidence import _project, _scheduled_item, _write_manifest


def _data_root(tmp_path: Path) -> Path:
    return tmp_path / "rush-data"


def test_provider_reported_tokens_sum_exactly_when_present(tmp_path: Path) -> None:
    project_id, root, data_root = _project(tmp_path, "proj")
    _write_manifest(
        root,
        run_id="run-1",
        scheduled=[
            _scheduled_item("ai-eval", "quality", metrics={"total_tokens": 500}),
            _scheduled_item("ai-review", "quality", metrics={"total_tokens": 300}),
        ],
    )

    usage = project_token_usage(project_id, data_root=data_root)
    assert usage["provider_reported"]["total_tokens"] == 800
    assert usage["provider_reported"]["event_count"] == 2


def test_provider_reported_stays_unknown_when_absent_from_every_manifest(
    tmp_path: Path,
) -> None:
    project_id, root, data_root = _project(tmp_path, "proj")
    _write_manifest(
        root, run_id="run-1", scheduled=[_scheduled_item("typecheck", "quality")]
    )

    usage = project_token_usage(project_id, data_root=data_root)
    assert usage["provider_reported"]["total_tokens"] is None
    assert usage["provider_reported"]["event_count"] == 0


def test_provider_reported_is_none_with_zero_runs_not_coerced_to_zero(
    tmp_path: Path,
) -> None:
    project_id, _root, data_root = _project(tmp_path, "proj")
    usage = project_token_usage(project_id, data_root=data_root)
    assert usage["provider_reported"]["total_tokens"] is None


def test_tokenizer_counted_sums_real_handoff_packet_tokens_exactly(
    tmp_path: Path,
) -> None:
    project_id, root, data_root = _project(tmp_path, "proj")
    handoffs_dir = root / ".rush" / "handoffs"
    handoffs_dir.mkdir(parents=True)
    for handoff_id, tokens in (("h1", 120), ("h2", 80)):
        payload = {
            "handoff_id": handoff_id,
            "packet": {
                "tokens": tokens,
                "bytes": tokens * 4,
                "encoding": "cl100k_base",
            },
        }
        (handoffs_dir / f"{handoff_id}.json").write_text(
            json.dumps(payload), encoding="utf-8"
        )

    usage = project_token_usage(project_id, data_root=data_root)
    assert usage["tokenizer_counted"]["total_tokens"] == 200
    assert usage["tokenizer_counted"]["packet_count"] == 2
    assert usage["tokenizer_counted"]["encoding"] == "cl100k_base"


def test_cache_hits_and_estimates_are_separate_real_numbers(tmp_path: Path) -> None:
    project_id, root, data_root = _project(tmp_path, "proj")
    telemetry = TelemetryStore(root)
    telemetry.record_memory_event(
        "retrieval", 50, request_id="r1", event_id="e1", cache_write=True
    )
    telemetry.record_memory_event(
        "expansion", 30, request_id="r1", event_id="e2", cache_write=True
    )
    telemetry.record_savings("scan", raw_tokens=1000, compressed_tokens=200)

    usage = project_token_usage(project_id, data_root=data_root)
    assert usage["cache_hits"]["total_tokens"] == 80
    assert usage["cache_hits"]["by_kind"]["retrieval"] == 50
    assert usage["cache_hits"]["by_kind"]["expansion"] == 30
    assert usage["cache_hits"]["by_kind"]["packing"] == 0

    assert usage["estimated_avoided"]["net_tokens_saved"] == 800
    assert usage["estimated_avoided"]["total_raw_tokens"] == 1000
    assert usage["estimated_avoided"]["total_compressed_tokens"] == 200

    # The estimate never inflates the real, recorded cache-hit total.
    assert (
        usage["cache_hits"]["total_tokens"]
        != usage["estimated_avoided"]["net_tokens_saved"]
    )


def test_unopted_memory_events_never_recorded_as_cache_hits(tmp_path: Path) -> None:
    project_id, root, data_root = _project(tmp_path, "proj")
    telemetry = TelemetryStore(root)
    # No opt_in, no cache_write -- a read-only lookup must never persist a cost.
    written = telemetry.record_memory_event(
        "retrieval", 999, request_id="r1", event_id="e1"
    )
    assert written is False

    usage = project_token_usage(project_id, data_root=data_root)
    assert usage["cache_hits"]["total_tokens"] == 0
