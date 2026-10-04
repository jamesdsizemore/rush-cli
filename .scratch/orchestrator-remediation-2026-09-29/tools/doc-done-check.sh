#!/usr/bin/env bash
# doc-done-check.sh <doc.md>
# STRUCTURAL LINT, not a review. It shows that each entry has the parts and that what it names exists on
# disk; it does not show the named artifact enforces the entry's rule (that needs the fixture or the hook
# test the entry cites, or a reader). Exit 0 pass, 1 findings, 2 unreadable input or no entries.
#  1. Every entry (#### A1., B2., ..., H1., I1., J1., T1.) has a Fix/Procedure/Edit/Status marker, and its
#     text after the marker names at least one backticked file, script or hook that resolves to a real file
#     or, for a hook or script named without extension, to a real file's name (roots below).
#  2. The document has none of the banned placeholders and hedges: TBD, TODO, "not established",
#     "to be determined", and no line that makes Sonnet a standing setting for all subagents.
# Roots searched for artifacts: the repo holding the doc, the remediation scratch tree next to it,
# ~/.claude/skills/orchestrator, ~/.claude/hooks, ~/.claude/agents.
set -uo pipefail
d="${1:-}"
[ -n "$d" ] && [ -r "$d" ] && [ -s "$d" ] || { echo "DOC-DONE-CHECK ERROR unreadable or empty input: '${d}'" >&2; exit 2; }
doc="$(cd "$(dirname "$d")" && pwd -P)/$(basename "$d")"
exec python3 - "$doc" "$(cd "$(dirname "$0")/.." && pwd -P)" <<'PY'
import os, re, subprocess, sys
doc = sys.argv[1]
tree = sys.argv[2]   # the remediation tree this checker lives in
text = open(doc, errors="replace").read()
lines = text.split("\n")
repo = subprocess.run(["git", "-C", os.path.dirname(doc), "rev-parse", "--show-toplevel"], capture_output=True, text=True).stdout.strip() or os.path.dirname(doc)
roots = [tree, repo,
         *[os.path.expanduser(p) for p in ("~/.claude/skills/orchestrator", "~/.claude/hooks", "~/.claude/agents")]]
skip = {".git", "node_modules", ".venv", "__pycache__", ".mypy_cache", ".ruff_cache", "worktrees"}
paths, names = set(), set()
for r in roots:
    for dp, dn, fn in os.walk(r):
        dn[:] = [x for x in dn if x not in skip]
        if dp.count(os.sep) - r.count(os.sep) > 6:
            dn[:] = []
        for f in fn:
            p = os.path.join(dp, f)
            paths.add(p)
            names.add(f)
            names.add(os.path.splitext(f)[0])
FILEISH = re.compile(r"^[~\w./-]+\.(sh|py|js|md|tsv|json|yaml|toml|txt|patch)$")
BARE = re.compile(r"^[a-z][a-z0-9]*(-[a-z0-9]+)+$")


def resolves(tok):
    tok = re.sub(r":[\d,-]+$", "", tok.strip())
    if FILEISH.match(tok):
        exp = os.path.expanduser(tok)
        if os.path.isabs(exp) and os.path.exists(exp):
            return True
        return os.path.basename(tok) in names
    return bool(BARE.match(tok)) and tok in names


entries, cur = [], None
for ln in lines:
    m = re.match(r"^#### ([A-JT]\d+)\.", ln)
    if m:
        cur = [m.group(1), []]
        entries.append(cur)
    elif ln.startswith("#") and cur is not None:
        cur = None
    elif cur is not None:
        cur[1].append(ln)
bad = 0
if not entries:
    print("DOC-DONE-CHECK ERROR no '#### X1.' entries found", file=sys.stderr)
    sys.exit(2)
for eid, body in entries:
    b = "\n".join(body)
    m = re.search(r"\*\*(Fix|Procedure|Edit|Status)[^*]*\*\*", b)
    if not m:
        print(f"FAIL NO-FIX {eid}"); bad = 1; continue
    rest = b[m.end():]
    toks = re.findall(r"`([^`\n]+)`", rest)
    cand = [t.split()[0] for t in toks if t.split()]
    if not any(resolves(t) for t in cand):
        print(f"FAIL NO-ARTIFACT {eid} (no backticked name after the marker resolves to a real file)"); bad = 1
banned = re.compile(r"TBD|TODO|not established|to be determined|all subagents (are|run|use) sonnet|only sonnet", re.I)
for i, ln in enumerate(lines, 1):
    if banned.search(ln):
        print(f"FAIL BANNED line {i}: {ln[:110]}"); bad = 1
if not bad:
    print(f"DOC-DONE-CHECK PASS {len(entries)} entries (structural lint)")
sys.exit(bad)
PY
