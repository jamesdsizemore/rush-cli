"""MC05 (Phase 63) canonical observation capture for real tool executions.

`record_observation` is the single canonical observer invoked from
`InvocationExecutor.execute` (§6.4 of the Phase 63 plan) after a handler
returns and before the result-cache write. It normalizes a completed
`InvocationContext` + tool result into one `experience`/`episodic`
`MemoryArtifact`, tagged with one of five explicit capability families
(R14-R17), and writes it through the existing `TypedArtifactStore.write()`
path -- never a parallel store or raw SQL. Secret redaction happens inside
`write()` itself (`sanitize_value` runs on `artifact.content` immediately
before the INSERT), so there is no window where an unredacted value could be
persisted.

Never raises: an internal failure here must never convert, rerun, or block
the original tool result (§6.4). Failure is reported as a log diagnostic only.
"""

from __future__ import annotations

import copy
import json
import logging
import time
import uuid
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

from rush.invocation.models import InvocationContext
from rush.memory.intent import intent_evidence as _intent_evidence
from rush.memory.store import (
    MemoryAccessChanged,
    MemoryArtifact,
    MemorySubject,
    TypedArtifactStore,
    compute_content_signature,
)
from rush.memory.trust import default_entry_tier

if TYPE_CHECKING:
    from rush.memory.retrieval import MemoryAccess

logger = logging.getLogger(__name__)


class MemoryWriteDenied(Exception):
    """72-T01 D4: an experience writer's write was not authorized (no row written)."""

    def __init__(self, code: str, reason: str) -> None:
        super().__init__(f"{code}: {reason}")
        self.code = code
        self.reason = reason


def _authorized_write(
    project_root: Path,
    artifact: MemoryArtifact,
    write: Any,
    *,
    open_store: Any,
    access: Any = None,
) -> Any:
    """D4: run `write(store, artifact, commit_check)` inside the shared writer
    gate. A denial (or an access change before commit) raises `MemoryWriteDenied`
    before any file, directory or row exists."""
    import dataclasses

    from rush.memory.retrieval import (
        RouteDenial,
        authorize_writer,
        recheck_failure,
        writer_owner,
    )

    with authorize_writer(project_root, artifact.source, access=access) as granted:
        if isinstance(granted, RouteDenial):
            raise MemoryWriteDenied(granted.code, granted.reason)
        owned = (
            dataclasses.replace(artifact, owner_scope=writer_owner(granted))
            if artifact.owner_scope is None
            else artifact
        )
        try:
            return write(open_store(), owned, lambda: recheck_failure(granted))
        except MemoryAccessChanged as exc:
            raise MemoryWriteDenied(exc.code, exc.reason) from exc


EvidenceKind = Literal[
    "tests_contracts",
    "source_graph",
    "security_dependency",
    "sandbox_verification",
    "continuity_checkpoint",
]

# Five capability families from the vibecoder-integrations assessment
# (`.scratch/memory-capability-assessment/vibecoder-integrations.md` §"Where the
# rest of Rush contributes", R14-R17). Unknown operations fall back to
# "sandbox_verification": most Rush tools ultimately execute and report a
# command outcome, the closest family semantics to a generic executed result.
_FAMILY_BY_OPERATION: dict[str, EvidenceKind] = {
    # Tests, contracts, snapshots, E2E, mutation (R14)
    "test": "tests_contracts",
    "contract": "tests_contracts",
    "mutation": "tests_contracts",
    "e2e": "tests_contracts",
    "pbt": "tests_contracts",
    "fuzz": "tests_contracts",
    "flaky": "tests_contracts",
    "tdd-guard": "tests_contracts",
    "snapshot": "tests_contracts",
    # Codegraph, API diff, coverage (R15)
    "api-diff": "source_graph",
    "coverage": "source_graph",
    "blast-radius": "source_graph",
    "blast-radius-graph": "source_graph",
    "arch-guard": "source_graph",
    "review": "source_graph",
    "complexity": "source_graph",
    "dead": "source_graph",
    "dead-asset": "source_graph",
    # Security, dependency and license checks (R16)
    "security": "security_dependency",
    "codeql": "security_dependency",
    "sbom": "security_dependency",
    "license-matrix": "security_dependency",
    "iam-audit": "security_dependency",
    "secrets": "security_dependency",
    "db-drift": "security_dependency",
    # Sandbox, patch verification, provenance (R17)
    "patch-apply": "sandbox_verification",
    "fix": "sandbox_verification",
    "attest": "sandbox_verification",
    "provenance-ai": "sandbox_verification",
    # Continuity, checkpoints, token utilities (R17)
    "continuity": "continuity_checkpoint",
    "flight-recorder": "continuity_checkpoint",
    "mem-profile": "continuity_checkpoint",
    "cold-start": "continuity_checkpoint",
}


