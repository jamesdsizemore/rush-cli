# Specification: Agent Flight Recorder & Session Replayer

## 1. Overview
`FlightRecorder` (`src/rush/tools/flight_recorder.py`) logs JSON-RPC requests, tool calls, and duration metrics into `.rush/sessions/flights/` for reproducible post-mortem replay.

## 2. CLI Reference
* `rush flight-recorder [--replay <SESSION_ID>]`
