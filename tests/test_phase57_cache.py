"""Bridge test for remediation contract references.

Imports test_cache_identity_and_bypass_contracts from test_phase57_cache_policy
so remediation-contracts.toml references resolve directly.
"""

from __future__ import annotations

from tests.test_phase57_cache_policy import (
    test_cache_identity_and_bypass_contracts,
)

__all__ = ["test_cache_identity_and_bypass_contracts"]
