# Memory capabilities: benchmark strategy

Status: proposed evaluation contract, 2026-09-08. No benchmark run or measured improvement is claimed. Implementation baseline: `997b56e`, `codex/phase-61-62-review-fixes`.

## Decision

Use established public benchmarks **plus a Rush-specific behavioral suite**. Extend Rush's existing `scripts/benchmarks/run.py`; do not build another general evaluation framework. Public datasets establish comparability. Rush scenarios establish that its permissions, evidence, CLI/MCP routes, handoffs and agent decisions work together.

The companion [Phase 63 TDD implementation plan](../phase-plans/phase-63-memory-capabilities-vibecoder-plan.md) continues the developed Phase 61/62 memory foundation and integrations, and owns production work and tests. This report owns Phase 63 evaluation methodology. Its thresholds are proposed engineering requirements, not observations.

## Comparison set and selection criteria

Compared: LongMemEval, MemoryAgentBench, SWE-bench Verified, LongMemEval-V2 and LoCoMo as benchmark workloads; native benchmark harnesses, Inspect AI and Rush's existing runner as execution frameworks. Criteria: relevance to remembered project behavior, reproducibility, executable correctness evidence, token/cost accounting, cross-session coverage, integration effort and isolation requirements.

### Core workloads

| Benchmark | Evidence it supplies | Gap Rush must cover | Decision |
|---|---|---|---|
| LongMemEval cleaned S | Multi-session recall, temporal questions, updates and abstention across 500 questions | Conversation answers do not prove repairs or permission safety | Required public memory-quality lane; preserve official scoring |
| MemoryAgentBench | Incremental memory under retrieval, learning, long-range understanding and conflict-resolution tasks | Does not establish Rush transport or project verification semantics | Required incremental/conflict lane |
| SWE-bench Verified | Real repository repair tasks scored with executable tests; 500-task verified set | Independent issue resolution does not itself test longitudinal memory | Required repair comparison using official harness; separate custom multi-session derivative |

