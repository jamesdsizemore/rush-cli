# Security Policy & Vulnerability Reporting

Rush prioritizes code security, execution isolation, and responsible disclosure.

---

## 1. The 7 Defensive Controls

Rush implements seven defense-in-depth architectural controls:

1. **Control 1 (Flag-Salted Cryptographic Caching)**: Cache keys incorporate file content hashes and runtime CLI flags (`src/rush/cache.py`), preventing stale result pollution or bypass via command-line manipulation.
2. **Control 2 (Path Boundary Confinement & Monorepo Scoping)**: Tools strictly validate target paths against the repository root (`assert_safe_workspace_path` and `discover_workspaces`), rejecting `..` traversal escapes.
3. **Control 3 (Shell Injection Prevention & Typed Arguments)**: Package installation (`src/rush/tools/setup_wizard.py`) validates package names via strict regex `^[a-zA-Z0-9@_./-]+$` and executes subprocesses with typed argv lists (`shell=False`, `stdin=DEVNULL`).
4. **Control 4 (Binary Integrity & Anti-Shadowing)**: Environment doctor (`src/rush/tools/doctor.py`) checks PATH precedence (virtualenv -> system PATH) and flags binary shadowing vulnerabilities in current working directories.
5. **Control 5 (Dashboard Auth, Loopback Binding, DNS Rebinding & CSRF Protection)**: The local web dashboard (`src/rush/dashboard.py`) binds strictly to `127.0.0.1`, enforces ephemeral 64-hex token auth (`X-Rush-Auth`), validates `Host` headers to defeat DNS rebinding, and rejects cross-origin `fetch` requests.
6. **Control 6 (Repository Trust Gating)**: Custom script plugins and hooks are blocked in untrusted repository directories by default until explicitly authorized via `rush trust` (`src/rush/plugins/trust.py`), preventing RCE on newly cloned checkouts.
7. **Control 7 (Patch Confinement & XML Session Memory Framing)**: Automated patches (`src/rush/patch_generator.py`) shield sensitive paths (`.git/`, `.env`, `.rush/cache.db`), and multi-turn session history (`src/rush/session_memory.py`) is framed in strict XML boundary tags (`<rush_session_memory>`) with XML escaping to neutralize prompt injection.

---

## 2. Security Architecture Highlights

1. **Subprocess Isolation**: External engines are launched using `stdin=subprocess.DEVNULL`, `shell=False`, and a 120s timeout, preventing arbitrary shell expansion and MCP pipe corruption.
2. **Automated Secret Redaction**: High-entropy strings, API keys, tokens, and credentials identified by secret scanners or stderr logs are masked as `[REDACTED]`.
3. **Execution Permissions**: Destructive, network-accessing, or resource-heavy operations require explicit `--allow-*` permissions.
4. **Offline Safety**: All security adapters default to local, offline analysis.

---

## 2. Reporting a Vulnerability

If you discover a security vulnerability in Rush CLI:
1. **Do NOT open a public GitHub issue.**
2. Report the vulnerability privately via GitHub Security Advisories or by emailing maintainers.
3. Include a detailed description, steps to reproduce, and a proof of concept.
4. Never include real production secrets, API keys, or private code in vulnerability reports.

See [Security Model](safety/security-model.md), [Incident & Security Runbook](maintainers/incident-and-security.md), and [Permissions](safety/permissions.md).

## Supply Chain & Import Security (Phases 41–43)
`rush hallu-guard` and `rush ship pack` provide static defense against:
1. Typosquatted dependencies and hallucinated package imports.
2. Accidental inclusion of sensitive keys, `.env` files, or certificates in package builds.
3. Risky table-locking SQL migrations in production deployments.

## Architectural Layer Isolation (Phase 46)
`rush arch-guard` prevents sensitive infrastructure code (database clients, crypto keys) from being imported into untrusted presentation or domain layers.
