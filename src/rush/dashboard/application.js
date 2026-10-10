/**
 * Phase 66 P66-02: application shell -- navigation, project selection,
 * fetch/error/auth state, section controls (plan sections 3.1-3.2, 3.6).
 * Phase 69 P69-04: real topbar/nav/section wiring -- project selector,
 * Select/Add/Create/Choose-later, Overview/Scans/Memory/Tokens/Git/
 * Artifacts/Setup section renderers, and visible controls for every
 * dispatchAction workflow (configure, provision, scan, handoff, memory,
 * artifact-export) plus agent connection.
 *
 * Exports: startApplication, selectProject, dispatchAction,
 * fetchOperationStatus, restoreSession, connectAgent, getState.
 * No framework, no build step; a plain ES module loaded by the bootstrap
 * page after session exchange. Talks only to this server's own `/api/*`
 * routes (server.py) using the session cookie + CSRF header contract.
 * Never assembles markup by string-interpolating fetched data into an HTML
 * sink (plan Sec security contract) -- every element is built via
 * `document.createElement`/`textContent`/`setAttribute`.
 */

// Row 15: a namespace import (not named bindings) so test harnesses that
// substitute a minimal `project_map.js` stub exporting only the original
// five names (tests/test_dashboard_projects.py's `_PROJECT_MAP_STUB`) keep
// working -- a named `import { setReducedMotion, pulseEvidence }` would
// fail ESM module linking outright against a module that doesn't export
// them, before any code runs. Real usage still gets the real functions;
// the stub simply leaves these two `undefined` and no scenario there
// triggers either (the reduced-motion toggle's change event, or a
// terminal event arriving from event polling).
import * as projectMap from "./project_map.js";
const {
  renderMap,
  fitMap,
  destroyMap,
  showGroupMembers,
  hideGroupMembers,
  setReducedMotion,
  pulseEvidence,
} = projectMap;

let state = {
  csrfToken: null,
  ownerScopeId: null,
  selectedProjectId: null,
  generation: 0,
  theme: null,
  motion: null,
  reducedMotion: false,
  highContrast: false,
  rootEl: null,
  mapContainer: null,
  mapFilters: {},
  sourceIdentity: null,
  activeSection: "map",
  lastEventSequence: 0,
};

/** Row 15: the one localStorage key preferences persist under -- never a
 * second storage mechanism alongside it. */
const PREFS_KEY = "rush-dashboard-prefs";

function loadStoredPrefs() {
  try {
    const raw = window.localStorage.getItem(PREFS_KEY);
    return raw ? JSON.parse(raw) : {};
  } catch (_err) {
    return {};
  }
}

function savePrefs(patch) {
  try {
    const current = loadStoredPrefs();
    window.localStorage.setItem(PREFS_KEY, JSON.stringify({ ...current, ...patch }));
  } catch (_err) {
    // localStorage unavailable (private mode, quota, etc.) -- preferences
    // simply won't persist across reload; never block the app on this.
  }
}

function applyHighContrast(rootEl, enabled) {
  if (rootEl && rootEl.classList) rootEl.classList.toggle("rush-high-contrast", !!enabled);
}

/** True only when a real `document` global exists (some of this module's
 * Node test harnesses run with no DOM/`document` at all) AND it reports the
 * tab as hidden -- never throws in either environment. */
function isDocumentHidden() {
  return typeof document !== "undefined" && !!document.hidden;
}

function isCurrentGeneration(generation) {
  return generation === state.generation;
}

async function fetchJson(path, options = {}) {
  const headers = Object.assign({}, options.headers || {});
  if (options.method && options.method !== "GET" && state.csrfToken) {
    headers["X-Rush-CSRF"] = state.csrfToken;
  }
  if (options.body && !headers["Content-Type"]) {
    headers["Content-Type"] = "application/json";
  }
  const response = await fetch(path, { ...options, headers, credentials: "same-origin" });
  const envelope = await response.json().catch(() => null);
  return { ok: response.ok, status: response.status, envelope };
}

/** GET /api/session -- reload-safe restore (spec 3.2/3.7): retains the
 * active cookie session and CSRF token without ever persisting a Bearer
 * token client-side. */
export async function restoreSession() {
  const { ok, envelope } = await fetchJson("/api/session", { method: "GET" });
  if (ok && envelope) {
    state.csrfToken = envelope.csrf_token;
    // U10: the session's non-secret owner_scope_id, so a `session`-kind
    // memory owner selection never has to ask for a cookie/CSRF secret.
    state.ownerScopeId = envelope.owner_scope_id || null;
  }
  return ok;
}

function renderError(message) {
  if (!state.rootEl) return;
  const banner = state.rootEl.querySelector('[data-role="error-banner"]');
  if (banner) banner.textContent = message;
}

/** Build the `section=map` query string from the active filters (spec 3.5:
 * kind/severity/status multiselect + literal query) -- shared by the map
 * fetch and expand_group so a group's fetched membership is always
 * filter-consistent with the map that showed its `member_count`. */
function buildMapQuery(filters = {}) {
  const params = new URLSearchParams({ section: "map" });
  if (filters.nodeTypes && filters.nodeTypes.length) {
    params.set("node_types", filters.nodeTypes.join(","));
  }
  if (filters.severity && filters.severity.length) {
    params.set("severity", filters.severity.join(","));
  }
  if (filters.status && filters.status.length) {
    params.set("status", filters.status.join(","));
  }
  if (filters.query) {
    params.set("query", filters.query);
  }
  return params;
}

/** Row 15/24: fetch abortion on a newer selection plus the specified
 * 1/2/4/8s retry schedule on failure -- aborts (a newer generation, or an
 * in-flight `AbortController.abort()` from this same helper's next call)
 * stop immediately with no retry; only a real fetch/response failure
 * retries. */
const RETRY_DELAYS_MS = [1000, 2000, 4000, 8000];
let loadMapController = null;

async function fetchJsonWithRetry(path, options, generation) {
  for (let attempt = 0; attempt <= RETRY_DELAYS_MS.length; attempt += 1) {
    if (!isCurrentGeneration(generation)) return { ok: false, status: 0, envelope: null, aborted: true };
    if (loadMapController) loadMapController.abort();
    loadMapController = new AbortController();
    let result;
    try {
      result = await fetchJson(path, { ...options, signal: loadMapController.signal });
    } catch (err) {
      if (err && err.name === "AbortError") {
        return { ok: false, status: 0, envelope: null, aborted: true };
      }
      result = { ok: false, status: 0, envelope: null };
    }
    if (result.ok) return result;
    if (!isCurrentGeneration(generation)) return { ok: false, status: 0, envelope: null, aborted: true };
    if (attempt < RETRY_DELAYS_MS.length) {
      await new Promise((resolve) => setTimeout(resolve, RETRY_DELAYS_MS[attempt]));
    } else {
      return result;
    }
  }
  return { ok: false, status: 0, envelope: null };
}

/** Fetch a project's map section and render it, discarding the response if
 * a newer selection/action has already superseded this generation (spec
 * 3.4: "increment selection generation and ignore responses ... from prior
 * generations"). */
