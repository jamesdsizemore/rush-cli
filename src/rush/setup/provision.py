"""Engine toolchain provisioning: plan build/apply and manifest binding.

Phase 65 §6.2. ``build_provision_plan`` resolves an exact, immutable,
hash-pinned identity for every requested engine (rejecting anything outside
the ``rush.setup.engine_packages`` allowlist). ``apply_provision_plan``
installs into Rush-owned toolchain directories, runs a post-install
binary/version probe, and writes a ``ProvisionManifest`` (via
``rush.runtime.binaries``) only after that probe passes -- a failed install
never reports ready and never leaves a stale selection pointing at a bad
build.

All network/subprocess/filesystem side effects are behind small injectable
callables (``http_get``, ``downloader``, ``runner``, ``prober``) so plan
building and application are exhaustively unit-testable with fixtures,
independent of live network access.
"""

from __future__ import annotations

import hashlib
import io
import json
import os
import platform
import shlex
import shutil
import ssl
import subprocess
import tarfile
import tempfile
import uuid
import zipfile
from collections.abc import Callable
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import certifi

from rush.permissions import ExecutionPermissions, check_permissions
from rush.runtime.binaries import (
    MANIFEST_FILENAME,
    ManifestVerificationError,
    ProvisionManifest,
    compute_file_sha256,
    read_manifest,
    verify_manifest,
    write_manifest,
)
from rush.setup.engine_packages import (
    ENGINE_PACKAGES,
    EnginePackage,
    resolve_engine_package,
)


class ProvisionError(Exception):
    """Raised for any resolution, integrity, or prerequisite failure.

    Always carries one of the exact §6.2 error codes: NO_COMPATIBLE_ASSET,
    AMBIGUOUS_ASSET, INTEGRITY_UNAVAILABLE, INTEGRITY_MISMATCH,
    PACKAGE_NOT_FOUND, VERSION_UNAVAILABLE, SYSTEM_PREREQUISITE_REQUIRED,
    ENGINE_PROTOCOL_MISMATCH; or one of the Phase 70 T24 reviewed-plan codes:
    PLAN_TAMPERED, WRONG_PLATFORM, DESTINATION_ESCAPE, IDENTITY_UNRESOLVED,
    PERMISSION_DENIED, DESTINATION_OCCUPIED, MANIFEST_CHANGED.
    """

    def __init__(self, code: str, message: str) -> None:
        super().__init__(f"[{code}] {message}")
        self.code = code


HttpGet = Callable[[str], bytes]


_SSL_CONTEXT = ssl.create_default_context(cafile=certifi.where())


def _default_http_get(url: str) -> bytes:
    with urlopen(
        Request(url, headers={"User-Agent": "rush-cli-provision"}),
        timeout=15,
        context=_SSL_CONTEXT,
    ) as resp:
        return resp.read()


def _http_get_json(url: str, http_get: HttpGet, *, not_found_code: str) -> Any:
    try:
        raw = http_get(url)
    except HTTPError as exc:
        if exc.code == 404:
            raise ProvisionError(not_found_code, f"{url} returned 404") from exc
        raise ProvisionError("PACKAGE_NOT_FOUND", f"{url} failed: {exc}") from exc
    except URLError as exc:
        raise ProvisionError("PACKAGE_NOT_FOUND", f"{url} unreachable: {exc}") from exc
    result: Any = json.loads(raw)
    return result


# --- OS/arch normalization --------------------------------------------------

_OS_ALIASES = {"darwin": "macos", "win32": "windows", "linux": "linux"}
_ARCH_ALIASES = {
    "amd64": "x86_64",
    "aarch64": "arm64",
    "x64": "x86_64",
    "arm64": "arm64",
}


def current_os_arch() -> tuple[str, str]:
    os_name = _OS_ALIASES.get(platform.system().lower(), platform.system().lower())
    arch = _ARCH_ALIASES.get(platform.machine().lower(), platform.machine().lower())
    return os_name, arch


class DataRootUnavailableError(Exception):
    """Raised when the platform user-data root cannot be resolved (§6.1)."""


def default_data_root() -> Path:
    """Return the durable per-OS-user Rush data root that owns `toolchains/`.

    Never substitutes the current working directory. Windows raises
    `DataRootUnavailableError` when `%LOCALAPPDATA%` is unset, per §6.1's
    `DATA_ROOT_UNAVAILABLE` contract.
    """
    system = platform.system()
    if system == "Darwin":
        return Path.home() / "Library" / "Application Support" / "Rush"
    if system == "Windows":
        local_app_data = os.environ.get("LOCALAPPDATA")
        if not local_app_data:
            raise DataRootUnavailableError(
                "DATA_ROOT_UNAVAILABLE: %LOCALAPPDATA% is unset"
            )
        return Path(local_app_data) / "Rush"
    xdg_data_home = os.environ.get("XDG_DATA_HOME")
    base = Path(xdg_data_home) if xdg_data_home else Path.home() / ".local" / "share"
    return base / "rush"


# --- Resolved identity -------------------------------------------------------


@dataclass(frozen=True)
class ResolvedIdentity:
    """Exact, pinned engine identity captured before any install occurs."""

    version: str
    url: str | None
    digest_algo: str | None
    digest_value: str | None


def _go_module_escape(module: str) -> str:
    """Go module proxy case-encoding: each uppercase letter becomes `!` + lower."""
    return "".join(f"!{c.lower()}" if c.isupper() else c for c in module)


def _maven_url(package_id: str) -> str:
    group_id, artifact_id = package_id.split(":", 1)
    query = f"g:{group_id}+AND+a:{artifact_id}"
    return (
        f"https://search.maven.org/solrsearch/select?q={query}&core=gav&rows=1&wt=json"
    )


# The one registry GET per source. `resolution_url` shows it in previews and
# every resolver requests exactly it, so a preview never under-reports.
_REGISTRY_URLS: dict[str, Callable[[str], str]] = {
    "pypi": lambda pid: f"https://pypi.org/pypi/{pid}/json",
    "npm": lambda pid: f"https://registry.npmjs.org/{pid.replace('/', '%2F')}",
    "crates": lambda pid: f"https://crates.io/api/v1/crates/{pid}",
    "gem": lambda pid: f"https://rubygems.org/api/v1/versions/{pid}.json",
    "composer": lambda pid: f"https://repo.packagist.org/p2/{pid}.json",
    "maven": _maven_url,
    "github": lambda pid: f"https://api.github.com/repos/{pid}/releases/latest",
    "go": lambda pid: (
        f"https://proxy.golang.org/{_go_module_escape('github.com/' + pid)}/@latest"
    ),
}


