"""Automated Multi-Tier Documentation Engine for Rush Phase Implementations.

Ensures that every phase implementation automatically audits and updates all 27+
documentation files across every category in the repository.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def update_docs_for_phase(
    project_root: Path,
    phase_num: int,
    phase_title: str,
    cli_commands: list[dict[str, str]],
    mcp_tools: list[dict[str, str]],
    specs: list[dict[str, str]],
    workflows: list[dict[str, str]],
    architecture_notes: str,
    glossary_terms: dict[str, str],
    faq_items: list[dict[str, str]],
) -> None:
    docs = project_root / "docs"
    if not docs.exists():
        print(f"Error: {docs} not found.")
        return

    # 1. Specs & Workflows
    (docs / "specs").mkdir(parents=True, exist_ok=True)
    (docs / "workflows").mkdir(parents=True, exist_ok=True)

    for spec in specs:
        spec_path = docs / "specs" / spec["filename"]
        if not spec_path.exists():
            spec_path.write_text(spec["content"].strip() + "\n", encoding="utf-8")
            print(f"[CREATED] {spec_path}")

    for wf in workflows:
        wf_path = docs / "workflows" / wf["filename"]
        if not wf_path.exists():
            wf_path.write_text(wf["content"].strip() + "\n", encoding="utf-8")
            print(f"[CREATED] {wf_path}")

    # 2. CLI_REFERENCE.md
    cli_ref = docs / "CLI_REFERENCE.md"
    if cli_ref.exists():
        t = cli_ref.read_text(encoding="utf-8")
        cli_entries = []
        for cmd in cli_commands:
            if f"### `{cmd['name']}`" not in t:
                cli_entries.append(f"### `{cmd['name']}`\n{cmd['description']}\n* Syntax / Options: `{cmd.get('syntax', '')}`\n")
        if cli_entries:
            header = f"\n## Phase {phase_num}: {phase_title} Commands\n\n"
            t += header + "\n".join(cli_entries)
            cli_ref.write_text(t, encoding="utf-8")
            print(f"[UPDATED] {cli_ref}")

    # 3. MCP_REFERENCE.md
    mcp_ref = docs / "MCP_REFERENCE.md"
    if mcp_ref.exists():
        t = mcp_ref.read_text(encoding="utf-8")
        mcp_entries = []
        for tool in mcp_tools:
            if f"`{tool['name']}`" not in t:
                mcp_entries.append(f"* **`{tool['name']}({tool.get('params', '')})`**: {tool['description']}")
        if mcp_entries:
            header = f"\n## Phase {phase_num} FastMCP Tools\n\n"
            t += header + "\n".join(mcp_entries) + "\n"
            mcp_ref.write_text(t, encoding="utf-8")
            print(f"[UPDATED] {mcp_ref}")

    # 4. README.md
    readme = docs / "README.md"
    if readme.exists():
        t = readme.read_text(encoding="utf-8")
        header = f"## Phase {phase_num}: {phase_title}"
        if header not in t:
            body = f"\n{header}\n{architecture_notes}\n"
            for cmd in cli_commands:
                body += f"* `{cmd['name']}`: {cmd['description']}\n"
            t += "\n" + body
            readme.write_text(t, encoding="utf-8")
            print(f"[UPDATED] {readme}")

    # 5. ARCHITECTURE.md
    arch = docs / "ARCHITECTURE.md"
    if arch.exists():
        t = arch.read_text(encoding="utf-8")
        header = f"## Phase {phase_num} Subsystems: {phase_title}"
        if header not in t:
            t += f"\n{header}\n\n{architecture_notes}\n"
            arch.write_text(t, encoding="utf-8")
            print(f"[UPDATED] {arch}")

    # 6. GLOSSARY.md & getting-started/glossary.md
    gl = docs / "GLOSSARY.md"
    if gl.exists():
        t = gl.read_text(encoding="utf-8")
        gl_entries = [f"* **{term}**: {defn}" for term, defn in glossary_terms.items() if f"**{term}**" not in t]
        if gl_entries:
            t += f"\n### Phase {phase_num} Terms\n" + "\n".join(gl_entries) + "\n"
            gl.write_text(t, encoding="utf-8")
            print(f"[UPDATED] {gl}")

    # 7. FAQ.md & user-guide/faq.md
    faq = docs / "FAQ.md"
    if faq.exists():
        t = faq.read_text(encoding="utf-8")
        faq_entries = []
        for item in faq_items:
            if f"### {item['q']}" not in t:
                faq_entries.append(f"### {item['q']}\n{item['a']}\n")
        if faq_entries:
            t += f"\n## Phase {phase_num} FAQ\n\n" + "\n".join(faq_entries)
            faq.write_text(t, encoding="utf-8")
            print(f"[UPDATED] {faq}")

    # 8. User Guides & Agentic Guides
    for file_rel in [
        "USER_GUIDE.md",
        "AGENTIC_RUSH.md",
        "CLI_COOKBOOK.md",
        "VIBECODING.md",
        "developer/architecture.md",
        "developer/source-tree.md",
        "developer/contributor-onboarding.md",
        "user-guide/advanced-checks.md",
        "user-guide/checking-code.md",
        "user-guide/everyday-workflow.md",
        "user-guide/working-with-ai-agents.md",
        "vibecoding/token-diet-for-vibecoders.md",
        "vibecoding/the-vibecoder-workflow.md",
        "tutorials/ai-coding-assistant.md",
        "tutorials/before-a-pull-request.md",
        "maintainers/release-playbook.md",
        "maintainers/architecture-lifecycle.md",
        "agentic-rush/token-efficiency.md",
    ]:
        p = docs / file_rel
        if p.exists():
            t = p.read_text(encoding="utf-8")
            sec_header = f"Phase {phase_num}: {phase_title}"
            if sec_header not in t:
                t += f"\n\n## {sec_header}\n{architecture_notes}\n"
                for cmd in cli_commands:
                    t += f"* `{cmd['name']}`: {cmd['description']}\n"
                p.write_text(t, encoding="utf-8")
                print(f"[UPDATED] {p}")

    print(f"\n[DONE] Full-corpus documentation updated for Phase {phase_num}.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Update full docs corpus for a phase")
    parser.add_argument("--meta", required=True, help="Path to JSON file containing phase metadata")
    args = parser.parse_args()

    meta_file = Path(args.meta)
    if not meta_file.exists():
        print(f"Metadata file {meta_file} not found.")
        exit(1)

    data = json.loads(meta_file.read_text(encoding="utf-8"))
    update_docs_for_phase(
        project_root=Path.cwd(),
        phase_num=data["phase_num"],
        phase_title=data["phase_title"],
        cli_commands=data.get("cli_commands", []),
        mcp_tools=data.get("mcp_tools", []),
        specs=data.get("specs", []),
        workflows=data.get("workflows", []),
        architecture_notes=data.get("architecture_notes", ""),
        glossary_terms=data.get("glossary_terms", {}),
        faq_items=data.get("faq_items", []),
    )
