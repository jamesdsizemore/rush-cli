# Token Economy & Context Optimization

Context is the single most valuable resource in modern AI software engineering. Dumping entire source files, massive dependency graphs, and full build outputs into an LLM's prompt window leads to three severe problems:
1. **High Latency & Costs**: Multi-megabyte prompts slow down agent response times and rack up huge API bills.
2. **Context Window Saturation**: Passing unnecessary boilerplate pushes crucial instructions and system prompts out of the attention window.
3. **"Needle in a Haystack" Amnesia**: LLMs struggle to find critical details when buried inside thousands of lines of irrelevant code.

Rush’s **Token Economy Subsystem** (`rush token`) provides local BPE accounting and bounded transformations. Token reduction is reported only for the concrete input; it is not a promised provider-cost or model-performance saving.

---

## 1. Accurate Offline Token Counting

Rush calculates exact BPE token counts for files, diffs, and prompt strings locally without requiring any network calls or API keys.

```bash
# Count tokens for a single file or directory
rush token count src/rush/cli.py
# Output:
# File: src/rush/cli.py (1,759 lines)
# Total BPE Tokens: 18,420 tokens (cl100k_base / o200k_base)

# Compare token density across your workspace
rush token count src/ --top 10
```

Supported tokenizers include `cl100k_base` (GPT-4 / Claude estimation) and `o200k_base` (GPT-4o).

---

## 2. AST Outline Compression

When an AI agent needs to understand a module's architecture or public API, it rarely needs the full implementation bodies or verbose internal docstrings.

The `rush token outline` command parses the source code's Abstract Syntax Tree (AST) and extracts a lean, type-annotated structural skeleton:

```bash
# Generate an AST outline of a module
rush token outline src/rush/tools/review.py
```

### Compression Comparison

```python
# Raw Source (120 lines, 1,450 tokens):
class ReviewTool(Tool):
    """Deep review heuristics engine for static code analysis..."""
    def __init__(self, config: RushConfig):
        self.config = config
        self._cache = {}
        ... 80 lines of helper methods ...
    def run(self, path: Path, *, changed_file: list[str] | None = None) -> ToolResult:
        ... 40 lines of implementation logic ...

# Compressed AST Outline (18 lines, 160 tokens — 89% token savings!):
class ReviewTool(Tool):
    config: RushConfig
    def __init__(self, config: RushConfig) -> None: ...
    def run(self, path: Path, *, changed_file: list[str] | None = None) -> ToolResult: ...
```

---

## 3. Prompt Diet & Context Advisor

The `rush token cache-advisor` scans your repository and prompt templates to recommend optimal prompt layouts for LLM prompt caching (such as Anthropic Prompt Caching and OpenAI Prefix Caching).

```bash
# Analyze prompt efficiency and cache readiness
rush token cache-advisor
```

- Groups static system instructions, tool definitions, and repository rules at the start of prompts.
- Separates dynamic, frequently-changing context (like active diffs) at the tail of prompts.
- Maximizes cache hit rates to cut API latency by up to 50%.

---

## Next Steps

- Discover how to query specific function slices in [CodeGraph & Semantic Slicing](codegraph-and-semantic-slicing.md).
- Learn how to synchronize backend models with frontend types in [Codebase Hygiene & AST Merges](codebase-hygiene-and-ast-merging.md).
