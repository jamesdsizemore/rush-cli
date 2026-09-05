"""Plugin manifest specification and parameter schema validator."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from rush.safety.redactor import SECRET_PATTERNS


@dataclass(frozen=True)
class PluginManifestValidationResult:
    is_valid: bool
    errors: list[str]


def _contains_literal_secret(text: str) -> bool:
    if not text or not isinstance(text, str):
        return False
    return any(p.search(text) is not None for p, _ in SECRET_PATTERNS)


class PluginManifestValidator:
    """Validates the structure and parameter types of plugin specifications."""

    @staticmethod
    def validate_spec_dict(
        name: str, spec_data: dict[str, Any]
    ) -> PluginManifestValidationResult:
        errors = []
        if not name or not name.isidentifier():
            errors.append(
                f"Plugin name '{name}' must be a valid alphanumeric identifier."
            )

        cmd = spec_data.get("command")
        if not cmd:
            errors.append(
                "Plugin specification must define a non-empty 'command' string or list."
            )
        elif isinstance(cmd, str) and _contains_literal_secret(cmd):
            errors.append(
                "Literal secret detected in plugin command string. "
                "Literal secrets are strictly forbidden in plugin manifests."
            )
        elif isinstance(cmd, list) and any(
            _contains_literal_secret(str(arg)) for arg in cmd
        ):
            errors.append(
                "Literal secret detected in plugin command arguments. "
                "Literal secrets are strictly forbidden in plugin manifests."
            )

        env = spec_data.get("env") or spec_data.get("environment")
        if isinstance(env, dict):
            for env_k, env_v in env.items():
                v_str = str(env_v)
                k_upper = str(env_k).upper()
                if _contains_literal_secret(v_str) or (
                    any(
                        s in k_upper
                        for s in ("KEY", "SECRET", "TOKEN", "PASSWORD", "AUTH")
                    )
                    and not v_str.startswith("secret:")
                ):
                    errors.append(
                        f"Literal secret detected in plugin environment variable '{env_k}'. "
                        "Literal secrets are strictly forbidden in plugin manifests; "
                        "use declared secret references and protected channels instead."
                    )

        secret_refs = spec_data.get("secret_refs")
        if isinstance(secret_refs, list):
            for ref in secret_refs:
                if _contains_literal_secret(str(ref)):
                    errors.append(
                        f"Literal secret detected in secret reference '{ref}'. "
                        "References must not contain raw secret values."
                    )

        timeout = spec_data.get("timeout_seconds", 30.0)
        try:
            t_val = float(timeout)
            if t_val <= 0 or t_val > 300.0:
                errors.append(
                    "Plugin timeout_seconds must be between 1.0 and 300.0 seconds."
                )
        except (ValueError, TypeError):
            errors.append("Plugin timeout_seconds must be a valid number.")

        patterns = spec_data.get("patterns", ["*"])
        if not isinstance(patterns, list) or not all(
            isinstance(p, str) for p in patterns
        ):
            errors.append("Plugin 'patterns' must be a list of glob strings.")

        return PluginManifestValidationResult(
            is_valid=len(errors) == 0,
            errors=errors,
        )

    @staticmethod
    def validate_spec_or_raise(name: str, spec_data: dict[str, Any]) -> None:
        """Validate spec dict and raise ValidationErrorV1 on failure."""
        res = PluginManifestValidator.validate_spec_dict(name, spec_data)
        if not res.is_valid:
            from rush.contracts.results import ValidationErrorV1

            raise ValidationErrorV1(
                f"Plugin '{name}' manifest validation failed: {'; '.join(res.errors)}"
            )
