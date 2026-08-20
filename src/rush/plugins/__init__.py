"""Rush Extensible Plugin Runtime & Trust Gate.

Architecture §8, Phase 28.
Enforces Control 6: Repository Trust Gating.
"""

from __future__ import annotations

from .loader import CustomPlugin, discover_plugins, execute_plugin
from .trust import is_repo_trusted, revoke_trust, trust_repo
from .validator import validate_plugin_output

__all__ = [
    "CustomPlugin",
    "discover_plugins",
    "execute_plugin",
    "is_repo_trusted",
    "revoke_trust",
    "trust_repo",
    "validate_plugin_output",
]
