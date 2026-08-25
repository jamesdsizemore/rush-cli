# Platform & Ecosystem Compatibility

## Provider continuation compatibility

Only installed, authenticated `claude`, `codex`, and `agy` profiles are supported direct continuation routes. Rush does not launch OAuth/browser flows, invoke a shell, or mutate profiles. 9Router and OmniRoute compatibility is not claimed until their routes are implemented and tested.

This document defines the platform, operating system, and language ecosystem compatibility boundaries for Rush CLI and its Model Context Protocol (MCP) server.

---

## 1. Rush Core Runtime

| Component | Requirement / Specification | Supported Scope |
|---|---|---|
| **Python** | Python 3.12 or newer | Core package, FastMCP server, heuristic review, all engine adapters. |
| **Package Manager** | uv (recommended), pip | Development loop, frozen dependency lockfile, package build (`uv build`). |
| **Operating Systems** | Windows 10/11, macOS (x86_64, ARM64), Linux (glibc, musl) | Path separators normalized, subprocess environment isolated, ANSI/color auto-detected. |
| **MCP Transport** | stdio (JSON-RPC over standard input/output) | Compatible with Claude Desktop, Cursor, Claude Code, Goose, Hermes, Zed, Windsurf. |

---

## 2. Language & Framework Ecosystem Support

Rush auto-detects project languages by analyzing root project markers (`pyproject.toml`, `package.json`, `Cargo.toml`, `go.mod`, `pom.xml`, etc.) and routes to applicable installed engines:

| Ecosystem | Detected Project Markers | Primary Supported Quality Engines (Phases 01–19) |
|---|---|---|
| **Python** | `pyproject.toml`, `setup.py`, `requirements.txt`, `Pipfile` | Ruff, pytest, mypy, Vulture, Radon, sloppylint, djLint, pip-audit, Refurb, FawltyDeps, Cosmic Ray, Memray, PyClean, Diff-Cover, Flake8-Bugbear |
| **JavaScript / TypeScript** | `package.json`, `tsconfig.json`, `jsconfig.json` | ESLint, Prettier, Vitest, TypeScript `tsc`, Knip, jscpd, Biome, Ts-prune, Stryker, Statoscope, NCU, Depcruise |
| **Rust** | `Cargo.toml`, `Cargo.lock` | Cargo-mutants, wasm-tools, ast-grep, Semgrep |
| **Go** | `go.mod`, `go.sum` | ast-grep, Semgrep, Buf, Kubeconform, Atlas, Vale |
| **JVM (Java / Kotlin / Scala)** | `pom.xml`, `build.gradle`, `build.gradle.kts`, `build.sbt` | Pitest, RedPen, Semgrep, Trivy, Grype |
| **PHP** | `composer.json`, `composer.lock` | Infection, Semgrep, Trivy |
| **C / C++** | `CMakeLists.txt`, `Makefile`, `compile_commands.json` | Bloaty, ast-grep, Comby, Semgrep |
| **Cloud-Native & IaC** | `*.tf`, `*.yaml`, `Dockerfile`, `Containerfile` | Hadolint, Dockle, TFLint, Checkov, Kubeconform, Terrascan, Kube-score, Conftest, Polaris, KubeLinter |
| **API & Data Schemas** | `*.proto`, `schema.prisma`, `*.graphql`, `openapi.yaml`, `*.sql` | Buf, Prisma-lint, GraphQL-Inspector, Schemathesis, Zally, Cherrybomb, SQLFluff, Atlas, Squawk |
| **Prose & Documentation** | `*.md`, `*.mdx`, `*.rst`, `*.txt` | markdownlint, Lychee, Vale, CSpell, Alex, Readability, RedPen, No-Jargon, Markdown-Unfluff |

---

## 3. Engine Version Compatibility Matrix

For the complete list of all 77 external engines, minimum tested versions, install hints, and reference test suites, see the [Engine Compatibility Matrix](ENGINE_COMPATIBILITY.md) and [Engine Directory](reference/engine-directory.md).
