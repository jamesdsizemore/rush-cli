# Support runbook

## Triage order

1. Request Rush version, platform, invocation, target shape, JSON result, and redacted stderr logs.
2. Reproduce from a clean environment with the same engine version.
3. Classify: documentation, configuration, applicability, missing engine, engine compatibility, Rush defect, or security issue.
4. For missing engines, verify the binary in the same shell/client and consult EngineSpec—not a maintainer's global environment.
5. For Windows contamination, clear `VIRTUAL_ENV`/`PYTHONPATH`, use the project interpreter, and inspect client environment replacement.
6. For parser changes, obtain a sanitized native report, add a fixture, and return `error` until supported rather than accepting unknown output.

Never request credentials, private source, or unredacted secret-scanner output in a public issue. Link users to the exact troubleshooting page and record documentation gaps as defects.
