# Privacy & Data Handling Guarantees

## Provider-resume data boundary

Only `current_goal`, `open_work`, and `freshness` are projected to a supported CLI. Historic instructions, transcripts, failed patches, credentials, and provider output are excluded and no provider response is persisted. Router/API transport needs its own reviewed privacy contract before activation.

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
