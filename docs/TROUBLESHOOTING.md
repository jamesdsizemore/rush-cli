# Troubleshooting

Start with the user-friendly [symptom guide](user-guide/troubleshooting.md). Use the [troubleshooting matrix](TROUBLESHOOTING_MATRIX.md) for CLI, engine, MCP, Windows, configuration, and CI diagnostics.

Quick checks:

```bash
rush --version
rush --help
rush COMMAND PATH --json
rush --log-level debug COMMAND PATH --json
```

Read stdout as the result and stderr as NDJSON diagnostics. A `skipped` result is not a crash; inspect its summary before changing the environment.
