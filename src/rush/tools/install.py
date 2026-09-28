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
import json
import os
import platform
import shutil
import ssl
import subprocess
import sys
import tarfile
import tempfile
import zipfile
from collections.abc import Callable, Sequence
from pathlib import Path
from time import monotonic
from typing import Any, Literal
from urllib.request import Request, urlopen

import certifi

from rush.integrations.agents import (
    ADAPTERS,
    INSTRUCTION_TARGETS,
    PLUGIN_HOSTS,
    PLUGIN_ID,
    PLUGIN_MARKETPLACE,
    AgentConnectionError,
    CASConflictError,
    ManualEntryRemoval,
    WriteJournal,
    cas_replace_file,
    discover_agents,
    finalize_agent_plugin_upgrade,
    installed_plugin_roots,
    materialize_agent_plugins,
    plan_manual_entry_removal,
    read_agent_memory_state,
    reconcile_agent_instructions,
    record_native_plugin_install,
    resolve_rush_binary,
)
from rush.memory.transactions import StoreError
from rush.permissions import ExecutionPermissions
from rush.setup.provision import (
    DataRootUnavailableError,
    Downloader,
    Prober,
    default_data_root,
)
from rush.tools.agent_connection import AgentConnectionTool
from rush.tools.setup_wizard import (
    SETUP_HOSTS,
    render_setup_result,
    run_guided_setup,
    run_setup_wizard,
    setup_resume_command,
)
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
ManualEntryConsent = bool | Callable[[ManualEntryRemoval], bool]

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


def _plugin_install_commands(host: str, plugin_root: Path) -> list[tuple[str, ...]]:
    """The host's own local-marketplace install route (design brief X8)."""
    root = str(plugin_root)
    if host == "claude":
        return [
            ("claude", "plugin", "marketplace", "add", root, "--scope", "user"),
            ("claude", "plugin", "install", PLUGIN_ID, "--scope", "user"),
        ]
    return [
        ("codex", "plugin", "marketplace", "add", root),
        ("codex", "plugin", "add", PLUGIN_ID),
    ]


def _plugin_upgrade_commands(host: str, plugin_root: Path) -> list[tuple[str, ...]]:
    """Point `rush-local` at the new version root, then update the plugin.

    Verified against claude 2.1.283 and codex 0.155.1 in isolated homes: an
    update alone re-reads the old directory and stays on the old version.
    Claude re-adding the same marketplace name replaces its source; Codex
    refuses a second source under one name until the old one is removed
    (removing the marketplace leaves the installed plugin enabled).
    """
    root = str(plugin_root)
    if host == "claude":
        return [
            ("claude", "plugin", "marketplace", "add", root, "--scope", "user"),
            ("claude", "plugin", "marketplace", "update", PLUGIN_MARKETPLACE),
            ("claude", "plugin", "update", PLUGIN_ID, "--scope", "user"),
        ]
    return [
        ("codex", "plugin", "marketplace", "remove", PLUGIN_MARKETPLACE),
        ("codex", "plugin", "marketplace", "add", root),
        ("codex", "plugin", "add", PLUGIN_ID),
    ]


# Host output that means a policy/approval refusal, reproduced in isolated
# homes (HOME, CLAUDE_CONFIG_DIR, CODEX_HOME under the session scratchpad):
# - claude 2.1.283, `claude --managed-settings '{"strictKnownMarketplaces":[]}'`
#   (or `blockedMarketplaces` naming the root): `plugin marketplace add` and
#   `plugin marketplace update` print "Marketplace source 'dir:<root>' is
#   blocked by enterprise policy."; `plugin install` and `plugin update` print
#   'Plugin "rush" is from marketplace "rush-local", which is blocked by your
#   organization's policy'. All exit 1.
# - codex 0.155.1, marketplace entry `"policy": {"installation":
#   "NOT_AVAILABLE"}`: `plugin add` prints "Error: plugin `rush` is not
#   available for install in marketplace `rush-local`" and exits 1.
# Every other nonzero exit (missing source, unknown plugin, crash) is `failed`.
_HOST_REFUSAL_SIGNATURES = (
    "is blocked by enterprise policy",
    "which is blocked by your organization's policy",
    "is not available for install in marketplace",
)
_STDERR_TAIL_CHARS = 2000


