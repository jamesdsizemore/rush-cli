# The Interactive Terminal UI

`rush ui` opens a persistent, keyboard-driven dashboard in your terminal for exploring a
project's checks, findings, memory, git state, and artifacts — without leaving the shell.

---

## 1. Launching

```bash
uv run rush ui
```

With no arguments, it opens on the current directory. Give it one or more project paths to
open and switch between multiple projects in the same session:

```bash
uv run rush ui path1 path2
```

The interface starts immediately on a read-only Overview. It never runs an analysis on its
own — starting a scan or check is always an explicit action you take once inside (see
[Section 4](#4-running-work-and-quitting)).

Add any of the standard execution-permission flags before opening the interface if the work
you plan to start needs them: `--allow-network`, `--allow-download`, `--allow-cache-write`,
`--allow-build`, `--allow-slow`, `--allow-artifact-write`, `--allow-browser`.

### Non-interactive snapshot

`rush ui` needs both stdin and stdout attached to a real terminal to open the interface. If
either isn't a TTY (for example, when its output is redirected or piped), or if you pass
`--json`, it prints each project's read-only status instead and exits — the interface never
opens. A plain-text snapshot looks like this:

```
myproject: unregistered project /path/to/myproject; no analysis has run; project is not registered.
Next: rush status /path/to/myproject --json
      rush check /path/to/myproject
```

`--json` prints the same per-project data as a JSON array, each entry holding the project's
name, path, and the full `rush status` payload for that root.

---

## 2. The eight sections

The interface is organized into eight sections, switchable at any time:

| Section | Shows |
|---|---|
| Overview | Project registration state and the entry point for adding, creating, or relinking a project |
| Map | The project's file/module tree, navigable and searchable; a finding row keeps its provenance (severity, tool, path) next to the message, shown again in the expanded detail view |
| Scans/Findings | Results from the last check or scan run, one finding per row |
| Memory | Stored memory records: browse, search, create, edit, promote, archive, delete |
| Tokens | Token-usage data for past runs, filterable by run, agent, or session identity |
| Git | Commit history and the current dirty working-tree diff |
| Artifacts | Captured tool artifacts plus other shared evidence (scan outputs, handoffs, memory records): inspect, search, and export them |
| Setup/Agents | Agent setup stages and their grants, plus handoff preparation |

---

## 3. Navigation keys

These work from anywhere in the interface unless a specific mode below overrides them:

| Key | Action |
|---|---|
| `F2` | Open the project selector (switch between open projects) |
| `F3` | Open the section chooser |
| `1`–`8` | Inside the section chooser, jump straight to that section |
| `Tab` / `Shift+Tab` | Cycle panes forward / backward |
| `↓`/`j`, `↑`/`k` | Move the selection down / up |
| `→`/`l`, `←`/`h` | In Map: expand / collapse the selected node |
| `+` / `-` | Expand / collapse the detail pane — in every section (Map nodes also keep `→`/`l` and `←`/`h`; in Git, `+` shows the selected commit's diff detail; in Memory, `+` is the same as `x`) |
| `Enter` | Inspect the selected row, or accept the highlighted choice in an overlay |
| `Escape` | Back / dismiss the current overlay / decline |
| `/` | Filter or search — see below, its effect depends on where you are |
| `?` | Show the current key bindings |
| `q` | Quit |
| `M` | Jump to the Memory section |
| `G` | Jump to the Git section |
| `m` | Jump to the Tokens section |
| `F5` | Refresh the current section |

When focus reaches Actions, the selected action has a `>` marker in the footer, even when
the Actions pane is outside the visible area. `Enter` runs that enabled action; `F5`
refreshes the current section directly.

`/` behaves differently per section: in Map it searches the map's own nodes, in Artifacts it
searches the captured artifact index, in Tokens it opens a run/agent/session filter, and
everywhere else (Scans/Findings) it filters the visible findings.

In Scans/Findings, `/` matches against severity, step status, tool, engine, path, and message
by default. Prefix the query with a field name to narrow to just that field:
`severity:error`, `status:warn`, `tool:ruff`, `engine:bandit`, or `path:some/file.py`.
`Escape` clears the filter back to the unfiltered list. While a filter is active, the section
title shows the shown-versus-total count, for example `Findings (1 of 3)`.

The project selector (`F2`) is navigated with `↓`/`j`, `↑`/`k`; `Enter` switches to the
highlighted project, `Escape` cancels with no switch. Past the list of open projects it also
offers **Add this folder**, **Create a new project**, and **Choose later** as extra rows.

The section chooser (`F3`) is navigated the same way, or jump straight to a section by
pressing its digit (`1` Overview through `8` Setup/Agents). Past the eight sections it also
offers **Check**, **Scan**, **Projects**, and **Help** as extra rows. Pressing `F3` again
while the chooser is open cycles to the next section.

---

## 4. Running work and quitting

Inside the Overview or Scans/Findings sections:

| Key | Action |
|---|---|
| `s` | Start a full scan (reviewed before it runs) |
| `C` | Start a check (reviewed before it runs) |
| `r` | Rescan the last run (reviewed before it runs) |
| `c` | Cancel the currently running scan |
| `H` | Review and send an agent handoff (also available in Setup/Agents) |

A reviewed action — scan, check, rescan, handoff, artifact export, setup apply/retry — opens
a grant-review overlay first. Nothing runs until you accept it: `y` accepts, `Escape` or any
other key declines.

Pressing `c` is honored immediately even while a scan, rescan, or check is still starting (still
resolving which process owns the run, before any work has been dispatched): the key returns in
under 25ms and no local work, admission, or dashboard dispatch ever happens.

### Quitting while work is running

Pressing `q` (or `Ctrl-C`) while a run is in progress opens a three-way choice instead of
quitting immediately:

| Key | Choice | Effect |
|---|---|---|
| `d` / `Enter` | Detach | A run owned by the dashboard keeps running in the background; a run this TUI process owns is cancelled with its partial result saved, since nothing can keep a bare CLI process's work alive past its own exit |
| `c` | Cancel and stay | Requests cancellation but the TUI process never exits — you keep watching the run finish |
| `r` / `n` / `Escape` | Return | Cancels the quit; you keep observing |

A second `Ctrl-C` while this menu is open Detaches. If input reaches end-of-file (stdin
closed), the TUI Detaches the same way, then restores the terminal and prints the cause to
stderr.

---

## 5. Memory

Inside the Memory section (`M`, or section `4`):

| Key | Action |
|---|---|
| `↓`/`j`, `↑`/`k` | Move the selection |
| `Tab` / `Shift+Tab` | Move keyboard focus through search, filter, list, inspect, and edit; `Enter` then does what `/`, `f`, `x`, `x`, or `e` does for the focused control |
| `]` / `[` | Page forward / backward through the record list by page cursor; in detail, scroll visible content, related records, and receipts (or return to the cached prior content page) |
| `f` | Open the filter form (`Tab` cycles fields, `Enter` applies, `Escape` cancels) |
| `S` | Cycle the subject filter through all seven subjects: `active_context`, `episodic`, `preference`, `failure`, `architectural_decision`, `domain_knowledge`, and `skill_pattern` |
| `/` | Search records by text |
| `v` | Show the history of the selected record: every stored version, oldest first, with its trust, freshness, and integrity |
| `E` | Explain the selected record, or the typed search when no record is selected: the recorded rationale, contrary evidence, what was tried, affected code references, and unknowns |
| `c` | Correct the selected record: `Tab` cycles kind, reason, and content, `Space` on kind cycles correct, reject, and supersede, `Enter` previews, `y` applies, `Escape` cancels |
| `I` | Review a portable memory capsule import: type or paste the capsule path, `Enter` previews it, `Space` marks a constraint to confirm, `y` applies, `Escape` cancels |
| `b` | Toggle expanded content between `base64` and `utf8`; the next `x` fetches the pages again in the chosen form |
| `Space` | Select/deselect the highlighted record for a bulk action (`>[x]` marks a selected row) |
| `n` | Create a new memory record (`Tab` cycles fields, `Enter` previews and submits, `Escape` cancels) |
| `x` | Show the selected record's stored content, related records, and recorded write/use receipts; press again for the next bounded content page |
| `+` | Expand the selected record (same as `x`) |
| `-` | Collapse the selected record's detail |
| `e` | Edit the selected record |
| `o` | Choose owner scope for the next mutation (`Tab` cycles kinds, `Enter` applies, `Escape` cancels) |
| `a` | Preview archiving the selected record(s) |
| `p` | Preview promotion using current, matching records from distinct sources |
| `d` | Preview deleting the selected record(s) |
| `w` | Preview maintenance (cleanup) on the record set |
| `y` | Accept a pending preview (archive, delete, maintenance, or new-record submit) |
| `n` / `Escape` | Cancel a pending preview |
| `r` | If a conflict is shown after an edit, refresh and re-review it |
| `?` | Show current key bindings |
| `q` | Quit |

Every write (create, edit, promote, archive, delete, maintenance) previews first and applies only on
`y`; `n` or `Escape` cancels with nothing written. If another process edited a record between
your edit and its review, the review is flagged as a conflict and `r` re-fetches it before
you retry. Record page status stays above the list; after an owner change, the current
owner and confirmation appear on screen. Expanded content shows its record version and byte
position. `]` / `[` scroll visible detail rows; `x` continues until `complete`.
Related records appear only when visible to the current project. Receipts name recorded
operations and their version. Promotion requires genuinely corroborating, current
records with the same subject, content, owner, and symbol from distinct sources; one source
is denied. A changed corroborating record refuses promotion at confirmation.

To open the Memory section and search records for a word, press these keys in order, typing the word in place of `needle`:

<!-- t09-example: tui-memory-search -->
```text
M / needle enter
```

### What the Memory section shows and why

What the section lists depends on whether the project has a memory grant. With a grant, the
section lists what the grant approves, and a source filter only narrows that list. A project
that was never enrolled keeps the legacy rule, where the section needs named sources. Each row
shows the record id and version, owner, trust, freshness, and source. `v` and `E` show cited
exact records only; where no rationale was recorded the explanation says it is unknown, and no
model is called. Record text from any source, including hostile HTML or terminal control
sequences, is shown as escaped literal text and is never interpreted.

A correction (`c`) never edits a version in place: applying it stores a new version, and the
old version then answers `conflict` instead of returning its content. A conflict keeps the
text you typed in the correction or edit form, shows `edit conflict on ID vN -- [r] refresh and
re-review`, and waits for `r`. `Escape` leaves every memory form with nothing written and puts
focus back on the list.

Imported capsule records arrive as imported and unverified, and an import changes nothing until
you confirm it with `y`.

### Memory states

When a request cannot show records, the section prints `state: STATE: reason` and an
`action:` line that says what to do next:

| State | Meaning | Action shown |
|---|---|---|
| `absent` | No memory store exists for this project | Record one with a memory write |
| `empty` | The request succeeded and nothing matches | Change the subject, query, or filters |
| `denied` | The grant or the legacy source rule does not allow the read | Request access with `rush memory grant`, or name a source |
| `revoked` | The grant was revoked | Ask the project owner to grant memory access again |
| `expired` | The grant expired | Renew the grant |
| `conflict` | The record changed since you reviewed it | Refresh, review the current version, then apply again |
| `partial` | More results exist, or a size limit stopped the page | Open the next page, or raise the size limit |
| `server_error` | The request failed | Retry the request; if it fails again run `rush doctor` |

The classifier also reports `migration_required`, `corrupt`, `busy`, `restart`, `not_visible`,
`invalid`, and `digest_mismatch`, each with its own action. `digest_mismatch` withholds content
whose bytes do not match the recorded payload hash.

### Memory scope and token counts

There is no claim of isolation against mutually hostile processes running as the same OS user.

Rush counts memory tokens using the request's declared encoding, defaulting to `cl100k_base`. Counts for another host tokenizer are estimates. An admitted delivered frame obeys its UTF-8 `max_bytes`; if that tokenizer consumes at least one byte per token, its token count cannot exceed those delivered bytes. No measured cross-tokenizer margin is claimed.

---

## 6. Tokens

Inside the Tokens section (`m`, or section `5`), `/` opens a filter prompt: type `run:<id>`,
`agent:<id>`, or `session:<id>` (a bare value with no prefix is treated as a run ID), `Enter`
applies it, `Escape` clears every identity filter.

The section always shows:

- an `attribution:` line naming the current run/agent/session filter values (`all` when unset);
- an `interval:` line with the earliest and latest event time in the current selection, or a
  note that no stored event time exists in the selection;
- an `unscoped:` line counting events with no stored run/agent/session identity — labelled
  "excluded from this selection" while a filter is active, or "included in project totals"
  when it isn't.

---

## 7. Git

Inside the Git section (`G`, or section `6`):

| Key | Action |
|---|---|
| `]` | Page to older commits |
| `[` | Page to newer commits |
| `d` | Expand the next dirty file's bounded diff |
| `+` | Expand the selected commit's diff detail |
| `-` | Collapse the diff detail |
| `Enter` | Inspect the selected commit |

Diff detail is bounded. When a diff exceeds the bound, `... more: diff cut at
N lines` appears before its body, so clipping the body does not hide truncation.

---

## 8. Artifacts

Inside the Artifacts section (section `7`):

| Key | Action |
|---|---|
| `↓`/`j`, `↑`/`k` | Move the selection; scroll text while inspecting |
| `/` | Search the captured artifact index |
| `i` | Inspect the selected artifact (press again to see more of it) |
| `e` | Review, then export the selected artifact |
| `Escape` | Close inspection and return to the tables |

The section shows two paginated tables sharing one selection: a **Captured** table (tool
identity, path, type, run/attempt, size) for artifacts a tool captured directly, and an
**Evidence** table (source bucket, identity, type, run, size) for every other shared evidence
item — scan outputs, handoffs, memory records, and any bucket added later. Selection moves
through the Captured rows first, then the Evidence rows. `/` matches path, category, or media
type in Captured rows, and bucket, identity, category, or kind in Evidence rows.
Inspection puts captured content and its byte range in view at compact terminal sizes;
`Escape` restores the full tables at the same selection.

Export opens the same grant-review overlay as scans and checks: nothing is written to disk
until you accept it with `y`.

---

## 9. Setup/Agents

Inside the Setup/Agents section (section `8`):

| Key | Action |
|---|---|
| `t` | Toggle the highlighted stage's grant |
| `p` | Review the toggled grants, then apply setup |
| `x` | Regenerate the review after a failed stage |
| `a` | Cycle the agent target for a handoff |
| `H` | Review and send an agent handoff |

---

## 10. Paste

Bracketed paste is supported: pasted text lands literally in whatever text field is active
(a search box, the Tokens or Artifacts filter, a memory create/edit field, a form field) and is
never replayed as key presses — a paste can never itself trigger a scan, a quit, or navigation.
Outside of a text field, a paste is ignored.

On Windows, a console with VT input enabled sends the same bracketed-paste escape sequences a
POSIX terminal does, handled the same way. On an older console without VT input, a burst of
more than one printable character can't be told apart from a real paste, so it is always
treated as literal paste text rather than replayed as key presses — a pasted "qq" still never
quits.

---

## 11. Environment variables

- `NO_COLOR` — set to any value to disable colored output. This is independent of motion.
- `RUSH_REDUCED_MOTION` — set to any value to render the final state of an animation
  immediately instead of playing it, and to make idle background-load redraws immediate too.

Without `RUSH_REDUCED_MOTION`, the screen refreshes at up to 20Hz while something is active
(a run, a change, or an animation in progress) and at 4Hz while idle, checking for input in
slots of 50ms or less. A newly revealed list reveals one more row every 40ms, capped at 240ms
total. Selection highlight fades in over 120ms, and the detail pane fades in over 180ms.

---

## 12. Terminal size

The interface needs at least **60 columns by 20 rows**. Below that, every section is replaced
with a resize-guidance panel showing the current and required size; all your state is kept
underneath it. Only `q`, `c`, `F2`, and `Escape` still work while it's shown; every other key
waits until the terminal is large enough again.

---

## 13. Project registration state

The Overview section reports the project's registration state and offers a next step:

| State | What you see | What you can do |
|---|---|---|
| No project registered | "No project registered for this folder." | `A` Add this folder, `N` Create a new project, `L` Choose a project later |
| Project root moved | "Project root moved: `<reason>`" | `R` Relink to the new root (reviewed) |
| Registry corrupt or unreadable | "Registry corrupt: `<reason>`" (or "unreadable") | Reported as its own state, distinct from "no project" |
| Registration ambiguous | "Registration ambiguous: `<reason>`" | More than one registered project matches this root; resolve the ambiguity outside the TUI |

---

## Memory claim status

Each row states what the repository holds at the revision shown. `integrated` means the named test drives the route and covers the access forms. The terminal walkthrough on an installed binary is lane `pty-terminal` in `docs/reports/phase-72-memory-acceptance.md#lanes`, and it is open until that lane runs.

| Claim | Status | Revision | Route | Evidence |
|---|---|---|---|---|
| `tui:search` The Memory section searches records by typed text with `/`, or with `Enter` when focus is on search | `integrated` | `392f882` | Memory section, `/` | `tests/test_phase70_tui_usability.py::test_t28d_memory_workflows` |
| `tui:filter` `f` opens the filter form for owner, source, trust, freshness, and archived records | `integrated` | `392f882` | Memory section, `f` | `tests/test_phase72_memory_ui.py::test_t07_route_mode_matrix`; `tests/test_phase72_memory_ui.py::test_t07_shared_user_journey` |
| `tui:subject-cycle` `S` reaches all seven subjects and the list equals the memory tool result for each | `integrated` | `392f882` | Memory section, `S` | `tests/test_phase70_tui_usability.py::test_t28d_memory_workflows`; `tests/test_phase72_memory_ui.py::test_t07_shared_user_journey` |
| `tui:paging` `]` and `[` page the record list by cursor and return to the earlier page | `integrated` | `392f882` | Memory section, `]` and `[` | `tests/test_phase70_tui_usability.py::test_t28d_memory_workflows` |
| `tui:expand-exact-version` `x` shows the exact selected version in bounded pages, and a changed or revoked version cannot be expanded | `integrated` | `392f882` | Memory section, `x` | `tests/test_phase72_memory_ui.py::test_t07_shared_user_journey`; `tests/test_memory_retrieval.py::test_revoked_or_changed_version_cannot_expand` |
| `tui:history` `v` shows every stored version of the selected record | `integrated` | `392f882` | Memory section, `v` | `tests/test_phase70_tui_usability.py::test_t28d_memory_workflows`; `tests/test_phase72_memory_public.py::test_t06_history_and_explain` |
| `tui:explain` `E` shows cited rationale, contrary evidence, what was tried, affected code references, and unknowns, and says unknown where nothing was recorded | `integrated` | `392f882` | Memory section, `E` | `tests/test_phase72_memory_ui.py::test_t07_explain_buckets_cli_and_tui` |
| `tui:correct` `c` previews a correction, rejection, or supersession and applies it as a new version on `y` | `integrated` | `392f882` | Memory section, `c` | `tests/test_phase70_tui_usability.py::test_t28d_memory_workflows` |
| `tui:import-review` `I` shows the same import review state as the command line and applies only after confirmation | `integrated` | `392f882` | Memory section, `I` | `tests/test_phase72_portable_memory_policy.py::test_import_review_cli_tui_same_state` |
| `tui:representation-toggle` `b` switches expanded content between `base64` and `utf8` and fetches the pages again | `integrated` | `392f882` | Memory section, `b` | `tests/test_phase72_memory_ui.py::test_t07_cache_key_request_identity` |
| `tui:denied-state` A read the grant or legacy source rule refuses shows state `denied` with a next action and no row content | `integrated` | `392f882` | Memory section | `tests/test_phase72_memory_ui.py::test_t07_ui_state_classifier` |
| `tui:revoked-state` A revoked grant shows state `revoked` and the next request never serves a cached page | `integrated` | `392f882` | Memory section | `tests/test_phase72_memory_ui.py::test_t07_ui_state_classifier`; `tests/test_phase72_memory_ui.py::test_t07_cache_cleared_on_revoke_expire_switch` |
| `tui:expired-state` An expired grant shows state `expired` and the next request never serves a cached page | `integrated` | `392f882` | Memory section | `tests/test_phase72_memory_ui.py::test_t07_ui_state_classifier`; `tests/test_phase72_memory_ui.py::test_t07_cache_cleared_on_revoke_expire_switch` |
| `tui:conflict-state` A version conflict keeps the text typed in the form and waits for `r` to refresh | `integrated` | `392f882` | Memory section, `r` | `tests/test_phase70_tui_usability.py::test_t28d_memory_workflows`; `tests/test_phase72_memory_ui.py::test_t07_ui_state_classifier` |
| `tui:hostile-text` Hostile HTML and terminal control sequences in record text render as escaped literal text | `integrated` | `392f882` | Memory section | `tests/test_phase72_memory_ui.py::test_t07_tui_hostile_terminal_text` |
| `tui:installed-walkthrough` The keyboard journey above was driven on an installed binary under a terminal and recorded as machine receipts | `proposed` | `392f882` | `rush ui` | — |

## Next steps

- For what each section's findings mean, see [Understanding Rush Results](understanding-results.md).
- For the checks a scan or check run actually executes, see [Checking Your Code](checking-code.md).