def resolution_url(engine: EnginePackage) -> str | None:
    """The exact GET `resolve_identity` makes for `engine`, or None when
    resolving needs no request (a pinned go version) or cannot resolve."""
    if engine.source == "go" and ":" in engine.version_policy:
        return None
    builder = _REGISTRY_URLS.get(engine.source)
    return builder(engine.package_id) if builder is not None else None


def _resolve_pypi(package_id: str, http_get: HttpGet) -> ResolvedIdentity:
    data = _http_get_json(
        _REGISTRY_URLS["pypi"](package_id),
        http_get,
        not_found_code="PACKAGE_NOT_FOUND",
    )
    version = data.get("info", {}).get("version")
    if not version:
        raise ProvisionError(
            "VERSION_UNAVAILABLE", f"no stable version for {package_id}"
        )
    releases = data.get("releases", {}).get(version, [])
    dist = next((r for r in releases if r.get("packagetype") == "bdist_wheel"), None)
    dist = dist or next(iter(releases), None)
    if dist is None:
        raise ProvisionError(
            "VERSION_UNAVAILABLE", f"no distribution for {package_id}=={version}"
        )
    sha256 = dist.get("digests", {}).get("sha256")
    if not sha256:
        raise ProvisionError(
            "INTEGRITY_UNAVAILABLE", f"{package_id}=={version} has no sha256 digest"
        )
    return ResolvedIdentity(version, dist.get("url"), "sha256", sha256)


def _resolve_npm(package_id: str, http_get: HttpGet) -> ResolvedIdentity:
    data = _http_get_json(
        _REGISTRY_URLS["npm"](package_id),
        http_get,
        not_found_code="PACKAGE_NOT_FOUND",
    )
    version = data.get("dist-tags", {}).get("latest")
    if not version:
        raise ProvisionError(
            "VERSION_UNAVAILABLE", f"no dist-tags.latest for {package_id}"
        )
    dist = data.get("versions", {}).get(version, {}).get("dist", {})
    integrity = dist.get("integrity")
    if not integrity or "-" not in integrity:
        raise ProvisionError(
            "INTEGRITY_UNAVAILABLE", f"{package_id}@{version} has no dist.integrity"
        )
    algo, value = integrity.split("-", 1)
    return ResolvedIdentity(version, dist.get("tarball"), algo, value)


def _resolve_crates(package_id: str, http_get: HttpGet) -> ResolvedIdentity:
    data = _http_get_json(
        _REGISTRY_URLS["crates"](package_id),
        http_get,
        not_found_code="PACKAGE_NOT_FOUND",
    )
    versions = [v for v in data.get("versions", []) if not v.get("yanked")]
    if not versions:
        raise ProvisionError(
            "VERSION_UNAVAILABLE", f"no non-yanked version for {package_id}"
        )
    latest = versions[0]
    checksum = latest.get("checksum")
    if not checksum:
        raise ProvisionError("INTEGRITY_UNAVAILABLE", f"{package_id} has no checksum")
    return ResolvedIdentity(latest["num"], None, "sha256", checksum)


def _resolve_gem(package_id: str, http_get: HttpGet) -> ResolvedIdentity:
    data = _http_get_json(
        _REGISTRY_URLS["gem"](package_id),
        http_get,
        not_found_code="PACKAGE_NOT_FOUND",
    )
    versions = [v for v in data if not v.get("prerelease")]
    if not versions:
        raise ProvisionError(
            "VERSION_UNAVAILABLE", f"no stable version for gem {package_id}"
        )
    latest = versions[0]
    sha = latest.get("sha")
    if not sha:
        raise ProvisionError("INTEGRITY_UNAVAILABLE", f"gem {package_id} has no sha")
    return ResolvedIdentity(latest["number"], None, "sha256", sha)


def _resolve_composer(package_id: str, http_get: HttpGet) -> ResolvedIdentity:
    data = _http_get_json(
        _REGISTRY_URLS["composer"](package_id),
        http_get,
        not_found_code="PACKAGE_NOT_FOUND",
    )
    packages = data.get("packages", {}).get(package_id, [])
    stable = next(
        (
            p
            for p in packages
            if p.get("version_normalized", "").split(".")[-1].isdigit() or True
        ),
        None,
    )
    if not stable:
        raise ProvisionError(
            "VERSION_UNAVAILABLE", f"no version for composer package {package_id}"
        )
    dist = stable.get("dist", {})
    sha = dist.get("shasum")
    if not sha:
        raise ProvisionError(
            "INTEGRITY_UNAVAILABLE", f"composer package {package_id} has no shasum"
        )
    return ResolvedIdentity(stable["version"], dist.get("url"), "sha1", sha)


def _resolve_maven(package_id: str, http_get: HttpGet) -> ResolvedIdentity:
    data = _http_get_json(
        _REGISTRY_URLS["maven"](package_id),
        http_get,
        not_found_code="PACKAGE_NOT_FOUND",
    )
    docs = data.get("response", {}).get("docs", [])
    if not docs:
        raise ProvisionError("VERSION_UNAVAILABLE", f"no artifact for {package_id}")
    return ResolvedIdentity(docs[0]["v"], None, None, None)


def _resolve_github(
    repo: str, engine: EnginePackage, os_name: str, arch: str, http_get: HttpGet
) -> ResolvedIdentity:
    data = _http_get_json(
        _REGISTRY_URLS["github"](repo),
        http_get,
        not_found_code="PACKAGE_NOT_FOUND",
    )
    if data.get("draft") or data.get("prerelease"):
        raise ProvisionError(
            "VERSION_UNAVAILABLE", f"latest release of {repo} is draft/prerelease"
        )
    version = data.get("tag_name")
    if not version:
        raise ProvisionError("VERSION_UNAVAILABLE", f"{repo} release has no tag_name")
    assets = data.get("assets", [])
    os_tokens = {os_name, {"macos": "darwin"}.get(os_name, os_name)}
    arch_tokens = {arch, {"x86_64": "amd64", "arm64": "aarch64"}.get(arch, arch)}
    matches = [
        a
        for a in assets
        if any(t in a.get("name", "").lower() for t in os_tokens)
        and any(t in a.get("name", "").lower() for t in arch_tokens)
    ]
    archives = [
        a for a in matches if a.get("name", "").lower().endswith((".tar.gz", ".zip"))
    ]
    candidates = archives or matches
    if not candidates:
        raise ProvisionError(
            "NO_COMPATIBLE_ASSET", f"no asset for {repo} matching {os_name}/{arch}"
        )
    if len(candidates) > 1:
        raise ProvisionError(
            "AMBIGUOUS_ASSET", f"multiple matching assets for {repo} {os_name}/{arch}"
        )
    asset = candidates[0]
    digest = asset.get("digest")
    if digest and digest.startswith("sha256:"):
        return ResolvedIdentity(
            version, asset["browser_download_url"], "sha256", digest.split(":", 1)[1]
        )
    raise ProvisionError(
        "INTEGRITY_UNAVAILABLE",
        f"{repo} asset {asset.get('name')} has no published digest",
    )


