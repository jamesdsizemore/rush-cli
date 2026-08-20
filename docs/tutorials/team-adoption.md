# Tutorial: Adopting Rush Across an Engineering Team

**Goal:** Roll out Rush across an engineering organization smoothly without disrupting developer velocity or breaking existing CI builds.

---

## 1. 4-Stage Rollout Strategy

```text
Stage 1: Local Developer Pilot -> Install Rush locally and test CLI commands beside existing scripts.
Stage 2: Standardize Pre-Commit -> Add rush review and rush lint to Git hooks.
Stage 3: CI Quality Gate -> Add single-step Rush verification jobs in GitHub Actions/GitLab CI.
Stage 4: AI Agent Enablement -> Connect Rush FastMCP stdio server to Cursor, Windsurf, or Claude Code.
```

---

## 2. Adoption Best Practices

1. **Keep Engine Roster Bounded**: Only install the engines needed for your team's languages. Do not mandate all 121 engines in developer onboarding.
2. **Start with Non-Mutating Checks**: Introduce `rush format . --check` and `rush lint .` before introducing deeper AST rules or mutation testing.
3. **Establish CI Policy for `skipped`**: Ensure CI flags missing engines as policy violations if those engines are designated mandatory.

See [First 10 Minutes](first-10-minutes.md) and [Configuration Cookbook](../reference/configuration-cookbook.md).
