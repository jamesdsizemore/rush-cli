"""Interactive HTML scorecard dashboard generator."""

from __future__ import annotations

from rush.score.calculator import ScorecardReport


class HtmlReportGenerator:
    """Generates standalone HTML reports for repository quality scorecards."""

    @staticmethod
    def generate_html_report(report: ScorecardReport) -> str:
        from rush.safety.redactor import sanitize_value

        clean = sanitize_value(
            {
                "composite_score": report.composite_score,
                "letter_grade": report.letter_grade,
                "summary": report.summary,
                "pillars": {
                    "type_safety": report.pillars.type_safety,
                    "test_coverage": report.pillars.test_coverage,
                    "code_health": report.pillars.code_health,
                    "security": report.pillars.security,
                    "token_economy": report.pillars.token_economy,
                    "governance": report.pillars.governance,
                },
            }
        ).value
        p = clean["pillars"]
        return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>Rush Quality Scorecard - {clean["composite_score"]}%</title>
  <style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; margin: 40px; background: #0d1117; color: #c9d1d9; }}
    .card {{ background: #161b22; border: 1px solid #30363d; border-radius: 8px; padding: 24px; max-width: 600px; }}
    .score {{ font-size: 48px; font-weight: bold; color: #58a6ff; }}
    .grade {{ font-size: 24px; color: #7ee787; }}
    .pillar {{ display: flex; justify-content: space-between; padding: 8px 0; border-bottom: 1px solid #21262d; }}
  </style>
</head>
<body>
  <div class="card">
    <h1>Rush Quality Scorecard</h1>
    <div class="score">{clean["composite_score"]}% <span class="grade">[{clean["letter_grade"]}]</span></div>
    <p>{clean["summary"]}</p>
    <div class="pillars">
      <div class="pillar"><span>Type Safety:</span><span>{p["type_safety"]}%</span></div>
      <div class="pillar"><span>Test Coverage:</span><span>{p["test_coverage"]}%</span></div>
      <div class="pillar"><span>Code Health:</span><span>{p["code_health"]}%</span></div>
      <div class="pillar"><span>Security:</span><span>{p["security"]}%</span></div>
      <div class="pillar"><span>Token Economy:</span><span>{p["token_economy"]}%</span></div>
      <div class="pillar"><span>Governance:</span><span>{p["governance"]}%</span></div>
    </div>
  </div>
</body>
</html>"""
