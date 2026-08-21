"""v0.2 static-analysis tool contracts."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from rush.engines import ENGINES
from rush.engines.jscpd import JscpdEngine
from rush.engines.knip import KnipEngine
from rush.engines.mypy import MypyEngine
from rush.engines.radon import RadonEngine
from rush.engines.sloppylint import SloppylintEngine
from rush.engines.tsc import TscEngine
from rush.engines.vulture import VultureEngine
from rush.tools.common import resolve_binary
from rush.tools.complexity import ComplexityTool
from rush.tools.dead import DeadTool
from rush.tools.slop import SlopTool
from rush.tools.typecheck import TypecheckTool


@pytest.mark.parametrize(
    ("binary", "marker"),
    [
        pytest.param("mypy", "needs_mypy", marks=pytest.mark.needs_mypy),
        pytest.param("tsc", "needs_tsc", marks=pytest.mark.needs_tsc),
        pytest.param("vulture", "needs_vulture", marks=pytest.mark.needs_vulture),
        pytest.param("knip", "needs_knip", marks=pytest.mark.needs_knip),
        pytest.param("radon", "needs_radon", marks=pytest.mark.needs_radon),
        pytest.param("jscpd", "needs_jscpd", marks=pytest.mark.needs_jscpd),
        pytest.param(
            "sloppylint", "needs_sloppylint", marks=pytest.mark.needs_sloppylint
        ),
    ],
)
def test_static_engine_is_opt_in_and_discoverable(binary: str, marker: str) -> None:
    """Real-engine contract: probe the installed adapter without source config."""
    if resolve_binary(binary) is None:
        pytest.skip(f"{marker}: {binary} not installed")
    assert ENGINES[binary].version() is not None


def test_typecheck_skips_when_no_supported_source_exists(tmp_path: Path) -> None:
    (tmp_path / "notes.txt").write_text("not source\n")

    result = TypecheckTool().run(tmp_path)

    assert result["tool"] == "typecheck"
    assert result["status"] == "skipped"


def test_typecheck_mcp_description_is_short() -> None:
    assert len(TypecheckTool().mcp_description) < 200


def test_typecheck_handles_python_file_without_mypy(
    monkeypatch, tmp_path: Path
) -> None:
    source = tmp_path / "module.py"
    source.write_text("def answer() -> int:\n    return 42\n")
    monkeypatch.setattr("rush.tools.common.resolve_binary", lambda binary: None)

    result = TypecheckTool().run(source)

    assert result["status"] == "skipped"
    assert "mypy" in result["summary"]


def test_dead_skips_when_no_supported_source_exists(tmp_path: Path) -> None:
    (tmp_path / "notes.txt").write_text("not source\n")

    result = DeadTool().run(tmp_path)

    assert result["tool"] == "dead"
    assert result["status"] == "skipped"


def test_dead_handles_python_file_without_vulture(monkeypatch, tmp_path: Path) -> None:
    source = tmp_path / "module.py"
    source.write_text("def answer() -> int:\n    return 42\n")
    monkeypatch.setattr("rush.tools.common.resolve_binary", lambda binary: None)

    result = DeadTool().run(source)

    assert result["status"] == "skipped"
    assert "vulture" in result["summary"]


def test_complexity_skips_when_no_supported_source_exists(tmp_path: Path) -> None:
    (tmp_path / "notes.txt").write_text("not source\n")

    result = ComplexityTool().run(tmp_path)

    assert result["tool"] == "complexity"
    assert result["status"] == "skipped"


def test_complexity_handles_python_file_without_radon(
    monkeypatch, tmp_path: Path
) -> None:
    source = tmp_path / "module.py"
    source.write_text("def answer() -> int:\n    return 42\n")
    monkeypatch.setattr("rush.tools.common.resolve_binary", lambda binary: None)

    result = ComplexityTool().run(source)

    assert result["status"] == "skipped"
    assert "radon" in result["summary"]


def test_sloppylint_normalizes_documented_json_fixture() -> None:
    fixture = Path("tests/fixtures/engine_reports/sloppylint.json")
    raw = {"exit_code": 0, "stdout": fixture.read_text(), "stderr": ""}

    result = SloppylintEngine().normalize(raw, Path("."), "slop")

    assert result["findings"] == [
        {
            "path": "src/example.py",
            "line": 12,
            "rule": "verbose-comment",
            "severity": "warn",
            "message": "Comment repeats the code",
        }
    ]
    assert json.loads(result["raw"])["summary"]["score"]["total"] == 2


def test_mypy_normalizes_documented_text_fixture() -> None:
    raw = {
        "exit_code": 1,
        "stdout": Path("tests/fixtures/engine_reports/mypy.txt").read_text(),
        "stderr": "",
    }

    result = MypyEngine().normalize(raw, Path("."), "typecheck")

    assert result["findings"] == [
        {
            "path": "src/example.py",
            "line": 4,
            "rule": "assignment",
            "severity": "error",
            "message": "Incompatible types in assignment",
        }
    ]


def test_tsc_normalizes_documented_text_fixture() -> None:
    raw = {
        "exit_code": 2,
        "stdout": Path("tests/fixtures/engine_reports/tsc.txt").read_text(),
        "stderr": "",
    }

    result = TscEngine().normalize(raw, Path("."), "typecheck")

    assert result["findings"] == [
        {
            "path": "src/example.ts",
            "line": 7,
            "column": 3,
            "rule": "TS2322",
            "severity": "error",
            "message": "Type 'string' is not assignable to type 'number'.",
        }
    ]


def test_slop_uses_js_fallback_when_sloppylint_is_unavailable(
    monkeypatch, tmp_path: Path
) -> None:
    source = tmp_path / "generated.ts"
    source.write_text("// generated by AI\nexport const answer = 42\n")
    monkeypatch.setattr("rush.tools.common.resolve_binary", lambda binary: None)

    result = SlopTool().run(tmp_path)

    assert result["status"] == "warn"
    assert result["engine"] == "rush"
    assert result["findings"][0]["rule"] == "rush-ai-marker"


def test_vulture_normalizes_documented_text_fixture() -> None:
    raw = {
        "exit_code": 3,
        "stdout": Path("tests/fixtures/engine_reports/vulture.txt").read_text(),
        "stderr": "",
    }

    result = VultureEngine().normalize(raw, Path("."), "dead")

    assert result["findings"] == [
        {
            "path": "src/example.py",
            "line": 9,
            "rule": "vulture",
            "severity": "warn",
            "message": "unused function 'unused_helper' (60% confidence)",
        }
    ]


def test_radon_normalizes_documented_json_fixture() -> None:
    raw = {
        "exit_code": 0,
        "stdout": Path("tests/fixtures/engine_reports/radon.json").read_text(),
        "stderr": "",
    }

    result = RadonEngine().normalize(raw, Path("."), "complexity")

    assert result["findings"] == [
        {
            "path": "src/example.py",
            "line": 5,
            "rule": "radon",
            "severity": "warn",
            "message": "too_complex: complexity 12",
        }
    ]


def test_knip_normalizes_report_fixture() -> None:
    raw = {
        "exit_code": 0,
        "stdout": Path("tests/fixtures/engine_reports/knip.txt").read_text(),
        "stderr": "",
    }

    result = KnipEngine().normalize(raw, Path("."), "dead")

    assert result["findings"] == [
        {
            "path": "src/example.ts",
            "line": 3,
            "rule": "knip",
            "severity": "warn",
            "message": "Unused export: unusedHelper",
        }
    ]


def test_jscpd_normalizes_report_fixture() -> None:
    raw = {
        "exit_code": 1,
        "stdout": Path("tests/fixtures/engine_reports/jscpd.txt").read_text(),
        "stderr": "",
    }

    result = JscpdEngine().normalize(raw, Path("."), "complexity")

    assert result["findings"] == [
        {
            "path": "src/example.ts",
            "line": 10,
            "rule": "jscpd",
            "severity": "warn",
            "message": "duplicate block",
        }
    ]
