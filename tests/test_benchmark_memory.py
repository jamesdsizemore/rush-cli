"""MC00 deterministic memory benchmark contracts."""

from __future__ import annotations

import importlib
import json
import os
from dataclasses import replace
from itertools import count
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pytest

from scripts.benchmarks import memory
from scripts.benchmarks.contracts import FixtureError, Outcome, Scenario
from scripts.benchmarks.fixtures import load_memory_cases, load_scenarios
from scripts.benchmarks.memory import run_memory_probe
from scripts.benchmarks.run import get_probe_runner, main


def _scenario(case_id: str, **input_overrides: object) -> Scenario:
    payload: dict[str, object] = {
        "fixture": "memory_cases.json",
        "case_id": case_id,
    }
    payload.update(input_overrides)
    return Scenario(
        scenario_id=case_id,
        probe="memory",
        category="memory",
        input=payload,
        required_facts=("actual_memory_tool",),
        expected_outcome=Outcome.PASS,
    )


def _metrics(result: Any) -> dict[str, Any]:
    return cast(dict[str, Any], result.metrics)


def test_memory_probe_uses_real_store(tmp_path: Path) -> None:
    assert get_probe_runner("memory") is run_memory_probe
    assert [case["scenario_id"] for case in load_memory_cases()] == [
        "M01",
        "M03",
        "M05",
        "M06",
        "M09",
        "M10",
    ]
    result = run_memory_probe(_scenario("M01"), output_root=tmp_path)

    assert result.outcome == Outcome.PASS
    assert result.metrics["artifact_count"] == 100
    assert _metrics(result)["serialized_bytes"] > 8192
    assert _metrics(result)["token_count"] > 0
    assert result.metrics["token_method"] == "tiktoken:cl100k_base"
    assert _metrics(result)["elapsed_ms"] >= 0
    assert len(_metrics(result)["source_hash"]) == 64
    assert len(_metrics(result)["scenario_hash"]) == 64


def test_memory_baseline_records_over_budget_payload(tmp_path: Path) -> None:
    result = run_memory_probe(_scenario("M06"), output_root=tmp_path)

    assert result.outcome == Outcome.PASS
    assert _metrics(result)["serialized_bytes"] > 8192
    assert result.metrics["payload_truncated"] is True


def test_memory_probe_keeps_denied_content_out_of_results(tmp_path: Path) -> None:
    result = run_memory_probe(_scenario("M05"), output_root=tmp_path)

    serialized = json.dumps(result.to_dict(), ensure_ascii=False)
    assert result.metrics["denied_id_visible"] is False
    assert result.metrics["denied_source_visible"] is False
    assert "D1" not in serialized
    assert "DENIED_SECRET" not in serialized


def test_memory_probe_rejects_fixture_path_escape() -> None:
    with pytest.raises(FixtureError, match="fixture path denied"):
        load_memory_cases("../outside.json")


def test_memory_scenarios_are_public_and_write_probe_results(tmp_path: Path) -> None:
    scenarios = load_scenarios()
    for case_id in ("M01", "M03", "M05", "M06", "M09", "M10"):
        assert scenarios[case_id].probe == "memory"
    output = tmp_path / "public"
    assert main(["--scenario", "M01", "--output", str(output)]) == 0
    result = json.loads((output / "M01.json").read_text(encoding="utf-8"))
    assert result["probe"] == "memory"
    assert result["metrics"]["artifact_count"] == 100


def test_memory_probe_repeat_isolated_and_rejects_unsafe_id(tmp_path: Path) -> None:
    first = run_memory_probe(_scenario("M01"), output_root=tmp_path)
    second = run_memory_probe(_scenario("M01"), output_root=tmp_path)
    assert first.metrics["artifact_count"] == 100
    assert second.metrics["artifact_count"] == 100
    assert not list(tmp_path.glob("memory-*"))

    with pytest.raises(FixtureError, match="scenario path denied"):
        run_memory_probe(
            replace(_scenario("M01"), scenario_id="../outside"), output_root=tmp_path
        )
    assert not (tmp_path.parent / "outside").exists()


def test_memory_probe_fails_if_denied_allowlist_leaks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    original = memory.MemoryTool

    class RecordingTool:
        def __init__(self) -> None:
            self.delegate = original()

        def run(self, root: Path, **kwargs: Any) -> Any:
            if kwargs.get("operation") == "ask":
                kwargs["session_allowlist"] = ["allowed", "denied"]
            return self.delegate.run(root, **kwargs)

    monkeypatch.setattr(memory, "MemoryTool", RecordingTool)
    result = run_memory_probe(_scenario("M05"), output_root=tmp_path)

    assert result.outcome == Outcome.FAIL
    assert result.metrics["denied_id_visible"] is True


