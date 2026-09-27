"""Physical target resolution and boundary containment for Phase 57.

Guarantees immutable target representations, SHA-256 digests,
and strict rejection of scope-widening symlinks, junctions, and undeclared host paths.
"""

from __future__ import annotations

import hashlib
import os
import stat
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from rush.invocation.models import (
    AmbiguousRootError,
    PhysicalTarget,
    ScopeWideningError,
    TargetState,
    UndeclaredInputError,
)
from rush.io.physical_paths import ContainmentError, PhysicalRoot
from rush.safety.redactor import sanitize_value

_REPARSE_POINT = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)

_Ident = tuple[int, int]


@dataclass(frozen=True)
class RootSelection:
    """T8/§3.2: one ROOT-ENTRY walk's result.

    `root` is the logical root (a physical directory, or the declared
    registry root), `relative` the link-free root-relative suffix (`.` when
    the target is the root), `target` is `root / relative`, `lexical` the
    input joined once to the anchor without any normalization, and `anchor`
    the directory relative input was joined to.
    """

    root: Path
    relative: Path
    target: Path
    lexical: Path
    anchor: Path
    declared_root: Path | None


def _redact(text: str) -> str:
    return str(sanitize_value(text).value)


def _lstat_or_none(path: Path) -> os.stat_result | None:
    try:
        return os.lstat(path)
    except (OSError, ValueError):
        return None


def _is_link(st: os.stat_result) -> bool:
    return stat.S_ISLNK(st.st_mode) or bool(
        getattr(st, "st_file_attributes", 0) & _REPARSE_POINT
    )


def _ident(st: os.stat_result) -> _Ident:
    return (st.st_dev, st.st_ino)


def _has_marker(directory: Path) -> bool:
    """§3.2 root marker probe, `lstat` only: a regular `rush.toml`, a real
    `.rush` directory holding a regular `project.json`, or a `.git`
    directory/worktree file. A symlinked marker is not a marker, and a
    symlinked `.rush` is never traversed."""
    st = _lstat_or_none(directory / "rush.toml")
    if st is not None and stat.S_ISREG(st.st_mode):
        return True
    st = _lstat_or_none(directory / ".rush")
    if st is not None and stat.S_ISDIR(st.st_mode) and not _is_link(st):
        descriptor = _lstat_or_none(directory / ".rush" / "project.json")
        if descriptor is not None and stat.S_ISREG(descriptor.st_mode):
            return True
    st = _lstat_or_none(directory / ".git")
    return bool(
        st is not None
        and not _is_link(st)
        and (stat.S_ISDIR(st.st_mode) or stat.S_ISREG(st.st_mode))
    )


def registered_root_index(
    data_root: Path | None = None, *, strict: bool = False
) -> dict[str, str]:
    """Every registered project ID -> its canonical root string, from one
    side-effect-free registry read. Never `list_projects`/`resolve_project`,
    whose project view inspects every project tree. An unresolvable data
    root means no registration can exist, so the index is empty; `strict`
    propagates that error instead, for an explicitly declared project."""
    from rush.setup.provision import DataRootUnavailableError
    from rush.workflows import projects

    try:
        base = data_root or projects.default_data_root()
    except DataRootUnavailableError:
        if strict:
            raise
        return {}
    registry = projects._load_registry(base)
    return {
        str(project_id): str(entry["root"])
        for project_id, entry in registry["projects"].items()
        if isinstance(entry, dict) and entry.get("root")
    }


def route_project_reference(
    value: Any, *, anchor: Path, index: Mapping[str, str]
) -> tuple[str, Path]:
    """A declared project reference: a registered ID first (IDs may contain
    `/`), else a path anchored to `anchor` (never the live cwd) matched
    against registered canonical roots exactly as `resolve_project` does."""
    from rush.workflows.projects import ProjectNotFoundError

    if not isinstance(value, str) or value == "":
        raise ProjectNotFoundError(_redact(f"no registered project matches: {value}"))
    if value in index:
        return value, Path(index[value])
    candidate = (
        Path(os.path.expanduser(value)) if value.startswith("~") else Path(value)
    )
    if not candidate.is_absolute():
        candidate = anchor / candidate
    canonical = str(candidate.resolve())
    for project_id, root in index.items():
        if root == canonical:
            return project_id, Path(root)
    raise ProjectNotFoundError(_redact(f"no registered project matches: {value}"))


def anchor_path_value(value: Any, anchor: Path) -> Any:
    """A relative path-valued request field resolves against `anchor`;
    absolute, `~` and non-string values are left as given."""
    if (
        not isinstance(value, str)
        or not value
        or value.startswith("~")
        or os.path.isabs(value)
    ):
        return value
    return str(anchor / value)