def classify_capability_family(operation_id: str) -> EvidenceKind:
    """Map an operation ID onto one of the five explicit capability families."""
    normalized = operation_id.replace("_", "-")
    return _FAMILY_BY_OPERATION.get(
        normalized, _FAMILY_BY_OPERATION.get(operation_id, "sandbox_verification")
    )


def _field(result: Any, key: str, default: Any = None) -> Any:
    """Read one field from a `ToolResult` TypedDict/dict or a `ToolResultV1` dataclass."""
    if isinstance(result, Mapping):
        return result.get(key, default)
    return getattr(result, key, default)


def write_observation(
    *,
    evidence_kind: EvidenceKind,
    operation_id: str,
    source: str,
    content: dict[str, Any],
    project_root: Path,
    access: Any = None,
) -> MemoryArtifact | None:
    """Normalize and persist one `experience`/`episodic` observation. Raises only
    `MemoryWriteDenied` (72-T01 D4: the write is authorized through the shared
    writer gate; `access` is a caller-resolved `MemoryAccess`); every other failure
    is logged and returns `None`.

    Reuses `TypedArtifactStore.write()` (§6.1 family/subject vocabulary,
    redact-before-store invariant) -- no parallel store, no raw SQL.
    """
    try:
        payload = {
            "schema_version": 1,
            "kind": "observation",
            "evidence_kind": evidence_kind,
            "operation_id": operation_id,
            **content,
        }
        artifact = MemoryArtifact(
            id=str(uuid.uuid4()),
            family="experience",
            subject="episodic",
            trust_tier=default_entry_tier("local_tool"),
            content=payload,
            source=source,
            created_at=time.time(),
            content_hash=compute_content_signature(payload),
        )
        stored: MemoryArtifact = _authorized_write(
            project_root,
            artifact,
            lambda store, row, check: store.write(row, commit_check=check),
            open_store=lambda: TypedArtifactStore(project_root),
            access=access,
        )
        return stored
    except MemoryWriteDenied:
        raise
    except Exception:
        logger.warning(
            "memory observation write failed for operation %r (evidence_kind=%r)",
            operation_id,
            evidence_kind,
            exc_info=True,
        )
        return None


def record_observation(
    context: InvocationContext,
    result: Any,
    *,
    project_root: Path | None = None,
) -> MemoryArtifact | None:
    """Capture one real tool execution as a canonical, redacted observation.

    Caller (`InvocationExecutor.execute`) already gates this on
    `context.memory_record` and `"cache_write" in context.permissions`; this
    function additionally excludes the `memory` tool's own operations from
    recursive self-observation (§6.4).
    """
    if context.operation_id == "memory":
        return None

    evidence_kind = classify_capability_family(context.operation_id)
    content = {
        "request_id": context.request_id,
        "transport": context.transport,
        "targets": [str(t.relative_path) for t in context.targets],
        "workspace_root": str(context.workspace_root),
        "effective_config_digest": context.effective_config_digest,
        "environment_digest": context.environment_digest,
        "artifact_build_identity": context.artifact_build_identity,
        "tool_revision": context.tool_revision,
        "normalizer_revision": context.normalizer_revision,
        "ordered_args": list(context.ordered_args),
        "declared_ignored_inputs": list(context.declared_ignored_inputs),
        "engine": _field(result, "engine"),
        "engine_version": _field(result, "engine_version"),
        "status": _field(result, "status"),
        "summary": _field(result, "summary"),
        "metadata": _field(result, "metadata"),
        "raw": _field(result, "raw"),
        "conditions": {
            "permissions": list(context.permissions),
            "cache_policy": context.cache_policy,
        },
    }
    root = project_root
    if root is None:
        root, content = _unstaged(context.workspace_root, content)
    return write_observation(
        evidence_kind=evidence_kind,
        operation_id=context.operation_id,
        source=f"invocation:{context.operation_id}:{context.transport}",
        content=content,
        project_root=root,
    )


