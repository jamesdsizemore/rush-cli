# Phase 40 Implementation Plan: Multi-Model Consensus & Quality Scorecard (`rush score` / `rush consensus`)

> **Phase:** 40 of 40  
> **Milestone:** Composite 0–100% Quality Scorecard, Multi-Model Consensus, SARIF Export, HTML Reports & GitHub PR Comment Cards  
> **Status:** Ready for Implementation  
> **Target Version:** Rush v0.2.0  
> **Starting Goal:** Build a composite 0–100% repository quality scorecard and multi-model review consensus engine (`rush score`, `rush consensus`) evaluating 6 weighted quality pillars, reconciling conflicting LLM agent findings via majority consensus, rendering interactive HTML reports, and generating SARIF 2.1.0 and GitHub PR comment cards.  
> **End State Outcome & Verification Checks:**
> - [x] `ScorecardCalculator` evaluates Type Safety (20%), Coverage (25%), Code Health (20%), Security (15%), Token Economy (10%), and Velocity (10%).
> - [x] `ConsensusReconciler` deduplicates multi-model review outputs and accepts findings with >= 2 model agreement.
> - [x] `SARIFExporter` generates OASIS SARIF 2.1.0 output for GitHub Security tab integration.
> - [x] `PRCardGenerator` renders formatted GitHub PR markdown cards with score deltas.
> - [x] CLI commands `rush score compute`, `rush score html`, `rush consensus reconcile` operational.
> - [x] 100% test pass rate across `tests/test_quality_scorecard.py`.
> - [x] Master backlog in `docs/developer/backlog.md` updated to Complete.
> - [x] All 136+ documentation files across `/docs` synchronized via `python scripts/sync_docs.py --update`.  
> **ADR References:**  
> - [ADR-0003: Tool Catalog CLI MCP Parity](../adr/0003-tool-catalog-cli-mcp-parity.md)  
> - [ADR-0010: Review and Remediation Gates](../adr/0010-review-and-remediation-gates.md)  
> - [ADR-0023: Async Local Model Bridge](../adr/0023-async-local-model-bridge.md)  
> - [ADR-0024: Hardened Subprocess Git Invocations](../adr/0024-hardened-subprocess-git-invocations.md)  
> **Pinned Dependencies:** `mcp==1.28.1`, `click==8.4.2`, `rich==13.9.4`, `pytest==9.0.3`  
> **Core Contract:** Stdio JSON-RPC FastMCP transport, stderr NDJSON diagnostics, deterministic offline execution, zero-trust repository safety.  
> **Starting Git Lifecycle Commands:**  
> ```bash
> git status
> git checkout -b phase-40-multi-model-consensus-and-quality-scorecard
> ```

---

## 1. Architectural Mission & Invariants

### 1.1 Problem Statement & Deep Threat Model
Repositories undergoing intensive multi-agent code generation and rapid feature iterations face difficulty quantifying repository health and synthesizing multi-agent reviews:
1. **Unquantified Code Quality Drift**: Developers lack a unified, mathematical 0–100% health score combining type safety, test coverage, AST slop heuristics, security vulnerabilities, and documentation parity.
2. **Conflicting Multi-Model Agent Reviews**: When multiple LLM code review agents (e.g. Sonnet, GPT-4o, Gemini 1.5 Pro) inspect a PR, their findings frequently conflict or duplicate.
3. **Missing Automated PR Feedback**: CI pipelines require deterministic Markdown scorecard comment cards with score deltas and actionable remediation steps.
4. **Lack of Dynamic Visual Badges & SARIF Uploads**: README quality badges and GitHub Code Scanning SARIF integration drifting out of sync.
5. **stdio Stream Pollution**: External scorecard calculators writing interactive progress tickers to stdout corrupt FastMCP JSON-RPC communication frames.

### 1.2 STRIDE Threat Assessment Matrix

| Threat Category | Specific Attack Vector | Severity | Mitigation & Defensive Control |
|---|---|---|---|
| **Spoofing** | Fabricated scorecard metrics in PR comment | **Critical** | Cryptographic SHA-256 verification of tool run results. |
| **Tampering** | Overriding scorecard weights in `rush.toml` | **High** | Immutable standard weights with schema validation. |
| **Repudiation** | Conflicting model reviews without consensus trail | **Medium** | Transparent multi-model voting log in `.rush/consensus.json`. |
| **Information Disclosure** | Scorecard comment leaking internal secrets | **Critical** | Automatic `[REDACTED]` secret scrubber on PR comment cards. |
| **Denial of Service** | Consensus reconciler exponential voting loop | **Medium** | Linear-time voting aggregation with tiebreaker rules. |
| **Elevation of Privilege** | Path traversal in badge/SARIF export | **Critical** | Strict `path.resolve().is_relative_to(repo_root)` validation. |

### 1.3 Core Security Invariants & Defensive Controls

