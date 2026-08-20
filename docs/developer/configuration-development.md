# Configuration development

Discovery begins at a file's parent or directory target, walks upward, selects the first `rush.toml`, and stops at `.git` or filesystem root. Multiple configs are not merged.

To add a field:

1. Place it in the owning frozen dataclass with a safe default.
2. Parse and type-normalize it in `_parse`; reject wrong types rather than coercing silently.
3. Add a consumer in a specific tool; do not ship parsed no-op policy.
4. Define precedence: default < TOML < explicit invocation option.
5. Add discovery, boundary, parse, precedence, unknown-value, and behavior tests.
6. Update configuration reference, cookbook, example config, environment docs if relevant, and migration notes.

`[tools.NAME]` validation must remain catalog-driven so typos fail. Permission-sensitive actions should not become persistent blanket grants through configuration without a separate security decision.
