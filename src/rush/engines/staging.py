"""P69-03 (d-j): immutable staging + real consumption provenance.

A path-based engine (the overwhelming majority of `src/rush/engines/`) takes a
filesystem *path* and spawns a subprocess that reads the bytes independently --
Rush's own process never sees what was consumed, so there is no "moment of read"
to hash. A start-vs-end hash of the live tree cannot certify the run either: an
A->B->A edit during the scan matches at both endpoints while the engine actually
read `B`.

The fix is structural: copy exactly the in-scope inventory into a private
staging root before any engine runs, point every path-based engine at the
staged tree, and hash the staged bytes. Nothing but the scan orchestrator can
touch that directory, so its content genuinely cannot change mid-scan.

Subsections implemented here:

* **f** -- staging is a genuinely *independent* copy. APFS `clonefile(2)` (a
  real copy-on-write clone) when the platform supports it, `shutil.copy2`
  otherwise. Never a hardlink: a hardlink shares the inode, so writing the
  original mutates the "staged" copy too, which is the exact property staging
  exists to prevent.
* **g** -- path mapping, both directions. Input side: `path`/`cwd` redirection
  plus explicit-argument substitution. Output side: `map_staged_path()` called
  on decoded, path-bearing fields only (never a raw-text substitution, which
  JSON-escapes differently and would corrupt literal content such as ruff's
  `fix.edits[].content`).
* **e/g** -- the bounded inventory alone is not a sufficient execution
  environment. Dependency/build/config directories the ignore convention
  excludes (`node_modules`, `.venv`, `.github`, ...) are exposed from the
  staging root as symlinks back to the live tree at the same relative path, so
  ESLint's config/plugin resolution and TSC's module resolution behave exactly
  as they do live. Those directories are never copied, so a finding inside one
  already carries a real live path and `map_staged_path()` passes it through
  untouched.
* **h** -- repository-state-dependent engines (`git-guard`, `diff-cover`,
  `undercover`) are excluded from staging entirely: they need real `.git`
  history/index/branches that a file copy cannot provide.
* **i** -- symlinks are dereferenced into real staged content; a symlink whose
  real target resolves outside the project root is rejected with an explicit
  finding rather than followed into staging.
* **j** -- `PROVENANCE_FORMAT` tags every new-format record so an old
  path/size/mtime value is never silently compared as a content hash.
"""

from __future__ import annotations

import ctypes
import os
import platform
import shutil
import urllib.parse
import urllib.request
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from hashlib import sha256
from pathlib import Path
from typing import Any

__all__ = [
    "DEPENDENCY_SYMLINK_EXCLUDED",
    "PROVENANCE_FORMAT",
    "REPOSITORY_STATE_ENGINES",
    "StagingContext",
    "active_staging",
    "aggregate_content_identity",
    "map_staged_path",
    "remap_paths",
    "stage_inventory",
    "staging_scope",
    "supports_reflink",
]

#: Subsection j. Bumped whenever the provenance algorithm changes; a record
#: carrying a different (or absent) tag is unsupported, never reinterpreted.
PROVENANCE_FORMAT = 2

#: Subsection h. Classified by whether the *invoked command* genuinely needs
#: real repository state, not by whether `git` appears in its argv --
#: `diff-cover` and `undercover` each launch their own binary and never call
#: `git` directly, yet both require a real repo internally.
REPOSITORY_STATE_ENGINES = frozenset({"git-guard", "diff-cover", "undercover"})

#: Never symlinked into staging. `.git` would make the staged tree
#: indistinguishable from the real repository (the exact confusion subsection h
#: excludes those engines to avoid) and `.rush` is Rush's own run state.
DEPENDENCY_SYMLINK_EXCLUDED = frozenset({".git", ".rush"})

#: Subsection g. Only genuinely path-bearing keys across the engines' real
#: output schemas. Deliberately excludes message/content keys: ruff's
#: `fix.edits[].content` is literal replacement source text, and substituting
#: into it would corrupt the fix.
_PATH_KEYS = frozenset(
    {
        "path",
        "file",
        "filename",
        "filePath",
        "file_path",
        "absolutePath",
        "uri",
    }
)


