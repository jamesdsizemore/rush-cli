# T013: Design gate for 72-T08, recorded verbatim from the goal-judge report

Below the line is the goal-judge's T013 report, copied unchanged.

## PM re-checks (run on 07775f1)

1. **F1.** `scripts/benchmarks/run.py:222` builds hypothesis text with `item.get("content", "")`. The gate cited lines 228-229. Compact recall items carry `excerpt`, not `content`, so the text is empty.
2. **F2.** `scripts/benchmarks/memory_datasets.py:215` hardcodes `ExecutionPermissions(cache_write=True)`, and `src/rush/tools/memory.py:1002` returns "retrieval=hybrid requires network."
3. **T006 routed item.** `run.py:235` reads `related_data.get("related")`.

verified-by: `grep -n 'get("content"' scripts/benchmarks/run.py` (198, 222, 237); `sed -n 213,216p scripts/benchmarks/memory_datasets.py`; `grep -n "requires network" src/rush/tools/memory.py` (1002); `sed -n 226,236p scripts/benchmarks/run.py`.

Pending owner decisions: OD-T08-1 through OD-T08-7, plus T012 D2.

Not re-run by the PM: the rest of the report. The T046 RED author re-checks the code map at HEAD (stop_if).

---

## (A) Note body for `notes/T013-design-gate-72-t08.md`

# T013: Design gate for 72-T08 (optional hybrid retrieval and paired evaluation)

A goal-judge ran this gate read-only against `07775f1`, in `/Users/jamesdsizemore/Developer/rush-cli-worktrees/phase-72`.

**Status:** approved with owner decisions OD-T08-1 to OD-T08-7 pending. The gate also depends on:
- the T012 owner decisions OD1-OD13, which are still pending;
- T004 OD-1 and OD-3, which are still pending;
- the T005 (72-T02) and T014 (72-T09) gate notes, which were not on disk when this gate ran.

T046 re-checks every mapped symbol at task start (see stop_if).

### 0. Facts this gate executed at 07775f1 (not inherited)

**F1. Every recall-based benchmark variant produces an empty hypothesis today.**
- Probe: I spied on `MemoryTool.run` and ran `run_longmemeval_case` with `run._variant_hypothesis` for `current`, `hybrid` and `linked` on both `longmemeval` records.
- Output: all six hypotheses were `''`.
- Cause, `run.py:228-229`: compact recall items have the keys `excerpt, freshness, id, relations, source, trust, version`. The code reads `item.get("content","")`, which never exists.
- Consequence: the 7-variant "comparison" and T012 B6 live-answer history (`text=<_variant_hypothesis output>`) are both empty strings.

**F2. The `hybrid` variant never runs hybrid and never even falls back.**
- `run_longmemeval_case` hardcodes `ExecutionPermissions(cache_write=True)` (`memory_datasets.py:215`), so network is off.
- `MemoryTool` therefore returns `E_PERMISSION "memory recall retrieval=hybrid requires network."` (`tools/memory.py:995-1004`). The probe captured exactly this.
- No embedding config is ever passed: `run.py:203-207` sends no `embedding_*` keys.
- No "installed embedding configuration" exists anywhere in `src`. The only source is the per-request `embedding_endpoint/model/model_digest/chunking_version` fields (`tools/memory.py:950-1012`).

**F3. The `linked` bug (routed from T006) is reproduced and is worse than reported (verified-by: PM sed -n 226,236p scripts/benchmarks/run.py shows data.get("related") at line 235).**
- `run.py:235` reads `data["related"]`, but `related_artifacts` returns `data["items"]` (`relations.py:192-260`).
- Those items carry only `id, version, kind, direction`, with no text. So even with the right key, `linked` would add nothing.

**F4. `hybrid_page` always returns `complete=True` with `next_cursor=None`** (`retrieval.py:1043-1055`). This holds even when `candidates_truncated` is true or the loop broke on limit or budget with eligible rows left. It violates "capped pool stays labeled incomplete".

**F5. Invalid vectors can be reported as hybrid success.**
- `_cosine` returns `0.0` on a dimension mismatch (`retrieval.py:779-781`), so a cached vector with a different dimension silently ranks as hybrid.
- An injected `embed_fn` bypasses `validate_embedding_response`, so NaN passes.
- A count mismatch raises an uncaught `ValueError` from `zip(strict=True)` (`retrieval.py:882`), which crashes instead of falling back.
- A timeout is indistinguishable from an unreachable engine: both become `EmbeddingEngineUnavailable(str(exc))`, as `embeddings.py:76-77` shows.

**F6. Embedding invalidation already exists.**
- The cache key is `(namespace, artifact_id, artifact_version, content_hash, model_digest, chunking_version)` (`store.py:529-539`, `get_embedding` at `1610-1636`). An edit bumps the version, and delete drops vectors (`store.py:1405`).
- Under the plan's "only if missing" condition, `store.py` is **not** needed by T08.

**F7. `sync_docs --check` is red at HEAD right now.** It reports 4 errors, `missing coverage receipt` for `notes/T003`, `T004`, `T009` and `T012`. Every file under `docs/` needs a receipt (`sync_docs.py:469-481`), including JSON.

**F8. Baselines.**
- `tests/test_memory_hybrid.py` plus `tests/test_benchmark_memory_datasets.py`: 17 passed.
- The product_digest command (T014 §3.2 form) runs and reports 527 files at HEAD.
- `ollama` is at `/opt/homebrew/bin/ollama`, `codex` at `~/.local/bin/codex` and `claude` at `~/.local/bin/claude`. None of them was invoked.

### 1. Testable behavior

- **B1, eligibility first.** `hybrid_candidates` passes only rows with T01 `evaluate_artifact_visibility(...).visible ∧ usable_as_current` to `embedding_text` or `embed_fn`. Rows that are archived, expired, foreign-owner (declared owner), integrity-mismatched, stale or unknown-source, or outside the allowlist never reach the embedder. The spy sees exactly the eligible texts plus the query.

**B2, precise lexical fallback.** Every unavailable case returns:
- `code="E_EMBEDDING_UNAVAILABLE"`, `retrieval="lexical"` and `embedding_status="skipped"`;
- the existing `hybrid_unavailable_reason` text, with `"no embedding engine configured"` unchanged;
- a new `embedding_fallback_code`;
- items equal to `recall_page` for the same request.

The fallback codes, exact:

| Code | Trigger |
|---|---|
| `no_engine_configured` | No embedding config |
| `network_not_granted` | Network permission off (OD-T08-1) |
| `engine_unavailable` | Connection or URL failure |
| `engine_timeout` | `TimeoutError`, or `URLError` whose `.reason` is a `TimeoutError` |
| `invalid_vectors` | NaN or infinite values, empty vector, zero norm, count mismatch, or inconsistent dimension across cached, fresh and query vectors |

A fallback is never labeled `hybrid`.