def _redacted_tail(text: str) -> str:
    from rush.logging import redact_secrets

    return redact_secrets(text.strip()[-_STDERR_TAIL_CHARS:])


def _run_host_commands(commands: list[tuple[str, ...]]) -> dict[str, Any] | None:
    """Run each command in order; the first failure as a state dict, else None.

    A nonzero exit is `denied` only when the host's output carries one of its
    own policy/approval refusal messages; any other nonzero exit is `failed`
    with the exit code and a redacted stderr tail. Never reported as success.
    """
    for index, argv in enumerate(commands):
        try:
            proc = subprocess.run(
                list(argv), capture_output=True, text=True, timeout=120, check=False
            )
        except (OSError, subprocess.SubprocessError) as exc:
            return {"state": "failed", "detail": str(exc), "step": index}
        if proc.returncode != 0:
            output = f"{proc.stderr or ''}\n{proc.stdout or ''}"
            refused = any(sig in output for sig in _HOST_REFUSAL_SIGNATURES)
            return {
                "state": "denied" if refused else "failed",
                "exit_code": proc.returncode,
                "detail": _redacted_tail(proc.stderr or proc.stdout or "")
                or f"exit {proc.returncode}",
                "command": list(argv),
                "step": index,
            }
    return None


def _host_output(argv: list[str]) -> str | None:
    try:
        proc = subprocess.run(
            argv, capture_output=True, text=True, timeout=60, check=False
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return proc.stdout if proc.returncode == 0 else None


def _host_version(host: str) -> str | None:
    output = _host_output([host, "--version"])
    return output.strip().splitlines()[0] if output and output.strip() else None


def _installed_plugin_version(host: str) -> str | None:
    """The Rush plugin version the host itself reports as installed."""
    output = _host_output([host, "plugin", "list", "--json"])
    try:
        data = json.loads(output or "")
    except ValueError:
        return None
    rows = data.get("installed") if isinstance(data, dict) else data
    for row in rows if isinstance(rows, list) else []:
        if isinstance(row, dict) and PLUGIN_ID in (row.get("id"), row.get("pluginId")):
            version = row.get("version")
            return version if isinstance(version, str) else None
    return None


def _check_plugin_host(host: str) -> dict[str, Any] | None:
    if host not in PLUGIN_HOSTS:
        return {
            "state": "failed",
            "host": host,
            "detail": f"unknown plugin host {host!r}",
        }
    if shutil.which(host) is None:
        return {
            "state": "host_missing",
            "host": host,
            "detail": f"{host} executable not found on PATH",
        }
    return None


def install_native_agent_plugin(
    *,
    host: str,
    plugin_root: Path,
    manual_config_path: Path | None = None,
    dry_run: bool = False,
    data_root: Path | None = None,
    consent: ManualEntryConsent = False,
) -> dict[str, Any]:
    """Install the materialized plugin at `plugin_root` through the host's own CLI.

    A manual `rush` MCP entry in `manual_config_path` is shown as a diff,
    removed before the install runs and restored byte-for-byte if the
    install fails, so two Rush servers are never registered at once. Only
    an entry the ownership ledger records is converted without asking; any
    other entry needs `consent` (True, or a callable that is shown the
    removal and answers), mirroring T3's guidance consent. Without it the
    state is `consent_required` (or `declined`), nothing is written and no
    host command runs. A host policy refusal is `denied`; any other host
    failure is `failed`. With `data_root`, the install and the entry it
    replaced are recorded in the ownership ledger.
    """
    plugin_root = Path(plugin_root)
    unavailable = _check_plugin_host(host)
    if unavailable is not None:
        return unavailable
    commands = _plugin_install_commands(host, plugin_root)
    try:
        removal = (
            plan_manual_entry_removal(
                PLUGIN_HOSTS[host], Path(manual_config_path), data_root=data_root
            )
            if manual_config_path is not None
            else None
        )
    except (AgentConnectionError, ValueError, OSError) as exc:
        return {"state": "conflict", "host": host, "detail": str(exc)}
    preview = {
        "commands": [list(argv) for argv in commands],
        "conversion": removal.to_dict() if removal is not None else None,
    }
    if dry_run:
        return {"state": "preview", "host": host, "preview": preview}
    if removal is not None and not removal.owned:
        granted = consent(removal) if callable(consent) else consent
        if not granted:
            return {
                "state": "declined" if callable(consent) else "consent_required",
                "host": host,
                "detail": (
                    f"{removal.path} has a 'rush' MCP entry Rush did not record; "
                    "converting it to the plugin needs your consent "
                    "(rush install --convert-manual-entry)"
                ),
                "preview": preview,
            }

    journal = WriteJournal()
    if removal is not None:
        try:
            written = cas_replace_file(
                removal.path,
                removal.new_bytes,
                expected_sha256=hashlib.sha256(removal.original).hexdigest(),
            )
        except (CASConflictError, OSError) as exc:
            return {"state": "conflict", "host": host, "detail": str(exc)}
        journal.record_file("mcp_entry", removal.path, removal.original, written)

    failure = _run_host_commands(commands)
    if failure is not None:
        return {
            **failure,
            "host": host,
            "recovery": journal.rollback(),
            "preview": preview,
        }
    report: dict[str, Any] = {
        "state": "installed",
        "host": host,
        "plugin_root": str(plugin_root),
        "host_version": _host_version(host),
        "reload": "restart the host session to load the plugin",
        "preview": preview,
    }
    if data_root is not None:
        try:
            record_native_plugin_install(
                data_root=data_root,
                host=host,
                plugin_root=plugin_root,
                removed_entry=removal,
            )
        except (AgentConnectionError, StoreError, OSError) as exc:
            report["ledger_error"] = str(exc)
    return report


def upgrade_native_agent_plugin(
    *,
    host: str,
    plugin_root: Path,
    previous_root: Path | None = None,
    data_root: Path | None = None,
) -> dict[str, Any]:
    """Move the host to the new version root and confirm what it now runs.

    The previous version directory is removed (through the ownership
    ledger) only after the host itself reports the new version; until then
    the state is `pending_confirmation` and the old directory stays. A
    failed step re-points `rush-local` at `previous_root` when one is given.
    """
    plugin_root = Path(plugin_root)
    unavailable = _check_plugin_host(host)
    if unavailable is not None:
        return unavailable
    failure = _run_host_commands(_plugin_upgrade_commands(host, plugin_root))
    if failure is not None:
        recovery: dict[str, Any] | None = None
        if previous_root is not None and failure["step"] > 0:
            restore = _plugin_install_commands(host, Path(previous_root))[:1]
            recovery = _run_host_commands(restore) or {"state": "restored"}
        return {**failure, "host": host, "recovery": recovery}
    expected = plugin_root.parent.name
    installed = _installed_plugin_version(host)
    report: dict[str, Any] = {
        "state": "upgraded" if installed == expected else "pending_confirmation",
        "host": host,
        "plugin_root": str(plugin_root),
        "host_version": _host_version(host),
        "installed_version": installed,
        "expected_version": expected,
        "reload": "restart the host session to load the plugin",
    }
    if data_root is not None and installed == expected:
        try:
            record_native_plugin_install(
                data_root=data_root, host=host, plugin_root=plugin_root
            )
            report["cleanup"] = finalize_agent_plugin_upgrade(
                host=host, confirmed_version=expected, data_root=data_root
            )
        except (AgentConnectionError, StoreError, OSError) as exc:
            report["ledger_error"] = str(exc)
    return report


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
        install_guidance: bool = False,
        agent_plugins: Sequence[str] = (),
        convert_manual_entry: bool = False,
        handoff_archive: Path | None = None,
        handoff_sums: Path | None = None,
        only_agent: str | None = None,
    ) -> ToolResult:
        """Install (or accept a verified handoff of) Rush, then agents/project.

        T26: `handoff_archive`/`handoff_sums` are the bootstrap script's own
        downloaded release files. They are verified against each other and
        against the running installed executable; nothing is downloaded or
        installed in that mode, so no path can install unverified bytes.
        `only_agent` (an adapter id) connects exactly that host.
        """
        started = monotonic()
        granted = permissions or ExecutionPermissions()
        downloader = downloader or _default_downloader
        prober = prober or _default_prober
        resolved_os = os_name or platform.system()
        resolved_arch = arch or platform.machine()
        unknown_plugins = sorted(set(agent_plugins) - set(PLUGIN_HOSTS))
        if unknown_plugins:
            return self._result(
                started,
                "error",
                f"install: unknown --agent-plugin host(s) {unknown_plugins}; "
                f"expected {sorted(PLUGIN_HOSTS)}",
            )

        try:
            resolved_data_root = data_root or default_data_root()
        except DataRootUnavailableError as exc:
            return self._result(started, "error", f"install: {exc}")
        bin_dir = install_dir or (resolved_data_root / "bin")

        handoff = handoff_archive is not None or handoff_sums is not None
        binary_version: str | None = None
        try:
            asset_name = select_release_asset(resolved_os, resolved_arch)
            if handoff:
                binary_path, binary_version = self._verify_handoff(
                    archive=handoff_archive,
                    sums=handoff_sums,
                    asset_name=asset_name,
                    os_name=resolved_os,
                    install_dir=install_dir,
                    prober=prober,
                )
            else:
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
                native_plugin_agents={PLUGIN_HOSTS[host] for host in agent_plugins},
                only_agent=only_agent,
            )
            plugin_reports = self._install_agent_plugins(
                agent_plugins,
                rush_binary=resolved_rush_binary,
                data_root=resolved_data_root,
                home=home,
                os_name=resolved_os,
                convert_manual_entry=convert_manual_entry,
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

        self._reconcile_guidance(
            agent_reports,
            agents_flag=agents,
            project_root=Path(project_view["root"]) if project_view else None,
            data_root=resolved_data_root,
            consent=install_guidance and granted.cache_write and granted.artifact_write,
            only_agent=only_agent,
        )

        raw = {
            "schema_version": 1,
            "binary": {
                "path": str(binary_path),
                "asset": asset_name,
                "os": resolved_os,
                "arch": resolved_arch,
                "handoff": handoff,
                "version": binary_version,
            },
            "agents": agent_reports,
            "agent_plugins": plugin_reports,
            "project": project_view,
            "provision": provision_summary,
        }
        # A requested plugin the host did not install (or has not confirmed)
        # is incomplete work: the install still succeeded, so warn, not ok.
        plugins_done = all(
            report.get("state") in ("installed", "upgraded")
            for report in plugin_reports.values()
        )
        status: ToolStatus = "ok" if plugins_done else "warn"
        summary = (
            f"install: {status} (no active project)"
            if project_view is None
            else f"install: {status} (project={project_view['project_id']})"
        )
        return self._result(started, status, summary, raw=raw)

    # --- Native host plugins (Phase 70 T2) ----------------------------------

    def _install_agent_plugins(
        self,
        hosts: Sequence[str],
        *,
        rush_binary: str,
        data_root: Path,
        home: Path | None,
        os_name: str | None,
        convert_manual_entry: bool,
    ) -> dict[str, dict[str, Any]]:
        """Materialize the plugins once, then install or upgrade each host."""
        if not hosts:
            return {}
        try:
            roots = materialize_agent_plugins(
                rush_binary=rush_binary, data_root=data_root
            )
        except (AgentConnectionError, StoreError, OSError) as exc:
            return {
                host: {"state": "failed", "host": host, "detail": str(exc)}
                for host in hosts
            }
        reports: dict[str, dict[str, Any]] = {}
        for host in dict.fromkeys(hosts):
            root = roots[host]
            previous = [
                path for path in installed_plugin_roots(host, data_root) if path != root
            ]
            if previous:
                reports[host] = upgrade_native_agent_plugin(
                    host=host,
                    plugin_root=root,
                    previous_root=previous[0],
                    data_root=data_root,
                )
                continue
            # The manual-entry config path only; install_native_agent_plugin
            # reads it and reports an unreadable file as a conflict.
            candidates = ADAPTERS[PLUGIN_HOSTS[host]].config_paths(
                os_name or platform.system(), home or Path.home()
            )
            config_path = next((p for p in candidates if p.exists()), candidates[0])
            reports[host] = install_native_agent_plugin(
                host=host,
                plugin_root=root,
                manual_config_path=config_path,
                data_root=data_root,
                consent=convert_manual_entry,
            )
        return reports

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

    def _verify_handoff(
        self,
        *,
        archive: Path | None,
        sums: Path | None,
        asset_name: str,
        os_name: str,
        install_dir: Path | None,
        prober: Prober,
    ) -> tuple[Path, str]:
        """Accept the bootstrap script's verified download (T26 handoff).

        The archive must match its SHA256SUMS entry, and the binary inside it
        must be byte-identical to the installed executable that is running.
        Nothing is downloaded, installed, or replaced here. Returns the
        executable and the version it reports.
        """

        def failed(message: str) -> InstallError:
            return InstallError("HANDOFF_VERIFICATION_FAILED", message)

        if archive is None or sums is None:
            raise failed("--handoff-archive and --handoff-sums must be given together")
        try:
            archive_bytes = Path(archive).read_bytes()
            sums_text = Path(sums).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            raise failed(f"cannot read the handed-off release files: {exc}") from exc
        if not _verify_checksum(archive_bytes, sums_text, asset_name):
            raise failed(
                f"{archive} does not match the SHA256SUMS entry for {asset_name}"
            )
        binary_name = _binary_name(os_name)
        try:
            binary_bytes = _extract_binary_bytes(archive_bytes, asset_name, binary_name)
        except (InstallError, tarfile.TarError, zipfile.BadZipFile, OSError) as exc:
            raise failed(f"cannot extract {binary_name}: {exc}") from exc
        target = _running_executable(install_dir, binary_name)
        try:
            installed = target.read_bytes() if target is not None else None
        except OSError:
            installed = None
        if installed is None or (
            hashlib.sha256(installed).digest() != hashlib.sha256(binary_bytes).digest()
        ):
            raise failed(
                f"the handed-off release is not the running installed executable "
                f"({target or 'none found'})"
            )
        assert target is not None
        probe = prober([str(target), "--version"])
        if probe.returncode != 0:
            raise failed(f"{target} --version failed: {(probe.stderr or '').strip()}")
        return target, (probe.stdout or "").strip()

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
        native_plugin_agents: set[str] | None = None,
        only_agent: str | None = None,
    ) -> list[dict[str, Any]]:
        statuses = discover_agents(home=home, os_name=os_name, rush_binary=rush_binary)
        connect_tool = AgentConnectionTool()
        reports: list[dict[str, Any]] = []

        for status in statuses:
            adapter = ADAPTERS[status.agent_id]
            if not status.detected:
                reports.append(self._agent_report(status, adapter, "unsupported"))
                continue

            if status.agent_id in (native_plugin_agents or set()):
                # The native plugin registers Rush for this host; a manual
                # MCP connection as well would run two Rush servers.
                reports.append(self._agent_report(status, adapter, "native_plugin"))
                continue

            # `--agent HOST` (T26) connects exactly that host; others are left as is.
            if agents_flag != "all" or only_agent not in (None, status.agent_id):
                passive_state = (
                    "active" if status.status == "registered" else "configured"
                )
                reports.append(self._agent_report(status, adapter, passive_state))
                continue

            # Memory is user-scoped here (project_root=None), independent of any
            # project choice. An agent already connected+acknowledged is left
            # completely untouched: no re-registration, no duplicate memory
            # write, no disruption to whatever live session it already has.
            # Its instruction-block preview is still attached afterwards by
            # `_reconcile_guidance` (Phase 70 T3), so no reconnect is needed.
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

    def _reconcile_guidance(
        self,
        reports: list[dict[str, Any]],
        *,
        agents_flag: AgentsFlag,
        project_root: Path | None,
        data_root: Path,
        consent: bool,
        only_agent: str | None = None,
    ) -> None:
        """Attach the instruction-block preview to every connected-or-kept agent.

        Runs for already-active agents too (the early-continue branch in
        `_process_agents`), so existing connections receive guidance without
        a reconnect. It writes only with explicit guidance consent.
        """
        if agents_flag != "all":
            return
        for report in reports:
            if not report["detected"] or report["agent_id"] not in INSTRUCTION_TARGETS:
                continue
            if only_agent not in (None, report["agent_id"]):
                continue
            try:
                report["guidance"] = reconcile_agent_instructions(
                    report["agent_id"],
                    project_root=project_root,
                    data_root=data_root,
                    consent=consent,
                )
            except AgentConnectionError as exc:
                report["guidance"] = {"state": "error", "error": str(exc)}

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