def _unstaged(
    workspace_root: Path, content: dict[str, Any]
) -> tuple[Path, dict[str, Any]]:
    """T19 R19.4 (G2): an invocation inside a staged scan attempt records into
    the live project's store (`staging.original_root`), never the temporary
    copy deleted with the attempt, with its path-bearing content mapped back
    to live paths. Outside staging the workspace root is unchanged."""
    from rush.engines.staging import active_staging, map_staged_path, remap_paths

    staging = active_staging()
    if staging is None or not workspace_root.is_relative_to(staging.staged_root):
        return workspace_root, content
    live = remap_paths(
        copy.deepcopy(content), staging.staged_root, staging.original_root
    )
    live["workspace_root"] = map_staged_path(
        str(workspace_root), staging.staged_root, staging.original_root
    )
    return staging.original_root, live


RepairOutcome = Literal["failed", "verified", "untested"]
RepairMatch = Literal["same", "changed", "incomplete"]

# §9.0 condition identity: runtime, platform, dependencies, config_digest and source_digest
# are all required for an exact-conditions comparison; a field missing on either side always
# yields match="incomplete", never a same-conditions warning.
_CONDITION_FIELDS = (
    "runtime",
    "platform",
    "dependencies",
    "config_digest",
    "source_digest",
)


def _conditions_complete(conditions: Mapping[str, Any]) -> bool:
    return all(field in conditions for field in _CONDITION_FIELDS)


def _repair_match(
    *,
    candidate_conditions: Mapping[str, Any],
    candidate_patch_hash: str | None,
    query_conditions: Mapping[str, Any],
    query_patch_hash: str | None,
) -> RepairMatch:
    """MC06.2/§9.0: same patch plus complete equal conditions is "same"; a field missing on
    either side is "incomplete" (never a same-conditions warning); anything else -- a
    different patch, or the same patch under changed conditions -- is "changed", which
    permits retrial."""
    if not (
        _conditions_complete(candidate_conditions)
        and _conditions_complete(query_conditions)
    ):
        return "incomplete"
    if (
        query_patch_hash is not None
        and candidate_patch_hash == query_patch_hash
        and all(
            candidate_conditions[field] == query_conditions[field]
            for field in _CONDITION_FIELDS
        )
    ):
        return "same"
    return "changed"