async function loadMap(projectId, generation, filters = {}) {
  state.mapFilters = filters;
  hideGroupMembers();
  const params = buildMapQuery(filters);
  const { ok, status, envelope, aborted } = await fetchJsonWithRetry(
    `/api/projects/${encodeURIComponent(projectId)}/snapshot?${params.toString()}`,
    { method: "GET" },
    generation
  );
  if (aborted || !isCurrentGeneration(generation)) return; // stale -- a newer switch/selection won.
  if (!ok || !envelope || envelope.project_id !== projectId) {
    renderError(status === 401 ? "Reconnect required." : "Failed to load project map.");
    return;
  }
  if (state.mapContainer) {
    renderMap(state.mapContainer, envelope.data, {
      theme: state.theme,
      motion: state.motion,
      reducedMotion: state.reducedMotion,
      onSelect: (nodeId, meta) => {
        if (meta.node && meta.node.kind === "group") {
          expandGroup(projectId, nodeId, generation);
        }
      },
    });
  }
  state.lastEventSequence = envelope.sequence || 0;
}

/** Row 10: durable event-polling over `GET .../events?after=<sequence>`
 * (server.py's P69-03p endpoint) -- 750ms while the tab is visible, 5s
 * while hidden, per Phase 66 §3.6. A terminal transition in the polled
 * batch fires the project root's one-shot evidence pulse (row 15); its
 * node id follows project_map.py's own `f"project:{project_id}"`
 * convention, read directly this session, never invented here. Any new
 * event triggers `loadMap`, which itself renders incrementally (the
 * renderer is reused, not recreated, across poll cycles). */
const POLL_INTERVAL_ACTIVE_MS = 750;
const POLL_INTERVAL_IDLE_MS = 5000;
let pollTimer = null;

function stopEventPolling() {
  if (pollTimer) {
    clearTimeout(pollTimer);
    pollTimer = null;
  }
}

function startEventPolling(projectId, generation, { immediate = false } = {}) {
  stopEventPolling();
  const tick = async () => {
    if (!isCurrentGeneration(generation)) return; // superseded -- stop polling this project.
    const after = state.lastEventSequence || 0;
    const resp = await fetchJson(
      `/api/projects/${encodeURIComponent(projectId)}/events?after=${after}`,
      { method: "GET" }
    );
    if (!isCurrentGeneration(generation)) return;
    if (resp.ok && resp.envelope) {
      const events = (resp.envelope.data && resp.envelope.data.events) || [];
      if (events.length > 0) {
        await loadMap(projectId, generation, state.mapFilters);
        // T036: `loadMap` (above) also writes `state.lastEventSequence`,
        // but from `envelope.sequence` -- the project record's own mutation
        // counter (verified this session -- identical, low, and unchanging
        // across an entire real scan's worth of ticks), never the events
        // log's own per-event `sequence`. Left unfixed there (other callers
        // of `loadMap` rely on that field for their own purposes), so this
        // assignment must run after `loadMap`'s, not before, or `loadMap`
        // silently clobbers it back to the stale watermark every tick --
        // confirmed live: 400+ identical `after=1` requests across one real
        // scan before this fix, and still stuck after only reordering the
        // terminal-status check without this reorder too.
        state.lastEventSequence = events[events.length - 1].sequence || after;
        // T036: a real scan's terminal ledger event is `run_<RunState>`
        // (`project_run.py`'s own `f"run_{run_state}"`, verified this
        // session against a live scan) -- `completed`/`incomplete`/`failed`/
        // `cancelled` are its only terminal states. `"terminal"` alone (the
        // prior check) never matches any event a real server emits; kept
        // alongside the real statuses rather than replaced.
        const isTerminalEvent = (e) =>
          e.status === "terminal" ||
          e.status === "run_completed" ||
          e.status === "run_incomplete" ||
          e.status === "run_failed" ||
          e.status === "run_cancelled";
        if (isCurrentGeneration(generation) && events.some(isTerminalEvent)) {
          pulseEvidence(`project:${projectId}`);
        }
      }
    }
    if (!isCurrentGeneration(generation)) return;
    const interval = isDocumentHidden() ? POLL_INTERVAL_IDLE_MS : POLL_INTERVAL_ACTIVE_MS;
    pollTimer = setTimeout(tick, interval);
  };
  if (immediate) {
    tick();
  } else {
    pollTimer = setTimeout(tick, isDocumentHidden() ? POLL_INTERVAL_IDLE_MS : POLL_INTERVAL_ACTIVE_MS);
  }
}

/** GET .../snapshot?section=map&group=<id> -- expand_group's real browser
 * caller (plan 3.5: "server-paginated members (100 per page)"), the fix for
 * the dead-code finding: clicking a group node pages through its full
 * membership under the SAME active filters used to render the map, so
 * `member_count` never diverges from what is actually fetched here. */
async function expandGroup(projectId, groupId, generation, { append = false, cursor = null } = {}) {
  const params = buildMapQuery(state.mapFilters);
  params.set("group", groupId);
  if (append && cursor) params.set("cursor", cursor);
  const { ok, envelope } = await fetchJson(
    `/api/projects/${encodeURIComponent(projectId)}/snapshot?${params.toString()}`,
    { method: "GET" }
  );
  if (!isCurrentGeneration(generation)) return; // stale -- a newer switch/selection won.
  if (!ok || !envelope) {
    renderError("Failed to load group members.");
    return;
  }
  const { group_id: returnedGroupId, members, next_cursor: nextCursor, total } = envelope.data;
  showGroupMembers(returnedGroupId, members, {
    total,
    hasMore: nextCursor !== null,
    append,
    onLoadMore: () =>
      expandGroup(projectId, returnedGroupId, generation, { append: true, cursor: nextCursor }),
  });
}

/** Select a project: every pending request/animation for a previously
 * selected project is superseded and its late response is dropped, so
 * switching mid-flight never leaves stale data visible (spec 3.2/3.4). */
export function selectProject(projectId, filters = {}) {
  state.generation += 1;
  const generation = state.generation;
  state.selectedProjectId = projectId;
  state.lastEventSequence = 0;
  savePrefs({ selectedProjectId: projectId });
  destroyMap();
  stopEventPolling();
  loadMap(projectId, generation, filters).then(() => {
    if (isCurrentGeneration(generation)) startEventPolling(projectId, generation);
  });
  if (state.rootEl) {
    const select = state.rootEl.querySelector('[data-role="project-select"]');
    if (select) select.value = projectId;
  }
  if (state.activeSection !== "map") switchSection(state.activeSection);
  return generation;
}

/** POST /api/projects/{id}/actions -- allowlisted operation dispatch
 * (spec 3.2/3.6). `grants` mirrors the explicit consent the user reviewed
 * before this call; never invented client-side. `expected` is sourced from
 * the currently displayed record's own identity fields (source_identity,
 * plan_id, config_hash) by the caller -- every mutation call sends it, per
 * P69-02.3.
 *
 * On a 409 (stale `expected`/replayed `request_id` with a different body),
 * per Phase 66 §3.6's reload-offer contract: the client's known state is
 * out of date, so this reloads the current project's own data rather than
 * silently retrying or discarding the conflict.
 *
 * On a 202 (a long action -- `scan_start`/`scan_resume`/`rescan`/
 * `handoff_send`/`provision_apply`), the response carries `operation_id`
 * for polling `GET .../operations/{operation_id}` until it reaches a
 * terminal status; this is surfaced on the returned result as
 * `operationId`. */
