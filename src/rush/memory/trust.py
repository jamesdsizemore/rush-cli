"""Trust tier taxonomy and write-promotion rule (Phase 61 §6.2).

`default_entry_tier` classifies a newly-written artifact by origin (never `STATED`);
`evaluate_promotion` composes the ALLOW/REDACT/BLOCK screen, a regex pre-filter against
instruction-override/exfiltration patterns, a schema-completeness check, a grounding check
(`resolve_symbol_ref`), and a user-stated/corroboration gate (`count_corroboration`) before a
record may be promoted to `STATED`; `evaluate_conflict` reconciles a new record against an
existing `STATED` row sharing `(subject, symbol_ref)` at write time (§3.2.2).
"""

from __future__ import annotations

import ast
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Literal

from rush.safety.redactor import SecretRedactor

if TYPE_CHECKING:
    from rush.memory.store import MemoryArtifact, MemorySubject, TrustTier

PromotionDenialReason = Literal[
    "failed_allow_redact_block_screen",
    "failed_regex_prefilter",
    "incomplete_schema_fields",
    "failed_grounding_check",
    "insufficient_corroboration",
]


@dataclass(frozen=True)
class PromotionResult:
    promoted: bool
    new_tier: "TrustTier"
    denial_reason: PromotionDenialReason | None = None
    corroboration_count: int = 0


_INSTRUCTION_OVERRIDE_PATTERNS = [
    re.compile(r"(?i)ignore (all )?(previous|prior) instructions"),
    re.compile(r"(?i)disregard (all )?(previous|prior) instructions"),
    re.compile(r"(?i)reveal (your |the )?system prompt"),
    re.compile(r"(?i)exfiltrate"),
    re.compile(r"(?i)you are now (in )?(developer|dan) mode"),
]

_REQUIRED_FIELDS = (
    "id",
    "family",
    "subject",
    "trust_tier",
    "content",
    "source",
    "created_at",
)


def default_entry_tier(
    source_kind: Literal["local_tool", "cross_tool_handoff", "human_derived"],
) -> "TrustTier":
    """Maps a write's origin to its entry trust tier. Never returns `STATED` (T-61.08)."""
    if source_kind == "cross_tool_handoff":
        return "IMPORTED"
    if source_kind == "local_tool":
        return "EXTERNAL_WRITE"
    return "DERIVED"  # human_derived: inferred from a human interaction, not directly stated


def _allow_redact_block_screen(content: dict) -> Literal["ALLOW", "REDACT", "BLOCK"]:
    """Rush-own ALLOW/REDACT/BLOCK screen (idea-only per hindsight, no hindsight code copied).

    Lazy/function-local import: see `rush.memory.store._inspect_text_for_trojan_chars` — importing
    `rush.hook.trojan_source` at module load time drags in the whole `rush.hook` package, which
    transitively imports back to `rush.memory.store`/`rush.memory.trust`, a circular import.
    """
    from rush.hook.trojan_source import BIDI_CHARS

    text = json.dumps(content, ensure_ascii=False)
    if any(ch in text for ch in BIDI_CHARS):
        return "BLOCK"
    if SecretRedactor.redact_text(text) != text:
        return "REDACT"
    return "ALLOW"


def _fails_regex_prefilter(content: dict) -> bool:
    """Rush-own regex pre-filter against instruction-override/exfiltration patterns."""
    text = json.dumps(content, ensure_ascii=False)
    return any(pattern.search(text) for pattern in _INSTRUCTION_OVERRIDE_PATTERNS)


def _incomplete_schema(artifact: "MemoryArtifact") -> bool:
    """True if any non-optional `MemoryArtifact` field is unset/empty."""
    for field_name in _REQUIRED_FIELDS:
        value = getattr(artifact, field_name)
        if value is None:
            return True
        if isinstance(value, str) and not value.strip():
            return True
        if isinstance(value, dict) and not value:
            return True
    return False


