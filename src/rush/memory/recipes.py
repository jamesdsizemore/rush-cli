"""MC08 (Phase 63) recipes: an adaptation pattern resolved against *current* project source,
never a frozen snapshot -- reading `helper_ref` straight off disk every `resolve_recipe()`
call is what proves the returned implementation is today's, not the one recorded.

One `skill_pattern` artifact per `recipe_id`, mutated in place through
`TypedArtifactStore.update_content()`'s existing compare-and-swap path -- never a parallel
store (mirrors MC07 `intent.py`). `required_symbols`, `required_dependencies` and
`required_config_digest` are applicability predicates (MC08.2): every declared one must
match or the recipe is `usable=False` with a named reason; an empty list/dict/`None`
imposes no predicate. `record_recipe_outcome()` never accepts a caller-declared `passed`
value -- it is derived only from resolving a real `sandbox_verification` receipt (MC05's
`verify_attempt`), so a bare `passed=True` claim is structurally impossible, and one passing
outcome never widens `required_symbols`/`required_dependencies`, drops `checks`/
`exceptions`, or promotes `trust_tier` toward `STATED` (MC08 authority rule).
"""

from __future__ import annotations

import ast
import hashlib
import time
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from rush.memory.store import (
    MemoryArtifact,
    TypedArtifactStore,
    VersionConflictError,
    compute_content_signature,
)
from rush.memory.trust import default_entry_tier

_VERIFIER_RECOGNIZED_OUTCOMES = frozenset({"completed", "failed", "unavailable"})
_VERIFIER_PASS_OUTCOMES = frozenset({"completed"})


def _find_node(body: Sequence[ast.stmt], parts: Sequence[str]) -> ast.AST | None:
    name = parts[0]
    for node in body:
        if (
            isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
            and node.name == name
        ):
            if len(parts) == 1:
                return node
            return _find_node(node.body, parts[1:])
    return None


def resolve_symbol_source(
    project_root: Path, symbol_ref: Mapping[str, Any] | None
) -> tuple[str, str] | None:
    """Reads `symbol_ref` (`{"path": relative-file, "symbol": dotted-name}`) straight off
    disk -- never a cached/graph snapshot -- and returns its exact current source text and
    SHA-256 hash, or `None` if the path/symbol no longer resolves.

    ponytail: single-file AST lookup, not a cross-file graph resolver; upgrade to
    `rush.codegraph` if a recipe ever needs a symbol defined via re-export/inheritance.
    """
    if not symbol_ref:
        return None
    path = symbol_ref.get("path")
    symbol = symbol_ref.get("symbol")
    if not path or not symbol:
        return None
    try:
        file_path = (project_root / str(path)).resolve()
        file_path.relative_to(project_root.resolve())
    except ValueError:
        return None
    if not file_path.is_file():
        return None
    try:
        text = file_path.read_text(encoding="utf-8")
        tree = ast.parse(text)
    except (OSError, SyntaxError, ValueError):
        return None
    node = _find_node(tree.body, str(symbol).split("."))
    if node is None:
        return None
    segment = ast.get_source_segment(text, node)
    if segment is None:
        return None
    return segment, hashlib.sha256(segment.encode("utf-8")).hexdigest()


def _verifier_outcome(content: Mapping[str, Any]) -> tuple[bool, bool]:
    """`(recognized, passed)` for one resolved receipt artifact's content -- mirrors
    `intent._execution_result`, scoped to MC05's `sandbox_verification` evidence kind so a
    receipt from an unrelated observation can never stand in for real patch verification."""
    if content.get("evidence_kind") != "sandbox_verification":
        return False, False
    outcome = content.get("outcome")
    if outcome in _VERIFIER_RECOGNIZED_OUTCOMES:
        return True, outcome in _VERIFIER_PASS_OUTCOMES
    return False, False