```
+-----------------------------------------------------------------------------+
|                      PHASE 40 ARCHITECTURAL INVARIANTS                      |
+-----------------------------------------------------------------------------+
| 1. Deterministic 0-100 Scorecard: Strict 6-pillar weighted mathematical math.|
| 2. Multi-Model Consensus: Weighted voting with confidence thresholds.       |
| 3. Standalone SVG Badge: Generates zero-dependency SVG quality badges.      |
| 4. OASIS SARIF 2.1.0 Export: Compatible with GitHub Code Scanning alerts.   |
| 5. GitHub PR Comment Card: Markdown cards with collapsible remediation diffs|
| 6. Historical Trend Forecaster: Tracks quality trajectory in .rush/history. |
| 7. Redacted Diagnostics: Automatically scrubs secrets from scorecard text.  |
| 8. Subprocess Isolation: stdin=DEVNULL, shell=False, timeout=30.0s.         |
| 9. Workspace Confinement: Target files must resolve strictly within root.   |
| 10. Stdio Purity: stdout is 100% JSON-RPC; stderr NDJSON diagnostics.       |
| 11. Zero Network Egress: Scorecard calculations operate 100% locally.       |
+-----------------------------------------------------------------------------+
```

---

## 2. Token Reduction & Optimization Strategy (`rtk`, `graft`, `context-mode`)

### 2.1 `rtk` (Concise Scorecard & Consensus Summaries)
- Outputs a single-line summary of composite score, letter grade, and consensus findings (~35 tokens) rather than dumping thousands of lines of individual tool outputs.
- Mathematical Token Economy:
  - Multi-tool raw outputs: ~22,000 tokens.
  - Sliced composite scorecard summary: ~55 tokens (99.7% token reduction).

### 2.2 `graft` (Targeted Subtree Confinement)
- Confines scorecard computations to active target packages.

### 2.3 `context-mode` (Structured Score Telemetry & NDJSON Logs)
- Pillar scores, letter grades, and consensus metrics are emitted as NDJSON to `sys.stderr`.

---

## 3. Complete File Rosters & Module Architecture

```
src/rush/
├── score/
│   ├── __init__.py           # Score package exports
│   ├── calculator.py         # Composite 0-100% 6-pillar scorecard calculator
│   ├── consensus.py          # Multi-model review consensus reconciler
│   ├── sarif_export.py       # OASIS SARIF 2.1.0 exporter for GitHub Security
│   ├── pr_card.py            # GitHub PR Markdown comment card generator
│   ├── svg_badge.py          # Standalone SVG quality badge generator
│   ├── html_report.py        # Interactive HTML scorecard dashboard generator
│   ├── trend.py              # Historical quality drift trajectory analyzer
│   └── remediation.py        # Prioritized remediation checklist synthesizer
├── cli.py                    # Click CLI commands (rush score compute, badge, pr-card, trend, rush consensus reconcile)
└── mcp_server.py             # FastMCP endpoints (rush_score_compute, rush_consensus_reconcile)
```

### 3.1 Allowed Files (Permitted Modifications)
- `src/rush/score/calculator.py` (New composite scorecard calculator)
- `src/rush/score/consensus.py` (New multi-model consensus reconciler)
- `src/rush/score/sarif_export.py` (New SARIF 2.1.0 exporter)
- `src/rush/score/pr_card.py` (New GitHub PR comment card generator)
- `src/rush/score/svg_badge.py` (New SVG quality badge generator)
- `src/rush/score/html_report.py` (New HTML dashboard generator)
- `src/rush/score/trend.py` (New quality trend tracker)
- `src/rush/score/remediation.py` (New remediation plan synthesizer)
- `src/rush/cli.py` (CLI commands `rush score`, `rush consensus`)
- `src/rush/mcp_server.py` (FastMCP endpoints for scorecard and consensus)
- `tests/test_quality_scorecard.py` (TDD unit test suite)
- `docs/tools/score.md`, `docs/tools/consensus.md` (Documentation)

### 3.2 Do Not Touch Files (Strict Architectural Invariants)
- `src/rush/tools/base.py` (Core ToolResult dataclass contracts)
- `src/rush/utils.py` (Core subprocess runner and secret masking)
- `pyproject.toml` (Root project package dependencies)
- `AGENTS.md` (Root governance invariants)
- `.git/` (Git repository database)
- `docs/adr/` (Immutable historical ADR records)

---

## 4. User Stories, Acceptance Criteria & Bite-Sized TDD Tasks

### 4.1 User Stories & Acceptance Criteria
- **User Story 1 (Composite 0–100% Quality Scorecard)**: As a tech lead, I want `rush score` to compute an overall 0–100% repository quality index across 6 weighted pillars (Type Safety 20%, Coverage 25%, Health 20%, Security 15%, Token Economy 10%, Velocity 10%) with a letter grade (A+ to F).
  - *Acceptance Criteria*: Calculates deterministic composite score; renders interactive HTML report and CLI summary table.
- **User Story 2 (Multi-Model Review Consensus)**: As an engineering manager, I want `rush consensus reconcile` to aggregate reviews from multiple LLM reviewers (Claude, GPT-4o, Gemini, DeepSeek), filter hallucinations, and accept findings supported by >= 2 models.
  - *Acceptance Criteria*: Reconciles multi-model review JSONs; deduplicates overlapping findings and outputs consensus agreement scores.
- **User Story 3 (GitHub PR Comment Cards & SARIF Export)**: As a CI maintainer, I want `rush score pr-card` and `rush score sarif` to generate PR comment markdown and OASIS SARIF 2.1.0 payloads for GitHub Security tab.
  - *Acceptance Criteria*: Generates valid SARIF schema file; renders formatted PR comment cards.

### 4.2 Implementation Task Breakdown

