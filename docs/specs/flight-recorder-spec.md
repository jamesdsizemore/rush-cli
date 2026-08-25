# Specification: Agent Flight Recorder & Session Replayer

## 1. Overview
`FlightRecorder` (`src/rush/tools/flight_recorder.py`) logs JSON-RPC requests, tool calls, and duration metrics into `.rush/sessions/flights/` for reproducible post-mortem replay.

`coordination_recovery` reads a session only as receipt metadata: state, session id, event count, and final event type. Missing or corrupt evidence is `skipped`/`unavailable`; it does not execute the recorded events or create flight storage during inspection.

## 2. CLI Reference
* `rush flight-recorder [--replay <SESSION_ID>]`