def _running_executable(install_dir: Path | None, binary_name: str) -> Path | None:
    """The installed Rush executable this process runs as: the named install
    directory's binary, the frozen executable itself, or the `rush` on PATH."""
    if install_dir is not None:
        return Path(install_dir) / binary_name
    if getattr(sys, "frozen", False):
        return Path(sys.executable)
    try:
        return Path(resolve_rush_binary(None))
    except AgentConnectionError:
        return None


def run_install_command(
    *,
    setup: bool,
    agent: str | None,
    project_path: str | None,
    interactive: bool,
    **install_kwargs: Any,
) -> dict[str, Any]:
    """`rush install` orchestration, kept out of the Click handler.

    With `setup` (the guided bootstrap's `--setup`) the install connects no
    agent itself; the selected host and project go to the same setup
    implementation as `rush setup`, with consent only from the controlling
    terminal. Otherwise `agent` connects exactly that host and the result
    carries the one shell-quoted `rush setup PATH [--agent HOST]` line that
    continues setup later -- nothing prompts. Returns the install result (the
    setup payload and that line added under `raw`), the text follow-up, and
    the setup exit code.
    """
    if setup:
        install_kwargs["agents"] = "none"  # the host is connected by setup itself
    result = InstallTool().run(
        project=None if setup else project_path,
        only_agent=None if setup or agent is None else SETUP_HOSTS[agent],
        permissions=ExecutionPermissions(
            network=True, download=True, cache_write=True, artifact_write=True
        ),
        **install_kwargs,
    )
    outcome: dict[str, Any] = {"install": result, "followup": None, "setup_exit": 0}
    raw = result.get("raw")
    if result["status"] == "error" or not isinstance(raw, dict):
        return outcome
    if not setup:
        project = raw.get("project")
        root = Path(project["root"]) if project else Path.cwd().resolve()
        raw["next_command"] = outcome["followup"] = setup_resume_command(root, agent)
        return outcome
    root = Path(project_path).expanduser() if project_path else Path.cwd()
    if not root.is_dir():
        payload: dict[str, Any] = {
            "status": "error",
            "reason": "project_missing",
            "message": f"--project {root} is not a directory",
        }
        code = 2
    else:
        payload, code = run_guided_setup(root.resolve(), agent, interactive=interactive)
    raw["setup"] = payload
    outcome["followup"] = render_setup_result(payload)
    outcome["setup_exit"] = code
    return outcome


__all__ = [
    "RELEASE_ASSET_MATRIX",
    "InstallError",
    "InstallTool",
    "UnsupportedPlatformError",
    "finalize_agent_plugin_upgrade",
    "install_native_agent_plugin",
    "run_install_command",
    "select_release_asset",
    "upgrade_native_agent_plugin",
]