def anchor_project_value(value: Any, anchor: Path, index: Mapping[str, str]) -> Any:
    """A request-dict `project` value: a registered ID is kept verbatim,
    anything else is a path anchored to `anchor`."""
    if isinstance(value, str) and value in index:
        return value
    return anchor_path_value(value, anchor)


@dataclass
class _Frame:
    path: Path
    ident: _Ident
    marked: bool
    registered: bool
    established: bool
    in_anchor: bool
    via_link: Path | None = None


def select_root(
    raw: str | Path,
    *,
    anchor: Path,
    declared_root: Path | None = None,
    index: Mapping[str, str] | None = None,
) -> RootSelection:
    """T8/§3.2 ROOT-ENTRY walk: the input joined once to `anchor`, walked
    component by component from the filesystem root without following links.

    A link met inside the anchor after a marked or registered project is
    established is INTERNAL and rejected (L1). Outside the anchor, a link met
    after a project is established is followed only when it leads to the
    anchor or one of its ancestors and the walk then reaches the anchor (L2).
    Inside the anchor before any project, a link is a root entry only when its
    destination is a marked or registered project root (L3). Outside the
    anchor before any project, a link to a directory is an above-root prefix
    and translated (L4); a link to a file is never transparent. A filesystem
    root anchor bounds nothing. `..` pops a real directory and is rejected
    after a link. Nothing is opened, and no descendant of a rejected link is
    ever probed.

    The logical root is the declared root (which must appear on the walk by
    identity, else `AmbiguousRootError`), else the deepest marked or
    registered directory, else the deepest existing directory.
    """
    raw = str(raw)
    index = registered_root_index() if index is None else index
    roots = frozenset(index.values())
    raw_path = Path(raw)
    lexical = raw_path if raw_path.is_absolute() else anchor / raw_path
    comps = lexical.parts
    bounded = anchor.parent != anchor
    anchor_ident = _ident(os.stat(anchor))
    anchor_lineage = {_ident(os.stat(q)) for q in (anchor, *anchor.parents)}
    root_ident = _ident(os.stat(declared_root)) if declared_root is not None else None

    def scope(code: str, message: str) -> ScopeWideningError:
        return ScopeWideningError(_redact(str(ContainmentError(code, message, raw))))

    def frame(path: Path, st: os.stat_result, parent: _Frame | None) -> _Frame:
        ident = _ident(st)
        marked = _has_marker(path)
        registered = str(path) in roots
        established = (
            (parent.established if parent is not None else False)
            or marked
            or registered
            or ident == root_ident
        )
        in_anchor = bounded and (
            (parent.in_anchor if parent is not None else False) or ident == anchor_ident
        )
        return _Frame(path, ident, marked, registered, established, in_anchor)

    def ancestry(destination: Path, via: Path) -> list[_Frame]:
        frames = [
            frame(Path(destination.parts[0]), os.lstat(destination.parts[0]), None)
        ]
        for name in destination.parts[1:]:
            path = frames[-1].path / name
            st = os.lstat(path)
            if _is_link(st) or not stat.S_ISDIR(st.st_mode):
                raise scope(
                    "SYMLINK_DISALLOWED",
                    f"Symlink at component '{via}' cannot be resolved: "
                    "destination changed during resolution",
                )
            frames.append(frame(path, st, frames[-1]))
        frames[-1].via_link = via
        return frames

    def project_of(frames: list[_Frame]) -> Path:
        return next(
            f.path
            for f in reversed(frames)
            if f.marked or f.registered or f.ident == root_ident
        )

    def internal(link: Path, frames: list[_Frame]) -> str:
        return (
            f"Symlink detected at component '{link}' inside project "
            f"'{project_of(frames)}'"
        )

    def destination_of(link: Path, code: str) -> Path:
        try:
            return Path(os.path.realpath(link, strict=True))
        except OSError as exc:
            raise scope(
                code,
                f"Symlink at component '{link}' cannot be resolved: {exc.strerror}",
            ) from None

    frames = [frame(Path(comps[0]), os.lstat(comps[0]), None)]
    tail: list[str] = []
    alias_guard: tuple[Path, Path] | None = None
    for i in range(1, len(comps)):
        part, top = comps[i], frames[-1]
        if part == "..":
            if top.via_link is not None:
                raise scope(
                    "PARENT_TRAVERSAL_DISALLOWED",
                    f"'..' after symlink component '{top.via_link}' is forbidden",
                )
            if len(frames) > 1:
                frames.pop()
            continue
        path = top.path / part
        try:
            st = os.lstat(path)
        except (FileNotFoundError, NotADirectoryError):
            tail = list(comps[i:])
            break
        if _is_link(st):
            code = (
                "SYMLINK_DISALLOWED"
                if stat.S_ISLNK(st.st_mode)
                else "REPARSE_POINT_DISALLOWED"
            )
            if top.established and top.in_anchor:  # L1
                raise scope(code, internal(path, frames))
            destination = destination_of(path, code)
            if top.established:  # L2
                if (
                    destination.is_dir()
                    and _ident(os.stat(destination)) in anchor_lineage
                ):
                    alias_guard = alias_guard or (path, project_of(frames))
                    frames = ancestry(destination, path)
                    continue
                raise scope(code, internal(path, frames))
            if top.in_anchor:  # L3
                if destination.is_dir() and (
                    _has_marker(destination) or str(destination) in roots
                ):
                    frames = ancestry(destination, path)
                    continue
                raise scope(
                    code,
                    f"Symlink at component '{path}' is not a project root entry: "
                    f"'{destination}' is not a marked or registered project root",
                )
            if destination.is_dir():  # L4
                frames = ancestry(destination, path)
                continue
            raise scope(
                code,
                f"Symlink detected at component '{path}': "
                "a symlinked file is never transparent",
            )
        if stat.S_ISDIR(st.st_mode):
            frames.append(frame(path, st, top))
            continue
        tail = list(comps[i:])
        break

    if alias_guard is not None and not frames[-1].in_anchor:
        link, project = alias_guard
        raise scope(
            "SYMLINK_DISALLOWED",
            f"Symlink detected at component '{link}' inside project '{project}'",
        )
    if declared_root is not None:
        found = next((k for k, f in enumerate(frames) if f.ident == root_ident), None)
        if found is None:
            raise AmbiguousRootError(
                _redact(
                    f"registered root '{declared_root}' does not contain "
                    f"requested target '{raw}'"
                )
            )
        j, root = found, declared_root
    else:
        marks = [k for k, f in enumerate(frames) if f.marked or f.registered]
        j = marks[-1] if marks else len(frames) - 1
        root = frames[j].path
    names = [f.path.name for f in frames[j + 1 :]] + tail
    relative = Path(*names) if names else Path(".")
    return RootSelection(
        root, relative, root / relative, lexical, anchor, declared_root
    )