def _resolve_go(engine: EnginePackage, http_get: HttpGet) -> ResolvedIdentity:
    """A pinned policy needs no request. Otherwise the Go module proxy's
    `@latest` names a concrete version; the proxy publishes no artifact
    digest, so the identity carries none and previews report integrity as
    unavailable."""
    if ":" in engine.version_policy:
        return ResolvedIdentity(
            engine.version_policy.split(":", 1)[1], None, None, None
        )
    url = _REGISTRY_URLS["go"](engine.package_id)
    data = _http_get_json(url, http_get, not_found_code="PACKAGE_NOT_FOUND")
    version = data.get("Version") if isinstance(data, dict) else None
    if not isinstance(version, str) or not version:
        raise ProvisionError("VERSION_UNAVAILABLE", f"{url} returned no Version")
    return ResolvedIdentity(version, url, None, None)


_RESOLVERS: dict[str, Callable[..., ResolvedIdentity]] = {
    "pypi": lambda engine, os_name, arch, http_get: _resolve_pypi(
        engine.package_id, http_get
    ),
    "npm": lambda engine, os_name, arch, http_get: _resolve_npm(
        engine.package_id, http_get
    ),
    "crates": lambda engine, os_name, arch, http_get: _resolve_crates(
        engine.package_id, http_get
    ),
    "gem": lambda engine, os_name, arch, http_get: _resolve_gem(
        engine.package_id, http_get
    ),
    "composer": lambda engine, os_name, arch, http_get: _resolve_composer(
        engine.package_id, http_get
    ),
    "maven": lambda engine, os_name, arch, http_get: _resolve_maven(
        engine.package_id, http_get
    ),
    "github": lambda engine, os_name, arch, http_get: _resolve_github(
        engine.package_id, engine, os_name, arch, http_get
    ),
    "go": lambda engine, os_name, arch, http_get: _resolve_go(engine, http_get),
}


def resolve_identity(
    engine: EnginePackage,
    *,
    os_name: str,
    arch: str,
    http_get: HttpGet = _default_http_get,
) -> ResolvedIdentity:
    """Resolve an exact, hash-pinned identity for one engine's declared source."""
    resolver = _RESOLVERS.get(engine.source)
    if resolver is None:
        raise ProvisionError(
            "VERSION_UNAVAILABLE",
            f"{engine.engine_id} has no resolvable registry identity",
        )
    return resolver(engine, os_name, arch, http_get)


# --- Grants required per source --------------------------------------------

_SOURCE_GRANTS: dict[str, tuple[str, ...]] = {
    "pypi": ("network", "download", "cache_write"),
    "npm": ("network", "download", "cache_write"),
    "crates": ("network", "download", "cache_write", "build"),
    "gem": ("network", "download", "cache_write"),
    "composer": ("network", "download", "cache_write"),
    "maven": ("network", "download", "cache_write", "build"),
    "github": ("network", "download", "cache_write"),
    "go": ("network", "download", "cache_write", "build"),
    "alias": (),
    "internal": (),
}

_GRANT_FLAGS: dict[str, str] = {
    "network": "--allow-network",
    "download": "--allow-download",
    "cache_write": "--allow-cache-write",
    "build": "--allow-build",
}

# Canonical flag order -- matches the order grants appear in `_SOURCE_GRANTS`
# tuples above, so a single-source lookup emits identically to before.
_GRANT_ORDER: tuple[str, ...] = ("network", "download", "cache_write", "build")


def setup_action_command(root: Path, entries: list[EnginePackage]) -> str:
    """The exact `rush setup` route to provision `entries` (S15.5).

    Single shared builder for the doctor readiness action string -- T24
    updates non-interactive apply flags here, in one place, for every
    caller. Grants are the union of every entry's source grants
    (`_SOURCE_GRANTS`), in canonical flag order; a single-entry call
    reproduces exactly one source's grant list.
    """
    grants: set[str] = set()
    for entry in entries:
        grants.update(_SOURCE_GRANTS.get(entry.source, ()))
    flags = " ".join(_GRANT_FLAGS[g] for g in _GRANT_ORDER if g in grants)
    quoted_root = shlex.quote(str(root.resolve()))
    base = f"rush setup {quoted_root} --install"
    return f"{base} {flags}" if flags else base


# --- Plan -------------------------------------------------------------------


@dataclass(frozen=True)
class ProvisionPlanEntry:
    engine_id: str
    package_id: str
    source: str
    manager: str
    disposition: str  # applicable | requires_input | unsupported
    required_grants: tuple[str, ...]
    prerequisites: tuple[str, ...]
    destination: str
    probe: tuple[str, ...]
    # Phase 70 T24 reviewed identity. Only a `resolved` entry is installable;
    # `reuse_verified` binds the project's existing verified manifest.
    # `blocked_reason` names a missing manager seen at preview time;
    # `resolution_error` is the code of a failed resolution.
    identity: ResolvedIdentity | None = None
    identity_state: str = (
        "unresolved"  # unresolved|resolved|reuse_verified|resolution_failed
    )
    blocked_reason: str | None = None
    resolution_error: str | None = None


@dataclass(frozen=True)
class ProvisionPlan:
    plan_id: str
    project_root: str
    os_name: str
    arch: str
    entries: tuple[ProvisionPlanEntry, ...]
    data_root: str = ""