def resolve_symbol_ref(symbol_ref: str, project_root: Path) -> bool:
    """Confirms `symbol_ref` ('path/to/file.py::Symbol') names a real file + top-level def/class.

    New, dedicated code — not a reuse of `GroundingVerifier` (which only resolves imports).
    """
    if "::" not in symbol_ref:
        return False
    path_part, symbol_name = symbol_ref.split("::", 1)
    file_path = (Path(project_root) / path_part).resolve()
    if not file_path.is_file():
        return False
    try:
        tree = ast.parse(file_path.read_text(encoding="utf-8"))
    except (SyntaxError, UnicodeDecodeError, OSError):
        return False
    return any(
        isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
        and node.name == symbol_name
        for node in tree.body
    )


def count_corroboration(
    subject: "MemorySubject",
    symbol_ref: str | None,
    candidate_sources: list[str],
) -> int:
    """Counts distinct sources among pending (non-`STATED`) candidates sharing `(subject, symbol_ref)`.

    New, dedicated code — not a reuse of `rush.score.consensus.MultiModelConsensusReconciler`
    (its grouping key is hardcoded to `(file_path, line_number, rule_id)`, incompatible with an
    `Optional` `symbol_ref`). Grouping by `(subject, symbol_ref)` is the caller's responsibility
    (it supplies the already-filtered `candidate_sources` pool); this counts distinct sources.
    """
    del (
        subject,
        symbol_ref,
    )  # grouping is caller-side; kept for signature/documentation clarity
    return len(set(candidate_sources))


def evaluate_promotion(
    artifact: "MemoryArtifact",
    *,
    user_stated: bool,
    candidate_sources: list[str] | None = None,
    project_root: Path | None = None,
) -> PromotionResult:
    """Composes the ALLOW/REDACT/BLOCK screen, regex pre-filter, schema, grounding, and
    user-stated/corroboration checks, in that order (§6.2, extended per §3.2.2)."""
    if _allow_redact_block_screen(artifact.content) == "BLOCK":
        return PromotionResult(
            promoted=False,
            new_tier=artifact.trust_tier,
            denial_reason="failed_allow_redact_block_screen",
        )

    if _fails_regex_prefilter(artifact.content):
        return PromotionResult(
            promoted=False,
            new_tier=artifact.trust_tier,
            denial_reason="failed_regex_prefilter",
        )

    if _incomplete_schema(artifact):
        return PromotionResult(
            promoted=False,
            new_tier=artifact.trust_tier,
            denial_reason="incomplete_schema_fields",
        )

    if artifact.symbol_ref is not None:
        root = project_root if project_root is not None else Path.cwd()
        if not resolve_symbol_ref(artifact.symbol_ref, root):
            return PromotionResult(
                promoted=False,
                new_tier=artifact.trust_tier,
                denial_reason="failed_grounding_check",
            )

    if user_stated:
        return PromotionResult(promoted=True, new_tier="STATED", corroboration_count=0)

    count = count_corroboration(
        artifact.subject, artifact.symbol_ref, candidate_sources or []
    )
    if count >= 2:
        return PromotionResult(
            promoted=True, new_tier="STATED", corroboration_count=count
        )
    return PromotionResult(
        promoted=False,
        new_tier=artifact.trust_tier,
        denial_reason="insufficient_corroboration",
        corroboration_count=count,
    )


def _is_explicit_contradiction(new_content: dict, existing_content: dict) -> bool:
    """A shared boolean field that flips value is an explicit contradiction of the old fact."""
    for key, existing_value in existing_content.items():
        if key not in new_content:
            continue
        new_value = new_content[key]
        if (
            isinstance(existing_value, bool)
            and isinstance(new_value, bool)
            and existing_value != new_value
        ):
            return True
    return False


def evaluate_conflict(
    new_artifact: "MemoryArtifact", existing_stated_artifact: "MemoryArtifact"
) -> Literal["add", "update", "delete", "none"]:
    """LLM-free reconciliation of a new record against an existing `STATED` row (§3.2.2 item 2)."""
    if new_artifact.content == existing_stated_artifact.content:
        return "none"
    if _is_explicit_contradiction(
        new_artifact.content, existing_stated_artifact.content
    ):
        return "delete"
    if new_artifact.symbol_ref == existing_stated_artifact.symbol_ref:
        return "update"
    return "add"
