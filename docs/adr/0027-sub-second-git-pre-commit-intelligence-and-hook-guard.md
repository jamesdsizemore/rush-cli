# ADR-0027: Sub-Second Git Pre-Commit Intelligence and Hook Guard

## Status
Accepted (v0.2.0)

## Context
Traditional pre-commit frameworks introduce multi-second execution delays by scanning entire repositories, prompting developers and AI agents to bypass checks using `git commit --no-verify`. Furthermore, malicious dependencies or compromised tools can tamper with `.git/hooks/` to disable security scanners.

## Decision
1. Implement staged-only discovery (`git diff --cached --name-only`) to restrict pre-commit validation strictly to indexed changes, achieving <500ms execution times.
2. Implement `HookTamperDetector` using cryptographic SHA-256 signatures stored in `.rush/hook_signatures.json` to detect unauthorized modifications to `.git/hooks/`.
3. Enforce Conventional Commits 1.0.0 via `ConventionalCommitValidator` on commit message files.
4. Implement `LargeFileGuard` to reject staged binary files or datasets > 5MB.
5. Provide `DirtyStateStashSupervisor` to isolate unstaged working tree changes during hook validation.

## Consequences
- **Positive**: Sub-second pre-commit feedback, cryptographic hook integrity, zero accidental dirty commits.
- **Negative**: Requires local `.git/hooks` installation via `rush hook install`.
- **Safety**: Blocks high-entropy secret commits, merge conflict markers (`<<<<<<< HEAD`), and trojan source Unicode bidi overrides.
