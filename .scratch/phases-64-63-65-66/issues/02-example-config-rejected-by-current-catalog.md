# Example configuration contains undeclared prompt-eval options

Status: ready-for-agent

## Evidence

Parsing `examples/rush.toml` with `rush.config._parse` fails with `RushConfigError: unknown option 'max_tokens' for tool 'prompt-eval'`. The same `max_tokens` and `max_cost` entries exist at pre-P64-08 commit `f212bcf`.

## Intervention assessment

Separate correction required: reconcile existing example options against current executable catalog and validate the whole example. Blocks copying the complete example as a working configuration; does not block the independently validated mutation table. Outside P64-08 mutation scope; no unrelated option changed.