def record_recipe(
    *,
    project_root: Path,
    recipe_id: str,
    purpose: str | None = None,
    helper_ref: Mapping[str, Any] | None = None,
    required_symbols: Sequence[Mapping[str, Any]] | None = None,
    required_dependencies: Mapping[str, str] | None = None,
    required_config_digest: str | None = None,
    checks: Sequence[Mapping[str, Any]] | None = None,
    exceptions: Sequence[str] | None = None,
    expected_version: int | None = None,
) -> dict[str, Any]:
    """MC08.2: create a new recipe, or re-record an existing one (compare-and-swap on
    `expected_version`, mirrors `intent.record_intent`). `helper_ref` is required for a
    brand-new `recipe_id` and must resolve on disk right now -- its exact current source and
    hash are captured as the recipe's baseline for future staleness comparison. Any field
    omitted on a re-record defaults to its currently-stored value, never silently cleared;
    prior `outcomes` are always carried forward.
    """
    store = TypedArtifactStore(project_root)
    current = store.get_current(recipe_id)
    if current is None:
        if expected_version is not None:
            return {
                "code": "E_VERSION",
                "message": f"recipe {recipe_id!r} does not exist yet; omit expected_version.",
            }
        if not helper_ref:
            return {
                "code": "E_INPUT",
                "message": f"recipe {recipe_id!r} is new; helper_ref is required.",
            }
    else:
        if expected_version is None or expected_version != current.artifact_version:
            return {
                "code": "E_VERSION",
                "message": (
                    f"recipe {recipe_id!r} already exists at version "
                    f"{current.artifact_version}; expected_version must match to re-record."
                ),
            }
        prior = current.content
        if helper_ref is None:
            helper_ref = prior.get("helper_ref")
        if purpose is None:
            purpose = prior.get("purpose")
        if required_symbols is None:
            required_symbols = prior.get("required_symbols", [])
        if required_dependencies is None:
            required_dependencies = prior.get("required_dependencies", {})
        if required_config_digest is None:
            required_config_digest = prior.get("required_config_digest")
        if checks is None:
            checks = prior.get("checks", [])
        if exceptions is None:
            exceptions = prior.get("exceptions", [])

    resolved = resolve_symbol_source(project_root, helper_ref)
    if resolved is None:
        return {
            "code": "E_INPUT",
            "message": f"recipe {recipe_id!r}: helper_ref {helper_ref!r} does not resolve.",
        }
    helper_source, helper_source_hash = resolved

    payload: dict[str, Any] = {
        "schema_version": 1,
        "kind": "recipe",
        "recipe_id": recipe_id,
        "purpose": purpose,
        "helper_ref": dict(helper_ref) if helper_ref else None,
        "helper_source": helper_source,
        "helper_source_hash": helper_source_hash,
        "required_symbols": [dict(s) for s in (required_symbols or ())],
        "required_dependencies": dict(required_dependencies or {}),
        "required_config_digest": required_config_digest,
        "checks": [dict(c) for c in (checks or ())],
        "exceptions": list(exceptions or ()),
        "outcomes": list(current.content.get("outcomes", [])) if current else [],
    }

    if current is None:
        artifact = MemoryArtifact(
            id=recipe_id,
            family="skill",
            subject="skill_pattern",
            trust_tier=default_entry_tier("local_tool"),
            content=payload,
            source=f"recipe:{recipe_id}",
            created_at=time.time(),
            content_hash=compute_content_signature(payload),
        )
        version = store.write(artifact).artifact_version
    else:
        try:
            store.update_content(recipe_id, payload, expected_version=expected_version)
        except VersionConflictError as exc:
            return {"code": exc.code, "message": str(exc)}
        version = current.artifact_version + 1

    return {
        "code": "OK",
        "id": recipe_id,
        "version": version,
        "recipe_id": recipe_id,
        "purpose": purpose,
        "helper_ref": payload["helper_ref"],
        "helper_source_hash": helper_source_hash,
        "checks": payload["checks"],
        "exceptions": payload["exceptions"],
    }


def resolve_recipe(
    *,
    project_root: Path,
    recipe_id: str,
    current_dependencies: Mapping[str, str] | None = None,
    current_config_digest: str | None = None,
) -> dict[str, Any]:
    """MC08.2: read-only -- resolves `recipe_id`'s applicability against source on disk
    *right now*, never a cached/recorded snapshot. `required_symbols`,
    `required_dependencies` and `required_config_digest` are declared predicates; every one
    that is non-empty/non-`None` must match or `usable=False` with a distinct, named
    `reason`. `checks`/`exceptions` are always returned unchanged regardless of `usable` --
    staleness never hides what safety checks the recipe declares (MC08 authority rule).
    """
    current = TypedArtifactStore(project_root).get_current(recipe_id)
    if current is None:
        return {"code": "E_INPUT", "message": f"unknown recipe {recipe_id!r}"}
    content = current.content
    checks = content.get("checks", [])
    exceptions = content.get("exceptions", [])
    required_symbols = content.get("required_symbols", [])
    required_dependencies = content.get("required_dependencies", {})
    required_config_digest = content.get("required_config_digest")

    def _unusable(reason: str) -> dict[str, Any]:
        return {
            "code": "OK",
            "recipe_id": recipe_id,
            "version": current.artifact_version,
            "usable": False,
            "reason": reason,
            "purpose": content.get("purpose"),
            "current_helper": None,
            "checks": checks,
            "exceptions": exceptions,
        }

    resolved = resolve_symbol_source(project_root, content.get("helper_ref"))
    if resolved is None:
        return _unusable(
            f"helper unresolved: {content.get('helper_ref')!r} no longer exists."
        )
    current_source, current_hash = resolved
    recorded_hash = content.get("helper_source_hash")
    if current_hash != recorded_hash:
        return _unusable(
            "helper source changed since recorded "
            f"(recorded_hash={str(recorded_hash)[:12]}, current_hash={current_hash[:12]})."
        )

    for symbol_ref in required_symbols:
        if resolve_symbol_source(project_root, symbol_ref) is None:
            return _unusable(f"missing required symbol: {symbol_ref!r}.")

    for name, expected in required_dependencies.items():
        actual = (current_dependencies or {}).get(name)
        if actual != expected:
            return _unusable(
                f"dependency mismatch: {name!r} expected {expected!r}, got {actual!r}."
            )

    if required_config_digest and required_config_digest != current_config_digest:
        return _unusable(
            f"config digest mismatch: expected {required_config_digest!r}, "
            f"got {current_config_digest!r}."
        )

    return {
        "code": "OK",
        "recipe_id": recipe_id,
        "version": current.artifact_version,
        "usable": True,
        "reason": None,
        "purpose": content.get("purpose"),
        "current_helper": {
            "helper_ref": content.get("helper_ref"),
            "source": current_source,
            "source_hash": current_hash,
        },
        "checks": checks,
        "exceptions": exceptions,
    }


