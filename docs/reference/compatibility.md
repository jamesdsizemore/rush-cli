# Compatibility Reference Specification

Defines exact platform, language ecosystem, and engine version compatibility boundaries for Rush CLI.

---

## 1. Rush Core Runtime Matrix

| Component | Target Version | Verification Method |
|---|---|---|
| Python | >=3.12 | Declared in `pyproject.toml`, verified via `uv sync` |
| FastMCP Transport | 1.2.1 | Verified via `tests/test_mcp.py` (stdio JSON-RPC) |
| Operating Systems | Windows 10/11, macOS 12+, Linux (Ubuntu 22.04+) | Multi-platform CI workflows |

---

## 2. Language Ecosystem Detection

| Ecosystem | Project Markers | Supported Primary Tool Routes |
|---|---|---|
| Python | `pyproject.toml`, `requirements.txt`, `setup.py`, `Pipfile` | `lint` (Ruff), `format` (Ruff), `test` (pytest), `typecheck` (mypy), `dead` (Vulture, FawltyDeps), `complexity` (Radon, Memray) |
| JavaScript / TypeScript | `package.json`, `tsconfig.json` | `lint` (ESLint, Biome), `format` (Prettier, Biome), `test` (Vitest), `typecheck` (tsc), `dead` (Knip, Ts-prune), `complexity` (jscpd, Statoscope) |
| Rust | `Cargo.toml`, `Cargo.lock` | `mutation` (Cargo-mutants), `lint` (ast-grep, wasm-tools) |
| Go | `go.mod`, `go.sum` | `lint` (ast-grep, Buf), `iac` (Kubeconform), `sql` (Atlas) |
| Java / Kotlin / JVM | `pom.xml`, `build.gradle`, `build.gradle.kts` | `mutation` (Pitest), `lint` (RedPen), `security` (Semgrep) |
| PHP | `composer.json` | `mutation` (Infection), `security` (Trivy) |
| Cloud / IaC / SQL | `*.tf`, `*.yaml`, `Dockerfile`, `*.sql`, `*.proto` | `iac` (Checkov, Terrascan, Polaris), `containerfile` (Hadolint, Dockle), `sql` (SQLFluff, Atlas, Squawk) |

See [Engine Directory](engine-directory.md) and [Maintainer Versioning](../maintainers/versioning-and-compatibility.md).
