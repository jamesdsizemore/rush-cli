# Rush Documentation Rewrite Brief

## Purpose

Create a complete, polished, beginner-friendly product documentation system for Rush. The current documentation is not sufficient when it reads like internal engineering notes rather than help for a new user.

Rush documentation serves **two distinct audiences**. Keep them rigorously separate:

1. **Users** — developers who may never have heard of Rush or MCP and want simple, practical help.
2. **Contributors** — maintainers who need implementation, architecture, testing, and extension guidance.

Never lead user documentation with internal terms such as registry, adapter, routing layer, schema, subprocess boundary, or catalog parity. Explain those only in developer documentation.

---

# User documentation

## Voice and standard

Write in a warm, clear, confident, product-oriented voice. Assume the reader is intelligent but new to Rush. Explain unfamiliar terms immediately. Favor plain statements:

- “Rush checks your project with the quality tools you already use.”
- “If a checker is not installed, Rush tells you what is missing.”
- “Run one small set of checks before opening a pull request.”

Every page must answer some combination of: what is this, why does it matter, when should I use it, what do I need, what exact steps do I take, what result should I expect, and what should I do next?

## Implemented-model capability boundary

Document model capabilities exactly as implemented. Rush does **not** run local
models. Its default `review` behavior is local deterministic Python heuristics.
`review --use-graft` may use optional local Graft context when explicitly
requested. The `review --llm` path is currently a deterministic development
stub: it detects an Anthropic/OpenAI environment key but does not make a real
provider call. Do not market, document, or configure it as a functioning local
or hosted AI review feature. If model support is implemented later, document
providers, local runtime support, data boundaries, consent, configuration,
failure behavior, and privacy only after verifying the implementation.

## Root README

Rewrite the root README as product onboarding.

It must include:

- A clear headline and concise value proposition.
- Plain-English explanations of **what Rush is**, **why it exists**, and **why a developer would use it**.
- A feature section centered on outcomes: review code before a PR; lint/format; run tests; dependency security; secret scanning; content and infrastructure checks; use with coding assistants.
- A clear “what Rush does not do” section: no silent rewrites, no implicit installs, no release publication, no tag/history rewriting, and no network service.
- A copy/paste three-step quick start.
- Realistic command output followed by “What this means.”
- A “choose your next step” section that points users to tutorials.
- A simple visual diagram showing the user or coding assistant, Rush, and existing quality tools.
- A documentation map organized by reader goal.

## User guide

Create `docs/USER_GUIDE.md` as a true beginner user manual. Organize it around a person’s goals, not source modules.

Required chapters:

### Welcome to Rush

Explain what Rush is, who it is for, the everyday problems it solves, and when to use it: before a pull request, after an AI coding session, while introducing CI, and while cleaning up a project.

### Before you begin

Explain what must be installed. Explain Python and uv without assuming expertise. Explain optional quality tools in simple language and what happens when one is missing.

### Your first Rush check

Give a copy/paste setup path. Start with `review`. Show realistic output. Explain each visible part of the result in plain English and tell the reader what to do next.

### The everyday workflow

Tell a practical story: “You finished a feature. Before opening a PR, run these checks.” Cover:

```bash
rush review .
rush lint .
rush format . --check
rush test .
rush security .
```

For every command, explain what it checks, why it matters, what a good result looks like, what warnings/failures mean, and what to do next.

### Understanding results

Explain `ok`, `warn`, `fail`, `error`, and `skipped` with plain examples. Make clear that `skipped` often means there was nothing relevant to check or an optional helper is not installed; it does not automatically mean the project is broken.

### Use Rush for common jobs

Create practical walkthroughs for checking a Python project; JavaScript/TypeScript project; mixed-language repository; Markdown/YAML/SQL/Dockerfile; secrets; software bill of materials; commit message; and GitHub Actions workflow. Each includes commands, outcomes, and next actions.

### Optional advanced checks

Explain browser tests, mutation tests, fuzzing, load testing, snapshots, visual checks, and semantic drift as optional capabilities. Explain permission flags simply: Rush requires explicit consent before slow, browser-based, networked, or baseline-changing work.

### Use Rush with an AI coding assistant

Introduce MCP without protocol jargon: “MCP lets compatible coding assistants ask Rush to inspect your project while they work.” Give exact setup steps and useful agent requests.

### Configure Rush for my project

Describe `rush.toml` as a small project settings file. Explain each setting before its syntax. Include beginner examples for a Python app, TypeScript app, monorepo, and stricter team policy.

### When something goes wrong

