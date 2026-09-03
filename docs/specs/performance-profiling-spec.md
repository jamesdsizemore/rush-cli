# Specification: Performance Profiling, Cold-Start & Benchmark Regression Guard

## 1. Overview
Phase 50c introduces lightweight, stdlib-only performance profiling tools to detect resource leaks, slow import chains, and execution regressions without external heavy scientific dependencies (`scipy`, `onnxruntime`, `llama-cpp-python`).

## 2. Resource Lifecycle Auditing (`mem-profile`)
- **Static AST Pass**: Inspects Python AST using `_ResourceLifecycleVisitor` to detect `open()`, `socket.socket()`, `sqlite3.connect()`, and `urllib.request.urlopen()` called outside `with` or `async with` context managers. Emits `mem-profile/unclosed-resource` findings.
- **Dynamic Sampling**: When `--dynamic` is requested, requires explicit `--allow-slow` permission. Uses stdlib `tracemalloc` to record peak allocation and memory delta.

## 3. Cold-Start Waterfall Analysis (`cold-start`)
- **Static AST Pass**: Inspects top-level imports in Python source files. Flags heavy scientific or cloud packages (`torch`, `tensorflow`, `boto3`, `google.cloud`, `pandas`) as `cold-start/heavy-top-level-import` and wildcard imports as `cold-start/wildcard-import`.
- **Dynamic Importtime Pass**: Under `--dynamic` and `--allow-slow`, executes `python -X importtime` and builds an import latency waterfall table.

## 4. Benchmark Regression Guard (`benchmark`)
- **Descriptive Statistics**: Computes `mean`, `median`, `min`, `max`, and `count` using Python 3.12 stdlib `statistics`.
- **Baseline Comparison**: Compares against stored thresholds in `.rush/baselines.json`. If performance degrades by more than `threshold_percent` (default 5.0%), emits `benchmark/regression`.
- **Permission Boundary**: Updating or recording baselines requires `--allow-cache-write`.

## 5. CLI & FastMCP Contracts
- `rush mem-profile [PATH] [--json]`
- `rush cold-start [PATH] [--json]`
- `rush benchmark check [PATH] [--json]`
- FastMCP: `rush_mem_profile`, `rush_cold_start`, `rush_benchmark`.
