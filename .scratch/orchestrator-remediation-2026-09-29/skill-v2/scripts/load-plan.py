#!/usr/bin/env python3
"""Load a phase plan's task graph into a tasks.tsv (id, deps, status, files).
usage: load-plan.py <plan.md> <tasks.tsv> [--keep] [--merged-from-git <revision-range>]
Reads the 'Execution order:' block: 'Ta → Tb' chains; 'then' between chains; a lone
'Tx ... first;' before a chain; 'Tn (also) requires ...' sentences ('T9/T16', 'T18–T23').
files: the plan's 'One writer at a time for `a.py`, `b.py` ...' names that a task's **Deliverables:** line
touches; run-state.sh next never offers two nodes that hold the same name.
Refuses to overwrite an existing tasks.tsv (that would reset merged nodes to pending); --keep keeps the
status of every id already in it. --merged-from-git marks a node merged when a first-parent merge subject
in the range names it (migrating a run that has no tasks.tsv yet).
Exits 1 when a '#### Tn' heading has no node or an edge names an unknown task."""
import os
import re
import subprocess
import sys

plan = open(sys.argv[1], encoding="utf-8").read()
out_path = sys.argv[2]
keep = "--keep" in sys.argv
git_range = sys.argv[sys.argv.index("--merged-from-git") + 1] if "--merged-from-git" in sys.argv else None
if os.path.exists(out_path) and not keep:
    sys.exit(f"{out_path} exists: refusing to overwrite run state (pass --keep to keep statuses, or delete it on purpose)")
heads = re.findall(r"^#### (T\d+)\b", plan, re.M)
block = re.search(r"^Execution order:\n(.*?)\n\n", plan, re.M | re.S)
if not block:
    sys.exit("no 'Execution order:' block")
block = block.group(1)
deps = {t: set() for t in heads}
unknown = set()


def add(after, before):
    if after not in deps or before not in deps:
        unknown.update({after, before} - set(deps))
        return
    deps[before].add(after)


def expand(spec):
    out = []
    for a, b in re.findall(r"T(\d+)(?:\s*[–-]\s*T(\d+))?", spec):
        out += [f"T{i}" for i in range(int(a), int(b or a) + 1)]
    return out


sentences = re.findall(r"(T\d+)\s+(?:also\s+)?requires\s+([^.;\n]*)", block)
body = re.sub(r"T\d+\s+(?:also\s+)?requires\s+[^.;\n]*", "", block)
for line in body.splitlines():
    prev_ids, prev_text = [], ""
    for part in line.split(";"):
        ids = re.findall(r"T\d+", part)
        spans = [(m.group(0), m.start()) for m in re.finditer(r"T\d+", part)]
        for (a, i), (b, j) in zip(spans, spans[1:]):
            if "→" in part[i:j]:
                add(a, b)
        if ids and prev_ids and (re.search(r"\bthen\b", part) or re.search(r"\bfirst\b", prev_text)):
            add(prev_ids[-1], ids[0])
        if ids:
            prev_ids, prev_text = ids, part
for t, spec in sentences:
    for d in expand(spec):
        add(d, t)
if unknown:
    sys.exit(f"edges name tasks with no heading: {sorted(unknown)}")
shared = re.search(r"One writer at a time for (.*?)\.\s", plan)
shared_names = re.findall(r"`([^`]+)`", shared.group(1)) if shared else []


def touched(task):
    sec = re.search(rf"^#### {task}\b.*?(?=^#{{2,4}} |\Z)", plan, re.M | re.S)
    line = re.search(r"\*\*Deliverables:\*\*([^\n]*)", sec.group(0)) if sec else None
    paths = re.findall(r"`([^`]+)`", line.group(1)) if line else []
    return sorted({n for n in shared_names if any(p == n or p.endswith("/" + n) for p in paths)})


status = {t: "pending" for t in heads}
extra = []
if keep and os.path.exists(out_path):
    for row in open(out_path, encoding="utf-8").read().splitlines():
        cols = row.split("\t")
        if cols[0] in status:
            status[cols[0]] = cols[2]
        else:
            extra.append(row)
if git_range:
    repo = os.path.dirname(os.path.abspath(sys.argv[1]))
    subjects = subprocess.run(["git", "-C", repo, "log", "--first-parent", "--format=%s", git_range],
                              capture_output=True, text=True, check=True).stdout.splitlines()
    for t in heads:
        if any(s.startswith("Merge") and re.search(rf"(?i)(?<![0-9]){t}(?![0-9])", s) for s in subjects):
            status[t] = "merged"
with open(out_path, "w", encoding="utf-8") as f:
    for t in heads:
        f.write(f"{t}\t{','.join(sorted(deps[t], key=lambda x: int(x[1:])))}\t{status[t]}\t{','.join(touched(t))}\n")
    for row in extra:
        f.write(row + "\n")
print(f"{len(heads)} nodes, {sum(len(v) for v in deps.values())} edges, "
      f"{sum(1 for t in heads if status[t] == 'merged')} merged, {sum(1 for t in heads if touched(t))} hold shared files")