export async function dispatchAction(
  operation,
  args = {},
  grants = {},
  expected = {},
  options = {}
) {
  if (!state.selectedProjectId) {
    throw new Error("no project selected");
  }
  const requestId =
    typeof crypto !== "undefined" && crypto.randomUUID
      ? crypto.randomUUID()
      : `${Date.now()}-${Math.random()}`;
  const body = JSON.stringify({
    schema_version: 1,
    operation,
    arguments: args,
    expected,
    grants,
    request_id: requestId,
  });
  const result = await fetchJson(
    `/api/projects/${encodeURIComponent(state.selectedProjectId)}/actions`,
    { method: "POST", body }
  );
  // U06: handoff_send opts out -- the generic reload discards the
  // preserved Preview/Send review state a 409 there is supposed to keep
  // visible (finding's own "bypass generic automatic reload" requirement).
  if (result.status === 409 && options.reloadOn409 !== false) {
    renderError("This changed since you last loaded it. Reloading current data.");
    selectProject(state.selectedProjectId, state.mapFilters);
  }
  if (result.status === 202 && result.envelope) {
    result.operationId = (result.envelope.data || {}).operation_id || null;
  }
  return result;
}

/** GET .../operations/{operation_id} -- poll a long action's (`scan_start`/
 * `scan_resume`/`rescan`/`handoff_send`/`provision_apply`) status through
 * to a terminal outcome, the same polling shape `dispatchAction`'s 202
 * responses all share. */
export async function fetchOperationStatus(operationId) {
  if (!state.selectedProjectId) {
    throw new Error("no project selected");
  }
  return fetchJson(
    `/api/projects/${encodeURIComponent(state.selectedProjectId)}/operations/${encodeURIComponent(operationId)}`,
    { method: "GET" }
  );
}

/** POST /api/projects -- global add/create (spec 3.6), works with an empty
 * registry and never requires a preexisting selected project. */
export async function addOrCreateProject(payload) {
  const requestId =
    typeof crypto !== "undefined" && crypto.randomUUID
      ? crypto.randomUUID()
      : `${Date.now()}-${Math.random()}`;
  return fetchJson("/api/projects", {
    method: "POST",
    body: JSON.stringify({ schema_version: 1, request_id: requestId, ...payload }),
  });
}

/** POST /api/agents/actions -- global (non-project) `rush_agent_connection`
 * list/connect/doctor (plan Sec 3.6/3.1 row 6). Distinct from
 * `dispatchAction`: agents are not scoped to a selected project. */
export async function connectAgent(agentId, options = {}, grants = {}) {
  const requestId =
    typeof crypto !== "undefined" && crypto.randomUUID
      ? crypto.randomUUID()
      : `${Date.now()}-${Math.random()}`;
  return fetchJson("/api/agents/actions", {
    method: "POST",
    body: JSON.stringify({
      action: options.action || "connect",
      agent_id: agentId,
      session_id: options.sessionId || null,
      consent: !!options.consent,
      acknowledge: !!options.acknowledge,
      grants,
      request_id: requestId,
    }),
  });
}

/** P69-04.2: each visible-control operation's own argument fields, mirroring
 * server.py's `_ARGUMENT_ALLOWLIST` -- never invents an argument the server
 * doesn't already accept for that operation. `csv`/`json`/`number`/
 * `checkbox` name how a raw form value is coerced before dispatch. */
const ACTION_FORMS = [
  {
    section: "setup",
    operation: "configure",
    label: "Configure",
    applyGated: true,
    grants: ["cache_write", "artifact_write"],
    fields: [
      { name: "settings", multiline: true, json: true },
      { name: "expected_revision" },
      { name: "plan_id" },
    ],
  },
  {
    section: "setup",
    operation: "provision_plan",
    label: "Provision: Review / Resolve",
    grants: ["network"],
    fields: [
      { name: "resolve", checkbox: true },
      { name: "exclude", csv: true },
      { name: "targets", csv: true },
      { name: "severity", csv: true },
      { name: "concurrency", number: true },
      { name: "timeout_seconds", number: true },
    ],
  },
  {
    section: "setup",
    operation: "provision_apply",
    label: "Provision: Apply",
    grants: ["network", "download", "build", "cache_write", "artifact_write"],
    fields: [{ name: "plan_id" }, { name: "review", multiline: true, jsonObject: true,
      placeholder: "Paste readiness.review from Provision: Review / Resolve" }],
  },
  {
    section: "scans",
    operation: "scan_start",
    label: "Scan: Start",
    grants: ["cache_write", "artifact_write"],
    fields: [{ name: "plan_id" }],
  },
  {
    section: "scans",
    operation: "scan_cancel",
    label: "Scan: Cancel",
    grants: ["cache_write"],
    fields: [{ name: "run_id" }],
  },
  {
    section: "scans",
    operation: "scan_resume",
    label: "Scan: Resume",
    grants: ["cache_write", "artifact_write"],
    fields: [{ name: "run_id" }],
  },
  {
    section: "scans",
    operation: "rescan",
    label: "Rescan",
    grants: ["cache_write", "artifact_write"],
    fields: [{ name: "run_id" }],
  },
  // handoff_preview/handoff_send (U06) and artifact_export (U05) are built
  // by their own dedicated controls below -- not generic `buildActionForm`
  // forms -- since both need a stateful Preview/Send (resp. paged-download)
  // flow a single stateless submit can't express.
  {
    section: "memory",
    operation: "memory_propose",
    label: "Memory: Write",
    grants: ["cache_write"],
    ownerScope: true,
    fields: [
      { name: "subject" },
      { name: "content", multiline: true, jsonObject: true },
      { name: "source" },
      { name: "source_kind", select: ["local_tool", "cross_tool_handoff", "human_derived"] },
      { name: "symbol_ref" },
    ],
  },
  {
    section: "memory",
    operation: "memory_promote",
    label: "Memory: Promote",
    grants: ["cache_write"],
    ownerScope: true,
    fields: [
      { name: "subject" },
      { name: "content", multiline: true, jsonObject: true },
      { name: "source" },
      { name: "source_kind", select: ["local_tool", "cross_tool_handoff", "human_derived"] },
      { name: "symbol_ref" },
      { name: "candidate_sources", csv: true },
    ],
  },
  {
    section: "memory",
    operation: "memory_edit",
    label: "Memory: Edit",
    applyGated: true,
    grants: ["cache_write"],
    ownerScope: true,
    fields: [
      { name: "scope" },
      { name: "id" },
      { name: "expected_version", number: true },
      { name: "content", multiline: true, jsonObject: true },
    ],
  },
  {
    section: "memory",
    operation: "memory_archive",
    label: "Memory: Archive",
    applyGated: true,
    grants: ["cache_write"],
    ownerScope: true,
    fields: [
      { name: "scope" },
      { name: "id" },
      { name: "expected_version", number: true },
      { name: "archived", checkbox: true },
    ],
  },
  {
    section: "memory",
    operation: "memory_delete",
    label: "Memory: Delete",
    applyGated: true,
    grants: ["cache_write"],
    ownerScope: true,
    fields: [
      { name: "scope" },
      { name: "artifact_ids", csv: true },
      { name: "expected_revisions", multiline: true, json: true },
    ],
  },
];

function labelWrap(text, inputEl) {
  const label = document.createElement("label");
  label.appendChild(document.createTextNode(text + " "));
  label.appendChild(inputEl);
  return label;
}

const _OWNER_SCOPE_KINDS = ["project", "user", "agent", "session"];

