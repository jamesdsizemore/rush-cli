# Migration guide

## From direct tools to Rush

Keep existing Ruff/ESLint/pytest/etc. configuration. Install Rush, run one command beside the direct tool, compare normalized results, then adopt only the checks that preserve policy. Treat `skipped` as incomplete when the engine is required.

## From Rush v0.1 to the current catalog

The original five commands remain, while additional commands have mixed maturity. Do not assume every catalog entry is executable. ToolResult uses `engine_version` and `duration_ms` (not `version`/`duration`) and may add metrics, artifacts, metadata, and provenance.

Configuration accepts catalog-validated `[tools.NAME]`, but some fields remain parsed without universal consumers. Update automation to inspect JSON status and consult [Known issues](KNOWN_ISSUES.md).