Use symptom → likely reason → exact fix for skipped checks, missing tools, missing configuration, wrong Python, coding-assistant connection problems, and permission-required errors.

## Tutorials

Create `docs/TUTORIALS.md` as guided lessons, not a command list:

1. Your first 10 minutes with Rush
2. Set up a Python project quality check
3. Set up a JavaScript/TypeScript quality check
4. Use Rush before every pull request
5. Connect Rush to an AI coding assistant
6. Add Rush to CI without installing every language tool

Every tutorial needs an outcome, prerequisites, numbered steps, exact commands, expected results, explanations, and a next step.

## Command guide

Create `docs/CLI_REFERENCE.md`, organized by user intent. For every command document: purpose, when to use it, basic command, useful options, what it checks, possible results, whether it modifies anything, required optional tools in plain language, and related commands. Include a “Which command should I run?” decision tree.

## Engine/setup guide

Explain engines as optional helpers: Rush works with tools such as Ruff, ESLint, pytest, and pip-audit, but does not force users to install all of them. For every supported engine, explain what it checks, who needs it, platform-appropriate install commands, how Rush decides to use it, and what users see when it is missing.

## Troubleshooting and safety

Create user-facing troubleshooting and safety guides. Explain permissions and defaults in everyday terms. Include diagrams where they make an action or boundary easier to understand.

## Required documentation architecture

Do not limit delivery to a README, a user guide, and a developer guide. Build
a complete documentation system with the following information architecture.

```text
README.md                         Product landing page and short onboarding

docs/
  getting-started/
    installation.md               Platform-specific installation
    first-run.md                  First ten minutes, with expected output explained
    glossary.md                   Plain-English terminology
  user-guide/
    index.md                      Friendly start-here table of contents
    everyday-workflow.md          Before-PR and after-AI-session workflow
    understanding-results.md      ok / warn / fail / error / skipped
    checking-code.md              Python, JS/TS, and mixed repository workflows
    checking-project-files.md     Markdown, YAML, SQL, Dockerfile, Actions
    security-and-supply-chain.md  dependencies, secrets, SBOM
    testing-confidence.md         tests, coverage, snapshots, visual, flaky
    advanced-checks.md            e2e, fuzz, load, mutation, semantic drift
    working-with-ai-agents.md     User-friendly MCP/agent workflows
    troubleshooting.md            Symptom, reason, and exact fix
    faq.md                        Practical common questions
  tutorials/
    first-10-minutes.md
    python-project.md
    typescript-project.md
    mixed-language-project.md
    before-a-pull-request.md
    ci-integration.md
    ai-coding-assistant.md
    team-adoption.md
  reference/
    cli-reference.md
    result-reference.md
    configuration-reference.md
    configuration-cookbook.md
    engine-directory.md
    mcp-tool-reference.md
    environment-variables.md
    compatibility.md
  integrations/
    mcp-overview.md
    mcp-client-setup.md
    ci-overview.md
    github-actions.md
    scripts-and-automation.md
  safety/
    safety-overview.md
    permissions.md
    privacy-and-data-handling.md
    security-model.md
  developer/
    contributor-onboarding.md
    architecture.md
    source-tree.md
    tool-development.md
    engine-development.md
    routing-development.md
    configuration-development.md
    mcp-development.md
    testing-guide.md
    ci-and-packaging.md
    release-process.md
    debugging-guide.md
    coding-standards.md
  maintainers/
    support-runbook.md
    incident-and-security.md
    versioning-and-compatibility.md
    documentation-style-guide.md
    adr/
```

The exact directory names may be improved where a clearer navigation model is
better, but every audience, topic, and operational responsibility above must
have a substantive home.

## Additional user-facing requirements

### Product overview and value proposition

Create an explicit product-overview document or README section that explains
why Rush exists and differentiates it from manually running Ruff, ESLint, or
pytest. Explain the user benefit: one safe, consistent interface across their
existing quality tools, local terminal workflow, CI, and compatible AI coding
assistants.

### Platform installation manual

Document Windows, macOS, and Linux installation separately. Cover Python 3.12,
uv, clone/source use, wheel use, PATH verification, tool isolation, expected
success output, and recovery steps. Include corporate proxy/offline guidance if
the implementation supports it; otherwise explicitly state the boundary.

### Result and exit-code reference

Create a complete user-readable reference for ToolResult fields, findings,
status values, exit behavior, JSON consumption, and CI/shell decisions. Show
the difference between `skipped`, `error`, `fail`, and `warn` through examples.

### Configuration cookbook

