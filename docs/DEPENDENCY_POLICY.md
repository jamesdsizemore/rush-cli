# Dependency policy

Rush pins every direct runtime, development, and build dependency with `==`.

| Scope | Policy | Verification |
|---|---|---|
| Runtime/development | Resolved in `uv.lock`; direct entries in `pyproject.toml` are exact. | `tests/test_dependency_policy.py` and `uv sync --all-extras --frozen` |
| Build backend | `hatchling==1.32.0` is independently resolved by the build frontend. It is **not** expected in `uv.lock`. | `uv build` |
| Optional scanners | Never bundled Rush dependencies. Users install them locally; Rush discovers them from the active venv or `PATH`. | Adapter fixture and version tests |

Rush never installs an engine, rule pack, package manager, browser runtime, or vulnerability database. A changed runtime/development dependency requires an inspected `uv.lock` update; a build-only pin does not.
