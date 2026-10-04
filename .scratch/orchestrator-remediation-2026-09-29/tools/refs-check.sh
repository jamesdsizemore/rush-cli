#!/usr/bin/env bash
# refs-check.sh <doc.md>
# Verifies the cross-references in a document in one batch: every file:line citation points at a file that exists
# and has that many lines; every "Decision Dn"/"Dn" names a row of the decisions table; every "Xn" names an
# "### Xn." heading; every backticked test file name exists. Prints one FAIL line per broken reference with the
# document line number. It checks that a reference resolves, not that the cited line says what the document says.
# Exit 0 = all resolve, 1 = broken references, 2 = unreadable input.
# Roots: the remediation tree this script lives in, the repo holding the doc, ~/.claude/skills/orchestrator,
# ~/.claude/hooks, ~/.claude/agents, and the phase-70 worktree when it exists.
set -uo pipefail
d="${1:-}"
[ -n "$d" ] && [ -r "$d" ] && [ -s "$d" ] || { echo "REFS-CHECK ERROR unreadable or empty input: '${d}'" >&2; exit 2; }
doc="$(cd "$(dirname "$d")" && pwd -P)/$(basename "$d")"
exec python3 - "$doc" "$(cd "$(dirname "$0")/.." && pwd -P)" <<'PY'
import os, re, subprocess, sys
doc, tree = sys.argv[1], sys.argv[2]
lines = open(doc, errors="replace").read().split("\n")
repo = subprocess.run(["git", "-C", os.path.dirname(doc), "rev-parse", "--show-toplevel"], capture_output=True, text=True).stdout.strip() or os.path.dirname(doc)
home = os.path.expanduser("~")
roots = [tree, repo, home + "/.claude/skills/orchestrator", home + "/.claude/hooks", home + "/.claude/agents",
         os.path.join(os.path.dirname(repo), os.path.basename(repo) + "-worktrees", "phase-70")]
skip = {".git", "node_modules", ".venv", "__pycache__", ".mypy_cache", ".ruff_cache"}
by_name = {}
for r in roots:
    for dp, dn, fn in os.walk(r):
        dn[:] = [x for x in dn if x not in skip]
        if dp.count(os.sep) - r.count(os.sep) > 6:
            dn[:] = []
        for f in fn:
            by_name.setdefault(f, []).append(os.path.join(dp, f))
nl = {}
def nlines(p):
    if p not in nl:
        try: nl[p] = open(p, errors="replace").read().count("\n") + 1
        except OSError: nl[p] = 0
    return nl[p]
decisions = set(re.findall(r"^\|\s*(D\d+)\s*\|", "\n".join(lines), re.M))
xheads = set(re.findall(r"^### (X\d+)\.", "\n".join(lines), re.M))
bad = 0
# the ask block quotes prose the user wrote; skip it
in_ask = False
fenced = False
for i, ln in enumerate(lines, 1):
    if ln.startswith("```"):
        fenced = not fenced      # code blocks hold code and example data, not claims about other files
        continue
    if fenced:
        continue
    if re.match(r"^## 0\.", ln): in_ask = True
    elif re.match(r"^## [1-9]", ln): in_ask = False
    if in_ask or ln.startswith("|") and re.match(r"^\|\s*R\d+\s*\|", ln):
        continue
    for m in re.finditer(r"([\w./~-]+\.(?:sh|py|js|md|tsv|json|ya?ml|toml|patch)):(\d+)(?:-(\d+))?", ln):
        name, a, b = os.path.basename(m.group(1)), int(m.group(2)), int(m.group(3) or m.group(2))
        cands = by_name.get(name, [])
        if not cands:
            print(f"FAIL line {i}: {m.group(0)} names a file that does not exist under the roots"); bad = 1
        elif not any(nlines(p) >= b for p in cands):
            print(f"FAIL line {i}: {m.group(0)} is past the end of every candidate ({max(nlines(p) for p in cands)} lines at most)"); bad = 1
    for m in re.finditer(r"\bD(\d+)\b", ln):
        if "D" + m.group(1) not in decisions and not re.search(r"[A-Za-z0-9_]D\d+", ln[max(0, m.start() - 1):m.end()]):
            print(f"FAIL line {i}: Decision D{m.group(1)} is not a row of the decisions table"); bad = 1
    for m in re.finditer(r"\bX(\d+)\b", ln):
        if "X" + m.group(1) not in xheads and not re.search(r"[A-Za-z0-9_-]X\d+", ln[max(0, m.start() - 1):m.end()]):
            print(f"FAIL line {i}: X{m.group(1)} is not a section heading"); bad = 1
    for m in re.finditer(r"`(?:[\w./-]*/)?(test[-_][\w.-]+\.(?:sh|py|js))`", ln):
        if m.group(1) not in by_name and not os.path.exists(os.path.join(repo, "tests", m.group(1))):
            print(f"FAIL line {i}: test file {m.group(1)} does not exist"); bad = 1
if not bad:
    print("REFS-CHECK PASS")
sys.exit(bad)
PY