def record_attempt(
    *,
    project_root: Path,
    symptom: str,
    hypothesis: str,
    patch_hash: str | None,
    conditions: Mapping[str, Any],
    receipt_ref: str | None,
    behavior_ids: Sequence[str],
    outcome: RepairOutcome,
    affected_symbols: Sequence[str] = (),
    commit_message: str | None = None,
    access: Any = None,
) -> MemoryArtifact:
    """MC06.2: record one repair-episode attempt under exact §9.0 conditions.

    `receipt_ref` is the only evidence a check actually ran, and this function never
    executes anything to manufacture one -- an `outcome="untested"` hypothesis (recorded,
    not yet tried) is the only outcome allowed to omit it. A `commit_message` (e.g. a
    revert or a "fix:"-labelled commit) is stored as attribution text only: per §6, a
    revert/fix label never proves cause or upgrades `outcome` on its own -- only real
    receipted evidence does.
    """
    if outcome != "untested" and not receipt_ref:
        raise ValueError(
            f"record_attempt requires receipt_ref for outcome={outcome!r}; "
            "only outcome='untested' may omit it."
        )
    payload = {
        "schema_version": 1,
        "kind": "repair_episode",
        "symptom": symptom,
        "hypothesis": hypothesis,
        "patch_hash": patch_hash,
        "conditions": dict(conditions),
        "receipt_ref": receipt_ref,
        "behavior_ids": list(behavior_ids),
        "affected_symbols": list(affected_symbols),
        "outcome": outcome,
        "commit_message": commit_message,
    }
    subject: MemorySubject = "episodic" if outcome == "verified" else "failure"
    artifact = MemoryArtifact(
        id=str(uuid.uuid4()),
        family="experience",
        subject=subject,
        trust_tier=default_entry_tier("local_tool"),
        content=payload,
        source=f"repair_attempt:{symptom}",
        created_at=time.time(),
        content_hash=compute_content_signature(payload),
    )
    stored: MemoryArtifact = _authorized_write(
        project_root,
        artifact,
        lambda store, row, check: store.write(row, commit_check=check),
        open_store=lambda: TypedArtifactStore(project_root),
        access=access,
    )
    return stored


def recall_repair_episodes(
    *,
    project_root: Path,
    symptom: str,
    conditions: Mapping[str, Any],
    session_allowlist: Iterable[str] | None,
    patch_hash: str | None = None,
    access: MemoryAccess | None = None,
) -> dict[str, Any]:
    """MC06.2/MC06.3: recall prior repair episodes for `symptom`, bucketed by outcome.

    Read-only: a read-only view (a missing store creates nothing) and FTS matches -- never
    executes a command, never writes. 72-T01 (OD-3): every candidate goes through the
    shared decision (`retrieval.evaluate_artifact_visibility`, ordinary mode). A non-empty
    `session_allowlist` is the legacy access form (no owner filter); otherwise the memory
    policy at the default data root decides, and no grant fails closed (no default
    cross-session access). `patch_hash`, when given, is the proposed patch being considered
    for retrial; entries under `"failures"` carry a `"match"` state for it. Omitting it
    never produces a `match="same"` claim -- recall never asserts an exact repeat for a
    patch it wasn't asked to compare.

    72-T05 (R16): a supplied `access` decides the rows as is (its task context
    included); `None` keeps the default access above.
    """
    from rush.memory.retrieval import read_access, read_visible

    if access is None:
        access = read_access(project_root, "ask", session_allowlist)
    if access is None:
        return {
            "code": "E_PERMISSION",
            "message": "recall_repair_episodes requires a non-empty session_allowlist.",
            "failures": [],
            "verified_repairs": [],
            "untested_hypotheses": [],
        }

    failures: list[dict[str, Any]] = []
    verified_repairs: list[dict[str, Any]] = []
    untested_hypotheses: list[dict[str, Any]] = []
    found = read_visible(
        project_root, [("failure", symptom), ("episodic", symptom)], access=access
    )
    candidates = [artifact for batch in found for artifact in batch]
    for artifact in candidates:
        content = artifact.content
        if content.get("kind") != "repair_episode" or content.get("symptom") != symptom:
            continue
        entry: dict[str, Any] = {
            "id": artifact.id,
            "version": artifact.artifact_version,
            "hypothesis": content.get("hypothesis"),
            "patch_hash": content.get("patch_hash"),
            "conditions": content.get("conditions", {}),
            "receipt_ref": content.get("receipt_ref"),
            "behavior_ids": content.get("behavior_ids", []),
            "commit_message": content.get("commit_message"),
        }
        outcome = content.get("outcome")
        if outcome == "failed":
            entry["match"] = _repair_match(
                candidate_conditions=entry["conditions"],
                candidate_patch_hash=entry["patch_hash"],
                query_conditions=conditions,
                query_patch_hash=patch_hash,
            )
            if entry["match"] == "same":
                entry["warning"] = (
                    f"repeated failure: artifact {artifact.id} v{artifact.artifact_version} "
                    "already failed with this patch under these exact conditions."
                )
            failures.append(entry)
        elif outcome == "verified":
            entry["note"] = (
                f"verified alternative: artifact {artifact.id} "
                f"v{artifact.artifact_version} passed its regression check."
            )
            verified_repairs.append(entry)
        elif outcome == "untested":
            untested_hypotheses.append(entry)
    return {
        "code": "OK",
        "failures": failures,
        "verified_repairs": verified_repairs,
        "untested_hypotheses": untested_hypotheses,
    }


