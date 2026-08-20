# Troubleshooting

| Symptom | Likely reason | Exact fix |
|---|---|---|
| `rush: command not found` | Rush is not installed on `PATH`. | From the checkout run `uv run rush --help`, or install a wheel with `uv tool install`. |
| A command is `skipped` | No applicable files/evidence, optional engine absent, or permission absent. | Read `summary`; confirm project markers, install the named engine if required, or accept that the capability is not executable yet. |
| ESLint or Prettier skips | JS tool/config is absent in this environment. | Install it in the project and verify the engine directly in the same shell. |
| Wrong Python/packages on Windows | Global `PYTHONPATH` or an active environment contaminates execution. | Use `uv run`; contributors should clear `VIRTUAL_ENV` and `PYTHONPATH` before project-venv tests. |
| MCP client disconnects immediately | Wrong command/path or stdout was polluted. | Use an absolute checkout path; do not wrap the server with a banner/echo; capture stderr logs only. |
| MCP tool schema lacks a permission flag | Generic catalog command surface does not expose it yet. | Do not invent a flag. Treat the command as guarded and `skipped`. |
| `fail` in CI | A check found a policy failure. | Read normalized findings and run the underlying engine locally if deeper output is needed. |
| `error` in CI | Engine invocation/report parsing/environment failed. | Use `--json` and `--log-level debug`; fix the environment and rerun. |

For engine-specific recovery, see the [Engine directory](../reference/engine-directory.md) and [Troubleshooting matrix](../TROUBLESHOOTING_MATRIX.md).
