# Workflow: Supply Chain Security & Flagship Release

## 1. Generating Build Attestation
```bash
rush attest --out build.intoto.jsonl
```

## 2. Auditing Dependencies and Dead Assets
```bash
rush license-matrix
rush dead-asset
```

## 3. Synthesizing PR Cards
```bash
rush pr-synthesize --base main
```
