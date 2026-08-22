# Agentic Rush/Token Efficiency

## Token Efficiency Architecture (Phases 41–43)
* **Command Distillation**: 50–90% reduction on test outputs (`PytestDistiller`, `CargoDistiller`, `VitestDistiller`).
* **TOON v4.1 Serialization**: 40–65% reduction on tabular findings (`--format toon`).
* **AST Skeletons**: 85%+ reduction on module reading (`rush token outline`).
* **CCR Caching**: SQLite chunking with `<!-- ccr:chunk:HASH -->`.
