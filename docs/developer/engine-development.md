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
        """Check if binary is found on PATH or in current venv."""
        return shutil.which(self.binary) is not None

    def run(self, target: Path, options: dict[str, Any]) -> ToolResult:
        """Constructs bounded argv, executes with run_subprocess(), and parses output."""
        if not self.is_available():
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

        cmd = [self.binary, "--format", "json", str(target)]
        code, stdout, stderr = run_subprocess(cmd, timeout=120.0)

        # Parse JSON and normalize findings
        return self._parse_output(code, stdout, stderr, target)
```

---

## 2. Mandatory Steps for New Engines

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
   - Add to `TOOL_SPECS` engine list in `src/rush/catalog.py`.
   - Register in `PARSER_FIXTURE_SUITES` in `src/rush/catalog.py`.
5. **Documentation**: Update all 13 documentation files as mandated by the [Master Build Plan](master-innovation-remediation-build-plan.md).

See [Tool Development](tool-development.md) and [Coding Standards](coding-standards.md).
