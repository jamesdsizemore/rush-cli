# Debugging guide

1. Reproduce with `--json` and `--log-level debug`; separate stdout result from stderr NDJSON.
2. Classify failure: applicability, config, executable discovery, argv/environment, timeout, parser, aggregation, transport, or rendering.
3. Run the engine directly in the same environment only to compare behavior; preserve the actual report.
4. Add the smallest fixture/test that reproduces the root cause.
5. Fix at the owning boundary, then run sibling-path regressions.

Windows-specific checks: stale `VIRTUAL_ENV`, global `PYTHONPATH`, executable extension resolution, desktop-client `PATH`, real-file stderr capture, and client environment replacement. MCP hangs often indicate a child process inherited protocol stdin; shared subprocess execution must keep `DEVNULL`.
