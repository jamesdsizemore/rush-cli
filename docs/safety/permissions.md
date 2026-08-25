# Permissions

## Provider continuation permission

`provider_resume` requires explicit network permission (`--allow-network`) before Rush invokes a supported user-owned CLI or the fixed-loopback OmniRoute API. The permission does not grant credential reads, OAuth/browser access, automatic fallback, automatic retry, or a 9Router API route.

Rush distinguishes ordinary local inspection from work that can be expensive, mutating, browser-driven, or networked.

| Boundary | CLI flag | Intended effect | Default |
|---|---|---|---|
| network access | `--allow-network` | Permit live network calls (e.g. k6, Lychee URL checks, Semgrep registry) | skip/refuse |
| vulnerability downloads | `--allow-download` | Permit downloading vulnerability feeds or schemas | skip/refuse |
| rules cache write | `--allow-cache-write` | Permit writing local tool caches | skip/refuse |
| compilation / DB build | `--allow-build` | Permit compiling project code or CodeQL databases | skip/refuse |
| long-running work | `--allow-slow` | Permit long-running test suites, mutation, fuzz, contract, or drift runs | skip/refuse |
| baseline / artifact write | `--allow-artifact-write` | Permit mutating or generating report/baseline artifacts | skip/refuse |
| browser runtime | `--allow-browser` | Permit launching browser engines (Playwright, Chromium/WebKit/Firefox) | skip/refuse |

## Execution Metadata

Every tool returns canonical execution metadata:

```json
{
  "metadata": {
    "execution": {
      "mode": "executed",
      "requested_permissions": {
        "network": false,
        "download": false,
        "cache_write": false,
        "build": false,
        "slow": true,
        "artifact_write": false,
        "browser": false
      },
      "granted_permissions": {
        "network": false,
        "download": false,
        "cache_write": false,
        "build": false,
        "slow": true,
        "artifact_write": false,
        "browser": false
      },
      "producer": "mutmut",
      "report_path": null
    }
  }
}
```

Consent is specific to each invocation and target. Rush never encodes blanket browser/network/publication permission in an assistant prompt or shared config.
