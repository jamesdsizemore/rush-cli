"""Tests for Phase 23: Stack Discovery.

Verifies:
- Detection of Python stacks (pyproject.toml, requirements.txt, uv)
- Detection of TypeScript/JavaScript stacks (package.json, tsconfig.json)
- Detection of Rust stacks (Cargo.toml)
- Detection of Go stacks (go.mod)
- Suggested engine mappings for detected ecosystems
"""

from __future__ import annotations

from pathlib import Path

from rush.discovery.stack import detect_project_stacks


def test_detect_python_stack(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "demo"\n', encoding="utf-8"
    )
    stacks = detect_project_stacks(tmp_path)
    langs = [s.language for s in stacks]
    assert "python" in langs

    py_stack = next(s for s in stacks if s.language == "python")
    assert "ruff" in py_stack.suggested_engines


def test_detect_typescript_stack(tmp_path: Path) -> None:
    (tmp_path / "package.json").write_text(
        '{"name": "demo-js", "dependencies": {}}', encoding="utf-8"
    )
    (tmp_path / "tsconfig.json").write_text("{}", encoding="utf-8")
    stacks = detect_project_stacks(tmp_path)
    langs = [s.language for s in stacks]
    assert "typescript" in langs

    ts_stack = next(s for s in stacks if s.language == "typescript")
    assert (
        "biome" in ts_stack.suggested_engines or "eslint" in ts_stack.suggested_engines
    )


def test_detect_rust_stack(tmp_path: Path) -> None:
    (tmp_path / "Cargo.toml").write_text(
        '[package]\nname = "demo-rs"\nversion = "0.1.0"\n', encoding="utf-8"
    )
    stacks = detect_project_stacks(tmp_path)
    langs = [s.language for s in stacks]
    assert "rust" in langs
