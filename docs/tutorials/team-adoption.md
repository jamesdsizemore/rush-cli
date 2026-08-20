# Tutorial: adopt Rush as a team

**Outcome:** introduce Rush without surprising developers or overloading CI.

1. Trial Rush on one representative repository.
2. Choose a small required set: usually review, lint, format-check, test, and dependency security.
3. Record required optional engines and ownership.
4. Add project settings only where the current implementation consumes them.
5. Define how `warn` and `skipped` are handled; exit code alone is insufficient for mandatory checks.
6. Add bounded CI jobs and a troubleshooting owner.
7. Expand to content, infrastructure, or supply-chain checks after measuring usefulness.

**Expected:** a documented, explainable policy—not every catalog command installed everywhere.

**Next:** [Configuration cookbook](../reference/configuration-cookbook.md) and [CI overview](../integrations/ci-overview.md).
