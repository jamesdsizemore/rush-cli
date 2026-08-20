# Environment Variables Reference

Rush inspects a bounded set of environment variables to configure logging, runtime discovery, and optional helper behaviors.

---

## 1. Supported Environment Variables

| Variable | Type / Values | Default | Purpose & Safety Contract |
|---|---|---|---|
| `RUSH_LOG_LEVEL` | `debug`, `info`, `warn`, `error` | `warn` | Sets default logging level for CLI and MCP stderr diagnostics. MCP stdout is strictly reserved for JSON-RPC. |
| `PATH` | System search path | System | Used by Rush to discover external engine binaries (`ruff`, `eslint`, `pytest`, `semgrep`, etc.). Rush prioritizes venv-local binaries when running inside a virtual environment. |
| `VIRTUAL_ENV` | Filesystem path | None | Standard Python environment marker. Cleared in contributor test suites to prevent foreign dependency leakage. |
| `PYTHONPATH` | Python import paths | None | Cleared in contributor onboarding loops to ensure only local repository packages are loaded. |
| `ANTHROPIC_API_KEY` | API Key string | None | Detected if `rush review --llm` is invoked. Note: `--llm` is currently a development stub and makes no live network requests. Value is never logged or printed. |
| `OPENAI_API_KEY` | API Key string | None | Fallback key detection for `review --llm`. Same stub boundary; no live requests made. Value is never logged or printed. |

---

## 2. Child Subprocess Environment Sanitization

When Rush launches external engine subprocesses via `run_subprocess()`:
- `PATH` and essential OS variables are preserved to allow child binaries to find their runtime dependencies.
- Sensitive environment credentials are never injected or serialized to log files.
- Child processes are executed with `stdin=DEVNULL`, preventing any inheritance of terminal input.

See [Result Reference](reference/result-reference.md) and [Security Model](safety/security-model.md).