/** U10: the one owner-kind/id control shared by Write/Promote/Edit/
 * Archive/Delete (`buildActionForm`'s `spec.ownerScope`). `project` and
 * `session` are auto-derived (the selected project's own id, and the
 * session's non-secret `owner_scope_id`) and read-only -- never a
 * free-typed value a caller could get wrong; `user`/`agent` are opaque
 * caller-supplied labels this phase authenticates nothing about, so they
 * stay editable. Exact enforcement (foreign project, wrong session,
 * missing id) remains the server/store's job (M08); this control only
 * improves what a caller can express. */
function buildOwnerScopeControl(form) {
  const kindSelect = document.createElement("select");
  kindSelect.setAttribute("data-role", "owner-kind");
  for (const kind of _OWNER_SCOPE_KINDS) {
    const option = document.createElement("option");
    option.value = kind;
    option.textContent = kind;
    kindSelect.appendChild(option);
  }
  kindSelect.value = _OWNER_SCOPE_KINDS[0];
  const idInput = document.createElement("input");
  idInput.type = "text";
  idInput.setAttribute("data-role", "owner-id");
  idInput.setAttribute("name", "owner_id");

  function applyKind() {
    const kind = kindSelect.value;
    if (kind === "project") {
      idInput.value = state.selectedProjectId || "";
      idInput.readOnly = true;
    } else if (kind === "session") {
      idInput.value = state.ownerScopeId || "";
      idInput.readOnly = true;
    } else {
      idInput.readOnly = false;
    }
  }
  kindSelect.addEventListener("change", applyKind);
  applyKind();

  form.appendChild(labelWrap("owner kind", kindSelect));
  form.appendChild(labelWrap("owner id", idInput));

  return {
    collect() {
      return { kind: kindSelect.value, id: idInput.value };
    },
  };
}

/** Poll a 202 action's `operation_id` to a terminal outcome (`terminal_at`
 * set), rendering each transition's status into `resultEl` -- the same
 * polling contract `fetchOperationStatus` documents. */
async function pollOperation(operationId, resultEl) {
  for (let attempt = 0; attempt < 30; attempt += 1) {
    const status = await fetchOperationStatus(operationId);
    if (!status.ok || !status.envelope) {
      resultEl.textContent = "operation status unavailable";
      return;
    }
    const data = status.envelope.data || {};
    resultEl.textContent = JSON.stringify(data, null, 2);
    if (data.terminal_at) return;
    await new Promise((resolve) => setTimeout(resolve, 500));
  }
}

/** Build one action's visible control: a `<form data-operation>` with an
 * input per argument field, a checkbox per required grant (unchecked by
 * default -- grants are never invented client-side), and either a single
 * submit (plain actions) or Preview/Apply buttons (`applyGated`
 * operations: `configure`/`memory_edit`/`memory_archive`/`memory_delete`,
 * matching `_APPLY_GATED_ACTIONS`). `expected.source_identity` is attached
 * from `state.sourceIdentity` (seeded by the Overview section) when known. */
function buildActionForm(container, spec) {
  const form = document.createElement("form");
  form.setAttribute("data-role", "action-form");
  form.setAttribute("data-operation", spec.operation);

  const heading = document.createElement("h3");
  heading.textContent = spec.label;
  form.appendChild(heading);

  const fieldEls = {};
  for (const field of spec.fields) {
    let input;
    if (field.select) {
      input = document.createElement("select");
      for (const optionValue of field.select) {
        const option = document.createElement("option");
        option.value = optionValue;
        option.textContent = optionValue;
        input.appendChild(option);
      }
      // Explicit, rather than relying on a `<select>`'s own first-option
      // default -- so `source_kind` is always one of these three exact
      // values from the moment the form exists, before any change event.
      input.value = field.select[0];
    } else {
      input = document.createElement(field.multiline ? "textarea" : "input");
      if (field.checkbox) {
        input.type = "checkbox";
      } else if (!field.multiline) {
        input.type = "text";
      }
    }
    input.setAttribute("name", field.name);
    input.setAttribute("data-field", field.name);
    // U11: a visible, illustrative example -- never a universal subject
    // schema -- for the fields that now require a non-array JSON object.
    if (field.jsonObject) input.setAttribute("placeholder", field.placeholder || '{"text":"..."}');
    fieldEls[field.name] = { el: input, field };
    form.appendChild(labelWrap(field.name, input));
  }

  const grantEls = {};
  for (const grant of spec.grants || []) {
    const checkbox = document.createElement("input");
    checkbox.type = "checkbox";
    checkbox.setAttribute("data-grant", grant);
    grantEls[grant] = checkbox;
    form.appendChild(labelWrap("grant: " + grant, checkbox));
  }

  // U10: one shared owner-kind/id control per mutation form, sending
  // `arguments.owner_scope` separately from the subject/version fields
  // above -- never invented by any one operation's own field list.
  const ownerScopeControl = spec.ownerScope ? buildOwnerScopeControl(form) : null;

  const result = document.createElement("pre");
  result.setAttribute("data-role", "action-result");

  /** Returns `{ args, error }` -- `error` set (and `args` null) means a
   * declared-JSON-object field (U11: `content`) failed to parse or parsed
   * to something other than a plain object; the caller must send no
   * request at all rather than fall back to a raw string. */
  function collectArgs() {
    const args = {};
    for (const { el, field } of Object.values(fieldEls)) {
      if (field.checkbox) {
        args[field.name] = el.checked;
        continue;
      }
      const raw = el.value;
      if (field.select) {
        args[field.name] = raw;
        continue;
      }
      if (raw === "") continue;
      if (field.csv) {
        args[field.name] = raw
          .split(",")
          .map((v) => v.trim())
          .filter(Boolean);
      } else if (field.jsonObject) {
        let parsed;
        try {
          parsed = JSON.parse(raw);
        } catch (_err) {
          return { args: null, error: `${field.name} must be valid JSON, e.g. {"text":"..."}` };
        }
        if (typeof parsed !== "object" || parsed === null || Array.isArray(parsed)) {
          return {
            args: null,
            error: `${field.name} must be a JSON object, e.g. {"text":"..."}`,
          };
        }
        args[field.name] = parsed;
      } else if (field.json) {
        try {
          args[field.name] = JSON.parse(raw);
        } catch (_err) {
          args[field.name] = raw;
        }
      } else if (field.number) {
        args[field.name] = Number(raw);
      } else {
        args[field.name] = raw;
      }
    }
    return { args, error: null };
  }

  function collectGrants() {
    const grants = {};
    for (const [name, checkbox] of Object.entries(grantEls)) {
      grants[name] = checkbox.checked;
    }
    return grants;
  }

  async function submit(applyValue) {
    const { args, error } = collectArgs();
    if (error) {
      result.textContent = error;
      return;
    }
    if (spec.applyGated) args.apply = applyValue;
    if (ownerScopeControl) args.owner_scope = ownerScopeControl.collect();
    const expected = state.sourceIdentity
      ? { source_identity: state.sourceIdentity }
      : {};
    const outcome = await dispatchAction(spec.operation, args, collectGrants(), expected);
    if (outcome.status === 202 && outcome.operationId) {
      result.textContent = "pending: " + outcome.operationId;
      await pollOperation(outcome.operationId, result);
    } else {
      result.textContent = JSON.stringify(outcome.envelope, null, 2);
    }
  }

  if (spec.applyGated) {
    const previewBtn = document.createElement("button");
    previewBtn.type = "button";
    previewBtn.setAttribute("data-role", "preview");
    previewBtn.textContent = "Preview";
    previewBtn.addEventListener("click", () => submit(false));
    const applyBtn = document.createElement("button");
    applyBtn.type = "button";
    applyBtn.setAttribute("data-role", "apply");
    applyBtn.textContent = "Apply";
    applyBtn.addEventListener("click", () => submit(true));
    form.appendChild(previewBtn);
    form.appendChild(applyBtn);
  } else {
    const submitBtn = document.createElement("button");
    submitBtn.type = "submit";
    submitBtn.textContent = spec.label;
    form.appendChild(submitBtn);
    form.addEventListener("submit", (event) => {
      event.preventDefault();
      submit();
    });
  }

  form.appendChild(result);
  container.appendChild(form);
}

