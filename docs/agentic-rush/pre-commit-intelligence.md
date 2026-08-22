# Pre-Commit Intelligence & Hook Guard

Traditional pre-commit hooks that run heavy test suites or full-project linters take 30 to 60 seconds to run. When developers and AI agents commit frequently, slow hooks lead to frustration and developers bypassing hooks with `--no-verify`.

Rush’s **Pre-Commit Intelligence Subsystem** (`rush hook`) executes in **under 300 milliseconds**, running lightweight AST syntax checks, Trojan Source Unicode vulnerability scans, merge conflict marker detection, and hook tamper verification on staged files only.

---

## 1. Sub-Second Staged AST Linting

Rather than scanning thousands of untouched repository files, `rush hook run` inspects only the exact files staged in the Git index (`.git/index`):

```bash
# Run the pre-commit intelligence suite manually
rush hook run
```

### Checks Performed in <300ms:
- **Fast Syntax & AST Validation**: Checks Python, JavaScript, TypeScript, Rust, and Go files for unparseable syntax errors before commits are written.
- **Merge Conflict Marker Scanner**: Prevents accidental commits containing leftover `<<<<<<< HEAD`, `=======`, or `>>>>>>>` markers.
- **Secrets & API Key Scanner**: Scans staged lines for unredacted tokens, private keys, or credentials.

---

## 2. Trojan Source & Invisible Unicode Detection

"Trojan Source" (CVE-2021-42574) is a subtle vulnerability where bidirectional Unicode control characters (like `\u202E` Right-to-Left Override) cause code to render visually one way in code editors and web UIs, but execute completely differently in compilers and interpreters.

Rush automatically scans all staged changes for invisible or bidirectional Unicode characters:

```bash
# Scan for Trojan Source Unicode exploits
rush hook run --trojan-check
```

---

## 3. Cryptographic Hook Tamper Guard

To prevent malicious scripts or hallucinated agent commands from secretly removing or tampering with `.git/hooks/pre-commit`, Rush verifies the hook's cryptographic SHA-256 integrity:

```bash
# Install and verify the hardened pre-commit hook
rush hook install
rush hook verify
```

---

## Next Steps

- Learn how to reconcile multi-model AI reviews in [Multi-Model Consensus & Quality Scorecards](multi-model-consensus-and-scoring.md).
- Discover how to extend agent capabilities with [Plugins & Agent Skills](plugins-and-agent-skills.md).