- **B3, success labels.** A hybrid success page adds `embedding_status="used"` and `embedding_fallback_code=None`.
- **B4, honest completeness.** A hybrid page is `complete=True` only if `candidates_truncated` is false and every fused eligible row was considered. Otherwise it is `complete=False` with `next_cursor=None` and `incomplete_reason`:
  - `candidate_cap` when the 512-candidate cap was hit;
  - `page_limit_no_cursor` when `limit` cut the page;
  - `budget_no_cursor` when the byte or token cap cut it.

  No hybrid cursor is added. A 513-row pool reports `candidate_cap`.
- **B5, cost.** Every hybrid page, success or fallback, carries `embedding_cost`:
  - `batches = ceil(missing/32) + (1 if query embedded)`;
  - `embedded_chunks`, `cache_hits`;
  - `input_tokens` (cl100k over the texts sent) and `input_tokens_basis="local_estimate_cl100k_base"`;
  - `embedding_ms` and `retrieval_ms`, measured with a module `_clock = time.perf_counter` that tests patch.

  Unavailable is not zero (C06): on a fallback before any call, `batches=0`. Page `tokens`/`bytes` stay as today.
- **B6, no stale vectors.** After an edit (new version), the old vector is never used: `cache_hits` drops to 0 for that id and the new text is embedded. The ranking reflects the new vector.
- **B7, default unchanged.** The default `retrieval` stays `lexical`. Hybrid needs explicit `retrieval:"hybrid"`, an explicit embedding config and the network grant. There is no new mandatory model or provider, and no automatic promotion.
- **B8, benchmark variant retrieval (`scripts/benchmarks/memory.py::variant_retrieval`).** It returns `VariantRetrieval(text, record)`.
  - The text is the joined item `excerpt`s (fixes F1).
  - `hybrid` passes the runner's embedding config and the runner's network grant. The record keeps `retrieval`, `embedding_status`, `embedding_fallback_code`, `hybrid_unavailable_reason`, `complete`, `incomplete_reason`, `candidates_truncated` and `embedding_cost` (fixes F2 and the T012 flag).
  - `linked` reads `data["items"]` and adds each neighbor's text through `expand` with T02 `representation:"utf8"`, concatenating slices until complete, then taking `content.text` or the JSON (fixes F3).
  - `run._variant_hypothesis` becomes a thin wrapper returning `.text`.
- **B9, runner flags.** New flags: `--embedding-endpoint`, `--embedding-model`, `--embedding-model-digest`, `--embedding-chunking-version` (default `mc12-v1`) and `--allow-embedding-network`. Validation runs before any spawn, ingestion or network, with these exact messages (`main` returns 1, message on stderr):
  - `embedding configuration requires --embedding-endpoint, --embedding-model and --embedding-model-digest`
  - `--embedding-endpoint requires --allow-embedding-network`
  - `--variant raw is not supported by task kind retrieval_answer`

  Both arms of a paired run carry identical flags. Only `--variant` and `--output` differ.
