"""Runtime binary resolution and discovery caching.

Architecture §4.4 — enforces requirement C10 (engine discovery, never hard-fail).
Phase 65 §6.2 — verified project provision manifest resolution binds an
executable hash, engine version, project scope and runtime identity before
falling back to the interpreter-bin/PATH policy below. A manifest that fails
any check is never trusted; resolution silently falls back to the existing
safe PATH-based policy instead of returning a tampered or scope-mismatched
path.
"""

from __future__ import annotations

import contextvars
import hashlib
import json
import os
import re
import shutil
import stat as stat_mod
import sys
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

if TYPE_CHECKING:
    from rush.permissions import ExecutionPermissions

MANIFEST_SCHEMA_VERSION = 1
MANIFEST_FILENAME = "manifest.json"


class ManifestVerificationError(Exception):
    """Raised when a provision manifest fails hash, scope, or schema checks."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(f"[{code}] {message}")
        self.code = code


@dataclass(frozen=True)
class ProvisionManifest:
    """Immutable record binding a provisioned executable to its verified identity."""

    schema_version: int
    engine_id: str
    package_id: str
    version: str
    source: str
    manager: str
    executable: str
    executable_sha256: str
    os_name: str
    arch: str
    project_id: str
    project_root: str
    runtime_identity: str
    plan_id: str
    created_at: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ProvisionManifest:
        return cls(**{field: data[field] for field in cls.__dataclass_fields__})


def compute_file_sha256(path: Path | str) -> str:
    """Return the lowercase hex SHA256 of a file's actual bytes on disk."""
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_manifest(dest_dir: Path, manifest: ProvisionManifest) -> Path:
    """Atomically write a provision manifest into ``dest_dir``."""
    dest_dir.mkdir(parents=True, exist_ok=True)
    target = dest_dir / MANIFEST_FILENAME
    payload = json.dumps(manifest.to_dict(), sort_keys=True, indent=2).encode("utf-8")
    with tempfile.NamedTemporaryFile(dir=dest_dir, delete=False) as handle:
        temp_path = Path(handle.name)
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temp_path, target)
    return target


# (path, mtime_ns, size) -> parsed ProvisionManifest. Invalidated automatically
# when the manifest file is replaced (mtime/size change); this cache never
# substitutes for the fresh executable-hash check performed on every call to
# `verify_manifest`, which cannot be bypassed by stale caching.
_manifest_parse_cache: dict[tuple[str, int, int], ProvisionManifest] = {}


def read_manifest(path: Path) -> ProvisionManifest | None:
    """Return the parsed manifest at ``path``, or None if absent/corrupt."""
    try:
        stat = path.stat()
    except OSError:
        return None
    cache_key = (str(path), stat.st_mtime_ns, stat.st_size)
    cached = _manifest_parse_cache.get(cache_key)
    if cached is not None:
        return cached
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        manifest = ProvisionManifest.from_dict(data)
    except (OSError, ValueError, KeyError, TypeError):
        return None
    _manifest_parse_cache.clear()
    _manifest_parse_cache[cache_key] = manifest
    return manifest


def clear_manifest_cache() -> None:
    """Clear the in-memory manifest parse cache."""
    _manifest_parse_cache.clear()


def verify_manifest(manifest: ProvisionManifest, *, project_root: Path) -> None:
    """Raise ManifestVerificationError on any hash, scope, or schema mismatch.

    Fails closed: a tampered manifest or an executable whose bytes no longer
    match the recorded hash is never trusted, regardless of caching.
    """
    if manifest.schema_version != MANIFEST_SCHEMA_VERSION:
        raise ManifestVerificationError(
            "MANIFEST_SCHEMA_MISMATCH",
            f"expected schema {MANIFEST_SCHEMA_VERSION}, got {manifest.schema_version}",
        )
    resolved_root = str(project_root.resolve())
    if manifest.project_root != resolved_root:
        raise ManifestVerificationError(
            "SCOPE_MISMATCH",
            f"manifest scoped to {manifest.project_root!r}, not {resolved_root!r}",
        )
    exe = Path(manifest.executable)
    if not exe.is_file():
        raise ManifestVerificationError("EXECUTABLE_MISSING", f"{exe} does not exist")
    actual_hash = compute_file_sha256(exe)
    if actual_hash != manifest.executable_sha256:
        raise ManifestVerificationError(
            "HASH_MISMATCH",
            f"{exe} sha256 {actual_hash} does not match manifest {manifest.executable_sha256}",
        )


