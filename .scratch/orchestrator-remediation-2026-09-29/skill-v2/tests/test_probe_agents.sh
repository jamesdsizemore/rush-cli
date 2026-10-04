#!/usr/bin/env bash
# Plan A5/F19: probe-agents.sh judges each agent's reply and model. A stub `claude` on PATH stands in for the live
# CLI, so this covers the aggregation: a missing line, a wrong model, a fail line, extra lines and a missing result
# all make ok=false. The live run against the real definitions is recorded in A5.
set -uo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
probe="$here/../scripts/probe-agents.sh"
tmp="$(mktemp -d)"; trap 'rm -rf "$tmp"' EXIT
pass=0 fail=0
check() { if [ "$2" -eq 0 ]; then pass=$((pass + 1)); else fail=$((fail + 1)); echo "FAIL: $1"; fi; }
mkdir -p "$tmp/bin" "$tmp/proj"
cat > "$tmp/bin/claude" <<'EOF'
#!/usr/bin/env bash
# stub: prints $STUB_JSON, or exits 1 when STUB_FAIL is set
[ -z "${STUB_FAIL:-}" ] || exit 1
printf '%s\n' "$STUB_JSON"
EOF
chmod +x "$tmp/bin/claude"
run() { PATH="$tmp/bin:$PATH" PROBE_ROLES="$1" bash "$probe" "$tmp/proj" "$tmp/out.json" > /dev/null 2>&1; jq -r '.ok' "$tmp/out.json"; }
good='{"result":"toolsearch: ok\ngraft-mcp: ok\nctx-mcp: ok","modelUsage":{"claude-haiku-4-5-20251001":{}}}'

export STUB_JSON="$good"; [ "$(run scout)" = true ]; check "three ok lines and exactly the matrix model pass" $?
export STUB_JSON='{"result":"toolsearch: ok\ngraft-mcp: ok\nctx-mcp: ok","modelUsage":{"claude-sonnet-5-5":{}}}'; [ "$(run scout)" = false ]; check "a wrong model fails" $?
export STUB_JSON='{"result":"toolsearch: ok\ngraft-mcp: ok\nctx-mcp: ok","modelUsage":{"claude-haiku-4-5-20251001":{},"claude-opus-5-5":{}}}'; [ "$(run scout)" = false ]; check "a second model in modelUsage fails" $?
export STUB_JSON='{"result":"toolsearch: ok\ngraft-mcp: ok","modelUsage":{"claude-haiku-4-5-20251001":{}}}'; [ "$(run scout)" = false ]; check "a missing ctx-mcp line fails" $?
export STUB_JSON='{"result":"toolsearch: ok\ngraft-mcp: fail\nctx-mcp: ok","modelUsage":{"claude-haiku-4-5-20251001":{}}}'; [ "$(run scout)" = false ]; check "a fail line fails" $?
export STUB_JSON='{"result":"toolsearch: ok\ngraft-mcp: ok\nctx-mcp: ok\nextra","modelUsage":{"claude-haiku-4-5-20251001":{}}}'; [ "$(run scout)" = false ]; check "an extra reply line fails" $?
export STUB_JSON='{"result":"toolsearch: ok\ngraft-mcp: ok\ngraft-mcp: ok\nctx-mcp: ok","modelUsage":{"claude-haiku-4-5-20251001":{}}}'; [ "$(run scout)" = false ]; check "a repeated label fails" $?
export STUB_JSON='not json'; [ "$(run scout)" = false ]; check "a malformed result fails" $?
export STUB_JSON="$good" STUB_FAIL=1; [ "$(run scout)" = false ]; check "a claude run that exits 1 with no output fails" $?
unset STUB_FAIL; export STUB_JSON="$good"
[ "$(run 'scout design-gate')" = false ]; check "one role failing (design-gate wants Opus) fails the whole probe" $?
jq -e '.agents["design-gate"].want_model == "claude-opus-5-5"' "$tmp/out.json" > /dev/null; check "design-gate is probed and expects the Opus id" $?

echo "passed $pass, failed $fail"
[ "$fail" -eq 0 ]