def supports_reflink(directory: Path) -> bool:
    """True when `directory`'s filesystem supports a real copy-on-write clone.

    Probed, never assumed (subsection f): a real `clonefile(2)` is attempted
    against a throwaway pair inside `directory` itself, because support is a
    per-filesystem property, not a per-OS one.
    """
    if platform.system() != "Darwin":
        return False
    probe_src = directory / ".rush-reflink-probe"
    probe_dst = directory / ".rush-reflink-probe.clone"
    try:
        probe_src.write_bytes(b"probe")
        probe_dst.unlink(missing_ok=True)
        return _clonefile(probe_src, probe_dst)
    except OSError:
        return False
    finally:
        for probe in (probe_src, probe_dst):
            try:
                probe.unlink(missing_ok=True)
            except OSError:
                pass


def _clonefile(src: Path, dst: Path) -> bool:
    """`clonefile(2)` with flags=0 (follows symlinks, which is what subsection
    i wants -- the real target's content lands at the staged path). Returns
    False on any platform or filesystem that cannot do it."""
    if platform.system() != "Darwin":
        return False
    try:
        libc = ctypes.CDLL(None, use_errno=True)
        fn = libc.clonefile
    except (OSError, AttributeError):
        return False
    fn.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_int]
    fn.restype = ctypes.c_int
    return fn(os.fsencode(str(src)), os.fsencode(str(dst)), 0) == 0


def _independent_copy(src: Path, dst: Path) -> None:
    """A real, independently-mutable copy -- COW clone where the filesystem
    genuinely supports it, a plain byte copy otherwise. Never a hardlink."""
    dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.exists():
        dst.unlink()
    if not _clonefile(src, dst):
        shutil.copy2(src, dst, follow_symlinks=True)


