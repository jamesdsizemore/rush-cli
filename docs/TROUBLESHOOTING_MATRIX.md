# Troubleshooting matrix

| Area | Symptom | Evidence | Fix |
|---|---|---|---|
| Install | command missing | `uv run rush --help` works | use `uv run` or install wheel as uv tool |
| Python | import/version mismatch | active `VIRTUAL_ENV`, `PYTHONPATH` | clear contamination and use project interpreter |
| Engine | `skipped`, executable absent | engine `--version` fails in same shell | install approved engine and fix `PATH` |
| Applicability | `skipped`, no eligible engines | missing extension/marker | target correct project root or add normal project metadata |
| Config | `RushConfigError` | malformed TOML/unknown tool | validate field types and exact tool name |
| Parser | `error` on newer engine | raw engine format changed | pin supported version and report fixture gap |
| MCP | client sees no tools | process exits/path wrong | use absolute `uv --directory` command |
| MCP | JSON-RPC corruption | banner on stdout | remove wrapper output; logs stderr only |
| MCP/Windows | child engine hangs/fails | client replaced environment | preserve ordinary OS environment and override only needed vars |
| CI | green despite skipped check | exit code 0, JSON `skipped` | enforce status policy in JSON step |
| Advanced | `skipped`, permission missing | `metadata.execution` shows ungranted permission | pass required permission flag (`--allow-slow`, `--allow-network`, `--allow-build`, `--allow-browser`, `--allow-artifact-write`) |
| Security | secret appears in raw log | external engine raw output | remove artifact, rotate credential, report privately |
