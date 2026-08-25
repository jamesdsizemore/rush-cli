# Dependency & Engine Discovery Policy

Rush enforces a strict, reproducible dependency policy to maintain rock-solid stability, zero runtime bloat, and offline-first guarantees across all operating systems.

---

## 1. Direct Python Dependencies

1. **Exact Version Pinning**: All direct runtime, development, and linting dependencies in `pyproject.toml` are pinned with exact versions (`==`).
2. **Deterministic Lockfile**: `uv.lock` is committed to the repository and enforced in CI via `uv sync --all-extras --frozen`.
3. **Automated Auditing**: Every CI run audits direct dependencies using `pip-audit` to ensure zero known vulnerabilities.

| Package | Purpose | Verification Contract |
|---|---|---|
| `click==8.1.8` | CLI command routing & option parsing | Tested via `tests/test_cli_registry.py` |
| `mcp==1.2.1` | FastMCP stdio server transport | Tested via `tests/test_mcp.py` |
| `rich==13.9.4` | Terminal output rendering & formatting | Tested via `tests/test_theme.py` |
| `hatchling==1.32.0` | Isolated build backend | Verified via `uv build` |

---

## 2. External Engine Discovery Policy

1. **Zero Engine Bundling**: Rush does **not** bundle Node.js, Go, Rust, Java, or C++ binaries. Quality engines (such as Ruff, ESLint, Semgrep, Trivy, Hadolint) are discovered dynamically from the host environment (`PATH` or active virtualenv).
2. **Non-Fatal Absence (`skipped`)**: When an optional engine is not installed, Rush returns a structured `skipped` result explaining what binary is missing and provides an install hint. Rush **never** attempts to silently download or install binaries.
3. **Reproducibility**: Polyglot teams only need to install the specific checkers relevant to their tech stack.

---

## 3. Subprocess Safety Boundary

 When invoking discovered engine binaries:
 - `stdin=subprocess.DEVNULL` ensures external engines cannot consume or block MCP stdio JSON-RPC streams.
 - `shell=False` prevents shell injection vulnerabilities.
 - `timeout=120.0` prevents hung processes.
 - Output redaction strips credentials, tokens, and keys from findings before JSON emission.

---

## 4. Benchmark & Local Model Policy

1. **Zero Unapproved Binaries**: Tools evaluated in the benchmark suite (e.g. Gitleaks, llama.cpp, ONNX Runtime) must have explicit license, version, and memory/timeout bounds declared in JSON descriptors (`CandidateBinary`).
2. **Rejection of Ollama**: Rush explicitly rejects the `ollama` executable daemon and HTTP endpoints. Local model inference is strictly benchmarked using bounded argument arrays with `llama.cpp` or `onnxruntime`.
3. **External Model Cache**: Model weights must reside in external user-specified caches via `--model-cache`. Storing model caches inside the repository tree is denied.
