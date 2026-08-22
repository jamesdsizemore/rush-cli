"""Unit tests for Phase 48 DbDriftAuditor, ComplexityDecomposer, and TypeSynthesizer."""

from pathlib import Path

from src.rush.tools.db_drift import DbDriftAuditor
from src.rush.tools.simplify import ComplexityDecomposer
from src.rush.tools.strictify import TypeSynthesizer


def test_db_drift_detection(tmp_path: Path):
    src = tmp_path / "src"
    src.mkdir(parents=True, exist_ok=True)

    model_file = src / "models.py"
    model_file.write_text(
        """
class UserModel:
    id: int
    username: str
    email: str
    phone_number: str
""",
        encoding="utf-8",
    )

    mig_file = tmp_path / "schema.sql"
    mig_file.write_text(
        """
CREATE TABLE users (
    id INTEGER,
    username VARCHAR,
    email VARCHAR
);
""",
        encoding="utf-8",
    )

    auditor = DbDriftAuditor(project_root=tmp_path)
    res = auditor.audit_drift()

    assert res["passed"] is False
    assert res["drift_count"] == 1
    assert "phone_number" in res["drift_issues"][0]["unmigrated_fields"]


def test_complexity_decomposer(tmp_path: Path):
    code_file = tmp_path / "spaghetti.py"
    code_file.write_text(
        """
def monolithic_function(x, y, z):
    if x > 0:
        if y > 0:
            while z > 0:
                for i in range(5):
                    if i % 2 == 0:
                        assert True
    return False
""",
        encoding="utf-8",
    )

    decomposer = ComplexityDecomposer(project_root=tmp_path)
    res = decomposer.decompose_file(code_file, max_complexity=4)

    assert res["needs_simplification"] is True
    assert res["complex_functions_count"] == 1
    assert res["candidates"][0]["function"] == "monolithic_function"
    assert res["candidates"][0]["complexity"] > 4


def test_type_synthesizer(tmp_path: Path):
    code_file = tmp_path / "untyped.py"
    code_file.write_text(
        """
def process_payload(data, status: str = "ok"):
    return data
""",
        encoding="utf-8",
    )

    synth = TypeSynthesizer(project_root=tmp_path)
    res = synth.audit_and_synthesize(code_file)

    assert res["untyped_count"] == 1
    assert res["untyped_arguments"][0]["argument"] == "data"