LongMemEval publishes data fields, answer-generation format and evaluation scripts. Use the cleaned release; record exact dataset and evaluator revisions. Report session-level and turn-level evidence recall separately from answer correctness. [Official LongMemEval repository](https://github.com/xiaowu0162/LongMemEval)

MemoryAgentBench explicitly studies incremental memory and four capability groups. Preserve its task partitions and evaluation protocol instead of merging them into one custom accuracy number. [Official MemoryAgentBench repository](https://github.com/HUST-AI-HYZ/MemoryAgentBench)

SWE-bench's harness evaluates generated patches in containers. Use its evaluator for comparable repair results; provision storage and execution resources separately from installing Rush. [Official SWE-bench harness documentation](https://www.swebench.com/SWE-bench/reference/harness/)

### Additional workloads and framework alternatives

| Candidate | Assessment | Decision |
|---|---|---|
| LongMemEval-V2 | Agent trajectories, changing state, workflow knowledge, gotchas and premise awareness fit recipes and last-success diagnosis; newer protocol and richer inputs increase integration work | Include compatibility lane; publish separately from original LongMemEval and identify any modality restriction |
| LoCoMo | Useful long-conversation and event regression coverage; less direct evidence for coding behavior | Secondary conversation regression, not a required replacement for core lanes |
| Inspect AI | Established dataset/solver/scorer framework with tool-agent and sandbox support | Serious alternative for a standalone evaluation project; do not add a second orchestration layer to Rush now |
| New bespoke harness | Complete control but duplicates scheduling, manifests and reporting already present | Reject; create only missing scenarios/adapters inside existing runner |

LongMemEval-V2 is a newer published benchmark; its paper describes work in progress. Pin its evolving harness and report limitations rather than treating its scores as interchangeable with original LongMemEval. [Official repository](https://github.com/xiaowu0162/LongMemEval-V2), [paper](https://arxiv.org/abs/2605.12493)

LoCoMo supplies conversation QA, event summarization and multimodal material. A text-only subset must be labelled as such. [Official LoCoMo repository](https://github.com/snap-research/locomo)

Inspect AI supports reusable evaluation components and agent evaluations. That makes it a valid alternative, but adoption here would duplicate an existing execution surface. [Official Inspect AI documentation](https://inspect.aisi.org.uk/)

## Existing Rush substrate

`scripts/benchmarks/run.py:19-53` already registers probes; `:120-187` admits scenarios and runs them. `scripts/benchmarks/contracts.py` defines `Scenario`, `SourceEvidence` and `ProbeResult`. `fixtures.py` validates contained JSON fixtures. `providers.py` has explicitly admitted live routes. `reporting.py` writes evidence-backed results. Extend these contracts without weakening path containment or changing existing scenarios.

`scripts/benchmarks/context.py:21-158` provides local context probes. `src/rush/tools/prompt_eval.py:101-286` evaluates supplied run records; it is not an agent launcher or proof that supplied records reflect execution. New probes must gather actual tool, provider and verifier events. `TelemetryStore`'s fixed dollar estimate is not observed provider billing.

## Rush-specific scenario contract

Use tiny deterministic repositories and JSON records checked into `tests/fixtures/benchmarks/memory_cases.json`. Each scenario declares setup, allowed audience, input, expected evidence IDs, prohibited evidence, required commands and exact outcome. Failure is an exact assertion, never membership in a permissive status set.

| Scenario IDs | Required demonstration | Feature coverage |
|---|---|---|
| M01–M05 | Exact identifier; paraphrase; stale record; contradictory advice; denied source outranking valid result | Retrieval, contextual metadata, scoped ranking, abstention |
| M06–M10 | Oversized evidence paged exactly; revoked permission between pages; duplicate episodes; source edit; cache-budget mismatch | Expansion, consolidation, freshness, cache identity |
| M11–M15 | Failed timeout repair; successful size-limit repair; changed environment permits retrial; guest-checkout regression; explicit intent supersession | Repair episodes and product intent |
| M16–M20 | Current CSV export recipe; changed API rejects recipe; early regression-catching check; missing engine; security/license finding revisited after version change | Recipes, check ordering, capability observations |
| M21–M25 | Code regression since success; dependency drift; environment mismatch; acknowledged provider delta; replay or interrupted receipt | Last-success diagnosis and handoff |
| M26–M30 | Imported prompt injection; malformed embeddings; schema migration rollback; concurrent update; agent changes next action after retrieval | Trust, optional hybrid path, persistence, closed-loop behavior |

All fixtures are synthetic, inspectable and local. Public benchmark answers, patches and grader labels never become fixture hints supplied to the evaluated agent. Add realistic multi-session episodes after the deterministic fixtures; label those results separately.

## Experimental protocol

### Variants and isolation

Compare `none` (no memory), `current` (997b56e defended BM25), `raw` (authorized raw history), `budgeted`, `linked`, `full`, and `hybrid`. Run baseline from its immutable revision in an isolated checkout, not by approximating old behavior in new production code. Use the same agent model revision, prompt, tool permissions, task order, inference settings and total task budget for paired comparisons.

Reset the memory namespace between independent cases. Carry memory only between sessions explicitly belonging to one episode. Split development and held-out tasks by repository/history lineage. Do not seed later tasks with their gold patches or answers. Record cache cold/warm state; do not compare cold baseline with warm candidate.

Each dataset manifest records upstream URL, commit/release, file SHA256, license/terms, split, selected IDs, ingestion transformation, evaluator revision and retrieval date. Dataset caches stay outside Git. Downloads and model calls require the existing explicit admission mechanism; this plan does not grant them. A missing dependency or model produces a recorded unavailable run, never a successful score of zero.

For LongMemEval, remove `answer`, `answer_session_ids` and per-turn `has_answer` labels before ingestion. Retain grader data in a separate process/input inaccessible to the agent. Emit official `{question_id, hypothesis}` JSONL for native scoring. Preserve dates and session identifiers that are legitimate question context. A gold-evidence-only run is an explicitly labelled oracle diagnostic.

For SWE-bench, score patches with the official harness, for example:

```bash
python -m swebench.harness.run_evaluation --dataset_name princeton-nlp/SWE-bench_Verified --predictions_path predictions.jsonl --max_workers 1 --run_id rush-memory-paired
```

Run this inside a separately pinned benchmark environment. It is not a Rush installation command. Official scores use native cases. A longitudinal sequence that carries repair experience between issues is a **Rush-derived repair benchmark**, with its own split and leakage controls; never publish its score as official SWE-bench Verified.

### Metrics

Record answer/task correctness, required-evidence recall, unsupported-answer/abstention errors and unauthorized/stale delivery counts. For repairs also record repeated unsuccessful attempts, final executable pass rate and user corrections. For checks record time and tokens to first real regression detection plus complete required-gate outcomes. For handoffs record delivered versus rehydrated versions and missing/extra records.

Account for ingestion, consolidation, retrieval, expansion, graph neighbors, handoff, embeddings and evaluator work separately. Report total agent input/output tokens, memory-delivered context tokens, token-count method, network bytes, wall time, p50/p95 retrieval latency, SQL query count, source reads and parser invocations. Report actual provider usage when supplied; otherwise mark it unavailable or estimated. Do not add tokenizer estimates to actual usage for the same call. Report grader costs outside agent costs and all-in costs alongside them.

Run at least three fixed seeds for stochastic task comparisons. Report per-case paired differences and a seeded paired bootstrap 95% confidence interval. Resample independent episode/repository clusters, keeping their sessions and paired seeds together; do not count correlated turns as independent samples. Retain unsuccessful, timed-out and budget-exhausted cases in denominators. Publish sample size and exclusions. Do not infer statistical equivalence from a nonsignificant difference or claim broad quality from deterministic fixtures.

### Acceptance targets

| Gate | Proposed requirement |
|---|---|
| Correctness and trust | All deterministic scenario assertions pass; zero unauthorized content, false acknowledgements, falsely verified repairs or silent evidence loss |
| Budgets | Every successful bounded response obeys both advertised token and byte caps; all expansions count toward episode budget |
| Token benefit | At least 25% reduction in median total memory-delivered context versus `raw` on the predeclared long-history subset, including expansions and handoffs; report all-in cost too |
| Quality | Paired 95% interval lower bound for candidate-minus-baseline task success at least −2 percentage points; insufficient precision is inconclusive, not pass |
| Runtime | Warm/cold p95 recall no more than 10% above corresponding baseline at matched corpus size; one file validation per unique file per request; no redundant defended searches |
| Agent benefit | Repeated unsuccessful attempts decrease on the predeclared repeat-prone repair subset; final correctness satisfies quality gate. Check ordering improves median time to first detection without dropping any required check |

These gates apply to measured promotion of a variant, not permission to omit a suggested feature. Implement and test the optional hybrid route even if results keep lexical retrieval as default. If a quality interval is too wide, publish the uncertainty and collect a larger predeclared held-out sample; do not change thresholds after seeing results. Zero baseline repeats or no seeded regressions make those benefit metrics inapplicable, not improved.

## Execution tiers and completion claims

**Tier A, routine CI:** deterministic SQLite, parser, budget, permission, migration, adapter and local executable fixtures. No network, provider or model download.

**Tier B, integration:** real local stdio peers, actual patch verification, process cancellation, configured embedding engine and installed CLI/MCP parity. Fake peers test protocol contracts only. Exercise supported operating systems where process behavior differs.

**Tier C, admitted evaluation:** native public datasets, real provider handoffs and multi-session agent tasks. Record exact provider/runtime versions and grants. No Tier A or B result substitutes for Tier C evidence.

Implementation completion, integration verification and measured product improvement are three separate statuses. Unavailable provider credentials, dataset terms or compute are named blockers for the affected lane. Keep the feature and its required evaluation in scope; never replace missing execution with invented metrics.
