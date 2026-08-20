# Configuration schema

Rush uses a small TOML dataclass model rather than a published JSON Schema. The authoritative field, default, validation, discovery, precedence, and consumer notes are in [Configuration reference](reference/configuration-reference.md). Unknown `[tools.NAME]` entries fail against the catalog.
