# ADR-0036: Air-Gapped SLM Local ONNX Runtime and SLSA Attestation

## Status
Accepted (v0.2.0 / Phase 44-46)

## Context
Regulated enterprise environments (defense, healthcare, finance) prohibit sending proprietary source code to cloud LLM APIs, while SOC2/FedRAMP compliance requires non-tamperable proof of build quality.

## Decision
1. Implement `rush offline` (`src/rush/providers/offline.py`) and FastMCP tool `rush_review(offline=True)` embedding lightweight ONNX Runtime / `llama.cpp` small language models (Qwen 2.5 Coder 1.5B/3B 4-bit quantized).
2. Execute in-process code review, docstring synthesis, and AST pattern matching with `--allow-network=False`.
3. Implement `rush attest` (`src/rush/release/attest.py`) to generate in-toto v1.0 / SLSA Level 3 cryptographic provenance statements recording commit SHA, artifact digests, and quality gate results signed with local Cosign or Git SSH keys.

## Consequences
- **Positive**: Enables full AI-assisted code review and cryptographic attestation in 100% air-gapped environments.
- **Negative**: Adds local CPU/GPU inference requirements when running offline models.
- **Safety**: Strict zero-network guarantees; cryptographic signing of release artifacts.
