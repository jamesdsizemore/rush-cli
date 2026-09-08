# Engine Adapter Development & Integration Guide

This guide describes the complete protocol for developing, testing, registering, and documenting external quality engine adapters in `src/rush/engines/`.

---

## 1. Engine Adapter Lifecycle & Contract

Every engine adapter extends the `Engine` base class in `src/rush/engines/base.py` and adheres to this contract:

```python
class MyEngine(Engine):
    name: str = "my-engine"
    binary: str = "my-engine-cli"
    file_extensions = ("py",)

    def run(
        self, path: Path, args: list[str], cwd: Path | None = None
    ) -> EngineResult:
        """Construct bounded argv and retain raw process evidence."""
        binary = resolve_binary(self.binary) or self.binary
        process = run_subprocess(
            [binary, "--format", "json", *args, str(path)],
            cwd=cwd or path,
            timeout=120,
        )
        return EngineResult(
            exit_code=process.returncode,
            stdout=process.stdout,
            stderr=process.stderr,
            duration_ms=0,
        )

    def normalize(
        self, raw: EngineResult, path: Path, tool_name: str
    ) -> ToolResult:
        """Parse raw evidence and return canonical findings/status."""
        ...
```

> **Note on Binary Execution**: `run_subprocess` catches `FileNotFoundError` if a resolved binary disappears or fails to spawn on Windows/POSIX, safely returning exit code `127` and stderr diagnostic so the engine fails closed with structured results rather than crashing the runtime.

---

## 2. Specialized Engine Patterns

### AST Query & Tree-Sitter Adapters (`aislop`, `globstar`, `ast-grep`)
- Process AST pattern matching against polyglot syntax trees.
- Normalize code snippet context, rule IDs, and automated suggested fixes into `Finding.fix`.

### Modular Monolith & Architecture Sensors (`tach`, `sentrux`, `depcruise`)
- Inspect internal module import trees against boundary policies.
- Surface cyclomatic spikes and cross-boundary illegal coupling as actionable findings with file:line accuracy.

### Structural Diff-Coverage Adapters (`undercover`, `diff-cover`)
- Intersect git branch diffs with LCOV/Cobertura coverage reports.
- Flag newly introduced methods or changed blocks lacking unit test assertions.

### Agent Hook & Security Scanners (`medusa`, `trufflehog`, `bearer`)
- Target agent instruction configurations (`.claude/`, `.cursor/`, `.windsurf/`).
- Auto-redact detected credentials as `[REDACTED]` prior to generating `ToolResult`.

### Offline Cryptographic Trust Attestation (`cejel`)
- Verify cryptographic pass certificates for release readiness without network calls.

---

## 3. Mandatory Steps for New Engines

1. **Adapter File**: Create `src/rush/engines/<engine_name>.py`.
2. **Parser Fixtures**: Add deterministic sample outputs to `tests/fixtures/engine_reports/<engine_name>/`:
   - `clean.json` (0 findings)
   - `findings.json` (>=1 findings)
   - `malformed.json` (corrupted syntax)
3. **Reference Test Suite**: Create `tests/test_<engine_name>_reference.py` using `unittest.mock.patch` to mock `run_subprocess` and verify:
   - Clean report -> `status: "ok"`
   - Findings report -> `status: "fail"` / `"warn"`
   - Malformed report -> `status: "error"`
   - Missing binary -> `status: "skipped"`
4. **Registration**:
   - Register in `ENGINES` dictionary in `src/rush/engines/__init__.py`.
   - Add to `ENGINE_SPECS` and `TOOL_SPECS` engine list in `src/rush/catalog.py`.
   - Register in `PARSER_FIXTURE_SUITES` in `src/rush/catalog.py`.
5. **Documentation**: Update affected references and run `python scripts/sync_docs.py --check`. The checker is read-only and reports exact stale paths/contracts.

See [Tool Development](tool-development.md) and [Coding Standards](coding-standards.md).

### Phase 50b Engines
- `git-trailer-parser`: Uses `git log` with format `%H%x00%an%x00%ae%x00%at%x00%B%x01` to parse commit metadata and trailers.
- `dead-asset-scanner`: In-memory polyglot regex and AST reference scanner with SHA-256 validation.
- `git-diff-synthesizer`: Runs `git diff --stat` and `--numstat`, parses CODEOWNERS, and synthesizes markdown card.

### Phase 50c Engines
- `attest`: Built-in in-toto Statement v1 generator with SHA-256 artifact hashing.
- `mem-profile`: Built-in AST `_ResourceLifecycleVisitor` and stdlib `tracemalloc` dynamic probe.
- `cold-start`: Built-in AST `_ImportVisitor` and Python `-X importtime` parser.
- `offline-review`: Optional `onnxruntime` inference adapter; returns `skipped` when absent.
- `benchmark`: Built-in stdlib `statistics` mean/median regression calculator.
