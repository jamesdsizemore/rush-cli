#!/usr/bin/env python3
"""Apply the plan's agent-definition changes to the orch-*.md files in a directory (A2, A3, A4, A5, B7, F15).
usage: patch-agents.py <agents-dir> [--write]      (without --write it prints a unified diff and changes nothing)
Frontmatter: full model id, effort per the matrix, maxTurns, omitClaudeMd, and the exact tool names (ToolSearch,
graft, codegraph and context-mode). Body: the B7 replacements. Creates orch-design-gate.md when absent."""
import difflib
import pathlib
import sys

MATRIX = {  # role: (model id, effort or None, maxTurns)
    "implementer": ("claude-sonnet-5-5", "medium", 100),
    "docs": ("claude-sonnet-5-5", "medium", 135),
    "reviewer": ("claude-opus-5-5", "medium", 80),
    "planner": ("claude-opus-5-5", "medium", 55),
    "adversarial-reviewer": ("claude-opus-5-5", "high", 240),
    "design-gate": ("claude-opus-5-5", "medium", 80),
    "scout": ("claude-haiku-4-5-20251001", None, 60),
    "verifier": ("claude-haiku-4-5-20251001", None, 30),
}
NEED = [
    "ToolSearch",
    "mcp__graft__graft_find_code", "mcp__graft__graft_find_all", "mcp__graft__graft_trace_calls",
    "mcp__graft__graft_file_api", "mcp__graft__graft_repo_map", "mcp__codegraph__codegraph_explore",
    "mcp__plugin_context-mode_context-mode__ctx_batch_execute",
    "mcp__plugin_context-mode_context-mode__ctx_execute",
    "mcp__plugin_context-mode_context-mode__ctx_execute_file",
    "mcp__plugin_context-mode_context-mode__ctx_search",
]
# B7: the sentences that send an agent to read or run more than its prompt gives it.
BODY = {
    "implementer": [(
        "1. Read the cited spans of every file in `allowed_files` and the code it calls (graft) before\n   editing.",
        "1. Your prompt's `## Cited code` and `## Done when` are your map. Call graft only for a symbol they do\n   not show. Read only the lines you will Edit.")],
    "reviewer": [(
        "Read the callers of every\n   changed function and check they still hold.",
        "Trace every changed symbol with\n   `graft_trace_calls`; inspect the caller spans whose behavior or contract the change alters, including\n   an unchanged signature with new semantics.")],
    "adversarial-reviewer": [
        ("Read the real modules.", "Use graft to read the modules the change touches."),
        ("Run the relevant tests yourself when useful.", "Run only the test ids in your prompt. The full suite runs in `gate.sh`.")],
    "docs": [(
        "3. Read a doc in full before editing it.",
        "3. Read the section you edit and its neighboring headings; read a whole doc only when it is under 150 lines.")],
}
DESIGN_GATE = """---
name: orch-design-gate
description: Orchestrator Design Gate. Read-only. Turns one phase-plan task into its packet map: testable behavior, complete code map, exact design of the hard parts, full test matrix, done items, at full scope with no open decisions. Dispatched by the orchestrator skill.
tools: Read, Grep, Glob, Bash
model: sonnet
---

You are the Design Gate for ONE task of an orchestrator run. Read-only: never edit, never change git state.

## Tool stack
Code questions go to graft first (`graft_find_code`, `graft_find_all`, `graft_trace_calls`, `graft_file_api`,
`graft_repo_map`, or the `graft` CLI), then `codegraph_explore`. Any output over 40 lines or file over 200
lines goes through context-mode. Read only the spans your prompt cites plus what these queries return.
Shell commands are `rtk`-prefixed.

## Output: the packet map, and nothing else
Your final message is the map file in the format at the top of `scripts/dispatch-prompt.sh`, one item per line:
`write:` (each allowed file), `change:` (at most 3 exact changes, `path:line` and the change), `test:` (each exact
test id), `done:` (each checkable fact that means the task is finished, a command or a `file:line`), `keep:`
(`<test or path:line> -- <what it asserts>`, the existing behavior to keep), `sym:` (each changed symbol), and
`model: opus` with `model-reason: <file:line>` only for a trust-boundary task. Then the `path:line | role` code map:
every file, symbol and caller the task touches, including files missing from the plan's file list.
Resolve every ambiguity to the design that delivers the full plan scope; write no question. A true grant (a file
outside the approved list, an approval-gated action) goes on one line `GRANT: <what, why, full-scope options>`.

## Rules
- Absolute rules: do not descope, do not degrade, do not report incomplete work as done.
"""


def patch(text, role):
    head, sep, body = text.partition("\n---\n")           # text starts with '---\n'
    lines = head.split("\n")[1:]
    model, effort, turns = MATRIX[role]
    out, seen = [], set()
    for ln in lines:
        key = ln.split(":", 1)[0]
        if key == "tools":
            have = [t.strip() for t in ln.split(":", 1)[1].split(",") if t.strip()]
            have = [t for t in have if t != "mcp__plugin_context-mode_context-mode"]   # server-level name: replaced by exact names
            ln = "tools: " + ", ".join(have + [t for t in NEED if t not in have])
        elif key == "model":
            ln = f"model: {model}"
        elif key == "effort":
            if effort is None:
                continue
            ln = f"effort: {effort}"
        elif key in ("maxTurns", "omitClaudeMd"):
            continue
        seen.add(key)
        out.append(ln)
    if effort and "effort" not in seen:
        out.append(f"effort: {effort}")
    out += [f"maxTurns: {turns}", "omitClaudeMd: true"]
    for old, new in BODY.get(role, []):
        if new in body:          # already applied: running the patch twice changes nothing
            continue
        if body.count(old) != 1:
            sys.exit(f"orch-{role}.md: the sentence to replace occurs {body.count(old)} times, expected 1: {old[:60]!r}")
        body = body.replace(old, new)
    return "---\n" + "\n".join(out) + "\n---\n" + body


def main():
    d, write = pathlib.Path(sys.argv[1]), "--write" in sys.argv
    for role in MATRIX:
        p = d / f"orch-{role}.md"
        old = p.read_text() if p.exists() else (DESIGN_GATE if role == "design-gate" else None)
        if old is None:
            sys.exit(f"missing {p}")
        new = patch(old, role)
        sys.stdout.writelines(difflib.unified_diff(old.splitlines(True), new.splitlines(True), str(p), str(p)))
        if write:
            p.write_text(new)


if __name__ == "__main__":
    main()
