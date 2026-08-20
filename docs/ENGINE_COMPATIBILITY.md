# Engine compatibility and integration contract

A catalog command is not automatically a live scanner. Rush labels every tool with one maturity:

- `real_adapter`: Rush discovers a local binary, invokes a bounded list-only command, parses output, and has fixture-backed tests.
- `catalog_only`: a visible command with no claimed live engine execution.
- `guarded_placeholder`: intentionally returns `skipped` until a future adapter/importer meets the contract.
- `direct_adapter_candidate`, `importer`, and `feasibility_gated`: reserved truth states for future work; none may be presented as supported execution without evidence.
- `browser_runtime`: browser-dependent work, reserved for Phase 08.

## Gitleaks reference adapter

| Field | Contract |
|---|---|
| Binary / tested baseline | `gitleaks` / `8.30.1` |
| Invocation | Local `gitleaks detect --source PATH --report-format json --report-path - --no-banner` |
| Input / side effects | Explicit local path; no installation, download, or baseline write by Rush |
| Output | JSON findings normalized to secret-safe findings; secret values are never emitted by Rush |
| Missing engine | `skipped` |
| Malformed output / timeout / command error | structured `error`, never an invented public status |

Every future adapter must document the exact engine release, source/license, supported platform, safe command, machine output/exit behavior, network/cache/build/write defaults, timeout, fixtures, and known limitations before it is called supported.

## Phase 01 truth audit

| Catalog command | Current maturity | Engine / baseline | Verified parser-fixture owner | Support boundary |
|---|---|---|---|---|
| `secrets` | `real_adapter` | Gitleaks `8.30.1` | `tests/test_gitleaks_reference.py` | Supported local JSON adapter. |
| `coverage`, `mutation`, `pbt`, `flaky`, `contract`, `snapshot`, `fuzz`, `load` | `importer` | Rush-owned local report readers | `tests/test_coverage_importer.py`; `tests/test_mutation_importer.py`; `tests/test_pbt_importer.py`; `tests/test_flaky_importer.py`; `tests/test_contract_importer.py`; `tests/test_snapshot_importer.py`; `tests/test_fuzz_importer.py`; `tests/test_load_importer.py` | A target file is imported as an explicit report; directories remain skipped without a report. Importers never launch an engine, repeat tests, contact a target, write a baseline, or accept path traversal. Coverage accepts coverage.py JSON, LCOV, and Cobertura XML; flaky accepts JUnit; the remaining importers accept their documented JSON summaries. |
| `codeql` | `importer` | Rush-owned contained SARIF reader | `tests/test_codeql_importer.py`; `tests/test_capabilities.py` | Import an explicit, contained CodeQL SARIF 2.1.0 file only. Every run must identify a CodeQL driver; foreign, malformed, non-object, missing, or target-escaping reports are never treated as findings. Rush does not invoke CodeQL, create a database, build a project, download query packs, install an SDK, or contact a service. |
| `lint`, `format`, `test`, `typecheck`, `dead`, `complexity`, `slop`, `templates`, `commit-msg` | `feasibility_gated` | Catalogued local engine candidates | None registered | Commands are retained, but they must not be presented as live scanner integrations until deterministic parser/invocation coverage is registered. Repository markers for unsupported ecosystems are detected in stable order and return `skipped`; Rush does not invoke their commands, so it cannot trigger a restore, build, cache write, or network fetch. |
| `security` | `real_adapter` | pip-audit, npm audit, OSV-Scanner | `tests/test_pip_audit_reference.py`; `tests/test_npm_audit_reference.py`; `tests/test_osv_reference.py` | Explicit local requirements/lockfile routing only. pip-audit receives a local `requirements.txt`; npm audit is offline and requires `package-lock.json`; OSV-Scanner is offline. It is dependency evidence, not source SAST. |
| `yaml` | `real_adapter` | Spectral `6.16.3` | `tests/test_spectral_reference.py` | Supported local JSON YAML/OpenAPI adapter. Rush supplies a static no-extends local ruleset, never passes a resolver/output path, and blocks remote `$ref` values before execution. |
| `sql` | `real_adapter` | SQLFluff `4.3.0` | `tests/test_sqlfluff_reference.py` | Supported local JSON SQL adapter. Rush ignores local configuration, supplies owned ANSI/raw configuration, and never enables dbt, fix, or output writes. |
| `markdown` | `real_adapter` | markdownlint-cli `0.49.1` | `tests/test_markdownlint_reference.py` | Supported local JSON Markdown adapter. Rush supplies empty owned JSON config and ignore files, preventing project configuration and ignore discovery. |
| `actions` | `real_adapter` | actionlint `1.7.12` | `tests/test_actionlint_reference.py` | Supported local JSON GitHub Actions workflow adapter. Rush supplies an empty owned config and disables actionlint's shellcheck/pyflakes child integrations. |
| `containerfile` | `real_adapter` | Hadolint `2.15.1` | `tests/test_hadolint_reference.py` | Supported local JSON Containerfile adapter; Rush supplies an empty owned config so project/home Hadolint configuration and `HADOLINT_*` environment configuration are not inherited. |
| `iac` | `real_adapter` | TFLint `0.64.0`; Checkov `3.3.9` | `tests/test_tflint_reference.py`; `tests/test_checkov_reference.py` | Supported local JSON Terraform adapters, in declared `tflint`, then `checkov` order. |
| `sast` / Semgrep | Not catalogued | Semgrep `1.173.0` candidate | None | No adapter exists. A future local-rule-only implementation requires official safe-invocation, no-network, output/exit, license, fixture, CLI/MCP, and Windows evidence. |

