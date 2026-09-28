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
| Map | The project's file/module tree, navigable and searchable |
| Scans/Findings | Results from the last check or scan run, one finding per row |
| Memory | Stored memory records: browse, search, create, edit, promote, archive, delete |
| Tokens | Token-usage data for past runs, filterable by run ID |
| Git | Commit history and the current dirty working-tree diff |
| Artifacts | Captured tool artifacts: inspect, search, and export them |
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
| `+` / `-` | In Map: expand / collapse the selected node (same as `→`/`←`) |
| `Enter` | Inspect the selected row, or accept the highlighted choice in an overlay |
| `Escape` | Back / dismiss the current overlay / decline |
| `/` | Filter or search — see below, its effect depends on where you are |
| `?` | Show the current key bindings |
| `q` | Quit |
| `M` | Jump to the Memory section |
| `G` | Jump to the Git section |
| `m` | Jump to the Tokens section |
| `F5` | Refresh the current section |

`/` behaves differently per section: in Map it searches the map's own nodes, in Artifacts it
searches the captured artifact index, in Tokens it opens a run-ID filter, and everywhere else
(Scans/Findings) it filters the visible findings.

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
| `]` / `[` | Page forward / backward through the record list |
| `f` | Open the filter form (`Tab` cycles fields, `Enter` applies, `Escape` cancels) |
| `S` | Cycle the subject filter |
| `/` | Search records by text |
| `Space` | Select/deselect the highlighted record for a bulk action |
| `n` | Create a new memory record (`Tab` cycles fields, `Enter` previews and submits, `Escape` cancels) |
| `x` | Expand the selected record |
| `e` | Edit the selected record |
| `o` | Set the owner scope for the next mutation |
| `a` | Preview archiving the selected record(s) |
| `d` | Preview deleting the selected record(s) |
| `w` | Preview maintenance (cleanup) on the record set |
| `y` | Accept a pending preview (archive, delete, maintenance, or new-record submit) |
| `n` / `Escape` | Cancel a pending preview |
| `r` | If a conflict is shown after an edit, refresh and re-review it |
| `?` | Show current key bindings |
| `q` | Quit |

Every write (create, edit, archive, delete, maintenance) previews first and applies only on
`y`; `n` or `Escape` cancels with nothing written. If another process edited a record between
your edit and its review, the review is flagged as a conflict and `r` re-fetches it before
you retry.

---

## 6. Tokens

Inside the Tokens section (`m`, or section `5`), `/` opens a run-ID filter: type the ID,
`Enter` filters the view to that run, `Escape` clears the filter.

---

## 7. Git

Inside the Git section (`G`, or section `6`):

| Key | Action |
|---|---|
| `]` | Page to older commits |
| `[` | Page to newer commits |
| `d` | Expand the next dirty file's bounded diff |
| `Enter` | Inspect the selected commit |

---

## 8. Artifacts

Inside the Artifacts section (section `7`):

| Key | Action |
|---|---|
| `↓`/`j`, `↑`/`k` | Move the selection |
| `/` | Search the captured artifact index |
| `i` | Inspect the selected artifact (press again to see more of it) |
| `e` | Review, then export the selected artifact |

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
(a search box, the run-ID filter, a memory create/edit field, a form field) and is never
replayed as key presses — a paste can never itself trigger a scan, a quit, or navigation.
Outside of a text field, a paste is ignored.

---

## 11. Environment variables

- `NO_COLOR` — set to any value to disable colored output. This is independent of motion.
- `RUSH_REDUCED_MOTION` — set to any value to render the final state of an animation
  immediately instead of playing it, and to make idle background-load redraws immediate too.

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

## Next steps

- For what each section's findings mean, see [Understanding Rush Results](understanding-results.md).
- For the checks a scan or check run actually executes, see [Checking Your Code](checking-code.md).
