Current status: historical decision; Current tools are exposed through the registered command tree, not a `rush vibecoder` namespace. The 22-tool count, latency, and comprehensive integrity guarantees below are historical; current drift/profile/analysis defects are recorded in [application review F15–F23](../reports/phase-64-66-application-review.md). [Phase 64](../phase-plans/phase-64-runtime-correctness-and-safe-execution-plan.md) and [Phase 65](../phase-plans/phase-65-project-provisioning-scan-and-agent-workflow-plan.md) preserve the corrective workflow requirements.

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