The catalog enforces that every engine-backed `real_adapter` has a registered deterministic suite. A registry entry is only a promotion prerequisite; the referenced tests remain the proof.

## Deterministic source-policy markers

`review` can flag explicitly configured unfinished-scaffold text without
attributing code to a person or model. The policy is opt-in: no markers are
enabled by default. Use `source_policy_exclude` to suppress generated or
otherwise intentionally retained paths.

```toml
[review]
scaffold_markers = ["TODO: replace this scaffold"]
source_policy_exclude = ["generated/**"]
```

Each matching source line produces the stable `scaffold-marker` warning with a
repair message. Review policy only reads local source files; it does not invoke
an external engine, network service, or browser runtime.

## Phase 02 IaC and content inventory

| Command | Current route / catalog engine | Maturity | Fixture owner | Current boundary |
|---|---|---|---|---|
| `iac` | `IacTool` routes `.tf` files to TFLint, then Checkov | `real_adapter` | `tests/test_tflint_reference.py`; `tests/test_checkov_reference.py` | TFLint `v0.64.0` (MPL-2.0): local `--chdir DIR --format json --call-module-type none`; Rush omits `--init`, `--force`, and `--fix`, never runs Terraform initialization, and maps exits `0`/`2`/`1` to clean/findings/error. Checkov `3.3.9` (Apache-2.0): local `--directory DIR --framework terraform --output json --skip-download --download-external-modules false`; Rush passes an allowlisted child environment, omits platform credentials and Checkov config, never enables external checks or source rewriting, and maps clean `0`/failed-check `1` JSON reports to clean/findings. Malformed, partial, timeout, or inconsistent reports are structured `error`. |
| `yaml` | `YamlTool` / Spectral | `feasibility_gated` | None | Retained route only; OpenAPI/YAML policy behavior is not supported until structured fixture evidence exists. |
| `sql` | `SqlTool` / SQLFluff | `feasibility_gated` | None | Retained route only; dialect/config/network/write behavior remains unverified. |
| `templates` | `TemplatesTool` / djLint | `feasibility_gated` | None | Retained route only; template scope and parser behavior remain unverified. |
| `containerfile` | `ContainerfileTool` / Hadolint | `real_adapter` | `tests/test_hadolint_reference.py` | Hadolint `2.15.1` (GPL-3.0): local `--config RUSH_EMPTY_CONFIG --format json --no-color FILE`; Rush prevents implicit project/home config and `HADOLINT_*` environment configuration, performs no install/download/write, maps clean `0` and findings `1`, and returns malformed/inconsistent JSON as structured `error`. |
| `actions` | `ActionsTool` / actionlint | `real_adapter` | `tests/test_actionlint_reference.py` | actionlint `1.7.12` (MIT): local `-config-file RUSH_EMPTY_CONFIG -shellcheck= -pyflakes= -no-color -format '{{json .}}' FILE`; Rush prevents implicit actionlint config, disables child linters, performs no install/download/write, maps clean `0` and findings `1`, and returns malformed/inconsistent JSON as structured `error`. |
| `markdown` | `MarkdownTool` / markdownlint-cli | `real_adapter` | `tests/test_markdownlint_reference.py` | markdownlint-cli `0.49.1` (MIT): local `--config RUSH_EMPTY_JSON --ignore-path RUSH_EMPTY_IGNORE --json FILE...`; Rush prevents implicit project config/ignore discovery, never passes `--fix`, `--rules`, or output-file flags, performs no install/download/write, maps clean `0` and findings `1`, and returns malformed/inconsistent JSON as structured `error`. |

