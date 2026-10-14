"""Main entrypoint and scenario dispatcher for Rush benchmark harness."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import stat
import sys
import tempfile
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, cast

from rush.delivery.compact import canonical_json
from rush.io.physical_paths import ContainmentError, PhysicalRoot
from rush.memory.retrieval import MemoryAccess, _excerpt
from rush.memory.store import MemorySubject, OwnerScope, TypedArtifactStore
from rush.patch_generator import patch_target_paths
from rush.permissions import ExecutionPermissions
from rush.tools.memory import MemoryTool

# D13a: `python scripts/benchmarks/run.py` (script form) resolves the
# relative imports below exactly like `python -m scripts.benchmarks.run`.
if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    __package__ = "scripts.benchmarks"

from . import memory_datasets
from .contracts import (
    DecisionBudget,
    DecisionResult,
    FixtureError,
    Outcome,
    ProbeResult,
)
from .fixtures import load_scenarios
from .memory import (
    BASELINE_CASES_SHA256,
    EPISODE_BUILDERS,
    EPISODE_OPERATION_KWARGS,
    OPERATION_SCHEMAS,
    EpisodeAction,
    EpisodeObservation,
    expand_python_token,
    fixture_revision,
    load_task_manifest,
    normalized_contains,
    receiver_readback_acknowledged,
    run_memory_episode,
    run_named_episode,
    verifier_receipt_completed,
)
from .memory_datasets import (
    CountingMemoryTool,
    DatasetCaseResult,
    aggregate_dataset_results,
    load_dataset_section,
    run_longmemeval_case,
    strip_longmemeval_gold,
)
from .providers import (
    invocation_record,
    preflight_decision_route,
    resolve_decision_route,
    run_memory_decision,
)
from .reporting import (
    HYBRID_ARMS,
    chance_recall,
    paired_bootstrap_ci,
    recall_at_k,
    redact_report,
    write_hybrid_verdict,
    write_memory_suite_report,
    write_result,
)

_MEMORY_VARIANTS = (
    "none",
    "current",
    "raw",
    "budgeted",
    "linked",
    "full",
    "hybrid",
    "metadata",
)
_VARIANT_MAX_TOKENS = {"budgeted": 256, "current": 2048, "full": 16000}
# 72-T08: the in-process Rush calls of a memory-suite run see these redirected into a
# temporary root; provider subprocesses keep the caller's original environment.
_ISOLATED_ENV_KEYS = ("HOME", "XDG_DATA_HOME", "LOCALAPPDATA")
# The frozen `p72-` corpus: 48 records, 12 of them security-role records no arm may
# return, so `E_i = 36` eligible records per case.
_P72_ELIGIBLE = 36
_P72_SECURITY_ROLES = frozenset({"denied_owner", "revoked_source", "stale_hash"})
_P72_READER = OwnerScope("user", "p72-reader")
_P72_QUERIES_SECTION = "phase72_hybrid_queries"
_P72_CORPUS_SECTION = "phase72_hybrid_corpus"

# Probe registry forward references (imported lazily or dynamically)
_PROBE_MAP: dict[str, Callable[..., ProbeResult]] = {}


def register_probe(name: str, fn: Callable[..., ProbeResult]) -> None:
    """Registers a probe runner function for a scenario probe category."""
    _PROBE_MAP[name] = fn


def get_probe_runner(probe_name: str) -> Callable[..., ProbeResult]:
    """Retrieves probe runner for category or lazy-loads probe modules."""
    if probe_name not in _PROBE_MAP:
        if probe_name == "provider":
            from . import providers

            _PROBE_MAP["provider"] = providers.run_provider_probe
        elif probe_name == "protocol":
            from . import protocol

            _PROBE_MAP["protocol"] = protocol.run_protocol_probe
        elif probe_name == "privacy":
            from . import privacy

            _PROBE_MAP["privacy"] = privacy.run_privacy_probe
        elif probe_name == "context":
            from . import context

            _PROBE_MAP["context"] = context.run_context_probe
        elif probe_name == "coordination":
            from . import coordination

            _PROBE_MAP["coordination"] = coordination.run_coordination_probe
        elif probe_name == "local":
            from . import local

            _PROBE_MAP["local"] = local.run_local_probe
        elif probe_name == "memory":
            from . import memory

            _PROBE_MAP["memory"] = memory.run_memory_probe
        else:
            raise FixtureError(f"unknown probe: {probe_name}")
    return _PROBE_MAP[probe_name]


def build_parser() -> argparse.ArgumentParser:
    """Builds the strict argument parser for benchmark harness execution."""
    parser = argparse.ArgumentParser(
        description="Rush Deterministic Benchmark Harness",
        prog="python -m scripts.benchmarks.run",
    )
    parser.add_argument(
        "--scenario",
        type=str,
        help="Single scenario ID to execute (from scenarios.json)",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Execute all declared scenarios in scenarios.json",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("research/benchmark/run"),
        help="Destination directory for benchmark result JSON files",
    )
    parser.add_argument(
        "--model-cache",
        type=Path,
        default=None,
        help="External model cache directory for local model benchmarks (must resolve outside repo)",
    )
    parser.add_argument(
        "--allow-live-route",
        type=str,
        action="append",
        default=[],
        help="Explicit opt-in route ID for live provider invocation; repeat as needed",
    )
    parser.add_argument(
        "--provider-executable",
        type=Path,
        default=None,
        help="Explicit executable path for the selected live provider CLI",
    )
    parser.add_argument(
        "--router-url",
        action="append",
        default=[],
        help="Explicit router endpoint as NAME=URL; repeat for multiple routers",
    )
    parser.add_argument(
        "--local-runtime-executable",
        type=Path,
        action="append",
        default=[],
        help="Explicit external llama.cpp and/or onnxruntime_perf_test executable; repeat as needed",
    )
    parser.add_argument(
        "--allow-model-download",
        type=str,
        action="append",
        default=[],
        help="Explicit candidate ID for downloading local model weights into external model cache",
    )
    parser.add_argument(
        "--suite",
        type=str,
        choices=("scenario", "memory", "project_journey"),
        default="scenario",
        help="MC13: 'memory' runs the public dataset/agent-episode memory suite; "
        "P65-09: 'project_journey' runs the installed end-to-end acceptance "
        "workload (install/provision/scan/aggregate/handoff/rescan/memory) "
        "instead of scenario dispatch",
    )
    parser.add_argument(
        "--variant",
        type=str,
        choices=_MEMORY_VARIANTS,
        default="current",
        help="MC13.4: memory retrieval variant to compare against 'current' baseline",
    )
    parser.add_argument(
        "--dataset-manifest",
        type=Path,
        default=None,
        help="MC13.2: explicit external dataset manifest+records JSON (bypasses the bundled fixture)",
    )
    parser.add_argument(
        "--seeds",
        type=str,
        default="",
        help="MC13.4: comma-separated fixed seeds for paired bootstrap comparisons",
    )
    parser.add_argument(
        "--max-total-tokens",
        type=int,
        default=16000,
        help="MC13.2: per-case/per-episode token budget for the memory suite",
    )
    parser.add_argument(
        "--decision-mode",
        type=str,
        choices=("component", "live"),
        default="component",
        help="Phase 72 D13: 'component' runs the scripted harness (harness "
        "completion only); 'live' asks --decision-route for every decision",
    )
    parser.add_argument(
        "--decision-route",
        type=str,
        default=None,
        help="Phase 72 D13: live decision route ID (requires --decision-mode live "
        "and its --allow-live-route grant)",
    )
    parser.add_argument(
        "--task-manifest",
        type=Path,
        default=None,
        help="Phase 72 D13a: strict memory task manifest "
        "(tests/fixtures/phase75/task_manifest.json)",
    )
    return parser


def _variant_retrieval(
    variant: str,
    root: Path,
    tool: MemoryTool,
    permissions: ExecutionPermissions,
    *,
    query: str,
    subject: MemorySubject,
    owner_scope: OwnerScope | None,
    session_allowlist: list[str] | None,
    request_override: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """72-T08: one arm's retrieval for one case and its measurements. Compact arms ask
    `recall` for at most 8 items in 8192 bytes; `hybrid` adds `request_override` (the
    frozen engine identity) or a bare `retrieval="hybrid"`. `metadata` answers from the
    legacy `list` route: the grant's sources, the owner, freshness `fresh`, no query, the
    first eight rows by id."""
    owner_kwargs: dict[str, Any] = (
        {"owner_scope": owner_scope} if owner_scope is not None else {}
    )
    out: dict[str, Any] = {
        "ids": [],
        "excerpts": [],
        "retrieval": None,
        "embedding_fallback_code": None,
        "override_skipped": None,
        "page_tokens": 0,
        "retrieval_ms": 0.0,
        "embedded_texts": 0,
        "raw": None,
    }
    started = time.perf_counter()
    if variant == "metadata":
        sources = session_allowlist
        if sources is None:
            access = MemoryAccess.resolve(
                Path(root), operation="list", owner_scope=owner_scope
            )
            sources = list(access.sources) if access is not None else []
        listed: dict[str, Any] = dict(
            tool.run(
                root,
                operation="list",
                subject=subject,
                session_allowlist=sources,
                freshness_filter="fresh",
                owner_filter=(
                    f"{owner_scope.kind}:{owner_scope.id}" if owner_scope else None
                ),
                permissions=permissions,
                **owner_kwargs,
            )
        )
        raw = listed.get("raw")
        entries = sorted(
            (e for e in (raw if isinstance(raw, list) else []) if isinstance(e, dict)),
            key=lambda entry: str(entry.get("id")),
        )[:8]
        out.update(
            ids=[str(entry.get("id")) for entry in entries],
            excerpts=[_excerpt(entry.get("content") or {}) for entry in entries],
            retrieval="metadata",
            raw=raw,
        )
    else:
        request: dict[str, Any] = {
            "view": "compact",
            "limit": 8,
            "max_tokens": _VARIANT_MAX_TOKENS.get(variant, 2048),
            "max_bytes": 8192,
        }
        if variant == "hybrid":
            request.update(request_override or {"retrieval": "hybrid"})
        recalled: dict[str, Any] = dict(
            tool.run(
                root,
                operation="recall",
                subject=subject,
                query=query,
                session_allowlist=session_allowlist,
                request=request,
                permissions=permissions,
                **owner_kwargs,
            )
        )
        recalled_raw: dict[str, Any] = recalled.get("raw") or {}
        data: dict[str, Any] = recalled_raw.get("data") or {}
        items = [i for i in data.get("items") or [] if isinstance(i, dict)]
        excerpts = [str(item.get("excerpt", "")) for item in items]
        if variant == "linked" and items:
            first = items[0]
            related: dict[str, Any] = dict(
                tool.run(
                    root,
                    operation="related",
                    session_allowlist=session_allowlist,
                    request={"id": first.get("id"), "version": first.get("version", 1)},
                    **owner_kwargs,
                )
            )
            related_raw: dict[str, Any] = related.get("raw") or {}
            related_data: dict[str, Any] = related_raw.get("data") or {}
            excerpts.extend(
                str(item.get("excerpt", ""))
                for item in related_data.get("items") or []
                if isinstance(item, dict)
            )
        out.update(
            ids=[str(item.get("id")) for item in items],
            excerpts=excerpts,
            retrieval=data.get("retrieval", "lexical"),
            embedding_fallback_code=data.get("embedding_fallback_code"),
            page_tokens=int(data.get("tokens") or 0),
            embedded_texts=int(data.get("embedded_texts") or 0),
            raw=recalled_raw,
        )
    out["retrieval_ms"] = (time.perf_counter() - started) * 1000.0
    return out


def _variant_hypothesis(
    variant: str,
    root: Path,
    tool: MemoryTool,
    permissions: ExecutionPermissions,
    sanitized: dict[str, Any],
    *,
    query: str | None = None,
    subject: MemorySubject = "episodic",
    owner_scope: OwnerScope | None = None,
    session_allowlist: list[str] | None = None,
    request_override: Mapping[str, Any] | None = None,
) -> str:
    """Produces one dataset case's hypothesis under a named memory variant: the
    returned items' excerpts (a compact item carries `excerpt`, never `content`).
    Never touches `sanitized`'s stripped gold fields (already removed by
    `strip_longmemeval_gold`). `"none"` never calls the memory tool at all;
    `"hybrid"` requests `retrieval=hybrid` and honestly reports whatever
    `MemoryTool` itself returns (a labelled lexical fallback when no embedding
    engine answers, per MC12/72-T08 -- never a fabricated hybrid result).

    72-T08: a caller passes the case's own `query` and grant (`owner_scope`, or an
    explicit `session_allowlist`); without them the LongMemEval form derives the query
    from the question's last word and the allowlist from the haystack sessions."""
    if variant == "none":
        return ""
    if variant == "raw":
        return " ".join(
            str(turn.get("content", ""))
            for session in sanitized.get("haystack_sessions", [])
            for turn in session.get("turns", [])
        )
    if query is None:
        query_terms = [w.strip("?.,!") for w in sanitized.get("question", "").split()]
        query = query_terms[-1] if query_terms else ""
    if session_allowlist is None and owner_scope is None:
        session_allowlist = [
            s.get("session_id", "") for s in sanitized.get("haystack_sessions", [])
        ]
    retrieved = _variant_retrieval(
        variant,
        root,
        tool,
        permissions,
        query=query,
        subject=subject,
        owner_scope=owner_scope,
        session_allowlist=session_allowlist,
        request_override=request_override,
    )
    return " ".join(retrieved["excerpts"])


