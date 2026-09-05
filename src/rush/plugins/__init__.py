"""Rush Extensible Plugin Runtime & Trust Gate.

Architecture §8, Phase 28.
Enforces Control 6: Repository Trust Gating.
"""

from __future__ import annotations

from .closure import (
    ClosureError,
    ClosureTamperedError,
    PluginClosureManifest,
    build_plugin_closure,
)
from .executor import HardenedPluginExecutor
from .hash_verifier import PreExecutionHashVerifier
from .loader import (
    CustomPlugin,
    PluginLoader,
    PluginSpec,
    discover_plugins,
    execute_plugin,
)
from .manifest_schema import PluginManifestValidator
from .sandboxed_env import SandboxedEnvironment
from .secret_channels import (
    SecretChannelError,
    SecretDeliveryContext,
    negotiate_secret_channel,
)
from .skills_generator import AgentSkillGenerator
from .snapshot_store import PluginSnapshotStore, SnapshotError
from .trust import is_repo_trusted, revoke_trust, trust_repo
from .trust_store import (
    PluginTrustError,
    PluginTrustStore,
    TrustedPluginRecord,
    UntrustedPluginError,
)
from .validator import validate_plugin_output

__all__ = [
    "AgentSkillGenerator",
    "ClosureError",
    "ClosureTamperedError",
    "CustomPlugin",
    "HardenedPluginExecutor",
    "PluginClosureManifest",
    "PluginLoader",
    "PluginManifestValidator",
    "PluginSnapshotStore",
    "PluginSpec",
    "PluginTrustError",
    "PluginTrustStore",
    "PreExecutionHashVerifier",
    "SandboxedEnvironment",
    "SecretChannelError",
    "SecretDeliveryContext",
    "SnapshotError",
    "TrustedPluginRecord",
    "UntrustedPluginError",
    "build_plugin_closure",
    "discover_plugins",
    "execute_plugin",
    "is_repo_trusted",
    "negotiate_secret_channel",
    "revoke_trust",
    "trust_repo",
    "validate_plugin_output",
]
