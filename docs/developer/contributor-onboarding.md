# Contributor onboarding

## Clone and install

```bash
git clone https://github.com/jamesdsizemore/rush-cli.git
cd rush-cli
uv sync --all-extras --frozen
```

Run the full loop from [Developer guide](../DEVELOPER_GUIDE.md). Do not use a global interpreter for evidence.

## Windows

Use Git Bash commands or the equivalent shell, but invoke the project executables explicitly:

```bash
unset VIRTUAL_ENV PYTHONPATH
.venv/Scripts/python.exe -m pytest tests/ -q
.venv/Scripts/ruff.exe check src tests
```

A globally set `PYTHONPATH` can load incompatible packages. If an engine is not found, compare `PATH` inside the shell/client that launches Rush.

## macOS and Linux

```bash
unset VIRTUAL_ENV PYTHONPATH
.venv/bin/python -m pytest tests/ -q
.venv/bin/ruff check src tests
```

## First change

Choose one bounded issue, write or update the narrow failing test, make the minimum change, run focused tests, then full gates. Never install every optional external engine to make fixture tests pass; installed-engine tests are marked and bounded.

## Contributor Guide for Context & Ship Subsystems (Phases 41–43)
When contributing to Rush:
* Place context compression and token economy code in `src/rush/token_economy/`.
* Place memory, session, and invariant code in `src/rush/memory/`.
* Place release validation vectors in `src/rush/tools/ship/`.
* Place grounding verifiers in `src/rush/codegraph/`.
* Register subcommands in `src/rush/cli.py` and FastMCP tools in `src/rush/mcp.py`.

## Contributing to Blast Radius and Telemetry
* Place codegraph packing engines in `src/rush/codegraph/`.
* Place token economy and telemetry modules in `src/rush/token_economy/`.
* Place architectural guards in `src/rush/tools/`.



## Contributing to Test Healing and API Differ
* Place sandbox isolation logic in `src/rush/core/`.
* Place test healing and API diff tools in `src/rush/tools/`.



## Contributing to DB Drift and Simplification
* Place schema comparison algorithms in `src/rush/tools/db_drift.py`.
* Place AST complexity calculations in `src/rush/tools/simplify.py`.



## Contributing to Swarm and Traceability
* Place multi-agent mesh lock components in `src/rush/mcp_mesh/`.
* Place traceability and flight recorder tools in `src/rush/tools/`.



## Contributing to Phase 50a Quality & Security Tools
* Place polyglot error extraction and RFC 7807 problem details in `src/rush/tools/error_catalog.py`.
* Place dependency license matrix and copyleft risk checks in `src/rush/tools/license_matrix.py`.
* Place multi-cloud SDK calls and Terraform IAM policy synthesizers in `src/rush/tools/iam_audit.py`.
* Place cryptographic attestation tools in `src/rush/tools/attest.py`.


### Phase 50b Tools: Attribution & PR Evidence
When contributing to `provenance-ai`, `dead-asset`, or `pr-synthesize`, ensure:
1. All tools remain strictly read-only by default; zero unprompted Git mutations or file deletions.
2. File writes require explicit `--allow-artifact-write` and path containment validation.
3. Tests use temporary Git repositories initialized via `subprocess.run(['git', 'init', ...])`.

### Phase 50c Tools: Profiling, Benchmarking & Provenance
When contributing to Phase 50c tools:
1. Never add `scipy`, `onnxruntime`, or `llama-cpp-python` as required dependencies. Rush uses stdlib `statistics`.
2. Never claim SLSA Build Level 3 for local CLI runs. Mark attestations as `unsigned_draft`.
3. Keep dynamic executions strictly guarded behind `--allow-slow`.