In addition to a field reference, provide complete annotated configurations for
a Python project, JS/TS project, multi-language repository, monorepo, strict
team policy, and CI-oriented policy. Explain every choice and its effect.

### Complete engine directory

Do not dump raw metadata. For each supported engine document what it checks,
who benefits, exact supported-platform install commands, commands that use it,
how project applicability is detected, the missing-engine experience, and
common failure recovery.

### Agent and MCP adoption guide

Explain the user experience of using Rush with a coding assistant before
introducing MCP terminology. Provide concrete client setup only for clients
supported by verified repository information; otherwise present a generic stdio
template and label it as generic. Include useful prompts such as “review files
I changed,” “run relevant tests,” and “tell me what checker is missing.”

### CI and automation guide

Provide a CI story, GitHub Actions walkthrough, JSON/exit-code guidance, and
bounded-engine strategy. Explain how teams should choose checks instead of
installing every possible runtime.

### FAQ, glossary, privacy, and safety

Include an approachable FAQ, a glossary for quality/MCP terminology, a privacy
and data-handling guide covering local execution, optional LLM use, logging,
and secret redaction, and a permission guide covering browser, slow, network,
fuzz, baseline, and release boundaries.

---

# Developer documentation

Keep all implementation detail in a separate `docs/DEVELOPER_GUIDE.md` and companion architecture documentation.

Cover:

- Source tree and module responsibilities.
- Canonical catalog and registration architecture.
- `ToolFn` and ToolResult contracts.
- Engine adapters, parsers, and external process behavior.
- CLI/MCP shared implementation rule.
- Configuration discovery, precedence, and catalog validation.
- Multi-language routing and aggregation.
- Subprocess stdin safety, structured logging, and redaction.
- Exact recipes for adding a tool, engine, configuration field, language route, and safety-gated operation.
- Test layers, fixtures, CI design, package validation, and release-candidate validation.
- Contributor standards and PR checklist.

Use diagrams for CLI/MCP convergence, catalog-to-registration flow, engine execution/result normalization, and configuration discovery/precedence.

## Additional developer and maintainer requirements

Create documents or chapters that separately cover:

- Contributor onboarding from clone through first passing verification on every
  supported platform, including Windows/PATH/Python-environment troubleshooting.
- A source-tree guide that assigns responsibility to each major package, module,
  test family, fixture set, CI file, and documentation area.
- A complete tool-authoring guide with a worked example: catalog metadata,
  implementation, result contract, CLI/MCP exposure, configuration, tests,
  docs, and safety review.
- A complete engine-authoring guide: binary discovery, subprocess contract,
  parser fixtures, install hints, markers/extensions, skip behavior, redaction,
  and bounded-CI expectations.
- A routing/language-support guide: detection, aggregation, deterministic order,
  adding language markers, and external-engine test isolation.
- A testing guide explaining unit, contract, parser fixture, routing, CLI, MCP
  stdio, installed-engine, packaging, clean-clone, and remote-CI tests.
- An MCP developer guide for tool signatures, schema constraints, stdout/stderr
  rules, environment behavior, real-server tests, and compatibility rules.
- Packaging and release runbooks: versioning, wheel/sdist build, clean install,
  audit, release-candidate validation, explicit tag/publish authorization.
- Maintainer runbooks for bug reports, missing engines, security reports,
  Windows environment contamination, and CI triage.
- Architecture Decision Records for stdio-only MCP, external engine discovery,
  catalog-driven metadata, safety gates, fixture-first tests, bounded CI, and
  Git-root-limited configuration discovery.
- A documentation style guide that defines user language versus developer
  language, required examples, terminology, diagram standards, and the docs
  that must change for a new tool, engine, or configuration field.

---

# Execution and quality requirements

- Use the implementation, generated CLI help, catalog, configuration model, engine adapters, MCP server, tests, CI workflow, and package metadata as source of truth.
- Do not claim a feature that is not implemented or tested.
- Do not omit experimental or safety-gated commands.
- Preserve the product’s safety guarantees: no implicit installs, no history mutation, no publishing by default, no browser/network/slow work without consent, and no secrets in logs/results.
- Write substantial explanatory prose; tables complement explanations and do not replace them.
- Add realistic examples and explain their outcomes.
- Cross-link every guide and validate local Markdown links.
- Maintain a user-oriented docs index.
- Update the README, user docs, developer docs, existing references, examples, contributor docs, changelog, progress record, and task backlog.
- Run full tests, Ruff, Markdown local-link validation, `git diff --check`, rtk review, and Graft graph validation.
- Do not commit or push unless explicitly instructed.
