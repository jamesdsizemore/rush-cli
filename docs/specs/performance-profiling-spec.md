# Specification: Performance Profiling, Cold-Start & Benchmark Regression Guard

## 1. Overview
Phase 50c introduces lightweight, stdlib-only performance profiling tools to detect resource leaks, slow import chains, and execution regressions without external heavy scientific dependencies (`scipy`, `onnxruntime`, `llama-cpp-python`).

Current execution contract: the profiling CLI commands do not expose `--dynamic`; catalog configuration and MCP `options` supply tool-specific inputs. Dynamic work requires the relevant slow-execution grant. [Phase 64 P64-14](../phase-plans/phase-64-runtime-correctness-and-safe-execution-plan.md) repairs target-failure reporting; until repaired, zero measurements must not be interpreted as successful execution of a failing target.

## 2. Resource Lifecycle Auditing (`mem-profile`)
- **Static AST Pass**: Inspects Python AST using `_ResourceLifecycleVisitor` to detect `open()`, `socket.socket()`, `sqlite3.connect()`, and `urllib.request.urlopen()` called outside `with` or `async with` context managers. Emits `mem-profile/unclosed-resource` findings.
- **Dynamic Sampling**: When dynamic profiling is requested through tool options, requires explicit slow-execution permission. Uses stdlib `tracemalloc` to record peak allocation and memory delta; the target must finish successfully for those values to establish a completed measurement.

## 3. Cold-Start Waterfall Analysis (`cold-start`)
- **Static AST Pass**: Inspects top-level imports in Python source files. Flags heavy scientific or cloud packages (`torch`, `tensorflow`, `boto3`, `google.cloud`, `pandas`) as `cold-start/heavy-top-level-import` and wildcard imports as `cold-start/wildcard-import`.
- **Dynamic Importtime Pass**: With dynamic tool options and slow-execution permission, executes `python -X importtime` and builds an import latency waterfall table. `--dynamic` is not a current CLI flag.

## 4. Benchmark Regression Guard (`benchmark`)
- **Descriptive Statistics**: Computes `mean`, `median`, `min`, `max`, and `count` using Python 3.12 stdlib `statistics`.
- **Baseline Comparison**: Compares against stored thresholds in `.rush/baselines.json`. If performance degrades by more than `threshold_percent` (default 5.0%), emits `benchmark/regression`.
- **Permission Boundary**: Updating or recording baselines requires `--allow-cache-write`.

## 5. CLI & FastMCP Contracts
- `rush mem-profile [PATH] [--json]`
- `rush cold-start [PATH] [--json]`
- `rush benchmark check [PATH] [--json]`
- FastMCP: `rush_mem_profile`, `rush_cold_start`, `rush_benchmark`; all require `path` and an `options` object. Empty `{}` requests default options; consult each tool contract before supplying additional keys.