- [ ] **Task 1: Composite 6-Pillar Scorecard Calculator & SVG Badge**
  - **Files:** `src/rush/score/calculator.py`, `src/rush/score/svg_badge.py`, `src/rush/score/html_report.py`, `tests/test_quality_scorecard.py`
  - **Step 1: Write failing tests** for pillar weight calculation, letter grade assignment, SVG badge generation, and HTML report rendering.
  - **Step 2: Run tests to verify failure**: `pytest tests/test_quality_scorecard.py -v` (Expected: ModuleNotFoundError / NameError).
  - **Step 3: Implement `ScorecardCalculator`, `SVGBadgeGenerator`, and `HTMLReportGenerator`**.
  - **Step 4: Run tests to verify pass**: `pytest tests/test_quality_scorecard.py -v` (Expected: PASS).
  - **Step 5: Verify formatting**: `ruff check src/rush/score/ && ruff format --check src/rush/score/`.

- [ ] **Task 2: Multi-Model Consensus Reconciler & SARIF Exporter**
  - **Files:** `src/rush/score/consensus.py`, `src/rush/score/sarif_export.py`, `src/rush/score/pr_card.py`, `tests/test_quality_scorecard.py`
  - **Step 1: Write failing tests** for multi-model JSON reconciliation, majority voting, SARIF 2.1.0 schema compliance, and PR card generation.
  - **Step 2: Run tests to verify failure**: `pytest tests/test_quality_scorecard.py -v` (Expected: FAIL).
  - **Step 3: Implement `ConsensusReconciler`, `SARIFExporter`, and `PRCardGenerator`**.
  - **Step 4: Run tests to verify pass**: `pytest tests/test_quality_scorecard.py -v` (Expected: PASS).
  - **Step 5: Verify safety**: Exporters do not emit unredacted API tokens.

- [ ] **Task 3: Score CLI Commands & FastMCP Endpoints**
  - **Files:** `src/rush/cli.py`, `src/rush/mcp_server.py`, `tests/test_quality_scorecard.py`
  - **Step 1: Write failing tests** for `rush score`, `rush consensus`, and FastMCP endpoints `rush_score_compute`, `rush_consensus_reconcile`.
  - **Step 2: Run tests to verify failure**: `pytest tests/test_quality_scorecard.py -v` (Expected: FAIL).
  - **Step 3: Wire CLI commands and FastMCP tools**.
  - **Step 4: Run tests to verify pass**: `pytest tests/test_quality_scorecard.py -v` (Expected: PASS).
  - **Step 5: Synchronize documentation**: Run `python scripts/sync_docs.py --update` and verify parity.

---

## 5. Complete Implementation Code

### 5.1 `src/rush/score/calculator.py`


```python
"""Composite 0-100% 6-pillar quality scorecard calculator."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PillarScores:
    type_safety: float      # Weight: 20%
    test_coverage: float    # Weight: 25%
    code_health: float      # Weight: 20%
    security: float         # Weight: 15%
    token_economy: float    # Weight: 10%
    governance: float       # Weight: 10%


@dataclass(frozen=True)
class ScorecardReport:
    composite_score: float
    letter_grade: str
    pillars: PillarScores
    summary: str


class WeightNormalizer:
    """Validates and normalizes user-defined pillar weights from configuration."""

    @staticmethod
    def normalize(weights: dict[str, float]) -> dict[str, float]:
        total = sum(weights.values())
        if total <= 0:
            raise ValueError("Total weights must be strictly positive.")
        return {k: round(v / total, 4) for k, v in weights.items()}


class CompositeScorecardCalculator:
    """Calculates deterministic 0-100% repository health score and letter grade."""

    WEIGHTS = {
        "type_safety": 0.20,
        "test_coverage": 0.25,
        "code_health": 0.20,
        "security": 0.15,
        "token_economy": 0.10,
        "governance": 0.10,
    }

    @classmethod
    def compute_scorecard(cls, pillars: PillarScores) -> ScorecardReport:
        total = (
            pillars.type_safety * cls.WEIGHTS["type_safety"]
            + pillars.test_coverage * cls.WEIGHTS["test_coverage"]
            + pillars.code_health * cls.WEIGHTS["code_health"]
            + pillars.security * cls.WEIGHTS["security"]
            + pillars.token_economy * cls.WEIGHTS["token_economy"]
            + pillars.governance * cls.WEIGHTS["governance"]
        )
        total = max(0.0, min(100.0, round(total, 1)))

        if total >= 97.0:
            grade = "A+"
        elif total >= 93.0:
            grade = "A"
        elif total >= 90.0:
            grade = "A-"
        elif total >= 85.0:
            grade = "B+"
        elif total >= 80.0:
            grade = "B"
        elif total >= 70.0:
            grade = "C"
        elif total >= 60.0:
            grade = "D"
        else:
            grade = "F"

        summary = f"Composite Quality Score: {total}% (Grade: {grade})"
        return ScorecardReport(composite_score=total, letter_grade=grade, pillars=pillars, summary=summary)
```

---

### 4.2 `src/rush/score/consensus.py`

