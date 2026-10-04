#!/usr/bin/env bash
# skill-coverage.sh list [--require] | mark <path> <first>-<last>
# Review coverage by exact path, source hash and line span, not by whether a doc mentions a file name.
#   list   prints one row per file: STATUS <lines> <sha256:12> <exact path>. Files: everything under the orchestrator
#          skill directory, the user-level orch-*.md definitions, and any repo-level .claude/agents/orch-*.md.
#          REVIEWED = the ledger holds spans for the file's current sha256 that cover every line; STALE = the ledger has
#          spans for an older sha256; UNREVIEWED = none. --require exits 1 when any row is not REVIEWED.
#   mark   records that lines <first>-<last> of <path> were opened, under the file's current sha256.
# Ledger: $REVIEW_LEDGER (default ~/.claude/orchestrator/reviewed.tsv), rows: path<TAB>sha256<TAB>first<TAB>last.
# Roots for tests: SKILL_DIR, USER_AGENTS, REPO_AGENTS override the defaults.
set -uo pipefail
cmd="${1:-list}"; shift || true
exec python3 - "$cmd" "$@" <<'PY'
import glob, hashlib, os, sys
cmd, args = sys.argv[1], sys.argv[2:]
home = os.path.expanduser("~")
ledger = os.environ.get("REVIEW_LEDGER", os.path.join(home, ".claude", "orchestrator", "reviewed.tsv"))
skill = os.environ.get("SKILL_DIR", os.path.join(home, ".claude", "skills", "orchestrator"))
uagents = os.environ.get("USER_AGENTS", os.path.join(home, ".claude", "agents"))
ragents = os.environ.get("REPO_AGENTS", os.path.join(os.getcwd(), ".claude", "agents"))
sha = lambda p: hashlib.sha256(open(p, "rb").read()).hexdigest()
nlines = lambda p: len(open(p, errors="replace").read().split("\n")) - (1 if open(p, errors="replace").read().endswith("\n") else 0)


def rows():
    out = []
    if os.path.exists(ledger):
        for ln in open(ledger):
            p = ln.rstrip("\n").split("\t")
            if len(p) == 4 and p[2].isdigit() and p[3].isdigit():
                out.append((p[0], p[1], int(p[2]), int(p[3])))
    return out


if cmd == "mark":
    if len(args) != 2 or "-" not in args[1]:
        print("usage: skill-coverage.sh mark <path> <first>-<last>", file=sys.stderr); sys.exit(2)
    p = os.path.realpath(args[0])
    a, b = args[1].split("-", 1)
    if not os.path.isfile(p) or not (a.isdigit() and b.isdigit()) or int(a) < 1 or int(b) < int(a) or int(b) > nlines(p):
        print(f"refusing: '{args[0]}' is not a file, or {args[1]} is not a span inside its {nlines(p) if os.path.isfile(p) else 0} lines", file=sys.stderr); sys.exit(2)
    os.makedirs(os.path.dirname(ledger), exist_ok=True)
    with open(ledger, "a") as f:
        f.write(f"{p}\t{sha(p)}\t{a}\t{b}\n")
    print(f"marked {p} {a}-{b}"); sys.exit(0)

if cmd != "list":
    print("usage: skill-coverage.sh list [--require] | mark <path> <first>-<last>", file=sys.stderr); sys.exit(2)
files = []
for root, _dn, fn in os.walk(skill):
    if "__pycache__" in root or "/tests/" in root + "/":
        continue
    files += [os.path.join(root, f) for f in fn if not f.endswith(".pyc")]
files += sorted(glob.glob(os.path.join(uagents, "orch-*.md"))) + sorted(glob.glob(os.path.join(ragents, "orch-*.md")))
led = rows()
bad = 0
for f in sorted({os.path.realpath(x) for x in files}):
    h, n = sha(f), nlines(f)
    same = [(a, b) for p, s, a, b in led if p == f and s == h]
    seen = set()
    for a, b in same:
        seen.update(range(a, b + 1))
    if n and seen >= set(range(1, n + 1)):
        st = "REVIEWED"
    elif any(p == f and s != h for p, s, _a, _b in led):
        st = "STALE"
    else:
        st = "UNREVIEWED"
    if st != "REVIEWED":
        bad = 1
    print(f"{st}\t{n}\t{h[:12]}\t{f}")
sys.exit(1 if bad and "--require" in args else 0)
PY
