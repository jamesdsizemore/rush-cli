# Shipping with Swagger: From Vibes to Production Release

Vibecoding is fast, but real swagger comes from shipping software that is **indisputably rock-solid**.

When you open a Pull Request or push a release, you don't just want to say *"it worked on my machine."* You want to back up your code with objective quality scores, verified test results, and professional artifacts.

Here is how Rush helps you ship with swagger.

---

## 1. The 6-Pillar Repository Health Scorecard

```bash
rush score compute
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

## 2. Generating GitHub PR Cards (`rush score pr-card`)

When opening a Pull Request, generate a clean markdown summary to paste into your PR description:

```bash
rush score pr-card
```

### Generated PR Card:
```markdown
### 🛡️ Rush Quality Verified (Grade: A+)
- **Tests**: 682 passed, 0 failures (100% green)
- **Linting & Formatting**: 100% compliant with Ruff & Prettier
- **Security & Secrets**: 0 vulnerabilities detected
- **Documentation**: All documentation verified in full parity
```

Reviewers and teammates will be blown away by the clarity and rigor of your submission.

---

## 3. Automated Changelog & Semver (`rush release`)

When you are ready to cut a new release tag or publish a package:

```bash
# Calculate next semver version and preview changelog
rush release . --dry-run
```

Rush inspects your commit history, groups changes by Conventional Commit types (`feat`, `fix`, `docs`), and formats an updated `CHANGELOG.md` entry automatically.

---

## 4. Visual README Badges

Add a dynamic SVG quality badge to your repository's README:

```bash
rush score badge --output badges/quality.svg
```

You can embed the generated badge directly in your `README.md` to showcase your repository's test coverage and health grade.


---

## Next Steps

- Grab ready-to-copy AI prompt templates in [Vibecoder Cheat Sheet & Golden Prompts](cheat-sheet.md).
- Explore the complete [Agentic Rush Knowledge Base](../AGENTIC_RUSH.md).