/** Global (non-project) agent connection control -- `rush_agent_connection`
 * connect, plan Sec 3.6 row 6. Distinct from `ACTION_FORMS`: dispatches via
 * `connectAgent`/`POST /api/agents/actions`, not `dispatchAction`. */
function buildAgentConnectControl(container) {
  const form = document.createElement("form");
  form.setAttribute("data-role", "agent-connect-form");

  const agentIdInput = document.createElement("input");
  agentIdInput.type = "text";
  agentIdInput.setAttribute("name", "agent_id");
  const consentBox = document.createElement("input");
  consentBox.type = "checkbox";
  consentBox.setAttribute("data-role", "agent-connect-consent");
  const ackBox = document.createElement("input");
  ackBox.type = "checkbox";
  ackBox.setAttribute("data-role", "agent-connect-acknowledge");
  const cacheWriteBox = document.createElement("input");
  cacheWriteBox.type = "checkbox";
  cacheWriteBox.setAttribute("data-grant", "cache_write");
  const artifactWriteBox = document.createElement("input");
  artifactWriteBox.type = "checkbox";
  artifactWriteBox.setAttribute("data-grant", "artifact_write");
  const result = document.createElement("pre");
  result.setAttribute("data-role", "agent-connect-result");
  const submitBtn = document.createElement("button");
  submitBtn.type = "submit";
  submitBtn.textContent = "Connect agent";

  form.appendChild(labelWrap("agent_id", agentIdInput));
  form.appendChild(labelWrap("consent", consentBox));
  form.appendChild(labelWrap("acknowledge", ackBox));
  form.appendChild(labelWrap("grant: cache_write", cacheWriteBox));
  form.appendChild(labelWrap("grant: artifact_write", artifactWriteBox));
  form.appendChild(submitBtn);
  form.appendChild(result);

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const outcome = await connectAgent(
      agentIdInput.value,
      { action: "connect", consent: consentBox.checked, acknowledge: ackBox.checked },
      { cache_write: cacheWriteBox.checked, artifact_write: artifactWriteBox.checked }
    );
    result.textContent = JSON.stringify(outcome.envelope, null, 2);
  });

  container.appendChild(form);
}

/** U06: `handoff_preview` + `handoff_send` as one reviewed Preview-then-Send
 * flow, replacing the two independent stateless forms the generic
 * `buildActionForm` builder previously gave them. Send is disabled until a
 * fresh Preview succeeds; it always resubmits exactly the inputs and
 * `handoff_id` that Preview stored -- never the form's current (possibly
 * since-edited) field values and never an arbitrary client-built envelope.
 * A 409 (S06 hash mismatch: source/attempt changed since Preview) marks the
 * stored preview stale, disables Send, but preserves the typed field values
 * so a caller can inspect and deliberately re-Preview -- `dispatchAction`'s
 * generic reload-current-project-on-409 behavior is skipped here
 * (`reloadOn409: false`) since it would discard that preserved state. */
function buildHandoffControl(container) {
  const form = document.createElement("form");
  form.setAttribute("data-role", "action-form");
  form.setAttribute("data-operation", "handoff_preview");

  const heading = document.createElement("h3");
  heading.textContent = "Handoff: Preview & Send";
  form.appendChild(heading);

  const fieldNames = ["run_id", "attempt_id", "agent_id", "finding_ids", "max_tokens", "max_bytes"];
  const fieldEls = {};
  for (const name of fieldNames) {
    const input = document.createElement("input");
    input.type = "text";
    input.setAttribute("name", name);
    input.setAttribute("data-field", name);
    fieldEls[name] = input;
    form.appendChild(labelWrap(name, input));
  }

  const grantEls = {};
  for (const grant of ["cache_write", "artifact_write"]) {
    const checkbox = document.createElement("input");
    checkbox.type = "checkbox";
    checkbox.setAttribute("data-grant", grant);
    grantEls[grant] = checkbox;
    form.appendChild(labelWrap("grant: " + grant, checkbox));
  }

  const previewBtn = document.createElement("button");
  previewBtn.type = "button";
  previewBtn.setAttribute("data-role", "handoff-preview");
  previewBtn.textContent = "Preview";
  const sendBtn = document.createElement("button");
  sendBtn.type = "button";
  sendBtn.setAttribute("data-role", "handoff-send");
  sendBtn.textContent = "Send";
  sendBtn.disabled = true;
  const result = document.createElement("pre");
  result.setAttribute("data-role", "action-result");

  form.appendChild(previewBtn);
  form.appendChild(sendBtn);
  form.appendChild(result);

  let storedPreview = null; // { inputs, handoffId, expected }

  function currentInputs() {
    return {
      run_id: fieldEls.run_id.value,
      attempt_id: fieldEls.attempt_id.value,
      agent_id: fieldEls.agent_id.value,
      finding_ids: fieldEls.finding_ids.value
        ? fieldEls.finding_ids.value.split(",").map((v) => v.trim()).filter(Boolean)
        : [],
      max_tokens: fieldEls.max_tokens.value ? Number(fieldEls.max_tokens.value) : undefined,
      max_bytes: fieldEls.max_bytes.value ? Number(fieldEls.max_bytes.value) : undefined,
    };
  }

  function markStale(message) {
    storedPreview = null;
    sendBtn.disabled = true;
    result.textContent = message;
  }

  previewBtn.addEventListener("click", async () => {
    const inputs = currentInputs();
    if (!inputs.run_id || !inputs.attempt_id) {
      result.textContent = "run_id and attempt_id are required (S06)";
      return;
    }
    const expected = state.sourceIdentity ? { source_identity: state.sourceIdentity } : {};
    const outcome = await dispatchAction("handoff_preview", inputs, {}, expected);
    if (!outcome.ok || !outcome.envelope) {
      markStale(JSON.stringify(outcome.envelope, null, 2));
      return;
    }
    const data = outcome.envelope.data || {};
    storedPreview = { inputs, handoffId: data.handoff_id, expected };
    sendBtn.disabled = false;
    result.textContent = JSON.stringify(data, null, 2);
  });

  sendBtn.addEventListener("click", async () => {
    if (!storedPreview) return;
    const sendArgs = { ...storedPreview.inputs, handoff_id: storedPreview.handoffId };
    const grants = {
      cache_write: grantEls.cache_write.checked,
      artifact_write: grantEls.artifact_write.checked,
    };
    const outcome = await dispatchAction(
      "handoff_send",
      sendArgs,
      grants,
      storedPreview.expected,
      { reloadOn409: false }
    );
    if (outcome.status === 409) {
      markStale("Handoff preview is stale -- Preview again before sending.");
      return;
    }
    if (outcome.status === 202 && outcome.operationId) {
      result.textContent = "pending: " + outcome.operationId;
      await pollOperation(outcome.operationId, result);
    } else {
      result.textContent = JSON.stringify(outcome.envelope, null, 2);
    }
    storedPreview = null;
    sendBtn.disabled = true;
  });

  container.appendChild(form);
}

