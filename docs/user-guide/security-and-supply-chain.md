# Security and supply chain

Rush separates three jobs so their evidence is clear.

## Dependency security

```bash
rush security . --json
```

Supported Python and npm projects can use pip-audit and npm audit. Scanner findings are not a complete security assessment; investigate severity, reachability, and upgrade guidance.

## Secret scanning

```bash
rush secrets . --json
```

Rush uses Gitleaks when installed and redacts secret-like values from normalized messages. Never paste raw scanner output containing credentials into an issue. Rotate a real exposed credential before merely removing it from Git.

## CodeQL evidence you already have

```bash
rush codeql path/to/codeql.sarif --json
```

Use this command after you have produced a CodeQL SARIF 2.1.0 report locally.
Pass the report file itself, not a project directory. Rush checks that the
report identifies CodeQL and is contained by the report's target; it then
normalizes the local findings. A clean report is `ok`, warnings are `warn`, and
error-level findings are `fail`. A missing, malformed, foreign-engine, or
out-of-target report is `error` or `skipped`, never a clean result.

Rush does **not** run CodeQL for you. It does not create a database, restore or
build your project, install a CLI or SDK, fetch query packs, or contact a remote
service. Keep the original SARIF report with your security-review evidence.

## Software bill of materials

```bash
rush sbom . --json
```

The current CLI exposes only `PATH` and `--json`. The underlying SBOM implementation defaults to `rush-sbom.json` inside the target, refuses paths outside the target, and refuses overwrite unless called with an explicit API option. Because those output/overwrite options are not exposed by the generated CLI today, treat the command as a catalog-only capability and verify its result before relying on it.

Rush does not upload an SBOM. cdxgen may have its own ecosystem behavior; review it separately. See [Safety](../safety/safety-overview.md).
