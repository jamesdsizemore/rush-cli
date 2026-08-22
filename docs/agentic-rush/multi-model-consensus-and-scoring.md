# Multi-Model Consensus & Quality Scorecards

Single AI model reviews suffer from blind spots and hallucinations: Claude might catch a tricky async race condition but miss an edge case in SQL syntax; GPT-4o might flag a potential security risk that turns out to be a false positive; local models might provide fast feedback but lower reasoning depth.

Rush’s **Consensus & Scorecard Subsystem** (`rush consensus`, `rush score`) reconciles findings across multiple AI models and computes a deterministic, 6-pillar repository quality scorecard.

---

## 1. Multi-Model Consensus Reconciliation

The `rush consensus reconcile` engine collects review outputs from multiple AI models (Claude 3.7 Sonnet, GPT-4o, Gemini 2.5 Pro, local DeepSeek/Ollama models) and performs weighted agreement voting:

```mermaid
flowchart TD
    Claude["Claude 3.7 Review Findings"] --> Consensus["Weighted Agreement Consensus Filter"]
    GPT["GPT-4o Review Findings"] --> Consensus
    Gemini["Gemini 2.5 Review Findings"] --> Consensus
    Consensus --> Filtered["High-Confidence Verified Findings (Hallucinations Removed)"]
```

```bash
# Reconcile multi-model AI findings from JSON reports
rush consensus reconcile --inputs claude_review.json gpt_review.json gemini_review.json
```

- **Filters Out Hallucinations**: If only one model flags a non-existent issue and cannot point to an exact AST rule or compiler violation, the finding is weighted down or discarded.
- **Amplifies High-Risk Vulnerabilities**: When multiple independent models agree on a flaw, its severity is elevated to `fail` or `critical`.

---

## 2. The 6-Pillar Repository Health Scorecard

The `rush score compute` command evaluates your repository across 6 deterministic pillars to generate an objective health score (0–100%) and letter grade (A+ to F):

```bash
# Compute comprehensive repository health score
rush score compute
```

### The 6 Pillars:
1. **Type Safety (20%)**: Type coverage ratio, strict mode conformance (`mypy`, `tsc`).
2. **Test Coverage (20%)**: Line & branch coverage percentage (`pytest`, `vitest`).
3. **Code Health (20%)**: Clean linting, low cyclomatic complexity (`ruff`, `eslint`, `radon`).
4. **Security & Secrets (20%)**: Zero vulnerabilities and clean secret scans (`gitleaks`, `semgrep`).
5. **Token Economy (10%)**: Clean AST density and optimized prompt context readiness.
6. **Governance & Docs (10%)**: Full `AGENTS.md` and documentation parity.

---

## 3. Visual Artifacts & SVG Badges

Rush can export your quality scorecard into visual formats for pull requests, dashboards, and README badges:

```bash
# Generate SVG badge for README
rush score badge --output docs/badges/quality-score.svg

# Generate markdown summary card for GitHub Pull Requests
rush score pr-card
```

---

## Next Steps

- Learn how to extend Rush with custom tools in [Plugins & Agent Skills](plugins-and-agent-skills.md).
- Explore the core user guide in [Everyday Workflow](../user-guide/everyday-workflow.md).