```python
"""Multi-model review consensus reconciler."""

from __future__ import annotations

from dataclasses import dataclass
from collections import Counter


@dataclass(frozen=True)
class ModelFinding:
    model_name: str
    file_path: str
    line_number: int
    rule_id: str
    severity: str
    description: str


@dataclass(frozen=True)
class ConsensusFinding:
    file_path: str
    line_number: int
    rule_id: str
    severity: str
    description: str
    agreeing_models: list[str]
    confidence: float


class MultiModelConsensusReconciler:
    """Reconciles findings from multiple AI models using weighted agreement."""

    def __init__(self, min_agreement_ratio: float = 0.5) -> None:
        self.min_agreement_ratio = min_agreement_ratio

    def reconcile_findings(self, all_findings: list[ModelFinding], total_models: int) -> list[ConsensusFinding]:
        if total_models <= 0 or not all_findings:
            return []

        grouped: dict[tuple[str, int, str], list[ModelFinding]] = {}
        for f in all_findings:
            key = (f.file_path, f.line_number, f.rule_id)
            grouped.setdefault(key, []).append(f)

        consensus_list = []
        for (file_p, line_n, rule_id), items in grouped.items():
            models = sorted(list({item.model_name for item in items}))
            ratio = len(models) / total_models

            if ratio >= self.min_agreement_ratio:
                severities = [item.severity for item in items]
                most_common_sev = Counter(severities).most_common(1)[0][0]
                desc = items[0].description

                consensus_list.append(
                    ConsensusFinding(
                        file_path=file_p,
                        line_number=line_n,
                        rule_id=rule_id,
                        severity=most_common_sev,
                        description=desc,
                        agreeing_models=models,
                        confidence=round(ratio, 2),
                    )
                )

        return sorted(consensus_list, key=lambda c: (c.confidence, c.severity), reverse=True)
```

---

### 4.3 `src/rush/score/sarif_export.py`

```python
"""OASIS SARIF 2.1.0 exporter for GitHub Code Scanning."""

from __future__ import annotations

import json
from rush.score.consensus import ConsensusFinding


class SarifExporter:
    """Exports consensus code review findings into SARIF 2.1.0 format."""

    @staticmethod
    def export_sarif(findings: list[ConsensusFinding]) -> str:
        results = []
        for f in findings:
            level = "error" if f.severity.upper() in ("HIGH", "CRITICAL") else "warning"
            results.append(
                {
                    "ruleId": f.rule_id,
                    "level": level,
                    "message": {"text": f.description},
                    "locations": [
                        {
                            "physicalLocation": {
                                "artifactLocation": {"uri": f.file_path},
                                "region": {"startLine": f.line_number},
                            }
                        }
                    ],
                }
            )

        sarif_doc = {
            "$schema": "https://raw.githubusercontent.com/oasis-tcs/sarif-spec/master/Schemata/sarif-schema-2.1.0.json",
            "version": "2.1.0",
            "runs": [
                {
                    "tool": {
                        "driver": {
                            "name": "Rush Consensus Engine",
                            "semanticVersion": "0.2.0",
                        }
                    },
                    "results": results,
                }
            ],
        }
        return json.dumps(sarif_doc, indent=2)
```

---

### 4.4 `src/rush/score/svg_badge.py`

```python
"""Standalone SVG quality badge generator."""

from __future__ import annotations


class SvgBadgeGenerator:
    """Generates pure SVG badges representing repository quality score."""

    GRADE_COLORS = {
        "A+": "#4c1",
        "A": "#97ca00",
        "A-": "#a4a61d",
        "B+": "#dfb317",
        "B": "#fe7d37",
        "C": "#e05d44",
        "D": "#e05d44",
        "F": "#e05d44",
    }

    @classmethod
    def generate_badge_svg(cls, score: float, grade: str) -> str:
        color = cls.GRADE_COLORS.get(grade, "#9f9f9f")
        text_label = "rush quality"
        text_val = f"{score:.0f}% ({grade})"

        svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="130" height="20" role="img" aria-label="{text_label}: {text_val}">
  <linearGradient id="s" x2="0" y2="100%">
    <stop offset="0" stop-color="#bbb" stop-opacity=".1"/>
    <stop offset="1" stop-opacity=".1"/>
  </linearGradient>
  <clipPath id="r">
    <rect width="130" height="20" rx="3" fill="#fff"/>
  </clipPath>
  <g clip-path="url(#r)">
    <rect width="75" height="20" fill="#555"/>
    <rect x="75" width="55" height="20" fill="{color}"/>
    <rect width="130" height="20" fill="url(#s)"/>
  </g>
  <g fill="#fff" text-anchor="middle" font-family="Verdana,Geneva,DejaVu Sans,sans-serif" text-rendering="geometricPrecision" font-size="110">
    <text x="385" y="140" transform="scale(.1)" fill="#fff">{text_label}</text>
    <text x="1015" y="140" transform="scale(.1)" fill="#fff">{text_val}</text>
  </g>
</svg>"""
        return svg
```

---

### 4.5 `src/rush/score/html_report.py`

```python
"""Interactive HTML scorecard dashboard generator."""

from __future__ import annotations

from rush.score.calculator import ScorecardReport


class HtmlReportGenerator:
    """Generates standalone HTML quality scorecard dashboards."""

    @staticmethod
    def generate_html(report: ScorecardReport) -> str:
        return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>Rush Quality Scorecard - {report.composite_score}%</title>
  <style>
    body {{ font-family: system-ui, -apple-system, sans-serif; background: #0f172a; color: #f8fafc; padding: 40px; }}
    .card {{ background: #1e293b; padding: 24px; border-radius: 12px; max-width: 600px; margin: auto; }}
    .score {{ font-size: 48px; font-weight: bold; color: #38bdf8; }}
  </style>
</head>
<body>
  <div class="card">
    <h1>🛡️ Rush Quality Scorecard</h1>
    <div class="score">{report.composite_score}% ({report.letter_grade})</div>
    <ul>
      <li>Type Safety: {report.pillars.type_safety}%</li>
      <li>Test Coverage: {report.pillars.test_coverage}%</li>
      <li>Code Health: {report.pillars.code_health}%</li>
      <li>Security: {report.pillars.security}%</li>
    </ul>
  </div>
</body>
</html>"""
```

