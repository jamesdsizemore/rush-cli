# Rush configuration

Use [`reference/configuration-reference.md`](reference/configuration-reference.md) for the exact fields and implementation notes, and [`reference/configuration-cookbook.md`](reference/configuration-cookbook.md) for complete examples.

Rush configuration is optional. Discovery starts at the target, walks upward, and stops at the Git root. Built-in defaults are overridden by the nearest `rush.toml`, then explicit CLI arguments.

> Not every parsed field is currently consumed by every tool. The reference labels verified consumers so teams do not build policy on a no-op setting.