def select_member(
    raw: str | Path, *, anchor: Path, root: Path, index: Mapping[str, str]
) -> Path:
    """A `files`/`paths` list member, walked like the target and required to
    lie under the already-selected root."""
    try:
        return select_root(raw, anchor=anchor, declared_root=root, index=index).relative
    except AmbiguousRootError:
        raise UndeclaredInputError(
            _redact(f"External host input '{raw}' is outside workspace root '{root}'")
        ) from None


def assert_contained(selection: RootSelection) -> None:
    """Containment pre-check before any config read, hash or handler call."""
    try:
        PhysicalRoot(selection.root).open_contained(selection.relative, purpose="read")
    except ContainmentError as exc:
        raise ScopeWideningError(str(exc)) from exc


def assert_root_config_not_linked(root: Path) -> None:
    """A symlinked `rush.toml` inside the root is a link inside the root."""
    try:
        PhysicalRoot(root).open_contained("rush.toml", purpose="read")
    except ContainmentError as exc:
        raise ScopeWideningError(str(exc)) from exc


def resolve_logical_root(
    target: str | Path,
    *,
    anchor: Path | None = None,
    registered_root: str | None = None,
    data_root: Path | None = None,
) -> Path:
    """The logical root `select_root` chooses for `target`, walked from
    `anchor` (default: the current working directory). `registered_root` is a
    declared project ID or root path, routed ID first."""
    base = Path.cwd() if anchor is None else anchor
    index = registered_root_index(data_root)
    declared = (
        route_project_reference(registered_root, anchor=base, index=index)[1]
        if registered_root is not None
        else None
    )
    return select_root(target, anchor=base, declared_root=declared, index=index).root


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
        raw_path: Path | str = target_path.relative_path
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
                rel = p.relative_to(root_path)
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


__all__ = [
    "RootSelection",
    "anchor_path_value",
    "anchor_project_value",
    "assert_contained",
    "assert_root_config_not_linked",
    "build_physical_targets",
    "registered_root_index",
    "resolve_logical_root",
    "resolve_target",
    "route_project_reference",
    "select_member",
    "select_root",
]
