# CI dependency installation plan — stop skipping tests for missing tools

## Problem

`uv run pytest tests/ -q` in the `Quality and tests` CI job (ubuntu-latest) currently
reports these as SKIPPED, every run, because the external binaries they exercise are
never installed on the runner:

| Test | Skip reason | Binary/package |
|---|---|---|
| `tests/test_ai_eval.py:191` | `Promptfoo must be installed for live local-provider acceptance` | `promptfoo` (npm) |
| `tests/test_engines.py:138` | `prettier not installed` | `prettier` (npm) |
| `tests/test_static_tools.py:43` (`needs_vulture`) | `vulture not installed` | `vulture` (pip) |
| `tests/test_static_tools.py:43` (`needs_knip`) | `knip not installed` | `knip` (npm) |
| `tests/test_static_tools.py:43` (`needs_radon`) | `radon not installed` | `radon` (pip) |
| `tests/test_static_tools.py:43` (`needs_jscpd`) | `jscpd not installed` | `jscpd` (npm) |
| `tests/test_static_tools.py:43` (`needs_sloppylint`) | `sloppylint not installed` | `sloppylint` (pip) |
| `tests/test_phase52_installed_artifacts.py:193` | no native archive at `dist/rush-linux-x86_64.tar.gz` | PyInstaller onefile build |
| `tests/test_release_asset_contract.py:157` | same, no native archive | same |

Every one of these is a real, verified-installable dependency (checked below), not a
placeholder or fictional tool. None of this is currently installed anywhere in
`.github/workflows/ci.yml`.

## Verified package identities and pinned versions

Checked against `docs/ENGINE_COMPATIBILITY.md`'s stated compatible ranges and each
registry directly (not guessed):

| Tool | Source | Compatible range (per `ENGINE_COMPATIBILITY.md`) | Pin |
|---|---|---|---|
| `vulture` | PyPI | 2.11+ | `vulture==2.16` (current) |
| `radon` | PyPI | 6.0+ | `radon==6.0.1` (current) |
| `sloppylint` | PyPI | 0.2+ | `sloppylint==0.5.1` (current — confirmed on PyPI directly, no git install needed) |
| `knip` | npm | **5.x** | `knip@5.88.1` — **latest is 6.35.1; pinning to 5.x is required**, the codebase's `KnipEngine` normalizer was built against knip 5's report format |
| `jscpd` | npm | **3.x** | `jscpd@3.5.10` — **latest is 5.2.0; pinning to 3.x is required**, same reason |
| `prettier` | npm | 3.x | `prettier@3.9.6` (current, within range) |
| `promptfoo` | npm | 0.90+ | `promptfoo@0.123.0` (current, within range) |

Pinning knip/jscpd to latest instead of their tested major would silently swap in a
different report schema and likely break `KnipEngine.normalize()` /
`JscpdEngine.normalize()`, which are tested against fixed fixture files
(`tests/fixtures/engine_reports/knip.txt`, `jscpd.txt`) — this is a real risk, not
theoretical, so pin exactly.

## CI changes

### 1. New job: `static-tool-acceptance`

Mirrors the existing `engine-contracts` job pattern (own job, own installs, narrow
`pytest -k`/file selection) rather than bloating `Quality and tests` with a Node.js
toolchain. Add to `.github/workflows/ci.yml`:

```yaml
  static-tool-acceptance:
    name: Static tool acceptance (real binaries)
    runs-on: ubuntu-latest
    steps:
      - name: Check out repository
        uses: actions/checkout@v7.0.1

      - name: Set up Python
        uses: actions/setup-python@v7.0.0
        with:
          python-version-file: .python-version

      - name: Set up uv
        uses: astral-sh/setup-uv@v10.0.1
        with:
          enable-cache: true

      - name: Set up Node.js
        uses: actions/setup-node@v4
        with:
          node-version: "22"

      - name: Install test dependencies
        run: uv sync --all-extras --frozen

      - name: Install Python static-analysis engines
        run: uv pip install vulture==2.16 radon==6.0.1 sloppylint==0.5.1

      - name: Install Node-based static-analysis and eval engines
        run: npm install -g knip@5.88.1 jscpd@3.5.10 prettier@3.9.6 promptfoo@0.123.0

      - name: Run static-tool and ai-eval acceptance
        run: uv run --no-sync pytest tests/test_static_tools.py tests/test_ai_eval.py tests/test_engines.py -q
```

`--no-sync` on the last step matches the existing `engine-contracts` job's pattern
(dependencies already installed by the prior `uv sync` step; avoids re-resolving).

### 2. Native release archive, for `test_phase52_installed_artifacts.py` / `test_release_asset_contract.py`

These specifically need `dist/rush-linux-x86_64.tar.gz` to exist on an **ubuntu-latest**
runner, matching the exact asset name `release.yml`'s `build-binaries` job already builds
for real releases. Add a build step to the `Quality and tests` job (where the full
`pytest tests/ -q` actually runs and currently skips these two), before `Run tests`:

```yaml
      - name: Build native release archive for installed-artifact probes
        run: |
          uv pip install pyinstaller
          uv run pyinstaller --onefile --name rush --paths src --collect-data license_expression rush_entry.py
          uv run python -c "
          from pathlib import Path
          from scripts.probe_installed_artifacts import build_release_archive
          import rush
          build_release_archive(Path('dist/rush'), Path('dist'), 'rush-linux-x86_64.tar.gz', rush.__version__)
          "
```

This reuses the exact `pyinstaller` invocation from `.github/workflows/release.yml:79`
(same flags, same entry point) so the test archive matches what real releases produce —
not a parallel, drifting build path. `rush.__version__` needs confirming as the actual
version-string accessor (`grep -n "__version__" src/rush/__init__.py` before wiring this
in) — I have not verified that exact symbol name yet.

## What this does NOT change

- No change to what `Quality and tests`'s existing steps do (lint, format, main test run,
  mypy, doc-sync, pip-audit, whitespace) — only adds the archive-build step before `Run
  tests`.
- No change to `engine-contracts`, `windows-contracts`, `artifact-probes`, or
  `representative-engines` jobs.
- Does not touch the untracked `docs/goals/mc00-benchmark-review-remediation/` directory
  (separate, unrelated to CI).

## Open item before implementing

- Confirm `rush.__version__` (or equivalent) is the right accessor for
  `build_release_archive`'s `version` argument — one grep, not done yet.

## Verification plan

1. Add the new job + build step exactly as above.
2. Push to a branch, watch the new `static-tool-acceptance` job and the modified
   `Quality and tests` job both go green with **0 skips** on the 9 lines listed in
   Problem above (`pytest -q -rs` output check).
3. Confirm existing jobs (`engine-contracts`, `windows-contracts`, `artifact-probes`,
   `representative-engines`) are unaffected (still green, same runtime).
