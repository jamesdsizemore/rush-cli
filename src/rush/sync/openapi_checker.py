"""OpenAPI contract synchronization validator."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ApiDriftFinding:
    endpoint_path: str
    method: str
    issue: str


class OpenApiContractChecker:
    """Verifies that an OpenAPI spec matches active backend router definitions."""

    def __init__(self, spec_path: Path) -> None:
        self.spec_path = spec_path.resolve()

    def check_spec_exists(self) -> bool:
        return self.spec_path.exists()

    def inspect_breaking_changes(self, old_spec_json: str, new_spec_json: str) -> list[ApiDriftFinding]:
        try:
            old_data = json.loads(old_spec_json)
            new_data = json.loads(new_spec_json)
        except Exception as e:
            return [ApiDriftFinding(endpoint_path="*", method="*", issue=f"Invalid JSON: {e}")]

        findings = []
        old_paths = old_data.get("paths", {})
        new_paths = new_data.get("paths", {})

        for path, methods in old_paths.items():
            if path not in new_paths:
                findings.append(ApiDriftFinding(endpoint_path=path, method="ALL", issue="Endpoint deleted."))
            else:
                for method in methods:
                    if method not in new_paths[path]:
                        findings.append(
                            ApiDriftFinding(
                                endpoint_path=path,
                                method=method.upper(),
                                issue=f"HTTP method '{method.upper()}' deleted.",
                            )
                        )

        return findings
