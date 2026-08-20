# Understanding results

Rush reports one status for each command and may include individual findings.

| Status | Plain meaning | Typical next action |
|---|---|---|
| `ok` | The check completed without a blocking finding. | Continue. |
| `warn` | The check completed with advisory findings. | Read and triage them. |
| `fail` | The check completed and found failed criteria. | Fix or explicitly accept the risk. |
| `error` | Rush or an engine could not complete reliably. | Correct the invocation/environment and rerun. |
| `skipped` | The check did not run: not applicable, evidence/permission absent, or helper missing. | Read `summary`; decide whether the check is required. |

Examples:

```json
{"tool":"lint","status":"skipped","summary":"ruff executable not found", ...}
```

This does **not** say the source passes lint. It says no lint conclusion was produced.

```json
{"tool":"security","status":"fail","summary":"1 vulnerability finding(s)", ...}
```

The scanner completed and found an issue. Use finding identifiers and messages to investigate.

Rush maps statuses to process exit codes: `ok`, `warn`, and `skipped` → `0`; `fail` → `1`; `error` → `2`. CI that requires a non-skipped check should inspect JSON rather than relying only on exit code 0. See [Result reference](../reference/result-reference.md).
