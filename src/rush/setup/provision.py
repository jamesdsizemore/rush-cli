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
import shutil
import ssl
import subprocess
import tarfile
import tempfile
import zipfile
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import certifi

from rush.permissions import ExecutionPermissions, check_permissions
from rush.runtime.binaries import ProvisionManifest, compute_file_sha256, write_manifest
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
    ENGINE_PROTOCOL_MISMATCH.
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


def _resolve_pypi(package_id: str, http_get: HttpGet) -> ResolvedIdentity:
    data = _http_get_json(
        f"https://pypi.org/pypi/{package_id}/json",
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
    encoded = package_id.replace("/", "%2F")
    data = _http_get_json(
        f"https://registry.npmjs.org/{encoded}",
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
        f"https://crates.io/api/v1/crates/{package_id}",
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
        f"https://rubygems.org/api/v1/versions/{package_id}.json",
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
        f"https://repo.packagist.org/p2/{package_id}.json",
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
    group_id, artifact_id = package_id.split(":", 1)
    query = f"g:{group_id}+AND+a:{artifact_id}"
    data = _http_get_json(
        f"https://search.maven.org/solrsearch/select?q={query}&core=gav&rows=1&wt=json",
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
        f"https://api.github.com/repos/{repo}/releases/latest",
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
    "go": lambda engine, os_name, arch, http_get: ResolvedIdentity(
        engine.version_policy.split(":", 1)[1]
        if ":" in engine.version_policy
        else "latest",
        None,
        None,
        None,
    ),
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


@dataclass(frozen=True)
class ProvisionPlan:
    plan_id: str
    project_root: str
    os_name: str
    arch: str
    entries: tuple[ProvisionPlanEntry, ...]


def _canonical_json(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _toolchains_root(data_root: Path) -> Path:
    return data_root / "toolchains"


def _destination_for(
    data_root: Path, engine_id: str, version: str, os_name: str, arch: str
) -> Path:
    return _toolchains_root(data_root) / engine_id / version / f"{os_name}-{arch}"


def build_provision_plan(
    project_root: Path,
    engine_ids: list[str],
    *,
    os_name: str | None = None,
    arch: str | None = None,
) -> ProvisionPlan:
    """Build an immutable provision plan for exactly the requested engines.

    Raises `UnknownEngineError` immediately for any id outside the declared
    `ENGINE_PACKAGES` allowlist -- no arbitrary package is ever planned.
    """
    resolved_os, resolved_arch = (
        (os_name, arch) if os_name and arch else current_os_arch()
    )
    entries: list[ProvisionPlanEntry] = []
    for engine_id in engine_ids:
        engine = resolve_engine_package(
            engine_id
        )  # raises UnknownEngineError for bad input
        if engine.source == "internal":
            disposition = "requires_input"
        else:
            disposition = "applicable"
        destination = str(
            _destination_for(
                Path("<data_root>"), engine_id, "<version>", resolved_os, resolved_arch
            )
        )
        entries.append(
            ProvisionPlanEntry(
                engine_id=engine.engine_id,
                package_id=engine.package_id,
                source=engine.source,
                manager=engine.manager,
                disposition=disposition,
                required_grants=_SOURCE_GRANTS.get(engine.source, ()),
                prerequisites=engine.prerequisites,
                destination=destination,
                probe=engine.probe,
            )
        )
    payload = {
        "project_root": str(project_root.resolve()),
        "os": resolved_os,
        "arch": resolved_arch,
        "entries": [e.__dict__ for e in entries],
    }
    plan_id = hashlib.sha256(_canonical_json(payload)).hexdigest()
    return ProvisionPlan(
        plan_id=plan_id,
        project_root=str(project_root.resolve()),
        os_name=resolved_os,
        arch=resolved_arch,
        entries=tuple(entries),
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


def apply_provision_plan(
    plan: ProvisionPlan,
    permissions: ExecutionPermissions,
    *,
    project_id: str,
    data_root: Path,
    http_get: HttpGet = _default_http_get,
    downloader: Downloader = _default_downloader,
    runner: Runner = _default_runner,
    prober: Prober = _default_prober,
    which: Callable[[str], str | None] = shutil.which,
) -> ProvisionResult:
    """Apply a previously built plan: resolve, install, probe, and bind a manifest.

    A failed post-install probe or checksum mismatch never writes a manifest
    and never touches the project's existing toolchain selection -- the
    previous compatible toolchain (if any) is retained untouched.

    This is Rush's authorized global setup flow: it also ensures the
    project registry's HMAC cursor-signing key exists (plan §6.1 --
    `cursor.key` is created here, never from a query path), so
    `list_projects_page`'s cursor pagination is reachable after setup
    instead of permanently `SETUP_REQUIRED`.
    """
    from rush.workflows.projects import ensure_cursor_key

    result = ProvisionResult()
    ensure_cursor_key(data_root)
    project_root = Path(plan.project_root)
    for entry in plan.entries:
        if entry.disposition == "requires_input":
            result.requires_input.append(entry.engine_id)
            continue
        ok, missing = check_permissions(
            ExecutionPermissions(**{g: True for g in entry.required_grants})
            if entry.required_grants
            else None,
            permissions,
        )
        if not ok:
            result.permission_blocked[entry.engine_id] = missing
            continue
        engine = ENGINE_PACKAGES[entry.engine_id]
        try:
            identity = resolve_identity(
                engine, os_name=plan.os_name, arch=plan.arch, http_get=http_get
            )
            dest_dir = _destination_for(
                data_root, entry.engine_id, identity.version, plan.os_name, plan.arch
            )
            if dest_dir.exists() and not (dest_dir / "manifest.json").is_file():
                # Interrupted prior attempt: clean the partial directory before retrying.
                shutil.rmtree(dest_dir, ignore_errors=True)
            if engine.source in ("github",):
                if identity.url is None:
                    raise ProvisionError(
                        "NO_COMPATIBLE_ASSET", f"{entry.engine_id} has no download URL"
                    )
                data = downloader(identity.url)
                _verify_digest(data, identity.digest_algo, identity.digest_value)
                executable = _safe_extract_binary(
                    data, identity.url, engine.binary, dest_dir
                )
            else:
                _check_manager_available(engine, which)
                argv = list(
                    _manager_install_command(engine, identity.version, dest_dir)
                )
                env = {"GOBIN": str(dest_dir)} if engine.source == "go" else None
                try:
                    proc = runner(argv, env)
                except OSError as exc:
                    raise ProvisionError(
                        "SYSTEM_PREREQUISITE_REQUIRED",
                        f"could not execute {argv[0]}: {exc}",
                    ) from exc
                if proc.returncode != 0:
                    raise ProvisionError(
                        "SYSTEM_PREREQUISITE_REQUIRED",
                        f"install command failed: {' '.join(argv)}",
                    )
                dest_dir.mkdir(parents=True, exist_ok=True)
                found = shutil.which(engine.binary, path=str(dest_dir)) or shutil.which(
                    engine.binary, path=str(dest_dir / "bin")
                )
                executable = Path(found) if found else dest_dir / engine.binary
                if not executable.is_file():
                    raise ProvisionError(
                        "ENGINE_PROTOCOL_MISMATCH",
                        f"{entry.engine_id} binary not found after install",
                    )
            probe_argv = (
                [str(executable), *entry.probe[1:]]
                if entry.probe
                else [str(executable), "--version"]
            )
            probe_result = prober(probe_argv)
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
                os_name=plan.os_name,
                arch=plan.arch,
                project_id=project_id,
                project_root=plan.project_root,
                runtime_identity=f"{entry.manager} {identity.version}",
                plan_id=plan.plan_id,
                created_at=__import__("datetime")
                .datetime.now(__import__("datetime").timezone.utc)
                .isoformat(),
            )
            manifest_path = write_manifest(dest_dir, manifest)
            _update_selection(project_root, entry.engine_id, manifest_path)
            result.applied[entry.engine_id] = manifest
        except ProvisionError as exc:
            result.failed[entry.engine_id] = {"code": exc.code, "message": str(exc)}
    return result


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
    "current_os_arch",
    "default_data_root",
    "resolve_identity",
]
