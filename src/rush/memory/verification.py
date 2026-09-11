"""MC05 (Phase 63) `verify-attempt`: a real memory operation over the existing patch sandbox.

Applies a caller-declared patch inside an isolated `PatchSandboxManager` worktree,
runs the existing `PatchVerifier.verify_patch()` against a caller-declared
`PatchContract`, and finalizes a truthful `sandbox_verification` observation
through `rush.memory.experience`. Never promotes the patch, never mutates the
source checkout, never auto-commits or auto-rolls-back source, and always tears
the sandbox down. Dirty-root precondition, drift, failed checks, and unavailable
commands are explicit non-success results -- never inferred success.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from rush.memory.experience import write_observation
from rush.memory.store import MemoryArtifact, TypedArtifactStore
from rush.patch.applier import PatchApplier
from rush.patch.contracts import (
    DirtyWorkspaceError,
    PatchContract,
    PatchVerificationError,
    PatchVerificationResult,
    VerifierCommandPlan,
)
from rush.patch.sandbox import PatchSandboxManager
from rush.patch.verifier import PatchVerifier
from rush.permissions import ExecutionPermissions, check_permissions

VerifyAttemptOutcome_Kind = str  # "completed" | "failed" | "unavailable" | "denied"

# Permissions a caller may declare as required by its own check commands.
# `cache_write`, `artifact_write`, and `build` are always required regardless of
# declaration; never inferred from the command text itself.
_DECLARABLE_PERMISSION_NAMES = frozenset({"network", "download", "slow", "browser"})


@dataclass(frozen=True)
class VerifyAttemptOutcome:
    """Truthful, non-promoting outcome of one `verify-attempt` call."""

    attempt_id: str
    behavior_ids: tuple[str, ...]
    outcome: VerifyAttemptOutcome_Kind
    summary: str
    result: PatchVerificationResult | None = None


def parse_patch_contract(
    payload: dict[str, Any], *, default_sandbox_path: Path
) -> PatchContract:
    """Build a `PatchContract` from a caller-declared JSON payload. Never inferred."""
    required_raw = payload.get("required_commands") or ()
    commands = tuple(
        VerifierCommandPlan(
            command=tuple(str(c) for c in cmd["command"]),
            cwd_relative=str(cmd.get("cwd_relative", ".")),
            expected_exit_code=int(cmd.get("expected_exit_code", 0)),
            timeout_seconds=float(cmd.get("timeout_seconds", 60.0)),
        )
        for cmd in required_raw
    )
    return PatchContract(
        base_commit=str(payload.get("base_commit", "")),
        base_tree_digest=str(payload.get("base_tree_digest", "")),
        patch_content_digest=str(payload.get("patch_content_digest", "")),
        sandbox_path=Path(payload.get("sandbox_path", default_sandbox_path)),
        required_commands=commands,
        config_digest=str(payload.get("config_digest", "")),
        review_class=str(payload.get("review_class", "standard")),
    )


def verify_attempt(
    *,
    attempt_id: str,
    behavior_ids: tuple[str, ...],
    repo_root: Path,
    contract: PatchContract,
    patch: str,
    granted: ExecutionPermissions,
    declared_permission_names: tuple[str, ...] = (),
) -> VerifyAttemptOutcome:
    """Apply `patch` in an isolated sandbox and run `PatchVerifier.verify_patch()`.

    Fail-closed: requires `cache_write`, `artifact_write`, `build`, plus every
    permission the caller explicitly declares its checks need. Never infers a
    permission from the declared commands or from memory.
    """
    unknown = set(declared_permission_names) - _DECLARABLE_PERMISSION_NAMES
    if unknown:
        return VerifyAttemptOutcome(
            attempt_id=attempt_id,
            behavior_ids=behavior_ids,
            outcome="denied",
            summary=f"verify-attempt denied: unknown declared permission(s) {sorted(unknown)}.",
        )

    required = ExecutionPermissions(
        cache_write=True,
        artifact_write=True,
        build=True,
        network="network" in declared_permission_names,
        download="download" in declared_permission_names,
        slow="slow" in declared_permission_names,
        browser="browser" in declared_permission_names,
    )
    allowed, missing = check_permissions(required, granted)
    if not allowed:
        return VerifyAttemptOutcome(
            attempt_id=attempt_id,
            behavior_ids=behavior_ids,
            outcome="denied",
            summary=f"verify-attempt denied: missing {', '.join(missing)}.",
        )

    manager = PatchSandboxManager(repo_root=repo_root)
    try:
        sandbox_path = manager.create_sandbox()
    except DirtyWorkspaceError as exc:
        return VerifyAttemptOutcome(
            attempt_id=attempt_id,
            behavior_ids=behavior_ids,
            outcome="denied",
            summary=f"verify-attempt refused: {exc}",
        )

    try:
        applied, apply_summary = PatchApplier.apply_patch_to_dir(sandbox_path, patch)
        if not applied:
            return VerifyAttemptOutcome(
                attempt_id=attempt_id,
                behavior_ids=behavior_ids,
                outcome="failed",
                summary=f"verify-attempt patch application failed: {apply_summary}",
            )

        verifier = PatchVerifier(sandbox_path, contract=contract)
        try:
            _ok, summary = verifier.verify_patch()
        except PatchVerificationError as exc:
            return VerifyAttemptOutcome(
                attempt_id=attempt_id,
                behavior_ids=behavior_ids,
                outcome="failed",
                summary=f"verify-attempt rejected: {exc}",
            )

        result = verifier.last_result
        outcome_kind: VerifyAttemptOutcome_Kind = (
            result.outcome if result is not None else "failed"
        )
        if result is not None:
            write_observation(
                evidence_kind="sandbox_verification",
                operation_id="memory.verify_attempt",
                source=f"verify_attempt:{attempt_id}",
                content={
                    "attempt_id": attempt_id,
                    "behavior_ids": list(behavior_ids),
                    "base_commit": contract.base_commit,
                    "config_digest": contract.config_digest,
                    "review_class": contract.review_class,
                    "outcome": result.outcome,
                    "summary": summary,
                    "executed_commands": list(result.executed_commands),
                    "passed_count": result.passed_count,
                },
                project_root=repo_root,
            )
        return VerifyAttemptOutcome(
            attempt_id=attempt_id,
            behavior_ids=behavior_ids,
            outcome=outcome_kind,
            summary=summary,
            result=result,
        )
    finally:
        manager.cleanup_sandbox(sandbox_path)


# MC09: evidence kinds `plan_checks` ranks by. Anything else (`sandbox_verification`,
# `continuity_checkpoint`) is irrelevant to check ordering and is ignored.
_RELEVANT_EVIDENCE_KINDS = frozenset(
    {"tests_contracts", "source_graph", "security_dependency"}
)


def _fts_phrase(text: str) -> str:
    """Quotes `text` as one FTS5 phrase (mirrors `intent._fts_phrase`) so a hyphenated
    target/dependency identifier can't be misread as the `-` NOT operator."""
    return '"' + text.replace('"', '""') + '"'