def prepare_memory(
    *,
    project_root: Path,
    symptom: str,
    conditions: Mapping[str, Any],
    behavior_ids: Sequence[str] = (),
    session_allowlist: Iterable[str] | None = None,
    access: MemoryAccess | None = None,
) -> dict[str, Any]:
    """MC06.3/MC07.3: read-only prepare pack -- bounded `failures`, `verified_repairs`,
    `untested_hypotheses`, `intent_evidence` and their `evidence_refs`. Executes no commands
    and never withholds or prohibits a patch; it only surfaces recorded evidence for a caller
    to decide what to try next. 72-T05 (R16): a supplied `access` decides both
    the episodes and the intent evidence.
    """
    recalled = recall_repair_episodes(
        project_root=project_root,
        symptom=symptom,
        conditions=conditions,
        session_allowlist=session_allowlist,
        access=access,
    )
    if behavior_ids:
        wanted = set(behavior_ids)
        for key in ("failures", "verified_repairs", "untested_hypotheses"):
            recalled[key] = [
                entry
                for entry in recalled[key]
                if wanted.intersection(entry.get("behavior_ids") or ())
            ]
    recalled["intent_evidence"] = _intent_evidence(
        project_root=project_root,
        behavior_ids=behavior_ids,
        session_allowlist=session_allowlist,
        access=access,
    )
    recalled["evidence_refs"] = [
        {"id": entry["id"], "version": entry["version"]}
        for key in (
            "failures",
            "verified_repairs",
            "untested_hypotheses",
            "intent_evidence",
        )
        for entry in recalled[key]
    ]
    return recalled


CauseState = Literal["candidate", "reproduced"]

DEFAULT_BEHAVIOR_NAMESPACE = "default"


def behavior_runtime_digest(*, runtime: Any, platform: Any) -> str:
    """MC10 §9.0: the runtime-platform digest half of the last-success key. Deliberately
    excludes code/config/dependency/engine -- those are separate comparison subjects
    (§9.0), never part of the pointer's identity, so a code-only change stays comparable
    under the same key while a genuinely different runtime/platform key is separate.
    """
    return compute_content_signature({"runtime": runtime, "platform": platform})


def record_behavior_success(
    *,
    project_root: Path,
    behavior_id: str,
    conditions: Mapping[str, Any],
    source: str,
    namespace: str = DEFAULT_BEHAVIOR_NAMESPACE,
    access: Any = None,
) -> MemoryArtifact:
    """MC10.2: record one genuinely executed pass of `behavior_id` and advance its
    namespace/behavior/runtime-platform last-success pointer, atomically, via
    `TypedArtifactStore.write_pass()` -- never a separate/parallel write path. This is the
    only function callers may use to advance that pointer; call it only for a real
    executed pass. A cache hit, skip, tag, or caller label has no other route to the
    pointer table and must never call this.
    """
    payload = {
        "schema_version": 1,
        "kind": "behavior_success",
        "behavior_id": behavior_id,
        "conditions": dict(conditions),
        "outcome": "pass",
    }
    artifact = MemoryArtifact(
        id=str(uuid.uuid4()),
        family="experience",
        subject="episodic",
        trust_tier=default_entry_tier("local_tool"),
        content=payload,
        source=source,
        created_at=time.time(),
        content_hash=compute_content_signature(payload),
    )
    digest = behavior_runtime_digest(
        runtime=conditions.get("runtime"), platform=conditions.get("platform")
    )
    stored: MemoryArtifact = _authorized_write(
        project_root,
        artifact,
        lambda store, row, check: store.write_pass(
            row,
            namespace=namespace,
            behavior_id=behavior_id,
            runtime_digest=digest,
            commit_check=check,
        ),
        open_store=lambda: TypedArtifactStore(project_root),
        access=access,
    )
    return stored


