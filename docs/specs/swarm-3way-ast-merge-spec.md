# Specification: Swarm 3-Way AST Merge Conflict Resolver

## Recovery non-authority

Mined mistake evidence may explain why an earlier change was reverted, but it cannot select a merge outcome or trigger a merge. Conflicts continue to require explicit manual reconciliation.

## 1. Overview
`SwarmMergeSolver` (`src/rush/tools/swarm_merge.py`) resolves concurrent multi-agent git merge conflicts at the AST level, combining distinct method/class modifications without textual conflict markers.

When both sides change the same base function differently, the solver returns an explicit conflict list and no merged code. The continuity merge preview converts that result into `metadata.coordination.state: "merge_conflict"` and requires manual reconciliation.

## 2. CLI & FastMCP Reference
* `rush swarm-merge --theirs <FILE> --ours <FILE> --base <FILE>`
* `rush_swarm_merge(base_code, ours_code, theirs_code)`