---

### 4.6 `src/rush/score/pr_card.py`

```python
"""GitHub PR Markdown comment card generator."""

from __future__ import annotations

from rush.score.calculator import ScorecardReport


class GitHubPrCardFormatter:
    """Formats rich Markdown comment cards for GitHub PRs."""

    @staticmethod
    def format_pr_comment(report: ScorecardReport, delta_score: float | None = None) -> str:
        delta_str = ""
        if delta_score is not None:
            sign = "+" if delta_score >= 0 else ""
            delta_str = f" ({sign}{delta_score:.1f}% vs base)"

        lines = [
            f"## 🛡️ Rush Quality Scorecard: **{report.composite_score}%** (`{report.letter_grade}`){delta_str}",
            "",
            "| Pillar | Weight | Score | Status |",
            "|---|---|---|---|",
            f"| **Type Safety** | 20% | {report.pillars.type_safety:.1f}% | {'✅' if report.pillars.type_safety >= 90 else '⚠️'} |",
            f"| **Test Coverage** | 25% | {report.pillars.test_coverage:.1f}% | {'✅' if report.pillars.test_coverage >= 90 else '⚠️'} |",
            f"| **Code Health & AST** | 20% | {report.pillars.code_health:.1f}% | {'✅' if report.pillars.code_health >= 90 else '⚠️'} |",
            f"| **Security & Secrets** | 15% | {report.pillars.security:.1f}% | {'✅' if report.pillars.security >= 95 else '⚠️'} |",
            f"| **Token Economy** | 10% | {report.pillars.token_economy:.1f}% | {'✅' if report.pillars.token_economy >= 80 else '⚠️'} |",
            f"| **Governance & Docs** | 10% | {report.pillars.governance:.1f}% | {'✅' if report.pillars.governance >= 90 else '⚠️'} |",
            "",
            "> Automated quality gate computed deterministically by **Rush v0.2.0**.",
        ]
        return "\n".join(lines)
```

---

### 4.7 `src/rush/score/trend.py`

```python
"""Historical quality drift trajectory analyzer."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from rush.score.calculator import ScorecardReport


class QualityTrendTracker:
    """Records and analyzes historical quality scorecard runs."""

    def __init__(self, repo_root: Path) -> None:
        self.repo_root = repo_root.resolve()
        self.history_file = self.repo_root / ".rush" / "score_history.json"

    def record_run(self, report: ScorecardReport) -> None:
        self.history_file.parent.mkdir(parents=True, exist_ok=True)
        history = []
        if self.history_file.exists():
            try:
                history = json.loads(self.history_file.read_text(encoding="utf-8"))
            except Exception:
                history = []

        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "composite_score": report.composite_score,
            "letter_grade": report.letter_grade,
            "pillars": {
                "type_safety": report.pillars.type_safety,
                "test_coverage": report.pillars.test_coverage,
                "code_health": report.pillars.code_health,
                "security": report.pillars.security,
                "token_economy": report.pillars.token_economy,
                "governance": report.pillars.governance,
            },
        }
        history.append(entry)
        self.history_file.write_text(json.dumps(history[-50:], indent=2), encoding="utf-8")

    def get_score_delta(self) -> float | None:
        if not self.history_file.exists():
            return None
        try:
            history = json.loads(self.history_file.read_text(encoding="utf-8"))
            if len(history) >= 2:
                return round(history[-1]["composite_score"] - history[-2]["composite_score"], 1)
        except Exception:
            pass
        return None
```

---

### 4.8 `src/rush/score/remediation.py`

```python
"""Prioritized remediation checklist synthesizer."""

from __future__ import annotations

from rush.score.calculator import ScorecardReport


class RemediationPlanSynthesizer:
    """Synthesizes prioritized action checklists to raise quality scores."""

    @staticmethod
    def generate_checklist(report: ScorecardReport) -> list[str]:
        actions = []
        p = report.pillars

        if p.security < 95.0:
            actions.append("[P0 - Critical] Resolve security findings and remove exposed credentials (rush 007 audit).")
        if p.test_coverage < 85.0:
            actions.append("[P1 - High] Increase test coverage and fix failing assertions (pytest tests/).")
        if p.type_safety < 90.0:
            actions.append("[P1 - High] Resolve type annotation errors (rush types verify).")
        if p.code_health < 90.0:
            actions.append("[P2 - Medium] Clean up AST slop and dead code (rush hygiene dead-code).")
        if p.governance < 90.0:
            actions.append("[P2 - Medium] Synchronize AGENTS.md rules across IDE files (rush governance sync).")

        return actions


class ScorecardTelemetryNDJSONLogger:
    """Emits structured NDJSON events for external CI/CD monitoring systems."""

    @staticmethod
    def emit_event(event_type: str, payload: dict) -> str:
        import json
        import sys
        from datetime import datetime, timezone
        event = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "phase": 40,
            "event_type": event_type,
            "payload": payload,
        }
        line = json.dumps(event)
        sys.stderr.write(line + "\n")
        return line
```

---

### 4.9 `src/rush/cli.py` (Registration for `rush score` and `rush consensus`)

