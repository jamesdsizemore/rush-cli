"""Unit tests for Phase 47 TestHealer, ApiDiffer, and GitSandbox."""

from pathlib import Path

from src.rush.tools.api_diff import ApiDiffer
from src.rush.tools.test_heal import TestHealer


def test_test_healer_diagnose(tmp_path: Path):
    target = tmp_path / "test_dummy.py"
    target.write_text("def test_ok(): assert True\n", encoding="utf-8")

    healer = TestHealer(project_root=tmp_path)
    res = healer.diagnose_and_heal(str(target), runs=2)
    assert "error" not in res
    assert res["runs"] == 2
    assert res["is_flaky"] is False


def test_api_differ_signatures(tmp_path: Path):
    code_old = """
def public_api(arg1: int, arg2: str) -> bool:
    return True

class Service:
    def execute(self, task: str) -> None:
        pass
"""
    differ = ApiDiffer(project_root=tmp_path)
    sigs = differ._extract_public_signatures(code_old)

    assert "public_api" in sigs
    assert sigs["public_api"] == ["arg1", "arg2"]
    assert "Service.execute" in sigs
    assert sigs["Service.execute"] == ["self", "task"]
