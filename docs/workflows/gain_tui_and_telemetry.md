# Workflow: Context Gain TUI & Real-Time Telemetry

## 1. Launching the Gain HUD
`rush gain` (and its live alias `rush context gain`) opens a live-updating Rich HUD of token-statistics estimates, re-rendering on a timer until Ctrl+C. The same live summary also appears in the Tokens section of `rush ui` / `rush dashboard`.
```bash
rush gain
```

## 2. FastMCP Telemetry Query
Agents can inspect recorded local telemetry. Distinguish local estimates from measured provider usage; missing measurements are not savings:
```python
stats = rush_context_gain_stats()
```
The query is read-only and anchored at the project's logical root; it never creates the telemetry database. When no telemetry has been recorded yet, `stats` is `{"available": false, "reason": "...", "path": "<db path>"}` instead of raising; once telemetry exists it is `{"available": true, "path": "<db path>", ...token/compression totals}`.