def _plan_evidence(
    store: TypedArtifactStore, target_ids: Sequence[str]
) -> list[tuple[MemoryArtifact, dict[str, Any]]]:
    """MC09.3: read-only lookup of already-recorded `episodic` observations (written
    through the existing `write_observation` -- never a parallel store) whose content
    mentions one of `target_ids`. Deduplicated by (id, version) since one artifact can
    match more than one target's search."""
    seen: dict[tuple[str, int], tuple[MemoryArtifact, dict[str, Any]]] = {}
    for target_id in target_ids:
        for artifact in store.search("episodic", _fts_phrase(target_id)):
            key = (artifact.id, artifact.artifact_version)
            if key not in seen and artifact.content.get("evidence_kind") in (
                _RELEVANT_EVIDENCE_KINDS
            ):
                seen[key] = (artifact, artifact.content)
    return list(seen.values())


def plan_checks(
    *,
    project_root: Path,
    changed_targets: Sequence[Mapping[str, Any]],
    required_checks: Sequence[Mapping[str, Any]],
    environment: Mapping[str, Any],
) -> dict[str, Any]:
    """MC09.2/.3: rank `required_checks` by real evidence strength -- reordering only,
    never dropping or adding required membership.

    Evidence ranks (lower sorts first): an observed regression -- a prior `tests_contracts`
    observation that actually failed against a changed target -- or a version-bound
    security/dependency/license finding invalidated by a changed dependency version (0); a
    real measured-coverage execution against a changed target (1); a structural-only
    relation from graph/static evidence, e.g. blast-radius or api-diff (2 -- never promoted
    to rank 1, which would report a heuristic as measured coverage); no evidence at all,
    i.e. only ever configured (3). Ties break on measured duration (missing sorts last),
    then original configured position. A surviving mutation observation, or a structural
    relation naming no required check (a dynamic consumer), is never invented as coverage
    -- both surface only as an explicit `coverage_gaps` entry.
    """
    target_versions = {str(t["id"]): t.get("version") for t in changed_targets}
    available_engines = set(environment.get("available_engines", ()))
    store = TypedArtifactStore(project_root)

    coverage_gaps: list[dict[str, Any]] = []
    seen_gaps: set[tuple[str, str]] = set()

    def _add_gap(
        target_id: str, check_id: str | None, reason: str, ref: dict[str, Any]
    ) -> None:
        gap_key = (check_id or "", target_id)
        if gap_key in seen_gaps:
            return
        seen_gaps.add(gap_key)
        coverage_gaps.append(
            {
                "target_id": target_id,
                "check_id": check_id,
                "reason": reason,
                "ref": ref,
            }
        )

    by_check: dict[str, list[tuple[MemoryArtifact, dict[str, Any]]]] = {}
    for artifact, content in _plan_evidence(store, list(target_versions)):
        check_id = content.get("check_id")
        if check_id:
            by_check.setdefault(str(check_id), []).append((artifact, content))
            continue
        # No check_id: a structural relation naming a target with no required check to
        # exercise it -- an unmeasured dynamic consumer, never invented as coverage.
        ref = {"id": artifact.id, "version": artifact.artifact_version}
        for target_id in set(content.get("targets", ())) & target_versions.keys():
            _add_gap(
                target_id,
                None,
                "dynamic consumer relation is structural only (graph heuristic); no "
                "measured coverage exists for it.",
                ref,
            )

    required_ids = list(dict.fromkeys(str(c["id"]) for c in required_checks))
    entries: list[dict[str, Any]] = []
    for index, raw_check in enumerate(required_checks):
        check_id = str(raw_check["id"])
        rank = 3
        reasons: list[str] = []
        refs: list[dict[str, Any]] = []
        for artifact, content in by_check.get(check_id, ()):
            ref = {"id": artifact.id, "version": artifact.artifact_version}
            evidence_kind = content["evidence_kind"]
            targets_hit = set(content.get("targets", ())) & target_versions.keys()
            if evidence_kind == "tests_contracts":
                metadata = content.get("metadata") or {}
                if (
                    content.get("operation_id") == "mutation"
                    and metadata.get("killed") is False
                ):
                    for target_id in targets_hit:
                        _add_gap(
                            target_id,
                            check_id,
                            "mutation observation survived; not counted as measured "
                            "coverage.",
                            ref,
                        )
                    continue
                if not targets_hit:
                    continue
                if content.get("status") in ("fail", "error"):
                    if rank > 0:
                        rank, reasons = 0, []
                    reasons.append(
                        f"observed regression: {check_id} previously failed against a "
                        "changed target."
                    )
                    refs.append(ref)
                elif rank > 1:
                    rank = 1
                    reasons = [
                        (
                            f"measured coverage: {check_id} previously executed against "
                            "a changed target."
                        )
                    ]
                    refs.append(ref)
                else:
                    refs.append(ref)
            elif evidence_kind == "source_graph":
                if not targets_hit:
                    continue
                if rank > 2:
                    rank = 2
                    reasons = [
                        (
                            f"structural relation only (graph heuristic) for {check_id}; "
                            "never counted as measured coverage."
                        )
                    ]
                refs.append(ref)
            else:  # security_dependency
                dependency = (content.get("metadata") or {}).get("dependency") or {}
                dep_name = dependency.get("name")
                recorded_version = dependency.get("version")
                current_version = (
                    target_versions.get(str(dep_name)) if dep_name else None
                )
                if dep_name in target_versions and current_version != recorded_version:
                    if rank > 0:
                        rank, reasons = 0, []
                    reasons.append(
                        f"security/license finding for {dep_name!r} reopened: version "
                        f"changed {recorded_version!r} -> {current_version!r}."
                    )
                    refs.append(ref)
        engine = raw_check.get("engine")
        availability = "available"
        if engine and engine not in available_engines:
            availability = "unresolved"
            reasons.append(f"required engine unavailable: {engine!r}.")
        entries.append(
            {
                "ids": [check_id],
                "argv": list(raw_check.get("argv", ())),
                "cwd": raw_check.get("cwd", "."),
                "environment": dict(raw_check.get("environment", {})),
                "engine": engine,
                "rank": rank,
                "availability": availability,
                "reasons": reasons,
                "refs": refs,
                "_duration": raw_check.get("duration_seconds"),
                "_index": index,
            }
        )

    # MC09.2: deduplicate exact argv/cwd/environment identity -- merges duplicate run
    # entries under one canonical check, never drops any id from `required_ids` above.
    merged: dict[tuple[Any, ...], dict[str, Any]] = {}
    merge_order: list[tuple[Any, ...]] = []
    for entry in entries:
        key = (
            tuple(entry["argv"]),
            entry["cwd"],
            tuple(sorted(entry["environment"].items())),
        )
        if key not in merged:
            merged[key] = entry
            merge_order.append(key)
            continue
        existing = merged[key]
        existing["ids"].extend(entry["ids"])
        existing["refs"].extend(entry["refs"])
        if entry["rank"] < existing["rank"]:
            existing["reasons"] = entry["reasons"] + existing["reasons"]
            existing["rank"] = entry["rank"]
        else:
            existing["reasons"].extend(entry["reasons"])
        if entry["availability"] != "available":
            existing["availability"] = entry["availability"]
        existing["_index"] = min(existing["_index"], entry["_index"])
        if entry["_duration"] is not None and (
            existing["_duration"] is None or entry["_duration"] < existing["_duration"]
        ):
            existing["_duration"] = entry["_duration"]

    checks = [merged[key] for key in merge_order]
    checks.sort(
        key=lambda e: (
            e["rank"],
            e["_duration"] if e["_duration"] is not None else float("inf"),
            e["_index"],
        )
    )
    for entry in checks:
        entry.pop("_index", None)
        entry.pop("_duration", None)

    return {
        "checks": checks,
        "required_ids": required_ids,
        "coverage_gaps": coverage_gaps,
    }


__all__ = [
    "VerifyAttemptOutcome",
    "parse_patch_contract",
    "plan_checks",
    "verify_attempt",
]
