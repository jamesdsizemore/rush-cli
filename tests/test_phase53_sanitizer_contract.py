"""Contract tests for Phase 53: Complete Sanitizer Kernel (P53.1.1)."""

from __future__ import annotations

import copy
from typing import Any

from rush.safety.redactor import SanitizationResult, sanitize_value


def test_fresh_sentinel_is_removed_from_values_and_keys() -> None:
    """Verify that fresh secret sentinels are redacted from nested values and dictionary keys."""
    fresh_anthropic = "sk-ant-api03-abcdef123456789012345678"
    fresh_openai = "sk-proj-12345678901234567890abcdef"
    fresh_ghp = "ghp_12345678901234567890abcdef"
    fresh_bearer = "Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.abcdef1234567890"
    fresh_password = "password=SuperSecretPassword123"

    payload: dict[str, Any] = {
        "anthropic": fresh_anthropic,
        fresh_openai: "nested_value",
        "nested": {
            "list": [1, fresh_ghp, 3],
            fresh_bearer: {"sub": fresh_password},
        },
    }

    result = sanitize_value(payload)
    assert isinstance(result, SanitizationResult)
    assert result.redacted is True
    assert result.redaction_count >= 5

    # Ensure none of the raw secret sentinels appear in values or keys
    raw_text = str(result.value)
    assert fresh_anthropic not in raw_text
    assert fresh_openai not in raw_text
    assert fresh_ghp not in raw_text
    assert "SuperSecretPassword123" not in raw_text
    assert "eyJhbGciOiJIUzI1Ni" not in raw_text

    # Verify key redaction
    assert any("[REDACTED" in k for k in result.value)
    nested_sub = result.value["nested"]
    assert any("[REDACTED" in k for k in nested_sub)


def test_key_collision_is_loss_visible() -> None:
    """Verify that dictionary keys colliding upon redaction are preserved deterministically with loss visibility."""
    key1 = "sk-ant-api03-keyONE11111111111111111"
    key2 = "sk-ant-api03-keyTWO22222222222222222"

    payload = {
        key1: "value_one",
        key2: "value_two",
    }

    result = sanitize_value(payload)
    assert isinstance(result, SanitizationResult)
    assert result.redacted is True
    assert len(result.value) == 2  # Both entries MUST be preserved; no silent drop!
    assert "value_one" in result.value.values()
    assert "value_two" in result.value.values()
    assert len(result.collisions) == 1
    assert result.collisions[0]["count"] >= 2
    # Ensure raw secret keys are not leaked in the collision metadata
    assert key1 not in str(result.collisions)
    assert key2 not in str(result.collisions)


def test_url_and_exception_forms_are_sanitized() -> None:
    """Verify that URLs with credentials and exception forms are redacted, and unsupported types fail closed."""
    url_with_creds = "https://admin:SuperSecretPass999@api.example.com/v1/projects"
    result_url = sanitize_value(url_with_creds)
    assert "SuperSecretPass999" not in str(result_url.value)
    assert "admin" not in str(result_url.value)
    assert result_url.redacted is True

    # Exception string
    exc = ValueError("Failed authenticating token=secret_token_val_12345 in db")
    result_exc = sanitize_value(exc)
    assert "secret_token_val_12345" not in str(result_exc.value)
    assert result_exc.redacted is True

    # Unsupported object (socket, lambda, generator) must not expose raw internal repr with secrets
    class CustomSecretHolder:
        def __init__(self, token: str) -> None:
            self.token = token

        def __repr__(self) -> str:
            return f"<CustomSecretHolder token={self.token}>"

    holder = CustomSecretHolder("sk-ant-api03-secretinrepr123456")
    result_holder = sanitize_value(holder)
    assert "sk-ant-api03-secretinrepr123456" not in str(result_holder.value)
    assert "[UNSUPPORTED_TYPE:" in str(result_holder.value)


def test_execution_input_is_unchanged() -> None:
    """Verify that sanitize_value never mutates the original input objects."""
    key = "sk-ant-api03-inputkey1234567890"
    val = "sk-proj-inputval1234567890abcdef"
    original: dict[str, Any] = {
        key: val,
        "list": ["sk-ant-api03-item1234567890", {"inner": "secret"}],
    }
    clone = copy.deepcopy(original)

    result = sanitize_value(original)
    assert result.redacted is True
    # The original dict and clone must be 100% identical and unmutated
    assert original == clone
    assert key in original
    assert original[key] == val


def test_circular_reference_handled_gracefully() -> None:
    """Adversarial check: cyclical structures must not cause infinite recursion."""
    cyclic: dict[str, Any] = {"name": "root"}
    cyclic["self"] = cyclic

    result = sanitize_value(cyclic)
    assert result.value["name"] == "root"
    assert result.value["self"] == "[CIRCULAR_REFERENCE]"
