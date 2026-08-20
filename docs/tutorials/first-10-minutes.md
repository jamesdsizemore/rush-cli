# Tutorial: your first 10 minutes

**Outcome:** install Rush from source, run a local review, and understand one result.

**Prerequisites:** Git, Python 3.12+, uv.

1. Clone and sync:
   ```bash
   git clone https://github.com/jamesdsizemore/rush-cli.git
   cd rush-cli
   uv sync --all-extras --frozen
   ```
2. Confirm commands:
   ```bash
   uv run rush --help
   ```
   Expected: a generated command list and `mcp` group.
3. Run review and export an interactive HTML dashboard:
   ```bash
   uv run rush review src --export-html review.html
   ```
   Expected: `ok` or `warn`, with a self-contained visual inspection report generated at `review.html`.
4. Run JSON mode:
   ```bash
   uv run rush review src --json
   ```
   Check `status`, `summary`, and `findings`.

**Explanation:** review is deterministic local Python analysis. A warning asks for judgment; it does not claim a human or model reviewed the code.

**Next:** [Python project](python-project.md) or [Before a pull request](before-a-pull-request.md).
