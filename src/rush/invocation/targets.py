"""Physical target resolution and boundary containment for Phase 57.

Guarantees immutable target representations, SHA-256 digests,
and strict rejection of scope-widening symlinks, junctions, and undeclared host paths.
"""

from __future__ import annotations

import hashlib
from collections.abc import Sequence
from pathlib import Path

from rush.invocation.models import (
    PhysicalTarget,
    ScopeWideningError,
    TargetState,
    UndeclaredInputError,
)
from rush.io.physical_paths import ContainmentError, PhysicalRoot


def resolve_target(
    workspace_root: Path,
    target_path: Path | str | PhysicalTarget,
    provenance: str = "explicit",
    capability: str = "read",
    declared_inputs: tuple[str, ...] | None = None,
    state: TargetState | None = None,
) -> PhysicalTarget:
    """Resolve and physically validate a single execution target within workspace root.

    Guarantees:
    - Enforces physical workspace boundary containment via PhysicalRoot.
    - Translates ContainmentError into ScopeWideningError fail-closed.
    - Rejects undeclared external host paths and unlisted inputs with UndeclaredInputError.
    - Computes deterministic SHA-256 content_hash for regular files (empty for deleted/dirs).
    - Returns frozen, immutable PhysicalTarget instance.
    """
    root_path = Path(workspace_root).resolve()
    physical_root = PhysicalRoot(root_path)

    # Extract target metadata if already a PhysicalTarget
    if isinstance(target_path, PhysicalTarget):
        raw_path = target_path.relative_path
        prov = (
            target_path.provenance
            if provenance == "explicit" and target_path.provenance != "explicit"
            else provenance
        )
        cap = (
            target_path.capability
            if capability == "read" and target_path.capability != "read"
            else capability
        )
        target_state: TargetState | None = (
            state if state is not None else target_path.state
        )
    else:
        raw_path = target_path
        prov = provenance
        cap = capability
        target_state = state

    p = Path(raw_path)
    p_str = str(raw_path)

    # Detect external host absolute paths
    has_drive_letter = len(p_str) >= 2 and p_str[1] == ":" and p_str[0].isalpha()
    is_abs = (
        p.is_absolute()
        or p_str.startswith(("/", "\\"))
        or bool(p.drive)
        or has_drive_letter
    )

    if is_abs:
        try:
            rel = p.relative_to(workspace_root)
        except ValueError:
            try:
                rel = p.resolve().relative_to(root_path)
            except ValueError:
                raise UndeclaredInputError(
                    f"External host input '{raw_path}' is outside workspace root '{workspace_root}'"
                ) from None
    else:
        rel = p

    # Enforce physical containment, rejecting symlinks, junctions, and traversals
    try:
        contained_path = physical_root.open_contained(rel, purpose=cap)
    except ContainmentError as exc:
        raise ScopeWideningError(str(exc)) from exc

    # Enforce declared inputs policy if declared_inputs is provided and non-empty
    if declared_inputs is not None and len(declared_inputs) > 0:
        normalized_declared: set[str] = set()
        for d in declared_inputs:
            d_path = Path(d)
            normalized_declared.add(d_path.as_posix())
            normalized_declared.add(str(d))
            if d_path.is_absolute():
                try:
                    normalized_declared.add(d_path.relative_to(root_path).as_posix())
                    normalized_declared.add(str(d_path.relative_to(root_path)))
                except ValueError:
                    pass

        if (
            rel.as_posix() not in normalized_declared
            and str(rel) not in normalized_declared
            and str(raw_path) not in normalized_declared
        ):
            raise UndeclaredInputError(
                f"Target '{raw_path}' is not in declared inputs: {declared_inputs}"
            )

    # Determine state and compute content hash
    if target_state is None:
        if contained_path.exists():
            target_state = "present"
        else:
            target_state = "deleted"

    content_hash = ""
    if target_state != "deleted" and contained_path.is_file():
        try:
            content_hash = hashlib.sha256(contained_path.read_bytes()).hexdigest()
        except OSError:
            content_hash = ""

    return PhysicalTarget(
        relative_path=rel,
        state=target_state,
        capability=cap,
        provenance=prov,
        content_hash=content_hash,
    )


def build_physical_targets(
    workspace_root: Path,
    raw_targets: Sequence[str | Path | PhysicalTarget],
    provenance: str = "explicit",
    capability: str = "read",
    declared_inputs: tuple[str, ...] | None = None,
) -> tuple[PhysicalTarget, ...]:
    """Resolve and validate a sequence of targets within workspace physical boundaries."""
    return tuple(
        resolve_target(
            workspace_root=workspace_root,
            target_path=target,
            provenance=provenance,
            capability=capability,
            declared_inputs=declared_inputs,
        )
        for target in raw_targets
    )


__all__ = ["build_physical_targets", "resolve_target"]
