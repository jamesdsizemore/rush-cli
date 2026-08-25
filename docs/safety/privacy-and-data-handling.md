# Privacy and data handling

## Recoverable omission privacy

Before an omitted context payload is retained for CCR recovery, Rush applies the same value redaction boundary used for returned context. The recovery handle is local; mined mistake rationale is redacted and labelled historical evidence, never promoted to instruction authority.

## Provider-resume projection

Continuity sends only current goal, open work, and freshness to a supported CLI or OmniRoute's fixed local API. It excludes historical instructions, transcripts, failed patches, credentials, and provider output; those values are neither returned nor persisted. Z.AI is never invoked, and 9Router transport remains inactive pending its own key/model contract.

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
