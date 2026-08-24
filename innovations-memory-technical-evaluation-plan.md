# Rush continuity technical-evaluation plan

Status: proposed technical work only. This plan does not authorize product implementation, dependency adoption, configuration changes, or a long-running external-product watch process.

## 1. Purpose and boundary

Decide the fixed technical inputs for a provider-neutral Rush continuity system before development begins. The output is a signed decision record added to section 8 of this document; the development plan may consume only those decisions.

In scope:

- Canonical event/claim/receipt/obligation/projection/bundle semantics.
- Cross-provider and cross-model continuation quality.
- Token reduction, exact/FTS retrieval, optional semantic retrieval, and model-assisted operations.
- Privacy, authority, injection, concurrency, portability, and protocol behavior.
- Four bounded external-product pattern spikes plus one protocol conformance gate.

Out of scope:

- Product CLI/MCP commands, migration of existing user data, new default dependencies, background services, hooks, hosted transport, F9 coordination, or implementation of an external memory product.

## 2. Non-negotiable rules

- Rush remains local-first, Python 3.12, CLI plus stdio-only MCP, with one shared tool implementation returning `ToolResult`.
- Canonical state is local SQLite plus files under Rush control. Retrieval indexes and LLM outputs are derived material, never authority.
- Default capture is typed task/tool/repository events. Raw transcripts are optional private blobs with spans; they are not automatic memory.
- A historical provider's system/developer text is quarantined evidence, never current instruction.
- Every experiment runs in a disposable evaluation workspace. No hooks, Git history rewrite, release, upload, or persistent external service.
- A failure to meet a gate is a decision to omit that capability from v1, not a reason to extend the experiment indefinitely.

## 3. Evaluation corpus and instrumentation

Create a versioned local corpus of at least 40 fixtures. Every fixture has: source events/blobs, expected authority frontier, expected unresolved obligations, admissible evidence IDs, expected prohibited content, and a task-specific success oracle.

| Fixture family | Minimum | What it exposes |
|---|---:|---|
| Provider/model handoff | 8 | A different model resumes the same task without inheriting historical system instructions. |
| Repository drift | 6 | A changed file, Git ref, config, tool version, or instruction invalidates the right claim. |
| Failure/recovery | 6 | A failed tool or incomplete request cannot be silently marked complete. |
| Privacy and malicious input | 8 | Secrets, prompt injection, redacted spans, malicious bundles, and over-broad imports. |
| Token pressure | 8 | 2k, 8k, and 16k target budgets with large history and mandatory items. |
| Worktree/concurrency | 4 | Divergence, lock contention, idempotent writes, and workspace identity. |

Record exact input tokens (provider tokenizer and implementation estimate), output tokens, wall time, retrieval time, model/provider version, cost where available, selected/omitted object IDs, and oracle results. Store fixtures and results locally; redact before persistence.

## 4. Technical work packages

### T0 — Harness, corpus, and baselines

Build only a disposable harness and fixtures. Establish three baselines for every corpus item: raw relevant history, naive summary, and current Rush session/context behavior.

Pass: corpus has 40+ fixtures, deterministic fixture IDs, a documented oracle for each, and reproducible baseline reports.

Fail: no development starts; correct the harness/corpus rather than guessing a product design.

### T1 — Data-model and authority prototype

Prototype a minimal SQLite schema and pure reducer outside production paths. Test: immutable event, source span/gap, redaction state, receipt, claim with dependency fingerprint, obligation, projection, and bundle manifest.

Required cases: conflicting user/repository/provider messages; stale tool evidence; idempotent event replay; deletion/tombstone; imported instruction quarantine; no LLM-generated field elevates itself to canonical truth.

Pass: deterministic replay produces the expected frontier for every relevant fixture and zero authority violations.

Decision output: exact v1 schema, authority precedence, claim statuses, invalidation triggers, and retention/tombstone behavior.

### T2 — LLM/model continuation evaluation

The model is a consumer of a projection, not a source of canonical facts. Test at least three target classes selected at execution time: a high-capability hosted coding model, a lower-cost hosted coding model, and a local/open-weight coding model if the hardware supports it. Record exact model/version/provider; never treat a brand name as a permanent category.

For each model class and handoff fixture, compare raw history, naive summary, and deterministic projection. Score:

- correct next action and unresolved-obligation identification;
- authority compliance (current user/repository wins; historical provider instruction loses);
- evidence citation/recovery-handle use;
- correct abstention when the projection omits required proof;
- stale-claim detection after dependency changes;
- secret/non-consented-content leakage;
- actual input tokens, latency, and cost.

Separately test optional model-assisted transforms: structured extraction, semantic retrieval reranking, and projection rendering. A transform is admissible only if it is reproducible enough for the fixture, carries source IDs/confidence, never writes canonical facts directly, and has a deterministic fallback.

Pass: deterministic projections are non-inferior to raw history on completion, have zero authority and secret violations, and meet the T4 token gate. No optional model transform enters v1 unless it improves a named metric without breaking those conditions.