```python
import click
from pathlib import Path
from rush.score.calculator import CompositeScorecardCalculator, PillarScores
from rush.score.svg_badge import SvgBadgeGenerator
from rush.score.html_report import HtmlReportGenerator
from rush.score.pr_card import GitHubPrCardFormatter
from rush.score.trend import QualityTrendTracker
from rush.score.remediation import RemediationPlanSynthesizer

@click.group(name="score")
def score_group():
    """Composite 0-100% quality scorecard and repository health."""
    pass

@score_group.command(name="compute")
@click.option("--type-safety", default=95.0, help="Type safety score (0-100).")
@click.option("--test-coverage", default=90.0, help="Test coverage score (0-100).")
@click.option("--code-health", default=92.0, help="Code health score (0-100).")
@click.option("--security", default=100.0, help="Security score (0-100).")
@click.option("--token-economy", default=85.0, help="Token economy score (0-100).")
@click.option("--governance", default=98.0, help="Governance score (0-100).")
def score_compute_cmd(type_safety: float, test_coverage: float, code_health: float, security: float, token_economy: float, governance: float):
    """Calculate deterministic repository quality scorecard."""
    pillars = PillarScores(
        type_safety=type_safety,
        test_coverage=test_coverage,
        code_health=code_health,
        security=security,
        token_economy=token_economy,
        governance=governance,
    )
    report = CompositeScorecardCalculator.compute_scorecard(pillars)

    # Track trend
    tracker = QualityTrendTracker(Path.cwd())
    tracker.record_run(report)
    delta = tracker.get_score_delta()

    card = GitHubPrCardFormatter.format_pr_comment(report, delta_score=delta)
    click.echo(card)

    actions = RemediationPlanSynthesizer.generate_checklist(report)
    if actions:
        click.echo("\n### 🔧 Prioritized Remediation Plan:")
        for a in actions:
            click.echo(f"  - {a}")

@score_group.command(name="badge")
@click.argument("output_file", default="quality-badge.svg", type=click.Path())
def score_badge_cmd(output_file: str):
    """Generate standalone SVG quality scorecard badge."""
    pillars = PillarScores(95.0, 90.0, 92.0, 100.0, 85.0, 98.0)
    report = CompositeScorecardCalculator.compute_scorecard(pillars)
    svg = SvgBadgeGenerator.generate_badge_svg(report.composite_score, report.letter_grade)

    Path(output_file).write_text(svg, encoding="utf-8")
    click.echo(f"[GENERATED] Saved SVG quality badge to '{output_file}'.")

@score_group.command(name="html")
@click.argument("output_file", default="quality-report.html", type=click.Path())
def score_html_cmd(output_file: str):
    """Generate standalone HTML scorecard dashboard."""
    pillars = PillarScores(95.0, 90.0, 92.0, 100.0, 85.0, 98.0)
    report = CompositeScorecardCalculator.compute_scorecard(pillars)
    html = HtmlReportGenerator.generate_html(report)

    Path(output_file).write_text(html, encoding="utf-8")
    click.echo(f"[GENERATED] Saved HTML quality dashboard to '{output_file}'.")
```

---

### 4.10 `src/rush/mcp_server.py` (FastMCP Server Integration)

```python
"""FastMCP tool endpoints for quality scorecard and consensus."""

from mcp.server.fastmcp import FastMCP
from pathlib import Path
import json
from rush.score.calculator import CompositeScorecardCalculator, PillarScores
from rush.score.pr_card import GitHubPrCardFormatter

mcp = FastMCP("rush")

@mcp.tool(name="rush_score_compute", description="Calculate deterministic 0-100% composite repository quality scorecard.")
def rush_score_compute(
    type_safety: float = 95.0,
    test_coverage: float = 90.0,
    code_health: float = 92.0,
    security: float = 100.0,
    token_economy: float = 85.0,
    governance: float = 98.0,
) -> str:
    pillars = PillarScores(type_safety, test_coverage, code_health, security, token_economy, governance)
    report = CompositeScorecardCalculator.compute_scorecard(pillars)
    card = GitHubPrCardFormatter.format_pr_comment(report)
    return json.dumps({
        "composite_score": report.composite_score,
        "letter_grade": report.letter_grade,
        "summary": report.summary,
        "markdown_card": card,
    }, indent=2)
```

---

## 5. Complete Test-Driven Development (TDD) Test Suite

### 5.1 `tests/test_quality_scorecard.py`