def _digest(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def aggregate_content_identity(digests: dict[str, str]) -> str:
    """Deterministic aggregate over per-file content digests (subsection e).

    Order-independent by construction: sorted `relpath:digest` lines, so two
    scans that read the same bytes produce the same identity regardless of
    which engine read what first.
    """
    body = "\n".join(f"{rel}:{value}" for rel, value in sorted(digests.items()))
    return sha256(body.encode("utf-8")).hexdigest()


@dataclass
class StagingContext:
    """One scan attempt's private staging tree and its consumption record."""

    original_root: Path
    staged_root: Path
    digests: dict[str, str] = field(default_factory=dict)
    consumed: dict[str, str] = field(default_factory=dict)
    findings: list[dict[str, Any]] = field(default_factory=list)
    reflink: bool = False
    _candidate: dict[str, str] = field(default_factory=dict)

    # -- input side (subsection g) -------------------------------------
    def stage_path(self, path: Path | None) -> Path | None:
        """The staged mirror of `path`, or `path` itself when it is not inside
        the project root (an absolute temp file, a system config, ...)."""
        if path is None:
            return None
        try:
            rel = Path(path).resolve().relative_to(self.original_root)
        except (OSError, ValueError):
            return path
        return self.staged_root / rel

    def substitute_arg(self, value: str) -> str:
        """Explicit file-path arguments a caller built itself (`ruff_files`,
        `prettier_files`, ...) get the identical root-prefix substitution."""
        if not value or value.startswith("-"):
            return value
        try:
            candidate = Path(value)
            if not candidate.is_absolute():
                return value
            rel = candidate.resolve().relative_to(self.original_root)
        except (OSError, ValueError):
            return value
        return str(self.staged_root / rel)

    # -- consumption record (subsections d/e) --------------------------
    def record_consumption(self, path: Path | None) -> None:
        """Mark every staged file under `path` as actually run against.

        `path` is the staged location an engine was pointed at; everything the
        subprocess could have read under it is staged content that cannot have
        changed during the run.
        """
        if path is None:
            return
        try:
            prefix = Path(path).resolve().relative_to(self.staged_root).as_posix()
        except (OSError, ValueError):
            return
        for rel, value in self.digests.items():
            if prefix in ("", ".") or rel == prefix or rel.startswith(f"{prefix}/"):
                self.consumed[rel] = value
                self._candidate[rel] = value

    def take_candidate_digests(self) -> dict[str, str]:
        """Drain and return the digests consumed since the last drain --
        one candidate's own per-file digests (subsection e, carried forward
        verbatim across a resume rather than re-read)."""
        taken = dict(self._candidate)
        self._candidate.clear()
        return taken


_ACTIVE: ContextVar[StagingContext | None] = ContextVar("rush_staging", default=None)


def active_staging() -> StagingContext | None:
    return _ACTIVE.get()


@contextmanager
def staging_scope(context: StagingContext | None) -> Iterator[StagingContext | None]:
    token = _ACTIVE.set(context)
    try:
        yield context
    finally:
        _ACTIVE.reset(token)


def _is_excluded_dir(name: str) -> bool:
    from ..review.collection import SKIP_DIRS

    return name in SKIP_DIRS or name.startswith(".")


def stage_inventory(
    original_root: Path,
    staged_root: Path,
    relative_paths: list[str],
) -> StagingContext:
    """Stage exactly `relative_paths` (the bounded inventory) as independent
    copies under `staged_root`, mirroring the original tree's relative
    directory structure exactly, then symlink every ignore-convention-excluded
    directory back to the live tree so dependency/config resolution is
    unchanged."""
    original_root = original_root.resolve()
    staged_root.mkdir(parents=True, exist_ok=True)
    context = StagingContext(
        original_root=original_root,
        staged_root=staged_root.resolve(),
        reflink=supports_reflink(staged_root),
    )

    for rel in sorted(relative_paths):
        source = original_root / rel
        if source.is_symlink():
            try:
                target = source.resolve(strict=True)
            except OSError:
                continue
            try:
                target.relative_to(original_root)
            except ValueError:
                # Subsection i: never follow an escaping symlink into staging.
                context.findings.append(
                    {
                        "path": rel,
                        "line": 0,
                        "column": 0,
                        "rule": "staging.symlink_escapes_root",
                        "severity": "error",
                        "message": (
                            f"symlink {rel} resolves outside the project root "
                            f"({target}); excluded from the staged scan"
                        ),
                    }
                )
                continue
        if not source.is_file():
            continue
        destination = context.staged_root / rel
        try:
            _independent_copy(source, destination)
            context.digests[Path(rel).as_posix()] = _digest(destination)
        except OSError:
            continue

    for child in sorted(original_root.iterdir()):
        if not child.is_dir() or child.name in DEPENDENCY_SYMLINK_EXCLUDED:
            continue
        if not _is_excluded_dir(child.name):
            continue
        link = context.staged_root / child.name
        if link.exists() or link.is_symlink():
            continue
        try:
            link.symlink_to(child, target_is_directory=True)
        except OSError:
            continue
    return context


# -- output side (subsection g) ----------------------------------------


def map_staged_path(value: str, staged_root: Path, original_root: Path) -> str:
    """Map one decoded, path-bearing field from the staged tree back to the
    live tree, preserving the field's own representation.

    Decodes a `file://` URI (`cspell`'s `uri` field) before checking, resolves
    both sides so `..` indirection cannot escape containment and a genuinely
    staged file reported through a symlinked path is still recognised, then
    re-encodes into the representation the field started in. A value that is
    not genuinely inside the staging root -- including one that merely shares a
    literal string prefix with it, and including a path inside a symlinked
    dependency directory (which resolves back into the live tree) -- is
    returned unchanged.
    """
    if not isinstance(value, str) or not value:
        return value
    is_uri = value.startswith("file://")
    raw = (
        urllib.request.url2pathname(urllib.parse.urlparse(value).path)
        if is_uri
        else value
    )
    try:
        candidate = Path(raw)
        if not candidate.is_absolute():
            candidate = staged_root / candidate
        resolved = candidate.resolve()
        rel = resolved.relative_to(staged_root.resolve())
    except (OSError, ValueError):
        return value
    mapped = original_root.resolve() / rel
    return mapped.as_uri() if is_uri else str(mapped)


def remap_paths(payload: Any, staged_root: Path, original_root: Path) -> Any:
    """Walk already-decoded data and remap only genuinely path-bearing fields.

    Never a pass over raw text: JSON escapes a path differently than plain
    text, so a raw-text substitution both misses real matches and can corrupt
    already-encoded output.
    """
    if isinstance(payload, dict):
        for key, value in payload.items():
            if key in _PATH_KEYS and isinstance(value, str):
                payload[key] = map_staged_path(value, staged_root, original_root)
            else:
                remap_paths(value, staged_root, original_root)
    elif isinstance(payload, list):
        for item in payload:
            remap_paths(item, staged_root, original_root)
    return payload