function base64ToBytes(base64) {
  if (typeof atob === "function") {
    const binary = atob(base64);
    const bytes = new Uint8Array(binary.length);
    for (let i = 0; i < binary.length; i += 1) bytes[i] = binary.charCodeAt(i);
    return bytes;
  }
  return Uint8Array.from(Buffer.from(base64, "base64")); // ponytail: Node-only fallback for this module's non-browser test harnesses.
}

/** U05: follow `GET .../artifacts/{ref}?path=...&offset=...` (M12's
 * byte-page contract) via its own `data.content.next_offset` until null,
 * rejecting any page whose reference/path/offset/size/digest doesn't match
 * what every prior page in this same download already established --
 * never assembling a partial artifact as if it were complete. */
async function downloadArtifactContentPages(projectId, artifactRef, path, { signal, onProgress, expectedSha256 } = {}) {
  let offset = 0;
  let totalSize = null;
  let sha256 = expectedSha256 || null;
  let mediaType = null;
  const chunks = [];
  for (;;) {
    if (signal) signal.throwIfAborted();
    const params = new URLSearchParams({ path, offset: String(offset) });
    // Encode the artifact ID as one path tail; the server decodes it once
    // after route matching. Literal colons remain readable in the URL.
    const encodedArtifactRef = encodeURIComponent(artifactRef).replace(/%3A/g, ":");
    const response = await fetch(
      `/api/projects/${encodeURIComponent(projectId)}/artifacts/${encodedArtifactRef}?${params.toString()}`,
      { method: "GET", credentials: "same-origin", signal }
    );
    const envelope = await response.json().catch(() => null);
    if (!response.ok || !envelope) throw new Error("artifact page fetch failed");
    const data = envelope.data || {};
    if (data.entry && data.entry.artifact_ref && data.entry.artifact_ref !== artifactRef) {
      throw new Error("artifact reference mismatch mid-download");
    }
    const content = data.content;
    if (!content || content.content_base64 == null) {
      throw new Error((content && content.error) || "malformed artifact page");
    }
    if (content.path !== path || content.offset !== offset) {
      throw new Error("truncated or inconsistent artifact page sequence");
    }
    if (totalSize === null) totalSize = content.size;
    else if (content.size !== totalSize) throw new Error("artifact size changed mid-download");
    if (sha256 === null) sha256 = content.sha256;
    else if (content.sha256 !== sha256) throw new Error("artifact digest changed mid-download");
    if (mediaType === null) mediaType = content.media_type;
    const bytes = base64ToBytes(content.content_base64);
    chunks.push(bytes);
    offset += bytes.length;
    if (onProgress) onProgress(offset, totalSize);
    if (!Number.isSafeInteger(totalSize) || totalSize < 0 || offset > totalSize) {
      throw new Error("truncated or inconsistent artifact page sequence");
    }
    if (content.next_offset === null) {
      if (offset !== totalSize) {
        throw new Error("truncated or inconsistent artifact page sequence");
      }
      break;
    }
    if (bytes.length === 0 || content.next_offset !== offset) {
      throw new Error("truncated or inconsistent artifact page sequence");
    }
  }
  const bytes = new Uint8Array(totalSize);
  let position = 0;
  for (const chunk of chunks) {
    bytes.set(chunk, position);
    position += chunk.length;
  }
  const digest = new Uint8Array(await crypto.subtle.digest("SHA-256", bytes));
  if (signal) signal.throwIfAborted();
  const actualSha256 = Array.from(digest, (byte) => byte.toString(16).padStart(2, "0")).join("");
  if (actualSha256 !== sha256) throw new Error("artifact digest mismatch");
  return { chunks, totalSize, sha256, mediaType };
}

/** U05: the visible artifact-download control. `artifact_export`
 * (grant-gated) resolves the caller's chosen reference/path; the actual
 * bytes then come from the paged content GET above, reassembled into a
 * `Blob` and offered as a real download link -- `artifact_export` itself
 * only ever returns metadata (M12). Cancellable via `AbortController`;
 * cancelling or a rejected page never produces a downloaded file. */
function buildArtifactExportControl(container) {
  const form = document.createElement("form");
  form.setAttribute("data-role", "action-form");
  form.setAttribute("data-operation", "artifact_export");

  const heading = document.createElement("h3");
  heading.textContent = "Export Artifact";
  form.appendChild(heading);

  const idInput = document.createElement("input");
  idInput.type = "text";
  idInput.setAttribute("name", "artifact_id");
  idInput.setAttribute("data-field", "artifact_id");
  form.appendChild(labelWrap("artifact_id", idInput));

  const grantBox = document.createElement("input");
  grantBox.type = "checkbox";
  grantBox.setAttribute("data-grant", "download");
  form.appendChild(labelWrap("grant: download", grantBox));

  const submitBtn = document.createElement("button");
  submitBtn.type = "submit";
  submitBtn.textContent = "Export Artifact";
  const cancelBtn = document.createElement("button");
  cancelBtn.type = "button";
  cancelBtn.setAttribute("data-role", "artifact-export-cancel");
  cancelBtn.textContent = "Cancel";
  cancelBtn.hidden = true;
  const result = document.createElement("pre");
  result.setAttribute("data-role", "action-result");

  form.appendChild(submitBtn);
  form.appendChild(cancelBtn);
  form.appendChild(result);

  let activeController = null;

  cancelBtn.addEventListener("click", () => {
    if (activeController) activeController.abort();
  });

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    if (activeController) return;
    const artifactId = idInput.value;
    if (!artifactId) {
      result.textContent = "artifact_id is required";
      return;
    }
    const projectId = state.selectedProjectId;
    const controller = new AbortController();
    activeController = controller;
    cancelBtn.hidden = false;
    result.textContent = "downloading...";
    try {
      const expected = state.sourceIdentity ? { source_identity: state.sourceIdentity } : {};
      const exportOutcome = await dispatchAction(
        "artifact_export",
        { artifact_id: artifactId },
        { download: grantBox.checked },
        expected
      );
      controller.signal.throwIfAborted();
      if (!exportOutcome.ok || !exportOutcome.envelope) {
        result.textContent = JSON.stringify(exportOutcome.envelope, null, 2);
        return;
      }
      const entry = (exportOutcome.envelope.data || {}).entry || {};
      const artifactRef = entry.artifact_ref;
      const paths = entry.paths || [];
      if (!artifactRef || paths.length === 0) {
        result.textContent = "artifact has no downloadable content";
        return;
      }
      const path = paths[0];
      const { chunks, totalSize, mediaType } = await downloadArtifactContentPages(
        projectId,
        artifactRef,
        path,
        {
          signal: controller.signal,
          expectedSha256: entry.sha256,
          onProgress: (received, total) => {
            result.textContent = `downloading ${received}/${total ?? "?"} bytes`;
          },
        }
      );
      const blob = new Blob(chunks, { type: mediaType || "application/octet-stream" });
      const url = URL.createObjectURL(blob);
      const filename = path.split("/").pop() || artifactRef;
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = filename;
      anchor.setAttribute("data-role", "artifact-download-link");
      form.appendChild(anchor);
      anchor.click();
      URL.revokeObjectURL(url);
      result.textContent = `downloaded ${blob.size} of ${totalSize ?? blob.size} bytes`;
    } catch (err) {
      if (err && err.name === "AbortError") {
        result.textContent = "download cancelled";
      } else {
        result.textContent = "download failed: " + (err && err.message ? err.message : String(err));
      }
    } finally {
      activeController = null;
      cancelBtn.hidden = true;
    }
  });

  container.appendChild(form);
}