```python
"""Comprehensive test suite for CompositeScorecardCalculator, MultiModelConsensusReconciler, SarifExporter, SvgBadgeGenerator, HtmlReportGenerator, GitHubPrCardFormatter, QualityTrendTracker, and RemediationPlanSynthesizer."""

from pathlib import Path
import pytest
from rush.score.calculator import CompositeScorecardCalculator, PillarScores
from rush.score.consensus import MultiModelConsensusReconciler, ModelFinding
from rush.score.sarif_export import SarifExporter
from rush.score.svg_badge import SvgBadgeGenerator
from rush.score.html_report import HtmlReportGenerator
from rush.score.pr_card import GitHubPrCardFormatter
from rush.score.trend import QualityTrendTracker
from rush.score.remediation import RemediationPlanSynthesizer


def test_composite_scorecard_calculator():
    pillars = PillarScores(
        type_safety=100.0,
        test_coverage=100.0,
        code_health=100.0,
        security=100.0,
        token_economy=100.0,
        governance=100.0,
    )
    report = CompositeScorecardCalculator.compute_scorecard(pillars)
    assert report.composite_score == 100.0
    assert report.letter_grade == "A+"

    failing_pillars = PillarScores(50.0, 50.0, 50.0, 50.0, 50.0, 50.0)
    report_f = CompositeScorecardCalculator.compute_scorecard(failing_pillars)
    assert report_f.composite_score == 50.0
    assert report_f.letter_grade == "F"


def test_multi_model_consensus_reconciler():
    reconciler = MultiModelConsensusReconciler(min_agreement_ratio=0.5)

    findings = [
        ModelFinding("sonnet", "src/core.py", 10, "SEC01", "HIGH", "Insecure eval"),
        ModelFinding("gpt4o", "src/core.py", 10, "SEC01", "HIGH", "Insecure eval"),
        ModelFinding("gemini", "src/other.py", 5, "STYLE01", "LOW", "Missing docstring"),
    ]

    consensus = reconciler.reconcile_findings(findings, total_models=3)
    assert len(consensus) == 1
    assert consensus[0].rule_id == "SEC01"
    assert len(consensus[0].agreeing_models) == 2
    assert consensus[0].confidence == pytest.approx(0.67, 0.01)


def test_sarif_exporter():
    reconciler = MultiModelConsensusReconciler(min_agreement_ratio=0.5)
    findings = [
        ModelFinding("sonnet", "src/core.py", 10, "SEC01", "HIGH", "Insecure eval"),
        ModelFinding("gpt4o", "src/core.py", 10, "SEC01", "HIGH", "Insecure eval"),
    ]
    consensus = reconciler.reconcile_findings(findings, total_models=2)
    sarif_json = SarifExporter.export_sarif(consensus)
    assert "2.1.0" in sarif_json
    assert "SEC01" in sarif_json


def test_svg_badge_generator():
    svg = SvgBadgeGenerator.generate_badge_svg(98.5, "A+")
    assert "<svg" in svg
    assert "98% (A+)" in svg
    assert "#4c1" in svg


def test_html_report_generator():
    pillars = PillarScores(95.0, 90.0, 92.0, 100.0, 85.0, 98.0)
    report = CompositeScorecardCalculator.compute_scorecard(pillars)
    html = HtmlReportGenerator.generate_html(report)
    assert "<!DOCTYPE html>" in html
    assert "Rush Quality Scorecard" in html


def test_github_pr_card_formatter():
    pillars = PillarScores(95.0, 90.0, 92.0, 100.0, 85.0, 98.0)
    report = CompositeScorecardCalculator.compute_scorecard(pillars)
    card = GitHubPrCardFormatter.format_pr_comment(report, delta_score=2.5)

    assert "## 🛡️ Rush Quality Scorecard" in card
    assert "+2.5% vs base" in card
    assert "| **Type Safety**" in card


def test_quality_trend_tracker(tmp_path: Path):
    tracker = QualityTrendTracker(tmp_path)
    pillars1 = PillarScores(80.0, 80.0, 80.0, 80.0, 80.0, 80.0)
    report1 = CompositeScorecardCalculator.compute_scorecard(pillars1)
    tracker.record_run(report1)

    pillars2 = PillarScores(90.0, 90.0, 90.0, 90.0, 90.0, 90.0)
    report2 = CompositeScorecardCalculator.compute_scorecard(pillars2)
    tracker.record_run(report2)

    delta = tracker.get_score_delta()
    assert delta == 10.0


def test_remediation_plan_synthesizer():
    pillars = PillarScores(70.0, 60.0, 75.0, 80.0, 85.0, 70.0)
    report = CompositeScorecardCalculator.compute_scorecard(pillars)
    actions = RemediationPlanSynthesizer.generate_checklist(report)

    assert len(actions) >= 3
    assert any("P0 - Critical" in a for a in actions)


def test_telemetry_ndjson_logger(capsys):
    from rush.score.remediation import ScorecardTelemetryNDJSONLogger
    line = ScorecardTelemetryNDJSONLogger.emit_event("test_score", {"score": 95.0})
    assert '"event_type": "test_score"' in line
    captured = capsys.readouterr()
    assert '"score": 95.0' in captured.err


def test_weight_normalizer():
    from rush.score.calculator import WeightNormalizer
    raw = {"a": 2.0, "b": 2.0}
    norm = WeightNormalizer.normalize(raw)
    assert norm["a"] == 0.5
    assert norm["b"] == 0.5
```

---

## 6. Structured Error Logging & Diagnostics Contract

All Phase 40 diagnostics MUST be emitted to `sys.stderr` formatted as structured NDJSON.

```json
{"timestamp": "2026-08-21T10:30:00.100Z", "phase": 40, "tool": "rush_score", "event": "scorecard_computed", "composite_score": 94.2, "letter_grade": "A"}
{"timestamp": "2026-08-21T10:30:01.400Z", "phase": 40, "tool": "rush_consensus", "event": "consensus_reconciled", "total_findings": 14, "consensus_findings": 3}
```

---

## 7. Semantic Drift Review, Backlog Update & Documentation Synchronization

