"""High-speed Shannon entropy, regex secret redactor, and recursive serialization sanitizer."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from typing import Any

SECRET_PATTERNS = [
    (re.compile(r"sk-ant-[a-zA-Z0-9_\-]{20,}"), "[REDACTED_ANTHROPIC_KEY]"),
    (re.compile(r"sk-[a-zA-Z0-9_\-]{20,}"), "[REDACTED_OPENAI_KEY]"),
    (re.compile(r"ghp_[a-zA-Z0-9]{20,}"), "[REDACTED_GITHUB_TOKEN]"),
    (re.compile(r"gho_[a-zA-Z0-9]{20,}"), "[REDACTED_GITHUB_OAUTH]"),
    (re.compile(r"AKIA[0-9A-Z]{16}"), "[REDACTED_AWS_ACCESS_KEY]"),
    (
        re.compile(
            r"-----BEGIN [A-Z ]+ PRIVATE KEY-----[\s\S]*?-----END [A-Z ]+ PRIVATE KEY-----"
        ),
        "[REDACTED_PRIVATE_KEY]",
    ),
    (
        re.compile(r"(?i)\b(bearer)\s+([a-zA-Z0-9_\-\.]{20,})"),
        r"Bearer [REDACTED_BEARER_TOKEN]",
    ),
    (
        re.compile(
            r"(?i)\b(api[_-]?key|token|secret|password|authorization)\s*([=:])\s*([^\s,;]+)"
        ),
        r"\1\2[REDACTED]",
    ),
    (
        re.compile(r"(?i)(https?://)([^:]+):([^@]+)@"),
        r"\1[REDACTED_USER]:[REDACTED_PASSWORD]@",
    ),
]


@dataclass(frozen=True)
class SanitizationResult:
    """Immutable result of a recursive sanitization pass."""

    value: Any
    redaction_count: int = 0
    collisions: list[dict[str, Any]] = field(default_factory=list)

    @property
    def redacted(self) -> bool:
        return self.redaction_count > 0 or len(self.collisions) > 0


def sanitize_value(value: Any) -> SanitizationResult:
    """Recursively sanitize JSON-compatible values and mappings before write or serialization.

    Guarantees:
    - Never mutates the original execution input.
    - Sanitizes both values and dictionary keys.
    - Key collisions caused by redaction are handled deterministically with visible collision metadata.
    - Unsupported or un-serializable objects fail closed with a safe placeholder, never leaking raw repr.
    """
    total_count = 0
    all_collisions: list[dict[str, Any]] = []
    visited_ids: set[int] = set()

    def _sanitize(val: Any) -> Any:
        nonlocal total_count

        if val is None or isinstance(val, (int, float, bool)):
            return val

        if isinstance(val, str):
            redacted = SecretRedactor.redact_text(val)
            if redacted != val:
                total_count += 1
            return redacted

        if isinstance(val, (list, tuple, dict)):
            val_id = id(val)
            if val_id in visited_ids:
                return "[CIRCULAR_REFERENCE]"
            visited_ids.add(val_id)
            try:
                if isinstance(val, list):
                    return [_sanitize(item) for item in val]

                if isinstance(val, tuple):
                    return tuple(_sanitize(item) for item in val)

                if isinstance(val, dict):
                    new_dict: dict[str, Any] = {}
                    seen_raw_keys: dict[str, list[str]] = {}

                    for k, v in val.items():
                        if isinstance(k, str):
                            sanitized_k = SecretRedactor.redact_text(k)
                            if sanitized_k != k:
                                total_count += 1
                        else:
                            sanitized_k = f"[UNSUPPORTED_KEY:{type(k).__name__}]"
                            total_count += 1

                        sanitized_v = _sanitize(v)

                        if sanitized_k in new_dict:
                            # Key collision detected
                            seen_raw_keys.setdefault(sanitized_k, []).append(str(k))
                            collision_idx = len(seen_raw_keys[sanitized_k])
                            target_k = f"{sanitized_k}__collision_{collision_idx}"
                            new_dict[target_k] = sanitized_v
                            total_count += 1
                        else:
                            seen_raw_keys[sanitized_k] = [str(k)]
                            new_dict[sanitized_k] = sanitized_v

                    for sk, raw_list in seen_raw_keys.items():
                        if len(raw_list) > 1:
                            all_collisions.append(
                                {
                                    "sanitized_key": sk,
                                    "count": len(raw_list),
                                }
                            )

                    return new_dict
            finally:
                visited_ids.remove(val_id)

        if isinstance(val, BaseException):
            sanitized_msg = SecretRedactor.redact_text(str(val))
            if sanitized_msg != str(val):
                total_count += 1
            return f"[EXCEPTION:{type(val).__name__}: {sanitized_msg}]"

        # Unsupported arbitrary objects
        total_count += 1
        return f"[UNSUPPORTED_TYPE:{type(val).__name__}]"

    clean_value = _sanitize(value)
    return SanitizationResult(
        value=clean_value,
        redaction_count=total_count,
        collisions=all_collisions,
    )


class SecretRedactor:
    """Redacts secrets, API keys, and sensitive tokens from logs, diffs, and tool outputs."""

    @staticmethod
    def redact_text(text: str) -> str:
        if not text:
            return text

        redacted = text
        for pattern, replacement in SECRET_PATTERNS:
            redacted = pattern.sub(replacement, redacted)
        return redacted

    @classmethod
    def redact_value(cls, value: Any) -> tuple[Any, int]:
        """Recursively redact JSON-compatible values before they are persisted."""
        result = sanitize_value(value)
        return result.value, result.redaction_count

    @staticmethod
    def calculate_entropy(data: str) -> float:
        """Calculates Shannon entropy to detect high-randomness secret strings."""
        if not data:
            return 0.0
        entropy = 0.0
        for x in set(data):
            p_x = float(data.count(x)) / len(data)
            if p_x > 0:
                entropy += -p_x * math.log2(p_x)
        return entropy
