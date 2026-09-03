# Package Packaging & Distribution

Rush is packaged as a standard Python 3.12 wheel and source distribution using [Hatchling](https://hatch.pypa.io/) and [uv](https://docs.astral.sh/uv/).

---

## 1. Building Distribution Artifacts

From the repository root:
```bash
uv build
```

This generates:
- `dist/rush_cli-0.3.0-py3-none-any.whl` (Standard wheel distribution)
- `dist/rush_cli-0.3.0.tar.gz` (Source distribution)

---

## 2. Local Installation into Isolated Tool Environments

To install Rush into an isolated CLI environment:
```bash
uv tool install dist/rush_cli-0.3.0-py3-none-any.whl
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

---

## 4. Isolated Installed Artifact Probes (Phase 51 & 52: Finding R-001 Closed)

To ensure packaging correctness outside the source tree checkout, Rush employs `scripts/probe_installed_artifacts.py`:
1. Installs built wheel and sdist into separate, temporary virtual environments outside the repository checkout.
2. Scrubs `PYTHONPATH` and `VIRTUAL_ENV` completely to prevent source-tree shadowing.
3. Probes execution from an empty external working directory.
4. Verifies module origin (`verify_package_origin`) to ensure imports resolve to site-packages rather than the source checkout.
5. Evaluates the R-001 negative import control to guarantee zero `src.rush` imports across the codebase.

In Phase 52, all 74 occurrences of `src.rush` imports across 15 production files and 14 test files were eradicated. Both wheel and sdist now pass 100% of origin and CLI probes from external working directories with scrubbed environments.

Execute locally:
```bash
uv build
python scripts/probe_installed_artifacts.py --json
```

