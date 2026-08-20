# Phase 03 — supply chain, artifacts, secrets, provenance, and repository posture

> **Depends on:** Phases 00–02 accepted. **Excludes:** browser/runtime work and test-quality execution.

**Objective:** Add truthful multi-ecosystem dependency, SBOM, artifact, license, provenance, release, and repository-posture evidence without auto-downloading databases, images, attestations, or packages.

## Mandatory compact development protocol

Start/end every task via RTK Git scope. Use **Graft** to locate `sbom.py`, `supply_chain`/`security` tool paths, cdxgen/pip-audit/npm-audit/Gitleaks engines, release/CI helpers, catalog/config/CLI/MCP tests and callers. Use **context-mode** to query artifact/provenance/result/redaction/permission contracts. Use **RTK** for exact seam reads, report searches, staged diffs, and required venv verification. RED→GREEN→docs→self/spec/security reviews→targeted remediation→review again is mandatory per adapter.

## Candidate contract and exact scope

| Candidate | Selection gate / bounded invocation | Normalized evidence |
|---|---|---|
| OSV-Scanner | Official JSON + lockfile/SBOM mode + database/cache/network semantics verified; network refresh requires explicit permission | ecosystem/package/version/advisory/fixed version/source/freshness |
| Trivy | Filesystem/SBOM mode only after DB behavior is controllable; no image pull, remote repo, or automatic DB update | vulnerability/misconfiguration/license with DB freshness/provenance |
| Syft | Generate/read local SBOM only; no image fetch; write only to contained explicit artifact path | CycloneDX/SPDX component identities and source manifest |
| Grype | Consume explicit local SBOM; database update/network state opt-in and visible | advisory/component/fix/evidence freshness |
| Cosign/SLSA verifier | Verify user-supplied local artifact/attestation/bundle; no signing, upload, key generation, or remote fetch by default | verified/failed/unknown provenance evidence and safely redacted identity |
| OpenSSF Scorecard | Feasibility-gated unless local repo mode/output/network behavior is proven | repository posture facts, never a fabricated score |

## Task plan

1. **Artifact data model:** RED tests define SBOM/component/advisory/license/provenance fields, artifact path containment, freshness/database state, dedupe and secret-safe evidence. Implement additive normalization only after ADR 0002/0006 review.
2. **Repair existing supply-chain tools:** fixture-test cdxgen, pip-audit, npm-audit, Gitleaks clean/findings/malformed/nonzero/missing/version/timeout. Fix misleading summary/status/maturity claims found by independent review.
3. **OSV and SBOM pipeline:** research, pin compatibility, fake JSON fixtures, safe binary discovery/invocation/parser/config/docs. Treat report import as separate from live scan. Require explicit lockfile/SBOM target and distinguish stale/missing database from clean result.
4. **Trivy/Syft/Grype feasibility:** take one at a time. Add only after local input, no-pull/no-update default, output parser, and fixture gate are proven. Otherwise register as feasibility-gated with install/permission explanation.
5. **Provenance/release posture:** add verify-only Cosign/SLSA handling for explicit contained paths. Make signing/publishing/tagging impossible through Rush default workflows. Improve `release.py` evidence display without release side effects.
6. **Docs/review/CI:** update compatibility matrix, artifact input examples, freshness/DB/network explanation, config schema, CLI/MCP, troubleshooting, contributor fixture guide. Require independent security review for artifact paths and provenance identity handling.

## Failure and safety semantics

Missing binary/report/artifact/attestation → `skipped`; malformed BOM/JSON/attestation → `error`; unavailable/stale DB is explicit freshness state, never pass; no image/container/package/repository download, signing, upload, publish, key generation, or history rewrite. Any `allow_network` is explicit per tool and recorded in result provenance.

## Acceptance / non-goals

**Accept when:** each live scanner passes all real-integration fixtures; artifact evidence includes source/freshness; docs distinguish import versus execution; catalog/CLI/MCP parity and full gates pass.

**Non-goals:** mutation/contracts/fuzz/load, language semantic builds, UI/browser/Playwright/a11y/visual/DAST. Roll back individual adapters to truthful `skipped` state, never delete shared artifact fixtures or earlier security tools.