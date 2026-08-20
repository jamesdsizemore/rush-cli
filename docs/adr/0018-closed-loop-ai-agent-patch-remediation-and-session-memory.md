# ADR-0018: Closed-Loop AI Agent Patch Remediation and Session Context Memory

## Status
Accepted

## Context
Coding agents interacting with Rush over MCP receive diagnostic findings but must infer how to apply code modifications, often hallucinating syntax or consuming excessive conversational turns. Additionally, long-running agent tasks suffer from context degradation across multiple sessions.

## Decision
1. Augment `ToolFinding` with optional machine-readable unified diff patches in `patch` and `suggested_fix`.
2. Implement a local Session Memory Ledger in `.rush/session_memory.json` tracking historical tool findings, resolution status, context token consumption, and established architectural patterns.
3. Expose dedicated FastMCP agent tools: `rush_get_patch`, `rush_apply_fix`, and `rush_session_context`.

## Consequences
- Fast, single-turn AI agent problem remediation.
- Reduced model token consumption and hallucination.
- Persistent session memory preventing repetitive mistakes during long-running tasks.
