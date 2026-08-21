"""Tests for Phase 40: Multi-Model Consensus & Quality Scorecard."""

from __future__ import annotations

import json

from rush.score.calculator import CompositeScorecardCalculator, PillarScores, WeightNormalizer
from rush.score.consensus import ModelFinding, MultiModelConsensusReconciler
from rush.score.html_report import HtmlReportGenerator
from rush.score.pr_card import PRCardGenerator
from rush.score.sarif_export import SarifExporter
from rush.score.svg_badge import SvgBadgeGenerator


def test_weight_normalizer() -> None:
    weights = {"type_safety": 2.0, "test_coverage": 2.0}
    norm = WeightNormalizer.normalize(weights)
    assert norm["type_safety"] == 0.5
    assert norm["test_coverage"] == 0.5


def test_composite_scorecard_calculator() -> None:
    pillars = PillarScores(
        type_safety=95.0,
        test_coverage=90.0,
        code_health=95.0,
        security=100.0,
        token_economy=90.0,
        governance=95.0,
    )
    report = CompositeScorecardCalculator.compute_scorecard(pillars)
    assert report.composite_score >= 90.0
    assert report.letter_grade in ("A+", "A", "A-")
    assert "Composite Quality Score" in report.summary


def test_multi_model_consensus_reconciler() -> None:
    reconciler = MultiModelConsensusReconciler(min_agreement_ratio=0.5)

    f1 = ModelFinding("claude", "src/auth.py", 42, "SEC001", "HIGH", "SQL Injection risk")
    f2 = ModelFinding("gpt4", "src/auth.py", 42, "SEC001", "HIGH", "SQL Injection risk")
    f3 = ModelFinding("gemini", "src/auth.py", 10, "STYLE01", "LOW", "Missing docstring")

    findings = reconciler.reconcile_findings([f1, f2, f3], total_models=3)
    assert len(findings) == 1
    assert findings[0].rule_id == "SEC001"
    assert findings[0].confidence == round(2 / 3, 2)
    assert len(findings[0].agreeing_models) == 2


def test_sarif_exporter() -> None:
    reconciler = MultiModelConsensusReconciler(min_agreement_ratio=0.5)
    f1 = ModelFinding("claude", "src/auth.py", 42, "SEC001", "HIGH", "SQL Injection risk")
    findings = reconciler.reconcile_findings([f1], total_models=1)

    sarif_json = SarifExporter.export_sarif(findings)
    data = json.loads(sarif_json)
    assert data["version"] == "2.1.0"
    assert len(data["runs"][0]["results"]) == 1
    assert data["runs"][0]["results"][0]["ruleId"] == "SEC001"


def test_svg_badge_generator() -> None:
    svg = SvgBadgeGenerator.generate_badge_svg(95.4, "A")
    assert "<svg" in svg
    assert "rush quality" in svg
    assert "95% (A)" in svg


def test_html_report_generator() -> None:
    pillars = PillarScores(90.0, 90.0, 90.0, 90.0, 90.0, 90.0)
    report = CompositeScorecardCalculator.compute_scorecard(pillars)
    html = HtmlReportGenerator.generate_html_report(report)
    assert "<html" in html
    assert "Rush Quality Scorecard" in html


def test_pr_card_generator() -> None:
    pillars = PillarScores(90.0, 90.0, 90.0, 90.0, 90.0, 90.0)
    report = CompositeScorecardCalculator.compute_scorecard(pillars)
    md = PRCardGenerator.generate_markdown_card(report)
    assert "### 🛡️ Rush Code Quality Scorecard" in md
    assert "| 🔒 Security | `90.0%` |" in md
