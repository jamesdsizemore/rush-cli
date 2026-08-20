# Optional advanced checks

Rush names advanced capabilities so their safety boundaries are visible. Some
commands import an explicit local report file; they do not launch the underlying
test or contact a target. Presence in `rush --help` does not mean live execution.

| Command | Intended permission | Current behavior |
|---|---|---|
| `mutation` | live execution would need `allow_slow` | Imports a contained local report; never runs mutation tests. |
| `e2e` | `allow_browser` | Guarded placeholder; generic CLI has no permission option, so it skips. |
| `fuzz` | live execution would need `allow_fuzz` | Imports a contained local report; never starts a fuzzer. |
| `load` | live execution would need `allow_network` | Imports a contained local report; never contacts a target. |
| `snapshot` | baseline changes would need `accept` | Imports a contained local report; never changes a baseline. |
| `visual` | browser/baseline work needs consent | Guarded placeholder; skips. |
| `semantic-drift` | browser **and** slow consent | Experimental engine path; CLI has no consent options and therefore skips. |

`coverage`, `pbt`, `flaky`, and `contract` are also contained local report
importers. For every importer, give the report file as `PATH`; a directory
without an explicit report remains `skipped`. Coverage accepts coverage.py JSON,
LCOV, and Cobertura XML; flaky accepts JUnit XML; the other importers accept the
documented JSON summaries. A malformed report is an `error`, not an empty scan.

The permission names in this table describe future safety prerequisites, not
hidden command-line switches. No live mutation, fuzz, load, browser, provider,
or baseline-update adapter is implemented in this release. These defaults prevent
an ordinary command from launching a browser, consuming significant time, sending
load to a target, fuzzing a process, or changing baselines.

Do not work around a guard by calling internal Python APIs from an untrusted assistant. An eventual permission surface must be explicit, scoped, tested, and documented. Follow [Permissions](../safety/permissions.md).