def compare_last_success(
    *,
    project_root: Path,
    behavior_id: str,
    conditions: Mapping[str, Any],
    namespace: str = DEFAULT_BEHAVIOR_NAMESPACE,
    historical: bool = False,
) -> dict[str, Any]:
    """MC10.3: compare current `conditions` to the recorded last-success pointer for
    `behavior_id`. Read-only -- never executes anything, never writes.

    Looks up the pointer under the exact runtime/platform digest first; with
    `historical=True` and no exact match, falls back to the most recent pointer under any
    digest and reports `environment_compatible=False` for it (§9.0: "incompatible
    environments appear separately"). `cause_state` always defaults to `"candidate"`; it
    is only `"reproduced"` when a prior `record_cause_experiment()` call already recorded
    a controlled-comparison result for this exact baseline -- correlation alone never
    upgrades it.

    72-T01 (OD-3): this function has no allowlist, so only the memory policy at the default
    data root authorizes the read (no grant: no baseline). The baseline pass and every
    cause experiment go through the shared decision (`retrieval.evaluate_artifact_
    visibility`, ordinary mode) over a read-only view; an archived, expired, tampered or
    foreign baseline is no baseline.
    """
    from rush.memory.retrieval import (
        evaluate_artifact_visibility,
        read_access,
        visible_artifacts,
    )
    from rush.memory.store import binding_verifier, payload_digest

    no_baseline: dict[str, Any] = {
        "baseline_ref": None,
        "code_changes": None,
        "config_changes": None,
        "dependency_changes": None,
        "engine_changes": None,
        "environment_compatible": True,
        "cause_state": "candidate",
    }
    access = read_access(project_root, "ask")
    if access is None:
        return no_baseline
    view, _state = TypedArtifactStore.open_readonly_view(project_root)
    if view is None:
        return no_baseline
    digest = behavior_runtime_digest(
        runtime=conditions.get("runtime"), platform=conditions.get("platform")
    )
    verifier = binding_verifier(view)

    def usable_text(found: tuple[str, int] | None) -> str | None:
        """The pointed-to version's bytes, or `None` unless the shared decision
        delivers that artifact as current and the version's payload binding holds.
        72-T01 D41: a `STATED` row's bytes also need `version_bytes == "bound"`
        (its bound current version with exactly the MAC-covered content)."""
        if found is None:
            return None
        row = view.get_current_row(found[0])
        decision = evaluate_artifact_visibility(
            view, row, access=access, verifier=verifier
        )
        if row is None or not decision.usable_as_current:
            return None
        payload = view.get_version_payload(*found)
        if payload is None:
            return None
        text, bound = payload
        if bound is not None and payload_digest(text) != bound:
            return None
        if (
            row["trust_tier"] == "STATED"
            and verifier.version_bytes(row, found[1], text) != "bound"
        ):
            return None
        return text

    try:
        pointer = view.get_behavior_success(
            namespace=namespace, behavior_id=behavior_id, runtime_digest=digest
        )
        raw = usable_text(pointer)
        if raw is None:
            pointer = None
        environment_compatible = True
        if pointer is None and historical:
            pointer = view.find_any_behavior_success(
                namespace=namespace, behavior_id=behavior_id
            )
            raw = usable_text(pointer)
            if raw is None:
                pointer = None
            environment_compatible = pointer is None
        causes = (
            visible_artifacts(
                view, view.search_rows("episodic", behavior_id), access=access
            )
            if pointer is not None
            else []
        )
    finally:
        view.close()

    # 72-T01 F2: recheck immediately before emit; a moved policy is no baseline.
    if pointer is None or raw is None or access.recheck() != "ok":
        return no_baseline

    artifact_id, artifact_version = pointer
    baseline_conditions: dict[str, Any] = {}
    parsed = json.loads(raw)
    if isinstance(parsed, dict):
        baseline_conditions = parsed.get("conditions") or {}

    def _delta(field: str) -> dict[str, Any] | None:
        baseline_value = baseline_conditions.get(field)
        current_value = conditions.get(field)
        if baseline_value == current_value:
            return None
        return {"baseline": baseline_value, "current": current_value}

    engine_changes = None
    if baseline_conditions.get("engine") != conditions.get(
        "engine"
    ) or baseline_conditions.get("engine_version") != conditions.get("engine_version"):
        engine_changes = {
            "baseline": {
                "engine": baseline_conditions.get("engine"),
                "engine_version": baseline_conditions.get("engine_version"),
            },
            "current": {
                "engine": conditions.get("engine"),
                "engine_version": conditions.get("engine_version"),
            },
        }

    baseline_ref = {"id": artifact_id, "version": artifact_version}
    cause_state: CauseState = "candidate"
    for artifact in causes:
        content = artifact.content
        if (
            content.get("kind") == "cause_experiment"
            and content.get("behavior_id") == behavior_id
            and content.get("cause_state") == "reproduced"
            and content.get("baseline_ref") == baseline_ref
        ):
            cause_state = "reproduced"
            break

    return {
        "baseline_ref": baseline_ref,
        "code_changes": _delta("code_digest"),
        "config_changes": _delta("config_digest"),
        "dependency_changes": _delta("dependency_digest"),
        "engine_changes": engine_changes,
        "environment_compatible": environment_compatible,
        "cause_state": cause_state,
    }


