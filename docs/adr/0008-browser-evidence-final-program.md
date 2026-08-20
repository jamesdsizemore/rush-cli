# ADR 0008: Browser evidence is the final program

## Context
Browser runtimes add downloads, live targets, and a distinct safety boundary.

## Decision
Browser/UI/UX/accessibility/visual/E2E/DAST work is Phase 08 only, after Phases 00–07 acceptance and fresh user approval.

## Rejected alternatives
Early Playwright, Lighthouse, axe browser flow, screenshot, DOM, or runtime dependency work was rejected.

## Consequences
`semantic-drift` remains explicitly browser-runtime maturity; no earlier phase may introduce browser dependencies.

## Compatibility and operations
Preserves existing guarded behavior and prevents accidental runtime downloads.
