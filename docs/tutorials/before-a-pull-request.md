# Tutorial: use Rush before every pull request

**Outcome:** produce a repeatable local evidence bundle before review.

1. Start from a clean understanding of your Git diff.
2. Run:
   ```bash
   rush review .
   rush lint .
   rush format . --check
   rush test .
   rush security .
   ```
3. Add focused project checks where relevant:
   ```bash
   rush markdown .
   rush actions .
   rush secrets .
   ```
4. Treat a required `skipped` result as incomplete setup.
5. Rerun after repairs and summarize the actual commands/results in the PR.

**Expected:** no source rewrite from checks; format remains check-only. Rush does not open the PR or claim human review.

**Next:** [Team adoption](team-adoption.md).
