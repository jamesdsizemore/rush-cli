# Privacy & Data Handling Guarantees

## Provider-resume data boundary

Only `current_goal`, `open_work`, and `freshness` are projected to a supported CLI or fixed local provider route. Historic instructions, transcripts, failed patches, credentials, and provider output are excluded and no provider response is persisted. `9router_cli` passes `RUSH_9ROUTER_API_KEY` only as its child Codex process's `OPENAI_API_KEY`, never records it, and sends no model argument.

Rush is strictly local-first. It contains no telemetry, analytics tracking, external data collection, or remote reporting servers.

Session handoff state is also local: secret-shaped values are redacted before session-memory and checkpoint persistence; provider credentials, raw historic instructions, raw transcripts, and failed patches are excluded from the receipt. Redaction is a safety layer, not permission to store credentials.

---

## 1. Core Privacy Invariants

1. **Local-Only Execution**: All 34 Rush tools and 77 engine adapters execute locally on your machine. No source code, filenames, or metrics are transmitted to any remote Rush server.
2. **Zero Telemetry**: Rush does not phone home, track usage statistics, or log user behavior.
3. **Automated Secret Redaction**: Any secret, password, private key, or credential identified in scanner findings or error logs is masked as `[REDACTED]` prior to emission.
4. **Offline Default Posture**: External engines operate offline by default. Remote queries (e.g. live URL checks with Lychee or load tests with k6) require explicit `--allow-network` permission flags.
5. **No Stealth Model Invocations**: The `rush review --llm` option is a development stub that makes zero external API or LLM provider calls. Default review uses deterministic local heuristics.

---

## 2. Model Context Protocol (MCP) Privacy

When Rush runs as a local stdio MCP server for an AI coding assistant:
- The conversation occurs entirely through local standard input/output (`stdio`) pipes on the host machine.
- Rush does not open any network ports, HTTP listeners, or WebSocket servers.
- The AI assistant only receives the structured `ToolResult` JSON payload explicitly requested by the assistant.

See [Privacy and Data Handling Guide](safety/privacy-and-data-handling.md) and [Security Model](safety/security-model.md).

---

## 3. Serialization & Persistent Storage Privacy (Phase 53)

Rush enforces end-to-end recursive sanitization across all data boundaries:
1. **Recursive Sanitizer Kernel**: `sanitize_value` redacts credentials, bearer tokens, API keys, and sensitive URL credentials from both dictionary keys and values.
2. **Immutable Input Isolation**: Data passed to execution operations is never modified in-place; sanitization occurs strictly on detached serialization copies.
3. **Loss-Visible Key Collisions**: Colliding redacted dictionary keys are preserved deterministically via suffixing rather than discarded, preventing silent state corruption while logging collision metadata.
4. **Clean Persistent State**: Audit logs, SQLite patch memory, session flight logs, preferences, and generated artifacts (SARIF, HTML, in-toto statements, IAM policies) are sanitized before writing to disk.
5. **Redacted Diagnostics**: Stderr NDJSON logs redact secrets from both log messages and full exception tracebacks, ensuring diagnostic clarity without credential exposure.

---

## 4. Schema Normalization & Operation Boundary Privacy (Phase 54)

1. **Sanitization-First Serialization**: In Phase 54, `serialize_tool_result()` executes secret sanitization (Phase 53) before structural schema validation, preventing un-sanitized data from ever reaching serialized envelopes.
2. **Canonical Finding Normalization**: Findings are coerced into immutable `FindingV1` records with normalized file paths, line coordinates, and standardized severity levels (`info`, `warning`, `error`), scrubbing unpredictable engine error fields.
3. **Service Protocol Separation**: Service operations (like MCP connection initialization) run through isolated `ServiceOperationAdapter` layers, ensuring raw communication frames remain separate from tool result data.

## 5. Non-Recoverable Capability Privacy (Phase 55)

1. **One-Way Verifier Storage**: Stored capabilities, authorization tokens, and lock proofs are persisted as `VerifierRecord` hashes derived via PBKDF2-HMAC-SHA256 (100k rounds, 32-byte salt).
2. **Zero Raw Capability Exposure**: `VerifierRecord` instances contain zero raw token information, omit raw values from `to_dict()` and `repr()`, and perform verification in constant time via `hmac.compare_digest`.
3. **Entropy Validation**: Capabilities must have Shannon entropy >= 2.5 bits/symbol and length >= 16 characters, preventing predictable or low-entropy secrets.
