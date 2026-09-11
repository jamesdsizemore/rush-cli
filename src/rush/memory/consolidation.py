"""MC03 §6.3 duplicate episode consolidation preserving originals, exceptions, contradictions
and trust (docs/phase-plans/MC03.md).

`consolidate_episodes()` groups `episodic` artifacts sharing one `symptom` by an exact
canonical `(symptom, condition, attempt, outcome)` tuple — never a fuzzy/semantic match, per
§6.3 ("semantic similarity may propose a group but cannot merge contradictory conditions
automatically"). The largest exact-duplicate group becomes the summary's repeated majority;
every other member (a differing condition, attempt, or outcome under the same symptom) is
recorded as a distinct `exceptions` entry, never folded into the repetition count. Every
original member row is left untouched — the derived summary is a new artifact referencing
member IDs/versions, not a replacement.
"""

from __future__ import annotations

import json
import time
import uuid
from collections.abc import Iterable
from typing import Any

from rush.memory.store import MemoryArtifact, TypedArtifactStore

_REQUIRED_FIELDS = ("symptom", "condition", "attempt", "outcome")


def _canonical_tuple(content: dict[str, Any]) -> tuple[str, str, str, str] | None:
    """`None` marks an episode missing one of the four required fields — skipped, never
    raised, so one malformed episode can't abort grouping the rest."""
    if not all(field in content for field in _REQUIRED_FIELDS):
        return None
    canonical_condition = json.dumps(
        content["condition"], sort_keys=True, separators=(",", ":")
    )
    return (
        str(content["symptom"]),
        canonical_condition,
        str(content["attempt"]),
        str(content["outcome"]),
    )


def consolidate_episodes(
    store: TypedArtifactStore,
    *,
    symptom: str,
    session_allowlist: Iterable[str] | None,
    source: str = "consolidation",
) -> dict[str, Any]:
    """Groups `episodic` members matching `symptom` and writes one derived summary artifact.

    Returns `{"code": ...}`: `"E_PERMISSION"` for an empty `session_allowlist` (fail-closed,
    matching `TypedArtifactStore.recall()`'s existing precedent), `"E_INPUT"` when no visible
    episode matches `symptom`, else `"OK"` with the summary under `"summary"`.
    """
    allowed_sources = set(session_allowlist or ())
    if not allowed_sources:
        return {
            "code": "E_PERMISSION",
            "message": "memory consolidate requires a non-empty session_allowlist "
            "(fail-closed, no default cross-session access).",
        }

    groups: dict[tuple[str, str, str, str], list[MemoryArtifact]] = {}
    for artifact in store.search("episodic", symptom):
        if artifact.source not in allowed_sources:
            continue
        canonical = _canonical_tuple(artifact.content)
        if canonical is None or canonical[0] != symptom:
            continue
        groups.setdefault(canonical, []).append(artifact)

    if not groups:
        return {
            "code": "E_INPUT",
            "message": f"no episodes found for symptom {symptom!r}",
        }

    majority_tuple, majority_members = max(groups.items(), key=lambda kv: len(kv[1]))
    exception_members = [
        artifact
        for canonical, members in groups.items()
        if canonical != majority_tuple
        for artifact in members
    ]
    all_members = majority_members + exception_members

    trust_tiers = {artifact.trust_tier for artifact in all_members}
    # §6.3: "repetition/model agreement never promotes it" — the summary inherits the
    # members' own trust tier when they agree; a mixed group or a STATED majority (which
    # `write()` refuses to insert directly) falls back to "DERIVED", never upgraded.
    summary_trust = next(iter(trust_tiers)) if len(trust_tiers) == 1 else "DERIVED"
    if summary_trust == "STATED":
        summary_trust = "DERIVED"

    summary_content = {
        "kind": "consolidated_episode_summary",
        "symptom": symptom,
        "common_condition": json.loads(majority_tuple[1]),
        "common_attempt": majority_tuple[2],
        "common_outcome": majority_tuple[3],
        "repetition": len(majority_members),
        "member_ids": sorted(artifact.id for artifact in all_members),
        "member_versions": {
            artifact.id: artifact.artifact_version for artifact in all_members
        },
        "exceptions": [
            {
                "id": artifact.id,
                "version": artifact.artifact_version,
                "condition": artifact.content.get("condition"),
                "attempt": artifact.content.get("attempt"),
                "outcome": artifact.content.get("outcome"),
            }
            for artifact in exception_members
        ],
    }
    summary = store.write(
        MemoryArtifact(
            id=str(uuid.uuid4()),
            family="experience",
            subject="episodic",
            trust_tier=summary_trust,
            content=summary_content,
            source=source,
            created_at=time.time(),
        )
    )
    return {
        "code": "OK",
        "summary": {
            "id": summary.id,
            "version": summary.artifact_version,
            "trust_tier": summary.trust_tier,
            **summary.content,
        },
    }


def summary_is_current(
    store: TypedArtifactStore, summary_content: dict[str, Any]
) -> bool:
    """True iff every member referenced in a stored summary's `member_versions` still has the
    exact `artifact_version` it had when the summary was built (§6.3: "an edited member
    invalidates the summary")."""
    for member_id, version in summary_content.get("member_versions", {}).items():
        current = store.get_current(member_id)
        if current is None or current.artifact_version != version:
            return False
    return True
