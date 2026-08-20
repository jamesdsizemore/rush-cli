# Examples

```bash
# Human review
rush review .

# Machine-readable lint
rush lint src --json

# Check formatting without writing
rush format . --check

# Focused project files
rush markdown docs
rush actions .github/workflows
rush iac infra

# Supply-chain checks
rush security . --json
rush secrets . --json

# Local assistant server
rush mcp serve
```

Every example requires an existing path. Missing engines return `skipped`. See [Recipe book](RECIPE_BOOK.md) and [Tutorials](TUTORIALS.md) for explained outcomes.