def record_recipe_outcome(
    *,
    project_root: Path,
    recipe_id: str,
    recipe_version: int,
    patch_hash: str,
    verifier_receipt_ref: Mapping[str, Any],
) -> dict[str, Any]:
    """MC08.3: append one adaptation outcome to `recipe_id`, gated on `recipe_version`
    (compare-and-swap) and a real, resolvable `sandbox_verification` receipt from
    `rush.memory.verification.verify_attempt` -- there is no `passed=` parameter here
    precisely so a caller can never assert success without one (MC08 authority rule).
    Never touches `required_symbols`/`required_dependencies`/`required_config_digest`/
    `checks`/`exceptions`, and never changes `trust_tier`: one passing adaptation proves
    only that one patch under one receipt worked, never a universal or promoted recipe.
    """
    store = TypedArtifactStore(project_root)
    current = store.get_current(recipe_id)
    if current is None:
        return {"code": "E_INPUT", "message": f"unknown recipe {recipe_id!r}"}
    if current.artifact_version != recipe_version:
        return {
            "code": "E_VERSION",
            "message": (
                f"recipe_version={recipe_version} does not match current "
                f"version={current.artifact_version}."
            ),
        }
    if not patch_hash or not isinstance(patch_hash, str):
        return {
            "code": "E_INPUT",
            "message": "record_recipe_outcome requires patch_hash.",
        }
    receipt_id = verifier_receipt_ref.get("id") if verifier_receipt_ref else None
    receipt_version = (
        verifier_receipt_ref.get("version") if verifier_receipt_ref else None
    )
    if not receipt_id or receipt_version is None:
        return {
            "code": "E_INPUT",
            "message": "record_recipe_outcome requires a resolvable verifier_receipt_ref.",
        }
    receipt = store.get_current(str(receipt_id))
    if receipt is None or receipt.artifact_version != receipt_version:
        return {
            "code": "E_INPUT",
            "message": "verifier_receipt_ref does not resolve to a current artifact version.",
        }
    recognized, passed = _verifier_outcome(receipt.content)
    if not recognized:
        return {
            "code": "E_INPUT",
            "message": (
                "verifier_receipt_ref is not a recognized sandbox_verification receipt "
                "-- a bare passed claim is never accepted."
            ),
        }

    prior = current.content
    outcomes = list(prior.get("outcomes", []))
    outcomes.append(
        {
            "recipe_version": recipe_version,
            "patch_hash": patch_hash,
            "receipt_ref": {"id": receipt.id, "version": receipt.artifact_version},
            "passed": passed,
            "recorded_at": time.time(),
        }
    )
    payload = dict(prior)
    payload["outcomes"] = outcomes
    try:
        store.update_content(recipe_id, payload, expected_version=recipe_version)
    except VersionConflictError as exc:
        return {"code": exc.code, "message": str(exc)}

    return {
        "code": "OK",
        "id": recipe_id,
        "version": recipe_version + 1,
        "recipe_id": recipe_id,
        "passed": passed,
        "receipt_ref": {"id": receipt.id, "version": receipt.artifact_version},
        "outcomes_count": len(outcomes),
    }


__all__ = [
    "record_recipe",
    "record_recipe_outcome",
    "resolve_recipe",
    "resolve_symbol_source",
]