def _canonical_json(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _toolchains_root(data_root: Path) -> Path:
    return data_root / "toolchains"


def _destination_for(
    data_root: Path, engine_id: str, version: str, os_name: str, arch: str
) -> Path:
    return _toolchains_root(data_root) / engine_id / version / f"{os_name}-{arch}"


def compute_plan_id(
    *,
    project_root: str,
    data_root: str,
    os_name: str,
    arch: str,
    entries: tuple[ProvisionPlanEntry, ...],
) -> str:
    """Canonical SHA-256 over both roots, the platform, and every entry field
    (frozen identity and concrete destination included)."""
    payload = {
        "project_root": project_root,
        "data_root": data_root,
        "os": os_name,
        "arch": arch,
        "entries": [asdict(e) for e in entries],
    }
    return hashlib.sha256(_canonical_json(payload)).hexdigest()


def _make_plan(
    project_root: str,
    data_root: str,
    os_name: str,
    arch: str,
    entries: tuple[ProvisionPlanEntry, ...],
) -> ProvisionPlan:
    plan_id = compute_plan_id(
        project_root=project_root,
        data_root=data_root,
        os_name=os_name,
        arch=arch,
        entries=entries,
    )
    return ProvisionPlan(
        plan_id=plan_id,
        project_root=project_root,
        os_name=os_name,
        arch=arch,
        entries=entries,
        data_root=data_root,
    )


def _is_contained(path: Path, data_root: Path) -> bool:
    """True when `path` lies strictly below `data_root/toolchains`."""
    root = _toolchains_root(data_root).resolve()
    target = path.resolve()
    return target != root and target.is_relative_to(root)


def _verified_manifest_at(
    dest: Path, engine_id: str, version: str, project_root: Path
) -> ProvisionManifest | None:
    manifest = read_manifest(dest / MANIFEST_FILENAME)
    if manifest is None or (manifest.engine_id, manifest.version) != (
        engine_id,
        version,
    ):
        return None
    try:
        verify_manifest(manifest, project_root=project_root)
    except ManifestVerificationError:
        return None
    return manifest


def _reusable_selection(
    project_root: Path, data_root: Path, engine_id: str, os_name: str, arch: str
) -> tuple[ProvisionManifest, Path] | None:
    """Read-only local resolution: the project's selected manifest for
    `engine_id` when it is for this platform, lives under this data root's
    toolchains, and verifies. Returns `(manifest, destination)`."""
    try:
        selection = json.loads(
            (project_root / ".rush" / "toolchains.json").read_text(encoding="utf-8")
        )
    except (OSError, ValueError):
        return None
    chosen = selection.get(engine_id) if isinstance(selection, dict) else None
    manifest_path = chosen.get("manifest") if isinstance(chosen, dict) else None
    if not isinstance(manifest_path, str):
        return None
    dest = Path(manifest_path).parent
    manifest = read_manifest(Path(manifest_path))
    if manifest is None or (manifest.os_name, manifest.arch) != (os_name, arch):
        return None
    if not _is_contained(dest, data_root):
        return None
    if _verified_manifest_at(dest, engine_id, manifest.version, project_root) is None:
        return None
    return manifest, dest


def _plan_entry(
    engine: EnginePackage,
    project_root: Path,
    data_root: Path,
    os_name: str,
    arch: str,
    which: Callable[[str], str | None],
) -> ProvisionPlanEntry:
    entry = ProvisionPlanEntry(
        engine_id=engine.engine_id,
        package_id=engine.package_id,
        source=engine.source,
        manager=engine.manager,
        disposition="requires_input" if engine.source == "internal" else "applicable",
        required_grants=_SOURCE_GRANTS.get(engine.source, ()),
        prerequisites=engine.prerequisites,
        destination=str(
            _destination_for(data_root, engine.engine_id, "<version>", os_name, arch)
        ),
        probe=engine.probe,
    )
    if entry.disposition != "applicable":
        return entry
    reusable = _reusable_selection(
        project_root, data_root, engine.engine_id, os_name, arch
    )
    if reusable is not None:
        manifest, dest = reusable
        return replace(
            entry,
            required_grants=(),
            destination=str(dest),
            identity=ResolvedIdentity(manifest.version, None, None, None),
            identity_state="reuse_verified",
        )
    manager = _MANAGER_BINARIES.get(engine.source)
    if manager is not None and which(manager) is None:
        return replace(entry, blocked_reason="SYSTEM_PREREQUISITE_REQUIRED")
    return entry


def build_provision_plan(
    project_root: Path,
    engine_ids: list[str],
    *,
    os_name: str | None = None,
    arch: str | None = None,
    data_root: Path | None = None,
    which: Callable[[str], str | None] = shutil.which,
) -> ProvisionPlan:
    """Build an immutable provision plan for exactly the requested engines.

    Raises `UnknownEngineError` immediately for any id outside the declared
    `ENGINE_PACKAGES` allowlist -- no arbitrary package is ever planned.
    Read-only and offline: an engine whose project selection already has a
    verified manifest is `reuse_verified`; every other applicable engine
    stays `unresolved` until `resolve_provision_identities` runs under the
    network grant. A missing package manager is reported as
    `blocked_reason="SYSTEM_PREREQUISITE_REQUIRED"` so the preview shows it.
    """
    resolved_os, resolved_arch = (
        (os_name, arch) if os_name and arch else current_os_arch()
    )
    root = project_root.resolve()
    data = data_root if data_root is not None else default_data_root()
    engines = [resolve_engine_package(e) for e in engine_ids]  # UnknownEngineError
    entries = tuple(
        _plan_entry(engine, root, data, resolved_os, resolved_arch, which)
        for engine in engines
    )
    return _make_plan(str(root), str(data), resolved_os, resolved_arch, entries)


def _resolve_entry(
    entry: ProvisionPlanEntry, plan: ProvisionPlan, http_get: HttpGet
) -> ProvisionPlanEntry:
    if entry.disposition != "applicable" or entry.identity_state != "unresolved":
        return entry
    try:
        identity = resolve_identity(
            ENGINE_PACKAGES[entry.engine_id],
            os_name=plan.os_name,
            arch=plan.arch,
            http_get=http_get,
        )
    except ProvisionError as exc:
        return replace(
            entry, identity_state="resolution_failed", resolution_error=exc.code
        )
    except (ValueError, KeyError, TypeError, AttributeError):
        # A registry answer that is not the documented shape.
        return replace(
            entry,
            identity_state="resolution_failed",
            resolution_error="VERSION_UNAVAILABLE",
        )
    destination = _destination_for(
        Path(plan.data_root), entry.engine_id, identity.version, plan.os_name, plan.arch
    )
    return replace(
        entry,
        identity=identity,
        identity_state="resolved",
        destination=str(destination),
    )


def resolve_provision_identities(
    plan: ProvisionPlan,
    permissions: ExecutionPermissions | None,
    *,
    http_get: HttpGet = _default_http_get,
) -> ProvisionPlan:
    """Freeze a concrete identity and destination for every unresolved
    applicable entry, returning a new plan with a new plan_id.

    Requires the `network` grant, checked before any request, and requests
    only each entry's `resolution_url`. A failed resolution leaves the entry
    `resolution_failed` with its error code; it is not installable.
    """
    ok, missing = check_permissions(ExecutionPermissions(network=True), permissions)
    if not ok:
        raise ProvisionError(
            "PERMISSION_DENIED", f"identity resolution requires {', '.join(missing)}"
        )
    entries = tuple(_resolve_entry(e, plan, http_get) for e in plan.entries)
    return _make_plan(
        plan.project_root, plan.data_root, plan.os_name, plan.arch, entries
    )


def _integrity(entry: ProvisionPlanEntry) -> str:
    """What byte-level verification the reviewed identity allows."""
    identity = entry.identity
    if entry.identity_state == "reuse_verified":
        return "installed_manifest_verified"
    if identity is None:
        return "unresolved"
    if identity.digest_value is None:
        return "unavailable"
    if entry.source == "github":
        return "download_digest_verified"
    # The package manager fetches the artifact itself; Rush cannot attest the
    # installed bytes against the registry digest, only hash what it installed.
    return "source_digest_unattested"


def plan_to_dict(plan: ProvisionPlan) -> dict[str, Any]:
    """JSON-ready full plan, with each entry's exact resolution request and
    integrity class added for review."""
    data = asdict(plan)
    for raw, entry in zip(data["entries"], plan.entries, strict=True):
        engine = ENGINE_PACKAGES.get(entry.engine_id)
        raw["resolution_url"] = (
            resolution_url(engine)
            if engine is not None and entry.identity_state == "unresolved"
            else None
        )
        raw["integrity"] = _integrity(entry)
    return data


def plan_from_dict(data: dict[str, Any]) -> ProvisionPlan:
    """Rebuild a plan from `plan_to_dict` output. Apply recomputes its
    plan_id, so any edit to the payload is rejected as PLAN_TAMPERED.
    Malformed input raises KeyError/TypeError/ValueError."""

    def entry(e: dict[str, Any]) -> ProvisionPlanEntry:
        identity = e.get("identity")
        return ProvisionPlanEntry(
            engine_id=str(e["engine_id"]),
            package_id=str(e["package_id"]),
            source=str(e["source"]),
            manager=str(e["manager"]),
            disposition=str(e["disposition"]),
            required_grants=tuple(e["required_grants"]),
            prerequisites=tuple(e["prerequisites"]),
            destination=str(e["destination"]),
            probe=tuple(e["probe"]),
            identity=ResolvedIdentity(**identity) if identity is not None else None,
            identity_state=str(e["identity_state"]),
            blocked_reason=e.get("blocked_reason"),
            resolution_error=e.get("resolution_error"),
        )

    return ProvisionPlan(
        plan_id=str(data["plan_id"]),
        project_root=str(data["project_root"]),
        os_name=str(data["os_name"]),
        arch=str(data["arch"]),
        entries=tuple(entry(e) for e in data["entries"]),
        data_root=str(data["data_root"]),
    )


# --- Apply -------------------------------------------------------------------

Downloader = Callable[[str], bytes]
Runner = Callable[[list[str], dict[str, str] | None], subprocess.CompletedProcess[str]]
Prober = Callable[[list[str]], subprocess.CompletedProcess[str]]


def _default_downloader(url: str) -> bytes:
    return _default_http_get(url)


def _default_runner(
    argv: list[str], env: dict[str, str] | None = None
) -> subprocess.CompletedProcess[str]:
    merged_env = {**os.environ, **env} if env else None
    return subprocess.run(
        argv, capture_output=True, text=True, timeout=600, check=False, env=merged_env
    )


def _default_prober(argv: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(argv, capture_output=True, text=True, timeout=30, check=False)


def _verify_digest(data: bytes, algo: str | None, value: str | None) -> None:
    if algo is None or value is None:
        return
    if algo == "sha256":
        actual = hashlib.sha256(data).hexdigest()
        if actual != value:
            raise ProvisionError(
                "INTEGRITY_MISMATCH", f"sha256 {actual} != expected {value}"
            )
    elif algo == "sha1":
        actual = hashlib.sha1(data).hexdigest()
        if actual != value:
            raise ProvisionError(
                "INTEGRITY_MISMATCH", f"sha1 {actual} != expected {value}"
            )
    elif algo in ("sha512", "sha256") or algo.startswith("sha"):
        import base64

        hasher = hashlib.new(algo)
        hasher.update(data)
        actual_b64 = base64.b64encode(hasher.digest()).decode("ascii")
        if actual_b64 != value:
            raise ProvisionError("INTEGRITY_MISMATCH", f"{algo} digest mismatch")
    else:
        raise ProvisionError(
            "INTEGRITY_UNAVAILABLE", f"unsupported digest algorithm {algo}"
        )


def _safe_extract_binary(
    archive_bytes: bytes, url: str, binary_name: str, dest_dir: Path
) -> Path:
    """Extract exactly the named binary from a tar.gz/zip archive, or treat as raw bytes.

    Guards against path traversal (Zip Slip): only a member whose resolved
    path stays inside `dest_dir` and whose basename matches `binary_name`
    (optionally with a platform executable suffix) is ever written.
    """
    dest_dir.mkdir(parents=True, exist_ok=True)
    candidates = {binary_name, binary_name + ".exe"}
    lowered = url.lower()
    if lowered.endswith((".tar.gz", ".tgz")):
        with tarfile.open(fileobj=io.BytesIO(archive_bytes), mode="r:gz") as tar:
            member = next(
                (
                    m
                    for m in tar.getmembers()
                    if Path(m.name).name in candidates and m.isfile()
                ),
                None,
            )
            if member is None:
                raise ProvisionError(
                    "NO_COMPATIBLE_ASSET", f"no {binary_name} inside archive"
                )
            target = (dest_dir / Path(member.name).name).resolve()
            if not target.is_relative_to(dest_dir.resolve()):
                raise ProvisionError(
                    "NO_COMPATIBLE_ASSET", "archive member escapes destination"
                )
            extracted = tar.extractfile(member)
            if extracted is None:
                raise ProvisionError(
                    "NO_COMPATIBLE_ASSET", f"could not read {member.name}"
                )
            target.write_bytes(extracted.read())
            target.chmod(0o755)
            return target
    if lowered.endswith(".zip"):
        with zipfile.ZipFile(io.BytesIO(archive_bytes)) as zf:
            zip_member = next(
                (n for n in zf.namelist() if Path(n).name in candidates), None
            )
            if zip_member is None:
                raise ProvisionError(
                    "NO_COMPATIBLE_ASSET", f"no {binary_name} inside archive"
                )
            target = (dest_dir / Path(zip_member).name).resolve()
            if not target.is_relative_to(dest_dir.resolve()):
                raise ProvisionError(
                    "NO_COMPATIBLE_ASSET", "archive member escapes destination"
                )
            target.write_bytes(zf.read(zip_member))
            target.chmod(0o755)
            return target
    # Raw single-binary asset (no archive extension recognized).
    target = dest_dir / binary_name
    target.write_bytes(archive_bytes)
    target.chmod(0o755)
    return target


_MANAGER_BINARIES: dict[str, str] = {
    "pypi": "uv",
    "npm": "npm",
    "crates": "cargo",
    "gem": "gem",
    "composer": "composer",
    "maven": "mvn",
    "go": "go",
}


def _check_manager_available(
    engine: EnginePackage, which: Callable[[str], str | None] = shutil.which
) -> None:
    """Raise SYSTEM_PREREQUISITE_REQUIRED naming the exact missing manager binary.

    Bootstrapping an absent manager/runtime via its own verified download is
    real network I/O infeasible in this sandbox; this reports the precise
    unresolved prerequisite instead of silently attempting an install.
    """
    manager_binary = _MANAGER_BINARIES.get(engine.source)
    if manager_binary is not None and which(manager_binary) is None:
        raise ProvisionError(
            "SYSTEM_PREREQUISITE_REQUIRED",
            f"required manager '{manager_binary}' is not installed",
        )


# Manager-specific install command builders for registry-resolved sources.
# Each returns the argv Rush executes to install the exact pinned version
# into an isolated, Rush-owned destination directory.
def _manager_install_command(
    engine: EnginePackage, version: str, dest: Path
) -> tuple[str, ...]:
    if engine.source == "pypi":
        return ("uv", "tool", "install", "--force", f"{engine.package_id}=={version}")
    if engine.source == "npm":
        return (
            "npm",
            "install",
            "--global",
            "--prefix",
            str(dest),
            "--ignore-scripts",
            f"{engine.package_id}@{version}",
        )
    if engine.source == "crates":
        return (
            "cargo",
            "install",
            engine.package_id,
            "--version",
            version,
            "--locked",
            "--root",
            str(dest),
        )
    if engine.source == "gem":
        return (
            "gem",
            "install",
            engine.package_id,
            "--version",
            version,
            "--install-dir",
            str(dest),
            "--no-document",
        )
    if engine.source == "composer":
        return (
            "composer",
            "require",
            f"{engine.package_id}:{version}",
            "--no-interaction",
            "--no-scripts",
            "--working-dir",
            str(dest),
        )
    if engine.source == "maven":
        return ("mvn", "dependency:get", f"-Dartifact={engine.package_id}:{version}")
    if engine.source == "go":
        return ("go", "install", f"github.com/{engine.package_id}@{version}")
    raise ProvisionError(
        "NO_COMPATIBLE_ASSET", f"no install command for source {engine.source}"
    )


@dataclass
class ProvisionOutcome:
    engine_id: str
    manifest: ProvisionManifest | None = None
    failed_code: str | None = None
    failed_message: str | None = None


@dataclass
class ProvisionResult:
    applied: dict[str, ProvisionManifest] = field(default_factory=dict)
    failed: dict[str, dict[str, str]] = field(default_factory=dict)
    permission_blocked: dict[str, list[str]] = field(default_factory=dict)
    requires_input: list[str] = field(default_factory=list)
    # Phase 70 T24 (additive): verified installs kept as-is, destinations
    # that need manual recovery (engine -> path), where the applied identity
    # came from, and the plan that was applied.
    reused: dict[str, ProvisionManifest] = field(default_factory=dict)
    recovery_required: dict[str, str] = field(default_factory=dict)
    identity_source: str = "frozen_review"
    plan_id: str = ""


OWNER_MARKER = ".rush-provision-owner.json"


@dataclass(frozen=True)
class _ApplyContext:
    plan: ProvisionPlan
    project_id: str
    project_root: Path
    data_root: Path
    txid: str
    identity_source: str
    downloader: Downloader
    runner: Runner
    prober: Prober
    which: Callable[[str], str | None]


def _update_selection(project_root: Path, engine_id: str, manifest_path: Path) -> None:
    selection_dir = project_root / ".rush"
    selection_dir.mkdir(parents=True, exist_ok=True)
    selection_path = selection_dir / "toolchains.json"
    try:
        current = json.loads(selection_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        current = {}
    if not isinstance(current, dict):
        current = {}
    current[engine_id] = {"manifest": str(manifest_path)}
    with tempfile.NamedTemporaryFile(
        dir=selection_dir, delete=False, mode="w", encoding="utf-8"
    ) as handle:
        json.dump(current, handle, sort_keys=True, indent=2)
        temp_path = Path(handle.name)
    os.replace(temp_path, selection_path)


def _plan_rejection(
    plan: ProvisionPlan, reviewed_plan_id: str, current_platform: tuple[str, str]
) -> tuple[str, str] | None:
    """Plan-level checks that reject every entry before any effect."""
    recomputed = compute_plan_id(
        project_root=plan.project_root,
        data_root=plan.data_root,
        os_name=plan.os_name,
        arch=plan.arch,
        entries=plan.entries,
    )
    if recomputed != plan.plan_id or reviewed_plan_id != plan.plan_id:
        return "PLAN_TAMPERED", "plan content does not match the reviewed plan_id"
    for e in plan.entries:
        engine = ENGINE_PACKAGES.get(e.engine_id)
        if engine is None:
            return "PLAN_TAMPERED", f"{e.engine_id} is not an allowlisted engine"
        grants = (
            ()
            if e.identity_state == "reuse_verified"
            else _SOURCE_GRANTS.get(engine.source, ())
        )
        if (
            e.package_id,
            e.source,
            e.manager,
            tuple(e.probe),
            tuple(e.required_grants),
        ) != (
            engine.package_id,
            engine.source,
            engine.manager,
            engine.probe,
            grants,
        ):
            return (
                "PLAN_TAMPERED",
                f"{e.engine_id} package metadata differs from the allowlist",
            )
    if (plan.os_name, plan.arch) != current_platform:
        return (
            "WRONG_PLATFORM",
            (
                f"plan is for {plan.os_name}/{plan.arch}, this machine is "
                f"{current_platform[0]}/{current_platform[1]}"
            ),
        )
    return None


def _missing_grants(
    plan: ProvisionPlan, permissions: ExecutionPermissions | None
) -> dict[str, list[str]]:
    missing: dict[str, list[str]] = {}
    for entry in plan.entries:
        if entry.disposition != "applicable" or not entry.required_grants:
            continue
        ok, flags = check_permissions(
            ExecutionPermissions(**{g: True for g in entry.required_grants}),
            permissions,
        )
        if not ok:
            missing[entry.engine_id] = flags
    return missing


def _checked_destination(
    entry: ProvisionPlanEntry, identity: ResolvedIdentity, ctx: _ApplyContext
) -> Path:
    expected = _destination_for(
        ctx.data_root,
        entry.engine_id,
        identity.version,
        ctx.plan.os_name,
        ctx.plan.arch,
    )
    if entry.destination != str(expected) or not _is_contained(expected, ctx.data_root):
        raise ProvisionError(
            "DESTINATION_ESCAPE",
            f"{entry.destination} is not the reviewed destination under "
            f"{_toolchains_root(ctx.data_root)}",
        )
    return expected


def _read_owner_marker(dest: Path) -> dict[str, Any] | None:
    try:
        data = json.loads((dest / OWNER_MARKER).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def _claim_destination(
    dest: Path,
    entry: ProvisionPlanEntry,
    identity: ResolvedIdentity,
    ctx: _ApplyContext,
) -> None:
    """Own `dest` for this transaction before any install writes into it.

    A new destination is created exclusively. An existing one is taken over
    only when its ownership marker names this exact frozen identity (a prior
    Rush attempt); its partial contents are then cleared. Anything else is
    DESTINATION_OCCUPIED and is never modified or deleted.
    """
    if dest.exists():
        owner = _read_owner_marker(dest)
        if (
            owner is None
            or owner.get("engine_id") != entry.engine_id
            or owner.get("identity") != asdict(identity)
        ):
            raise ProvisionError(
                "DESTINATION_OCCUPIED",
                f"{dest} exists and is not a Rush partial install of this reviewed "
                "identity; move or remove it, then rerun setup",
            )
        if not (dest / MANIFEST_FILENAME).exists():
            for child in dest.iterdir():
                if child.name == OWNER_MARKER:
                    continue
                if child.is_dir() and not child.is_symlink():
                    shutil.rmtree(child)
                else:
                    child.unlink()
    else:
        dest.parent.mkdir(parents=True, exist_ok=True)
        try:
            dest.mkdir()
        except FileExistsError as exc:
            raise ProvisionError(
                "DESTINATION_OCCUPIED", f"{dest} was created concurrently"
            ) from exc
    marker = {
        "txid": ctx.txid,
        "plan_id": ctx.plan.plan_id,
        "engine_id": entry.engine_id,
        "identity": asdict(identity),
        "identity_source": ctx.identity_source,
    }
    (dest / OWNER_MARKER).write_text(
        json.dumps(marker, sort_keys=True, indent=2), encoding="utf-8"
    )


def _install_into(
    engine: EnginePackage,
    identity: ResolvedIdentity,
    dest: Path,
    ctx: _ApplyContext,
) -> Path:
    """Install exactly `identity.version` into `dest`; return the executable."""
    if engine.source == "github":
        if identity.url is None:
            raise ProvisionError(
                "NO_COMPATIBLE_ASSET", f"{engine.engine_id} has no download URL"
            )
        data = ctx.downloader(identity.url)
        _verify_digest(data, identity.digest_algo, identity.digest_value)
        return _safe_extract_binary(data, identity.url, engine.binary, dest)
    argv = list(_manager_install_command(engine, identity.version, dest))
    env: dict[str, str] | None = None
    if engine.source == "go":
        env = {"GOBIN": str(dest)}
    elif engine.source == "pypi":
        # `uv tool install` ignores the positional dest we pass it and always
        # installs into uv's own global tool directory; these two env vars are
        # uv's real mechanism for redirecting that (verified directly: a shim
        # lands at UV_TOOL_BIN_DIR pointing into UV_TOOL_DIR, and is directly
        # executable from there).
        env = {"UV_TOOL_DIR": str(dest / "tools"), "UV_TOOL_BIN_DIR": str(dest)}
    try:
        proc = ctx.runner(argv, env)
    except OSError as exc:
        raise ProvisionError(
            "SYSTEM_PREREQUISITE_REQUIRED", f"could not execute {argv[0]}: {exc}"
        ) from exc
    if proc.returncode != 0:
        raise ProvisionError(
            "SYSTEM_PREREQUISITE_REQUIRED",
            f"install command failed: {' '.join(argv)}",
        )
    found = shutil.which(engine.binary, path=str(dest)) or shutil.which(
        engine.binary, path=str(dest / "bin")
    )
    executable = Path(found) if found else dest / engine.binary
    if not executable.is_file():
        raise ProvisionError(
            "ENGINE_PROTOCOL_MISMATCH",
            f"{engine.engine_id} binary not found after install",
        )
    return executable


def _apply_entry(
    entry: ProvisionPlanEntry, ctx: _ApplyContext, result: ProvisionResult
) -> None:
    engine = ENGINE_PACKAGES[entry.engine_id]
    identity = entry.identity
    if entry.identity_state == "reuse_verified" and identity is not None:
        dest = Path(entry.destination)
        reused = (
            _verified_manifest_at(
                dest, entry.engine_id, identity.version, ctx.project_root
            )
            if _is_contained(dest, ctx.data_root)
            else None
        )
        if reused is None:
            raise ProvisionError(
                "MANIFEST_CHANGED",
                f"the verified {entry.engine_id} manifest at {dest} no longer "
                "verifies; review setup again",
            )
        result.reused[entry.engine_id] = reused
        return
    if engine.source != "github":
        _check_manager_available(engine, ctx.which)
    if entry.identity_state != "resolved" or identity is None:
        raise ProvisionError(
            "IDENTITY_UNRESOLVED",
            f"{entry.engine_id} has no reviewed identity "
            f"({entry.resolution_error or entry.identity_state}); review again "
            "with --allow-network to resolve it",
        )
    dest = _checked_destination(entry, identity, ctx)
    existing = _verified_manifest_at(
        dest, entry.engine_id, identity.version, ctx.project_root
    )
    if existing is not None:
        _update_selection(ctx.project_root, entry.engine_id, dest / MANIFEST_FILENAME)
        result.reused[entry.engine_id] = existing
        return
    _claim_destination(dest, entry, identity, ctx)
    executable = _install_into(engine, identity, dest, ctx)
    probe_argv = (
        [str(executable), *entry.probe[1:]]
        if entry.probe
        else [str(executable), "--version"]
    )
    probe_result = ctx.prober(probe_argv)
    if probe_result.returncode != 0:
        raise ProvisionError(
            "ENGINE_PROTOCOL_MISMATCH",
            f"{entry.engine_id} probe failed: {probe_result.stderr}",
        )
    manifest = ProvisionManifest(
        schema_version=1,
        engine_id=entry.engine_id,
        package_id=entry.package_id,
        version=identity.version,
        source=entry.source,
        manager=entry.manager,
        executable=str(executable),
        executable_sha256=compute_file_sha256(executable),
        os_name=ctx.plan.os_name,
        arch=ctx.plan.arch,
        project_id=ctx.project_id,
        project_root=ctx.plan.project_root,
        runtime_identity=f"{entry.manager} {identity.version}",
        plan_id=ctx.plan.plan_id,
        created_at=__import__("datetime")
        .datetime.now(__import__("datetime").timezone.utc)
        .isoformat(),
    )
    manifest_path = write_manifest(dest, manifest)
    _update_selection(ctx.project_root, entry.engine_id, manifest_path)
    result.applied[entry.engine_id] = manifest


def apply_provision_plan(
    plan: ProvisionPlan,
    permissions: ExecutionPermissions | None,
    *,
    project_id: str,
    data_root: Path,
    reviewed_plan_id: str,
    identity_source: str = "frozen_review",
    http_get: HttpGet | None = None,
    downloader: Downloader = _default_downloader,
    runner: Runner = _default_runner,
    prober: Prober = _default_prober,
    which: Callable[[str], str | None] = shutil.which,
    current_platform: tuple[str, str] | None = None,
) -> ProvisionResult:
    """Apply a reviewed plan: install each frozen identity, probe, and bind a manifest.

    Never resolves an identity (`http_get` is accepted for callers that pass
    one shared fake set, and is never called). Before any effect, in order:
    the recomputed plan_id must equal both `plan.plan_id` and
    `reviewed_plan_id`, and every entry must match the engine allowlist
    (else PLAN_TAMPERED); the plan platform must equal this machine
    (WRONG_PLATFORM); every applicable entry's grants must be present (else
    `permission_blocked` lists the missing flags and nothing happens). Only
    then is the cursor key ensured. Per entry: an unresolved entry is
    IDENTITY_UNRESOLVED, a destination other than the reviewed contained one
    is DESTINATION_ESCAPE, a destination Rush does not own for this identity
    is DESTINATION_OCCUPIED (listed in `recovery_required`, never deleted),
    and an existing verified manifest is `reused` without reinstalling.

    A failed post-install probe or checksum mismatch never writes a manifest
    and never touches the project's existing toolchain selection -- the
    previous compatible toolchain (if any) is retained untouched. The partial
    destination keeps its ownership marker so a rerun of the same identity
    can clean and retry it.

    This is Rush's authorized global setup flow: it also ensures the
    project registry's HMAC cursor-signing key exists (plan §6.1 --
    `cursor.key` is created here, never from a query path), so
    `list_projects_page`'s cursor pagination is reachable after setup
    instead of permanently `SETUP_REQUIRED`.
    """
    from rush.workflows.projects import ensure_cursor_key

    result = ProvisionResult(identity_source=identity_source, plan_id=plan.plan_id)
    rejection = _plan_rejection(
        plan, reviewed_plan_id, current_platform or current_os_arch()
    )
    if rejection is not None:
        code, message = rejection
        result.failed = {
            e.engine_id: {"code": code, "message": f"[{code}] {message}"}
            for e in plan.entries
        }
        return result
    result.requires_input = [
        e.engine_id for e in plan.entries if e.disposition == "requires_input"
    ]
    missing = _missing_grants(plan, permissions)
    if missing:
        result.permission_blocked = missing
        return result
    ensure_cursor_key(data_root)
    ctx = _ApplyContext(
        plan=plan,
        project_id=project_id,
        project_root=Path(plan.project_root),
        data_root=data_root,
        txid=uuid.uuid4().hex,
        identity_source=identity_source,
        downloader=downloader,
        runner=runner,
        prober=prober,
        which=which,
    )
    for entry in plan.entries:
        if entry.disposition != "applicable":
            continue
        try:
            _apply_entry(entry, ctx, result)
        except ProvisionError as exc:
            result.failed[entry.engine_id] = {"code": exc.code, "message": str(exc)}
            if exc.code == "DESTINATION_OCCUPIED":
                result.recovery_required[entry.engine_id] = entry.destination
    return result


def resolve_and_apply_provision_plan(
    plan: ProvisionPlan,
    permissions: ExecutionPermissions | None,
    *,
    project_id: str,
    data_root: Path,
    http_get: HttpGet = _default_http_get,
    downloader: Downloader = _default_downloader,
    runner: Runner = _default_runner,
    prober: Prober = _default_prober,
    which: Callable[[str], str | None] = shutil.which,
    current_platform: tuple[str, str] | None = None,
) -> ProvisionResult:
    """Unattended callers (InstallTool, `scan --install`, dashboard
    `provision_apply`): resolve under the caller's network grant, then apply
    that plan in the same invocation, labelled `resolved_at_apply`. Without
    the network grant nothing resolves and apply reports the missing grants.
    """
    has_unresolved = any(e.identity_state == "unresolved" for e in plan.entries)
    if has_unresolved and permissions is not None and permissions.network:
        plan = resolve_provision_identities(plan, permissions, http_get=http_get)
    return apply_provision_plan(
        plan,
        permissions,
        project_id=project_id,
        data_root=data_root,
        reviewed_plan_id=plan.plan_id,
        identity_source="resolved_at_apply",
        downloader=downloader,
        runner=runner,
        prober=prober,
        which=which,
        current_platform=current_platform,
    )


__all__ = [
    "DataRootUnavailableError",
    "ProvisionError",
    "ProvisionOutcome",
    "ProvisionPlan",
    "ProvisionPlanEntry",
    "ProvisionResult",
    "ResolvedIdentity",
    "apply_provision_plan",
    "build_provision_plan",
    "compute_plan_id",
    "current_os_arch",
    "default_data_root",
    "plan_from_dict",
    "plan_to_dict",
    "resolution_url",
    "resolve_and_apply_provision_plan",
    "resolve_identity",
    "resolve_provision_identities",
]
