# Rush Epistemic Memory & Coding Agent Substrate

## Bounded recovery references

Context omissions are stored only after redaction as local CCR chunks and exposed by a stable handle. Coordination recovery can add mined git-revert guardrails as `historical_evidence`; these are context for judgment, never executable instructions or a trigger for retry.

## 1. Why Existing Agent Memory Fails

Current agent memory implementations (chat history summaries, vector databases, or static `.cursorrules` / `AGENTS.md` files) break down because they treat all text equally:
* **No distinction between proof and guesswork:** An unverified assumption made by an agent in Turn 3 is stored alongside a verified test result or explicit user instruction. Future sessions treat guesses as ground truth.
* **No invalidation when code changes:** When code is refactored, past memories about function signatures, API behavior, or test assumptions become silently toxic, poisoning future agent turns with stale information.
* **Context pollution:** Dumping memory files into every prompt burns token budgets and dilutes the model's focus on the active task.

The continuity receipt therefore carries only selected current goal/open work, hashes for declared dependencies, and bounded failure evidence. A historic instruction is explicitly `historical_evidence` and `quarantined`, never an executable authority; restore marks mismatched snapshots stale instead of silently reusing them.

---

## 2. The Core Primitives of Rush Memory

```
┌──────────────────────────────────────────────────────────────────────────┐
│                           RUSH EPISTEMIC LEDGER                          │
│                                                                          │
│  [PROVEN EVIDENCE]     Backed by test runs, compiler output, AST proofs │
│  [USER INTENT]         Explicit human instructions & business rules      │
│  [OBSERVED CONVENTION] Mined patterns from git history & codebase style   │
│  [AGENT HYPOTHESIS]    Unverified assumptions (marked for proof/death)   │
└──────────────────────────────────────────────────────────────────────────┘
                                   │
              ┌────────────────────┴────────────────────┐
              ▼                                         ▼
   [Symbol-Bound Context]                     [Active Invalidation]
   Hydrated only when the                     Demoted to STALE when
   agent touches the target symbol            underlying AST changes
```

### A. The Grounded Epistemic Record
Every piece of knowledge stored by Rush in `.rush/memory/` is a structured record with four mandatory fields:

1. **Epistemic Class**:
   * `PROVEN_EVIDENCE`: Fact verified by a deterministic tool (e.g., passing test, type check, AST signature).
   * `USER_INTENT`: Direct requirement from the developer (e.g., "Always use UUID for user IDs").
   * `OBSERVED_CONVENTION`: Established repository pattern mined from git history or existing code.
   * `AGENT_HYPOTHESIS`: An assumption an agent made during planning that has not yet been verified.
2. **Grounding Hash**: The exact SHA-256 hash of the AST node, test output, or commit that generated the record.
3. **Invalidation Watchers**: The list of file paths and symbol names that, if modified, instantly transition this record to `STALE`.
4. **Scope**:
   * `SESSION`: Ephemeral to the active task (deleted on task completion).
   * `REPO`: Durable to the project (stored in `.rush/ledger/`).
   * `USER`: Cross-repo developer preferences.

---

## 3. The Coding Agent & MCP Lifecycle

### Step 1: Just-in-Time Context Hydration (Zero Bloat)
Rush does not inject the entire memory ledger into the agent's prompt. 

When an agent invokes a tool or opens a file (e.g., `src/auth/session.py`):
1. Rush identifies the target symbols in that file.
2. Rush queries the Epistemic Ledger for active, verified records bound to those specific symbols.
3. Rush filters out all `STALE` records.
4. Rush injects a high-density, symbol-scoped context block into the tool response:
   ```xml
   <rush_grounded_context symbol="SessionManager.create_token">
     <user_intent>Token expiry must be configurable via ENV (Turn 2)</user_intent>
     <proven_evidence test="tests/test_auth.py:42">Returns JWT with HS256 algorithm</proven_evidence>
     <negative_pattern failed_commit="c4a12">Do not store raw session tokens in memory cache</negative_pattern>
   </rush_grounded_context>
   ```

### Step 2: Automatic Invalidation on Code Changes
When an agent or developer edits `src/auth/session.py`:
1. Rush compares the new AST against the Grounding Hashes in the ledger.
2. If `SessionManager.create_token` changed its signature or return type, all dependent records (e.g., "Returns JWT with HS256") automatically transition from `PROVEN_EVIDENCE` $\rightarrow$ `STALE`.
3. The next agent turn receives an explicit invalidation notice:
   ```xml
   <rush_stale_alert symbol="SessionManager.create_token">
     Prior assumption [Returns JWT with HS256] was invalidated by recent edit on line 45.
     Re-verification via test run required before downstream consumers can be modified.
   </rush_stale_alert>
   ```

### Step 3: Learning from Real Rejections (Negative Invariant Extraction)
When a test fails, a patch is reverted, or a developer rejects an agent's change:
1. Rush extracts the AST difference of the rejected change and the error trace or user review comment.
2. Rush creates a `NEGATIVE_INVARIANT` record bound to the modified symbol:
   * *Target Symbol:* `PaymentService.charge`
   * *Pattern:* Missing retry backoff on `StripeNetworkError`
   * *Reason:* Failed in Turn 4 with connection timeout
3. On all future turns touching `PaymentService.charge`, the agent is actively constrained from proposing that same structural pattern again.

### Step 4: Structured Task Handoffs (Across Models & Agents)
When handing off work from one agent (or model provider) to another:
* Rush generates a **Task Handoff Capsule** (`.rush/capsules/<task_id>.json`) containing:
  1. `Declared Goal`: The initial user requirement.
  2. `Proven Progress`: List of files modified with green test proofs.
  3. `Active Hypotheses`: What the prior agent was currently testing.
  4. `Known Dead Ends`: Negative invariants discovered during this task.
  5. `Remaining Obligations`: Broken tests or unwritten layers.
* The incoming agent (whether running Claude, Codex, or DeepSeek) reads the capsule in 1 call and resumes execution immediately without re-exploring the codebase or repeating failed attempts.

---

## 4. MCP Tool & Hook Contracts

| Component | Type | Responsibility |
|---|---|---|
| `rush_memory_hydrate` | Tool / Resource | Returns only the active, verified, non-stale records for a specific file or symbol. |
| `rush_memory_record_intent` | Tool | Registers an explicit user requirement into the ledger with associated AST scope. |
| `rush_memory_record_proof` | Hook (Post-Test) | Automatically promotes an `AGENT_HYPOTHESIS` to `PROVEN_EVIDENCE` when a test passes. |
| `rush_memory_invalidate` | Hook (Post-Edit) | Scans AST deltas and demotes dependent records to `STALE`. |
| `rush_task_capsule` | Tool / Resource | Creates and loads provider-portable task handoff capsules. |

---

## 5. Summary of Differences from Commodity Approaches

| Problem | Commodity / Chat Approach | Rush Epistemic Substrate |
|---|---|---|
| **Memory Accuracy** | Chat transcripts mix guesses and facts | Strict epistemic classes (`PROVEN`, `INTENT`, `HYPOTHESIS`) |
| **Code Evolution** | Stale advice stays in memory forever | AST-hashed invalidation triggers when code changes |
| **Context Overhead** | Giant global rules files dumped every turn | Symbol-scoped context injected only at the active edit site |
| **Error Learning** | Agents repeat the same bug across sessions | AST negative invariants prevent re-attempting failed patterns |
| **Model Switching** | Context lost when switching providers | Open, structured task capsules restore exact task state |