Decision output: supported target-model envelope, required renderer format, allowed/disallowed model-assisted transforms, and fallback behavior.

### T3 — Retrieval and index decision

Compare four retrieval configurations on the same corpus: exact IDs/field filters, SQLite FTS5, optional local semantic index, and Uteke read-only sidecar. Hindsight is a benchmark-only comparison if an isolated environment is available; it is never installed in Rush.

Measure recall of required evidence, false recall, retrieval latency, local disk/RAM/download cost, offline behavior, deletion propagation, and result explainability. Test source recovery after an omitted projection item.

Pass: choose the simplest configuration that meets required-evidence recall and latency targets. Default must be exact plus FTS5. Semantic/Uteke is rejected unless it produces a measured benefit, stays local, is optional, and is removable without data loss.

Decision output: v1 retrieval stack, optional adapter policy, index rebuild/delete behavior, and recovery-handle syntax.

### T4 — Token-projection decision

Use the fixed T1 schema to compile projections at 2k, 8k, and 16k budgets. Mandatory order is authority, current frontier, unresolved obligations, fresh receipts, then useful supporting evidence. Every omission must be recorded with a recovery handle and reason.

Pass at every target budget:

- zero omitted mandatory objects, otherwise emit an explicit insufficient-budget result;
- actual token count within the predeclared estimator tolerance;
- lower median input tokens than raw history;
- non-inferior completion and evidence recovery versus raw history;
- zero authority violations, stale-completion errors, and secret leaks.

Decision output: budget policy, mandatory ordering, estimator tolerance, omission-manifest schema, acknowledgement-delta policy, and the token metrics required in production telemetry.

### T5 — Bundle, protocol, and portability decision

Create disposable JSONL bundles and derived Markdown exports. Test same-provider, cross-provider, and cross-worktree import; tampering, unknown required schema version, conflicting repository identity, redactions, tombstones, and historical instruction quarantine.

Run MCP resource/tool compatibility against Rush's locked SDK boundary. Test ACP/A2A only as offline envelope mappings using official fixtures; do not start an HTTP listener or trust remote artifacts.

Pass: JSONL round trip preserves allowed state and rejects corrupt/unsafe input. Markdown remains derived/non-authoritative. An MCP/ACP/A2A mapping is accepted only when version/capability fallback is deterministic and it adds a real user requirement.

Decision output: bundle v1 schema, supported import/export formats, capability matrix, and whether any protocol envelope is in v1.

### T6 — Security, privacy, storage, and operational decision

Exercise SecretRedactor-compatible secret corpus, export authorization matrix, retention/delete/tombstone behavior, SQLite WAL/locking/crash recovery, workspace boundary checks, malformed databases, and malicious external bundle content. Run license/security review of every proposed optional adapter before it can be selected.

Pass: zero raw secret persistence/export, fail-closed import/version/permission behavior, deterministic recovery after interruption, and no requirement for a daemon, hook, network listener, model download, or provider credential in the default path.

Decision output: threat model, retention defaults, encryption-at-rest decision, permission matrix, SQLite operating mode, and optional-component allowlist.

### T7 — Four bounded product spikes

| Spike | Exact question | Pass result | Otherwise |
|---|---|---|---|
| AgentMem pattern | Do proof-before-reminder and its long-run harness catch more unsupported handoff assertions? | Borrow only the proved fixture/harness pattern. | Drop it. |
| Graphiti pattern | Does temporal vocabulary add a required query that T1 SQLite cannot express clearly? | Borrow the vocabulary/data rule only. | Keep simpler SQLite model. |
| Uteke sidecar | Does read-only local hybrid retrieval lower recovery cost beyond exact/FTS without losing required evidence? | Permit an optional adapter. | No adapter. |
| Basic Memory exchange | Can derived Markdown round trip without authority, redaction, or tombstone loss? | Permit derived Markdown export/import. | JSONL only. |

No other repository has an active work item. There is no monitor/watch task.

## 5. Decision record format

At the end of T0–T7, append one immutable decision table to this file:

| Decision ID | Fixed choice | Evidence artifact IDs | Alternatives rejected | Constraints carried into development |
|---|---|---|---|---|
| D1 | v1 schema + authority order | T0/T1 results | — | — |
| D2 | model/rendering policy | T2 results | — | — |
| D3 | retrieval stack | T3 results | — | — |
| D4 | token projection contract | T4 results | — | — |
| D5 | bundle/protocol scope | T5 results | — | — |
| D6 | privacy/storage/optional-component policy | T6 results | — | — |
| D7 | product-spike outcomes | T7 results | — | — |

## 6. Completion criteria

This plan is complete only when T0–T7 have pass/fail records, all D1–D7 are filled, and a reviewer can reproduce the result artifacts locally. It does not become complete because a preferred product looks promising.

## 7. Handoff to development

The development plan may start only after D1–D6 are fixed. D7 changes development scope only where a spike passed; otherwise it has no downstream work. Any later question that changes D1–D6 opens a new technical-evaluation revision rather than introducing exploratory work into development.
