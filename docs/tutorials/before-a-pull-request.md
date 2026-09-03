# Tutorial: use Rush before every pull request

**Outcome:** produce a repeatable local evidence bundle before opening a pull request.

1. Start from a clean understanding of your Git diff.
2. Enforce TDD compliance and run quality checks:
   ```bash
   rush tdd .
   rush review . --export-html artifacts/pr-review.html
   rush lint .
   rush format . --check
   rush complexity .
   rush slop .
   rush test .
   rush security .
   ```
3. Add focused project checks where relevant:
   ```bash
   rush markdown .
   rush actions .
   rush secrets .
   rush coverage . --allow-slow
   ```
4. Treat a required `skipped` result as incomplete setup.
5. Attach the generated `artifacts/pr-review.html` or SARIF artifact to the PR summary.

**Expected:** no source rewrite from checks; format remains check-only. Rush does not open the PR or claim human review.

**Next:** [Team adoption](team-adoption.md).

## Step 5: Run Pre-Flight Ship Gate (`rush ship gate`)

Run Rush's 7-vector release readiness cockpit to verify scratch cleanliness, environment declarations, doc links, migration safety, and SemVer compatibility:
```bash
rush ship gate
```
If any vector fails, inspect the diagnostic output and remediate before opening your pull request.

## Step 6: Check Blast Radius and Architecture Boundaries
Run `rush blast-radius --path <file>` and `rush arch-guard` to verify no downstream routes are broken and layer boundaries are clean.



## Step 7: Check API Contract Parity
Run `rush api-diff --base main` to guarantee backward compatibility before opening a PR.



## Step 8: Check Database Drift and Complexity
Run `rush db-drift` and `rush simplify` to guarantee clean migrations and modular architecture.



## Step 9: Verify Traceability and Local CI
Run `rush trace` to ensure 100% requirement coverage and `rush simulate-ci` to verify CI pass status.



## Step 10: Run Quality & Security Checks (Phase 50a)
Run `rush error-catalog .`, `rush license-matrix .`, and `rush iam-audit .` to audit exceptions, copyleft dependencies, and cloud IAM policies before opening your PR.

## Step 11: Verify Attribution & Generate Semantic PR Card (Phase 50b)
Run `rush provenance-ai .`, `rush dead-asset .`, and `rush pr-synthesize .` to generate a verifiable PR card with risk tiering and CODEOWNERS routing:
```bash
rush pr-synthesize . --export-path artifacts/PR_CARD.md --allow-artifact-write
```

## Step 12: Generate Build Attestation (Phase 50c)
Run `rush pr-synthesize` and `rush attest` to complete the pre-flight release checklist.

