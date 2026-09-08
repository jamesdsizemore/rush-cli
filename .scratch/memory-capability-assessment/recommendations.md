# Memory capability assessment

Source: `997b56e`, branch `codex/phase-61-62-review-fixes`. Assessment only; no runtime changes or new implementation approval. Scope: Rush's typed memory store, retrieval, context cache, existing token utilities and cross-provider delivery.

**Recommendation: make recall selective, connect records through explicit evidence, and hand off only the relevant changes.** These improvements address observed behavior without requiring another database or an embedding service. Their savings remain unmeasured; the checks below define how to establish them.

## Current evidence

- [Store search](/Users/jamesdsizemore/Developer/rush-cli-worktrees/phase-61-62-review-fixes/src/rush/memory/store.py:290) already uses FTS5/BM25, but fetches every matching full row. [MemoryTool query](/Users/jamesdsizemore/Developer/rush-cli-worktrees/phase-61-62-review-fixes/src/rush/tools/memory.py:171) returns every recalled artifact in full, without a result or token budget.
- [Defended recall](/Users/jamesdsizemore/Developer/rush-cli-worktrees/phase-61-62-review-fixes/src/rush/memory/store.py:306) filters permitted sources after search, then checks integrity, unsafe characters and source freshness. [Cache lookup](/Users/jamesdsizemore/Developer/rush-cli-worktrees/phase-61-62-review-fixes/src/rush/token_economy/memory_cache_gate.py:45) and [review citations](/Users/jamesdsizemore/Developer/rush-cli-worktrees/phase-61-62-review-fixes/src/rush/tools/review.py:95) first search, then invoke recall, repeating the search.
- [Artifacts](/Users/jamesdsizemore/Developer/rush-cli-worktrees/phase-61-62-review-fixes/src/rush/memory/store.py:48) carry IDs, origins, source references and trust metadata. Those provide useful foundations for relationships; they do not themselves provide indexed relationship traversal.
- [CCRStore](/Users/jamesdsizemore/Developer/rush-cli-worktrees/phase-61-62-review-fixes/src/rush/token_economy/ccr_store.py:33) already stores content by hash and supports exact restoration. Reuse its storage mechanics where appropriate, but retrieval of a hash must still enforce the memory artifact's access and validation rules.
- [Transport](/Users/jamesdsizemore/Developer/rush-cli-worktrees/phase-61-62-review-fixes/src/rush/memory/transport.py:74) delivers through supported SDK/ACP routes. Existing verification proves local protocol acknowledgement, not a live provider retrieving the same memories in a later session. The indexed call graph did not establish a production caller, so complete handoff integration needs explicit end-to-end evidence.

## Priorities and tradeoffs

| Priority | Improvement | Concrete behavior | Benefit and cost |
|---|---|---|---|
| 1 | Budgeted, two-stage recall | Return a few relevant excerpts with artifact IDs, source, trust and freshness; expand selected IDs on demand. Apply source scope in the query, retrieve bounded candidate batches and fill the budget only with validated results. | Directly bounds prompt growth. Adds an expansion route and explicit pagination; premature truncation must not hide the useful authorized results. |
| 2 | Connected evidence | Add explicit relationships such as `supersedes`, `contradicts`, `caused_by`, `fixed_by` and `validated_by`. Link a failure to its repair commit, regression test and governing decision; traverse a bounded number of authorized neighbors. | Answers “why?” and “what happened next?” across sessions. A SQLite edge table is a candidate; compare with existing graph storage before choosing. Relationships need provenance and invalidation. |
| 3 | Compact cross-provider handoff | Carry the active goal, constraints, unresolved decisions, selected artifact IDs/versions and source references. Transfer only changed authorized records since the last acknowledged handoff; let the receiving session request details. | Avoids repeatedly copying full history and makes continuity explicit. Requires a real receiving route, replay-safe delivery and acknowledgement/read-back tests. Sending text alone is insufficient. |
| 4 | Incremental retrieval and cache work | Remove redundant search-before-recall calls through one defended path. Batch validation of shared source files within a request. Define cache identity using all inputs that affect the result, including source revision and output budget. | Reduces repeated SQL, file reads and parsing. Gains depend on workload; cross-request validation caches require a reliable invalidation mechanism. Freshness checks remain mandatory. |
| 5 | Evidence-based consolidation | Group duplicate episodes while preserving exact originals. Produce a compact account of repeated failure, successful repair and exceptions, linked to the underlying records. Mark superseded advice explicitly. | Makes recurring experience more useful and reduces repetitive context. Summaries can omit exceptions; repetition must never automatically grant higher trust or erase contradictory evidence. |

For priority 1, distinguish a measured model-token ceiling from an approximate budget. [FastBPETokenCounter](/Users/jamesdsizemore/Developer/rush-cli-worktrees/phase-61-62-review-fixes/src/rush/token_economy/counter.py:10) is explicitly a heuristic. Use the target tokenizer when available; otherwise label the estimate and apply a conservative byte cap. Preserve full evidence behind references rather than silently discarding it.

## Retrieval alternatives

Compare approaches on the same permitted corpus and held-out questions, using answer correctness, relevant-memory retrieval, context tokens, latency and maintenance cost.

| Approach | Strength | Limitation | Recommendation |
|---|---|---|---|
| Existing BM25 plus scope, bounded retrieval and contextual metadata | Reuses the current store; preserves exact identifier search | Cannot reliably bridge every paraphrase | First implementation candidate |
| BM25 plus explicit evidence relationships | Retrieves related causes, decisions and verified outcomes | Requires reliable links; traversal can expand context | Add bounded traversal after selective recall |
| BM25 plus embeddings and reranking | Candidate for paraphrases and conceptually similar episodes | Adds model/index lifecycle, resource use and evaluation requirements | Trial only against demonstrated lexical retrieval misses |

SQLite documents its ranked FTS5 query path and built-in snippets, making a bounded lexical baseline a concrete option. [SQLite FTS5 documentation](https://www.sqlite.org/fts5.html#sorting_by_auxiliary_function_results)

Anthropic describes adding chunk-specific context to lexical and embedding indexes, and combining retrieval methods. That supports testing contextual metadata and hybrid retrieval as alternatives; its results do not establish gains for Rush. [Contextual Retrieval](https://www.anthropic.com/engineering/contextual-retrieval)

## Measure before calling it better

Extend existing tests and benchmark surfaces with a fixed set of realistic questions and expected evidence. Include exact identifiers, paraphrases, obsolete advice, contradictory records, code edits, repeated sessions and denied sources. Compare:

1. Correct answers with the required supporting memory present.
2. Total context tokens, including follow-up expansions and handoff overhead.
3. Median and tail retrieval latency, with cold and warm caches separated.
4. Stale, superseded or unauthorized material delivered to the model.
5. Cross-provider read-back of the intended artifact IDs and versions.

[TelemetryStore](/Users/jamesdsizemore/Developer/rush-cli-worktrees/phase-61-62-review-fixes/src/rush/token_economy/telemetry.py:34) already accepts token and duration events. Its indexed caller is currently a test, and its dollar figure uses a fixed estimate. Instrument actual memory calls and label estimates; do not report that figure as observed provider billing or treat fewer tokens as success if answers get worse.

**First bounded step:** specify and evaluate budgeted recall plus exact expansion, using the existing BM25 store as the baseline. Establish that quality holds while total delivered context decreases. Then add explicit evidence links and verify one complete provider handoff. This is a recommendation for the next work package, not an assertion that those capabilities are implemented.
