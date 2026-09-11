# Vibecoding with Rush: Guides & Tutorials

Welcome to the official **Vibecoding with Rush** guides!

Vibecoding is the art and science of building real-world software by directing AI models through natural language prompts. When done right, it makes software development feel like pure magic.

These guides will teach you how to set up Rush as your AI copilot's automated safety harness, run supercharged prompt workflows, purge AI hallucinations, slash API token bills, and ship production-ready applications with complete confidence.

---

## The Guides

1. [What is Vibecoding with Rush?](what-is-vibecoding-with-rush.md)
   - The philosophy of rapid creative flow meets bulletproof automated quality.
2. [The Vibecoder Workflow](the-vibecoder-workflow.md)
   - Step-by-step walkthrough of a friction-free vibecoding session from initial prompt to green tests.
3. [Setting Up Your AI Agent](setting-up-your-agent.md)
   - How to connect Rush to Cursor, Claude Code, Cline, Windsurf, Roo Code, and GitHub Copilot via FastMCP.
4. [Slop-Busting & Hallucination Defense](slop-busting-and-hallucination-defense.md)
   - How `rush slop`, `rush tdd`, and `rush review` catch AI mistakes, empty placeholder stubs, and redundant comments.
5. [Fix command: bounded Ruff remediation](instant-fix-and-auto-remediation.md)
   - Current preview/apply route; P64-04 patch cleanup remains planned.
6. [Token Diet for Vibecoders](token-diet-for-vibecoders.md)
   - How `rush token` and `rush codegraph` compress code context by 70–90%, slashing LLM latency and costs.
7. [Shipping with Swagger](shipping-with-swagger.md)
   - Generating 6-pillar repository health scorecards (`rush score`), SVG quality badges, and automated changelogs.
8. [Vibecoder Cheat Sheet & Golden Prompts](cheat-sheet.md)
   - Copy-paste prompts and terminal recipes to supercharge your AI coding assistants.

---

## Quick Command Reference for Vibecoders

- `rush watch .`: Starts live background monitoring with auto-re-evaluation.
- `uv run rush fix --help`: Preview bounded Ruff remediation with `uv run rush fix . --dry-run --force`; apply requires `--allow-artifact-write`.
- `rush slop .`: Flags AI hallucinations, empty placeholder methods, and filler comments.
- `rush tdd .`: Confirms that your AI assistant actually wrote tests for the new code.
- `rush score compute`: Computes your repository's health grade (A+ to F).
