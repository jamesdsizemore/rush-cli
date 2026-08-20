# Phase 02 — IaC, policy, configuration, templates, SQL, and content scanners

> **Depends on:** Phases 00–01 accepted. **Excludes:** supply-chain provenance, advanced reliability, and all browser/runtime work.

**Objective:** Deliver real, safe local inspection for infrastructure/configuration/content inputs without downloading schemas/modules or mutating a project.

**Phase-00/01 handoff required before the first edit:** use the accepted five-status mapping and execution metadata, maturity enum, resolver-only binary policy, catalog parity tests, and Gitleaks reference fixture contract. Phase 01 owns SAST, secrets, dependency security, actions/zizmor, and source policy; this phase must not absorb or relabel them.

## Mandatory compact development protocol

Every task starts/ends with RTK Git scope. Use **Graft** to discover `tools/iac.py`, existing focused YAML/SQL/template/Markdown/container seams, TFLint/Checkov/Spectral/SQLFluff/djLint/Hadolint adapters, catalog/config registration, `tests/test_content_infra_tools.py`, and `tests/test_config.py`; use **context-mode** on that bounded seam and ADRs 0001/0004/0005/0007/0009; use **RTK** for exact reads, task anchors, diffs, and venv tests. Each slice follows RED→GREEN→docs→self/spec/security review→fix/re-review→scoped Git gate.

## Exact external-engine baselines, ownership, and selection gates

| Integration | Exact baseline and release source | Exact safe behavior / owned files/tests |
|---|---|---|
| TFLint / Checkov repair | TFLint `0.64.0` [release](https://github.com/terraform-linters/tflint/releases/tag/v0.64.0); Checkov `3.3.9` [release](https://github.com/bridgecrewio/checkov/releases/tag/3.3.9) | Existing `tools/iac.py`/engine seams only; explicit local Terraform/IaC paths and structured output; never `init`, module download, remote checks, or apply. `test_content_infra_tools.py` fixtures. |
| KICS / Conftest | KICS `2.1.21` [release](https://github.com/Checkmarx/kics/releases/tag/v2.1.21); Conftest `0.69.0` [release](https://github.com/open-policy-agent/conftest/releases/tag/v0.69.0) | `feasibility_gated` until exact JSON, policy bundle path, license, exit/network evidence exists. If accepted, extend `tools/iac.py` with contained local policy paths; fake output/missing/config tests. |
| kubeconform / KubeLinter | kubeconform `0.8.0` [release](https://github.com/yannh/kubeconform/releases/tag/v0.8.0); KubeLinter `0.8.3` [release](https://github.com/stackrox/kube-linter/releases/tag/v0.8.3) | `feasibility_gated`. A new focused `kubernetes` ToolSpec/module is allowed only after RED registry/CLI/MCP tests and documented local schema policy; never silently overload `iac`. Multi-doc/invalid/network-block fixtures. Helm remains a later explicitly approved compatibility record, not a Phase 02 live adapter. |
| Hadolint / ansible-lint | Hadolint `2.15.1` [release](https://github.com/hadolint/hadolint/releases/tag/v2.15.1); ansible-lint `26.8.0` [release](https://github.com/ansible/ansible-lint/releases/tag/v26.8.0) | `feasibility_gated` until machine-output and no image/role-download proof; then engine plus focused content/infra test owner. |
| Spectral / SQLFluff / djLint / markdownlint | Spectral `6.16.3`, SQLFluff `4.3.0`, djLint `1.44.2`, markdownlint-cli `0.49.1` (official project releases verified 2026-08-18) | Repair the existing focused `yaml`, `sql`, `templates`, and `markdown` commands only; explicit config/local inputs and malformed/config/timeout fixtures. |
| codespell / Vale / Lychee | codespell `2.4.3`, Vale `3.17.1`, Lychee `0.24.2` (official project releases verified 2026-08-18) | `feasibility_gated`; no generic `content` catch-all command. A link checker remains blocked unless a future explicit network-permission ADR approves it; imported reports are separately labelled. |

All table versions are external compatibility pins, not Rush dependencies. No scanner package, SDK, schema, policy bundle, or runtime is added to `pyproject.toml`/`uv.lock`. Each candidate stays feasibility-gated until its exact version probe, official output/exit contract, license, and network/cache/build/write behavior are recorded in `docs/ENGINE_COMPATIBILITY.md` and local `research/engine-records/`.

## Task plan

1. **Inventory and research:** map only the Phase 02 catalog commands to the Phase-00 maturity enum. Before code, record the table baseline's official CLI/version/license/output/exit/cache/network/build/write behavior and exact compatibility pin in public docs/local research. Reject engines without a stable machine output or safe local invocation.
2. **Common structured IaC parser:** RED tests for multi-file/multi-document target containment, JSON/SARIF-like location/severity/rule mapping, malformed output, path traversal in reported locations, and missing config/binary. Implement only shared normalization allowed by Phase 00.
3. **Repair existing adapters:** make TFLint `0.64.0`/Checkov `3.3.9` fixture-backed with valid clean, valid-warning, valid-failure, malformed, nonzero, missing, version, and timeout cases. Map valid findings exits to existing `warn`/`fail`; block implicit Terraform initialization/downloads.
4. **Policy/cluster candidates:** add KICS `2.1.21`, Conftest `0.69.0`, kubeconform `0.8.0`, or KubeLinter `0.8.3` one at a time only after its feasibility gate. Policy/schema input paths must be explicit and contained; remote resolution is `skipped` or blocked without opt-in. New Kubernetes behavior requires a distinct `kubernetes` catalog/tool/CLI/MCP parity slice.
5. **Focused container/template/SQL/documentation commands:** add/repair Hadolint `2.15.1`, ansible-lint `26.8.0`, Spectral `6.16.3`, SQLFluff `4.3.0`, djLint `1.44.2`, markdownlint `0.49.1`, codespell `2.4.3`, Vale `3.17.1`, and Lychee `0.24.2` one at a time after structured-output feasibility. Preserve focused command ownership; report import and live execution remain separately labelled. Lychee must remain non-live without a dedicated network permission contract.
6. **Documentation/parity/review:** update config schema/examples, engine matrix, catalog maturity, CLI/MCP descriptions, install/troubleshoot docs and contributor fixtures. Run dual independent review and remediate only verified defects.

## Failure/permission contract

No matching files, missing binary/config/policy/schema, remote dependency blocked, or unsupported project marker → canonical `skipped`; malformed report/version/command failure → safe `error`; valid findings map to existing `warn`/`fail`; timeout/cancelled are `error` with Phase-00 `metadata.terminal_reason`/`metadata.partial`. Never run `terraform init/plan/apply`, Helm install, Kubernetes apply, Ansible run, container build, link crawl, or remote schema download by default.

## Acceptance and non-goals

**Accept when:** each claimed engine has the full Phase 00 gate; all config tables validate; CLI/MCP/catalog docs agree; multi-document and false-positive fixtures pass; CI uses only fake outputs/declared optional local engines.

**Non-goals:** dependency/SBOM/provenance, test execution, browser DOM/UI/visual/a11y/E2E/DAST. Rollback reverts only scoped adapter/docs commits and restores `skipped` maturity.