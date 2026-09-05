"""Transitive closure discovery and cryptographic manifest generation for external plugins.

Architecture §8, Phase 56: User-Owned Content-Addressed Plugin Trust.
Guarantees:
- Discovers and cryptographically binds every file, script, and asset in plugin root.
- Rejects symlinks, Windows directory junctions, and hardlinks fail-closed.
- Binds configuration dictionary, allowed environment names, declared secrets,
  runtime/interpreter identity, and platform architecture.
- Generates deterministic SHA-256 closure digests.
"""

from __future__ import annotations

import hashlib
import json
import os
import platform
import stat
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from rush.io.physical_paths import ContainmentError, PhysicalRoot
from rush.plugins.trust_store import PluginTrustError


class ClosureError(PluginTrustError):
    """Base exception for plugin closure construction and verification errors."""

    def __init__(self, message: str, code: str = "CLOSURE_ERROR") -> None:
        super().__init__(message=message, code=code)


class ClosureTamperedError(ClosureError):
    """Raised when plugin files or closures fail cryptographic hash verification."""

    def __init__(self, message: str, code: str = "CLOSURE_TAMPERED") -> None:
        super().__init__(message=message, code=code)


@dataclass(frozen=True)
class PluginClosureManifest:
    """Cryptographic closure manifest for an external quality plugin.

    Digests code, configuration, environment names, runtime, and platform
    into an immutable content-addressed identity.
    """

    schema_version: str = "1.0.0"
    plugin_name: str = ""
    entrypoint: str = ""
    file_manifest: dict[str, str] = field(default_factory=dict)
    config_digest: str = ""
    allowed_env_names: tuple[str, ...] = ()
    declared_secret_refs: tuple[str, ...] = ()
    runtime_identity: str = ""
    platform_identity: str = ""
    closure_digest: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Serialize manifest to canonical dictionary representation."""
        return {
            "schema_version": self.schema_version,
            "plugin_name": self.plugin_name,
            "entrypoint": self.entrypoint,
            "file_manifest": dict(sorted(self.file_manifest.items())),
            "config_digest": self.config_digest,
            "allowed_env_names": list(self.allowed_env_names),
            "declared_secret_refs": list(self.declared_secret_refs),
            "runtime_identity": self.runtime_identity,
            "platform_identity": self.platform_identity,
            "closure_digest": self.closure_digest,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PluginClosureManifest:
        """Construct manifest from dictionary representation."""
        return cls(
            schema_version=data.get("schema_version", "1.0.0"),
            plugin_name=data["plugin_name"],
            entrypoint=data["entrypoint"],
            file_manifest=dict(data.get("file_manifest", {})),
            config_digest=data.get("config_digest", ""),
            allowed_env_names=tuple(data.get("allowed_env_names", ())),
            declared_secret_refs=tuple(data.get("declared_secret_refs", ())),
            runtime_identity=data.get("runtime_identity", ""),
            platform_identity=data.get("platform_identity", ""),
            closure_digest=data.get("closure_digest", ""),
        )


def _compute_default_runtime_identity() -> str:
    try:
        exe_path = Path(sys.executable).resolve()
        exe_hash = hashlib.sha256(exe_path.read_bytes()).hexdigest()
        return f"python{sys.version_info.major}.{sys.version_info.minor}:{exe_path}:{exe_hash}"
    except (OSError, ValueError):
        return f"python{sys.version_info.major}.{sys.version_info.minor}:{sys.version}"


def _compute_default_platform_identity() -> str:
    return f"{sys.platform}-{platform.machine()}"


def build_plugin_closure(
    plugin_root: Path,
    entrypoint: Path,
    config: dict[str, Any],
    allowed_env_names: list[str] | tuple[str, ...] | None = None,
    declared_secret_refs: list[str] | tuple[str, ...] | None = None,
    runtime_identity: str | None = None,
    platform_identity: str | None = None,
    plugin_name: str | None = None,
) -> PluginClosureManifest:
    """Construct an immutable cryptographic PluginClosureManifest for an external plugin.

    Validates:
    - plugin_root and entrypoint exist and are contained within PhysicalRoot.
    - Rejects symlinks, directory junctions, and hardlinks fail-closed.
    - Recursively computes SHA-256 digests of all files in plugin_root.
    - Computes canonical config_digest over sorted JSON of config dict.
    - Computes closure_digest over canonical serialized manifest fields.
    """
    plugin_root_resolved = Path(plugin_root).resolve()
    if not plugin_root_resolved.exists():
        raise ClosureError(f"Plugin root does not exist: {plugin_root}")
    if not plugin_root_resolved.is_dir():
        raise ClosureError(f"Plugin root is not a directory: {plugin_root}")

    # Physical root boundary containment validation
    if Path(plugin_root).is_symlink():
        raise ContainmentError(
            "SYMLINK_DISALLOWED",
            f"Plugin root is a symlink: {plugin_root}",
            str(plugin_root),
        )

    st_root = os.lstat(plugin_root)
    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    if (getattr(st_root, "st_file_attributes", 0) & reparse_flag) or (
        os.name == "nt" and getattr(plugin_root, "is_junction", lambda: False)()
    ):
        raise ContainmentError(
            "REPARSE_POINT_DISALLOWED",
            f"Plugin root is a junction: {plugin_root}",
            str(plugin_root),
        )

    physical_root = PhysicalRoot(plugin_root_resolved)

    # Determine entrypoint relative path
    entrypoint_path = Path(entrypoint)
    if entrypoint_path.is_absolute():
        try:
            rel_entry = entrypoint_path.resolve().relative_to(plugin_root_resolved)
        except ValueError:
            try:
                rel_entry = entrypoint_path.relative_to(plugin_root)
            except ValueError:
                raise ContainmentError(
                    "PATH_ESCAPE_DISALLOWED",
                    f"Entrypoint '{entrypoint}' escapes plugin root '{plugin_root}'",
                    str(entrypoint),
                )
    else:
        rel_entry = entrypoint_path

    # Validate entrypoint containment and verify absence of symlinks/junctions
    candidate_entry = physical_root.open_contained(rel_entry)
    if not candidate_entry.exists():
        raise ClosureError(f"Entrypoint does not exist: {candidate_entry}")
    if not candidate_entry.is_file():
        raise ClosureError(f"Entrypoint is not a regular file: {candidate_entry}")

    st_entry = os.lstat(candidate_entry)
    if stat.S_ISREG(st_entry.st_mode) and st_entry.st_nlink > 1:
        raise ContainmentError(
            "HARDLINK_DISALLOWED",
            f"Hardlink detected at entrypoint '{candidate_entry}'",
            str(rel_entry),
        )

    # Walk all files under plugin_root, validating containment and computing hashes
    file_manifest: dict[str, str] = {}
    for root, dirs, files in os.walk(plugin_root_resolved, followlinks=False):
        current_dir_path = Path(root)
        for d in sorted(dirs):
            sub_dir = current_dir_path / d
            rel_d = sub_dir.relative_to(plugin_root_resolved)
            physical_root.open_contained(rel_d)

        for f in sorted(files):
            file_path = current_dir_path / f
            rel_f = file_path.relative_to(plugin_root_resolved)
            physical_root.open_contained(rel_f)

            st_f = os.lstat(file_path)
            if stat.S_ISREG(st_f.st_mode) and st_f.st_nlink > 1:
                raise ContainmentError(
                    "HARDLINK_DISALLOWED",
                    f"Hardlink detected at '{file_path}'",
                    str(rel_f),
                )

            hasher = hashlib.sha256()
            with open(file_path, "rb") as fp:
                while chunk := fp.read(65536):
                    hasher.update(chunk)
            file_manifest[rel_f.as_posix()] = hasher.hexdigest()

    rel_entry_posix = rel_entry.as_posix()
    if rel_entry_posix not in file_manifest:
        raise ClosureError(
            f"Entrypoint '{rel_entry_posix}' was not indexed in file manifest"
        )

    # Compute canonical config_digest
    config_bytes = json.dumps(config, sort_keys=True, separators=(",", ":")).encode(
        "utf-8"
    )
    config_digest = hashlib.sha256(config_bytes).hexdigest()

    # Allowed environments and secret references
    allowed_env = tuple(sorted(allowed_env_names or ()))
    declared_secrets = tuple(sorted(declared_secret_refs or ()))

    # Identities
    runtime_id = runtime_identity or _compute_default_runtime_identity()
    platform_id = platform_identity or _compute_default_platform_identity()

    resolved_plugin_name = plugin_name or str(
        config.get("name") or plugin_root_resolved.name
    )
    schema_version = "1.0.0"

    # Compute overall closure digest over canonical JSON representation
    closure_payload = {
        "schema_version": schema_version,
        "plugin_name": resolved_plugin_name,
        "entrypoint": rel_entry_posix,
        "file_manifest": dict(sorted(file_manifest.items())),
        "config_digest": config_digest,
        "allowed_env_names": list(allowed_env),
        "declared_secret_refs": list(declared_secrets),
        "runtime_identity": runtime_id,
        "platform_identity": platform_id,
    }
    closure_json = json.dumps(
        closure_payload, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    closure_digest = hashlib.sha256(closure_json).hexdigest()

    return PluginClosureManifest(
        schema_version=schema_version,
        plugin_name=resolved_plugin_name,
        entrypoint=rel_entry_posix,
        file_manifest=dict(sorted(file_manifest.items())),
        config_digest=config_digest,
        allowed_env_names=allowed_env,
        declared_secret_refs=declared_secrets,
        runtime_identity=runtime_id,
        platform_identity=platform_id,
        closure_digest=closure_digest,
    )