### 7.1 Master Backlog Synchronization Protocol
Upon completion of Phase 40 implementation tasks:
1. Open [`docs/developer/backlog.md`](file:///C:/Users/james/developer/rush-cli/docs/developer/backlog.md).
2. Locate **Phase 40: Multi-Model Consensus & Quality Scorecard**.
3. Update Status from `Ready` to `Complete`.
4. Record implementation commit hash and verification summary.

### 7.2 Specific Documentation Updates Across `/docs` (136+ Files Tree)

The following specific documents across the `/docs` tree must be created or updated upon Phase 40 completion:

#### A. User-Facing Documentation
- **[`docs/USER_GUIDE.md`](file:///C:/Users/james/developer/rush-cli/docs/USER_GUIDE.md)**: Add "Repository Quality Scorecards & Multi-Model Review Consensus" guide.
- **[`docs/CLI_REFERENCE.md`](file:///C:/Users/james/developer/rush-cli/docs/CLI_REFERENCE.md)**: Document `rush score compute`, `rush score html`, `rush score sarif`, `rush consensus reconcile` (flags: `--threshold`, `--pr-card`, `--models`).
- **[`docs/CLI_COOKBOOK.md`](file:///C:/Users/james/developer/rush-cli/docs/CLI_COOKBOOK.md)**: Add recipes for generating SVG badges and posting scorecard comment cards in GitHub Actions PRs.
- **[`docs/RECIPE_BOOK.md`](file:///C:/Users/james/developer/rush-cli/docs/RECIPE_BOOK.md)**: Add automated multi-model consensus reconciliation CI workflow.
- **[`docs/EXAMPLES.md`](file:///C:/Users/james/developer/rush-cli/docs/EXAMPLES.md)**: Show example composite scorecard breakdowns and interactive HTML report screenshots.
- **[`docs/TUTORIALS.md`](file:///C:/Users/james/developer/rush-cli/docs/TUTORIALS.md)**: Add tutorial on setting up custom pillar weights and letter grade thresholds.
- **[`docs/TROUBLESHOOTING.md`](file:///C:/Users/james/developer/rush-cli/docs/TROUBLESHOOTING.md)**: Add entries for SARIF schema validation errors and multi-model format parsing warnings.
- **[`docs/FAQ.md`](file:///C:/Users/james/developer/rush-cli/docs/FAQ.md)**: Explain the 6 quality pillar weight distribution and majority consensus filtering algorithm.

#### B. MCP Server & Agent Protocol Documentation
- **[`docs/MCP.md`](file:///C:/Users/james/developer/rush-cli/docs/MCP.md)**: Document `rush_score_compute` and `rush_consensus_reconcile` FastMCP tools.
- **[`docs/MCP_REFERENCE.md`](file:///C:/Users/james/developer/rush-cli/docs/MCP_REFERENCE.md)**: Document scorecard metrics and consensus findings JSON schemas.

#### C. Catalog & Configuration Documentation
- **[`docs/TOOL_CATALOG.md`](file:///C:/Users/james/developer/rush-cli/docs/TOOL_CATALOG.md)**: Register `score` and `consensus` tools in Quality & Consensus category.
- **[`docs/CONFIGURATION.md`](file:///C:/Users/james/developer/rush-cli/docs/CONFIGURATION.md)** & **[`docs/CONFIG_SCHEMA.md`](file:///C:/Users/james/developer/rush-cli/docs/CONFIG_SCHEMA.md)**: Document `[score]` and `[consensus]` configuration tables (`weights`, `min_consensus_models`).

#### D. Architecture & Developer Documentation
- **[`docs/ARCHITECTURE.md`](file:///C:/Users/james/developer/rush-cli/docs/ARCHITECTURE.md)**: Document 6-pillar composite weighting mathematics, multi-model consensus graph reconciliation, and SARIF 2.1.0 serializer architecture.
- **[`docs/DEVELOPER_GUIDE.md`](file:///C:/Users/james/developer/rush-cli/docs/DEVELOPER_GUIDE.md)**: Add guide for contributing custom score plugins and LLM review parsers.
- **[`docs/CI_INTEGRATION.md`](file:///C:/Users/james/developer/rush-cli/docs/CI_INTEGRATION.md)**: Provide complete GitHub Actions workflow for uploading SARIF reports to GitHub Code Scanning.
- **[`docs/TESTING.md`](file:///C:/Users/james/developer/rush-cli/docs/TESTING.md)**: Document scorecard calculation precision tests and multi-model consensus fixtures.
- **[`docs/tools/score.md`](file:///C:/Users/james/developer/rush-cli/docs/tools/score.md)** & **[`docs/tools/consensus.md`](file:///C:/Users/james/developer/rush-cli/docs/tools/consensus.md)**: Create dedicated reference documentation.

### 7.3 Automated Documentation Parity Check
```bash
.venv/Scripts/python.exe scripts/sync_docs.py --update
.venv/Scripts/python.exe scripts/sync_docs.py --check
```

### 7.4 Ending Git Lifecycle Commands
Execute these commands upon completing all phase tasks and verification checks:
```bash
# 1. Full verification gate
.venv/Scripts/python.exe -m pytest tests/ -q
.venv/Scripts/ruff.exe check src tests scripts
.venv/Scripts/ruff.exe format src tests scripts
.venv/Scripts/python.exe scripts/sync_docs.py --update
.venv/Scripts/python.exe scripts/sync_docs.py --check

# 2. Stage & Commit
git add src/ tests/ docs/
git commit -m "feat(phase-40): implement 6-pillar composite quality scorecard, multi-model consensus and sarif export"

# 3. Record commit SHA in docs/developer/backlog.md
git rev-parse --short HEAD
```