- **B10, Phase 72 manifest kind `retrieval_answer`** (registered in T044's `TASK_KINDS`; evaluator `normalized_contains` v1 from `EVALUATORS`).
  - **Seeding:** each case seeds the frozen corpus into a fresh case root through real `MemoryTool` writes, as described in §3.4.
  - **Retrieval:** it runs the arm strategy (`--variant current` = lexical/metadata BM25 route; `hybrid`). It also runs all three retrieval strategies deterministically for metrics: `lexical`, `metadata` and `hybrid`. `metadata` is the legacy `list` route with subject, allowlist, declared owner and freshness `fresh`, no query, first k.
  - **Live history:** it sends T012 schema-1 history `[{"source":"variant_retrieval","variant":v,"text":...}]`, the same shape in both arms. Labels go only into the report.
  - **No leaks:** the request never contains `answer`, `relevant_keys`, any corpus `key` or any `role`. Content is written as `{"text":...}` only.
- **B11, per-case `retrieval` record.**
  - Strategy: `strategy`, `retrieval_label`, `embedding_status`, `fallback_code`, `fallback_reason`, `complete`, `incomplete_reason`, `candidates_truncated`.
  - Results: `k=8`, `returned_keys`, `judged_relevant_keys`, `recall_at_k` (judged relevant returned / judged relevant total), `false_inclusion_count`/`_rate`, `unauthorized_inclusion_count` (denied_owner and revoked_source keys), `stale_inclusion_count` (stale_hash keys).
  - Cost: `retrieval_ms`, `page_tokens`, `page_bytes`, `embedding_cost`.
  - `strategies{lexical,metadata,hybrid}`, each with the same fields.
  - `dataset_answer` cases also get the label, fallback, completeness and cost subset.
- **B12, report.** `memory-suite-report.json` gains `phase72_hybrid_summary`. For each strategy and each class (`literal`, `paraphrase`):
  - `cases`, `recall_at_k_mean`, `false_inclusion_rate`;
  - `unauthorized_inclusions`, `stale_inclusions`;
  - `fallback_count`, `label_counts`;
  - `retrieval_ms_p50`, `retrieval_ms_max`, `embedding_cost_totals`.

  It also holds answer quality for the arm strategy: `passed`, `total`, `harness_completed`. Every fallback adds the blocker `hybrid strategy fell back to lexical on N case(s): <sorted codes>`.
- **B13, `compare_phase72_arms(current, hybrid)`.**
  - It raises `ValueError("arms are not paired: <field>")` unless these are equal: `task_manifest.cases_sha256`, `decision_route.route_id`, `seeds`, and `runner_argv` with `--variant`/`--output` removed.
  - It returns:
    - `classification`;
    - `paraphrase_recall{diffs[12], mean, ci{low, high}}`, using `reporting.paired_bootstrap_ci(diffs, seed=seeds[0])` over per-case diffs. Retrieval is deterministic, so it uses per-case means across seeds and lists `nondeterministic_cases`;
    - `literal_recall_mean_diff`;
    - `quality{current_passed, hybrid_passed, total}`;
    - `safety`, `fallbacks`, `blockers`.
- **B14, decision rule (pre-declared, OD-T08-4).** The rule is evaluated in this order:
  1. `unsafe`: any unauthorized or stale inclusion in any strategy of either report. This is a defect; T048 is blocked and the work returns to the PM.
  2. `unavailable`: any `retrieval_answer` case in the hybrid report whose hybrid label is not `hybrid`. The lane stays open with the fallback codes as its blocker.
  3. `harm`: `literal_recall_mean_diff < 0`, or `ci.high < 0`, or `hybrid_passed < current_passed`.
  4. `benefit`: `ci.low > 0`.
  5. Otherwise `no_benefit`.

  No classification changes the default. `benefit` licenses only the documented claim "measured benefit on the Phase 72 held-out set with route X and embedding model Y".

### 2. Code and caller map (07775f1; graft was unavailable in this session, so the map uses exhaustive `grep -rn` over src, scripts and tests)

**`src/rush/memory/retrieval.py`:**
- `embedding_text` L772, `_cosine` L779, `hybrid_candidates` L790-920, `hybrid_page` L923-1055.
- Helpers: `_candidate_to_item` L300, `_measure_page` L325, `_trial_page_bytes` L347, `_page` L378, `recall_page` L399.
- `_VECTOR_SCAN_CAP=512` L63, `DEFAULT_LIMIT=8` L65.

**Callers:**
- `hybrid_page`: `tools/memory.py:1013`, `tests/test_memory_hybrid.py`, `tests/test_phase70_ts.py:536-568`.
- `hybrid_candidates`: `hybrid_page` and `tests/test_memory_hybrid.py`.

**T01 (T004 note) symbols consumed:**
- `MemoryAccess.legacy(project_root, session_allowlist, *, owner_scope=None, operation="ask")` (a declared owner narrows);
- `VisibilityDecision`, `evaluate_artifact_visibility(store, artifact, *, access, mode="ordinary", now=None, memo=None)`;
- T01 filters `rows_by_id` before embedding text;
- `search_candidates`/`scope_artifacts` `owner_scope`/`include_archived`/`now` prefilters;
- `_read_access` in `MemoryTool`.

**T02 (T005, not on disk) symbols consumed:** `expand` `representation:"utf8"` returning `content_utf8`, `payload_hash`, total bytes and next offset (plan §2.1 item 5).

**`src/rush/memory/embeddings.py`:**
- `EmbeddingEngineUnavailable` L24, `EmbeddingResponseError` L30, `EmbeddingConfig` L37, `embed_chunks` L50, `_embed_batch` L63-80 (`_MAX_BATCH=32`, `_TIMEOUT_SECONDS=10`), `validate_embedding_response` L83-123.
- Callers: retrieval.py only; tests `test_memory_hybrid.py:16,363-390`.

**`src/rush/tools/memory.py`:** hybrid branch L995-1035, request field validation L945-983, `run` with `owner_scope` kwarg L401-424, `_related` L1226-1302.

**Other route, unchanged:** `dashboard/server.py:3015-3017` requires the `network` grant before calling `MemoryTool`. That file belongs to 72-T07.

**`src/rush/memory/store.py`:** `memory_embeddings` L529-539, `search_candidates` L1175 (no archive predicate until T01), `scope_artifacts` L1230-1273, `get_embedding` L1610, `put_embedding` L1638, delete drops vectors L1405. **Not edited by T08** (F6).

**`src/rush/memory/relations.py::related_artifacts`** L160-260 returns `items`. It is owned by 72-T03.

**`scripts/benchmarks/run.py`:**
- `_MEMORY_VARIANTS` L29, `_VARIANT_MAX_TOKENS` L30, `build_parser` L77-173;
- `_variant_hypothesis` L176-241, with callers L276 and L330;
- `_run_variant_cases` L257, `run_memory_suite` L289-460.
- T044 adds the manifest branch, the `live_answer_decider` injection and `--decision-*`/`--task-manifest`.

**`scripts/benchmarks/memory_datasets.py`:** `load_dataset_section` L108, `_validate_section` L79-105, `run_longmemeval_case` L190-259 (perms L215). Reused; not edited.

**`scripts/benchmarks/reporting.py`:** `paired_bootstrap_ci` L409, `write_memory_suite_report` L431 (one file per `--output`: `memory-suite-report.json`).

**`scripts/benchmarks/memory.py`:** T044's `TASK_KINDS`, `EVALUATORS`, `load_task_manifest`, `cases_digest`, `run_manifest_case` and `live_answer_decider` (T012 §4.1).

**Fixtures:**
- `tests/fixtures/benchmarks/memory_datasets.json` has sections `longmemeval`, `memory_agent_bench` and `swe_bench_verified`. Only `longmemeval` is read by tests, at `test_benchmark_memory_datasets.py:41`.
- `tests/fixtures/phase75/task_manifest.json` is T044's file: 5 cases, schema 1.

**Tests touched:**
- New: `tests/test_phase72_memory_hybrid.py`.
- Must stay green: `tests/test_memory_hybrid.py` (9), `tests/test_benchmark_memory_datasets.py` (8; its `set(per_variant)==set(_MEMORY_VARIANTS)` is unchanged because no runner variant is added), `tests/test_memory_retrieval.py:443-520` (hybrid with `network=True`), `tests/test_phase70_ts.py:536` (items only).
- T044's `tests/test_phase75_live_evaluation.py` tests 16 and 27 need amendment (§4).

**Docs:**
- `docs/reports/phase-72-memory-acceptance.md` (created by 72-T09/T014 schema; T048 appends);
- `docs/reports/phase-72-memory-eval/{current,hybrid}/memory-suite-report.json`;
- `docs/reports/phase-64-66-documentation-coverage.md`, checked by `scripts/sync_docs.py --check`. The owner of `docs/reports/` is `historical`. JSON receipts mirror the `docs/reports/continuity-gates/BG-AUTH.json` entry, with `authority:"generated"`, `media_type:"application/json"` and `source_state:"untracked"` before commit.

### 3. Design

**3.1 What "optional hybrid" means.**
- Hybrid is opt-in per request: `retrieval:"hybrid"` plus an explicit `EmbeddingConfig` plus the network grant.
- The default is `lexical` and stays `lexical` whatever T048 measures (B7, B14).
- Hybrid stays on legacy `recall` only. T06's v2 rejects `recall` and has no `retrieval` field (OD-T08-5).

**3.2 Product changes (T047).**

*`embeddings.py`:*
- Extract `validate_vectors(vectors, *, expected_count, expected_dimension=None) -> list[list[float]]` from `validate_embedding_response`, which then calls it. The behavior is identical, so the existing test stays green.
- `EmbeddingEngineUnavailable.__init__(message, *, timed_out=False)`. `_embed_batch` sets `timed_out=True` for a `TimeoutError`, or a `URLError` whose `.reason` is a `TimeoutError`.

*`retrieval.py`:*
- `_clock = time.perf_counter`.
- **`hybrid_candidates`:**
  - It validates `[*cached, *fresh, query]` through `validate_vectors` with `expected_count=len(...)`. A fresh count different from missing gives `EmbeddingResponseError`.
  - It catches by type and returns `{"available":False,"reason":str,"code":<B2 code>}`.
  - It counts `batches`, `embedded_chunks`, `cache_hits` and `input_tokens`, and times `embedding_ms`.
  - It returns `cost` in both the available and the unavailable result.
- **`hybrid_page(..., network_granted: bool = True)`:**
  - If `network_granted` is False, it falls back with `network_not_granted` without calling `hybrid_candidates`.
  - The fallback adds `embedding_fallback_code` and `embedding_cost`.
  - Success adds `embedding_status:"used"` and `embedding_fallback_code:None`.
  - It computes `complete`/`incomplete_reason` per B4 by tracking whether the loop broke with rows remaining and why.
  - `retrieval_ms` spans the whole call.
- `_measure_page` is unchanged; the new keys sit outside the measured payload, as `retrieval`/`candidates_truncated` do today.

*`tools/memory.py` hybrid branch (OD-T08-1):*
- It no longer returns `E_PERMISSION` when network is missing. It calls `hybrid_page(..., network_granted=granted.network)`.
- With network off, no socket opens: `embed_chunks` is never reached.
- The dashboard pre-call grant at `server.py:3015` is unchanged (T07 file).

**3.3 Benchmark changes (T047).**

*`memory.py`:*
- `EmbeddingRunConfig(config: EmbeddingConfig|None, network_granted: bool)`.
- `variant_retrieval(variant, root, tool, permissions, *, subject, query, session_allowlist, owner_scope=None, embedding: EmbeddingRunConfig, limit=8) -> VariantRetrieval` (B8).
- `seed_phase72_corpus(root, tool, corpus_records) -> dict[key, artifact_id]` (§3.4).
- `strip_phase72_gold(query_record)`.
- `retrieval_answer` kind in `TASK_KINDS`:
  - inputs exact keys: `corpus_section`, `query_section`, `query_id`;
  - supported variants: `none, current, budgeted, linked, full, hybrid`;
  - `raw` is rejected because it would deliver unscoped corpus text.
- `phase72_retrieval_metrics(...)`, `phase72_summary(case_records)` and `compare_phase72_arms(current, hybrid)` (B11-B14).

*`run.py`:*
- B9 flags and validation.
- `_variant_hypothesis` becomes a wrapper around `variant_retrieval(...).text`, with the embedding config passed through the `_decide` closures (L276 and L330).
- The manifest branch attaches the `retrieval` record and writes `phase72_hybrid_summary` plus blockers.

**Why `run.py` is in T047's `allowed_files`.** Three reasons:
- F1-F3 live in `_variant_hypothesis`.
- The flags must live in `build_parser`.
- T012's flag says the hybrid status must reach the report.

Routing the status through `memory.py` alone is impossible without the flags. All logic moves into `memory.py`; `run.py` keeps only wiring.

**3.4 Corpus and manifest additions (T046).**

*`memory_datasets.json`* gains two sections validated by the existing `_validate_section`:
- `phase72_hybrid_corpus`, with 48 records `{key, role, subject:"domain_knowledge", source, owner, text, anchor}`. The breakdown:

| Role | Keys | Source | Owner | Anchor |
|---|---|---|---|---|
| literal_positive | 12, `lp01-lp12` | `p72-main` | `{"kind":"agent","id":"p72-alice"}` | null |
| paraphrase_positive | 12, `pp01-pp12` | `p72-main` | alice | null |
| near_neighbor | 12, `nn01-nn12` | `p72-main` | alice | null |
| denied_owner | 4, `do01-do04` | `p72-main` | `{"kind":"agent","id":"p72-bob"}` | null |
| stale_hash | 4, `sh01-sh04` | `p72-main` | alice | `{path:"p72_src/<n>.py", symbol, written_source, current_source}` |
| revoked_source | 4, `rs01-rs04` | `p72-revoked` | alice | null |

- `phase72_hybrid_queries`, with 24 records `{query_id, class:"literal"|"paraphrase", query, question, relevant_keys:[one key], answer}`. `relevant_keys` and `answer` are gold-only.

*Each section manifest:*
- `dataset`: `rush_phase72_hybrid_corpus` or `rush_phase72_hybrid_queries`;
- `url`: `repo:tests/fixtures/benchmarks/memory_datasets.json#<section>`;
- `revision`: `phase72-t08-v1`;
- `sha256`: `_records_digest`;
- `license_or_terms`: `Rush project-authored fixture`;
- `split`: `heldout`.

*Content rules* (asserted by tests):
- Answers are unique tokens and absent from every non-relevant text.
- Each literal query phrase occurs verbatim in its positive.
- For each paraphrase query, `search_candidates` over all corpus sources excludes its positive.
- Each near-neighbor shares surface terms with a query but not its answer.
- Each of the 12 negatives contains the exact query phrase of one literal query, so a leak would rank.
- Item texts are at most 200 characters, so `excerpt` equals the full text.

*Seeding, per case into a fresh contained case root:*
1. Write each record through `MemoryTool.run(write, subject, content={"text":...}, source, owner_scope, symbol_ref=anchor? "path::symbol", permissions=ExecutionPermissions(cache_write=True))`.
2. For `stale_hash` records, write the anchor's `written_source` first and `current_source` after the write.
3. The read session uses `session_allowlist=["p72-main"]` and `owner_scope=alice`.

`revoked_source` is therefore source revocation of the session allowlist on the legacy route. Real policy revocation stays covered by T01 test 1, because `MemoryTool` policy resolution uses the real user data root (OD-T08-6).

*`task_manifest.json`, append-only:*
- Family appended: `{"id":"phase72_hybrid_heldout","origin":"phase-72 72-T08"}`.
- No variant added.
- 24 cases `p72-q-lit-01..12` and `p72-q-par-01..12` appended after the 5 shipped cases, each with:
  - `kind:"retrieval_answer"`, `variant:"base"`, `split:"heldout"`;
  - `inputs{corpus_section:"phase72_hybrid_corpus", query_section:"phase72_hybrid_queries", query_id}`;
  - `fixture_revision = sha256(f"{corpus_manifest_sha256}\n{queries_manifest_sha256}")`;
  - `grants{cache_write:true, artifact_write:false, build:false}`;
  - `requirements:["answer from the retrieved memory history only"]`;
  - `acceptance{evaluator:"normalized_contains", evaluator_version:1}`, `permitted_actions:["answer"]`;
  - `budget{max_total_tokens:16000, output_reserve_tokens:1024, max_steps:1, timeout_s:600}`.
- `freeze.cases_sha256` is refrozen with T044's `cases_digest`. The 5 shipped cases, the families prefix, the variants and the other top-level keys stay byte-identical.

**The freeze is the T046 commit, before any observation.**

**3.5 T048 exact commands (D1).**

*Preflight* (any failure stops the run; the lane stays open with that exact blocker):
1. `rtk proxy df -g /Users` must show at least 8 GiB free.
2. Check the runner help lists the flags: `rtk proxy env -u PYTHONPATH .venv/bin/python -m scripts.benchmarks.run --help | rtk grep -c -e --decision-mode -e --task-manifest -e --embedding-endpoint -e --allow-embedding-network`.
3. Check the embedding model is present: `rtk proxy curl -s -m 5 http://127.0.0.1:11434/api/tags`. A missing model is the blocker `embedding model <m> not installed; download not granted` unless OD-T08-2 grants `ollama pull`.
4. Record `rtk proxy ollama list`.

*Current arm:*

```
rtk proxy env -u PYTHONPATH uv run --python 3.12 --extra dev python -m scripts.benchmarks.run --suite memory --decision-mode live --decision-route openai-codex-oauth-cli-live --allow-live-route openai-codex-oauth-cli-live --task-manifest tests/fixtures/phase75/task_manifest.json --embedding-endpoint http://127.0.0.1:11434 --embedding-model <OD-T08-2 model> --embedding-model-digest <OD-T08-2 digest> --allow-embedding-network --variant current --seeds 1,2,3 --max-total-tokens 16000 --output docs/reports/phase-72-memory-eval/current
```

*Hybrid arm:* the identical command with `--variant hybrid --output docs/reports/phase-72-memory-eval/hybrid`.

*Compare:*

```
rtk proxy env -u PYTHONPATH .venv/bin/python -c "import json;from scripts.benchmarks.memory import compare_phase72_arms;c=json.load(open('docs/reports/phase-72-memory-eval/current/memory-suite-report.json'));h=json.load(open('docs/reports/phase-72-memory-eval/hybrid/memory-suite-report.json'));print(json.dumps(compare_phase72_arms(c,h),indent=2,sort_keys=True))"
```

*Size, recorded before commit:*
- `rtk proxy du -sk docs/reports/phase-72-memory-eval`
- `rtk wc -c docs/reports/phase-72-memory-eval/current/memory-suite-report.json docs/reports/phase-72-memory-eval/hybrid/memory-suite-report.json`

*Product digest:*

```
rtk proxy env -u PYTHONPATH .venv/bin/python -c "import hashlib,subprocess;ps=sorted(p for p in subprocess.run(['git','ls-files','src','scripts','pyproject.toml','uv.lock'],capture_output=True,text=True,check=True).stdout.splitlines() if p);h=hashlib.sha256();[h.update((p+'\0'+hashlib.sha256(open(p,'rb').read()).hexdigest()+'\n').encode()) for p in ps];print(h.hexdigest())"
```

*Coverage and docs check:* add receipts for both JSON files and the acceptance report, then run `rtk proxy env -u PYTHONPATH .venv/bin/python scripts/sync_docs.py --check`.

The live run is about 29 cases × 3 seeds × 2 arms, roughly 174 Codex decision calls, each capped at 16000 tokens (OD-T08-3).

**3.6 Report records (T048 into `docs/reports/phase-72-memory-acceptance.md`).** The "72-T08 paired hybrid evaluation" section records:
- route id, executable realpath and version from `decision_route`;
- the exact expanded commands;
- `manifest_id`, `cases_sha256` and the two corpus section sha256 values;
- evaluator ids and versions;
- product_digest;
- per-arm `phase72_hybrid_summary` and the compare JSON with its classification;
- latency, embedding cost and decision usage, with unavailable usage labeled non-comparable;
- every fallback with its code;
- unknowns, including confirmation or mismatch of the Codex JSONL event set (T012 missing evidence);
- raw output paths and byte sizes.

Then it appends the `L-hybrid-eval` lane record into the `rush-phase72-acceptance-v1` block. The record is append-only and uses T014's schema and its §3.2 product_digest. An unexecuted or unavailable lane is `open` with one exact blocker.

### 4. Cross-task conflicts

- **T044/T012:**
  - Tests 16 (`test_shipped_task_manifest_is_frozen_and_exact`) and 27 (`test_manifest_component_run_reports_every_case`) assert exactly 5 cases. T046 amends them only to "the 5 shipped cases are an exact, unchanged prefix" and "len(cases) × seeds". `tests/test_phase75_live_evaluation.py` is therefore in T046's files.
  - Test 27 will seed 24 × 48 artifacts per seed. That is acceptable and measured in T047's full-suite run.
- **T012 B6** says the request "never contains … the gold string". Once F1 is fixed, retrieved excerpts legitimately contain answers, for LME too: the session date is the gold for lme-q-001. B6 must ban gold fields and gold outside retrieved memory, not the substring in retrieved memory. This goes to the PM and the T043/T044 authors.
- **T044 lands before T047 with F1-F3 still present.** EVALUATOR live-answer history is then empty text until T047. T045's review must not treat that as an EVALUATOR pass for answer quality.
- **T01 (T004):**
  - The hybrid eligibility filter and owner narrowing on the legacy route are T01 deliverables. T08 tests assert them together with new T08 fields so that RED fails.
  - T01's freshness vocabulary changes compact `freshness`.
  - Owner decisions OD-1 and OD-3 from the T004 gate are still open.
- **T02 (T005, not on disk):** the `utf8` field names and whether `hybrid_page`'s success path applies T02's admission minimum. If T02 applies it, T08 inherits it.
- **T03:** the `related_artifacts` item shape (`items`) is used by the `linked` fix.
- **T06:** v2 has no hybrid (OD-T08-5).
- **T07:** the dashboard's network pre-gate for hybrid is unchanged. Surfaces should show `embedding_fallback_code`/`incomplete_reason`, which belongs to T07's scope.
- **T09/T014:** the T014 note was not on disk. T048 needs T014's lane schema and the acceptance file. The user docs must state opt-in, the fallback codes and the measured classification.
- **Phase 75:** the family id has the `phase72_` prefix, so it cannot collide with the 12 Phase 75 families. `embedding_cost` follows C06 for later 75-T01 migration.
- **sync_docs:** red at HEAD (F7). The PM must add receipts for the board notes before T048's check can pass.

### 5. Test matrix (`tests/test_phase72_memory_hybrid.py`, new; symbols imported inside test bodies)

| # | Test | Fixture | Assertion | Expected RED |
|---|---|---|---|---|
| 1 | `test_t08_scope_fallback_and_heldout_relevance` | 2 lp, 2 pp (absent from FTS), 2 nn, 1 do, 1 sh, 1 rs via real `MemoryTool` writes; deterministic fake vectors through patched `urllib.request.urlopen` in `rush.memory.embeddings` | Embed requests never contain do/sh/rs texts. For lexical, metadata and hybrid: exact `recall_at_k` (paraphrase lexical 0.0, hybrid 1.0; literal 1.0 for both), exact `false_inclusion_count`, unauthorized=0, stale=0, labels `lexical`/`metadata`/`hybrid`, `complete` | ImportError `variant_retrieval` |
| 2 | `test_t08_eligibility_precedes_vector_scoring` | Archived, expired, foreign owner (declared alice), raw-SQL tampered, stale anchor, out-of-allowlist, plus 2 eligible | Spy chunks = the 2 eligible texts plus the query; `embedding_cost.embedded_chunks==3`, `batches==2` | KeyError `embedding_cost` |
| 3 | `test_t08_fallback_codes_are_precise[no_engine_configured, network_not_granted, engine_unavailable, engine_timeout_socket, engine_timeout_urlerror, invalid_nan, invalid_wrong_dimension, invalid_count_mismatch, invalid_zero_norm, cached_vector_dimension_mismatch]` | Real `embed_chunks` with patched urlopen, or a fake `embed_fn`; `network_not_granted` through `MemoryTool` with `ExecutionPermissions(network=False)` and urlopen patched to fail the test if called | `code=="E_EMBEDDING_UNAVAILABLE"`, `retrieval=="lexical"`, exact `embedding_fallback_code`, items equal `recall_page` items | KeyError / NaN reported as hybrid / `E_PERMISSION` / uncaught ValueError |
| 4 | `test_t08_edit_invalidates_stale_embedding` | A1 v1 [1,0], A2 [0,1]; `cache_write`; edit A1 to [0,1] text | Call 2 `cache_hits==2`. After the edit, A1 is re-embedded, `cache_hits==1`, and the order changes exactly | KeyError `embedding_cost` |
| 5 | `test_t08_capped_pool_is_labeled_incomplete[candidate_cap_513, page_limit, budget, complete]` | 513 rows; 10 rows with limit 3; tiny `max_bytes`; 2 rows with limit 8 | `complete`, `next_cursor is None`, exact `incomplete_reason` and `candidates_truncated` | `complete` is True today |
| 6 | `test_t08_exact_budget_and_cost_recorded` | Patched `retrieval._clock` sequence | Page bytes/tokens equal `_measure_page` and are within caps; `embedding_cost` dict exactly equal (ms values from the patched clock, `input_tokens` from cl100k of the sent texts, basis string) | AttributeError `_clock` |
| 7 | `test_t08_variant_retrieval_reads_excerpts_and_labels` | lme-q-001 namespace via `run_longmemeval_case` | `current` text equals the joined excerpts (non-empty, exact); `hybrid` without config gives `no_engine_configured`, without network gives `network_not_granted`, text equal to `current`; `run._variant_hypothesis` returns the same text | ImportError / `''` |
| 8 | `test_t08_linked_variant_adds_related_text` | Two artifacts linked through the `link` operation | `linked` text = seed excerpt plus neighbor text, exact | `''` |
| 9 | `test_t08_runner_embedding_flags_validated[partial_config, no_network_grant, raw_with_retrieval_answer]` | `main([...])`; urlopen and spawn spies | Returns 1 with the exact message; no spawn or network | SystemExit 2 |
| 10 | `test_t08_phase72_manifest_cases_frozen_and_append_only` | Shipped manifest, plus `git show HEAD` copy loaded in test | Prefix unchanged; family appended; 29 cases; digest verifies; per-case fields exact (§3.4); `fixture_revision` formula | FixtureError unknown kind |
| 11 | `test_t08_retrieval_answer_case_component_record` | `run_manifest_case` component mode, `p72-q-lit-01` and `p72-q-par-01`, both arms | Exact B11 record values; the request contains no `answer`/`relevant_keys`/key/role; evaluator `normalized_contains`/1 | ImportError / FixtureError |
| 12 | `test_t08_compare_arms_decision_rule[unsafe, unavailable, harm, benefit, no_benefit, not_paired]` | Synthetic report dicts | Exact classification, fields and ValueError message | ImportError |
| 13 | `test_t08_seeded_corpus_shape` | `seed_phase72_corpus` into tmp | Counts 12/12/12/4/4/4; FTS constraints per §3.4; answers unique | ImportError |
| 14 | `test_t08_report_records_phase72_summary` | `run_memory_suite` in manifest component mode, `--variant hybrid`, no embedding flags, seeds `1` | `phase72_hybrid_summary.hybrid.label_counts=={"lexical":24}`, `fallback_count==24`, exact blocker string, no `"hybrid"` label | SystemExit 2 / KeyError |

**Amended T044 tests (T046), RED until T047 registers `retrieval_answer`:**
- `tests/test_phase75_live_evaluation.py::test_shipped_task_manifest_is_frozen_and_exact`
- `tests/test_phase75_live_evaluation.py::test_manifest_component_run_reports_every_case`

**Must stay green in T047:** `tests/test_memory_hybrid.py`, `tests/test_benchmark_memory_datasets.py`, `tests/test_memory_retrieval.py`, `tests/test_phase70_ts.py` and the full suite against the T001 baseline.

### 6. Worker packages

Listed in the receipt: T046 (red), T047 (implement) and T048 (live).

---

## (B) Receipt

```json
{
  "goalbuddy_receipt_v1": {
    "result": "done",
    "task_id": "T013",
    "board_path": "/Users/jamesdsizemore/Developer/rush-cli-worktrees/phase-72/docs/goals/phase-72-memory-correctness/state.yaml",
    "decision": "approved",
    "full_outcome_complete": false,
    "rationale": "Gate approved with owner decisions pending. Execution at 07775f1 shows the benchmark has no working hybrid comparison: every recall variant yields an empty hypothesis (excerpt vs content), the hybrid variant gets E_PERMISSION with no embedding config, and linked reads the wrong key with no text. hybrid_page always claims complete; invalid or mismatched vectors can pass as hybrid. Fixes go in retrieval.py, embeddings.py, tools/memory.py, benchmark memory.py and run.py. store.py is not needed because the version-keyed cache already invalidates. The corpus and manifest are append-only and frozen by T046. Hybrid stays opt-in; the decision rule is pre-declared and never enables it by default.",
    "worker_package": {
      "red": {
        "objective": "T046: write the full 72-T08 test matrix (T013 note §5, 14 tests plus the 2 amended T044 tests), the frozen Phase 72 corpus (2 memory_datasets.json sections) and the 24 appended manifest cases with refrozen cases_sha256; prove each selected test FAILS before any production change.",
        "allowed_files": [
          "tests/test_phase72_memory_hybrid.py",
          "tests/fixtures/phase75/task_manifest.json",
          "tests/fixtures/benchmarks/memory_datasets.json",
          "tests/test_phase75_live_evaluation.py"
        ],
        "verify": [
          "rtk proxy env -u PYTHONPATH uv run --python 3.12 --extra dev python -c \"import subprocess,sys; r=subprocess.run([sys.executable,'-m','pytest','tests/test_phase72_memory_hybrid.py','tests/test_phase75_live_evaluation.py::test_shipped_task_manifest_is_frozen_and_exact','tests/test_phase75_live_evaluation.py::test_manifest_component_run_reports_every_case','-q','-p','no:cacheprovider'],capture_output=True,text=True); print(r.stdout[-4000:]); s=(r.stdout.strip().splitlines() or [''])[-1]; sys.exit(0 if r.returncode==1 and ' failed' in s and not any(w in s for w in (' passed',' skipped',' error',' xfail',' xpass')) else 1)\"",
          "rtk proxy env -u PYTHONPATH .venv/bin/python -c \"import json,subprocess;old=json.loads(subprocess.run(['git','show','HEAD:tests/fixtures/phase75/task_manifest.json'],capture_output=True,text=True,check=True).stdout);new=json.load(open('tests/fixtures/phase75/task_manifest.json'));assert new['cases'][:len(old['cases'])]==old['cases'];assert new['families'][:len(old['families'])]==old['families'];assert new['variants']==old['variants'];assert {k:v for k,v in new.items() if k not in('cases','families','freeze')}=={k:v for k,v in old.items() if k not in('cases','families','freeze')};print('manifest append-only OK',len(old['cases']),'->',len(new['cases']))\"",
          "rtk proxy env -u PYTHONPATH .venv/bin/python -c \"import json,subprocess;old=json.loads(subprocess.run(['git','show','HEAD:tests/fixtures/benchmarks/memory_datasets.json'],capture_output=True,text=True,check=True).stdout);new=json.load(open('tests/fixtures/benchmarks/memory_datasets.json'));assert all(new[k]==old[k] for k in old);assert set(new)-set(old)=={'phase72_hybrid_corpus','phase72_hybrid_queries'};print('datasets append-only OK')\"",
          "rtk proxy env -u PYTHONPATH uv run --python 3.12 --extra dev python -m pytest tests/test_benchmark_memory_datasets.py tests/test_memory_hybrid.py -q -p no:cacheprovider  # keep-green: fixture additions break nothing"
        ],
        "stop_if": [
          "At task start, any symbol in T013 §2 differs at HEAD (T01 MemoryAccess/evaluate_artifact_visibility, T02 utf8 expand fields, T03 related items shape, T044 TASK_KINDS/EVALUATORS/load_task_manifest/cases_digest/run_manifest_case): return to PM for a gate delta.",
          "The legacy list operation cannot browse without a query, or MemoryTool write does not record content_hash for symbol_ref (stale_hash seeding).",
          "Need files outside allowed_files (PM amends only with gate-note justification).",
          "Behavior is ambiguous against the gate note.",
          "Verification fails twice."
        ]
      },
      "implement": {
        "objective": "T047: implement T013 §3.2-3.3 (fallback codes, vector validation, timeout classification, honest completeness, embedding_cost, network_not_granted fallback, variant_retrieval with excerpt/linked/hybrid fixes, embedding runner flags, retrieval_answer kind, metrics, summary, compare_phase72_arms) until the T046 tests pass; full suite, ruff, format, mypy green against the T001 baseline.",
        "allowed_files": [
          "src/rush/memory/retrieval.py",
          "src/rush/memory/embeddings.py",
          "src/rush/tools/memory.py",
          "scripts/benchmarks/memory.py",
          "scripts/benchmarks/run.py"
        ],
        "verify": [
          "rtk proxy env -u PYTHONPATH uv run --python 3.12 --extra dev python -m pytest tests/test_phase72_memory_hybrid.py tests/test_memory_hybrid.py tests/test_phase75_live_evaluation.py tests/test_benchmark_memory_datasets.py tests/test_memory_retrieval.py tests/test_phase70_ts.py -q -p no:cacheprovider",
          "rtk proxy env -u PYTHONPATH uv run --python 3.12 --extra dev python -c \"import subprocess,sys,re; r=subprocess.run([sys.executable,'-m','pytest','tests/','-q','-m','','-p','no:cacheprovider'],capture_output=True,text=True); out=r.stdout; print(out[-3000:]); fails=set(re.findall(r'^(?:FAILED|ERROR) (\\S+)',out,re.M)); base={'tests/test_phase70_t28f_review1.py::test_plus_minus_expand_and_collapse_detail_in_git_and_memory','tests/test_phase70_tui_usability_ef.py::test_t28e_tokens_git_artifacts'}; last=(out.strip().splitlines() or [''])[-1]; print('NEW FAILURES:',sorted(fails-base)); sys.exit(0 if fails<=base and 'skipped' not in last and ' error' not in last else 1)\"",
          "rtk proxy uv run --python 3.12 --extra dev ruff check src tests scripts",
          "rtk proxy uv run --python 3.12 --extra dev ruff format --check src tests scripts",
          "rtk proxy uv run --python 3.12 --extra dev mypy src/rush",
          "rtk proxy git diff --check",
          "rtk proxy env -u PYTHONPATH .venv/bin/python -m scripts.benchmarks.run --help  # must list --embedding-endpoint --embedding-model --embedding-model-digest --embedding-chunking-version --allow-embedding-network",
          "rush_check on the 5 changed files"
        ],
        "stop_if": [
          "store.py or any file outside allowed_files is needed (gate F6: invalidation already version-keyed).",
          "Any existing test must be edited to pass (test defect returns to PM; do not weaken RED tests).",
          "A hybrid cursor/paging route appears necessary (out of plan; B4 labels incomplete instead).",
          "Earlier-unit symbols differ from T013 §2.",
          "Need files outside allowed_files (PM amends only with gate-note justification).",
          "Behavior is ambiguous against the gate note.",
          "Verification fails twice (max two fix rounds; after round 2 the PM finishes directly)."
        ]
      },
      "live": {
        "objective": "T048: run the paired current-vs-hybrid live evaluation on identical frozen manifest/corpus/route/embedding model/grants/seeds; commit raw output under docs/reports/phase-72-memory-eval/{current,hybrid}/ after recording its size; record route/executable/version, exact commands, manifest and corpus digests, evaluators, product_digest, per-arm summaries, compare_phase72_arms classification, cost, latency, fallbacks and unknowns into docs/reports/phase-72-memory-acceptance.md, and append the L-hybrid-eval lane record per T014 §3.2. Unavailable or unexecuted lane = open with one exact blocker, never a pass.",
        "allowed_files": [
          "docs/reports/phase-72-memory-acceptance.md",
          "docs/reports/phase-72-memory-eval/current/memory-suite-report.json",
          "docs/reports/phase-72-memory-eval/hybrid/memory-suite-report.json",
          "docs/reports/phase-64-66-documentation-coverage.md"
        ],
        "verify": [
          "rtk proxy df -g /Users  # >= 8 GiB free",
          "rtk proxy curl -s -m 5 http://127.0.0.1:11434/api/tags  # OD-T08-2 model listed, else stop with exact blocker",
          "rtk proxy env -u PYTHONPATH uv run --python 3.12 --extra dev python -m scripts.benchmarks.run --suite memory --decision-mode live --decision-route openai-codex-oauth-cli-live --allow-live-route openai-codex-oauth-cli-live --task-manifest tests/fixtures/phase75/task_manifest.json --embedding-endpoint http://127.0.0.1:11434 --embedding-model <OD-T08-2 model> --embedding-model-digest <OD-T08-2 digest> --allow-embedding-network --variant current --seeds 1,2,3 --max-total-tokens 16000 --output docs/reports/phase-72-memory-eval/current",
          "rtk proxy env -u PYTHONPATH uv run --python 3.12 --extra dev python -m scripts.benchmarks.run --suite memory --decision-mode live --decision-route openai-codex-oauth-cli-live --allow-live-route openai-codex-oauth-cli-live --task-manifest tests/fixtures/phase75/task_manifest.json --embedding-endpoint http://127.0.0.1:11434 --embedding-model <OD-T08-2 model> --embedding-model-digest <OD-T08-2 digest> --allow-embedding-network --variant hybrid --seeds 1,2,3 --max-total-tokens 16000 --output docs/reports/phase-72-memory-eval/hybrid",
          "rtk proxy env -u PYTHONPATH .venv/bin/python -c \"import json;from scripts.benchmarks.memory import compare_phase72_arms;c=json.load(open('docs/reports/phase-72-memory-eval/current/memory-suite-report.json'));h=json.load(open('docs/reports/phase-72-memory-eval/hybrid/memory-suite-report.json'));print(json.dumps(compare_phase72_arms(c,h),indent=2,sort_keys=True))\"",
          "rtk proxy du -sk docs/reports/phase-72-memory-eval && rtk wc -c docs/reports/phase-72-memory-eval/current/memory-suite-report.json docs/reports/phase-72-memory-eval/hybrid/memory-suite-report.json",
          "rtk proxy env -u PYTHONPATH .venv/bin/python -c \"import hashlib,subprocess;ps=sorted(p for p in subprocess.run(['git','ls-files','src','scripts','pyproject.toml','uv.lock'],capture_output=True,text=True,check=True).stdout.splitlines() if p);h=hashlib.sha256();[h.update((p+'\\0'+hashlib.sha256(open(p,'rb').read()).hexdigest()+'\\n').encode()) for p in ps];print(h.hexdigest())\"",
          "rtk proxy env -u PYTHONPATH .venv/bin/python scripts/sync_docs.py --check"
        ],
        "stop_if": [
          "OD-T08-2 model or digest unfilled, model not installed and download not granted, or endpoint unreachable: lane open, exact blocker, do not start either arm.",
          "Codex route not logged in or --allow-live-route not owner-granted (OD-T08-3).",
          "compare_phase72_arms raises not paired, or classification unsafe: stop, return to PM as defect.",
          "T014 lane-record schema or the acceptance block is not on the board.",
          "sync_docs --check reports errors outside this lane's files (board-note receipts are the PM's).",
          "Need files outside allowed_files (PM amends only with gate-note justification).",
          "Verification fails twice."
        ]
      }
    },
    "evidence": [
      "Executed probe: current/hybrid/linked _variant_hypothesis on both longmemeval records all returned ''; recall items keys [excerpt,freshness,id,relations,source,trust,version]; hybrid recall code E_PERMISSION 'requires network'; related data keys [bytes,complete,encoding,items,tokens].",
      "retrieval.py:1043-1055 hybrid_page complete=True/next_cursor=None unconditionally; :779-781 _cosine 0.0 on dim mismatch; :882 zip strict uncaught.",
      "embeddings.py:76-77 timeout and connection failure share EmbeddingEngineUnavailable(str(exc)).",
      "store.py:529-539/1610-1636 embedding key includes artifact_version and content_hash; :1405 delete drops vectors.",
      "memory_datasets.py:215 permissions cache_write only; tools/memory.py:995-1012 network gate and request-only EmbeddingConfig; no installed embedding config in src.",
      "relations.py:192-260 returns items with id/version/kind/direction only; run.py:235 reads 'related'.",
      "sync_docs --check at HEAD: 4 errors (missing receipts for notes T003/T004/T009/T012).",
      "pytest tests/test_memory_hybrid.py tests/test_benchmark_memory_datasets.py: 17 passed.",
      "product_digest command executes (527 files at HEAD); ollama, codex, claude present on PATH (not invoked)."
    ],
    "subgoal_contract": null,
    "parallel_safety": null,
    "blocked_tasks": ["T046", "T047", "T048"],
    "missing_evidence": [
      "T005 (72-T02) and T014 (72-T09) gate notes not on disk: utf8 expand field names and the acceptance lane schema are taken from the plan and the PM prompt.",
      "graft unavailable in this session; caller map from exhaustive grep over src, scripts and tests.",
      "No live provider or embedding route executed (by design); Codex JSONL event set still unconfirmed (T012), so T048 must confirm it.",
      "Metadata-strategy ordering depends on uuid4 ids, so it may vary per seed; T048 records it per seed."
    ],
    "required_board_updates": [
      "Replace T046/T047/T048 allowed_files, verify and stop_if with worker_package red/implement/live.",
      "T046 starts only after T019 (72-T01), T022 (72-T02), T025 (72-T03) and T044 land.",
      "Add coverage receipts for docs/goals/phase-72-memory-correctness/notes/*.md (sync_docs red at HEAD) before T048.",
      "Route the T012 B6 gold-string correction and the T044 tests 16/27 amendment notice to T043/T044/T045.",
      "Fill the OD-T08-2 model and digest placeholders in T048 verify after the owner answers."
    ],
    "owner_decisions_needed": [
      "OD-T08-1: retrieval=hybrid without the network grant returns a labeled lexical fallback (embedding_fallback_code=network_not_granted) instead of E_PERMISSION, per the packet's 'network denial returns labeled lexical fallback'. The dashboard pre-call grant (T07 file) is unchanged. Confirm.",
      "OD-T08-2: embedding engine for T048: local Ollama at http://127.0.0.1:11434, which model (for example nomic-embed-text), consent to 'ollama pull' if absent, and model_digest = the asserted 'ollama list' ID.",
      "OD-T08-3: consent to live spend on openai-codex-oauth-cli-live: 29 cases x 3 seeds x 2 arms, about 174 decision calls, each capped at 16000 tokens.",
      "OD-T08-4: decision rule thresholds in B14 (unsafe > unavailable > harm > benefit when the paraphrase per-case recall paired-bootstrap CI low > 0 > no_benefit); hybrid never enabled by default under any outcome.",
      "OD-T08-5: hybrid stays a legacy recall option; T06 v2 rejects recall and has no retrieval field. Confirm, or add retrieval/embedding fields to the T06 v2 schema.",
      "OD-T08-6: revoked_source negatives are realized as session-allowlist revocation on the legacy route, because MemoryTool policy resolution reads the real user data root; real policy revocation stays covered by T01 test 1. Confirm.",
      "OD-T08-7: 'compare lexical, metadata and optional hybrid' is realized as in-run deterministic metrics for all three strategies plus the plan's two live answer arms (current, hybrid; D1 paths). Alternative: add a third live arm --variant metadata with output docs/reports/phase-72-memory-eval/metadata (extends D1).",
      "Inherited pending: T012 OD1-OD13 (notably OD2 5-case seed prefix, OD3/OD4 budget, OD5 live requires manifest, OD6 answer cwd, OD7 normalized_contains, OD10 seeds as labels, OD11 T048 is the first real-provider run) and T004 OD-1/OD-3."
    ]
  }
}
```

Relevant paths:
- /Users/jamesdsizemore/Developer/rush-cli-worktrees/phase-72/docs/goals/phase-72-memory-correctness/state.yaml
- /Users/jamesdsizemore/Developer/rush-cli-worktrees/phase-72/docs/goals/phase-72-memory-correctness/notes/T012-design-gate-75-t02-evaluator.md
- /Users/jamesdsizemore/Developer/rush-cli-worktrees/phase-72/docs/goals/phase-72-memory-correctness/notes/T004-design-gate-72-t01.md
- /Users/jamesdsizemore/Developer/rush-cli-worktrees/phase-72/src/rush/memory/retrieval.py
- /Users/jamesdsizemore/Developer/rush-cli-worktrees/phase-72/src/rush/memory/embeddings.py
- /Users/jamesdsizemore/Developer/rush-cli-worktrees/phase-72/src/rush/tools/memory.py
- /Users/jamesdsizemore/Developer/rush-cli-worktrees/phase-72/scripts/benchmarks/run.py
- /Users/jamesdsizemore/Developer/rush-cli-worktrees/phase-72/scripts/benchmarks/memory_datasets.py
- /Users/jamesdsizemore/Developer/rush-cli-worktrees/phase-72/scripts/sync_docs.py