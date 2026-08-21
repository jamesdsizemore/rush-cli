"""Autonomous agent skill synthesizer for plugins."""

from __future__ import annotations

from rush.plugins.loader import PluginSpec


class AgentSkillGenerator:
    """Generates standard SKILL.md documentation for dynamic agent plugins."""

    @staticmethod
    def generate_skill_markdown(plugin: PluginSpec) -> str:
        return f"""---
name: {plugin.name}
description: {plugin.description or f"Custom Rush plugin for {plugin.name}"}
toolAction: Running {plugin.name}
toolSummary: {plugin.name} verification
---

# {plugin.name} Agent Skill

## Overview
This skill executes the custom project plugin `{plugin.name}` verified by Rush's cryptographic trust store.

## Execution
Run the following tool command:
```bash
rush plugin run {plugin.name} <targets>
```
"""
