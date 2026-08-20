# Environment variables

| Variable | Current use | Safety note |
|---|---|---|
| `RUSH_LOG_LEVEL` | Default CLI/MCP log level: `debug`, `info`, `warn`, or `error`. | Logs are NDJSON on stderr; MCP stdout stays protocol-only. |
| `ANTHROPIC_API_KEY` | Detected only when `review --llm` is requested. | Current path is a deterministic stub and makes no provider call. Never print the value. |
| `OPENAI_API_KEY` | Fallback key detection for `review --llm`. | Same stub boundary; no provider call. |
| `PATH` | Locates Rush and optional engine executables. | Rush prefers venv-local executables where implemented. |
| `VIRTUAL_ENV` | Standard Python environment marker. | A stale value can contaminate contributor runs; see onboarding. |
| `PYTHONPATH` | Standard Python import override. | Global values can inject incompatible packages; clear it for repository verification. |

External engines may define their own environment variables. Rush does not promise to sanitize every ordinary engine environment; contained security-sensitive adapters may use allowlisted child environments. Review the [Engine directory](engine-directory.md).
