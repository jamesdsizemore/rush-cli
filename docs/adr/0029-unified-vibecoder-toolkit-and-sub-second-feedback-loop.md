# ADR-0029: Unified Vibe-Coder Toolkit and Sub-Second Feedback Loop

## Status
Accepted (v0.2.0)

## Context
High-velocity "vibe-coding" with AI agents often accumulates dead code, async event loop blocking calls, environment variable drift, and type desynchronizations without developer awareness.

## Decision
1. Unify 22 specialized quality, synchronization, and remediation tools under the `rush vibecoder` CLI and FastMCP catalog.
2. Implement `VibeFeedbackSupervisor` to provide immediate (<100ms) syntax, async loop starvation, and `.env.example` validation on newly edited files.
3. Provide `DatabaseSchemaDriftDetector` and `PackageLockfileGuard` to ensure full-stack contract integrity during rapid AI prompt cycles.
4. Implement `VibePromptHistoryLogger` to track prompt evolution and correlate prompts with modified AST nodes.

## Consequences
- **Positive**: Prevents AI slop accumulation, ensures instant developer feedback, maintains full-stack synchronization.
- **Negative**: Adds CLI namespace `rush vibecoder` requiring catalog documentation synchronization.
- **Safety**: Fully offline execution, zero stdout stream pollution, hardened subprocess execution.
