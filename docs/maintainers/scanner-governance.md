# Scanner governance

This policy governs promotion, selection, lifecycle, and retention for Rush
scanner evidence. It complements the executable maturity contract in
[Engine compatibility](../ENGINE_COMPATIBILITY.md).

## Selection and promotion record

Before promoting a catalog entry or changing its maturity, maintainers record:

| Record field | Required evidence |
|---|---|
| Tool, engine, and maturity | Catalog entry and exact executable/importer boundary. |
| Intended scope | Explicit local files, reports, or project markers; no inferred remote target. |
| Preconditions | Required local report, configuration, binary, and permission state. |
| Fixture proof | Clean, findings, malformed, missing-prerequisite, error/timeout where applicable, and redaction tests. |
| Version boundary | Tested engine version or an explicit statement that Rush does not probe or assert a version. |
| Safety boundary | Network/cache/build/write behavior, containment, redaction, and default-denial behavior. |
| User surface | CLI help, MCP schema if callable, ToolResult fields, catalog, compatibility, and troubleshooting documentation. |

The record belongs in the phase ledger and linked tests/docs. A catalog entry,
PATH discovery result, or a successful ad hoc local command is not promotion
evidence by itself.

## Capability inventory and planner policy

`rush capabilities` is observational: it reads local markers, configuration,
report names, and `PATH`, but does not execute or version-probe an engine. It
reports `configured`, `installed`, `applicable`, `missing`, and `blocked`
separately. `installed` therefore means only that a known binary was found, not
that its version is compatible or that it has completed a scan.

`rush plan` is also observational. Its deterministic steps carry local
prerequisite descriptions and reasons; selecting a step neither runs it nor
grants a browser, network, slow, write, or baseline-changing permission.

## Evidence lifecycle and retention

- Normalize and redact before returning findings or logging diagnostics.
- Preserve normalized finding fingerprint, provenance, scope, and source
  location only when they are already needed for the result; do not retain raw
  scanner output as a durable Rush store.
- Imported reports remain user-owned local inputs. Rush does not upload them,
  create a review baseline by default, or silently overwrite a baseline.
- Direct review uses supplied `changed_files` only. It never obtains a Git diff
  or change history itself.
- A caller may hold an in-memory fingerprint baseline for `new`/`existing`
  comparison. Persisting, replacing, or accepting a baseline requires a future
  explicitly authorized user surface and a containment/overwrite contract.

## Error budget and release decisions

Rush has no special success status for partial evidence. A timeout,
cancellation, malformed report, or command failure remains a structured
`error`; skipped child evidence is retained as partial aggregation metadata.
Neither may be rewritten as `ok`.

For a release or maturity promotion, the error budget is **zero untriaged
errors in required deterministic fixtures and verification gates**. A new
structured-error path must have a fixture, an owner, a recovery/documentation
path, and a reviewed status mapping before promotion. Optional external engines
may remain `skipped`; they must not be represented as passing evidence.

## Deprecation policy

Do not silently remove or relabel a visible scanner. Deprecation requires a
changelog entry, migration/alternative guidance, retained structured behavior
or a documented removal version, and updates to catalog, CLI/MCP, compatibility,
troubleshooting, and tests. A mature adapter that loses its fixture or safety
contract is demoted to the most truthful non-executing maturity rather than left
marketed as supported.
