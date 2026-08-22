# Token Diet for Vibecoders: Slash LLM Costs & Latency

As a vibecoder, your primary currency is **tokens**.

Every time you paste a 1,500-line file into Cursor or Claude Code, two things happen:
1. **You pay for all 1,500 lines** on every single turn of the conversation.
2. **The AI gets slower and dumber**: Large context windows dilute the model's attention, leading to missed instructions and subtle bugs.

Rush's **Token Economy Subsystem** (`rush token`) and **CodeGraph Engine** (`rush codegraph`) put your AI prompts on a strict, high-efficiency token diet.

---

## 1. Verbatim Slicing with `rush codegraph`

Suppose you want to add a retry loop to a function called `send_webhook`. The function lives in a file with 1,200 lines of unrelated code.

### The Old Way (Wasteful):
You paste all 1,200 lines into the chat window. (Cost: ~4,500 tokens).

### The Rush Way (Lean & Fast):
```bash
rush codegraph slice "send_webhook"
```

Rush extracts just the 15-line function implementation with line numbers:
```python
# [src/services/webhooks.py:48-63]
48: def send_webhook(url: str, payload: dict) -> bool:
49:     response = requests.post(url, json=payload, timeout=5)
50:     return response.status_code == 200
```
(Cost: ~85 tokens — **a 98% reduction!**).

Your AI gets the exact lines it needs to write a clean diff patch, responds in 1 second instead of 8 seconds, and costs pennies.

---

## 2. AST Outline Compression with `rush token outline`

What if the AI needs to understand an entire module's architecture or class hierarchy without needing the internal implementation bodies?

```bash
rush token outline src/services/billing.py
```

Rush parses the Abstract Syntax Tree (AST) and generates a compact, type-annotated outline:
```python
class BillingService:
    config: BillingConfig
    def __init__(self, config: BillingConfig) -> None: ...
    def create_subscription(self, user_id: str, plan: str) -> Subscription: ...
    def cancel_subscription(self, sub_id: str) -> bool: ...
```

This outline provides 100% of the architectural context needed for your AI to write integration code, while stripping out 85% of the token weight.

---

## 3. Counting Tokens Locally with `rush token count`

Curious how many tokens your repository or prompt templates take up?

```bash
# Count BPE tokens for any file locally (zero network calls)
rush token count src/main.py

# Find the heaviest token hogs in your repository
rush token count src/ --top 5
```

---

## Next Steps

- Learn how to ship production code with confidence in [Shipping with Swagger](shipping-with-swagger.md).
- Get ready-to-use prompt templates in [Vibecoder Cheat Sheet & Golden Prompts](cheat-sheet.md).

## Built-In Token Reduction Subsystems (Phases 41–43)

Rush now provides native token reduction tools directly in the CLI and FastMCP server:
* **`rush token outline <path>`**: Uses `AstSkeletonizer` to replace function bodies with `...`, allowing your agent to read entire module interfaces in under 200 tokens.
* **`--format toon`**: Formats findings and tables as compact pipe-tables instead of verbose JSON.
* **Command Distillation**: Automatically filters pytest and cargo noise to send only failing assertions.
* **CCR Caching**: Stores large outputs in SQLite (`.rush/cache/ccr.db`) and injects `<!-- ccr:chunk:HASH -->` tags.

## Context Packing & Stale Read Sweeping (Phases 44–45)
* `rush context pack`: Packs exact symbols under token budgets.
* StaleSweeper: Prunes old turns to single-line summaries.
* `rush context persona --set terse`: Trims filler words from outputs.



## Flaky Test Diet
Stop re-running test suites 10 times in AI context—use `rush test-heal` to diagnose non-determinism in one step.



## Complexity Diet
Decomposing 200-line monolithic functions with `rush simplify` reduces the context tokens needed for subsequent code edits by up to 50%.



## Swarm Merge Token Diet
Instead of feeding full merge conflicts into LLMs, `rush swarm-merge` reconciles non-overlapping edits deterministically with zero token overhead.

