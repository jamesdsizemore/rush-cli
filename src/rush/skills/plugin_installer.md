# AI Agent Skill: Rush Plugin Installer

## Description
Guides AI coding agents through installing and verifying third-party or internal plugins into a repository.

## Installation Steps
1. Place plugin executable or script under `scripts/` or `.rush/plugins/`.
2. Add plugin definition table to `rush.toml`:
```toml
[plugins.<plugin_name>]
command = "<interpreter> <path_to_script>"
description = "<one line description>"
```
3. Run `rush trust .` to approve the local repository trust ledger.
4. Execute `rush plugin run <plugin_name>` to verify execution and schema output.
