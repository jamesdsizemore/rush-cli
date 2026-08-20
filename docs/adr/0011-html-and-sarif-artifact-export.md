# ADR 0011: Standalone HTML & SARIF 2.1.0 Artifact Exporters

## Context
Rush tools return structured `ToolResult` dictionaries. While JSON output (`--json`) is optimal for scripts and MCP transports, human developers require visual dashboards with severity filters, and CI systems (like GitHub Code Scanning) require standard SARIF 2.1.0 payloads.

## Decision
1. Implement `src/rush/html_export.py` providing `export_to_html(result, output_path)`:
   - Zero external frontend dependencies.
   - Built-in dark mode, metric summary cards, status badges, and expandable finding tables with remediation code snippets.
2. Implement `src/rush/sarif.py` providing `export_to_sarif(result, output_path)`:
   - Converts `Finding` objects to standard SARIF 2.1.0 JSON format with URI-encoded paths and rule descriptors.
3. Expose `--export-html <path>` and `--export-sarif <path>` flags on Click CLI and MCP tools.

## Consequences
- Developers can immediately generate visual inspection artifacts without installing node or browser dependencies.
- GitHub Actions workflows can upload SARIF outputs directly to GitHub Advanced Security.