/** Real content-renderer shared by all seven non-map sections (Overview/
 * Scans/Memory/Tokens/Git/Artifacts/Setup, plan row 4): displays the
 * section's actual fetched data (never a stub), then builds every
 * `ACTION_FORMS` control that belongs to it plus, for Setup, the
 * agent-connect control -- this packet's answer to "render section
 * content does not by itself prove every workflow is reachable". */
function renderSectionWithActions(container, data, sectionName) {
  const summary = document.createElement("pre");
  summary.setAttribute("data-role", "section-summary");
  summary.textContent = JSON.stringify(data, null, 2);
  container.appendChild(summary);
  for (const spec of ACTION_FORMS) {
    if (spec.section === sectionName) buildActionForm(container, spec);
  }
  if (sectionName === "setup") buildAgentConnectControl(container);
}

function renderOverviewSection(container, data) {
  renderSectionWithActions(container, data, "overview");
}
function renderScansSection(container, data) {
  renderSectionWithActions(container, data, "scans");
  buildHandoffControl(container);
}
function renderMemorySection(container, data) {
  renderSectionWithActions(container, data, "memory");
}
function renderTokensSection(container, data) {
  renderSectionWithActions(container, data, "tokens");
}
function renderGitSection(container, data) {
  renderSectionWithActions(container, data, "git");
}
function renderArtifactsSection(container, data) {
  renderSectionWithActions(container, data, "artifacts");
  buildArtifactExportControl(container);
}
function renderSetupSection(container, data) {
  renderSectionWithActions(container, data, "setup");
}

const SECTION_RENDERERS = {
  overview: renderOverviewSection,
  scans: renderScansSection,
  memory: renderMemorySection,
  tokens: renderTokensSection,
  git: renderGitSection,
  artifacts: renderArtifactsSection,
  setup: renderSetupSection,
};

const MOBILE_MEDIA_QUERY = "(max-width: 768px)";

function isMobileViewport() {
  return (
    typeof window !== "undefined" &&
    typeof window.matchMedia === "function" &&
    window.matchMedia(MOBILE_MEDIA_QUERY).matches
  );
}

/** Row 15: real keyboard focus containment for a mobile off-canvas drawer
 * (`.rush-nav`/`.rush-inspector` below 768px, static_assets.py's CSS) --
 * Tab/Shift+Tab cycles within the drawer, Escape closes it and returns
 * focus to whatever opened it. Shared by both drawers, never a second
 * mechanism per drawer. */
function trapFocus(drawerEl, event) {
  const focusable = drawerEl.querySelectorAll(
    'a[href], button:not([disabled]), input:not([disabled]), textarea:not([disabled]), select:not([disabled]), [tabindex]:not([tabindex="-1"])'
  );
  if (focusable.length === 0) return;
  const first = focusable[0];
  const last = focusable[focusable.length - 1];
  if (event.shiftKey && document.activeElement === first) {
    event.preventDefault();
    last.focus();
  } else if (!event.shiftKey && document.activeElement === last) {
    event.preventDefault();
    first.focus();
  }
}

function openMobileDrawer(drawerEl, toggleBtn) {
  drawerEl.setAttribute("data-open", "true");
  if (toggleBtn) toggleBtn.setAttribute("aria-expanded", "true");
  const onKeydown = (event) => {
    if (event.key === "Escape") {
      closeMobileDrawer(drawerEl, toggleBtn);
      if (toggleBtn) toggleBtn.focus();
      return;
    }
    if (event.key === "Tab") trapFocus(drawerEl, event);
  };
  drawerEl.addEventListener("keydown", onKeydown);
  drawerEl._rushCloseHandler = onKeydown;
  const firstFocusable = drawerEl.querySelector(
    'a[href], button:not([disabled]), input:not([disabled]), [tabindex]:not([tabindex="-1"])'
  );
  if (firstFocusable) firstFocusable.focus();
}

function closeMobileDrawer(drawerEl, toggleBtn) {
  drawerEl.setAttribute("data-open", "false");
  if (toggleBtn) toggleBtn.setAttribute("aria-expanded", "false");
  if (drawerEl._rushCloseHandler) {
    drawerEl.removeEventListener("keydown", drawerEl._rushCloseHandler);
    drawerEl._rushCloseHandler = null;
  }
}

function wireMobileDrawers() {
  if (!state.rootEl) return;
  const nav = state.rootEl.querySelector('[data-role="nav"]');
  const navToggle = state.rootEl.querySelector('[data-role="nav-toggle"]');
  if (navToggle && nav) {
    navToggle.addEventListener("click", () => {
      const isOpen = nav.getAttribute("data-open") === "true";
      if (isOpen) closeMobileDrawer(nav, navToggle);
      else openMobileDrawer(nav, navToggle);
    });
  }
}

/** Nav destination switch (plan row 4: "Map" precedes Overview/Scans/
 * Memory/Tokens/Git/Artifacts/Setup, spec 3.1). `map` stays the existing
 * `[data-role="map"]` renderer; every other section renders into the
 * shell's own `[data-role="inspector"]` container. Reuses the map's
 * selection-generation guard so a project switch mid-fetch discards a
 * stale section response the same way `loadMap` already does. Below
 * 768px, the inspector opens/closes as the same focus-contained mobile
 * drawer `wireMobileDrawers` builds for nav. */
async function switchSection(name) {
  state.activeSection = name;
  if (!state.rootEl) return;
  const inspector = state.rootEl.querySelector('[data-role="inspector"]');
  if (!inspector) return;
  if (name === "map") {
    inspector.hidden = true;
    inspector.textContent = "";
    if (isMobileViewport()) closeMobileDrawer(inspector, null);
    return;
  }
  inspector.hidden = false;
  inspector.textContent = "";
  if (isMobileViewport()) openMobileDrawer(inspector, null);
  const renderer = SECTION_RENDERERS[name];
  if (!renderer || !state.selectedProjectId) return;
  const thisGeneration = state.generation;
  const resp = await fetchJson(
    `/api/projects/${encodeURIComponent(state.selectedProjectId)}/snapshot?section=${encodeURIComponent(name)}`,
    { method: "GET" }
  );
  if (!isCurrentGeneration(thisGeneration) || state.activeSection !== name) return;
  if (!resp.ok || !resp.envelope) {
    renderError("Failed to load " + name + " section.");
    return;
  }
  if (name === "overview") state.sourceIdentity = resp.envelope.data.source_identity;
  renderer(inspector, resp.envelope.data);
}

/** Wire the static nav buttons (`static_assets.py`'s `data-section`
 * elements) to `switchSection` -- markup is server-rendered, this only
 * attaches behavior. */
function wireNav() {
  if (!state.rootEl) return;
  const nav = state.rootEl.querySelector('[data-role="nav"]');
  if (!nav) return;
  const buttons = nav.querySelectorAll("[data-section]");
  for (const button of buttons) {
    button.addEventListener("click", () => switchSection(button.getAttribute("data-section")));
  }
}

