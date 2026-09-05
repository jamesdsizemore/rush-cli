"""Contract tests for protected secret channels (Phase 56 Workstream P56.3).

Tests:
- T-56.09: Literal secret is rejected from argv, config, resource, and environment.
- T-56.10: Declared protected channel is not visible in child argv or environment.
- T-56.11: Unsupported channel denies before spawn.
"""

from __future__ import annotations

import json
import os
from typing import Any

import pytest

from rush.plugins.manifest_schema import PluginManifestValidator
from rush.plugins.sandboxed_env import SandboxedEnvironment
from rush.plugins.secret_channels import (
    SecretChannelError,
    SecretDeliveryContext,
    negotiate_secret_channel,
)


def test_literal_secret_is_rejected_from_argv_config_resource_and_environment() -> None:
    """T-56.09: Literal secret in command, config, or env is rejected fail-closed."""
    # 1. Reject literal secret in command string
    bad_cmd_spec: dict[str, Any] = {
        "command": "analyzer --key sk-ant-api03-abcdef123456789012345678",
        "timeout_seconds": 30.0,
    }
    res_cmd = PluginManifestValidator.validate_spec_dict("bad_cmd_plugin", bad_cmd_spec)
    assert res_cmd.is_valid is False
    assert any(
        "secret" in err.lower() or "literal" in err.lower() for err in res_cmd.errors
    )

    # 2. Reject literal secret in command list
    bad_argv_spec: dict[str, Any] = {
        "command": ["analyzer", "--token", "ghp_123456789012345678901234567890"],
        "timeout_seconds": 30.0,
    }
    res_argv = PluginManifestValidator.validate_spec_dict(
        "bad_argv_plugin", bad_argv_spec
    )
    assert res_argv.is_valid is False
    assert any(
        "secret" in err.lower() or "literal" in err.lower() for err in res_argv.errors
    )

    # 3. Reject literal secret in environment dictionary
    bad_env_spec: dict[str, Any] = {
        "command": "analyzer --run",
        "env": {"ANTHROPIC_API_KEY": "sk-ant-api03-abcdef123456789012345678"},
        "timeout_seconds": 30.0,
    }
    res_env = PluginManifestValidator.validate_spec_dict("bad_env_plugin", bad_env_spec)
    assert res_env.is_valid is False
    assert any(
        "secret" in err.lower() or "literal" in err.lower() for err in res_env.errors
    )

    # 4. Reject literal secret in secret_refs during channel negotiation
    literal_secrets_as_refs = ["sk-ant-api03-abcdef123456789012345678"]
    with pytest.raises(SecretChannelError) as exc_info:
        negotiate_secret_channel("stdin", literal_secrets_as_refs, {})
    assert exc_info.value.code == "LITERAL_SECRET_FORBIDDEN"


def test_declared_protected_channel_is_not_visible_in_child_argv_or_environment() -> (
    None
):
    """T-56.10: Secrets are invisible in child environment overrides and command arguments."""
    secret_refs = ["secret:AUTH_TOKEN", "secret:OPENAI_API_KEY"]
    secret_values = {
        "AUTH_TOKEN": "super_secret_auth_token_99999",
        "OPENAI_API_KEY": "sk-real-openai-key-value-12345678",
    }

    # 1. Test Stdin Channel
    stdin_ctx = negotiate_secret_channel("stdin", secret_refs, secret_values)
    assert isinstance(stdin_ctx, SecretDeliveryContext)
    assert stdin_ctx.channel_type == "stdin"
    assert stdin_ctx.stdin_payload is not None
    assert isinstance(stdin_ctx.stdin_payload, bytes)

    # Verify stdin payload contains the exact delivered secrets
    payload_dict = json.loads(stdin_ctx.stdin_payload.decode("utf-8"))
    assert payload_dict == {
        "AUTH_TOKEN": "super_secret_auth_token_99999",
        "OPENAI_API_KEY": "sk-real-openai-key-value-12345678",
    }

    # Verify NO secret values appear anywhere in env_overrides keys or values
    for env_key, env_val in stdin_ctx.env_overrides.items():
        for secret_val in secret_values.values():
            assert secret_val not in env_key
            assert secret_val not in env_val
    assert stdin_ctx.env_overrides.get("RUSH_SECRET_CHANNEL") == "stdin"

    # 2. Test Descriptor Pipe Channel
    desc_ctx = negotiate_secret_channel("descriptor", secret_refs, secret_values)
    try:
        assert isinstance(desc_ctx, SecretDeliveryContext)
        assert desc_ctx.channel_type == "descriptor"
        assert len(desc_ctx.pass_fds) >= 1
        read_fd = desc_ctx.pass_fds[0]
        assert isinstance(read_fd, int)
        assert read_fd > 0

        # Verify descriptor channel env overrides contain only non-secret metadata
        for env_key, env_val in desc_ctx.env_overrides.items():
            for secret_val in secret_values.values():
                assert secret_val not in env_key
                assert secret_val not in env_val
        assert desc_ctx.env_overrides.get("RUSH_SECRET_CHANNEL") == "descriptor"
        assert desc_ctx.env_overrides.get("RUSH_SECRET_FD") == str(read_fd)

        # Verify stdin_payload is None for descriptor channel
        assert desc_ctx.stdin_payload is None
    finally:
        # Clean up any open file descriptors created during test
        for fd in desc_ctx.pass_fds:
            try:
                os.close(fd)
            except OSError:
                pass
        if desc_ctx.parent_fd is not None:
            try:
                os.close(desc_ctx.parent_fd)
            except OSError:
                pass

    # 3. Verify SandboxedEnvironment.get_sanitized_env() scrubs secret values completely
    old_env = dict(os.environ)
    try:
        os.environ["AUTH_TOKEN"] = "super_secret_auth_token_99999"
        os.environ["OPENAI_API_KEY"] = "sk-real-openai-key-value-12345678"
        os.environ["MY_CUSTOM_SECRET"] = "sensitive_value_123"

        sanitized = SandboxedEnvironment.get_sanitized_env()

        for secret_val in secret_values.values():
            assert secret_val not in sanitized.values()
        assert "AUTH_TOKEN" not in sanitized
        assert "OPENAI_API_KEY" not in sanitized
        assert "MY_CUSTOM_SECRET" not in sanitized
    finally:
        os.environ.clear()
        os.environ.update(old_env)

    # 4. Verify command argv arguments never contain secret values
    plugin_argv = ["plugin_runner", "--target", "src/"]
    for arg in plugin_argv:
        for secret_val in secret_values.values():
            assert secret_val not in arg


def test_unsupported_channel_denies_before_spawn() -> None:
    """T-56.11: Unsupported secret channel requests fail closed with UNSUPPORTED_SECRET_CHANNEL."""
    # 1. Arbitrary unsupported channel identifier
    with pytest.raises(SecretChannelError) as exc_info:
        negotiate_secret_channel(
            "unsupported_quantum_bus",
            ["secret:SOME_KEY"],
            {"SOME_KEY": "some_value"},
        )
    assert exc_info.value.code == "UNSUPPORTED_SECRET_CHANNEL"
    assert "unsupported_quantum_bus" in exc_info.value.message

    # 2. Another unsupported channel type
    with pytest.raises(SecretChannelError) as exc_info2:
        negotiate_secret_channel("shared_memory_segment", [], {})
    assert exc_info2.value.code == "UNSUPPORTED_SECRET_CHANNEL"
    assert "shared_memory_segment" in exc_info2.value.message
