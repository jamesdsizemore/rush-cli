# Package Packaging & Distribution

Rush is packaged as a standard Python 3.12 wheel and source distribution using [Hatchling](https://hatch.pypa.io/) and [uv](https://docs.astral.sh/uv/).

---

## 1. Building Distribution Artifacts

From the repository root:
```bash
uv build
```

This generates:
- `dist/rush-0.2.0-py3-none-any.whl` (Standard wheel distribution)
- `dist/rush-0.2.0.tar.gz` (Source distribution)

---

## 2. Local Installation into Isolated Tool Environments

To install Rush into an isolated CLI environment:
```bash
uv tool install dist/rush-0.2.0-py3-none-any.whl
rush --version
```

Or install from the local source directory in editable mode:
```bash
uv tool install --editable .
```

---

## 3. Package Verification Protocol

Before distributing any release artifact, verify:
1. **Clean Wheel Install**: Install wheel in a fresh, clean Python virtualenv and verify `rush --help` and `rush --version`.
2. **MCP Startup Smoke Test**: Execute `rush mcp serve` and ensure no banner is written to stdout.
3. **Deterministic Review**: Execute `rush review src/` and ensure expected exit code 0.
4. **Reproducibility**: Ensure hash verification matches `uv.lock` frozen pins.

See [CI and Packaging Guide](developer/ci-and-packaging.md) and [Release Process](developer/release-process.md).
