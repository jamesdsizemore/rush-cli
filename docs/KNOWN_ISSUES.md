# Known issues

1. Guarded advanced tools mention consent flags in summaries, but generic CLI commands do not expose those flags; they remain skipped.
2. `commit-msg` CLI has no message option, so only direct Python execution can supply a message.
3. SBOM CLI has no output-path/overwrite options although the implementation enforces them internally.
4. `release` CLI exposes no publish/confirm options; publication is intentionally unavailable.
5. `review --llm` returns deterministic stub information and does not call a provider.
6. `review.fail_on`, project path lists, and generic tool `check` configuration are parsed but not universally enforced.
7. Human renderer contains a replacement glyph for format in the current source; JSON output is unaffected.

These are documentation-visible capability gaps, not options users should guess. Track fixes through the normal issue/backlog process.
