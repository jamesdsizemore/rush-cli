"""Autonomous agent skill synthesizer for plugins."""

from __future__ import annotations

import time
import uuid

from rush.plugins.loader import PluginSpec


class AgentSkillGenerator:
    """Generates standard SKILL.md documentation for dynamic agent plugins."""

    @staticmethod
    def generate_skill_markdown(plugin: PluginSpec) -> str:
        # Imported locally (not module-level) to avoid a circular import: rush.plugins.__init__
        # eagerly imports this module, and rush.memory.store's own import chain (via
        # rush.hook -> rush.tools -> rush.continuity -> rush.memory.checkpoint_journal ->
        # rush.memory.migration) circles back to rush.memory.store itself. Importing rush.hook
        # first (pre-existing, independent of this file) resolves the ordering: once rush.hook is
        # registered in sys.modules, rush.memory.store's own `from rush.hook.trojan_source import
        # BIDI_CHARS` resolves as a plain submodule lookup instead of re-entering the cycle.
        import rush.hook  # noqa: F401
        from rush.memory.store import MemoryArtifact, TypedArtifactStore
        from rush.plugins.trust_store import PluginTrustStore

        closure_digest = plugin.closure.closure_digest if plugin.closure else None
        TypedArtifactStore().write(
            MemoryArtifact(
                id=str(uuid.uuid4()),
                family="skill",
                subject="skill_pattern",
                trust_tier="DERIVED",
                content={
                    "plugin_name": plugin.name,
                    "description": plugin.description,
                    "closure_digest": closure_digest,
                },
                source="skills_generator:generate_skill_markdown",
                created_at=time.time(),
                promoted_at=None,
            )
        )

        trusted = plugin.closure is not None and PluginTrustStore().is_trusted(
            plugin.name, plugin.closure.closure_digest
        )

        header = f"""---
name: {plugin.name}
description: {plugin.description or f"Custom Rush plugin for {plugin.name}"}
toolAction: Running {plugin.name}
toolSummary: {plugin.name} verification
---

# {plugin.name} Agent Skill

## Overview
This skill executes the custom project plugin `{plugin.name}` verified by Rush's cryptographic trust store.
"""
        if not trusted:
            return header

        execution = f"""
## Execution
Run the following tool command:
```bash
rush plugin run {plugin.name} <targets>
```
"""
        return header + execution
