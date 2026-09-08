# Shipping with Swagger: From Vibes to Production Release

Vibecoding is fast, but real swagger comes from shipping software that is **indisputably rock-solid**.

When you open a Pull Request or push a release, you don't just want to say *"it worked on my machine."* You want to back up your code with objective quality scores, verified test results, and professional artifacts.

Here is how Rush helps you ship with swagger.

---

## 1. The 6-Pillar Repository Health Scorecard

```bash
uv run rush score compute
```

Rush calculates an objective, deterministic 0–100% health score and letter grade (A+ to F) across 6 key pillars:

```text
============================================================
                   RUSH QUALITY SCORECARD
============================================================
  Overall Health:       96.4% (Grade: A+)

  [P1] Type Safety:     100.0% (mypy: 0 errors)
  [P2] Test Coverage:    94.2% (pytest: 682/682 passed)
  [P3] Code Health:      98.0% (ruff: 0 lint errors)
  [P4] Security:        100.0% (0 secrets / 0 vulnerabilities)
  [P5] Token Economy:    92.0% (clean AST density)
  [P6] Governance:      100.0% (AGENTS.md in full parity)
============================================================
```

---

## 2. Computing repository score (`rush score compute`)

When opening a pull request, capture the score output as evidence:

```bash
uv run rush score compute
```

`score compute` does not generate a PR card or prove every listed engine executed. Include only observed score inputs and separate executed test/security evidence.

---

## 3. Release version parity (`rush release check`)

When you are ready to cut a new release tag or publish a package:

```bash
# Check current version parity
uv run rush release check
```

Current `release` group exposes only `check`; it does not generate a changelog, tag, or publish a package.

---

## 4. Badge status

Current `score` group exposes only `compute`; it does not generate an SVG badge. Keep the badge requirement separate until an implemented command and artifact test exist.


---

## Next Steps

- Grab ready-to-copy AI prompt templates in [Vibecoder Cheat Sheet & Golden Prompts](cheat-sheet.md).
- Explore the complete [Agentic Rush Knowledge Base](../AGENTIC_RUSH.md).