def record_cause_experiment(
    *,
    project_root: Path,
    behavior_id: str,
    baseline_ref: Mapping[str, Any],
    changed_factor: str,
    control_receipt_ref: str | None,
    outcome_changed: bool,
    source: str,
    access: Any = None,
) -> dict[str, Any]:
    """MC10.3/MC10.4: record one controlled-comparison experiment result. Only a real
    receipted control run (`control_receipt_ref` present) whose outcome actually changed
    relative to the baseline earns `cause_state="reproduced"`; a missing receipt (e.g. an
    unavailable engine whose control run never ran) or an unchanged outcome always stays
    `"candidate"` -- correlation is never enough on its own (§9.0).
    """
    reproduced = bool(control_receipt_ref) and outcome_changed
    cause_state: CauseState = "reproduced" if reproduced else "candidate"
    payload = {
        "schema_version": 1,
        "kind": "cause_experiment",
        "behavior_id": behavior_id,
        "baseline_ref": dict(baseline_ref),
        "changed_factor": changed_factor,
        "control_receipt_ref": control_receipt_ref,
        "outcome_changed": outcome_changed,
        "cause_state": cause_state,
    }
    artifact = MemoryArtifact(
        id=str(uuid.uuid4()),
        family="experience",
        subject="episodic",
        trust_tier=default_entry_tier("local_tool"),
        content=payload,
        source=source,
        created_at=time.time(),
        content_hash=compute_content_signature(payload),
    )
    stored: MemoryArtifact = _authorized_write(
        project_root,
        artifact,
        lambda store, row, check: store.write(row, commit_check=check),
        open_store=lambda: TypedArtifactStore(project_root),
        access=access,
    )
    return {
        "cause_state": cause_state,
        "artifact_id": stored.id,
        "artifact_version": stored.artifact_version,
    }


__all__ = [
    "DEFAULT_BEHAVIOR_NAMESPACE",
    "CauseState",
    "EvidenceKind",
    "MemoryWriteDenied",
    "RepairMatch",
    "RepairOutcome",
    "behavior_runtime_digest",
    "classify_capability_family",
    "compare_last_success",
    "prepare_memory",
    "recall_repair_episodes",
    "record_attempt",
    "record_behavior_success",
    "record_cause_experiment",
    "record_observation",
    "write_observation",
]
