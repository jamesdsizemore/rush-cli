"""Plugin manifest specification and parameter schema validator."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PluginManifestValidationResult:
    is_valid: bool
    errors: list[str]


class PluginManifestValidator:
    """Validates the structure and parameter types of plugin specifications."""

    @staticmethod
    def validate_spec_dict(name: str, spec_data: dict) -> PluginManifestValidationResult:
        errors = []
        if not name or not name.isidentifier():
            errors.append(f"Plugin name '{name}' must be a valid alphanumeric identifier.")

        cmd = spec_data.get("command")
        if not cmd:
            errors.append("Plugin specification must define a non-empty 'command' string or list.")

        timeout = spec_data.get("timeout_seconds", 30.0)
        try:
            t_val = float(timeout)
            if t_val <= 0 or t_val > 300.0:
                errors.append("Plugin timeout_seconds must be between 1.0 and 300.0 seconds.")
        except (ValueError, TypeError):
            errors.append("Plugin timeout_seconds must be a valid number.")

        patterns = spec_data.get("patterns", ["*"])
        if not isinstance(patterns, list) or not all(isinstance(p, str) for p in patterns):
            errors.append("Plugin 'patterns' must be a list of glob strings.")

        return PluginManifestValidationResult(
            is_valid=len(errors) == 0,
            errors=errors,
        )
