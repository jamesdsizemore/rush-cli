# FastMCP settings import emits unresolved lifespan warning

Status: needs-triage

## Observed evidence

On Python 3.12.12, `env -u VIRTUAL_ENV -u PYTHONPATH .venv/bin/python scripts/sync_docs.py --check` emits `IncompleteFieldDefinitionWarning` from `pydantic_settings/sources/utils.py:47` while loading runtime command contracts:

> Field 'lifespan' has an incomplete definition: its annotation contains an unresolved forward reference, so settings sources may fail to correctly resolve its value.

The checker proceeds to documentation validation. No settings failure or broken MCP request has been demonstrated by this warning alone.

## Intervention assessment

Nonblocking for P64-00; separate dependency/runtime triage required. Reproduce with the project's installed FastMCP/Pydantic versions and determine whether supported configuration inputs fail before selecting a dependency update or model rebuild. Do not suppress the warning or modify package versions solely to make documentation checks quiet.

## Scope

Outside the named P64-00 documentation behavior. Preserve as an open issue; no runtime or dependency change made.
