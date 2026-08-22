"""Unit tests for Phase 46 BlastRadiusAnalyzer and ArchGuard."""

from pathlib import Path

from src.rush.tools.arch_guard import ArchGuard
from src.rush.tools.blast_radius import BlastRadiusAnalyzer


def test_blast_radius_analyzer(tmp_path: Path):
    mod_a = tmp_path / "util.py"
    mod_a.write_text("def helper(): return True\n", encoding="utf-8")

    mod_b = tmp_path / "api_route.py"
    mod_b.write_text(
        "from util import helper\ndef route(): return helper()\n", encoding="utf-8"
    )

    mod_c = tmp_path / "test_api.py"
    mod_c.write_text(
        "import util\ndef test_something(): assert util.helper()\n", encoding="utf-8"
    )

    analyzer = BlastRadiusAnalyzer(project_root=tmp_path)
    report = analyzer.analyze([mod_a], max_depth=3)

    assert len(report.affected_files) == 2
    assert "api_route.py" in report.affected_routes
    assert "test_api.py" in report.recommended_tests
    assert report.risk_score in ("LOW", "MEDIUM")


def test_arch_guard_detects_violations(tmp_path: Path):
    src = tmp_path / "src" / "rush"
    domain_dir = src / "domain"
    infra_dir = src / "infrastructure"
    domain_dir.mkdir(parents=True, exist_ok=True)
    infra_dir.mkdir(parents=True, exist_ok=True)

    # Clean file in infra importing domain
    (infra_dir / "repo.py").write_text(
        "from rush.domain import model\n", encoding="utf-8"
    )

    # Illegal violation: domain importing infrastructure
    (domain_dir / "entity.py").write_text(
        "from rush.infrastructure import repo\n", encoding="utf-8"
    )

    guard = ArchGuard(project_root=tmp_path)
    res = guard.evaluate_boundaries(
        {
            "domain": [],
            "infrastructure": ["domain"],
        }
    )

    assert res["passed"] is False
    assert res["violations_count"] == 1
    assert res["violations"][0]["source_layer"] == "domain"
    assert res["violations"][0]["illegal_target_layer"] == "infrastructure"
