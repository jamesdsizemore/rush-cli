# CI and packaging

The repository workflow performs locked `uv sync --all-extras --frozen`, Ruff lint, Ruff format check, pytest, pip-audit, whitespace check, and `uv build`. A second job runs a bounded representative Python-engine contract set.

Package validation:

```bash
uv build
uv venv /tmp/rush-wheel
uv pip install --python /tmp/rush-wheel dist/*.whl
/tmp/rush-wheel/bin/python -c "import rush"
```

Adapt paths on Windows and validate the sdist in a separate clean environment. Do not rely on the development checkout being importable. Broad external-engine compatibility belongs to parser fixtures; do not create an unbounded all-runtime CI image.
