# Tutorial: check a mixed-language repository

**Outcome:** run one command per intent while keeping optional runtimes bounded.

**Prerequisites:** Rush and at least two supported project markers, such as `pyproject.toml` and `package.json`.

1. Install only the engines required by repository policy.
2. Run `rush lint . --json` and inspect the combined `engine` label and finding provenance.
3. Repeat for `typecheck`, `test`, and `security`.
4. Record which `skipped` engines are intentional and which are setup gaps.
5. In CI, split jobs by ecosystem rather than constructing one giant all-runtime image.

**Expected:** applicable results aggregate in stable order; the worst status wins. Missing optional engines remain explicit.

**Next:** [CI integration](ci-integration.md).
