"""InstallTool -- one-command installation and readiness integration.

Phase 65 P65-10 (F35, F42). `rush install` is the single command a brand new
machine runs (via `scripts/install.sh`/`install.ps1`, or directly once an
older `rush` is already on PATH) to get a verified, self-contained `rush`
executable in place, connect every detected local coding agent, activate
user-scoped agent memory, and (only when the caller explicitly names one)
register/select a project.

Download/verify/extract of the release archive is this module's own,
independent implementation (never a re-import of `scripts.*`): PyInstaller's
`--onefile --paths src` build (`.github/workflows/release.yml`) never bundles
the top-level `scripts/` package, so anything under `src/rush/` that the
shipped binary must run at install time cannot import from `scripts/`.
`select_release_asset`/`RELEASE_ASSET_MATRIX` therefore duplicate (never
import) the six-way matrix `scripts/probe_installed_artifacts.py` and
`.github/workflows/release.yml` already define; `tests/test_bootstrap_install.py`
asserts the two matrices stay identical so the duplication can't silently
drift.

Every network/subprocess side effect is behind an injectable `downloader`/
`prober` callable (mirrors `rush.setup.provision`'s own `Downloader`/`Prober`
seams) so the whole pipeline is exhaustively testable without live network
access. Order is load-bearing: the binary is downloaded, checksum-verified,
atomically installed, and probed to confirm it actually starts *before*
anything below ever touches an agent config file or writes an agent memory
scope -- a failure at any earlier step never produces an agent write, and a
failure in the post-replace "does it start" probe restores the exact prior
executable bytes rather than leaving a broken binary in place.
"""

from __future__ import annotations

import hashlib
import io
import os
import platform
import shutil
import ssl
import subprocess
import tarfile
import tempfile
import zipfile
from pathlib import Path
from time import monotonic
from typing import Any, Literal
from urllib.request import Request, urlopen

import certifi

from rush.integrations.agents import (
    ADAPTERS,
    AgentConnectionError,
    discover_agents,
    read_agent_memory_state,
    resolve_rush_binary,
)
from rush.permissions import ExecutionPermissions
from rush.setup.provision import (
    DataRootUnavailableError,
    Downloader,
    Prober,
    default_data_root,
)
from rush.tools.agent_connection import AgentConnectionTool
from rush.tools.setup_wizard import run_setup_wizard
from rush.workflows.projects import (
    ProjectError,
    ProjectNotFoundError,
    create_project,
    register_project,
    resolve_project,
    select_project,
)

from .base import Finding, ToolFn, ToolResult, ToolStatus

AgentsFlag = Literal["all", "none"]
MemoryFlag = Literal["on", "off"]

_RELEASE_REPO = "jamesdsizemore/rush-cli"

# ponytail: this small matrix/extractor duplicates scripts/probe_installed_artifacts.py
# and rush.setup.provision._safe_extract_binary (neither is in this task's allowed_files,
# and scripts/ isn't bundled into the shipped PyInstaller binary at all). Consolidate into
# one shared src/rush module if a third caller ever needs it.
_ARCH_ALIASES = {
    "aarch64": "arm64",
    "arm64": "arm64",
    "amd64": "x86_64",
    "x86_64": "x86_64",
}

RELEASE_ASSET_MATRIX: dict[tuple[str, str], str] = {
    ("darwin", "arm64"): "rush-darwin-arm64.tar.gz",
    ("darwin", "x86_64"): "rush-darwin-x86_64.tar.gz",
    ("linux", "x86_64"): "rush-linux-x86_64.tar.gz",
    ("linux", "arm64"): "rush-linux-arm64.tar.gz",
    ("windows", "x86_64"): "rush-windows-x86_64.zip",
    ("windows", "arm64"): "rush-windows-arm64.zip",
}


