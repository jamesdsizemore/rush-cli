# Privacy and data handling

## Local behavior

Rush reads the target and invokes installed local engines. It has no telemetry implementation and opens no network server. Human output goes to CLI stdout; MCP stdout is protocol-only; NDJSON logs go to stderr.

## External engines

An engine is a separate program. Some dependency scanners may need advisory data or package metadata; Rush cannot make a universal offline promise for third-party tools. Contained adapters disable known downloads/remote references where their contract requires it, such as Checkov external modules and Spectral remote references.

## Model behavior

Default review is deterministic. `--use-graft` explicitly requests local Graft context. `--llm` only detects an Anthropic/OpenAI key and returns deterministic stub text; it makes no model call. If real providers are added, their data and consent contract must be documented before release.

## Secrets

Normalized finding messages and logs redact obvious secret assignments, and secret findings should not include captured values. Redaction is defense in depth, not permission to publish raw external scanner output. Rotate any real exposed credential.
