# Privacy and data handling

## Recoverable omission privacy

Before an omitted context payload is retained for CCR recovery, Rush applies the same value redaction boundary used for returned context. The recovery handle is local; mined mistake rationale is redacted and labelled historical evidence, never promoted to instruction authority.

## Provider-resume projection

Continuity sends only current goal, open work, and freshness to a supported CLI or fixed local provider route. It excludes historical instructions, transcripts, failed patches, credentials, and provider output; those values are neither returned nor persisted. `9router_cli` uses `RUSH_9ROUTER_API_KEY` only as a child-process `OPENAI_API_KEY` and sends no model argument. Z.AI is never invoked.

## Local behavior

Rush reads the target and invokes installed local engines. It has no telemetry implementation and opens no network server. Human output goes to CLI stdout; MCP stdout is protocol-only; NDJSON logs go to stderr.

Continuity checkpoints stay local under `.rush/`. Before persistence, Rush redacts secret-shaped values and stores only a bounded handoff receipt: current goal/open work, dependency hashes, historic-instruction presence, and a failure receipt. It does not persist provider credentials, raw transcripts, historic-instruction text, or failed patches.

## External engines

An engine is a separate program. Some dependency scanners may need advisory data or package metadata; Rush cannot make a universal offline promise for third-party tools. Contained adapters disable known downloads/remote references where their contract requires it, such as Checkov external modules and Spectral remote references.

## Model behavior

Default review is deterministic. `--use-graft` explicitly requests local Graft context. `--llm` only detects an Anthropic/OpenAI key and returns deterministic stub text; it makes no model call. If real providers are added, their data and consent contract must be documented before release.

## Secrets

Normalized finding messages and logs redact obvious secret assignments, and secret findings should not include captured values. Redaction is defense in depth, not permission to publish raw external scanner output. Rotate any real exposed credential.

## Review evidence retention

Rush does not operate a durable evidence store or upload review data. Direct
review returns local source-location evidence, deterministic fingerprints, and
freshness metadata in the current result only. A supplied report remains a
user-owned local input; Rush neither writes a review baseline by default nor
uses Git history to infer scope. See [scanner governance](../maintainers/scanner-governance.md)
for maintainer retention, error-budget, and deprecation policy.

## End-to-End Recursive Sanitization (Phase 53)

Rush treats all persistent and public output boundaries as sanitization choke-points:
- `sanitize_value` redacts secrets from dictionary values AND keys.
- Dict key collision suffixing ensures no data loss occurs when separate keys share redaction targets.
- Pre-truncation subprocess handling ensures secrets cut off by character limits are redacted before truncation.
- Output formats (CLI, MCP, SARIF, HTML, Cache) and persistent writers (state, mesh, logs, artifacts) enforce deep sanitization.

## Non-Recoverable Capability Verification (Phase 55)

All persistent capabilities, lock identifiers, and trust tokens are stored using `rush.io.VerifierRecord`. This uses PBKDF2-HMAC-SHA256 (100,000 iterations, 32-byte salt) and constant-time verification. Raw capabilities are never stored on disk, eliminating token disclosure in state files.

### Plugin Credential Confinement (Phase 56)
Secrets are strictly excluded from process command lines and environment blocks. Ephemeral descriptors and stdin payloads provide point-to-point credential delivery.

## Cache Storage & Prompt Privacy (Phase 57)

Data written to the invocation cache is sanitized prior to persistence. Prompts sent to LLM providers are guarded against unintended redirect exfiltration.
