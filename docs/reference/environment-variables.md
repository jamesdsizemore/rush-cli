# Environment Variables Specification

Exhaustive reference of environment variables recognized, inspected, or sanitized by Rush CLI.

---

## 1. Recognized Environment Variables

| Variable | Type / Format | Default | Purpose & Behavioral Contract |
|---|---|---|---|
| `RUSH_LOG_LEVEL` | `debug`, `info`, `warn`, `error` | `warn` | Controls log filtering on `stderr`. `stdout` remains pure JSON-RPC for FastMCP. |
| `ANTHROPIC_API_KEY` | String | None | Detected when `rush review --llm` is requested. Note: `--llm` is a development stub making zero network requests. Values are never printed or logged. |
| `OPENAI_API_KEY` | String | None | Detected as fallback for `rush review --llm`. Development stub making zero network requests. |
| `PATH` | System Search Path | System | Used for dynamic discovery of all 77 engine binaries (`ruff`, `eslint`, `semgrep`, `trivy`, etc.). |
| `VIRTUAL_ENV` | Filesystem Path | None | Standard Python environment marker. |
| `PYTHONPATH` | Filesystem Paths | None | Standard Python import search path. |

---

## 2. Child Process Environment Sanitization

When external engines are invoked:
- Engine executions receive a clean child environment inheriting necessary runtime paths (`PATH`, `HOME`, `TEMP`, `USERPROFILE`).
- Discovered credentials, access tokens, and secret parameters are automatically redacted from all output findings and diagnostic logs as `[REDACTED]`.

See [Engine Directory](engine-directory.md) and [Result Reference](result-reference.md).
