/**
 * Phase 66 P66-02: application shell -- navigation, project selection,
 * fetch/error/auth state, section controls (plan sections 3.1-3.2, 3.6).
 *
 * Exports: startApplication, selectProject, dispatchAction, restoreSession.
 * No framework, no build step; a plain ES module loaded by the bootstrap
 * page after session exchange. Talks only to this server's own `/api/*`
 * routes (server.py) using the session cookie + CSRF header contract.
 */

import {
  renderMap,
  fitMap,
  destroyMap,
  showGroupMembers,
  hideGroupMembers,
} from "./project_map.js";

let state = {
  csrfToken: null,
  selectedProjectId: null,
  generation: 0,
  theme: null,
  motion: null,
  reducedMotion: false,
  rootEl: null,
  mapContainer: null,
  mapFilters: {},
};

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

/** Fetch a project's map section and render it, discarding the response if
 * a newer selection/action has already superseded this generation (spec
 * 3.4: "increment selection generation and ignore responses ... from prior
 * generations"). */
async function loadMap(projectId, generation, filters = {}) {
  state.mapFilters = filters;
  hideGroupMembers();
  const params = buildMapQuery(filters);
  const { ok, status, envelope } = await fetchJson(
    `/api/projects/${encodeURIComponent(projectId)}/snapshot?${params.toString()}`,
    { method: "GET" }
  );
  if (!isCurrentGeneration(generation)) return; // stale -- a newer switch/selection won.
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
  destroyMap();
  loadMap(projectId, generation, filters);
  return generation;
}

/** POST /api/projects/{id}/actions -- allowlisted operation dispatch
 * (spec 3.2/3.6). `grants` mirrors the explicit consent the user reviewed
 * before this call; never invented client-side. */
export async function dispatchAction(operation, args = {}, grants = {}) {
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
    grants,
    request_id: requestId,
  });
  return fetchJson(
    `/api/projects/${encodeURIComponent(state.selectedProjectId)}/actions`,
    { method: "POST", body }
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

/** Boot the whole shell: restore session, load theme, list registered
 * projects, and either select the previously-active project (reload
 * restore) or show the empty-registry global chooser. */
export async function startApplication(rootEl, options = {}) {
  state = {
    csrfToken: null,
    selectedProjectId: null,
    generation: 0,
    theme: null,
    motion: null,
    reducedMotion: !!options.reducedMotion,
    rootEl,
    mapContainer: options.mapContainer || rootEl.querySelector('[data-role="map"]'),
    mapFilters: {},
  };

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

  const projectsResp = await fetchJson("/api/projects", { method: "GET" });
  const items =
    projectsResp.ok && projectsResp.envelope ? projectsResp.envelope.data.items : [];

  const restoredProjectId = options.restoreProjectId || null;
  if (restoredProjectId && items.some((p) => p.project_id === restoredProjectId)) {
    selectProject(restoredProjectId);
  } else if (items.length === 1) {
    selectProject(items[0].project_id);
  }
  // Zero or multiple projects with no prior selection: leave the global
  // chooser (select / add existing folder / create folder / choose later)
  // visible -- never auto-pick among multiple registered projects.

  return state;
}

export function getState() {
  return state;
}
