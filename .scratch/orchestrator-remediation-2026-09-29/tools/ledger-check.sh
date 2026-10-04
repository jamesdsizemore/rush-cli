#!/usr/bin/env bash
# ledger-check.sh <doc.md>
# Plan H13/J1/F32: the requirement ledger is mechanical. The doc's "0. The ask, verbatim" block quote is split
# into sentences; the "Requirement ledger" table must quote every sentence in full (a row may quote more than
# one sentence), and every row must name entries that exist as headings, a check, and a status of done or open.
# Exit 0 = ledger complete and no open row, 1 = a sentence is missing, a row names nothing real, or rows are open,
# 2 = unreadable input or no ask block / no ledger.
# Row format:  | R01 | "quoted sentence(s)" | A1, B2, 3.1 | the observable check | done |
set -uo pipefail
d="${1:-}"
[ -n "$d" ] && [ -r "$d" ] && [ -s "$d" ] || { echo "LEDGER-CHECK ERROR unreadable or empty input: '${d}'" >&2; exit 2; }
exec python3 - "$d" <<'PY'
import re, sys
text = open(sys.argv[1], errors="replace").read()
lines = text.split("\n")
norm = lambda s: re.sub(r"\s+", " ", s.replace("“", '"').replace("”", '"')).strip().strip('"').strip()
# ask block: '> ' lines between '## 0.' and the next '## '
ask, on = [], False
for ln in lines:
    if re.match(r"^## 0\.", ln): on = True; continue
    if on and ln.startswith("## "): break
    if on and ln.startswith(">"): ask.append(ln.lstrip("> ").strip())
if not ask:
    print("LEDGER-CHECK ERROR no '> ' block under '## 0.'", file=sys.stderr); sys.exit(2)
sentences = [norm(s) for s in re.split(r"(?<=[.!?])\s+(?=[A-Z(])", " ".join(ask)) if s.strip()]
# ledger rows
rows, on = [], False
for ln in lines:
    if re.match(r"^#{2,3} .*Requirement ledger", ln): on = True; continue
    if on and re.match(r"^#{2,3} ", ln): break
    if on and re.match(r"^\|\s*R\d+\s*\|", ln):
        cells = [c.strip() for c in ln.strip().strip("|").split("|")]
        if len(cells) == 5: rows.append(cells)
if not rows:
    print("LEDGER-CHECK ERROR no ledger rows under 'Requirement ledger'", file=sys.stderr); sys.exit(2)
heads = set(re.findall(r"^#{2,4} ([A-JT]?\d+(?:\.\d+)?)\.?\s", text, re.M))
bad, openrows = 0, 0
quoted = " ".join(norm(r[1]) for r in rows)
for i, s in enumerate(sentences, 1):
    if s not in quoted:
        print(f"FAIL MISSING sentence {i}: {s[:90]}"); bad = 1
for rid, quote, entries, check, status in rows:
    for e in [x.strip() for x in entries.split(",") if x.strip()]:
        if e not in heads:
            print(f"FAIL {rid} names '{e}', which is not a heading"); bad = 1
    if not check or not entries:
        print(f"FAIL {rid} has no check or no entries"); bad = 1
    if status not in ("done", "open"):
        print(f"FAIL {rid} status '{status}' is not done or open"); bad = 1
    if status == "open": openrows += 1
    if norm(quote) not in norm(" ".join(ask)):
        print(f"FAIL {rid} quotes text that is not in the ask"); bad = 1
if openrows:
    print(f"OPEN {openrows} ledger rows"); bad = 1
if not bad:
    print(f"LEDGER-CHECK PASS {len(sentences)} sentences, {len(rows)} rows")
sys.exit(bad)
PY