_BASELINE_VARIANT = "none"


def _case_completion_score(result: DatasetCaseResult) -> float:
    """Honest per-case score: `1.0` if the case actually finished and
    produced a scored hypothesis under its variant/budget, `0.0` if it hit a
    timeout or the fixed `max_total_tokens` budget first. This is the same
    `outcome` field `aggregate_dataset_results` already counts -- no
    gold-answer correctness evaluator exists in this benchmark (MC13.md), so
    this is the real signal available, never a fabricated score."""
    return 1.0 if result.outcome == "scored" else 0.0


def _run_variant_cases(
    records: list[dict[str, Any]],
    variant: str,
    *,
    max_total_tokens: int,
    workspace_root: Path,
) -> list[DatasetCaseResult]:
    """MC13.4: runs every dataset case once under one named retrieval
    variant at a fixed `max_total_tokens` budget -- for genuine cross-variant
    comparison. Each record uses `run_longmemeval_case`'s own fresh
    per-call namespace, so no case leaks state to another variant's run."""

    def _decide(
        root: Path,
        tool: MemoryTool,
        perms: ExecutionPermissions,
        sanitized: dict[str, Any],
        _variant: str = variant,
    ) -> str:
        return _variant_hypothesis(_variant, root, tool, perms, sanitized)

    return [
        run_longmemeval_case(
            record,
            decide_fn=_decide,
            max_total_tokens=max_total_tokens,
            workspace_root=workspace_root,
        )
        for record in records
    ]


_COMPONENT_BLOCKER = (
    "real agent decision-making (choosing the next tool call / producing "
    "a hypothesis or patch from a live model) was not exercised: no live "
    "provider credential or --allow-live-route grant was supplied in this "
    "environment. Dataset ingestion, gold-stripping, hash verification, "
    "namespace reset and every named episode's real MemoryTool/verify_attempt/"
    "handoff mechanics ran for real; only the live-model reasoning step is "
    "blocked, matching MC12's precedent for a missing external engine."
)
_EVALUATOR_VERSION = 1
_VERIFY_REQUEST_KEYS = frozenset({"attempt_id", "behavior_ids", "contract", "patch"})
_VERIFY_CONTRACT_KEYS = frozenset(
    {
        "base_commit",
        "base_tree_digest",
        "patch_content_digest",
        "required_commands",
        "config_digest",
        "review_class",
    }
)
_COMMAND_KEYS = frozenset({"command", "expected_exit_code"})
_EPISODE_RESPONSE_SCHEMA = {
    "action": {
        "kind": "action",
        "operation": "<one of permitted_actions except submit>",
        "kwargs": "<object with keys from operations[operation].kwargs>",
    },
    "submit": {"kind": "submit", "final": "<any JSON value>"},
}
_ANSWER_RESPONSE_SCHEMA = {"kind": "answer", "text": "<string>"}


def _check_decision_flags(args: argparse.Namespace) -> None:
    """B2 steps 2-4: decision flag combinations, before any filesystem effect."""
    if args.decision_route is not None and args.decision_mode == "component":
        raise FixtureError(
            "decision_route_requires_live_mode: --decision-route needs "
            "--decision-mode live"
        )
    if args.decision_mode == "live" and args.decision_route is None:
        raise FixtureError(
            "live_requires_decision_route: --decision-mode live needs --decision-route"
        )
    if args.decision_mode == "live" and args.task_manifest is None:
        raise FixtureError(
            "live_requires_task_manifest: --decision-mode live needs --task-manifest"
        )


def _sha256_json(value: Any) -> str:
    return hashlib.sha256(canonical_json(value)).hexdigest()


def _cases_sha256(cases: list[dict[str, Any]]) -> str:
    return _sha256_json(sorted(cases, key=lambda case: case["id"]))


def _parse_seeds(raw: str) -> list[int]:
    return [int(s) for s in raw.split(",") if s.strip()] or [0]