class InstallError(Exception):
    """Raised for any resolution, integrity, extraction, or startup failure."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(f"[{code}] {message}")
        self.code = code


class UnsupportedPlatformError(InstallError):
    def __init__(self, message: str) -> None:
        super().__init__("UNSUPPORTED_PLATFORM", message)


def select_release_asset(system: str, machine: str) -> str:
    """Return the exact release asset filename for an OS name and CPU architecture."""
    normalized_machine = _ARCH_ALIASES.get(
        machine.strip().lower(), machine.strip().lower()
    )
    key = (system.strip().lower(), normalized_machine)
    try:
        return RELEASE_ASSET_MATRIX[key]
    except KeyError:
        raise UnsupportedPlatformError(
            f"no release asset defined for system={system!r} machine={machine!r}"
        ) from None


def _binary_name(os_name: str) -> str:
    return "rush.exe" if os_name.strip().lower() == "windows" else "rush"


def _release_asset_url(asset_name: str, version: str | None) -> str:
    if version:
        return f"https://github.com/{_RELEASE_REPO}/releases/download/v{version}/{asset_name}"
    return f"https://github.com/{_RELEASE_REPO}/releases/latest/download/{asset_name}"


_SSL_CONTEXT = ssl.create_default_context(cafile=certifi.where())


def _default_downloader(url: str) -> bytes:
    with urlopen(
        Request(url, headers={"User-Agent": "rush-cli-install"}),
        timeout=30,
        context=_SSL_CONTEXT,
    ) as resp:
        return resp.read()


def _default_prober(argv: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(argv, capture_output=True, text=True, timeout=30, check=False)


def _verify_checksum(data: bytes, sums_text: str, asset_name: str) -> bool:
    expected = None
    for line in sums_text.splitlines():
        parts = line.strip().split(maxsplit=1)
        if len(parts) != 2:
            continue
        digest, name = parts
        if name.lstrip("*") == asset_name:
            expected = digest
            break
    if expected is None:
        return False
    return hashlib.sha256(data).hexdigest() == expected


def _extract_binary_bytes(
    archive_bytes: bytes, asset_name: str, binary_name: str
) -> bytes:
    """Return exactly the named binary's bytes from a tar.gz/zip archive."""
    lowered = asset_name.lower()
    if lowered.endswith((".tar.gz", ".tgz")):
        with tarfile.open(fileobj=io.BytesIO(archive_bytes), mode="r:gz") as tar:
            member = next(
                (
                    m
                    for m in tar.getmembers()
                    if Path(m.name).name == binary_name and m.isfile()
                ),
                None,
            )
            if member is None:
                raise InstallError(
                    "NO_COMPATIBLE_ASSET", f"no {binary_name} inside {asset_name}"
                )
            extracted = tar.extractfile(member)
            if extracted is None:
                raise InstallError(
                    "NO_COMPATIBLE_ASSET", f"could not read {member.name}"
                )
            return extracted.read()
    if lowered.endswith(".zip"):
        with zipfile.ZipFile(io.BytesIO(archive_bytes)) as zf:
            zip_member = next(
                (n for n in zf.namelist() if Path(n).name == binary_name), None
            )
            if zip_member is None:
                raise InstallError(
                    "NO_COMPATIBLE_ASSET", f"no {binary_name} inside {asset_name}"
                )
            return zf.read(zip_member)
    raise InstallError(
        "NO_COMPATIBLE_ASSET", f"unrecognized archive format: {asset_name}"
    )


def _atomic_install_binary(
    bin_dir: Path, binary_name: str, data: bytes
) -> tuple[Path, Path | None]:
    """Write `data` into place atomically, backing up any prior executable first."""
    bin_dir.mkdir(parents=True, exist_ok=True)
    final_path = bin_dir / binary_name
    backup_path: Path | None = None
    if final_path.is_file():
        backup_path = bin_dir / f"{binary_name}.rush-previous"
        shutil.copy2(final_path, backup_path)

    fd, tmp_name = tempfile.mkstemp(dir=bin_dir, prefix=f".{binary_name}.")
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
        tmp_path.chmod(0o755)
        os.replace(tmp_path, final_path)
    except Exception:
        tmp_path.unlink(missing_ok=True)
        raise
    return final_path, backup_path


