Current status: historical decision; HTML and SARIF serializers exist, but export flags are command-specific; the dedicated review route does not expose both flags. Use [CLI reference](../../CLI_REFERENCE.md) and [MCP reference](../../MCP_REFERENCE.md) for current signatures and artifact-write grants. The broad export outcome below remains an accepted requirement.

# ADR-008: Standalone HTML & SARIF 2.1.0 Artifact Export

## Status
Accepted

## Context
Developers require immediate visual feedback for code reviews without external web servers, and automated pipelines require standardized SARIF 2.1.0 for GitHub Security tab integration.

## Decision
1. Implement a zero-dependency standalone HTML dashboard generator in `src/rush/html_export.py`.
2. Implement a compliant SARIF 2.1.0 serializer in `src/rush/sarif.py`.
3. Provide `--export-html` and `--export-sarif` across all catalog tools.

## Consequences
- Single-command visual artifact creation.
- Native integration with GitHub Actions `upload-sarif`.
