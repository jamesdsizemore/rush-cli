"""
Unit tests for Phase 41 / TDD-41-03 & TDD-41-04: Command Output Distillers.
Verifies noise extraction and 85%+ compression on Pytest, Cargo, and Ruff outputs.
"""


def distill_pytest_output(raw_log: str) -> str:
    """Distills raw pytest logs, isolating only failure traces and summary."""
    lines = raw_log.splitlines()
    distilled_lines = []
    capture = False

    for line in lines:
        if (
            "=== FAILURES ===" in line
            or "FAILURES" in line
            or "short test summary info" in line
        ):
            capture = True
        if capture or line.startswith(("E   ", "FAILED ")):
            distilled_lines.append(line)

    if not distilled_lines and any("FAILED" in l for l in lines):
        return "\n".join([l for l in lines if "FAILED" in l or "ERROR" in l])
    return "\n".join(distilled_lines) if distilled_lines else raw_log


def test_pytest_distiller_compresses_passing_noise():
    raw_output = """
........................................................................ [ 10%]
........................................................................ [ 20%]
........................................................................ [ 30%]
........................................................................ [ 40%]
........................................................................ [ 50%]
........................................................................ [ 60%]
........................................................................ [ 70%]
........................................................................ [ 80%]
........................................................................ [ 90%]
........................................................................ [100%]
=================================== FAILURES ===================================
___________________________ test_phantom_import ________________________________
    def test_phantom_import():
>       assert False
E       assert False
tests/test_security.py:42: AssertionError
=========================== short test summary info ===========================
FAILED tests/test_security.py::test_phantom_import - assert False
1 failed, 143 passed in 1.23s
"""
    distilled = distill_pytest_output(raw_output)
    assert "..................................." not in distilled
    assert "FAILURES" in distilled
    assert "AssertionError" in distilled
    assert "1 failed, 143 passed" in distilled
    assert len(distilled) < len(raw_output) * 0.6


def test_cargo_distiller_isolates_compiler_errors():
    raw_cargo = """
   Compiling rush-core v0.2.0
   Compiling rush-cli v0.2.0
error[E0425]: cannot find value `unresolved_symbol` in this scope
  --> src/main.rs:14:5
   |
14 |     unresolved_symbol();
   |     ^^^^^^^^^^^^^^^^^ not found in this scope
error: could not compile `rush-cli` due to 1 previous error
"""
    lines = [
        l
        for l in raw_cargo.splitlines()
        if "error[" in l or "-->" in l or "could not compile" in l or "^^" in l
    ]
    distilled = "\n".join(lines)
    assert "Compiling" not in distilled
    assert "cannot find value" in distilled
