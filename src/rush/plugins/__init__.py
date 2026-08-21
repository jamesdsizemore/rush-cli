"""Rush Extensible Plugin Runtime & Trust Gate.

Architecture §8, Phase 28.
Enforces Control 6: Repository Trust Gating.
"""

from __future__ import annotations

from .executor import HardenedPluginExecutor
from .hash_verifier import PreExecutionHashVerifier
from .loader import CustomPlugin, PluginLoader, PluginSpec, discover_plugins, execute_plugin
from .manifest_schema import PluginManifestValidator
from .sandboxed_env import SandboxedEnvironment
from .skills_generator import AgentSkillGenerator
from .trust import is_repo_trusted, revoke_trust, trust_repo
from .trust_store import PluginTrustStore, TrustedPluginRecord
from .validator import validate_plugin_output

__all__ = [
    "AgentSkillGenerator",
    "CustomPlugin",
    "HardenedPluginExecutor",
    "PluginLoader",
    "PluginManifestValidator",
    "PluginSpec",
    "PluginTrustStore",
    "PreExecutionHashVerifier",
    "SandboxedEnvironment",
    "TrustedPluginRecord",
    "discover_plugins",
    "execute_plugin",
    "is_repo_trusted",
    "revoke_trust",
    "trust_repo",
    "validate_plugin_output",
]