The Phase 02 first code gate is a contained structured-IaC parser test. No
engine will be routed or promoted until its public compatibility record covers
exact version, source/license, local invocation, machine output, exit behavior,
cache/network/build/write behavior, Windows behavior, and deterministic
fixtures.

## Deferred ansible-lint candidate

ansible-lint `26.8.0` is not supported. Although it can emit SARIF JSON, its
documented project-root execution can create a project `.cache`, and upstream
warns linting untrusted content can execute code through Ansible configuration
and vault sources. Rush has no dedicated Ansible route or controlled environment
contract, so it remains feasibility-gated and is not added to `yaml`.

codespell `2.4.3` is also feasibility-gated: it has no established structured
report, discovers project `pyproject.toml` configuration even with `--config`,
and Phase 02 has no generic content aggregation command. Rush never passes its
mutating `--write-changes` option.

Vale `3.17.1` is feasibility-gated. Its style system discovers global/project
configuration and `vale sync` can create/remove style paths and download
packages. Rush does not own a versioned local Vale config/styles corpus or
permit that synchronization behavior.

Lychee `0.24.2` is feasibility-gated. Live link checking is network activity,
which Phase 02 forbids without a dedicated permission ADR; Rush has no
import-only report route to label separately either.

## Phase 03 offline dependency and SBOM evidence

| Engine / route | Tested baseline | Contract |
|---|---|---|
| OSV-Scanner / `security` | `2.5.1` (Apache-2.0) | Rush selects one explicit local lockfile and invokes `osv-scanner scan --offline --format json -L LOCKFILE`. Offline mode neither sends dependency data nor downloads or refreshes the local OSV database. Missing scanner remains `skipped`; a missing database or malformed JSON is `error`; a nonzero exit with valid vulnerabilities is normalized as `fail`. Rush does not pass `--download-offline-databases`, image, source, serve, or remote modes. |
| cdxgen / `sbom` | `13.0.1` (Apache-2.0) | Rush writes only to an explicit output contained within the selected local target and refuses overwrite unless requested. cdxgen nonzero generation exits are structured `error`, never synthetic findings. Rush does not supply URL, purl, image, profile, evidence, audit, license-fetch, plugin, signing, or publishing options. |

OSV support is limited to the offline local-database contract. Database freshness is external evidence, never inferred as a clean result, and Rush never downloads a database.

Trivy `0.74.0`, Syft `1.51.0`, and Grype `0.117.0` are feasibility-gated in this release. A release page is not proof of contained operation: Rush has not established versioned, machine-output fixture contracts that prevent their database refresh, image/archive pull, cache mutation, or implicit remote-source behavior. They therefore have no executable route.

Cosign `3.1.3` is likewise feasibility-gated. Rush has not established a no-remote-rekor, explicit-local-bundle verification contract with deterministic JSON evidence and safe identity redaction. Rush has no signing, key generation, upload, publication, or provenance-verification command until that contract exists.