def resolve_project_binary(engine_id: str, project_root: Path) -> str | None:
    """Resolve a verified, project-scoped provisioned binary for ``engine_id``.

    Reads ``<project_root>/.rush/toolchains.json`` (engine_id -> manifest
    path), loads and freshly re-hashes the referenced manifest's executable,
    and returns its absolute path only when the manifest's schema, project
    scope, and executable hash all verify. Returns None on any missing
    selection, missing/corrupt manifest, or verification failure -- callers
    must fall back to `resolve_binary`; this function never raises to a
    caller that only wants a path.
    """
    selection_path = project_root / ".rush" / "toolchains.json"
    try:
        selection = json.loads(selection_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    entry = selection.get(engine_id) if isinstance(selection, dict) else None
    if not isinstance(entry, dict):
        return None
    manifest_path = entry.get("manifest")
    if not isinstance(manifest_path, str):
        return None
    manifest = read_manifest(Path(manifest_path))
    if manifest is None or manifest.engine_id != engine_id:
        return None
    try:
        verify_manifest(manifest, project_root=project_root)
    except ManifestVerificationError:
        return None
    return manifest.executable


def _venv_scripts_dir() -> Path | None:
    """If we're running inside a uv-managed venv, return its Scripts/bin dir.

    shutil.which() with no explicit `path=` reads $PATH, which on Windows
    doesn't include the venv's Scripts/ when the venv is invoked by
    absolute path (vs activated via `source .venv/bin/activate`). Adding
    the venv's Scripts dir to the search list makes `engine_on_path()`
    find ruff/pytest/pip-audit installed via `uv pip install`.
    """
    scripts = Path(sys.prefix) / ("Scripts" if os.name == "nt" else "bin")
    if scripts.is_dir():
        return scripts
    return None


def _runtime_scripts_dir() -> Path | None:
    common = sys.modules.get("rush.tools.common")
    scripts_fn = (
        getattr(common, "_venv_scripts_dir", _venv_scripts_dir)
        if common is not None
        else _venv_scripts_dir
    )
    return scripts_fn()


def _within(path: str, roots: tuple[str, ...]) -> bool:
    return any(
        path == root or path.startswith(root.rstrip(os.sep) + os.sep) for root in roots
    )


def _is_project_scoped(candidate: str, roots: tuple[str, ...]) -> bool:
    """True when ``candidate``'s directory or real target lies inside a root.

    The Rush runtime's own interpreter bin is exempt: Rush is already
    executing from it, so it is not a project-supplied executable even when
    Rush's own dev checkout keeps its `.venv` inside the analyzed tree.
    """
    candidate_dir = os.path.realpath(os.path.dirname(candidate))
    scripts = _runtime_scripts_dir()
    if scripts is not None and candidate_dir == os.path.realpath(str(scripts)):
        return False
    return _within(candidate_dir, roots) or _within(os.path.realpath(candidate), roots)


def _search_binary(binary: str, roots: tuple[str, ...]) -> str | None:
    scripts = _runtime_scripts_dir()
    if scripts is not None:
        ext = ".exe" if os.name == "nt" else ""
        candidate = scripts / (binary + ext)
        if candidate.is_file():
            return str(candidate)
    if not roots:
        return shutil.which(binary)
    for entry in os.environ.get("PATH", "").split(os.pathsep):
        if not entry or _within(os.path.realpath(entry), roots):
            continue
        found = shutil.which(binary, path=entry)
        if found is not None and not _is_project_scoped(found, roots):
            return found
    return None


def _identity(path: str) -> tuple[int, int, int] | None:
    try:
        st = os.lstat(path)
    except OSError:
        return None
    return (st.st_ino, st.st_size, st.st_mtime_ns)


_NOT_FOUND = object()
# (binary, project roots, PATH, sys.prefix) -> (path | _NOT_FOUND, lstat
# identity). The key never depends on the lookup's own result; every hit is
# re-lstat'ed and recomputed when the executable's identity changed.
_binary_cache: dict[
    tuple[str, tuple[str, ...], str, str], tuple[object, tuple[int, int, int] | None]
] = {}


def _lookup_binary(binary: str, roots: tuple[str, ...]) -> str | None:
    key = (binary, roots, os.environ.get("PATH", ""), sys.prefix)
    hit = _binary_cache.get(key)
    if hit is not None:
        value, identity = hit
        if value is _NOT_FOUND:
            return None
        if isinstance(value, str) and _identity(value) == identity:
            return value
    found = _search_binary(binary, roots)
    _binary_cache[key] = (
        (found, _identity(found)) if found is not None else (_NOT_FOUND, None)
    )
    return found


def _resolve_binary_cached(binary: str) -> str | None:
    """Unscoped resolution: the Rush runtime's own bin, then PATH."""
    return _lookup_binary(binary, ())


def project_scoped_candidate(binary: str, project_root: Path) -> str | None:
    """The naive (unscoped) PATH candidate for `binary`, if `resolve_binary`
    with this `project_root` would exclude it as project-scoped -- never
    executes it.

    Independent of whether `resolve_binary` ultimately recovers a trusted
    candidate elsewhere on PATH or via a verified manifest: a caller that
    needs to report the project-scoped shadow attempt itself (T15's
    `binary-shadowing` finding) queries this, rather than re-deriving
    `resolve_binary`'s internal filtering from its return value alone.
    """
    roots = (os.path.realpath(str(project_root)),)
    candidate = _resolve_binary_cached(binary)
    if candidate is not None and _is_project_scoped(candidate, roots):
        return candidate
    return None


def clear_binary_cache() -> None:
    """Clear the in-memory binary resolution cache."""
    _binary_cache.clear()


@dataclass(frozen=True)
class AnalysisScope:
    """The logical project root (plus any staged execution root) an engine
    dispatch runs against, and the engine whose manifest may apply."""

    logical_root: Path
    execution_root: Path | None = None
    engine_id: str | None = None
    binary: str | None = None

    def roots(self) -> tuple[str, ...]:
        roots = [self.logical_root]
        if self.execution_root is not None:
            roots.append(self.execution_root)
        return tuple(os.path.realpath(str(root)) for root in roots)


_ANALYSIS_SCOPE: contextvars.ContextVar[AnalysisScope | None] = contextvars.ContextVar(
    "rush_analysis_scope", default=None
)


def current_analysis_scope() -> AnalysisScope | None:
    """The ambient `AnalysisScope`, or None outside an engine dispatch."""
    return _ANALYSIS_SCOPE.get()


@contextmanager
def analysis_scope(scope: AnalysisScope) -> Iterator[None]:
    """Make ``scope`` ambient for one dispatch.

    Every `resolve_binary(name)` inside it -- an engine's own argv, its
    `--version` probe, `engine_on_path` and `run_subprocess`'s exec
    resolution -- then applies verified-manifest precedence and the project
    PATH filter, with no Engine signature change. Context-local, so a
    concurrent dispatch on another thread never inherits it.
    """
    token = _ANALYSIS_SCOPE.set(scope)
    try:
        yield
    finally:
        _ANALYSIS_SCOPE.reset(token)


def resolve_binary(
    binary: str, *, engine_id: str | None = None, project_root: Path | None = None
) -> str | None:
    """Return an executable: verified manifest, the Rush runtime's bin, then PATH.

    When both ``engine_id`` and ``project_root`` are known -- passed
    explicitly, or ambient through `analysis_scope` -- a verified project
    provision manifest is tried first via `resolve_project_binary`; its result
    is used only when the manifest verifies. Any missing or tampered manifest
    falls through to the runtime-bin/PATH policy -- never a trust decision on
    an unverified project-controlled path.

    With a project root known, PATH entries and results inside that root (or
    a staged execution root) -- a project `node_modules/.bin`, an activated
    project `.venv/bin` -- are never selected: presence on PATH is not trust.
    The Rush runtime's own bin is exempt. Calls with no root and no ambient
    scope keep the unscoped policy.

    This resolver is the only engine-discovery policy. Configuration cannot
    supply an executable path, which prevents a project file from selecting an
    arbitrary local binary. Results are cached in-memory, keyed by root, PATH
    and runtime prefix, and revalidated against the executable's identity.
    """
    scope = _ANALYSIS_SCOPE.get()
    roots: tuple[str, ...] = ()
    manifest_root = project_root
    if project_root is not None:
        roots = (os.path.realpath(str(project_root)),)
    elif scope is not None:
        roots = scope.roots()
        manifest_root = scope.logical_root
        if engine_id is None and binary == scope.binary:
            engine_id = scope.engine_id
    if engine_id is not None and manifest_root is not None:
        verified = resolve_project_binary(engine_id, manifest_root)
        if verified is not None:
            return verified
    candidate = _resolve_binary_cached(binary)
    if (
        candidate is None
        or not roots
        or os.path.dirname(binary)
        or not _is_project_scoped(candidate, roots)
    ):
        return candidate
    return _lookup_binary(binary, roots)


# --- Analysis environment (project interpreter) selection -------------------

EnvironmentMode = Literal["project", "isolated"]
_MAX_SYMLINK_HOPS = 40
_PYVENV_KEY = re.compile(r"^[A-Za-z0-9_.-]+$")


@dataclass(frozen=True)
class AnalysisEnvironment:
    """The interpreter environment a Python type checker analyzes against.

    ``mode`` is ``project`` (the validated project `.venv` interpreter),
    ``isolated`` (no project interpreter is executed) or ``denied`` (an
    explicit project request without the build grant: nothing runs).
    """

    mode: Literal["project", "isolated", "denied"]
    interpreter: str | None = None
    interpreter_target: str | None = None
    interpreter_sha256: str | None = None
    environment_root: str | None = None
    cause: str | None = None
    permission: Literal["granted", "denied", "not_required"] = "not_required"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _pyvenv_home(cfg: Path) -> str | None:
    """`home` from a strictly parsed `pyvenv.cfg`, or None when invalid."""
    try:
        text = cfg.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None
    values: dict[str, str] = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        key, sep, value = line.partition("=")
        key = key.strip()
        if not sep or not _PYVENV_KEY.match(key):
            return None
        values[key] = value.strip()
    home = values.get("home")
    if not home or not os.path.isabs(home):
        return None
    return home


def _validate_interpreter(
    venv: Path, interpreter: Path, home: str
) -> tuple[str | None, str | None]:
    """(cause, real target). Validation only: lstat/readlink, never exec.

    Accepted when the final target is a regular file inside the venv, or
    when it is exactly what ``home`` provides under the basename of the
    chain's first hop out of the venv (so Homebrew's opt -> Cellar ->
    Frameworks chain is accepted while a relink to any other file is not).
    """
    venv_real = (os.path.realpath(str(venv)),)
    current = str(interpreter)
    first_out: str | None = None
    for _ in range(_MAX_SYMLINK_HOPS):
        try:
            st = os.lstat(current)
        except OSError:
            return "interpreter_missing", None
        if not stat_mod.S_ISLNK(st.st_mode):
            break
        nxt = os.path.join(os.path.dirname(current), os.readlink(current))
        if first_out is None and not _within(
            os.path.realpath(os.path.dirname(nxt)), venv_real
        ):
            first_out = nxt
        current = nxt
    else:
        return "interpreter_symlink_loop", None
    target = os.path.realpath(current)
    try:
        if not stat_mod.S_ISREG(os.stat(target).st_mode):
            return "interpreter_missing", None
    except OSError:
        return "interpreter_missing", None
    if first_out is None and _within(target, venv_real):
        return None, target
    if (
        first_out is not None
        and os.path.realpath(os.path.join(home, os.path.basename(first_out))) == target
    ):
        return None, target
    return "interpreter_outside_home", None


def select_analysis_environment(
    root: Path,
    mode: EnvironmentMode | None = None,
    granted: ExecutionPermissions | None = None,
) -> AnalysisEnvironment:
    """Choose the interpreter environment for Python type checking at ``root``.

    The project `.venv` interpreter is used only in project mode (explicit or
    default) with the build grant -- starting it runs the venv's `.pth`
    code -- and only when `pyvenv.cfg` parses with an existing `home` and the
    interpreter validates (`_validate_interpreter`). Default mode without the
    grant, or any invalid venv, falls back to ``isolated`` with a precise
    cause; explicit project mode without the grant is ``denied``. This
    function only stats, reads links and parses; it never executes anything.
    """
    has_build = bool(getattr(granted, "build", False))
    if mode == "isolated":
        return AnalysisEnvironment(mode="isolated", cause="requested")
    if not has_build:
        return AnalysisEnvironment(
            mode="denied" if mode == "project" else "isolated",
            cause="project_environment_requires_allow_build",
            permission="denied",
        )
    venv = root / ".venv"

    def fallback(cause: str) -> AnalysisEnvironment:
        return AnalysisEnvironment(
            mode="isolated",
            environment_root=str(venv),
            cause=cause,
            permission="granted",
        )

    if not venv.is_dir():
        return fallback("venv_missing")
    home = _pyvenv_home(venv / "pyvenv.cfg")
    if home is None or not os.path.isdir(home):
        return fallback("pyvenv_cfg_invalid")
    windows = os.name == "nt"
    interpreter = (
        venv / "Scripts" / "python.exe" if windows else venv / "bin" / "python"
    )
    cause, target = _validate_interpreter(venv, interpreter, home)
    if cause is not None or target is None:
        return fallback(cause or "interpreter_missing")
    return AnalysisEnvironment(
        mode="project",
        interpreter=str(interpreter),
        interpreter_target=target,
        interpreter_sha256=compute_file_sha256(target),
        environment_root=str(venv),
        permission="granted",
    )


def engine_on_path(binary: str) -> bool:
    """True if `binary` is findable on PATH or in the active venv's Scripts/."""
    common = sys.modules.get("rush.tools.common")
    resolver = (
        getattr(common, "resolve_binary", resolve_binary)
        if common is not None
        else resolve_binary
    )
    return resolver(binary) is not None


__all__ = [
    "MANIFEST_SCHEMA_VERSION",
    "AnalysisEnvironment",
    "AnalysisScope",
    "ManifestVerificationError",
    "ProvisionManifest",
    "_resolve_binary_cached",
    "_venv_scripts_dir",
    "analysis_scope",
    "clear_binary_cache",
    "clear_manifest_cache",
    "compute_file_sha256",
    "current_analysis_scope",
    "engine_on_path",
    "project_scoped_candidate",
    "read_manifest",
    "resolve_binary",
    "resolve_project_binary",
    "select_analysis_environment",
    "verify_manifest",
    "write_manifest",
]