/** GET /api/projects -- (re)populate the topbar's project `<select>` and
 * return the fetched items list (shared by `startApplication`'s
 * `restoreProjectId` resolution). */
async function refreshProjectSelect() {
  const resp = await fetchJson("/api/projects", { method: "GET" });
  const items = resp.ok && resp.envelope ? resp.envelope.data.items : [];
  if (state.rootEl) {
    const select = state.rootEl.querySelector('[data-role="project-select"]');
    if (select) {
      select.textContent = "";
      const placeholder = document.createElement("option");
      placeholder.value = "";
      placeholder.textContent = "Choose a project...";
      select.appendChild(placeholder);
      for (const item of items) {
        const option = document.createElement("option");
        option.value = item.project_id;
        option.textContent = item.root || item.project_id;
        select.appendChild(option);
      }
      if (state.selectedProjectId) select.value = state.selectedProjectId;
    }
  }
  return items;
}

/** Wire the static topbar controls (`static_assets.py`'s `project-select`/
 * `project-add`/`project-create`/`project-choose-later` elements and their
 * companion add/create forms) -- Select/Add/Create/Choose-later, all
 * reachable from the shell (plan row 4). */
function wireTopbar() {
  if (!state.rootEl) return;
  const topbar = state.rootEl.querySelector('[data-role="topbar"]');
  if (!topbar) return;

  const select = topbar.querySelector('[data-role="project-select"]');
  if (select) {
    select.addEventListener("change", () => {
      if (select.value) selectProject(select.value);
    });
  }

  const addForm = topbar.querySelector('[data-role="project-add-form"]');
  const addBtn = topbar.querySelector('[data-role="project-add"]');
  if (addBtn && addForm) {
    addBtn.addEventListener("click", () => {
      addForm.hidden = !addForm.hidden;
    });
    addForm.addEventListener("submit", async (event) => {
      event.preventDefault();
      const path = addForm.querySelector('[name="path"]').value;
      const outcome = await addOrCreateProject({
        operation: "add",
        path,
        grants: { cache_write: true, artifact_write: true },
      });
      if (outcome.ok) {
        addForm.hidden = true;
        await refreshProjectSelect();
        selectProject(outcome.envelope.data.project_id);
      } else {
        renderError(
          (outcome.envelope && outcome.envelope.error && outcome.envelope.error.message) ||
            "Failed to add project."
        );
      }
    });
  }

  const createForm = topbar.querySelector('[data-role="project-create-form"]');
  const createBtn = topbar.querySelector('[data-role="project-create"]');
  if (createBtn && createForm) {
    createBtn.addEventListener("click", () => {
      createForm.hidden = !createForm.hidden;
    });
    createForm.addEventListener("submit", async (event) => {
      event.preventDefault();
      const parent = createForm.querySelector('[name="parent"]').value;
      const name = createForm.querySelector('[name="name"]').value;
      const gitInit = createForm.querySelector('[name="git_init"]').checked;
      const outcome = await addOrCreateProject({
        operation: "create",
        parent,
        name,
        git_init: gitInit,
        grants: { cache_write: true, artifact_write: true },
      });
      if (outcome.ok) {
        createForm.hidden = true;
        await refreshProjectSelect();
        selectProject(outcome.envelope.data.project_id);
      } else {
        renderError(
          (outcome.envelope && outcome.envelope.error && outcome.envelope.error.message) ||
            "Failed to create project."
        );
      }
    });
  }

  const chooseLaterBtn = topbar.querySelector('[data-role="project-choose-later"]');
  if (chooseLaterBtn) {
    chooseLaterBtn.addEventListener("click", () => {
      if (addForm) addForm.hidden = true;
      if (createForm) createForm.hidden = true;
    });
  }

  const reducedMotionToggle = topbar.querySelector('[data-role="pref-reduced-motion"]');
  if (reducedMotionToggle) {
    reducedMotionToggle.checked = state.reducedMotion;
    reducedMotionToggle.addEventListener("change", () => {
      state.reducedMotion = reducedMotionToggle.checked;
      setReducedMotion(state.reducedMotion);
      savePrefs({ reducedMotion: state.reducedMotion });
    });
  }

  const highContrastToggle = topbar.querySelector('[data-role="pref-high-contrast"]');
  if (highContrastToggle) {
    highContrastToggle.checked = state.highContrast;
    highContrastToggle.addEventListener("change", () => {
      state.highContrast = highContrastToggle.checked;
      applyHighContrast(state.rootEl, state.highContrast);
      savePrefs({ highContrast: state.highContrast });
    });
  }
}

/** Boot the whole shell: wire the static topbar/nav controls, restore
 * session, load theme, list registered projects, and either select the
 * previously-active project (reload restore) or show the empty-registry
 * global chooser. */
export async function startApplication(rootEl, options = {}) {
  state = {
    csrfToken: null,
    ownerScopeId: null,
    selectedProjectId: null,
    generation: 0,
    theme: null,
    motion: null,
    reducedMotion: !!options.reducedMotion,
    highContrast: !!options.highContrast,
    rootEl,
    mapContainer: options.mapContainer || rootEl.querySelector('[data-role="map"]'),
    mapFilters: {},
    sourceIdentity: null,
    activeSection: "map",
    lastEventSequence: 0,
  };
  applyHighContrast(rootEl, state.highContrast);

  wireTopbar();
  wireNav();
  wireMobileDrawers();

  // Row 10: a background tab switching back to visible triggers an
  // immediate refresh instead of waiting for the next idle (5s) poll. Some
  // of this module's Node test harnesses run with no `document` global at
  // all, so this wiring is skipped entirely there, never a crash.
  if (typeof document !== "undefined" && typeof document.addEventListener === "function") {
    document.addEventListener("visibilitychange", () => {
      if (!isDocumentHidden() && state.selectedProjectId) {
        startEventPolling(state.selectedProjectId, state.generation, { immediate: true });
      }
    });
  }

  const restored = await restoreSession();
  if (!restored) {
    renderError("Reconnect required.");
    return state;
  }

  const themeResp = await fetchJson("/api/theme", { method: "GET" });
  if (themeResp.ok && themeResp.envelope) {
    state.theme = themeResp.envelope.data.theme;
    state.motion = themeResp.envelope.data.motion;
  }

  const items = await refreshProjectSelect();

  // P69-04.2: `restoreProjectId` resolves via a direct per-project existence
  // check, never single-page `items` membership -- a valid id for a project
  // beyond the registry's first page (50/page, server.py's default limit)
  // must still resolve. When it was supplied and does NOT resolve (unknown/
  // invalid id, or absent entirely with an empty registry), the lone-project
  // auto-select branch below never fires for it -- an explicitly-supplied,
  // not-found `restoreProjectId` always falls back to the chooser, never
  // auto-selects a different, unrelated project.
  const restoredProjectId = options.restoreProjectId || null;
  if (restoredProjectId) {
    const existsResp = await fetchJson(
      `/api/projects/${encodeURIComponent(restoredProjectId)}/snapshot`,
      { method: "GET" }
    );
    if (existsResp.ok) {
      selectProject(restoredProjectId);
    }
  } else if (items.length === 1) {
    selectProject(items[0].project_id);
  }
  // Zero or multiple projects with no prior selection (or an unresolved
  // restoreProjectId): leave the global chooser (select / add existing
  // folder / create folder / choose later) visible -- never auto-pick
  // among multiple registered projects.

  return state;
}

export function getState() {
  return state;
}