def _check_output_guard(
    output: Path, cases_sha256: str, embedding: dict[str, Any] | None
) -> None:
    """B9: an existing report under --output must come from the same frozen
    manifest (cases digest and embedding identity); nothing is written."""
    report_path = Path(output) / "memory-suite-report.json"
    if not os.path.lexists(report_path):
        return
    try:
        existing = json.loads(report_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        existing = None
    task_manifest = (
        existing.get("task_manifest") if isinstance(existing, dict) else None
    )
    if (
        not isinstance(task_manifest, dict)
        or task_manifest.get("cases_sha256") != cases_sha256
        or task_manifest.get("phase72_embedding") != embedding
    ):
        raise FixtureError(
            f"output_manifest_mismatch: {report_path} was written for a different "
            "task manifest"
        )


def _check_editable_path(root: Path, rel: str, case_id: str) -> None:
    """B10: an editable path is a contained regular file whose last component
    exists with exactly this spelling."""
    try:
        candidate = PhysicalRoot(root).open_contained(rel)
        mode = os.lstat(candidate).st_mode
        listing = os.listdir(candidate.parent)
    except (ContainmentError, OSError, ValueError):
        raise FixtureError(
            f"unsafe_path: case {case_id} editable path {rel!r}"
        ) from None
    if not stat.S_ISREG(mode) or candidate.name not in listing:
        raise FixtureError(f"unsafe_path: case {case_id} editable path {rel!r}")


@dataclass
class _Phase72Data:
    """72-T08: the frozen query records by id, the corpus records and the hybrid arm's
    request override (`None` for a manifest without `phase72_embedding`)."""

    queries: dict[str, dict[str, Any]]
    corpus: list[dict[str, Any]]
    override: dict[str, str] | None


def _is_phase72(case: dict[str, Any]) -> bool:
    return (
        case["kind"] == "dataset_answer"
        and case["inputs"].get("section") == _P72_QUERIES_SECTION
    )


def _load_phase72(manifest: dict[str, Any]) -> _Phase72Data:
    _queries_manifest, queries = load_dataset_section(_P72_QUERIES_SECTION)
    _corpus_manifest, corpus = load_dataset_section(_P72_CORPUS_SECTION)
    embedding = manifest.get("phase72_embedding")
    override = (
        {
            "retrieval": "hybrid",
            "embedding_endpoint": embedding["endpoint"],
            "embedding_model": embedding["model"],
            "embedding_model_digest": embedding["model_digest"],
        }
        if isinstance(embedding, dict)
        else None
    )
    return _Phase72Data(
        queries={str(q["question_id"]): q for q in queries},
        corpus=list(corpus),
        override=override,
    )


def _verify_fixtures(
    cases: list[dict[str, Any]],
    verify_root: Path,
    records_by_id: dict[str, dict[str, Any]],
    phase72: _Phase72Data | None = None,
) -> None:
    """B10: builds every case's fixture once under `<workspace>/verify/<index>`
    and checks its frozen revision, task text and editable paths before any
    route preflight or provider call."""
    # The Phase 72 fixtures (the T08 subject, seeded in-process) are built first; every
    # case is still checked before any route preflight or provider call.
    ordered = sorted(enumerate(cases), key=lambda item: not _is_phase72(item[1]))
    for index, case in ordered:
        root = verify_root / str(index)
        root.mkdir(parents=True)
        task: str | None = None
        revision: str | None
        if case["kind"] == "episode":
            task, _scripted = EPISODE_BUILDERS[case["inputs"]["builder"]](root)
            revision = fixture_revision(root)
        elif phase72 is not None and _is_phase72(case):
            seen72: list[str] = []

            def capture72(
                case_root: Path,
                _tool: MemoryTool,
                _perms: ExecutionPermissions,
                _record: dict[str, Any],
                _seen: list[str] = seen72,
            ) -> dict[str, Any]:
                _seen.append(fixture_revision(case_root))
                return {}

            memory_datasets.run_phase72_case(
                phase72.queries[case["inputs"]["record_id"]],
                phase72.corpus,
                decide_fn=capture72,
                max_total_tokens=None,
                workspace_root=root,
            )
            revision = seen72[0] if seen72 else None
        else:
            seen: list[str] = []

            def capture(
                case_root: Path,
                _tool: MemoryTool,
                _perms: ExecutionPermissions,
                _sanitized: dict[str, Any],
                _seen: list[str] = seen,
            ) -> str:
                _seen.append(fixture_revision(case_root))
                return ""

            run_longmemeval_case(
                records_by_id[case["inputs"]["record_id"]],
                decide_fn=capture,
                max_total_tokens=None,
                workspace_root=root,
            )
            revision = seen[0] if seen else None
        if revision != case["fixture_revision"]:
            raise FixtureError(
                f"fixture_revision_mismatch: case {case['id']} fixture is {revision}"
            )
        if task is not None and task != case["inputs"]["task"]:
            raise FixtureError(f"task_mismatch: case {case['id']} builder task changed")
        for rel in case["editable_paths"]:
            _check_editable_path(root, rel, case["id"])


def _expand_commands(commands: Any) -> list[dict[str, Any]] | None:
    """D13a: `{python}` expansion of a required-commands list; `None` when an
    entry is not exactly `{command, expected_exit_code}`."""
    if not isinstance(commands, list):
        return None
    expanded: list[dict[str, Any]] = []
    for entry in commands:
        if (
            not isinstance(entry, dict)
            or set(entry) != _COMMAND_KEYS
            or not isinstance(entry["command"], list)
            or not all(isinstance(part, str) for part in entry["command"])
            or type(entry["expected_exit_code"]) is not int
        ):
            return None
        expanded.append(
            {
                "command": list(expand_python_token(entry["command"])),
                "expected_exit_code": entry["expected_exit_code"],
            }
        )
    return expanded


def _validate_episode_action(
    case: dict[str, Any], decision: dict[str, Any]
) -> tuple[str | None, EpisodeAction | None]:
    """G8-A: a model action is checked against the fixture-owned case before
    any tool call; a refused action never reaches `MemoryTool.run`."""
    operation = decision["operation"]
    kwargs = decision["kwargs"]
    offered = set(case["permitted_actions"]) - {"submit"}
    if not isinstance(operation, str) or operation not in offered:
        return "action_not_permitted", None
    if not isinstance(kwargs, dict) or set(kwargs) - set(
        EPISODE_OPERATION_KWARGS[operation]
    ):
        return "unknown_decision_field", None
    kwargs = copy.deepcopy(kwargs)
    if operation == "verify_attempt":
        request = kwargs.get("request")
        if not isinstance(request, dict) or set(request) - _VERIFY_REQUEST_KEYS:
            return "unknown_decision_field", None
        contract = request.get("contract")
        if not isinstance(contract, dict) or set(contract) - _VERIFY_CONTRACT_KEYS:
            return "unknown_decision_field", None
        patch = request.get("patch")
        paths = patch_target_paths(patch) if isinstance(patch, str) else None
        if paths is None or any(path not in case["editable_paths"] for path in paths):
            return "edit_outside_editable_paths", None
        expanded = _expand_commands(contract.get("required_commands"))
        if expanded is None or expanded != _expand_commands(
            case["acceptance"]["required_commands"]
        ):
            return "contract_not_fixture_owned", None
        contract["required_commands"] = expanded
    elif operation == "handoff" and case["acceptance"]["handoff"] is not None:
        request = kwargs.get("request")
        if isinstance(request, dict):
            source = case["acceptance"]["handoff"]["source"]
            if request.setdefault("receiver_namespace", source) != source:
                return "action_not_permitted", None
    return None, EpisodeAction(operation=operation, kwargs=kwargs)


@dataclass
class _LiveContext:
    route_id: str
    decision_route: Any
    workspace_root: Path
    route_overhead_tokens: int
    provider_env: Mapping[str, str] | None = None


@dataclass
class _CaseState:
    reason: str | None = None
    steps: int = 0
    submitted: bool = False
    answer: str | None = None
    local_returned_tokens: int = 0
    invocations: list[dict[str, Any]] = field(default_factory=list)
    provider_ids: set[str] = field(default_factory=set)


def _invoke_decision(
    live: _LiveContext,
    state: _CaseState,
    request: dict[str, Any],
    *,
    kind: str,
    root: Path,
    budget: DecisionBudget,
    timeout_s: float,
    step: int,
) -> DecisionResult:
    """One live decision call (B12), recorded as an invocation (G8-O)."""
    result = run_memory_decision(
        request,
        decision_route=live.decision_route,
        kind=kind,
        root=root,
        workspace_root=live.workspace_root,
        budget=budget,
        timeout_s=timeout_s,
        env=live.provider_env,
    )
    state.invocations.append(
        invocation_record(result, step=step, route_id=live.route_id)
    )
    state.provider_ids.update(result.provider_ids)
    return result


def _remaining_tokens(budget: DecisionBudget) -> int:
    return (
        budget.max_total_tokens
        - budget.model_tokens
        - budget.route_overhead_tokens
        - budget.output_reserve_tokens
    )


def _history_result(result: Any) -> Any:
    """72-T08: a decision request's history entry. The `metadata` arm's legacy `list`
    answers with whole rows (a LongMemEval turn carries its own `role` key); the request
    carries each row's id and excerpt, the same text `variant_context` holds."""
    raw = result.get("raw") if isinstance(result, dict) else None
    if not isinstance(raw, list):
        return result
    return {
        **result,
        "raw": [
            {"id": entry.get("id"), "excerpt": _excerpt(entry.get("content") or {})}
            for entry in raw
            if isinstance(entry, dict)
        ],
    }


def _run_dataset_case(
    args: argparse.Namespace,
    case: dict[str, Any],
    record: dict[str, Any],
    run_dir: Path,
    state: _CaseState,
    live: _LiveContext | None,
    budget: DecisionBudget | None,
    effective: int,
) -> bool:
    """A dataset_answer case: ingestion by `run_longmemeval_case`, then one
    decision (live) or the variant hypothesis (component). Returns whether
    the harness completed; quality is the separate evaluator verdict."""
    _sanitized, gold = strip_longmemeval_gold(record)
    permissions = ExecutionPermissions(**{grant: True for grant in case["grants"]})
    timeout_s = float(case["budget"]["timeout_s"])

    def decide(
        root: Path,
        tool: MemoryTool,
        _perms: ExecutionPermissions,
        sanitized: dict[str, Any],
    ) -> str:
        state.steps += 1
        if fixture_revision(root) != case["fixture_revision"]:
            state.reason = "fixture_revision_mismatch"
            return ""
        counting = cast(CountingMemoryTool, tool)
        before, before_tokens = len(counting.results), counting.tokens
        context = _variant_hypothesis(args.variant, root, tool, permissions, sanitized)
        state.local_returned_tokens += counting.tokens - before_tokens
        if live is None or budget is None:
            state.answer = context
            return context
        request = {
            "schema_version": 1,
            "decision_kind": "answer",
            "case_id": case["id"],
            "task": sanitized["question"],
            "question_date": sanitized.get("question_date"),
            "step": 0,
            "variant": args.variant,
            "history": [
                {"operation": operation, "result": _history_result(result)}
                for operation, result in counting.results[before:]
            ],
            "variant_context": context,
            "remaining_budget_tokens": _remaining_tokens(budget),
            "permitted_actions": ["answer"],
            "response_schema": dict(_ANSWER_RESPONSE_SCHEMA),
        }
        result = _invoke_decision(
            live,
            state,
            request,
            kind="dataset_answer",
            root=root,
            budget=budget,
            timeout_s=timeout_s,
            step=0,
        )
        if result.reason is not None or result.decision is None:
            state.reason = result.reason or "malformed_decision_json"
            state.answer = result.text
            return ""
        state.answer = str(result.decision["text"])
        return state.answer

    outcome = run_longmemeval_case(
        record,
        decide_fn=decide,
        max_total_tokens=None if live is not None else effective,
        timeout_seconds=timeout_s,
        workspace_root=run_dir,
    )
    if state.reason is None and outcome.outcome != "scored":
        state.reason = outcome.outcome
    harness_completed = state.reason is None and state.steps > 0
    if state.reason is None and not normalized_contains(
        state.answer or "", str(gold.get("answer", ""))
    ):
        state.reason = "evaluator_failed"
    return harness_completed


def _run_phase72_case(
    args: argparse.Namespace,
    case: dict[str, Any],
    phase72: _Phase72Data,
    run_dir: Path,
    state: _CaseState,
    live: _LiveContext | None,
    budget: DecisionBudget | None,
    effective: int,
) -> tuple[bool, DatasetCaseResult]:
    """72-T08: a `p72-` dataset_answer case. The arm's retrieval runs in the seeded
    fresh root with the case's own query and the reader's grant; the decision (live) or
    the recalled excerpts (component) is scored against the query record's gold answer
    here, after the decision. Gold keys, `split` and the corpus `role` never enter the
    decision request."""
    query_record = phase72.queries[case["inputs"]["record_id"]]
    gold_answer = str(query_record.get("answer", ""))
    timeout_s = float(case["budget"]["timeout_s"])

    def decide(
        root: Path,
        tool: MemoryTool,
        perms: ExecutionPermissions,
        record: dict[str, Any],
    ) -> dict[str, Any]:
        state.steps += 1
        measured: dict[str, Any] = {
            "returned_ids": [],
            "retrieval": None,
            "embedding_fallback_code": None,
            "override_skipped": None,
            "page_tokens": 0,
            "retrieval_ms": 0.0,
            "decision_ms": 0.0,
            "embedded_texts": 0,
            "passed": False,
            "model_tokens": 0,
            "local_returned_tokens": 0,
        }
        if fixture_revision(root) != case["fixture_revision"]:
            state.reason = "fixture_revision_mismatch"
            return measured
        retrieved = _variant_retrieval(
            args.variant,
            root,
            tool,
            perms,
            query=case["inputs"]["query"],
            subject="domain_knowledge",
            owner_scope=_P72_READER,
            session_allowlist=None,
            request_override=phase72.override if args.variant == "hybrid" else None,
        )
        state.local_returned_tokens += int(retrieved["page_tokens"])
        measured.update(
            returned_ids=retrieved["ids"],
            retrieval=retrieved["retrieval"],
            embedding_fallback_code=retrieved["embedding_fallback_code"],
            override_skipped=retrieved["override_skipped"],
            page_tokens=retrieved["page_tokens"],
            retrieval_ms=retrieved["retrieval_ms"],
            embedded_texts=retrieved["embedded_texts"],
            local_returned_tokens=int(retrieved["page_tokens"]),
        )
        context = " ".join(retrieved["excerpts"])
        text = context
        if live is not None and budget is not None:
            request = {
                "schema_version": 1,
                "decision_kind": "answer",
                "case_id": case["id"],
                "task": record["question"],
                "step": 0,
                "variant": args.variant,
                "history": [],
                "variant_context": context,
                "remaining_budget_tokens": _remaining_tokens(budget),
                "permitted_actions": ["answer"],
                "response_schema": dict(_ANSWER_RESPONSE_SCHEMA),
            }
            started = time.perf_counter()
            result = _invoke_decision(
                live,
                state,
                request,
                kind="dataset_answer",
                root=root,
                budget=budget,
                timeout_s=timeout_s,
                step=0,
            )
            measured["decision_ms"] = (time.perf_counter() - started) * 1000.0
            measured["model_tokens"] = budget.model_tokens
            if result.reason is not None or result.decision is None:
                state.reason = result.reason or "malformed_decision_json"
                text = ""
            else:
                text = str(result.decision["text"])
        state.answer = text
        measured["passed"] = state.reason is None and normalized_contains(
            text, gold_answer
        )
        return measured

    case_started = time.perf_counter()
    outcome = memory_datasets.run_phase72_case(
        query_record,
        phase72.corpus,
        decide_fn=decide,
        max_total_tokens=None if live is not None else effective,
        timeout_seconds=timeout_s,
        workspace_root=run_dir,
    )
    if outcome.phase72 is not None:
        # The case's own wall-clock (seeding, retrieval and decision): the PR4 cost per
        # correct answer is measured on it, not on the retrieval call alone.
        outcome.phase72["case_ms"] = (time.perf_counter() - case_started) * 1000.0
    if state.reason is None and outcome.outcome != "scored":
        state.reason = outcome.outcome
    harness_completed = state.reason is None and state.steps > 0
    if state.reason is None and not (outcome.phase72 or {}).get("passed"):
        state.reason = "evaluator_failed"
    return harness_completed, outcome


def _run_episode_case(
    case: dict[str, Any],
    run_dir: Path,
    state: _CaseState,
    live: _LiveContext | None,
    budget: DecisionBudget | None,
    effective: int,
) -> tuple[bool, list[dict[str, Any]] | None]:
    """An episode case: rebuild the fixture, re-check its revision, then run
    the scripted (component) or live decider through `run_memory_episode`."""
    root = run_dir / "fixture"
    root.mkdir()
    _task, scripted = EPISODE_BUILDERS[case["inputs"]["builder"]](root)
    if fixture_revision(root) != case["fixture_revision"]:
        state.reason = "fixture_revision_mismatch"
        return False, None
    permissions = ExecutionPermissions(**{grant: True for grant in case["grants"]})
    timeout_s = float(case["budget"]["timeout_s"])
    acceptance = case["acceptance"]

    def decide_component(observation: EpisodeObservation) -> EpisodeAction:
        state.steps += 1
        action = scripted(observation)
        if action.operation == "submit":
            state.submitted = True
        return action

    def decide_live(observation: EpisodeObservation) -> EpisodeAction:
        if live is None or budget is None:
            raise FixtureError("decision_route_unavailable: live decider without route")
        state.steps += 1
        request = {
            "schema_version": 1,
            "decision_kind": "episode",
            "case_id": case["id"],
            "task": case["inputs"]["task"],
            "step": observation.step_index,
            "history": list(observation.history),
            "remaining_budget_tokens": _remaining_tokens(budget),
            "permitted_actions": case["permitted_actions"],
            "editable_paths": case["editable_paths"],
            "acceptance": {
                "behavior_ids": acceptance["behavior_ids"],
                "required_commands": acceptance["required_commands"],
                "handoff": acceptance["handoff"],
            },
            "operations": {
                op: OPERATION_SCHEMAS[op]
                for op in case["permitted_actions"]
                if op != "submit"
            },
            "response_schema": copy.deepcopy(_EPISODE_RESPONSE_SCHEMA),
        }
        result = _invoke_decision(
            live,
            state,
            request,
            kind="episode",
            root=root,
            budget=budget,
            timeout_s=timeout_s,
            step=observation.step_index,
        )
        decision = result.decision
        if result.reason is not None or decision is None:
            state.reason = result.reason or "malformed_decision_json"
            return EpisodeAction(operation="submit", final=None)
        if decision["kind"] == "submit":
            state.submitted = True
            return EpisodeAction(operation="submit", final=decision.get("final"))
        reason, action = _validate_episode_action(case, decision)
        if reason is not None or action is None:
            state.reason = reason or "malformed_decision_json"
            return EpisodeAction(operation="submit", final=None)
        return action

    result = run_memory_episode(
        case["id"],
        case["inputs"]["task"],
        decide_live if live is not None else decide_component,
        root=root,
        permissions=permissions,
        max_steps=case["budget"]["max_steps"],
        max_total_tokens=None if live is not None else effective,
        timeout_seconds=timeout_s,
    )
    state.local_returned_tokens = result.total_tokens
    if state.reason is None:
        if result.timed_out:
            state.reason = "timeout"
        elif result.budget_exhausted:
            state.reason = "budget_exhausted"
        elif not state.submitted:
            state.reason = "max_steps_exhausted"
    harness_completed = state.reason is None
    bound_refs: list[dict[str, Any]] | None = None
    if state.reason is None:
        if acceptance["evaluator"] == "verifier_receipt_completed":
            ok = verifier_receipt_completed(result.events, acceptance)
        else:
            ok, bound_refs = receiver_readback_acknowledged(
                result.events, acceptance, root
            )
        if not ok:
            state.reason = "evaluator_failed"
    return harness_completed, bound_refs


def _run_manifest_case(
    args: argparse.Namespace,
    case: dict[str, Any],
    seed: int,
    run_dir: Path,
    records_by_id: dict[str, dict[str, Any]],
    live: _LiveContext | None,
    provider_ids: set[str],
    phase72: _Phase72Data | None = None,
    phase72_results: dict[int, list[DatasetCaseResult]] | None = None,
) -> dict[str, Any]:
    """One case x seed (B17, B20): its own budget, decisions and evaluator."""
    effective = min(args.max_total_tokens, case["budget"]["max_total_tokens"])
    reserve = case["budget"]["output_reserve_tokens"]
    budget = (
        DecisionBudget(effective, reserve, live.route_overhead_tokens)
        if live is not None
        else None
    )
    state = _CaseState()
    run_dir.mkdir(parents=True)
    bound_refs: list[dict[str, Any]] | None = None
    phase72_result: DatasetCaseResult | None = None
    if phase72 is not None and _is_phase72(case):
        harness_completed, phase72_result = _run_phase72_case(
            args, case, phase72, run_dir, state, live, budget, effective
        )
        if phase72_results is not None:
            phase72_results.setdefault(seed, []).append(phase72_result)
    elif case["kind"] == "dataset_answer":
        harness_completed = _run_dataset_case(
            args,
            case,
            records_by_id[case["inputs"]["record_id"]],
            run_dir,
            state,
            live,
            budget,
            effective,
        )
    else:
        harness_completed, bound_refs = _run_episode_case(
            case, run_dir, state, live, budget, effective
        )
    provider_ids.update(state.provider_ids)
    record = {
        "case_id": case["id"],
        "seed": seed,
        "kind": case["kind"],
        "family": case["family"],
        "variant": case["variant"],
        "fixture_revision": case["fixture_revision"],
        "passed": state.reason is None,
        "reason": state.reason,
        "harness_completed": harness_completed,
        "evaluator": case["acceptance"]["evaluator"],
        "evaluator_version": _EVALUATOR_VERSION,
        "budget": {
            "max_total_tokens": effective,
            "output_reserve_tokens": reserve,
            "model_tokens": None if budget is None else budget.model_tokens,
            "local_returned_tokens": state.local_returned_tokens,
        },
        "steps": state.steps,
        "invocations": state.invocations,
        "answer": state.answer if case["kind"] == "dataset_answer" else None,
        "bound_refs": bound_refs,
    }
    if phase72_result is not None:
        record["phase72"] = phase72_result.phase72
    return record


def _aggregate(records: list[dict[str, Any]]) -> dict[str, Any]:
    failed: dict[str, int] = {}
    for record in records:
        if not record["passed"]:
            failed[record["reason"]] = failed.get(record["reason"], 0) + 1
    return {
        "total": len(records),
        "passed": sum(1 for record in records if record["passed"]),
        "failed_by_reason": failed,
    }


def _preflight_provider_ids(preflight: Any) -> list[str]:
    if isinstance(preflight, DecisionResult):
        return list(preflight.provider_ids)
    if isinstance(preflight, dict):
        ids = preflight.get("provider_ids") or []
        return [value for value in ids if isinstance(value, str)]
    return []


def _execute_manifest(
    args: argparse.Namespace,
    manifest: dict[str, Any],
    cases_sha256: str,
    decision_route: Any,
    workspace_root: Path,
    provider_env: Mapping[str, str] | None = None,
) -> int:
    cases: list[dict[str, Any]] = manifest["cases"]
    seeds = _parse_seeds(args.seeds)
    is_live = decision_route is not None
    records_by_id: dict[str, dict[str, Any]] = {}
    if any(case["kind"] == "dataset_answer" for case in cases):
        _section, records = load_dataset_section("longmemeval")
        records_by_id = {str(r.get("question_id")): r for r in records}
    phase72 = _load_phase72(manifest) if any(_is_phase72(c) for c in cases) else None
    _verify_fixtures(cases, workspace_root / "verify", records_by_id, phase72)

    blockers: list[str] = []
    route_report: dict[str, Any] | None = None
    redaction_patterns: list[str] = []
    provider_ids: set[str] = set()
    live: _LiveContext | None = None
    available = True
    if is_live:
        redaction_patterns = list(decision_route.redaction_patterns)
        preflight = preflight_decision_route(
            decision_route,
            workspace_root=workspace_root,
            case_budgets=[
                (
                    min(args.max_total_tokens, case["budget"]["max_total_tokens"]),
                    case["budget"]["output_reserve_tokens"],
                )
                for case in cases
            ],
            env=provider_env,
        )
        provider_ids.update(_preflight_provider_ids(preflight.get("preflight")))
        route_report = {
            "route_id": args.decision_route,
            "format": decision_route.format,
            "executable": str(decision_route.executable),
            "version": preflight.get("version"),
            "status": preflight.get("status"),
            "reason": preflight.get("reason"),
            "route_overhead_tokens": preflight.get("route_overhead_tokens"),
            "instruction_files": preflight.get("instruction_files"),
            "preflight": preflight.get("preflight"),
        }
        if preflight.get("status") == "unavailable":
            available = False
            blockers.append(
                f"decision route {args.decision_route} unavailable: "
                f"{preflight.get('reason')}"
            )
        else:
            live = _LiveContext(
                route_id=args.decision_route,
                decision_route=decision_route,
                workspace_root=workspace_root,
                route_overhead_tokens=int(preflight["route_overhead_tokens"]),
                provider_env=provider_env,
            )
    else:
        blockers.append(_COMPONENT_BLOCKER)

    case_results: list[dict[str, Any]] = []
    phase72_results: dict[int, list[DatasetCaseResult]] = {}
    if available:
        for index, case in enumerate(cases):
            for seed in seeds:
                case_results.append(
                    _run_manifest_case(
                        args,
                        case,
                        seed,
                        workspace_root / "runs" / f"{index}-{seed}",
                        records_by_id,
                        live,
                        provider_ids,
                        phase72,
                        phase72_results,
                    )
                )

    payload = {
        "decision_mode": args.decision_mode,
        "variant": args.variant,
        "seeds": seeds,
        "seed_semantics": "repetition_labels" if is_live else "bootstrap_seed",
        "max_total_tokens": args.max_total_tokens,
        "python": {"executable": sys.executable, "version": sys.version},
        "task_manifest": {
            "path": str(args.task_manifest),
            "schema_version": manifest["schema_version"],
            "cases_sha256": cases_sha256,
            "baseline_cases_sha256": BASELINE_CASES_SHA256,
            "phase72_cases_sha256": manifest.get("phase72_cases_sha256"),
            "phase72_embedding": manifest.get("phase72_embedding"),
            "case_count": len(cases),
            "declared": manifest["declared"],
            "phase75_family_coverage": manifest["phase75_family_coverage"],
        },
        "decision_route": route_report,
        "case_results": case_results,
        "aggregate": _aggregate(case_results),
        "usage_accounting": {
            "budget_basis": "provider_model_tokens" if is_live else "local_cl100k"
        },
        "blockers": blockers,
    }
    # 72-T08: the verdict rows (the provider of a row is its route directory,
    # `<eval root>/<arm>/<route>`) and the R20 counts of the arm.
    output = Path(args.output).resolve()
    if phase72 is not None:
        verdict_rows = (
            _phase72_rows(
                phase72_results, manifest, arm=args.variant, provider=output.name
            )
            if available
            else [_unavailable_row(output.name, args.variant)]
        )
        payload["verdict_rows"] = verdict_rows
        payload["phase72_summary"] = _phase72_summary(verdict_rows)
    report_path = write_memory_suite_report(
        args.output,
        payload,
        redaction_patterns=redaction_patterns,
        provider_id_values=sorted(provider_ids),
        home=None if provider_env is None else provider_env.get("HOME"),
    )
    if phase72 is not None and output.parent.name in HYBRID_ARMS:
        write_hybrid_verdict(output.parent.parent)
    sys.stdout.write(f"\nMemory suite report written to: {report_path}\n")
    for blocker in blockers:
        sys.stdout.write(f"BLOCKED (named): {blocker}\n")
    return 0 if available else 1


def _error_chain(err: BaseException | None) -> str:
    parts: list[str] = []
    seen: set[int] = set()
    current = err
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        text = str(current)
        if text and text not in parts:
            parts.append(text)
        current = current.__cause__ or (
            None if current.__suppress_context__ else current.__context__
        )
    return " <- ".join(parts)


def _raised_by_store_close(err: BaseException) -> bool:
    """True when `err` was raised inside `TypedArtifactStore.close` (the
    method currently bound on the store's class), wherever the caller was."""
    tb = err.__traceback__
    while tb is not None:
        frame = tb.tb_frame
        owner = frame.f_locals.get("self")
        if isinstance(owner, TypedArtifactStore) and frame.f_code is getattr(
            type(owner).close, "__code__", None
        ):
            return True
        tb = tb.tb_next
    return False


def _run_manifest_suite(args: argparse.Namespace) -> int:
    """B2 steps 5-6, B6-B11, B17, B20: a strict-manifest memory run in
    component or live decision mode. Every rejection happens before any
    provider call and before --output is touched; the workspace is always
    removed, and a cleanup failure never masks the primary error. 72-T08 (D14):
    every in-process Rush call sees `HOME`, `XDG_DATA_HOME` and `LOCALAPPDATA` inside a
    temporary root, restored on every exit."""
    original_env = dict(os.environ)
    isolated = tempfile.TemporaryDirectory(prefix="memory-suite-home-")
    primary: Exception | None = None
    code = 1
    try:
        for key in _ISOLATED_ENV_KEYS:
            os.environ[key] = str(Path(isolated.name) / key.lower())
        code = _run_isolated_manifest_suite(args, original_env)
    except Exception as exc:  # noqa: BLE001 - re-raised after the cleanup below
        primary = exc
    finally:
        os.environ.clear()
        os.environ.update(original_env)
    try:
        isolated.cleanup()
    except OSError as cleanup_exc:
        detail = _error_chain(cleanup_exc)
        if primary is not None:
            detail += f"; primary error: {_error_chain(primary)}"
        raise FixtureError(f"cleanup_failed: {detail}") from None
    if primary is not None:
        raise primary
    return code


def _run_isolated_manifest_suite(
    args: argparse.Namespace, provider_env: Mapping[str, str]
) -> int:
    """`_run_manifest_suite`'s body, run inside the isolated environment; every
    provider subprocess takes `provider_env`, the caller's original one."""
    manifest = load_task_manifest(args.task_manifest)
    cases: list[dict[str, Any]] = manifest["cases"]
    if (
        args.variant == "hybrid"
        and any(case["id"].startswith("p72-") for case in cases)
        and "phase72_embedding" not in manifest
    ):
        raise FixtureError(
            "hybrid_requires_phase72_embedding: --variant hybrid with p72- cases "
            "needs phase72_embedding"
        )
    cases_sha256 = _cases_sha256(cases)
    _check_output_guard(args.output, cases_sha256, manifest.get("phase72_embedding"))
    decision_route = None
    if args.decision_mode == "live":
        decision_route = resolve_decision_route(
            args.decision_route,
            allow_live_route=args.allow_live_route,
            provider_executable=args.provider_executable,
        )
    workspace = tempfile.TemporaryDirectory(prefix="memory-suite-")
    primary: Exception | None = None
    code = 1
    try:
        code = _execute_manifest(
            args,
            manifest,
            cases_sha256,
            decision_route,
            Path(workspace.name).resolve(),
            provider_env,
        )
    except Exception as exc:  # noqa: BLE001 - re-raised after workspace cleanup
        primary = exc
        if _raised_by_store_close(exc):
            # a store/read-only view close failed inside a tool call; the
            # chain keeps any primary error the close interrupted
            primary = FixtureError(f"cleanup_failed: store close: {_error_chain(exc)}")
    try:
        workspace.cleanup()
    except OSError as cleanup_exc:
        detail = _error_chain(cleanup_exc)
        if primary is not None:
            detail += f"; primary error: {_error_chain(primary)}"
        raise FixtureError(f"cleanup_failed: {detail}") from None
    if primary is not None:
        raise primary
    return code


def _manifest_document(path: Path | None) -> dict[str, Any] | None:
    if path is None:
        return None
    document = json.loads(Path(path).read_text(encoding="utf-8"))
    return document if isinstance(document, dict) else None


def _recorded_embedding_differs(output: Path, embedding: Any) -> bool:
    """72-T08: an `--output` already holding a report made under another frozen engine
    identity is never overwritten (the paired arms must share one identity)."""
    report = Path(output) / "memory-suite-report.json"
    if not report.is_file():
        return False
    recorded = json.loads(report.read_text(encoding="utf-8"))
    return (
        not isinstance(recorded, dict) or recorded.get("phase72_embedding") != embedding
    )


def _phase72_rows(
    results_by_seed: dict[int, list[DatasetCaseResult]],
    manifest: dict[str, Any] | None,
    *,
    arm: str,
    provider: str,
) -> list[dict[str, Any]]:
    """72-T08: one verdict row (`reporting.aggregate_hybrid_verdict`'s contract) per
    `p72-` case and seed, scored against the frozen query and corpus sections. The gold
    `relevant_ids`, `split` and corpus `role` are read here, after the decision."""
    measured = [
        (seed, result)
        for seed, results in results_by_seed.items()
        for result in results
        if result.phase72 is not None
    ]
    if not measured:
        return []
    _queries_manifest, queries = load_dataset_section("phase72_hybrid_queries")
    _corpus_manifest, corpus = load_dataset_section("phase72_hybrid_corpus")
    query_by_id = {str(q["question_id"]): q for q in queries}
    role_by_id = {str(c["id"]): c.get("role") for c in corpus}
    case_by_id = {
        str(case.get("id")): case
        for case in (manifest or {}).get("cases") or []
        if isinstance(case, dict)
    }
    rows: list[dict[str, Any]] = []
    for seed, result in measured:
        phase72 = result.phase72 or {}
        query = query_by_id[result.case_id]
        case = case_by_id.get(result.case_id, {})
        relevant = [str(i) for i in query.get("relevant_ids") or []]
        returned = [str(i) for i in phase72.get("returned_ids") or []]
        rows.append(
            {
                "provider": provider,
                "arm": arm,
                "case_id": result.case_id,
                "seed": seed,
                "fixture_revision": case.get("fixture_revision"),
                "grants": case.get("grants"),
                "budgets": case.get("budget"),
                "split": query.get("split"),
                "retrieval_required": bool(case.get("retrieval_required", True)),
                "recall_at_8": recall_at_k(returned, relevant),
                "chance_recall": chance_recall(len(returned[:8]), _P72_ELIGIBLE),
                "false_inclusion": sum(1 for i in returned[:8] if i not in relevant),
                "security_inclusion": sum(
                    1 for i in returned if role_by_id.get(i) in _P72_SECURITY_ROLES
                ),
                "passed": bool(phase72.get("passed")),
                "case_tokens": result.total_tokens,
                "case_ms": float(
                    phase72.get("case_ms")
                    or float(phase72.get("retrieval_ms") or 0.0)
                    + float(phase72.get("decision_ms") or 0.0)
                ),
                "page_tokens": phase72.get("page_tokens"),
                "retrieval_ms": phase72.get("retrieval_ms"),
                "embedded_texts": phase72.get("embedded_texts"),
                "retrieval": phase72.get("retrieval"),
                "embedding_fallback_code": phase72.get("embedding_fallback_code"),
                "override_skipped": phase72.get("override_skipped"),
                "route_available": True,
            }
        )
    return rows


def _unavailable_row(provider: str, arm: str) -> dict[str, Any]:
    """The one verdict row of an arm whose decision route was unavailable: the verdict
    for that provider is `unavailable`, never absent."""
    return {
        "provider": provider,
        "arm": arm,
        "case_id": "route",
        "seed": 0,
        "fixture_revision": None,
        "grants": None,
        "budgets": None,
        "split": None,
        "route_available": False,
    }


def _phase72_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Per-arm R20 counts and the retrieval latency p95 over the verdict rows."""
    latencies = sorted(float(r.get("retrieval_ms") or 0.0) for r in rows)
    p95 = latencies[max(0, -(-len(latencies) * 95 // 100) - 1)] if latencies else 0.0
    return {
        "retrieval_ms_p95": p95,
        "hybrid_pages": sum(1 for r in rows if r.get("retrieval") == "hybrid"),
        "fallback_pages": sum(
            1
            for r in rows
            if r.get("embedding_fallback_code")
            or r.get("override_skipped") == "no_request"
        ),
        "embedded_texts": sum(int(r.get("embedded_texts") or 0) for r in rows),
    }


def run_memory_suite(args: argparse.Namespace) -> int:
    """MC13.5: runs the local (no live-credential-required) portion of the
    memory benchmark suite -- LongMemEval-shaped dataset cases compared
    across all named retrieval variants, plus all five MC13.3 named
    agent episodes -- and writes a combined report. Missing external dataset
    downloads or live-provider credentials are recorded as named blockers,
    never a fabricated pass.

    72-T08 (D14): every in-process Rush call sees `HOME`, `XDG_DATA_HOME` and
    `LOCALAPPDATA` inside a temporary root; the caller's environment is captured first
    (`provider_env`, for every provider subprocess) and restored before return. A report
    already in `--output` under a different `phase72_embedding` is refused (exit 1)."""
    _check_decision_flags(args)
    if args.task_manifest is not None:
        return _run_manifest_suite(args)
    manifest = _manifest_document(getattr(args, "task_manifest", None))
    embedding = manifest.get("phase72_embedding") if manifest else None
    if _recorded_embedding_differs(Path(args.output), embedding):
        sys.stderr.write(
            "refused: --output holds a report made under a different "
            "phase72_embedding; use a fresh output directory.\n"
        )
        return 1
    original_env = dict(os.environ)
    with tempfile.TemporaryDirectory(prefix="memory-suite-home-") as isolated:
        try:
            for key in _ISOLATED_ENV_KEYS:
                os.environ[key] = str(Path(isolated) / key.lower())
            return _run_memory_suite(
                args, manifest=manifest, embedding=embedding, provider_env=original_env
            )
        finally:
            os.environ.clear()
            os.environ.update(original_env)


def _run_memory_suite(
    args: argparse.Namespace,
    *,
    manifest: dict[str, Any] | None,
    embedding: Any,
    provider_env: Mapping[str, str],
) -> int:
    """`run_memory_suite()`'s body, run inside the isolated environment."""
    permissions = ExecutionPermissions(
        network=True, cache_write=True, artifact_write=True, build=True
    )
    seeds = [int(s) for s in args.seeds.split(",") if s.strip()] or [0]
    blockers: list[str] = []

    if args.dataset_manifest is not None:
        raw = json.loads(Path(args.dataset_manifest).read_text(encoding="utf-8"))
        from .memory_datasets import _validate_section

        _manifest, records = _validate_section(
            "longmemeval", raw.get("longmemeval", raw)
        )
    else:
        _manifest, records = load_dataset_section("longmemeval")
        blockers.append(
            "no --dataset-manifest supplied: using the bundled sample fixture, "
            "never the full external LongMemEval/MemoryAgentBench/SWE-bench "
            "release (requires an operator-provided download grant)."
        )

    dataset_results: dict[int, list[DatasetCaseResult]] = {}
    case_results_by_variant: dict[str, list[DatasetCaseResult]] = {}
    with tempfile.TemporaryDirectory(prefix="memory-suite-") as workspace:
        workspace_root = Path(workspace)
        for seed in seeds:

            def _decide(
                root: Path,
                tool: MemoryTool,
                perms: ExecutionPermissions,
                sanitized: dict[str, Any],
                _variant: str = args.variant,
            ) -> str:
                return _variant_hypothesis(_variant, root, tool, perms, sanitized)

            case_results = [
                run_longmemeval_case(
                    record,
                    decide_fn=_decide,
                    max_total_tokens=args.max_total_tokens,
                    workspace_root=workspace_root,
                )
                for record in records
            ]
            dataset_results[seed] = case_results

        # MC13.4: the actual cross-variant comparison -- every case run once
        # per named variant at the same fixed `max_total_tokens`, so scores
        # differ because of the variant's real retrieval behavior, never
        # seed noise.
        case_results_by_variant = {
            variant: _run_variant_cases(
                records,
                variant,
                max_total_tokens=args.max_total_tokens,
                workspace_root=workspace_root,
            )
            for variant in _MEMORY_VARIANTS
        }

    aggregate_by_seed = {
        seed: aggregate_dataset_results(results)
        for seed, results in dataset_results.items()
    }

    case_ids = [r.case_id for r in case_results_by_variant[_BASELINE_VARIANT]]
    baseline_scores = [
        _case_completion_score(r) for r in case_results_by_variant[_BASELINE_VARIANT]
    ]
    cross_variant_comparison: dict[str, Any] = {}
    for variant in _MEMORY_VARIANTS:
        variant_scores = [
            _case_completion_score(r) for r in case_results_by_variant[variant]
        ]
        diffs = [variant_scores[i] - baseline_scores[i] for i in range(len(case_ids))]
        ci_low, ci_high = paired_bootstrap_ci(diffs, seed=seeds[0])
        cross_variant_comparison[variant] = {
            "score_kind": "harness_completion",
            "case_scores": variant_scores,
            "diff_vs_baseline": diffs,
            "paired_bootstrap_ci": {"low": ci_low, "high": ci_high},
        }

    if len(records) < 5:
        blockers.append(
            "cross-variant comparison ran against the bundled sample fixture "
            f"({len(records)} LongMemEval case(s)): per-case score differences "
            "across all 7 variants are real, not fabricated, but a sample this "
            "small cannot produce a non-degenerate bootstrap CI -- expect "
            "(0.0, 0.0) or a near-zero-width interval until an external "
            "--dataset-manifest with more cases is supplied."
        )

    blockers.append(_COMPONENT_BLOCKER)

    episode_results = {}
    for episode_id in EPISODE_BUILDERS:
        with tempfile.TemporaryDirectory(prefix=f"episode-{episode_id}-") as workspace:
            result = run_named_episode(
                episode_id, Path(workspace), permissions=permissions
            )
            episode_results[episode_id] = {
                "outcome": result.outcome.value,
                "total_tokens": result.total_tokens,
                "budget_exhausted": result.budget_exhausted,
                "timed_out": result.timed_out,
                "verifier_receipt": result.verifier_receipt,
                "receiver_readback": result.receiver_readback,
                "event_count": len(result.events),
            }

    seed_noise_diffs = [
        float(agg["scored"]) - float(aggregate_by_seed[seeds[0]]["scored"])
        for agg in aggregate_by_seed.values()
    ]
    seed_noise_ci_low, seed_noise_ci_high = paired_bootstrap_ci(
        seed_noise_diffs, seed=seeds[0]
    )

    payload = {
        "decision_mode": "component",
        "variant": args.variant,
        "seeds": seeds,
        "max_total_tokens": args.max_total_tokens,
        "dataset_manifest": _manifest.__dict__,
        "dataset_results_by_seed": {
            str(seed): aggregate_by_seed[seed] for seed in seeds
        },
        "paired_bootstrap_ci_seed_noise_within_variant": {
            "variant": args.variant,
            "low": seed_noise_ci_low,
            "high": seed_noise_ci_high,
            "note": "measures seed-to-seed noise for the single requested "
            "--variant across otherwise-identical deterministic runs -- "
            "NOT a cross-variant comparison. See cross_variant_comparison "
            "for the actual none/current/raw/budgeted/linked/full/hybrid "
            "comparison this field's old name (paired_bootstrap_ci_vs_first_seed) "
            "misleadingly implied.",
        },
        "cross_variant_comparison": {
            "baseline_variant": _BASELINE_VARIANT,
            "case_ids": case_ids,
            "per_variant": cross_variant_comparison,
        },
        "episodes": episode_results,
        "usage_accounting": {
            "measured_tokens": True,
            "estimated_tokens": False,
            "note": "all token counts above are measured via tiktoken over real "
            "serialized MemoryTool results, never estimated.",
        },
        "blockers": blockers,
    }
    # 72-T08: the frozen engine identity, the verdict rows and the R20 counts. The
    # provider of a row is its route directory (`<eval root>/<arm>/<route>`).
    output = Path(args.output).resolve()
    verdict_rows = _phase72_rows(
        dataset_results, manifest, arm=args.variant, provider=output.name
    )
    payload["phase72_embedding"] = embedding
    payload["verdict_rows"] = verdict_rows
    payload["phase72_summary"] = _phase72_summary(verdict_rows)
    report_path = write_memory_suite_report(args.output, payload)
    if output.parent.name in HYBRID_ARMS:
        write_hybrid_verdict(output.parent.parent)
    sys.stdout.write(f"\nMemory suite report written to: {report_path}\n")
    for blocker in blockers:
        sys.stdout.write(f"BLOCKED (named): {blocker}\n")
    return 0


# --- P65-09: installed end-to-end project-journey acceptance ---------------

_JOURNEY_PY_SOURCE = (
    "def unreviewed():\n"
    "    pass\n"
    "\n"
    "\n"
    "def compute_value():\n"
    "    return 1\n"
    "\n"
    "\n"
    "WEIRD_VALUE = compute_value()\n"
)
_JOURNEY_SECOND_PY_SOURCE = "def also_unreviewed():\n    pass\n"
_JOURNEY_JS_SOURCE = "function seeded() { return 1; }\n"
_JOURNEY_TF_SOURCE = 'resource "null_resource" "seeded" {}\n'
_JOURNEY_DOCS_SOURCE = "# Project A\n\nDocs for the acceptance journey fixture.\n"
_JOURNEY_MISSING_ENGINE_IDS = ("eslint", "checkov", "markdownlint-cli")


def _project_journey_release_fixture() -> tuple[str, dict[str, bytes]]:
    """Builds a real, self-contained release archive fixture -- a genuine
    POSIX shell script wrapped in a real tar.gz, verified by a real checksum
    manifest -- identical in shape to P65-10's own InstallTool fixture
    (`tests/test_bootstrap_install.py`), never a mocked-until-it-works
    stand-in."""
    import hashlib
    import io
    import platform
    import tarfile

    from rush.tools.install import select_release_asset

    binary_script = (
        b'#!/bin/sh\nif [ "$1" = "--version" ]; then\n  echo 9.9.9\nfi\nexit 0\n'
    )
    asset_name = select_release_asset(platform.system(), platform.machine())
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        info = tarfile.TarInfo(name="rush")
        info.size = len(binary_script)
        info.mode = 0o755
        tar.addfile(info, io.BytesIO(binary_script))
    archive_bytes = buf.getvalue()
    sums_text = f"{hashlib.sha256(archive_bytes).hexdigest()}  {asset_name}\n"
    return asset_name, {
        asset_name: archive_bytes,
        "SHA256SUMS": sums_text.encode("utf-8"),
    }


def run_project_journey(tmp_root: Path) -> dict[str, Any]:
    """P65-09.1/.2: exercises the real, already-implemented P65-01..08/P65-10
    pipeline end to end -- install, provision, register two isolated
    projects (Python+JS+IaC+docs and a second Python-only project),
    connect an isolated agent memory profile, scan, aggregate, hand off to
    an agent, rescan, and retrieve memory -- entirely through the same
    public tool/workflow functions P65-01..10's own tests already exercise
    (no second harness, no fabricated coverage). Every filesystem
    interaction stays under `tmp_root`; nothing touches a real installed
    client config or the real production Rush data root.

    The missing-toolchain acceptance criterion is proven deterministically
    and honestly via a real `apply_provision_plan` call across one engine
    per non-Python language in the fixture (JS/`eslint`, IaC/`checkov`,
    docs/`markdownlint-cli`) with a `which` probe reporting no installed
    package manager -- real code path, real failure code, never a
    fabricated "clean" scan. The scan step itself is scoped to
    `[ReviewTool()]` (mirroring `tests/test_scan_handoff.py`'s own
    determinism precedent) so seeded Python defects produce an exact,
    host-independent finding count; ReviewTool only reviews `.py` files, so
    the JS/IaC/docs files' own engines stay honestly unexercised here
    rather than fabricated.
    """
    from rush.integrations.agents import (
        acknowledge_agent_connection,
        initialize_agent_memory,
        read_agent_memory_state,
        record_tool_observation,
    )
    from rush.setup.provision import apply_provision_plan, build_provision_plan
    from rush.tools.install import InstallTool
    from rush.tools.review import ReviewTool
    from rush.workflows import project_run as project_run_module
    from rush.workflows.project_run import (
        acknowledge_handoff,
        build_handoff,
        complete_handoff,
        dispatch_handoff,
        execute_scan,
        plan_scan,
        rescan_project_run,
        status_handoff,
    )
    from rush.workflows.projects import register_project

    full_permissions = ExecutionPermissions(
        network=True, download=True, cache_write=True, artifact_write=True, build=True
    )
    data_root = tmp_root / "rush-data"
    install_dir = tmp_root / "bin"
    home = tmp_root / "home"
    home.mkdir(parents=True, exist_ok=True)

    _asset_name, assets = _project_journey_release_fixture()

    def _downloader(url: str) -> bytes:
        return assets[url.rsplit("/", 1)[-1]]

    install_result = dict(
        InstallTool().run(
            agents="none",
            memory="on",
            session_id="journey-session",
            home=home,
            data_root=data_root,
            install_dir=install_dir,
            downloader=_downloader,
            permissions=full_permissions,
        )
    )

    project_a_root = tmp_root / "project-a"
    project_a_root.mkdir()
    (project_a_root / "app.py").write_text(_JOURNEY_PY_SOURCE, encoding="utf-8")
    (project_a_root / "app.js").write_text(_JOURNEY_JS_SOURCE, encoding="utf-8")
    (project_a_root / "main.tf").write_text(_JOURNEY_TF_SOURCE, encoding="utf-8")
    (project_a_root / "README.md").write_text(_JOURNEY_DOCS_SOURCE, encoding="utf-8")
    project_a_id = register_project(project_a_root, data_root=data_root).project_id

    project_b_root = tmp_root / "project-b"
    project_b_root.mkdir()
    (project_b_root / "app.py").write_text(_JOURNEY_SECOND_PY_SOURCE, encoding="utf-8")
    project_b_id = register_project(project_b_root, data_root=data_root).project_id

    provision_plan = build_provision_plan(
        project_a_root, list(_JOURNEY_MISSING_ENGINE_IDS), data_root=data_root
    )
    provision_result = apply_provision_plan(
        provision_plan,
        full_permissions,
        project_id=project_a_id,
        data_root=data_root,
        reviewed_plan_id=provision_plan.plan_id,
        which=lambda _name: None,
    )

    initialize_agent_memory(
        "cursor", "journey-session", project_root=project_a_root, consent=True
    )
    initialize_agent_memory(
        "cursor", "journey-session", project_root=project_b_root, consent=True
    )
    record_tool_observation(
        "cursor",
        "journey-session",
        {"tool": "scan", "project": "a"},
        project_root=project_a_root,
    )
    acknowledge_agent_connection(
        "cursor", "journey-session", project_root=project_a_root
    )
    agent_state_a = read_agent_memory_state(
        "cursor", "journey-session", project_root=project_a_root
    )
    agent_state_b = read_agent_memory_state(
        "cursor", "journey-session", project_root=project_b_root
    )

    original_tools = project_run_module.ALL_TOOLS
    project_run_module.ALL_TOOLS = [ReviewTool()]
    try:
        plan_a = plan_scan(project_a_id, data_root=data_root)
        run_a = execute_scan(plan_a, permissions=full_permissions, data_root=data_root)
        plan_b = plan_scan(project_b_id, data_root=data_root)
        run_b = execute_scan(plan_b, permissions=full_permissions, data_root=data_root)
    finally:
        project_run_module.ALL_TOOLS = original_tools

    handoff = build_handoff(
        project_a_id, run_a.run_id, "codex-cli", data_root=data_root
    )
    dispatch_handoff(
        project_a_id,
        handoff.handoff_id,
        handoff.session_capability,
        data_root=data_root,
    )
    acknowledge_handoff(
        project_a_id, handoff.handoff_id, handoff.delivery_nonce, data_root=data_root
    )
    completed = complete_handoff(
        project_a_id,
        handoff.handoff_id,
        handoff.delivery_nonce,
        artifact_ids=("agent-patch-1",),
        data_root=data_root,
    )
    handoff_status = status_handoff(
        project_a_id, handoff.handoff_id, data_root=data_root
    )

    rescan_result = rescan_project_run(project_a_id, run_a.run_id, data_root=data_root)

    memory_tool = MemoryTool()
    memory_tool.run(
        project_a_root,
        operation="write",
        subject="episodic",
        content={
            "kind": "observation",
            "text": f"handoff {handoff.handoff_id} completed for run {run_a.run_id}",
        },
        source="journey-session",
        permissions=full_permissions,
    )
    memory_recall = dict(
        memory_tool.run(
            project_a_root,
            operation="recall",
            subject="episodic",
            query="handoff",
            session_allowlist=["journey-session"],
            request={"view": "compact", "max_tokens": 2048},
            permissions=full_permissions,
        )
    )

    ui_journey = run_dashboard_user_journey(tmp_root / "ui-journey")

    return {
        "install": install_result,
        "project_a_id": project_a_id,
        "project_b_id": project_b_id,
        "provision_result": provision_result,
        "agent_state_a": agent_state_a,
        "agent_state_b": agent_state_b,
        "run_a": run_a,
        "run_b": run_b,
        "handoff": handoff,
        "completed": completed,
        "handoff_status": handoff_status,
        "rescan_result": rescan_result,
        "memory_recall": memory_recall,
        "ui_journey": ui_journey,
        "blockers": [
            (
                "eslint/checkov/markdownlint-cli were never available in this "
                "sandbox (no npm/uv-installed package manager reachable) -- "
                "apply_provision_plan's real SYSTEM_PREREQUISITE_REQUIRED failure "
                "is asserted exactly, never a fabricated successful install."
            ),
            (
                "no real connected-agent session or live provider credential was "
                "available in this sandbox -- the connected-agent profile above "
                "exercises Rush's own real consent/acknowledgment/isolation "
                "mechanics (rush.integrations.agents), never a live agent process."
            ),
            *ui_journey["blockers"],
        ],
    }


def run_dashboard_user_journey(tmp_root: Path) -> dict[str, Any]:
    """P66-07.1: extends `run_project_journey` above with real dashboard-HTTP
    UI-action timing/coverage evidence for the browser/TUI-shared journey --
    add project, provision, scan, findings, handoff, rescan, memory, tokens,
    Git, artifact -- driven entirely through the one real
    `create_dashboard_server` HTTP boundary the browser and `rush ui` both
    share (no second harness, no mock backend). Every stage records its own
    wall-clock duration and a named pass/fail coverage flag, so a missing
    section/control fails a named assertion in the caller rather than
    reading as a silent pass.

    `time_to_first_interactive_ms` measures the real session bootstrap
    round-trip (`POST /api/session`) against the freshly-started server --
    the same authenticated exchange the browser performs before any UI is
    interactive.
    """
    import subprocess
    import threading
    import time
    import urllib.error
    import urllib.request
    import uuid
    from unittest.mock import patch
    from urllib.parse import urlencode

    from rush.dashboard.server import create_dashboard_server
    from rush.setup import provision as provision_module
    from rush.token_economy.telemetry import TelemetryStore
    from rush.tools.review import ReviewTool
    from rush.workflows import project_run as project_run_module
    from rush.workflows import projects as projects_module

    data_root = tmp_root / "rush-data"
    project_root = tmp_root / "ui-project"
    project_root.mkdir(parents=True, exist_ok=True)
    (project_root / "app.py").write_text(
        "def unreviewed():\n    pass\n", encoding="utf-8"
    )
    git_env = {
        **os.environ,
        "GIT_AUTHOR_NAME": "UI Journey",
        "GIT_AUTHOR_EMAIL": "ui-journey@rush.dev",
        "GIT_COMMITTER_NAME": "UI Journey",
        "GIT_COMMITTER_EMAIL": "ui-journey@rush.dev",
    }
    subprocess.run(
        ["git", "init", "--quiet"], cwd=project_root, env=git_env, check=True
    )
    subprocess.run(["git", "add", "app.py"], cwd=project_root, env=git_env, check=True)
    subprocess.run(
        ["git", "commit", "--quiet", "-m", "seed ui journey project"],
        cwd=project_root,
        env=git_env,
        check=True,
    )

    def _get(url: str, headers: dict[str, str] | None = None):
        req = urllib.request.Request(url, headers=headers or {}, method="GET")
        try:
            return urllib.request.urlopen(req, timeout=5)
        except urllib.error.HTTPError as exc:
            return exc

    def _post(url: str, headers: dict[str, str] | None = None, body: bytes = b""):
        req = urllib.request.Request(
            url, data=body, headers=headers or {}, method="POST"
        )
        try:
            return urllib.request.urlopen(req, timeout=5)
        except urllib.error.HTTPError as exc:
            return exc

    def _action(
        base_url: str,
        project_id: str,
        cookie: str,
        csrf: str,
        *,
        operation: str,
        arguments: dict[str, Any] | None = None,
        grants: dict[str, Any] | None = None,
        expected: dict[str, Any] | None = None,
    ) -> tuple[int, dict[str, Any]]:
        # P69-07 (round-7 correction, moved from P69-02): every memory-mutation call this
        # helper makes carries a real `owner_scope` -- P69-07's own ownership contract
        # (subsection a) accepts `owner_scope=None` gracefully (legacy default), so this
        # is additive, never a behavior change to what the dashboard already accepts.
        # M08 (T024): a `project`-kind owner's id must equal this request's own
        # URL-selected project id, not the filesystem root path -- the dashboard
        # boundary now rejects a mismatched id outright.
        final_arguments = dict(arguments or {})
        if operation.startswith("memory_") and "owner_scope" not in final_arguments:
            final_arguments["owner_scope"] = {
                "kind": "project",
                "id": project_id,
            }
        if operation.startswith("memory_"):
            memory_mutation_arguments_sent.append(dict(final_arguments))
        body = json.dumps(
            {
                "schema_version": 1,
                "operation": operation,
                "arguments": final_arguments,
                "grants": grants or {},
                "expected": expected or {},
                "request_id": str(uuid.uuid4()),
            }
        ).encode("utf-8")
        resp = _post(
            f"{base_url}/api/projects/{project_id}/actions",
            headers={
                "Cookie": cookie,
                "X-Rush-CSRF": csrf,
                "Origin": base_url,
                "Content-Type": "application/json",
            },
            body=body,
        )
        return resp.status, json.loads(resp.read())

    def _poll_operation(
        base_url: str,
        project_id: str,
        cookie: str,
        operation_id: str,
        *,
        timeout: float = 10.0,
    ) -> dict[str, Any] | None:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            resp = _get(
                f"{base_url}/api/projects/{project_id}/operations/{operation_id}",
                headers={"Cookie": cookie},
            )
            if resp.status == 200:
                payload = json.loads(resp.read())
                if (payload.get("data") or {}).get("status") == "terminal":
                    return payload
            time.sleep(0.05)
        return None

    def _snapshot(
        base_url: str, project_id: str, cookie: str, section: str, **query: str
    ) -> tuple[int, dict[str, Any]]:
        qs = urlencode({"section": section, **query})
        resp = _get(
            f"{base_url}/api/projects/{project_id}/snapshot?{qs}",
            headers={"Cookie": cookie},
        )
        return resp.status, json.loads(resp.read())

    timings_ms: dict[str, float] = {}
    coverage: dict[str, bool] = {}
    errors: list[str] = []
    # P69-07 (round-7 correction): every `_action()` call whose operation starts with
    # "memory_" records its actual sent arguments here, so a caller can assert
    # `owner_scope` was really on the wire, not just injected in the code.
    memory_mutation_arguments_sent: list[dict[str, Any]] = []
    grants_all = {"cache_write": True, "artifact_write": True, "download": True}

    def _mark(stage: str, ok: bool, detail: str = "") -> None:
        coverage[stage] = ok
        if not ok:
            errors.append(f"{stage}: {detail}" if detail else stage)

    _TERMINAL_RUN_STATES = {"completed", "incomplete", "failed", "cancelled"}
    _HOSTILE_MESSAGE = "<script>alert('hostile finding')</script>"

    class _HostileFindingTool:
        """Reuses the real `typecheck` catalog name (mirrors `_StubTypecheck`
        in tests/test_dashboard_scan_actions.py) so it is scheduled as a real
        applicable candidate for this Python project, returning one finding
        whose message is a real hostile payload -- proves the dashboard
        findings HTTP section carries untrusted scan output only as an inert
        JSON string field, never interpolated into HTML."""

        name = "typecheck"

        def __call__(self, path: Path) -> dict[str, object]:
            return {
                "tool": "typecheck",
                "engine": None,
                "engine_version": None,
                "status": "warn",
                "duration_ms": 1,
                "summary": "typecheck: 1 issue",
                "findings": [
                    {
                        "path": "app.py",
                        "line": 1,
                        "column": 0,
                        "rule": "hostile-payload",
                        "severity": "warn",
                        "message": _HOSTILE_MESSAGE,
                    }
                ],
                "raw": None,
            }

    with (
        patch.object(projects_module, "default_data_root", lambda: data_root),
        patch.object(provision_module, "default_data_root", lambda: data_root),
        patch.object(
            project_run_module, "ALL_TOOLS", [ReviewTool(), _HostileFindingTool()]
        ),
    ):
        server, ctx, token = create_dashboard_server({})
        thread = threading.Thread(
            target=server.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True
        )
        thread.start()
        try:
            base_url = ctx.launch_origin

            start = time.monotonic()
            session_resp = _post(
                f"{base_url}/api/session",
                headers={"Authorization": f"Bearer {token}"},
            )
            time_to_first_interactive_ms = round((time.monotonic() - start) * 1000, 3)
            _mark("session_bootstrap", session_resp.status == 200)
            session_payload = json.loads(session_resp.read())
            cookie = session_resp.headers.get("Set-Cookie", "").split(";")[0]
            csrf = session_payload["csrf_token"]

            # --- add project -----------------------------------------------
            start = time.monotonic()
            add_body = json.dumps(
                {
                    "operation": "add",
                    "path": str(project_root),
                    "grants": grants_all,
                    "request_id": str(uuid.uuid4()),
                }
            ).encode("utf-8")
            added = _post(
                f"{base_url}/api/projects",
                headers={
                    "Cookie": cookie,
                    "X-Rush-CSRF": csrf,
                    "Content-Type": "application/json",
                    "Origin": base_url,
                },
                body=add_body,
            )
            timings_ms["add_project"] = round((time.monotonic() - start) * 1000, 3)
            added_data = json.loads(added.read()).get("data", {})
            _mark(
                "add_project",
                added.status == 201 and "project_id" in added_data,
                f"status={added.status}",
            )
            project_id = added_data.get("project_id")

            # --- provision ---------------------------------------------------
            start = time.monotonic()
            status, body = _action(
                base_url, project_id, cookie, csrf, operation="provision_plan"
            )
            timings_ms["provision"] = round((time.monotonic() - start) * 1000, 3)
            plan_id = body.get("data", {}).get("scan_plan", {}).get("plan_id")
            _mark(
                "provision", status == 200 and plan_id is not None, f"status={status}"
            )

            # --- scan ----------------------------------------------------------
            start = time.monotonic()
            status, body = _action(
                base_url,
                project_id,
                cookie,
                csrf,
                operation="scan_start",
                arguments={"plan_id": plan_id},
                grants=grants_all,
            )
            run_id = body.get("data", {}).get("run_id")
            run_summary = None
            if status == 202 and run_id:
                deadline = time.monotonic() + 60.0
                while time.monotonic() < deadline:
                    scan_status, scans = _snapshot(
                        base_url, project_id, cookie, "scans", run_id=run_id
                    )
                    candidate_run = scans.get("data", {}).get("run")
                    if (
                        scan_status == 200
                        and candidate_run
                        and candidate_run.get("run_state") in _TERMINAL_RUN_STATES
                    ):
                        run_summary = candidate_run
                        break
                    time.sleep(0.05)
            timings_ms["scan"] = round((time.monotonic() - start) * 1000, 3)
            _mark("scan", run_summary is not None, f"status={status}")

            # --- findings --------------------------------------------------
            start = time.monotonic()
            status, scans = _snapshot(
                base_url, project_id, cookie, "scans", run_id=run_id
            )
            finding_items = scans.get("data", {}).get("findings", {}).get("items", [])
            timings_ms["findings"] = round((time.monotonic() - start) * 1000, 3)
            _mark(
                "findings",
                status == 200 and len(finding_items) > 0,
                f"status={status} count={len(finding_items)}",
            )

            # --- hostile finding text (P66-07.3 acceptance requirement) -----
            hostile_item = next(
                (f for f in finding_items if f.get("rule") == "hostile-payload"), None
            )
            asset_resp = _get(
                f"{base_url}/assets/application.js", headers={"Cookie": cookie}
            )
            map_asset_resp = _get(
                f"{base_url}/assets/project_map.js", headers={"Cookie": cookie}
            )
            _mark(
                "hostile_finding_text",
                hostile_item is not None
                and hostile_item.get("message") == _HOSTILE_MESSAGE
                and b"innerHTML" not in asset_resp.read()
                and b"innerHTML" not in map_asset_resp.read(),
                "hostile payload was not carried as an inert JSON field, or an "
                "owned rendering asset uses innerHTML",
            )

            # --- handoff -----------------------------------------------------
            start = time.monotonic()
            finding_ids = [f["finding_id"] for f in finding_items]
            status, body = _action(
                base_url,
                project_id,
                cookie,
                csrf,
                operation="handoff_preview",
                arguments={
                    "run_id": run_id,
                    "agent_id": "ui-journey-agent",
                    "finding_ids": finding_ids,
                },
                grants=grants_all,
            )
            content_hash = body.get("data", {}).get("handoff_id")
            send_status = None
            handoff_delivered = False
            if status == 200 and content_hash:
                send_status, send_body = _action(
                    base_url,
                    project_id,
                    cookie,
                    csrf,
                    operation="handoff_send",
                    arguments={
                        "run_id": run_id,
                        "agent_id": "ui-journey-agent",
                        "finding_ids": finding_ids,
                        "handoff_id": content_hash,
                    },
                    grants=grants_all,
                )
                operation_id = send_body.get("data", {}).get("operation_id")
                if send_status == 202 and operation_id:
                    terminal = _poll_operation(
                        base_url, project_id, cookie, operation_id
                    )
                    outcome = ((terminal or {}).get("data") or {}).get("payload") or {}
                    handoff_delivered = outcome.get("status") == "success"
            timings_ms["handoff"] = round((time.monotonic() - start) * 1000, 3)
            _mark(
                "handoff",
                handoff_delivered,
                f"preview_status={status} send_status={send_status}",
            )

            # --- rescan --------------------------------------------------------
            start = time.monotonic()
            status, body = _action(
                base_url,
                project_id,
                cookie,
                csrf,
                operation="rescan",
                arguments={"run_id": run_id},
                grants=grants_all,
            )
            rescan_run = None
            if status == 202:
                deadline = time.monotonic() + 60.0
                while time.monotonic() < deadline:
                    scan_status, scans = _snapshot(
                        base_url, project_id, cookie, "scans"
                    )
                    current_run = scans.get("data", {}).get("run")
                    if (
                        scan_status == 200
                        and current_run is not None
                        and current_run["run_id"] != run_id
                        and current_run.get("run_state") in _TERMINAL_RUN_STATES
                    ):
                        rescan_run = current_run
                        break
                    time.sleep(0.05)
            timings_ms["rescan"] = round((time.monotonic() - start) * 1000, 3)
            _mark("rescan", rescan_run is not None, f"status={status}")

            # --- memory --------------------------------------------------------
            start = time.monotonic()
            memory_tool = MemoryTool()
            memory_tool.run(
                project_root,
                operation="write",
                subject="domain_knowledge",
                content={"text": "ui journey memory write"},
                source="ui-journey-session",
                permissions=ExecutionPermissions(
                    network=False,
                    download=False,
                    cache_write=True,
                    artifact_write=True,
                    build=False,
                ),
            )
            mem_status, mem_snap = _snapshot(base_url, project_id, cookie, "memory")
            mem_items = mem_snap.get("data", {}).get("items", [])
            edit_status = None
            if mem_items:
                edit_status, _edit_body = _action(
                    base_url,
                    project_id,
                    cookie,
                    csrf,
                    operation="memory_edit",
                    arguments={
                        "scope": mem_items[0]["subject"],
                        "id": mem_items[0]["id"],
                        "expected_version": 1,
                        "content": {"text": "ui journey memory write (edited)"},
                        "apply": True,
                    },
                    grants=grants_all,
                )
            timings_ms["memory"] = round((time.monotonic() - start) * 1000, 3)
            _mark(
                "memory",
                mem_status == 200 and len(mem_items) > 0 and edit_status == 200,
                f"snapshot_status={mem_status} edit_status={edit_status}",
            )

            # --- tokens ----------------------------------------------------
            start = time.monotonic()
            telemetry = TelemetryStore(project_root)
            telemetry.record_savings(
                "review", raw_tokens=100, compressed_tokens=40, project_id=project_id
            )
            telemetry.record_savings("review", raw_tokens=1000, compressed_tokens=400)
            telemetry.record_savings(
                "review",
                raw_tokens=2000,
                compressed_tokens=800,
                project_id=str(uuid.uuid4()),
            )
            tok_status, tok_snap = _snapshot(base_url, project_id, cookie, "tokens")
            timings_ms["tokens"] = round((time.monotonic() - start) * 1000, 3)
            _mark(
                "tokens",
                tok_status == 200
                and tok_snap.get("data", {}).get("actual", {}).get("raw_tokens", 0)
                == 100,
                f"status={tok_status}",
            )

            # --- git -------------------------------------------------------
            start = time.monotonic()
            git_status, git_snap = _snapshot(base_url, project_id, cookie, "git")
            timings_ms["git"] = round((time.monotonic() - start) * 1000, 3)
            _mark(
                "git",
                git_status == 200 and git_snap.get("data", {}).get("has_git") is True,
                f"status={git_status}",
            )

            # --- artifact ----------------------------------------------------
            start = time.monotonic()
            art_status, art_snap = _snapshot(base_url, project_id, cookie, "artifacts")
            art_items = art_snap.get("data", {}).get("items", [])
            timings_ms["artifact"] = round((time.monotonic() - start) * 1000, 3)
            _mark(
                "artifact",
                art_status == 200 and len(art_items) > 0,
                f"status={art_status} count={len(art_items)}",
            )
        finally:
            server.shutdown()
            server.server_close()

    return {
        "time_to_first_interactive_ms": time_to_first_interactive_ms,
        "timings_ms": timings_ms,
        "coverage": coverage,
        "errors": errors,
        "memory_mutation_arguments_sent": memory_mutation_arguments_sent,
        "tokens_snapshot": tok_snap.get("data", {}),
        "blockers": [
            (
                "actual pixel layout at 360px/1280px and a real visual "
                "keyboard focus ring are unverifiable without a real "
                "browser in this sandbox (no usable headless-Chromium/"
                "Selenium binary here) -- this journey instead drives the "
                "real HTTP/JSON dashboard API the browser itself calls, "
                "and separately checks the NO_COLOR/reduced-motion/theme "
                "token contracts (tests/test_dashboard_motion_contract.py); "
                "never a fabricated browser screenshot pass."
            ),
            (
                "no Windows console is reachable from this Darwin sandbox -- "
                "the terminal journey is proven for POSIX only, via a real "
                "pty.fork() run (tests/test_tui_terminal.py); the Windows "
                "terminal lane remains an explicit, unresolved blocker, "
                "never completed-by-proxy."
            ),
        ],
    }


def run_project_journey_suite(args: argparse.Namespace) -> int:
    """P65-09.3: runs the installed end-to-end project-journey acceptance
    workload in an isolated temporary workspace and writes its report next
    to the other benchmark suites (same atomic-write pattern as
    `write_result`/`write_memory_suite_report`)."""
    with tempfile.TemporaryDirectory(prefix="project-journey-") as workspace:
        result = run_project_journey(Path(workspace))

    payload = {
        "install_status": result["install"]["status"],
        "project_a_id": result["project_a_id"],
        "project_b_id": result["project_b_id"],
        "provision_failed": result["provision_result"].failed,
        "agent_state_a": result["agent_state_a"],
        "agent_state_b": result["agent_state_b"],
        "run_a": result["run_a"].to_dict(),
        "run_b": result["run_b"].to_dict(),
        "handoff_state": result["completed"].state,
        "handoff_status": result["handoff_status"],
        "rescan_comparison": result["rescan_result"]["comparison"],
        "memory_recall": result["memory_recall"],
        "ui_journey": result["ui_journey"],
        "blockers": result["blockers"],
    }
    output_root = args.output.resolve()
    output_root.mkdir(parents=True, exist_ok=True)
    dest_path = output_root / "project-journey-report.json"
    tmp_path = output_root / "project-journey-report.tmp"
    tmp_path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    os.replace(tmp_path, dest_path)

    sys.stdout.write(f"\nProject journey report written to: {dest_path}\n")
    for blocker in result["blockers"]:
        sys.stdout.write(f"BLOCKED (named): {blocker}\n")
    return 0


def run_scenario(
    scenario_id: str,
    output_root: Path,
    *,
    model_cache: Path | None = None,
    allow_live_route: list[str] | tuple[str, ...] | str | None = None,
    allow_model_download: list[str] | None = None,
    provider_executable: Path | None = None,
    local_runtime_executable: list[Path] | None = None,
    router_urls: list[str] | None = None,
    env: Mapping[str, str] | None = None,
) -> ProbeResult:
    """Executes a single scenario by ID and writes atomic output JSON. 72-T08 (D14):
    `env`, when given, is the environment every provider subprocess runs with."""
    scenarios = load_scenarios()
    if scenario_id not in scenarios:
        raise FixtureError(f"unknown scenario: {scenario_id}")

    scenario = scenarios[scenario_id]
    allowed_model_downloads = set(allow_model_download or [])
    allowed_candidate = scenario.input.get("candidate_id") in allowed_model_downloads
    if scenario.probe == "local" and allowed_candidate:
        live_input = dict(scenario.input)
        live_input.pop("mode", None)
        scenario = replace(scenario, input=live_input)
    live_route_ids = (
        (allow_live_route,)
        if isinstance(allow_live_route, str)
        else tuple(allow_live_route or [])
    )
    allowed_live_routes = set(live_route_ids)
    if scenario.probe == "provider" and "router_id" not in scenario.input:
        from .fixtures import load_provider_routes

        routes = load_provider_routes()
        provider_ids = (
            str(scenario.input.get("source_provider", "")),
            str(scenario.input.get("target_provider", "")),
        )
        selected_route = next(
            (
                route_id
                for provider_id in provider_ids
                for route_id in live_route_ids
                if route_id in routes and routes[route_id].provider_id == provider_id
            ),
            None,
        )
    else:
        selected_route = None
    if selected_route:
        live_input = dict(scenario.input)
        live_input.pop("router_id", None)
        live_input["route_id"] = selected_route
        scenario = replace(scenario, input=live_input)
    probe_fn = get_probe_runner(scenario.probe)
    provider_env = (
        {"env": env} if env is not None and scenario.probe == "provider" else {}
    )
    result = probe_fn(
        scenario,
        model_cache=model_cache,
        allow_live_route=allowed_live_routes,
        allow_model_download=(
            scenario.input.get("candidate_id") if allowed_candidate else None
        ),
        output_root=output_root,
        provider_executable=provider_executable,
        local_runtime_executable=local_runtime_executable,
        router_urls=router_urls,
        **provider_env,
    )
    write_result(output_root, result)
    return result


def main(argv: list[str] | None = None) -> int:
    """CLI entrypoint."""
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.suite != "memory" and (
        args.decision_mode == "live"
        or args.decision_route is not None
        or args.task_manifest is not None
    ):
        sys.stderr.write(
            "Memory suite error: decision_flags_require_memory_suite: "
            "--decision-mode live, --decision-route and --task-manifest need "
            "--suite memory\n"
        )
        return 1

    if args.suite == "memory":
        try:
            return run_memory_suite(args)
        except (FixtureError, OSError, ValueError) as err:
            message, _count = redact_report(_error_chain(err))
            sys.stderr.write(f"Memory suite error: {message}\n")
            return 1

    if args.suite == "project_journey":
        try:
            return run_project_journey_suite(args)
        except (FixtureError, OSError, ValueError) as err:
            sys.stderr.write(f"Project journey suite error: {err}\n")
            return 1

    if not args.scenario and not args.all:
        parser.print_help()
        return 1

    try:
        scenarios = load_scenarios()
        target_ids = list(scenarios.keys()) if args.all else [args.scenario]
        results: list[ProbeResult] = []

        sys.stdout.write(f"\nRunning {len(target_ids)} benchmark scenario(s)...\n\n")
        header = f"{'Scenario ID':<48} {'Probe':<14} {'Outcome':<10} {'Duration':<10}"
        sys.stdout.write(header + "\n")
        sys.stdout.write("-" * len(header) + "\n")

        for sc_id in target_ids:
            res = run_scenario(
                sc_id,
                args.output,
                model_cache=args.model_cache,
                allow_live_route=args.allow_live_route,
                allow_model_download=args.allow_model_download,
                provider_executable=args.provider_executable,
                local_runtime_executable=args.local_runtime_executable,
                router_urls=args.router_url,
            )
            results.append(res)
            line = f"{res.scenario_id:<48} {res.probe:<14} {res.outcome.value:<10} {res.duration_ms}ms"
            sys.stdout.write(line + "\n")

        passed = sum(1 for r in results if r.outcome == Outcome.PASS)
        skipped = sum(1 for r in results if r.outcome == Outcome.SKIPPED)
        failed = sum(1 for r in results if r.outcome == Outcome.FAIL)
        inconclusive = sum(1 for r in results if r.outcome == Outcome.INCONCLUSIVE)

        # Generate formal gate decisions and final-handoff.md
        from .reporting import generate_and_write_decisions

        generate_and_write_decisions(results, args.output)

        sys.stdout.write("-" * len(header) + "\n")
        sys.stdout.write(
            f"Benchmark Summary: Total={len(results)} | Passed={passed} | Skipped={skipped} | Failed={failed} | Inconclusive={inconclusive}\n"
        )
        sys.stdout.write(f"Results & Handoff written to: {args.output.resolve()}\n\n")
        return 0 if failed == 0 else 1
    except Exception as err:  # noqa: BLE001
        sys.stderr.write(f"Benchmark error: {err}\n")
        return 1


if __name__ == "__main__":
    sys.exit(main())
