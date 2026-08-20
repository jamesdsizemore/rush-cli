# Scripts and automation

Use `--json` and parse `status`; do not scrape Rich tables.

```python
import json, subprocess
p = subprocess.run(["rush", "lint", ".", "--json"], text=True, capture_output=True)
result = json.loads(p.stdout)
if result["status"] in {"fail", "error", "skipped"}:
    raise SystemExit(f"required lint incomplete: {result['summary']}")
```

Set a subprocess timeout in production automation. Preserve stderr separately for NDJSON diagnostics. Do not pass untrusted engine arguments, publish raw secret-scanner output, or infer a pass from exit code 0 when `skipped` is unacceptable.
