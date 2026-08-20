# Engine Adapter Development & Integration Guide

This guide describes the complete protocol for developing, testing, registering, and documenting external quality engine adapters in `src/rush/engines/`.

---

## 1. Engine Adapter Lifecycle & Contract

Every engine adapter extends the `Engine` base class in `src/rush/engines/base.py` and adheres to this contract:

```python
class MyEngine(Engine):
    name: str = "my-engine"
    binary: str = "my-engine-cli"

    def is_available(self) -> bool:
        """Check if binary is found on PATH or in current venv using resolution cache."""
        return resolve_binary(self.binary) is not None

    def run(self, target: Path, options: dict[str, Any]) -> ToolResult:
        """Constructs bounded argv, executes with run_subprocess(), and parses output."""
        bin_path = resolve_binary(self.binary)
        if not bin_path:
            return ToolResult(
                tool=options.get("tool", "mytool"),
                engine=self.name,
                engine_version=None,
                status="skipped",
                duration_ms=0,
                summary=f"Engine '{self.name}' not found on PATH. Install via: npm install -g {self.binary}",
                findings=[],
                raw=None,
            )

        cmd = [bin_path, "--format", "json", str(target)]
        code, stdout, stderr = run_subprocess(cmd, cwd=target, timeout=120.0)

        # Parse JSON and normalize findings
        return self.normalize(stdout, stderr, code, str(target))
```

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
5. **Documentation**: Run `python scripts/sync_docs.py --update` to verify and auto-sync all documentation files across the repository.

See [Tool Development](tool-development.md) and [Coding Standards](coding-standards.md).
