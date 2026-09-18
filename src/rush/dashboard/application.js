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
      state.lastEventSequence = resp.envelope.sequence || after;
      const events = (resp.envelope.data && resp.envelope.data.events) || [];
      if (events.length > 0) {
        await loadMap(projectId, generation, state.mapFilters);
        if (isCurrentGeneration(generation) && events.some((e) => e.status === "terminal")) {
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
export async function dispatchAction(operation, args = {}, grants = {}, expected = {}) {
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
  if (result.status === 409) {
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
    label: "Provision: Plan",
    grants: [],
    fields: [
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
    grants: ["cache_write", "artifact_write"],
    fields: [{ name: "plan_id" }],
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
  {
    section: "scans",
    operation: "handoff_preview",
    label: "Handoff: Preview",
    grants: [],
    fields: [
      { name: "run_id" },
      { name: "agent_id" },
      { name: "finding_ids", csv: true },
      { name: "max_tokens", number: true },
      { name: "max_bytes", number: true },
    ],
  },
  {
    section: "scans",
    operation: "handoff_send",
    label: "Handoff: Send",
    grants: ["cache_write", "artifact_write"],
    fields: [
      { name: "run_id" },
      { name: "agent_id" },
      { name: "finding_ids", csv: true },
      { name: "max_tokens", number: true },
      { name: "max_bytes", number: true },
      { name: "handoff_id" },
    ],
  },
  {
    section: "memory",
    operation: "memory_propose",
    label: "Memory: Write",
    grants: ["cache_write"],
    fields: [
      { name: "subject" },
      { name: "content", multiline: true, json: true },
      { name: "source" },
      { name: "source_kind" },
      { name: "symbol_ref" },
    ],
  },
  {
    section: "memory",
    operation: "memory_promote",
    label: "Memory: Promote",
    grants: ["cache_write"],
    fields: [
      { name: "subject" },
      { name: "content", multiline: true, json: true },
      { name: "source" },
      { name: "source_kind" },
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
    fields: [
      { name: "scope" },
      { name: "id" },
      { name: "expected_version", number: true },
      { name: "content", multiline: true, json: true },
    ],
  },
  {
    section: "memory",
    operation: "memory_archive",
    label: "Memory: Archive",
    applyGated: true,
    grants: ["cache_write"],
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
    fields: [
      { name: "scope" },
      { name: "artifact_ids", csv: true },
      { name: "expected_revisions", multiline: true, json: true },
    ],
  },
  {
    section: "artifacts",
    operation: "artifact_export",
    label: "Export Artifact",
    grants: ["download"],
    fields: [{ name: "artifact_id" }],
  },
];

function labelWrap(text, inputEl) {
  const label = document.createElement("label");
  label.appendChild(document.createTextNode(text + " "));
  label.appendChild(inputEl);
  return label;
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
    const input = document.createElement(field.multiline ? "textarea" : "input");
    if (field.checkbox) {
      input.type = "checkbox";
    } else if (!field.multiline) {
      input.type = "text";
    }
    input.setAttribute("name", field.name);
    input.setAttribute("data-field", field.name);
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

  const result = document.createElement("pre");
  result.setAttribute("data-role", "action-result");

  function collectArgs() {
    const args = {};
    for (const { el, field } of Object.values(fieldEls)) {
      if (field.checkbox) {
        args[field.name] = el.checked;
        continue;
      }
      const raw = el.value;
      if (raw === "") continue;
      if (field.csv) {
        args[field.name] = raw
          .split(",")
          .map((v) => v.trim())
          .filter(Boolean);
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
    return args;
  }

  function collectGrants() {
    const grants = {};
    for (const [name, checkbox] of Object.entries(grantEls)) {
      grants[name] = checkbox.checked;
    }
    return grants;
  }

  async function submit(applyValue) {
    const args = collectArgs();
    if (spec.applyGated) args.apply = applyValue;
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
