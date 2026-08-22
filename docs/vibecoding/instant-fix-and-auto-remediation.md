# Instant Fix & Auto-Remediation

Nothing ruins a great vibecoding flow state like getting bogged down in trivial formatting errors: missing trailing commas, inconsistent double quotes, unsorted imports, or trailing whitespace.

Instead of typing manual fixes or wasting expensive LLM prompts asking the AI to reformat a file, Rush gives you **one-click automated remediation** with `rush fix`.

---

## 1. How `rush fix` Works

```bash
# Preview what Rush will clean up (safe, non-destructive preview)
rush fix . --dry-run

# Apply the safe fixes automatically across all files
rush fix .
```

When you run `rush fix .`, Rush orchestrates the best automated formatters and fixers installed in your environment:
- **Python**: Invokes `Ruff` to format code, sort imports (`I001`), and clean unused variables.
- **JavaScript & TypeScript**: Invokes `Prettier`, `ESLint`, and `Biome` to standardize style, format JSX/TSX, and resolve linting rules.
- **HTML / Templates**: Invokes `djLint` to tidy template indentation.

---

## 2. Safe & Confined by Design

Automated tools that modify code must be trustworthy. Rush enforces strict safety boundaries during all auto-remediation:

1. **Git Working Tree Protection**: `rush fix` checks that your current Git state is safe before making changes (pass `--force` to override).
2. **Strict Path Confinement**: Fixes are strictly confined inside your repository root—Rush will never touch files outside your workspace.
3. **Non-Destructive AST Rules**: Only safe, deterministic transformations are applied; Rush never rewrites complex logic or deletes meaningful code.

---

## 3. Automated Live Remediation with `rush watch`

To make formatting 100% effortless, start the live watcher at the beginning of your coding session:

```bash
rush watch .
```

Whenever you or your AI agent save a file, Rush instantly runs a fast check. If any minor formatting or import issue is spotted, you can run `rush fix .` in a separate terminal split and be back in your flow in under 2 seconds.

---

## Next Steps

- Learn how to compress code prompts in [Token Diet for Vibecoders](token-diet-for-vibecoders.md).
- Discover how to generate PR scorecards in [Shipping with Swagger](shipping-with-swagger.md).
