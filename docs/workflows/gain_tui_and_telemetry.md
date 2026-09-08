# Workflow: Context Gain TUI & Real-Time Telemetry

## 1. Launching the Gain HUD
The current command prints a token-statistics snapshot; it does not launch a persistent interactive dashboard. Live terminal telemetry is required by [P66-03](../phase-plans/phase-66-interactive-tui-and-local-web-plan.md#p66-03--persistent-colorful-animated-tui-f36).
```bash
rush context gain
```

## 2. FastMCP Telemetry Query
Agents can inspect recorded local telemetry. Distinguish local estimates from measured provider usage; missing measurements are not savings:
```python
stats = rush_context_gain_stats()
```