def test_memory_probe_metrics_match_recorded_tool_result(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    original = memory.MemoryTool
    captured: dict[str, object] = {}

    class RecordingTool:
        def __init__(self) -> None:
            self.delegate = original()

        def run(self, root: Path, **kwargs: Any) -> Any:
            result = self.delegate.run(root, **kwargs)
            if kwargs.get("operation") == "ask":
                captured["result"] = result
            return result

    monkeypatch.setattr(memory, "MemoryTool", RecordingTool)
    result = run_memory_probe(_scenario("M01"), output_root=tmp_path)
    recorded = captured["result"]
    assert isinstance(recorded, dict)
    serialized = json.dumps(recorded, ensure_ascii=False, separators=(",", ":"))
    assert result.metrics["serialized_bytes"] == len(serialized.encode("utf-8"))
    assert result.metrics["token_count"] == len(
        memory.tiktoken.get_encoding("cl100k_base").encode(serialized)
    )


def test_memory_probe_detects_stale_record_via_legacy_path_only(tmp_path: Path) -> None:
    result = run_memory_probe(_scenario("M03"), output_root=tmp_path)

    # 72-T01 (75-T02 M03): the shared decision closes the expired-legacy leak, so the
    # legacy path no longer shows the expired record either.
    assert result.metrics["stale_visible_legacy"] is False
    assert result.metrics["stale_visible_compact"] is False
    assert _metrics(result)["expiry_sweep_changed"] >= 1


def test_memory_probe_measures_real_payload_truncation(tmp_path: Path) -> None:
    result = run_memory_probe(_scenario("M06"), output_root=tmp_path)

    assert result.metrics["payload_truncated"] is True
    assert _metrics(result)["compact_items_returned"] < 100


def test_memory_probe_measures_source_edit(tmp_path: Path) -> None:
    result = run_memory_probe(_scenario("M09"), output_root=tmp_path)

    assert _metrics(result)["post_edit_version"] > _metrics(result)["pre_edit_version"]
    assert result.metrics["edited_content_visible"] is True


def test_memory_probe_measures_cache_budget_pagination(tmp_path: Path) -> None:
    result = run_memory_probe(_scenario("M10"), output_root=tmp_path)

    assert result.metrics["compact_paginated"] is True
    assert _metrics(result)["compact_pages"] > 1


def test_memory_probe_token_fallback_when_encoder_unavailable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def _raise_encoder_unavailable(*_args: object, **_kwargs: object) -> object:
        raise RuntimeError("encoder unavailable")

    monkeypatch.setattr(memory.tiktoken, "get_encoding", _raise_encoder_unavailable)
    result = run_memory_probe(_scenario("M01"), output_root=tmp_path)

    assert result.metrics["token_method"] == "tiktoken:cl100k_base:fallback"


# =============================================================================
# 72-T08: optional hybrid retrieval, honest paired evaluation (R8-R11, R16, R21-R23, D14)
#
# Shared fixtures (the frozen corpus, fixture F8, the oracle embedding) live in
# `tests/test_phase72_memory_hybrid.py`; they are imported inside each test body so this
# module keeps collecting while a producer is absent.
# =============================================================================

_T08_ROUTES = ("openai-codex-oauth-cli-live", "anthropic-claude-code-live")
_T08_MANIFEST = (
    Path(__file__).resolve().parents[1]
    / "tests"
    / "fixtures"
    / "phase75"
    / "task_manifest.json"
)
_T08_EVAL_DIR = (
    Path(__file__).resolve().parents[1] / "docs" / "reports" / "phase-72-memory-eval"
)


def _t08_support() -> Any:
    support = importlib.import_module("tests.test_phase72_memory_hybrid")

    return support


class _SpyTool:
    """A `MemoryTool` stand-in recording every call and answering from `replies`."""

    def __init__(self, replies: dict[str, Any]) -> None:
        self.calls: list[dict[str, Any]] = []
        self._replies = replies

    def run(self, root: Path, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        return self._replies[kwargs["operation"]](kwargs)


def _compact_reply(operation: str, items: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "status": "ok",
        "raw": {
            "schema_version": 1,
            "operation": operation,
            "code": "OK",
            "data": {"items": items, "next_cursor": None, "complete": True},
        },
    }


def _t08_permissions() -> Any:
    from rush.permissions import ExecutionPermissions

    return ExecutionPermissions(network=True, cache_write=True)


# --- R8, R9 -----------------------------------------------------------------------------


def test_t08_hypothesis_text_from_excerpt(tmp_path: Path) -> None:
    """A compact item carries an `excerpt`, never `content`: the hypothesis is built from it,
    asks the recall with the case's own query verbatim, and uses the compact budgets."""
    from scripts.benchmarks.run import _variant_hypothesis

    spy = _SpyTool(
        {
            "recall": lambda kwargs: _compact_reply(
                "recall",
                [
                    {"id": "a", "version": 1, "excerpt": "alpha excerpt"},
                    {"id": "b", "version": 1, "excerpt": "beta excerpt"},
                ],
            )
        }
    )
    text = _variant_hypothesis(
        "current",
        tmp_path,
        spy,  # type: ignore[arg-type]
        _t08_permissions(),
        {"question": "What is alpha beta"},
        query="alpha",
        session_allowlist=["s1"],
    )
    assert text == "alpha excerpt beta excerpt"
    (call,) = spy.calls
    assert call["operation"] == "recall"
    assert call["query"] == "alpha"
    assert call["subject"] == "episodic"
    assert call["session_allowlist"] == ["s1"]
    request = call["request"]
    assert request["view"] == "compact"
    assert request["limit"] == 8 and request["max_bytes"] == 8192
    assert request["max_tokens"] == 2048


def test_t08_related_items_key(tmp_path: Path) -> None:
    """`related` answers `data.items` (not `data.related`); the `linked` variant reads it."""
    from scripts.benchmarks.run import _variant_hypothesis

    spy = _SpyTool(
        {
            "recall": lambda kwargs: _compact_reply(
                "recall", [{"id": "a", "version": 3, "excerpt": "alpha excerpt"}]
            ),
            "related": lambda kwargs: _compact_reply(
                "related", [{"id": "r", "version": 1, "excerpt": "related excerpt"}]
            ),
        }
    )
    text = _variant_hypothesis(
        "linked",
        tmp_path,
        spy,  # type: ignore[arg-type]
        _t08_permissions(),
        {"question": "What is alpha"},
        query="alpha",
        session_allowlist=["s1"],
    )
    assert text == "alpha excerpt related excerpt"
    related = [c for c in spy.calls if c["operation"] == "related"]
    assert len(related) == 1
    assert related[0]["request"] == {"id": "a", "version": 3}


# --- R10 --------------------------------------------------------------------------------


def _embedding_override(manifest: dict[str, Any]) -> dict[str, str]:
    embedding = manifest["phase72_embedding"]
    return {
        "retrieval": "hybrid",
        "embedding_endpoint": embedding["endpoint"],
        "embedding_model": embedding["model"],
        "embedding_model_digest": embedding["model_digest"],
    }


def _recording_run(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    from rush.tools.memory import MemoryTool

    calls: list[dict[str, Any]] = []
    original = MemoryTool.run

    def recording(self: Any, path: Path, **kwargs: Any) -> Any:
        result = original(self, path, **kwargs)
        calls.append({"path": str(path), **kwargs, "_result": result})
        return result

    monkeypatch.setattr(MemoryTool, "run", recording)
    return calls


def test_t08_hybrid_arm_runs_without_network(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The dataset runners grant the local embedding route: a hybrid request is not refused
    with `retrieval=hybrid requires network`, for LongMemEval and `p72-` cases alike."""
    support = _t08_support()
    from scripts.benchmarks.memory_datasets import (
        load_dataset_section,
        run_longmemeval_case,
        run_phase72_case,
    )
    from scripts.benchmarks.run import _variant_hypothesis

    seen: list[Any] = []
    _manifest, records = load_dataset_section("longmemeval")

    def decide(root: Path, tool: Any, perms: Any, sanitized: dict[str, Any]) -> str:
        seen.append(perms)
        return "x"

    run_longmemeval_case(
        records[0], decide_fn=decide, max_total_tokens=10**6, workspace_root=tmp_path
    )
    assert seen[0].network is True and seen[0].cache_write is True

    # Through the real hybrid arm: the recall is not a permission refusal.
    calls = _recording_run(monkeypatch)
    from rush.memory import embeddings

    monkeypatch.setattr(
        embeddings, "_embed_batch", lambda config, batch: support.f8_vectors(batch)
    )
    override = {
        "retrieval": "hybrid",
        "embedding_endpoint": support.ENDPOINT,
        "embedding_model": support.MODEL,
        "embedding_model_digest": support.DIGEST,
    }

    def decide_hybrid(
        root: Path, tool: Any, perms: Any, sanitized: dict[str, Any]
    ) -> str:
        return _variant_hypothesis(
            "hybrid",
            root,
            tool,
            perms,
            sanitized,
            query="delayed",
            session_allowlist=[
                s["session_id"] for s in sanitized.get("haystack_sessions", [])
            ],
            request_override=override,
        )

    run_longmemeval_case(
        records[0],
        decide_fn=decide_hybrid,
        max_total_tokens=10**6,
        workspace_root=tmp_path,
    )
    recalls = [c for c in calls if c.get("operation") == "recall"]
    assert recalls, "the hybrid arm queried memory"
    for call in recalls:
        raw = call["_result"]["raw"]
        assert raw.get("code") != "E_PERMISSION", raw
        assert "requires network" not in json.dumps(raw)

    # `p72-` cases get the same grants.
    corpus_manifest, corpus = load_dataset_section("phase72_hybrid_corpus")
    _queries_manifest, queries = load_dataset_section("phase72_hybrid_queries")
    seen72: list[Any] = []

    def decide72(
        root: Path, tool: Any, perms: Any, record: dict[str, Any]
    ) -> dict[str, Any]:
        seen72.append(perms)
        return {"returned_ids": [], "passed": False}

    result = run_phase72_case(
        queries[0],
        corpus,
        decide_fn=decide72,
        max_total_tokens=10**6,
        workspace_root=tmp_path,
    )
    assert seen72[0].network is True and seen72[0].cache_write is True
    assert result.phase72 == {"returned_ids": [], "passed": False}
    assert corpus_manifest.dataset == "rush_phase72_hybrid_corpus"


def test_t08_runner_forwards_embedding_config(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Hybrid arm: every retrieval request carries `retrieval="hybrid"` and the three fields
    of the frozen manifest's `phase72_embedding`, with the manifest case's own query; the
    current and metadata arms carry none. Agent-supplied `retrieval="lexical"` in an episode
    action is overridden and recorded."""
    support = _t08_support()
    from rush.tools.memory import MemoryTool

    manifest = json.loads(_T08_MANIFEST.read_text(encoding="utf-8"))
    override = _embedding_override(manifest)
    queries = {
        c["inputs"]["query"]: c["id"]
        for c in manifest["cases"]
        if c["id"].startswith("p72-")
    }
    assert len(queries) == 24

    from rush.memory import embeddings

    monkeypatch.setattr(
        embeddings, "_embed_batch", lambda config, batch: support.oracle_vectors(batch)
    )
    for variant in ("hybrid", "current", "metadata"):
        calls = _recording_run(monkeypatch)
        out = tmp_path / variant
        rc = main(
            [
                "--suite",
                "memory",
                "--task-manifest",
                str(_T08_MANIFEST),
                "--variant",
                variant,
                "--seeds",
                "1",
                "--max-total-tokens",
                "16000",
                "--output",
                str(out),
            ]
        )
        assert rc == 0, variant
        retrieval = [
            c
            for c in calls
            if c.get("subject") == "domain_knowledge"
            and c.get("operation") in {"ask", "recall", "list"}
        ]
        if variant == "metadata":
            assert retrieval, variant
            for call in retrieval:
                assert call["operation"] == "list" and call.get("request") is None
                assert call["freshness_filter"] == "fresh"
            continue
        asked = [c for c in retrieval if c.get("query") in queries]
        assert sorted(c["query"] for c in asked) == sorted(queries), variant
        for call in asked:
            request = call["request"]
            if variant == "hybrid":
                for key, value in override.items():
                    assert request[key] == value, (variant, key, request)
            else:
                assert not any(
                    k == "retrieval" or k.startswith("embedding_") for k in request
                ), (variant, request)
            assert call.get("session_allowlist") is None
            assert call["owner_scope"] in (
                support.READER,
                support.READER.as_dict(),
            ), call["owner_scope"]
        # The fixture root is isolated and holds no rush.toml.
        assert not any(Path(c["path"], "rush.toml").exists() for c in asked)

    # Episodes: the override reaches ask/recall/list requests only.
    from scripts.benchmarks import memory as bench_memory
    from scripts.benchmarks.memory import EpisodeAction, run_memory_episode

    steps = [
        EpisodeAction(
            operation="ask",
            kwargs={
                "subject": "episodic",
                "query": "needle",
                "session_allowlist": ["s"],
                "request": {"view": "compact", "retrieval": "lexical"},
            },
        ),
        EpisodeAction(
            operation="recall",
            kwargs={
                "subject": "episodic",
                "query": "needle",
                "session_allowlist": ["s"],
                "request": {"view": "compact", "limit": 3},
            },
        ),
        EpisodeAction(operation="submit", final="done"),
    ]
    recorder: list[dict[str, Any]] = []

    class Recording(MemoryTool):
        def run(self, path: Path, **kwargs: Any) -> Any:
            recorder.append(kwargs)
            return {"status": "ok", "raw": {"code": "OK", "data": {"items": []}}}

    monkeypatch.setattr(bench_memory, "MemoryTool", Recording)
    index = iter(steps)
    result = run_memory_episode(
        "t08",
        "task",
        lambda observation: next(index),
        root=tmp_path / "episode",
        permissions=_t08_permissions(),
        request_override=override,
    )
    sent = [k["request"] for k in recorder]
    assert sent[0] == {"view": "compact", **override}
    assert sent[1] == {"view": "compact", "limit": 3, **override}
    first, second = result.events
    assert first.override_applied == override
    assert first.override_replaced == {"retrieval": "lexical"}
    assert second.override_applied == override
    assert second.override_replaced == {}


def test_t08_overrides_only_retrieval_requests(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The override never touches write/handoff/receive/expand/verify_attempt kwargs; the
    named episodes pass identically; a retrieval action with no `request` passes unchanged
    and is recorded as skipped."""
    import re

    from rush.permissions import ExecutionPermissions
    from scripts.benchmarks import memory as bench_memory
    from scripts.benchmarks.memory import (
        EPISODE_BUILDERS,
        EpisodeAction,
        run_memory_episode,
    )

    support = _t08_support()
    override = {
        "retrieval": "hybrid",
        "embedding_endpoint": support.ENDPOINT,
        "embedding_model": support.MODEL,
        "embedding_model_digest": support.DIGEST,
    }
    permissions = ExecutionPermissions(
        network=True, cache_write=True, artifact_write=True, build=True
    )
    for episode in ("guest-handoff", "upload-repair"):
        runs: list[tuple[Any, list[str]]] = []
        for arm, request_override in (("current", None), ("hybrid", override)):
            root = tmp_path / f"{episode}-{arm}"
            root.mkdir()
            task, decide = EPISODE_BUILDERS[episode](root)
            result = run_memory_episode(
                episode,
                task,
                decide,
                root=root,
                permissions=permissions,
                request_override=request_override,
            )
            # Each root mints its own artifact uuids, handoff session ids, capability
            # secrets and git commit/tree ids; every other kwarg (the receiver's digest
            # included) must be equal between the arms.
            kwargs_by_step = [
                re.sub(
                    r'("(?:capability|session_id)": )"[^"]*"',
                    r'\1"<generated>"',
                    re.sub(
                        r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"
                        r'|(?<=")[0-9a-f]{40}(?=")',
                        "<generated>",
                        json.dumps(
                            {"op": e.operation, "kwargs": e.kwargs},
                            sort_keys=True,
                            default=str,
                        ),
                    ),
                )
                for e in result.events
            ]
            runs.append((result, kwargs_by_step))
        (current, current_kwargs), (hybrid, hybrid_kwargs) = runs
        assert current.outcome.value == "pass", (episode, current.outcome)
        assert hybrid.outcome.value == "pass", (episode, hybrid.outcome)
        assert hybrid_kwargs == current_kwargs, episode
        assert all(e.override_applied is None for e in hybrid.events)

    # A retrieval action without `request`: unchanged kwargs, a recorded skip.
    recorder: list[dict[str, Any]] = []

    class Recording(bench_memory.MemoryTool):
        def run(self, path: Path, **kwargs: Any) -> Any:
            recorder.append(kwargs)
            return {"status": "ok", "raw": {"code": "OK", "data": {"items": []}}}

    monkeypatch.setattr(bench_memory, "MemoryTool", Recording)
    steps = iter(
        [
            EpisodeAction(
                operation="ask",
                kwargs={
                    "subject": "episodic",
                    "query": "q",
                    "session_allowlist": ["s"],
                },
            ),
            EpisodeAction(operation="submit", final=None),
        ]
    )
    result = run_memory_episode(
        "skip",
        "task",
        lambda observation: next(steps),
        root=tmp_path / "skip",
        permissions=permissions,
        request_override=override,
    )
    assert "request" not in recorder[0]
    (event,) = result.events
    assert event.override_skipped == "no_request"
    assert event.override_applied is None


# --- R11, R16 ---------------------------------------------------------------------------


def test_t08_metadata_variant(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """`--variant metadata` is accepted and answers from the legacy `list` route: grant
    sources, owner, freshness `fresh`, no query, the first eight rows by id ascending."""
    from rush.memory.retrieval import _excerpt
    from scripts.benchmarks.run import (
        _MEMORY_VARIANTS,
        _variant_hypothesis,
        build_parser,
    )

    support = _t08_support()
    assert "metadata" in _MEMORY_VARIANTS
    args = build_parser().parse_args(["--suite", "memory", "--variant", "metadata"])
    assert args.variant == "metadata"

    env = support.frozen_env(tmp_path, monkeypatch)
    calls = _recording_run(monkeypatch)
    from rush.tools.memory import MemoryTool

    text = _variant_hypothesis(
        "metadata",
        env.root,
        MemoryTool(),
        _t08_permissions(),
        {},
        query="invoice retry limit",
        subject="domain_knowledge",
        owner_scope=support.READER,
    )
    (call,) = [c for c in calls if c.get("subject") == "domain_knowledge"]
    assert call["operation"] == "list"
    assert call.get("request") is None
    assert call["freshness_filter"] == "fresh"
    assert call["owner_filter"] == "user:p72-reader"
    assert sorted(call["session_allowlist"]) == ["p72-anchored", "p72-notes"]
    first_eight = sorted(
        r for r in support.FROZEN_CORPUS if r[1] not in support.SECURITY_ROLES
    )[:8]
    assert text == " ".join(_excerpt({"text": r[5]}) for r in first_eight)
    security_texts = [
        r[5] for r in support.FROZEN_CORPUS if r[1] in support.SECURITY_ROLES
    ]
    assert not any(t in text for t in security_texts)


def _find_keys(value: Any, found: set[str]) -> set[str]:
    if isinstance(value, dict):
        for key, item in value.items():
            found.add(key)
            _find_keys(item, found)
    elif isinstance(value, list):
        for item in value:
            _find_keys(item, found)
    return found


def test_t08_metadata_arm_and_freeze(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    support = _t08_support()
    manifest = json.loads(_T08_MANIFEST.read_text(encoding="utf-8"))
    # Frozen before any observation: the corpus ids, the case digest and the engine identity.
    assert manifest["phase72_cases_sha256"] == support.CASES_SHA256
    embedding = manifest["phase72_embedding"]
    assert set(embedding) == {"endpoint", "model", "model_digest"}
    assert embedding["endpoint"] == "http://127.0.0.1:11434"
    assert embedding["model"] == "nomic-embed-text"
    import re

    assert re.fullmatch(r"[0-9a-f]{12}", embedding["model_digest"]), embedding
    from scripts.benchmarks.memory_datasets import load_dataset_section

    _m, corpus = load_dataset_section("phase72_hybrid_corpus")
    assert [r["id"] for r in corpus] == [r[0] for r in support.FROZEN_CORPUS]

    # The metadata and current arms run per seed and report the T08 measurements; the
    # metadata arm stays out of the verdict rows (it is the baseline of the pairing check).
    from rush.memory import embeddings

    monkeypatch.setattr(
        embeddings, "_embed_batch", lambda config, batch: support.oracle_vectors(batch)
    )
    keys: dict[str, set[str]] = {}
    reports: dict[str, dict[str, Any]] = {}
    for variant in ("metadata", "current"):
        out = tmp_path / variant
        rc = main(
            [
                "--suite",
                "memory",
                "--task-manifest",
                str(_T08_MANIFEST),
                "--variant",
                variant,
                "--seeds",
                "1,2",
                "--max-total-tokens",
                "16000",
                "--output",
                str(out),
            ]
        )
        assert rc == 0, variant
        reports[variant] = json.loads(
            (out / "memory-suite-report.json").read_text(encoding="utf-8")
        )
        keys[variant] = _find_keys(reports[variant], set())
        wanted = {
            "retrieval_ms_p95",
            "page_tokens",
            "case_tokens",
            "case_ms",
            "embedded_texts",
            "chance_recall",
            "recall_at_8",
            "false_inclusion",
            "security_inclusion",
            "hybrid_pages",
            "fallback_pages",
        }
        assert wanted <= keys[variant], (variant, sorted(wanted - keys[variant]))
        p72 = [
            r
            for r in reports[variant]["case_results"]
            if r["case_id"].startswith("p72-")
        ]
        assert {r["seed"] for r in p72} == {1, 2}
        assert len(p72) == 48
    assert reports["metadata"]["variant"] == "metadata"

    # A rerun into an output directory whose recorded phase72_embedding differs is refused.
    other = dict(manifest)
    other["phase72_embedding"] = {**embedding, "model_digest": "a" * 12}
    changed = tmp_path / "changed-manifest.json"
    changed.write_text(json.dumps(other, indent=2) + "\n", encoding="utf-8")
    report_path = tmp_path / "current" / "memory-suite-report.json"
    before = report_path.read_bytes()
    rc = main(
        [
            "--suite",
            "memory",
            "--task-manifest",
            str(changed),
            "--variant",
            "current",
            "--seeds",
            "1,2",
            "--max-total-tokens",
            "16000",
            "--output",
            str(tmp_path / "current"),
        ]
    )
    assert rc == 1
    assert report_path.read_bytes() == before


# --- R21 --------------------------------------------------------------------------------


def test_t08_frozen_corpus_literal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    support = _t08_support()
    from scripts.benchmarks.memory_datasets import (
        _validate_section,
        load_dataset_section,
    )

    expected_manifest = {
        "url": "repo:tests/fixtures/benchmarks/memory_datasets.json",
        "revision": "phase72-v1",
        "license_or_terms": "Rush repository fixture",
        "split": "heldout",
    }
    corpus_manifest, corpus = load_dataset_section("phase72_hybrid_corpus")
    queries_manifest, queries = load_dataset_section("phase72_hybrid_queries")
    assert corpus_manifest.dataset == "rush_phase72_hybrid_corpus"
    assert queries_manifest.dataset == "rush_phase72_hybrid_queries"
    for manifest, sha in (
        (corpus_manifest, support.CORPUS_SHA256),
        (queries_manifest, support.QUERIES_SHA256),
    ):
        assert manifest.sha256 == sha
        for key, value in expected_manifest.items():
            assert getattr(manifest, key) == value, (manifest.dataset, key)
    assert corpus == support.corpus_records() and len(corpus) == 48
    assert queries == support.query_records() and len(queries) == 24
    assert support.records_digest(corpus) == support.CORPUS_SHA256
    assert support.records_digest(queries) == support.QUERIES_SHA256
    from collections import Counter

    assert Counter(r["role"] for r in corpus) == {
        "literal_positive": 12,
        "paraphrase_positive": 12,
        "near_neighbor": 12,
        "denied_owner": 4,
        "revoked_source": 4,
        "stale_hash": 4,
    }
    # Every answer sits (NFKC, casefold, collapsed whitespace) in its relevant record and
    # in no other corpus record.
    import unicodedata

    def norm(text: str) -> str:
        return " ".join(unicodedata.normalize("NFKC", text).casefold().split())

    by_id = {r["id"]: norm(r["content"]["text"]) for r in corpus}
    for query in queries:
        (relevant,) = query["relevant_ids"]
        holders = [rid for rid, text in by_id.items() if norm(query["answer"]) in text]
        assert holders == [relevant], (query["question_id"], holders)
    # A tampered record no longer validates against its declared digest.
    from scripts.benchmarks.contracts import FixtureError

    raw = json.loads(
        (
            Path(__file__).resolve().parent
            / "fixtures"
            / "benchmarks"
            / "memory_datasets.json"
        ).read_text(encoding="utf-8")
    )
    tampered = json.loads(json.dumps(raw["phase72_hybrid_corpus"]))
    tampered["records"][0]["content"]["text"] += " (edited)"
    with pytest.raises(FixtureError):
        _validate_section("phase72_hybrid_corpus", tampered)

    # The manifest: the baseline untouched, the 24 `p72-` cases equal the template and the
    # digest, and the actual loader accepts the file.
    from scripts.benchmarks.memory import (  # type: ignore[attr-defined]  # 75-T02 loader
        load_task_manifest,
    )

    text = _T08_MANIFEST.read_text(encoding="utf-8")
    raw_manifest = json.loads(text)
    assert isinstance(load_task_manifest(_T08_MANIFEST), dict)
    assert raw_manifest["phase72_cases_sha256"] == support.CASES_SHA256
    p72 = [c for c in raw_manifest["cases"] if c["id"].startswith("p72-")]
    assert p72 == support.manifest_cases()
    assert [c["id"] for c in raw_manifest["cases"]][:5] == [
        "lme-q-001",
        "lme-q-002",
        "upload-repair",
        "guest-handoff",
        "diagnosis-handoff",
    ]
    import hashlib

    from rush.delivery.compact import canonical_json

    assert (
        hashlib.sha256(canonical_json(sorted(p72, key=lambda c: c["id"]))).hexdigest()
        == support.CASES_SHA256
    )

    # Current arm over the seeded fixture records: the literal split is found, the
    # paraphrase split is the lexical miss, nothing unauthorized or stale comes back; the
    # metadata arm (list route) returns no security row either.
    env = support.make_env(tmp_path, monkeypatch, rows=None, policy=False, store=False)
    support.seed_frozen(env, corpus)
    security = {r["id"] for r in corpus if r["role"] in support.SECURITY_ROLES}
    hits = {"literal": 0, "paraphrase": 0}
    for query in raw_manifest["cases"][5:]:
        record = next(q for q in queries if q["question_id"] == query["id"])
        out = support.p72_recall(env, query["inputs"]["query"])
        assert out.code == "OK"
        assert not (set(out.ids) & security), (query["id"], out.ids)
        hits[record["split"]] += record["relevant_ids"][0] in out.ids
    assert hits == {"literal": 12, "paraphrase": 0}, hits
    from rush.permissions import ExecutionPermissions
    from rush.tools.memory import MemoryTool

    listed = MemoryTool().run(
        env.root,
        operation="list",
        subject="domain_knowledge",
        query="",
        session_allowlist=["p72-anchored", "p72-notes"],
        owner_scope=support.READER.as_dict(),
        owner_filter="user:p72-reader",
        freshness_filter="fresh",
        permissions=ExecutionPermissions(network=True, cache_write=True),
    )
    assert listed["raw"] is not None
    assert not ({row["id"] for row in listed["raw"]} & security)


# --- R22 --------------------------------------------------------------------------------

_FAKE_HELP = """Usage: fake [options]
  -c, --config
  -p, --print
  --tools
  --output-format
  --permission-mode
  --safe-mode
  --strict-mcp-config
  --no-session-persistence
  --ephemeral
  --ignore-rules
  --ignore-user-config
  --strict-config
  --enable
  --disable
  --json
  --sandbox
  --skip-git-repo-check
"""


def _fake_provider_reply(args: list[str]) -> tuple[int, str]:
    """What a hermetic decision provider prints for one invocation: the help text listing
    every hermetic flag (`--help` and `exec --help`), a fixed version, or one decision in
    the route's output format with a constant 4000 model tokens. A dataset decision answers
    with the recalled excerpts the request carries; an episode decision submits at once."""
    if args and args[-1] == "--help":
        return 0, _FAKE_HELP
    if args == ["--version"]:
        return 0, "fake 0.162.1\n"
    prompt = args[-1]
    request, _end = json.JSONDecoder().raw_decode(prompt.split("\nREQUEST:\n", 1)[1])
    kind = request.get("decision_kind")
    if kind == "episode":
        decision: dict[str, Any] = {"kind": "submit", "final": None}
    elif kind == "preflight":
        decision = {"kind": "answer", "text": "ok"}
    else:
        decision = {"kind": "answer", "text": str(request.get("variant_context") or "")}
    text = json.dumps(decision)
    if args[0] == "exec":
        events = [
            {"type": "thread.started", "thread_id": "thread-0123456789"},
            {"type": "turn.started"},
            {
                "type": "item.completed",
                "item": {"id": "item_0", "type": "agent_message", "text": text},
            },
            {
                "type": "turn.completed",
                "usage": {
                    "input_tokens": 3000,
                    "cached_input_tokens": 0,
                    "output_tokens": 1000,
                },
            },
        ]
        return 0, "".join(json.dumps(event) + "\n" for event in events)
    result = {
        "type": "result",
        "subtype": "success",
        "is_error": False,
        "result": text,
        "num_turns": 1,
        "session_id": "session-0123456789",
        "usage": {
            "input_tokens": 3000,
            "cache_creation_input_tokens": 0,
            "cache_read_input_tokens": 0,
            "output_tokens": 1000,
        },
        "modelUsage": {"fake-model": {}},
    }
    return 0, json.dumps(result) + "\n"


def _install_fake_provider(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[Path, list[dict[str, Any]]]:
    """A provider executable that is only a file: every `subprocess.run` of its path is
    answered in-process, on every OS (the harness never goes through a shell), and the
    original production argv and environment are recorded."""
    import subprocess
    import sys

    exe = tmp_path / (
        "fake-provider.exe" if sys.platform == "win32" else "fake-provider"
    )
    exe.write_text("# fixture provider: invocations are answered in-process\n")
    exe.chmod(0o755)
    calls: list[dict[str, Any]] = []
    real_run = subprocess.run

    def fake_run(argv: Any, *args: Any, **kwargs: Any) -> Any:
        if (
            isinstance(argv, (list, tuple))
            and argv
            and Path(str(argv[0])).resolve() == exe.resolve()
        ):
            assert not kwargs.get("shell"), "decision invocations never use a shell"
            calls.append(
                {
                    "argv": [str(a) for a in argv],
                    "env": kwargs.get("env"),
                    "cwd": kwargs.get("cwd"),
                }
            )
            code, out = _fake_provider_reply([str(a) for a in argv[1:]])
            return subprocess.CompletedProcess(argv, code, out, "")
        return real_run(argv, *args, **kwargs)

    monkeypatch.setattr(subprocess, "run", fake_run)
    return exe, calls


def _partial_oracle(support: Any) -> Any:
    two = {"p72-q13", "p72-q14"}
    answered = {
        q[2] for q in support.FROZEN_QUERIES if q[0] in two
    }  # their query texts

    def vectors(batch: Any) -> list[list[float]]:
        out = []
        for text, vector in zip(batch, support.oracle_vectors(batch), strict=True):
            if text in {q[2] for q in support.FROZEN_QUERIES} and text not in answered:
                # A query outside the two answered ones lies on the spare axis: every
                # cosine is zero and the vector order is the id order.
                vector = [0.0] * (len(vector) - 1) + [1.0]
            out.append(vector)
        return out

    return vectors


@pytest.mark.parametrize(
    ("scenario", "expected"),
    [
        pytest.param("oracle", "benefit", id="oracle"),
        pytest.param("uniform", "harm", id="uniform"),
        pytest.param("partial_oracle", "no_benefit", id="partial_oracle"),
    ],
)
def test_t08_verdict_reachable_end_to_end(
    scenario: str, expected: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The whole path: CLI parser, manifest loader, fixture verification, route preflight,
    the live-decision case dispatch (a fixture decider answers from the recalled excerpts),
    the report writer and the verdict aggregator -- both routes, three arms, seeds 1,2,3."""
    support = _t08_support()
    from rush.memory import embeddings

    # This fixture tests verdict reachability, independent of host scheduling.
    clock = count()
    monkeypatch.setattr(
        "scripts.benchmarks.run.time",
        SimpleNamespace(perf_counter=lambda: next(clock) / 1000),
    )
    vectors = {
        "oracle": support.oracle_vectors,
        "uniform": support.uniform_vectors,
        "partial_oracle": _partial_oracle(support),
    }[scenario]
    monkeypatch.setattr(
        embeddings, "_embed_batch", lambda config, batch: vectors(batch)
    )
    provider, provider_calls = _install_fake_provider(tmp_path, monkeypatch)
    original_home = os.environ["HOME"]
    eval_root = tmp_path / "eval"
    for route in _T08_ROUTES:
        for arm in ("current", "hybrid", "metadata"):
            rc = main(
                [
                    "--suite",
                    "memory",
                    "--decision-mode",
                    "live",
                    "--decision-route",
                    route,
                    "--allow-live-route",
                    route,
                    "--task-manifest",
                    str(_T08_MANIFEST),
                    "--variant",
                    arm,
                    "--seeds",
                    "1,2,3",
                    "--max-total-tokens",
                    "16000",
                    "--provider-executable",
                    str(provider),
                    "--output",
                    str(eval_root / arm / route),
                ]
            )
            assert rc == 0, (scenario, route, arm)
            report = json.loads(
                (eval_root / arm / route / "memory-suite-report.json").read_text(
                    encoding="utf-8"
                )
            )
            assert {round(row["case_ms"], 6) for row in report["verdict_rows"]} == {5.0}
    verdict = json.loads(
        (eval_root / "hybrid-verdict.json").read_text(encoding="utf-8")
    )

    def name(value: Any) -> Any:
        return value["verdict"] if isinstance(value, dict) else value

    assert name(verdict["global"]) == expected, verdict
    assert {name(v) for v in verdict["per_provider"].values()} == {expected}, verdict
    # Every provider process kept the original environment, the harness redirected only
    # its in-process Rush calls.
    assert provider_calls, "the decision provider was invoked"
    for call in provider_calls:
        assert call["env"] is not None and call["env"]["HOME"] == original_home, call
    decisions = [c for c in provider_calls if c["argv"][-1].count("\nREQUEST:\n") == 1]
    assert decisions, "decision invocations carry one REQUEST"
    # The gold keys and the corpus roles never reach a decision request.
    forbidden_keys = {"relevant_ids", "split", "role"}
    forbidden_values = set(support.SECURITY_ROLES) | {
        "literal_positive",
        "paraphrase_positive",
        "near_neighbor",
    }

    def walk(node: Any) -> Any:
        if isinstance(node, dict):
            for key, value in node.items():
                yield key, value
                yield from walk(value)
        elif isinstance(node, list):
            for value in node:
                yield None, value
                yield from walk(value)

    for call in decisions:
        request, _end = json.JSONDecoder().raw_decode(
            call["argv"][-1].split("\nREQUEST:\n", 1)[1]
        )
        for key, value in walk(request):
            assert key not in forbidden_keys, (key, call["argv"][:2])
            assert not (isinstance(value, str) and value in forbidden_values), value


# --- R23 --------------------------------------------------------------------------------


def test_t08_committed_eval_output_redacted(tmp_path: Path) -> None:
    import re

    from scripts.benchmarks.reporting import write_memory_suite_report

    patterns = [
        re.compile(r"/Users/"),
        re.compile(r"/home/"),
        re.compile(r"sk-ant-[A-Za-z0-9_-]{8,}"),
        re.compile(r"\bsk-[A-Za-z0-9]{16,}"),
    ]
    id_key = re.compile(r'"(?:session_id|thread_id)"\s*:\s*"([^"]*)"')

    def scan(root: Path) -> list[str]:
        problems: list[str] = []
        for path in sorted(root.rglob("*")):
            if not path.is_file():
                continue
            text = path.read_text(encoding="utf-8", errors="replace")
            for pattern in patterns:
                if pattern.search(text):
                    problems.append(f"{path}: {pattern.pattern}")
            for match in id_key.finditer(text):
                if not re.fullmatch(r"redacted:[0-9a-f]{12}", match.group(1)):
                    problems.append(f"{path}: unhashed id {match.group(1)!r}")
        return problems

    if _T08_EVAL_DIR.exists():
        assert scan(_T08_EVAL_DIR) == []

    secret = "sk-ant-" + "A" * 24
    home_path = f"{Path.home()}/proj"
    payload = {
        "note": f"token {secret} at {home_path}",
        "events": [{"session_id": "0123456789abcdef", "thread_id": "fedcba9876543210"}],
    }
    out = tmp_path / "report"
    path = write_memory_suite_report(out, payload)
    assert scan(out) == []
    written = json.loads(path.read_text(encoding="utf-8"))
    assert secret not in path.read_text(encoding="utf-8")
    assert str(Path.home()) not in path.read_text(encoding="utf-8")
    assert written["redaction_count"] >= 4, written["redaction_count"]
    assert not list(out.glob("*.tmp"))


# --- D14 --------------------------------------------------------------------------------


def test_t08_provider_env_not_redirected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Provider subprocesses take the caller's environment: `env=` reaches every
    `subprocess.run` in the route probes, and `None` keeps today's inherited environment."""
    from scripts.benchmarks.contracts import Outcome, RouteDescriptor, Scenario
    from scripts.benchmarks.fixtures import load_routers
    from scripts.benchmarks.providers import run_provider_probe, run_router_probe

    route = RouteDescriptor(
        provider_id="anthropic",
        route_id="anthropic-claude-code-live",
        mode="oauth_cli",
        command=["claude", "-p", "Reply with exactly BENCHMARK_OK."],
        official_docs_url="https://docs.anthropic.com",
        terms_url="https://anthropic.com/terms",
        privacy_url="https://anthropic.com/privacy",
        credential_boundary="local Claude Code OAuth profile",
        redaction_patterns=["sk-ant-.*"],
    )
    scenario = Scenario(
        scenario_id="sc-provider-env",
        probe="provider",
        category="handoff",
        input={"route_id": "anthropic-claude-code-live"},
        required_facts=(),
        expected_outcome=Outcome.PASS,
    )
    seen: list[Any] = []

    class Done:
        returncode = 0
        stdout = '{"result":"BENCHMARK_OK"}'
        stderr = ""

    def fake_run(cmd: Any, **kwargs: Any) -> Any:
        seen.append(kwargs.get("env", "absent"))
        return Done()

    monkeypatch.setattr("subprocess.run", fake_run)
    original = {
        "HOME": str(tmp_path / "original-home"),
        "PATH": os.environ.get("PATH", ""),
    }
    run_provider_probe(
        scenario,
        allow_live_route="anthropic-claude-code-live",
        custom_route=route,
        env=original,
    )
    assert seen == [original]
    seen.clear()
    run_provider_probe(
        scenario, allow_live_route="anthropic-claude-code-live", custom_route=route
    )
    assert seen in (["absent"], [None])

    routers = load_routers()
    router_name, router = next(
        (name, entry)
        for name, entry in routers.items()
        if entry.get("cli_command")
        and entry.get("cli_marker")
        and entry.get("route_id")
    )
    router_scenario = Scenario(
        scenario_id="router-env",
        probe="provider",
        category="budget",
        input={"router_id": router_name},
        required_facts=(),
        expected_outcome=Outcome.DEFERRED,
    )
    seen.clear()
    run_router_probe(router_scenario, allow_live_route=router["route_id"], env=original)
    assert seen and all(value == original for value in seen), seen


# --- G4: the manifest names the same engine identity the config does --------------------


def _t08_manifest_with_embedding(tmp_path: Path, embedding: Any) -> Path:
    """The shipped baseline plus the 24 template `p72-` cases and the given
    `phase72_embedding` value, written next to the test (the shipped file is untouched)."""
    support = _t08_support()
    shipped = json.loads(_T08_MANIFEST.read_text(encoding="utf-8"))
    manifest = dict(shipped)
    manifest["cases"] = [
        *(c for c in shipped["cases"] if not c["id"].startswith("p72-")),
        *support.manifest_cases(),
    ]
    manifest["phase72_cases_sha256"] = support.CASES_SHA256
    manifest["phase72_embedding"] = embedding
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return path


_T08_MANIFEST_ENDPOINTS = {
    "manifest_port_absent": "http://127.0.0.1",
    "manifest_port_0": "http://127.0.0.1:0",
    "manifest_port_65536": "http://127.0.0.1:65536",
    "manifest_scheme_https": "https://127.0.0.1:11434",
    "manifest_scheme_file": "file:///tmp/p72-embed",
    "manifest_userinfo": "http://u:p@127.0.0.1:11434",
    "manifest_host_nip_io": "http://127.0.0.1.nip.io:11434",
    "manifest_host_localhost_suffix": "http://localhost.evil.test:11434",
    "manifest_host_zero": "http://0.0.0.0:11434",
    "manifest_host_remote": "http://10.0.0.1:11434",
    "manifest_path": "http://127.0.0.1:11434/api",
    "manifest_query": "http://127.0.0.1:11434?x=1",
    "manifest_fragment": "http://127.0.0.1:11434#frag",
    "manifest_trailing_cr": "http://127.0.0.1:11434\r",
    "manifest_trailing_lf": "http://127.0.0.1:11434\n",
    "manifest_trailing_space": "http://127.0.0.1:11434 ",
    "manifest_control_nul": "http://127.0.0.1:11434\x00",
    "manifest_control_del": "http://127.0.0.1:11434\x7f",
}


@pytest.mark.parametrize("name", list(_T08_MANIFEST_ENDPOINTS))
def test_t08_manifest_embedding_endpoint_predicate(
    name: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A manifest endpoint is judged by the predicate the config surface uses: loopback
    http, an explicit port 1-65535, no userinfo, path, query, fragment or control character.
    A refusal is `invalid_value`, before any provider, embedding or output effect."""
    from rush.memory import embeddings
    from rush.memory.embeddings import config_endpoint_ok

    endpoint = _T08_MANIFEST_ENDPOINTS[name]
    assert config_endpoint_ok(endpoint) is False, name
    embed_calls: list[Any] = []
    monkeypatch.setattr(
        embeddings, "_embed_batch", lambda config, batch: embed_calls.append(batch)
    )
    provider, provider_calls = _install_fake_provider(tmp_path, monkeypatch)
    embedding = {
        "endpoint": endpoint,
        "model": "nomic-embed-text",
        "model_digest": "0123456789ab",
    }
    manifest = _t08_manifest_with_embedding(tmp_path, embedding)
    out = tmp_path / "out"
    rc = main(
        [
            "--suite",
            "memory",
            "--task-manifest",
            str(manifest),
            "--variant",
            "current",
            "--seeds",
            "1",
            "--max-total-tokens",
            "16000",
            "--provider-executable",
            str(provider),
            "--output",
            str(out),
        ]
    )
    err = capsys.readouterr().err
    assert rc == 1, (name, err)
    assert "Memory suite error: " in err and "invalid_value" in err, (name, err)
    assert "Traceback" not in err
    assert not out.exists()
    assert provider_calls == [] and embed_calls == []
    for good in (
        "http://127.0.0.1:11434",
        "http://localhost:11434",
        "http://[::1]:11434",
    ):
        assert config_endpoint_ok(good) is True, good


@pytest.mark.parametrize(
    ("name", "embedding", "code"),
    [
        pytest.param(
            "manifest_endpoint_list",
            {
                "endpoint": ["http://127.0.0.1:11434"],
                "model": "nomic-embed-text",
                "model_digest": "0123456789ab",
            },
            "wrong_type",
            id="manifest_endpoint_list",
        ),
        pytest.param(
            "manifest_endpoint_dict",
            {
                "endpoint": {"url": "http://127.0.0.1:11434"},
                "model": "nomic-embed-text",
                "model_digest": "0123456789ab",
            },
            "wrong_type",
            id="manifest_endpoint_dict",
        ),
        pytest.param(
            "manifest_model_list",
            {
                "endpoint": "http://127.0.0.1:11434",
                "model": ["nomic-embed-text"],
                "model_digest": "0123456789ab",
            },
            "wrong_type",
            id="manifest_model_list",
        ),
        pytest.param(
            "manifest_digest_dict",
            {
                "endpoint": "http://127.0.0.1:11434",
                "model": "nomic-embed-text",
                "model_digest": {"digest": "0123456789ab"},
            },
            "wrong_type",
            id="manifest_digest_dict",
        ),
        pytest.param(
            "manifest_embedding_list",
            ["http://127.0.0.1:11434"],
            "wrong_type",
            id="manifest_embedding_list",
        ),
        pytest.param(
            "manifest_digest_upper",
            {
                "endpoint": "http://127.0.0.1:11434",
                "model": "nomic-embed-text",
                "model_digest": "ABCDEF123456",
            },
            "invalid_value",
            id="manifest_digest_upper",
        ),
        pytest.param(
            "manifest_model_slash",
            {
                "endpoint": "http://127.0.0.1:11434",
                "model": "a/b",
                "model_digest": "0123456789ab",
            },
            "invalid_value",
            id="manifest_model_slash",
        ),
    ],
)
def test_t08_manifest_embedding_shapes_refused_before_any_call(
    name: str,
    embedding: Any,
    code: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Every non-string and malformed identity field is refused with its declared code and
    no traceback: a list or dict never reaches a hash-based membership test."""
    provider, provider_calls = _install_fake_provider(tmp_path, monkeypatch)
    manifest = _t08_manifest_with_embedding(tmp_path, embedding)
    out = tmp_path / "out"
    rc = main(
        [
            "--suite",
            "memory",
            "--task-manifest",
            str(manifest),
            "--variant",
            "current",
            "--seeds",
            "1",
            "--max-total-tokens",
            "16000",
            "--provider-executable",
            str(provider),
            "--output",
            str(out),
        ]
    )
    err = capsys.readouterr().err
    assert rc == 1, (name, err)
    assert f"Memory suite error: {code}" in err, (name, err)
    assert "Traceback" not in err
    assert not out.exists() and provider_calls == []


def test_t08_manifest_deeply_nested_identity_is_refused_without_traceback(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A manifest nested past the recursion limit is a plain refusal: no RecursionError
    escapes `main`, nothing is written and no provider runs."""
    provider, provider_calls = _install_fake_provider(tmp_path, monkeypatch)
    manifest = _t08_manifest_with_embedding(tmp_path, {})
    depth = 20_000
    text = manifest.read_text(encoding="utf-8")
    head, _, _tail = text.rpartition('"phase72_embedding"')
    nested = "[" * depth + "]" * depth
    manifest.write_text(
        head + '"phase72_embedding": {"endpoint": ' + nested + "}\n}\n",
        encoding="utf-8",
    )
    out = tmp_path / "out"
    rc = main(
        [
            "--suite",
            "memory",
            "--task-manifest",
            str(manifest),
            "--variant",
            "current",
            "--seeds",
            "1",
            "--max-total-tokens",
            "16000",
            "--provider-executable",
            str(provider),
            "--output",
            str(out),
        ]
    )
    err = capsys.readouterr().err
    assert rc == 1, err
    assert "Memory suite error: " in err and "Traceback" not in err
    assert not out.exists() and provider_calls == []


# --- B10: the loader and the fixture verification know exactly one extra dataset pair ---

_T08_PAIR_REFUSALS: dict[str, dict[str, Any]] = {
    "pair_queries_without_corpus": {"corpus_section": None},
    "pair_longmemeval_with_corpus": {
        "section": "longmemeval",
        "corpus_section": "phase72_hybrid_corpus",
    },
    "pair_corpus_names_queries": {"corpus_section": "phase72_hybrid_queries"},
    "pair_corpus_as_section": {"section": "phase72_hybrid_corpus"},
    "pair_unknown_section": {"section": "phase72_hybrid_other"},
    "pair_unknown_record": {"record_id": "p72-q99"},
    "pair_record_of_other_section": {"record_id": "lme-q-001"},
}


def _t08_spy_phase72_case(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    """Record every `run_phase72_case` call (its keyword arguments) and run the real one."""
    from scripts.benchmarks import memory_datasets

    real = memory_datasets.run_phase72_case
    seen: list[dict[str, Any]] = []

    def spy(*args: Any, **kwargs: Any) -> Any:
        seen.append(dict(kwargs))
        return real(*args, **kwargs)

    monkeypatch.setattr(memory_datasets, "run_phase72_case", spy)
    return seen


def _t08_run_manifest(
    manifest: Path, provider: Path, out: Path, *, variant: str = "current"
) -> int:
    return main(
        [
            "--suite",
            "memory",
            "--task-manifest",
            str(manifest),
            "--variant",
            variant,
            "--seeds",
            "1",
            "--max-total-tokens",
            "16000",
            "--provider-executable",
            str(provider),
            "--output",
            str(out),
        ]
    )


@pytest.mark.parametrize("name", list(_T08_PAIR_REFUSALS))
def test_t08_dataset_pair_outside_the_two_known_is_invalid_value(
    name: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A dataset case names exactly (`longmemeval`, None) or the Phase 72 pair; any other
    section/corpus pair, or a record of another section, is `invalid_value` before a
    fixture is seeded, a provider is run or an output file is written."""
    embedding = {
        "endpoint": "http://127.0.0.1:11434",
        "model": "nomic-embed-text",
        "model_digest": "0123456789ab",
    }
    manifest_path = _t08_manifest_with_embedding(tmp_path, embedding)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    first = next(c for c in manifest["cases"] if c["id"] == "p72-q01")
    first["inputs"] = {**first["inputs"], **_T08_PAIR_REFUSALS[name]}
    # The digest of the template cases is part of the manifest: recompute it for the
    # edited case so the refusal under test is the pair, not a stale digest.
    import hashlib

    from rush.delivery.compact import canonical_json

    p72 = sorted(
        (c for c in manifest["cases"] if c["id"].startswith("p72-")),
        key=lambda c: c["id"],
    )
    manifest["phase72_cases_sha256"] = hashlib.sha256(canonical_json(p72)).hexdigest()
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    seeded = _t08_spy_phase72_case(monkeypatch)
    provider, provider_calls = _install_fake_provider(tmp_path, monkeypatch)
    out = tmp_path / "out"
    rc = _t08_run_manifest(manifest_path, provider, out)
    err = capsys.readouterr().err
    assert rc == 1, (name, err)
    assert "Memory suite error: " in err and "invalid_value" in err, (name, err)
    assert "Traceback" not in err
    assert not out.exists()
    assert seeded == [] and provider_calls == [], (name, seeded, provider_calls)


def test_t08_fixture_verification_builds_the_phase72_pair_without_a_budget(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """B10: manifest mode builds each `p72-` fixture once under `<workspace>/verify/<index>`
    through `run_phase72_case` with `max_total_tokens=None` (no live decision can be
    charged), recomputes the declared `fixture_revision`, and a mismatch stops the run with
    `fixture_revision_mismatch` before route preflight or any provider call."""
    embedding = {
        "endpoint": "http://127.0.0.1:11434",
        "model": "nomic-embed-text",
        "model_digest": "0123456789ab",
    }
    manifest_path = _t08_manifest_with_embedding(tmp_path, embedding)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    changed = next(c for c in manifest["cases"] if c["id"] == "p72-q07")
    assert changed["fixture_revision"] != "0" * 64
    changed["fixture_revision"] = "0" * 64
    import hashlib

    from rush.delivery.compact import canonical_json

    p72 = sorted(
        (c for c in manifest["cases"] if c["id"].startswith("p72-")),
        key=lambda c: c["id"],
    )
    manifest["phase72_cases_sha256"] = hashlib.sha256(canonical_json(p72)).hexdigest()
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    seen = _t08_spy_phase72_case(monkeypatch)
    provider, provider_calls = _install_fake_provider(tmp_path, monkeypatch)
    out = tmp_path / "out"
    rc = _t08_run_manifest(manifest_path, provider, out)
    err = capsys.readouterr().err
    assert rc == 1, err
    assert "fixture_revision_mismatch" in err and "Traceback" not in err, err
    assert not out.exists() and provider_calls == []
    assert len(seen) >= 7, len(
        seen
    )  # p72-q01 .. p72-q07 were built before the mismatch
    for call in seen:
        assert call["max_total_tokens"] is None, call
        assert "verify" in Path(str(call["workspace_root"])).parts, call


# --- G3: the redirected environment and temporary roots are restored on every exit ------


@pytest.mark.parametrize(
    "cleanup_fails", [False, True], ids=["primary", "primary_and_cleanup"]
)
def test_t08_suite_restores_environment_and_names_every_failure(
    cleanup_fails: bool,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The suite redirects HOME/XDG_DATA_HOME/LOCALAPPDATA for its in-process Rush calls
    only. When a case fails, the originals are back, the temporary root is gone, and the
    one diagnostic names the primary failure and, when cleanup also fails, the cleanup
    failure too: a cleanup error never replaces the primary one."""
    import tempfile

    originals = {
        "HOME": str(tmp_path / "orig-home"),
        "XDG_DATA_HOME": str(tmp_path / "orig-xdg"),
        "LOCALAPPDATA": str(tmp_path / "orig-local"),
    }
    for key, value in originals.items():
        monkeypatch.setenv(key, value)
    scratch = tmp_path / "tmp-root"
    scratch.mkdir()
    monkeypatch.setattr(tempfile, "tempdir", str(scratch))

    called: list[str] = []

    def failing_case(*args: Any, **kwargs: Any) -> Any:
        called.append("case")
        assert os.environ["HOME"] != originals["HOME"], (
            "in-process calls are redirected"
        )
        raise ValueError("p72 primary failure")

    from scripts.benchmarks import memory_datasets
    from scripts.benchmarks import run as run_module

    monkeypatch.setattr(memory_datasets, "run_phase72_case", failing_case)
    monkeypatch.setattr(run_module, "run_phase72_case", failing_case, raising=False)
    if cleanup_fails:
        real_cleanup = tempfile.TemporaryDirectory.cleanup

        def failing_cleanup(self: Any, *args: Any, **kwargs: Any) -> None:
            real_cleanup(self, *args, **kwargs)
            raise OSError("p72 cleanup failure")

        monkeypatch.setattr(tempfile.TemporaryDirectory, "cleanup", failing_cleanup)
    manifest = _t08_manifest_with_embedding(
        tmp_path,
        {
            "endpoint": "http://127.0.0.1:11434",
            "model": "nomic-embed-text",
            "model_digest": "0123456789ab",
        },
    )
    rc = main(
        [
            "--suite",
            "memory",
            "--task-manifest",
            str(manifest),
            "--variant",
            "current",
            "--seeds",
            "1",
            "--max-total-tokens",
            "16000",
            "--output",
            str(tmp_path / "out"),
        ]
    )
    err = capsys.readouterr().err
    assert called, "the run reached its first p72 case"
    assert rc == 1, err
    assert "p72 primary failure" in err, err
    if cleanup_fails:
        assert "p72 cleanup failure" in err, err
    for key, value in originals.items():
        assert os.environ[key] == value, key
    assert list(scratch.iterdir()) == [], "the temporary root was removed"


def test_t08_instruction_files_follow_the_provider_env(tmp_path: Path) -> None:
    """The recorded Codex instruction file is the one the provider process
    loads (its env's HOME/CODEX_HOME), not the harness's temporary HOME."""
    from scripts.benchmarks.providers import DecisionRoute, _instruction_files

    route = DecisionRoute(
        route_id="openai-codex-oauth-cli-live",
        format="codex_exec_jsonl",
        executable=tmp_path / "codex",
        protocol={"instruction_files": ["$CODEX_HOME/AGENTS.md"]},
        timeout_s=1.0,
    )
    real_home = tmp_path / "real"
    (real_home / ".codex").mkdir(parents=True)
    (real_home / ".codex" / "AGENTS.md").write_text("rules\n", encoding="utf-8")
    [entry] = _instruction_files(route, {"HOME": str(real_home)})
    assert entry["path"] == str(real_home / ".codex" / "AGENTS.md")
    assert entry["present"] is True
    other = tmp_path / "codex-home"
    [entry] = _instruction_files(
        route, {"HOME": str(real_home), "CODEX_HOME": str(other)}
    )
    assert entry["path"] == str(other / "AGENTS.md") and entry["present"] is False