class InstallTool(ToolFn):
    """Download/verify/install the release binary and bring agents + a project online."""

    name = "install"

    @property
    def mcp_description(self) -> str:
        return (
            "One-command install: download/verify/extract the release binary, "
            "connect local agents (agents=all|none), activate user-scoped agent "
            "memory (memory=on|off), and optionally register/select a project. "
            "Returns {status, findings[], summary, raw}."
        )

    def __call__(
        self,
        agents: AgentsFlag = "all",
        memory: MemoryFlag = "on",
        project: str | None = None,
    ) -> ToolResult:
        return self.run(agents=agents, memory=memory, project=project)

    def run(
        self,
        *,
        agents: AgentsFlag = "all",
        memory: MemoryFlag = "on",
        project: str | None = None,
        create_name: str | None = None,
        create_parent: Path | str | None = None,
        init_git: bool = False,
        session_id: str = "install",
        version: str | None = None,
        os_name: str | None = None,
        arch: str | None = None,
        home: Path | None = None,
        data_root: Path | None = None,
        install_dir: Path | None = None,
        downloader: Downloader | None = None,
        prober: Prober | None = None,
        permissions: ExecutionPermissions | None = None,
    ) -> ToolResult:
        started = monotonic()
        granted = permissions or ExecutionPermissions()
        downloader = downloader or _default_downloader
        prober = prober or _default_prober
        resolved_os = os_name or platform.system()
        resolved_arch = arch or platform.machine()

        try:
            resolved_data_root = data_root or default_data_root()
        except DataRootUnavailableError as exc:
            return self._result(started, "error", f"install: {exc}")
        bin_dir = install_dir or (resolved_data_root / "bin")

        try:
            asset_name = select_release_asset(resolved_os, resolved_arch)
            archive_bytes, sums_text = self._download_release(
                asset_name=asset_name, version=version, downloader=downloader
            )
            binary_path = self._install_binary(
                bin_dir=bin_dir,
                asset_name=asset_name,
                os_name=resolved_os,
                archive_bytes=archive_bytes,
                sums_text=sums_text,
                prober=prober,
            )
        except InstallError as exc:
            return self._result(
                started, "error", f"install: {exc}", raw={"code": exc.code}
            )

        # Agent discovery/connection and memory activation are user-scoped and
        # independent of any project choice below -- they run whether or not a
        # project ends up selected, and never before this point.
        try:
            # Resolve the rush binary path ONCE here and use that single
            # resolved value for both discovery/comparison and connect below
            # -- otherwise an install/data root that crosses a symlink (e.g.
            # macOS /var -> /private/var) makes the unresolved path compared
            # in discover_agents permanently mismatch the resolved path
            # connect writes into the agent's config, so status never
            # settles on "registered"/"active" (T211).
            resolved_rush_binary = resolve_rush_binary(str(binary_path))
            agent_reports = self._process_agents(
                agents_flag=agents,
                memory=memory,
                home=home,
                os_name=resolved_os,
                rush_binary=resolved_rush_binary,
                session_id=session_id,
                data_root=resolved_data_root,
                permissions=granted,
            )
        except AgentConnectionError as exc:
            return self._result(
                started,
                "error",
                f"install: agent setup failed: {exc}",
                raw={"binary": {"path": str(binary_path)}},
            )

        try:
            project_view = self._choose_project(
                project=project,
                create_name=create_name,
                create_parent=Path(create_parent) if create_parent else None,
                init_git=init_git,
                session_id=session_id,
                data_root=resolved_data_root,
            )
            provision_summary = (
                run_setup_wizard(
                    Path(project_view["root"]),
                    non_interactive=True,
                    install=True,
                    permissions=granted,
                    project_id=project_view["project_id"],
                    data_root=resolved_data_root,
                    downloader=downloader,
                )
                if project_view is not None
                else None
            )
        except ProjectError as exc:
            return self._result(
                started,
                "error",
                f"install: project setup failed: {exc}",
                raw={"binary": {"path": str(binary_path)}, "agents": agent_reports},
            )

        raw = {
            "schema_version": 1,
            "binary": {
                "path": str(binary_path),
                "asset": asset_name,
                "os": resolved_os,
                "arch": resolved_arch,
            },
            "agents": agent_reports,
            "project": project_view,
            "provision": provision_summary,
        }
        summary = (
            "install: ok (no active project)"
            if project_view is None
            else f"install: ok (project={project_view['project_id']})"
        )
        return self._result(started, "ok", summary, raw=raw)

    # --- Binary download/verify/extract/replace ----------------------------

    def _download_release(
        self, *, asset_name: str, version: str | None, downloader: Downloader
    ) -> tuple[bytes, str]:
        try:
            archive_bytes = downloader(_release_asset_url(asset_name, version))
            sums_bytes = downloader(_release_asset_url("SHA256SUMS", version))
        except InstallError:
            raise
        except Exception as exc:
            raise InstallError(
                "DOWNLOAD_FAILED", f"failed to download release assets: {exc}"
            ) from exc
        return archive_bytes, sums_bytes.decode("utf-8")

    def _install_binary(
        self,
        *,
        bin_dir: Path,
        asset_name: str,
        os_name: str,
        archive_bytes: bytes,
        sums_text: str,
        prober: Prober,
    ) -> Path:
        if not _verify_checksum(archive_bytes, sums_text, asset_name):
            raise InstallError("CHECKSUM_MISMATCH", f"sha256 mismatch for {asset_name}")

        binary_name = _binary_name(os_name)
        try:
            binary_bytes = _extract_binary_bytes(archive_bytes, asset_name, binary_name)
        except InstallError:
            raise
        except (tarfile.TarError, zipfile.BadZipFile, OSError) as exc:
            raise InstallError(
                "EXTRACT_FAILED", f"could not extract {binary_name}: {exc}"
            ) from exc

        final_path, backup_path = _atomic_install_binary(
            bin_dir, binary_name, binary_bytes
        )
        result = prober([str(final_path), "--version"])
        if result.returncode != 0:
            if backup_path is not None:
                shutil.copy2(backup_path, final_path)
            else:
                final_path.unlink(missing_ok=True)
            raise InstallError(
                "BINARY_VERIFY_FAILED",
                f"installed binary failed to start: {(result.stderr or '').strip()}",
            )
        if backup_path is not None:
            backup_path.unlink(missing_ok=True)
        return final_path

    # --- Agent discovery/connection/memory ----------------------------------

    def _process_agents(
        self,
        *,
        agents_flag: AgentsFlag,
        memory: MemoryFlag,
        home: Path | None,
        os_name: str | None,
        rush_binary: str,
        session_id: str,
        data_root: Path,
        permissions: ExecutionPermissions,
    ) -> list[dict[str, Any]]:
        statuses = discover_agents(home=home, os_name=os_name, rush_binary=rush_binary)
        connect_tool = AgentConnectionTool()
        reports: list[dict[str, Any]] = []

        for status in statuses:
            adapter = ADAPTERS[status.agent_id]
            if not status.detected:
                reports.append(self._agent_report(status, adapter, "unsupported"))
                continue

            if agents_flag != "all":
                passive_state = (
                    "active" if status.status == "registered" else "configured"
                )
                reports.append(self._agent_report(status, adapter, passive_state))
                continue

            # Memory is user-scoped here (project_root=None), independent of any
            # project choice. An agent already connected+acknowledged is left
            # completely untouched: no re-registration, no duplicate memory
            # write, no disruption to whatever live session it already has.
            existing_memory = read_agent_memory_state(
                status.agent_id, session_id, project_root=None, data_root=data_root
            )
            if (
                status.status == "registered"
                and existing_memory
                and existing_memory.get("connected")
            ):
                reports.append(self._agent_report(status, adapter, "active"))
                continue

            connect_result = connect_tool.run(
                status.agent_id,
                action="connect",
                session_id=session_id,
                rush_binary=rush_binary,
                consent=(memory == "on"),
                acknowledge=True,
                project_root=None,
                data_root=data_root,
                home=home,
                permissions=permissions,
            )
            raw = connect_result.get("raw") or {}
            applied = raw.get("apply") or {}
            probe = raw.get("probe") or {}
            if not applied.get("ok"):
                reports.append(
                    self._agent_report(
                        status, adapter, "configured", error=applied.get("error")
                    )
                )
                continue
            # Only the native path is an actual handshake (a real subprocess exit
            # code from the agent's own CLI) -- claim "active" for it only once
            # the post-apply probe confirms the registration is really there. A
            # config-edit write is file-only: an adapter that needs a client
            # restart to notice it stays "restart_required" rather than
            # claiming a live connection that hasn't happened yet.
            if applied.get("method") == "native":
                state = (
                    "active" if probe.get("status") == "registered" else "configured"
                )
            elif adapter.restart_required:
                state = "restart_required"
            else:
                state = "active"
            reports.append(self._agent_report(status, adapter, state))

        return reports

    def _agent_report(
        self, status: Any, adapter: Any, state: str, *, error: str | None = None
    ) -> dict[str, Any]:
        return {
            "agent_id": status.agent_id,
            "display_name": adapter.display_name,
            "state": state,
            "detected": status.detected,
            "config_path": str(status.config_path) if status.config_path else None,
            "error": error or status.error,
        }

    # --- Project choice (select existing / add / create / choose-later) ----

    def _choose_project(
        self,
        *,
        project: str | None,
        create_name: str | None,
        create_parent: Path | None,
        init_git: bool,
        session_id: str,
        data_root: Path,
    ) -> dict[str, Any] | None:
        if create_name:
            record = create_project(
                create_parent or Path.cwd(),
                create_name,
                init_git=init_git,
                data_root=data_root,
            )
            return select_project(session_id, record.project_id, data_root=data_root)

        if project:
            try:
                resolved = resolve_project(project, data_root=data_root)
            except ProjectNotFoundError:
                path = Path(project)
                if not path.is_dir():
                    raise
                record = register_project(path, data_root=data_root)
                resolved = resolve_project(record.project_id, data_root=data_root)
            return select_project(
                session_id, resolved["project_id"], data_root=data_root
            )

        # Choosing later is a successful global install with no active project.
        return None

    def _result(
        self, started: float, status: ToolStatus, summary: str, *, raw: Any = None
    ) -> ToolResult:
        findings: list[Finding] = []
        return ToolResult(
            tool=self.name,
            engine=None,
            engine_version=None,
            status=status,
            duration_ms=int((monotonic() - started) * 1000),
            summary=summary,
            findings=findings,
            raw=raw,
        )


__all__ = [
    "RELEASE_ASSET_MATRIX",
    "InstallError",
    "InstallTool",
    "UnsupportedPlatformError",
    "select_release_asset",
]
