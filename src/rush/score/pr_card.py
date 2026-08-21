"""GitHub PR Markdown summary scorecard card."""

from __future__ import annotations

from rush.score.calculator import ScorecardReport


class PRCardGenerator:
    """Generates markdown tables for PR comments and CI summaries."""

    @staticmethod
    def generate_markdown_card(report: ScorecardReport) -> str:
        p = report.pillars
        return f"""### 🛡️ Rush Code Quality Scorecard

**Overall Score:** `{report.composite_score}%` (**Grade: `{report.letter_grade}`**)

| Quality Pillar | Score | Target | Status |
|---|---|---|---|
| 🔒 Security | `{p.security}%` | `≥ 90%` | {'✅' if p.security >= 90 else '⚠️'} |
| 🧪 Test Coverage | `{p.test_coverage}%` | `≥ 80%` | {'✅' if p.test_coverage >= 80 else '⚠️'} |
| 🏷️ Type Safety | `{p.type_safety}%` | `≥ 85%` | {'✅' if p.type_safety >= 85 else '⚠️'} |
| 🧹 Code Health | `{p.code_health}%` | `≥ 85%` | {'✅' if p.code_health >= 85 else '⚠️'} |
| 🪙 Token Economy | `{p.token_economy}%` | `≥ 80%` | {'✅' if p.token_economy >= 80 else '⚠️'} |
| 🏛️ Governance | `{p.governance}%` | `≥ 90%` | {'✅' if p.governance >= 90 else '⚠️'} |

> *Generated automatically by Rush Platform.*
"""
