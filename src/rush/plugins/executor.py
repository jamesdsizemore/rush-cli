"""Hardened plugin executor with environment sanitization and subprocess isolation."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from rush.contracts.results import (
    FindingV1,
    ToolResultV1,
    adapt_legacy_tool_result,
    validate_tool_result,
)
from rush.io.physical_paths import PhysicalRoot
from rush.logging import get_logger
from rush.plugins.closure import (
    ClosureTamperedError,
    PluginClosureManifest,
    _compute_default_platform_identity,
    _compute_default_runtime_identity,
)
from rush.plugins.loader import PluginSpec
from rush.plugins.sandboxed_env import SandboxedEnvironment
from rush.plugins.secret_channels import (
    SecretChannelError,
    negotiate_secret_channel,
)
from rush.plugins.snapshot_store import PluginSnapshotStore
from rush.plugins.trust_store import (
    PluginTrustStore,
    TrustedPluginRecord,
    UntrustedPluginError,
)

__all__ = [
    "ClosureTamperedError",
    "HardenedPluginExecutor",
    "PluginClosureManifest",
    "PluginSnapshotStore",
    "PluginTrustStore",
    "SandboxedEnvironment",
    "SecretChannelError",
    "UntrustedPluginError",
    "negotiate_secret_channel",
]

logger = get_logger("plugins.executor")


class HardenedPluginExecutor:
    """Executes trust-gated plugins under bounded subprocess isolation and physical snapshots."""

    def __init__(
        self,
        repo_root: Path,
        trust_store: PluginTrustStore | None = None,
        snapshot_store: PluginSnapshotStore | None = None,
    ) -> None:
        self.repo_root = repo_root.resolve()
        self.trust_store = (
            trust_store if trust_store is not None else PluginTrustStore(self.repo_root)
        )
        self.snapshot_store = (
            snapshot_store if snapshot_store is not None else PluginSnapshotStore()
        )

    def _resolve_snapshot_dir(self, record: TrustedPluginRecord) -> Path:
        if (self.snapshot_store.snapshots_root / record.closure_digest).is_dir():
            return (
                self.snapshot_store.snapshots_root / record.closure_digest
            ).resolve()
        if record.snapshot_path and Path(record.snapshot_path).is_dir():
            return Path(record.snapshot_path).resolve()
        if record.snapshot_path and (self.repo_root / record.snapshot_path).is_dir():
            return (self.repo_root / record.snapshot_path).resolve()
        return (self.snapshot_store.snapshots_root / record.closure_digest).resolve()

    def _fail_untrusted(self, plugin: PluginSpec) -> ToolResultV1:
        fp_seed = (
            f"{plugin.name}:{plugin.executable_path}:untrusted-plugin-execution-blocked"
        )
        fingerprint = hashlib.sha256(fp_seed.encode("utf-8")).hexdigest()
        finding = FindingV1(
            path=str(plugin.executable_path),
            line=1,
            column=1,
            rule_id="untrusted-plugin-execution-blocked",
            severity="warning",
            message="Plugin blocked by zero-trust security gate.",
            fingerprint=fingerprint,
        )
        return ToolResultV1(
            schema_version="1.0.0",
            tool="plugin",
            engine=plugin.name,
            engine_version=None,
            status="skipped",
            duration_ms=0,
            summary=(
                f"Plugin '{plugin.name}' is untrusted. "
                f"Run 'rush trust grant {plugin.name}' to authorize."
            ),
            findings=[finding],
        )

    def execute(
        self,
        plugin: PluginSpec,
        paths: list[Path],
        secrets: dict[str, str] | None = None,
    ) -> ToolResultV1:
        # Pre-flight check 1: Load trust record from self.trust_store.load_trust_store()
        trusted_records = self.trust_store.load_trust_store()
        record = trusted_records.get(plugin.name)
        if record is None:
            return self._fail_untrusted(plugin)

        closure: PluginClosureManifest | None = getattr(plugin, "closure", None)
        if closure is not None and closure.closure_digest != record.closure_digest:
            return self._fail_untrusted(plugin)

        if not self.trust_store.is_trusted(plugin.name, record.closure_digest):
            return self._fail_untrusted(plugin)

        # Pre-flight check 2: Verify snapshot integrity with self.snapshot_store.verify_snapshot()
        if closure is None:
            snapshot_dir_candidate = self._resolve_snapshot_dir(record)
            manifest_file = snapshot_dir_candidate / ".closure_manifest.json"
            if manifest_file.is_file():
                try:
                    closure_data = json.loads(manifest_file.read_text(encoding="utf-8"))
                    closure = PluginClosureManifest.from_dict(closure_data)
                except (
                    OSError,
                    json.JSONDecodeError,
                    KeyError,
                    TypeError,
                    ValueError,
                ):
                    closure = None

        if closure is None:
            raise ClosureTamperedError(
                f"Missing or unverifiable closure manifest for plugin '{plugin.name}'"
            )

        if closure.closure_digest != record.closure_digest:
            raise ClosureTamperedError(
                f"Closure digest mismatch for plugin '{plugin.name}'"
            )

        current_runtime = _compute_default_runtime_identity()
        if closure.runtime_identity and closure.runtime_identity != current_runtime:
            raise ClosureTamperedError(
                f"Runtime identity mismatch for plugin '{plugin.name}': "
                f"expected '{closure.runtime_identity}', got '{current_runtime}'"
            )

        current_platform = _compute_default_platform_identity()
        if closure.platform_identity and closure.platform_identity != current_platform:
            raise ClosureTamperedError(
                f"Platform identity mismatch for plugin '{plugin.name}': "
                f"expected '{closure.platform_identity}', got '{current_platform}'"
            )

        if not self.snapshot_store.verify_snapshot(closure):
            raise ClosureTamperedError(
                f"Snapshot integrity verification failed for plugin '{plugin.name}'"
            )

        # Pre-flight check 3: Negotiate secret channels if secrets declared
        declared_refs = list(
            getattr(plugin, "secret_refs", ()) or closure.declared_secret_refs
        )
        channel_type = getattr(plugin, "channel_type", "stdin")
        secret_ctx = None
        if secrets is not None or declared_refs:
            secret_ctx = negotiate_secret_channel(
                channel_type=channel_type,
                secret_refs=declared_refs,
                secrets=secrets or {},
            )

        # Launch: Resolve snapshot entrypoint under PhysicalRoot
        snapshot_dir = self._resolve_snapshot_dir(record)
        snapshot_physical = PhysicalRoot(snapshot_dir)
        entry_rel = Path(closure.entrypoint)
        snapshot_entry = snapshot_physical.open_contained(entry_rel)

        cmd: list[str] = []
        replaced = False
        for arg in plugin.command:
            if (
                arg == closure.entrypoint
                or arg == str(plugin.executable_path)
                or arg == plugin.executable_path.name
                or (
                    Path(arg).name == Path(closure.entrypoint).name
                    and not Path(arg).is_absolute()
                )
            ):
                cmd.append(str(snapshot_entry))
                replaced = True
            else:
                cmd.append(arg)

        if not replaced and str(snapshot_entry) not in cmd:
            cmd.append(str(snapshot_entry))

        if cmd and cmd[0] in ("python", "python3"):
            cmd[0] = sys.executable

        target_args = [str(p) for p in paths]
        full_command = [*cmd, *target_args]

        sanitized_env = SandboxedEnvironment.get_sanitized_env()
        if secret_ctx:
            sanitized_env.update(secret_ctx.env_overrides)
        sanitized_env["PYTHONPATH"] = str(snapshot_dir)

        stdin_bytes: bytes | None = None
        pass_fds: tuple[int, ...] = ()
        if secret_ctx:
            if secret_ctx.channel_type == "stdin":
                stdin_bytes = secret_ctx.stdin_payload
            elif secret_ctx.channel_type == "descriptor":
                pass_fds = secret_ctx.pass_fds

        start_time = time.perf_counter()
        popen_kwargs: dict[str, Any] = {
            "cwd": str(self.repo_root),
            "env": sanitized_env,
            "stdout": subprocess.PIPE,
            "stderr": subprocess.PIPE,
            "text": False,
            "shell": False,
        }
        if stdin_bytes is not None:
            popen_kwargs["stdin"] = subprocess.PIPE
        else:
            popen_kwargs["stdin"] = subprocess.DEVNULL

        if pass_fds and os.name != "nt":
            popen_kwargs["pass_fds"] = pass_fds

        try:
            proc = subprocess.Popen(full_command, **popen_kwargs)
            stdout_raw, stderr_raw = proc.communicate(
                input=stdin_bytes,
                timeout=plugin.timeout_seconds,
            )
            duration_ms = int((time.perf_counter() - start_time) * 1000)
            code = proc.returncode
            stdout = stdout_raw.decode("utf-8", errors="replace")
            _stderr = stderr_raw.decode("utf-8", errors="replace")
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.communicate()
            duration_ms = int((time.perf_counter() - start_time) * 1000)
            return ToolResultV1(
                schema_version="1.0.0",
                tool="plugin",
                engine=plugin.name,
                engine_version="1.0",
                status="error",
                duration_ms=duration_ms,
                summary=f"Plugin '{plugin.name}' timed out after {plugin.timeout_seconds} seconds.",
                findings=[],
            )

        # Output parsing: Convert stdout to ToolResultV1
        try:
            data = json.loads(stdout)
            if isinstance(data, dict):
                if data.get("schema_version") == "1.0.0":
                    return validate_tool_result(data)
                legacy_dict = dict(data)
                legacy_dict.setdefault("tool", "plugin")
                legacy_dict.setdefault("engine", plugin.name)
                legacy_dict.setdefault("engine_version", "1.0")
                legacy_dict.setdefault("status", "ok" if code == 0 else "fail")
                legacy_dict.setdefault("duration_ms", duration_ms)
                legacy_dict.setdefault("summary", f"Plugin {plugin.name} finished.")
                if legacy_dict.get("status") not in (
                    "ok",
                    "warn",
                    "fail",
                    "error",
                    "skipped",
                ):
                    legacy_dict["status"] = "ok" if code == 0 else "fail"
                return adapt_legacy_tool_result(legacy_dict)
        except (
            json.JSONDecodeError,
            KeyError,
            TypeError,
            ValueError,
            UnicodeDecodeError,
        ) as exc:
            logger.debug("Failed to parse plugin output as JSON: %s", exc)

        return ToolResultV1(
            schema_version="1.0.0",
            tool="plugin",
            engine=plugin.name,
            engine_version="1.0",
            status="ok" if code == 0 else "fail",
            duration_ms=duration_ms,
            summary=f"Plugin {plugin.name} exited with code {code}.",
            findings=[],
        )
