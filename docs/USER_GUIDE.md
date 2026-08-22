# The Friendly Rush User Guide

Welcome to Rush! If you are new to code quality tools, static analysis, or pair-programming with AI coding assistants, you are in the right place. This guide is written in plain, human language to help you get up and running in minutes without getting lost in technical jargon.

---

## What is Rush?

Imagine you are building a house. Before handing the keys over to the owner, you want an experienced building inspector to walk through the rooms:
- Is the foundation solid, or are there hidden structural cracks?
- Did someone leave exposed electrical wiring (like leaked API keys or secrets)?
- Are the doors built to standard dimensions so they open smoothly (linting and formatting)?
- Did the builder leave behind unfinished scaffolding or empty closets (dead code and empty stubs)?

**Rush is your automated code inspector and AI copilot safety harness.**

Instead of forcing you to manually configure 15 different complicated command-line tools—each with its own arcane flags, strange output formats, and steep learning curve—Rush gives you a single, unified, friendly front door. You run one simple command, and Rush orchestrates the best tools for your project, presenting clear, actionable feedback.

---

## 1. Getting Started in 30 Seconds

### Step 1: Run your first review
Open your terminal in any project folder and type:

```bash
rush review .
```

### What happens behind the scenes:
Rush instantly inspects your files using lightweight, deterministic rules. It checks for common code smells, unfinished `TODO` markers, bloated functions, and missing docstrings.

If everything looks great, Rush prints a cheerful confirmation. If it spots something worth your attention, it gives you the exact file name and line number, along with a helpful hint explaining why it flagged the line.

---

## 2. The Everyday Workflow (A Day in the Life with Rush)

Here is how thousands of developers and AI agents use Rush throughout their daily coding routine:

```mermaid
flowchart LR
    A["1. Code & Edit"] --> B["2. rush check . (Fast feedback in ms)"]
    B --> C{"Any issues?"}
    C -- Yes --> D["3. rush fix . (Auto-clean formatting)"]
    D --> B
    C -- No --> E["4. rush test . (Verify tests pass)"]
    E --> F["5. rush hook run (Pre-commit check)"]
    F --> G["6. Git Commit & Push with confidence!"]
```

### The 4 Routine Commands:

1. **`rush check .`** (The Quick Health Check):
   - Run this while you are actively writing code. It runs your linters, format checkers, and type checkers together in milliseconds.
2. **`rush fix .`** (The Automatic Broom):
   - Spot some messy indentation, inconsistent quotes, or unused imports? Run `rush fix .` and let Rush safely clean it up for you. (Tip: Use `rush fix . --dry-run` to preview the changes first!)
3. **`rush test .`** (The Safety Net):
   - Runs your unit and integration tests to guarantee that your changes didn't accidentally break existing behavior.
4. **`rush gate .`** (The Pre-Merge Guard):
   - Before opening a Pull Request or merging your branch into `main`, run `rush gate .` to run a comprehensive quality check across all standards.

---

## 3. How to Read Rush Results Without Feeling Overwhelmed

Whenever Rush finishes checking your project, it assigns a clear **Status** to the result:

| Status | What it Means | What You Should Do |
|---|---|---|
| **`OK`** (Green) | Everything looks fantastic! | Celebrate and keep coding. |
| **`WARN`** (Yellow) | Advisory feedback or minor suggestions. | Take a quick look. It won’t break your build, but fixing it will keep your code clean. |
| **`FAIL`** (Red) | A definite issue was found (a broken test, type error, or syntax flaw). | Open the indicated file and line to resolve the error. |
| **`SKIPPED`** (Gray) | An optional tool is not installed on your machine. | Don't worry! Rush skips tools gracefully without crashing. If you want that check, install the tool; otherwise, feel free to ignore it. |
| **`ERROR`** (Red) | Something unexpected happened (like a malformed configuration file). | Check the error message for hints or run `rush doctor .` to diagnose your setup. |

---

## 4. Coding with AI Assistants (Cursor, Claude, Cline & Friends)

If you use AI coding assistants, Rush is your new best friend. AI models are lightning fast, but they can occasionally write repetitive code ("AI slop"), forget to write tests, or propose dangerous commands.

Rush includes dedicated guides for both [Agentic Rush](AGENTIC_RUSH.md) and [Vibecoding with Rush](VIBECODING.md) that protect your codebase:
- **`rush slop .`**: Catches AI hallucinations, repetitive boilerplate, and useless comments.
- **`rush tdd .`**: Verifies that your AI wrote tests for every new feature.
- **`rush safety check-cmd "<cmd>"`**: Intercepts destructive commands before they harm your filesystem.
- **`rush codegraph slice "<symbol>"`**: Slices exact function implementations to save 90% of prompt tokens.

👉 Check out the [Vibecoding Master Portal](VIBECODING.md), the [Working with AI Agents Guide](user-guide/working-with-ai-agents.md), and the [Agentic Rush Knowledge Base](AGENTIC_RUSH.md) to learn more.


---

## 5. Visual Dashboards & Terminal UI

Prefer visual interfaces over terminal text? Rush has you covered:

- **Interactive Terminal UI**:
  ```bash
  rush ui .
  ```
  Launches a keyboard-navigable terminal dashboard to browse findings file by file.

- **Local Web Dashboard**:
  ```bash
  rush dashboard .
  ```
  Opens an authenticated, private web dashboard in your browser (`http://127.0.0.1`) complete with metric charts, vulnerability summaries, and remediation tips.

---

## 6. Deep Dive Chapters

Explore our focused, beginner-friendly guides for specific topics:

- [Everyday Workflow](user-guide/everyday-workflow.md): Step-by-step walkthrough of writing and shipping code with Rush.
- [Checking Code](user-guide/checking-code.md): Everything you need to know about linting, formatting, and typechecking.
- [Checking Project Files](user-guide/checking-project-files.md): Keeping Markdown, YAML, SQL, and Dockerfiles spotless.
- [Testing Confidence](user-guide/testing-confidence.md): Understanding unit tests, code coverage, and test reliability.
- [Security & Supply Chain](user-guide/security-and-supply-chain.md): Keeping secrets safe and dependencies free of vulnerabilities.
- [Understanding Results](user-guide/understanding-results.md): A detailed breakdown of severities, rules, and exit codes.
- [Troubleshooting Guide](user-guide/troubleshooting.md): Quick solutions for common questions and errors.
- [Subsystem Architecture Diagrams](BUNDLE_DIAGRAMS.md): High-level visual maps of all 9 Rush bundles.
