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

import hashlib
import json
import os
import shutil
import sys
import tempfile
from dataclasses import asdict, dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

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


def compute_file_sha256(path: Path) -> str:
    """Return the lowercase hex SHA256 of a file's actual bytes on disk."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
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


@lru_cache(maxsize=256)
def _resolve_binary_cached(binary: str) -> str | None:
    common = sys.modules.get("rush.tools.common")
    scripts_fn = (
        getattr(common, "_venv_scripts_dir", _venv_scripts_dir)
        if common is not None
        else _venv_scripts_dir
    )
    scripts = scripts_fn()
    if scripts is not None:
        ext = ".exe" if os.name == "nt" else ""
        candidate = scripts / (binary + ext)
        if candidate.is_file():
            return str(candidate)
    return shutil.which(binary)


def clear_binary_cache() -> None:
    """Clear the in-memory binary resolution cache."""
    _resolve_binary_cached.cache_clear()


def resolve_binary(
    binary: str, *, engine_id: str | None = None, project_root: Path | None = None
) -> str | None:
    """Return an executable from the active venv Scripts/bin, then PATH.

    When both ``engine_id`` and ``project_root`` are supplied, a verified
    project provision manifest is tried first via `resolve_project_binary`;
    its result is used only when the manifest verifies. Any missing or
    tampered manifest falls straight through to the existing venv/PATH
    policy below -- never a trust decision on an unverified project-controlled
    path. Existing callers that omit both keyword arguments are unaffected.

    This resolver is the only engine-discovery policy. Configuration cannot
    supply an executable path, which prevents a project file from selecting an
    arbitrary local binary. Results are cached in-memory for fast repeated lookups.
    """
    if engine_id is not None and project_root is not None:
        verified = resolve_project_binary(engine_id, project_root)
        if verified is not None:
            return verified
    return _resolve_binary_cached(binary)


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
    "ManifestVerificationError",
    "ProvisionManifest",
    "_resolve_binary_cached",
    "_venv_scripts_dir",
    "clear_binary_cache",
    "clear_manifest_cache",
    "compute_file_sha256",
    "engine_on_path",
    "read_manifest",
    "resolve_binary",
    "resolve_project_binary",
    "verify_manifest",
    "write_manifest",
]
