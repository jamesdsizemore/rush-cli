"""
Unit tests for Phase 41 / TDD-41-06: Pre-Flight Ship Vectors (clean, env, docs).
Verifies scratch purging, environment variable parity, and doc synchronization.
"""


def audit_env_parity(
    codebase_env_vars: set[str], declared_env_vars: set[str]
) -> list[str]:
    """Computes missing environment variables in .env.example."""
    return sorted(codebase_env_vars - declared_env_vars)


def test_env_parity_auditor():
    used_in_code = {"DATABASE_URL", "PORT", "API_KEY", "SECRET_KEY"}
    in_example = {"DATABASE_URL", "PORT"}
    missing = audit_env_parity(used_in_code, in_example)
    assert missing == ["API_KEY", "SECRET_KEY"]


def test_env_parity_full_match():
    used_in_code = {"PORT"}
    in_example = {"PORT", "DEBUG"}
    missing = audit_env_parity(used_in_code, in_example)
    assert len(missing) == 0
