"""Environment variable schema and .env.example synchronizer."""

from __future__ import annotations

import re
from pathlib import Path


class EnvSchemaSynchronizer:
    """Verifies that all environment variables used in Pydantic Settings exist in .env.example."""

    @staticmethod
    def extract_env_keys_from_file(example_file: Path) -> set[str]:
        if not example_file.exists():
            return set()
        keys = set()
        for line in example_file.read_text(encoding="utf-8").splitlines():
            line_clean = line.strip()
            if line_clean and not line_clean.startswith("#"):
                key = line_clean.split("=")[0].strip()
                keys.add(key)
        return keys

    @staticmethod
    def extract_settings_keys_from_pydantic(pydantic_source: str) -> set[str]:
        keys = set()
        for line in pydantic_source.splitlines():
            line_clean = line.strip()
            m = re.match(r"^([A-Z0-9_]+)\s*:\s*[a-zA-Z0-9_\[\]]+", line_clean)
            if m:
                keys.add(m.group(1))
        return keys

    @staticmethod
    def verify_env_parity(
        example_keys: set[str], settings_keys: set[str]
    ) -> tuple[bool, set[str]]:
        missing_in_example = settings_keys - example_keys
        return len(missing_in_example) == 0, missing_in_example

    @classmethod
    def find_missing_keys(cls, example_file: Path, actual_file: Path) -> set[str]:
        """Find environment keys defined in example file that are missing in actual file."""
        example_keys = cls.extract_env_keys_from_file(example_file)
        actual_keys = cls.extract_env_keys_from_file(actual_file)
        return example_keys - actual_keys


EnvironmentVariableSynchronizer = EnvSchemaSynchronizer
