"""Embedded single-page application HTML/JS/CSS assets."""

from __future__ import annotations

import importlib.resources

from rush.dashboard.theme import MOTION, THEME

DASHBOARD_HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>Rush Quality Dashboard</title>
  <style>
    body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #0f172a; color: #f8fafc; margin: 0; padding: 24px; }
    h1 { font-size: 24px; font-weight: 700; color: #38bdf8; }
    .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 16px; margin-top: 24px; }
    .card { background: #1e293b; border-radius: 8px; padding: 16px; border: 1px solid #334155; }
    .status-pass { color: #4ade80; }
    .status-fail { color: #f87171; }
  </style>
</head>
<body>
  <h1>Rush Quality Dashboard</h1>
  <div id="stats" class="grid"></div>
  <script>
    const token = new URLSearchParams(window.location.search).get('token');
    fetch('/api/snapshot', { headers: { 'Authorization': 'Bearer ' + token } })
      .then(r => r.json())
      .then(data => {
        document.getElementById('stats').innerHTML = `
          <div class="card"><h3>Findings</h3><p>${data.total_findings}</p></div>
          <div class="card"><h3>Tools</h3><p>${data.total_tools}</p></div>
        `;
      });
  </script>
</body>
</html>
"""


# --- Phase 66 P66-01: canonical fragment-to-session bootstrap page -----------
#
# Served by the new canonical server (server.py::create_dashboard_server) at
# "/", with the companion script at "/assets/bootstrap.js". The bootstrap
# secret travels only in the URL fragment (never sent to the server by the
# browser) and is stripped via history.replaceState before any network
# request is issued, so it never persists in browser history, address bar,
# server logs, or a Referer header. Session/CSRF secrets are never logged
# (no console output anywhere in this script).

BOOTSTRAP_HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>Rush Dashboard</title>
  <link rel="stylesheet" href="/assets/dashboard.css">
</head>
<body>
  <div id="rush-status" data-state="connecting">Connecting&hellip;</div>
  <div class="rush-app" id="rush-app" hidden>
    <div class="rush-topbar" data-role="topbar">
      <button type="button" data-role="nav-toggle" aria-label="Toggle navigation" aria-expanded="false">&#9776;</button>
      <select data-role="project-select" aria-label="Select project"></select>
      <button type="button" data-role="project-add">Add existing folder</button>
      <button type="button" data-role="project-create">Create folder</button>
      <button type="button" data-role="project-choose-later">Choose later</button>
      <label class="rush-pref-toggle"><input type="checkbox" data-role="pref-reduced-motion"> Reduce motion</label>
      <label class="rush-pref-toggle"><input type="checkbox" data-role="pref-high-contrast"> High contrast</label>
      <form data-role="project-add-form" hidden>
        <label>Path <input type="text" name="path" required></label>
        <button type="submit">Add</button>
      </form>
      <form data-role="project-create-form" hidden>
        <label>Parent <input type="text" name="parent" required></label>
        <label>Name <input type="text" name="name" required></label>
        <label><input type="checkbox" name="git_init"> git init</label>
        <button type="submit">Create</button>
      </form>
    </div>
    <div class="rush-nav" data-role="nav">
      <button type="button" data-section="map">Map</button>
      <button type="button" data-section="overview">Overview</button>
      <button type="button" data-section="scans">Scans</button>
      <button type="button" data-section="memory">Memory</button>
      <button type="button" data-section="tokens">Tokens</button>
      <button type="button" data-section="git">Git</button>
      <button type="button" data-section="artifacts">Artifacts</button>
      <button type="button" data-section="setup">Setup</button>
    </div>
    <div class="rush-map" data-role="map"></div>
    <div class="rush-inspector" data-role="inspector" hidden></div>
    <div data-role="error-banner" role="alert"></div>
  </div>
  <script src="/assets/bootstrap.js"></script>
</body>
</html>
"""

BOOTSTRAP_JS = """(function () {
  "use strict";
  var statusEl = document.getElementById("rush-status");

  function setState(state, message) {
    statusEl.dataset.state = state;
    statusEl.textContent = message;
  }

  function exchangeBootstrap(token) {
    return fetch("/api/session", {
      method: "POST",
      headers: { "Authorization": "Bearer " + token },
    }).then(function (response) {
      if (!response.ok) {
        setState(response.status === 401 ? "denied" : "retry", "Reauthorization required.");
        throw new Error("bootstrap exchange failed: " + response.status);
      }
      return response.json();
    });
  }

  function restoreSession() {
    return fetch("/api/session", { method: "GET" }).then(function (response) {
      if (!response.ok) {
        setState("denied", "Reauthorization required.");
        throw new Error("no active session");
      }
      return response.json();
    });
  }

  var hash = window.location.hash;
  var token = hash.indexOf("#token=") === 0 ? hash.slice("#token=".length) : null;

  // Row 15: the one localStorage key preferences persist under, read here
  // before application.js boots so reducedMotion/highContrast/the selected
  // project apply from the very first render, not after a flash of
  // defaults -- never a second storage mechanism (application.js writes to
  // this same key on every toggle/selection).
  function loadPrefs() {
    try {
      var raw = window.localStorage.getItem("rush-dashboard-prefs");
      return raw ? JSON.parse(raw) : {};
    } catch (_err) {
      return {};
    }
  }

  function startApp() {
    setState("connected", "Connected.");
    var appEl = document.getElementById("rush-app");
    if (appEl) appEl.hidden = false;
    var prefs = loadPrefs();
    var reducedMotion =
      typeof prefs.reducedMotion === "boolean"
        ? prefs.reducedMotion
        : !!(window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches);
    import("/assets/application.js").then(function (module) {
      module.startApplication(appEl || document.body, {
        reducedMotion: reducedMotion,
        highContrast: !!prefs.highContrast,
        restoreProjectId: prefs.selectedProjectId || null,
      });
    }).catch(function () {});
  }

  if (token) {
    window.history.replaceState(null, "", window.location.pathname + window.location.search);
    exchangeBootstrap(token).then(startApp).catch(function () {});
  } else {
    restoreSession().then(startApp).catch(function () {});
  }
})();
"""


# --- Phase 66 P66-02: theme CSS + owned JS module asset loading -------------
#
# `DASHBOARD_CSS` serializes THEME/MOTION into CSS custom properties, the
# same single source of truth `tui.py` (P66-03) builds Rich styles from.
# `project_map.js` and `application.js` are real, separately-authored ES
# module files (never inlined as Python string constants like the legacy
# bootstrap script above) so they package correctly under
# `importlib.resources.files('rush.dashboard')` -- see pyproject.toml's
# wheel/sdist include list -- and are never read via a checkout-relative
# path.

DASHBOARD_CSS = f""":root {{
  --color-background: {THEME["background"]};
  --color-surface: {THEME["surface"]};
  --color-surface-raised: {THEME["surface_raised"]};
  --color-border: {THEME["border"]};
  --color-text: {THEME["text"]};
  --color-text-muted: {THEME["text_muted"]};
  --color-blue: {THEME["blue"]};
  --color-pink: {THEME["pink"]};
  --color-purple: {THEME["purple"]};
  --color-warning: {THEME["warning"]};
  --color-error: {THEME["error"]};
  --color-focus: {THEME["focus"]};
  --motion-easing: {MOTION["easing"]};
  --motion-easing-exit: {MOTION["easing_exit"]};
}}

* {{ box-sizing: border-box; }}

body {{
  margin: 0;
  background: var(--color-background);
  color: var(--color-text);
  font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
  font-size: 14px;
  line-height: 1.5;
}}

:focus-visible {{
  outline: 2px solid var(--color-focus);
  outline-offset: 3px;
}}

.rush-app {{ display: flex; flex-direction: column; height: 100vh; }}
.rush-topbar {{ height: 56px; background: var(--color-surface); border-bottom: 1px solid var(--color-border); }}
.rush-nav {{ width: 216px; background: var(--color-surface); }}
.rush-inspector {{ width: 360px; background: var(--color-surface-raised); }}
.rush-map {{ flex: 1; background: var(--color-background); }}

.rush-node-file, .rush-node-directory, .rush-node-project {{ stroke: var(--color-blue); }}
.rush-node-finding {{ stroke: var(--color-pink); }}
.rush-node-memory, .rush-node-agent {{ stroke: var(--color-purple); }}

/* Phase 69 P69-05 (row 15/24): visually-hidden utility for the semantic
   relationship list -- an accessible mirror of the SVG graph, never a
   second visible copy of it. */
.rush-sr-only {{
  position: absolute;
  width: 1px;
  height: 1px;
  padding: 0;
  margin: -1px;
  overflow: hidden;
  clip: rect(0, 0, 0, 0);
  white-space: nowrap;
  border: 0;
}}

[data-role="map-tooltip"] {{
  position: absolute;
  pointer-events: none;
  background: var(--color-surface-raised);
  border: 1px solid var(--color-border);
  color: var(--color-text);
  padding: 4px 8px;
  border-radius: 4px;
  font-size: 12px;
  z-index: 10;
}}

.rush-topbar button,
.rush-nav button {{
  transition: background-color {MOTION["hover_focus_ms"]}ms var(--motion-easing),
    color {MOTION["hover_focus_ms"]}ms var(--motion-easing);
}}

.rush-nav {{
  transition: transform {MOTION["menu_ms"]}ms var(--motion-easing), width {MOTION["menu_ms"]}ms var(--motion-easing);
}}

.rush-inspector {{
  transition: opacity {MOTION["exit_ms"]}ms var(--motion-easing-exit),
    transform {MOTION["menu_ms"]}ms var(--motion-easing);
}}

@media (prefers-reduced-motion: reduce) {{
  .rush-topbar button,
  .rush-nav button,
  .rush-nav,
  .rush-inspector {{
    transition-duration: {MOTION["reduced_motion_opacity_ms"]}ms !important;
  }}
}}

/* Row 15/24: below 1024px the nav collapses to an icon rail -- labels
   hidden, `data-section` shown as a compact glyph via ::before.
   ponytail: reuses the existing data-section attribute as the glyph text
   instead of a real icon asset; upgrade to real icons if the plain-text
   rail ever needs to look less placeholder-ish. */
@media (max-width: 1024px) {{
  .rush-nav {{
    width: 64px;
  }}
  .rush-nav[data-role="nav"] button {{
    font-size: 0;
    width: 100%;
    padding: 8px 0;
  }}
  .rush-nav[data-role="nav"] button::before {{
    content: attr(data-section);
    font-size: 10px;
    text-transform: uppercase;
  }}
}}

/* Row 15/24: below 768px the nav and inspector become off-canvas mobile
   drawers; `data-open="true"` (toggled by application.js, which also
   contains keyboard focus inside the open drawer) slides them in. */
@media (max-width: 768px) {{
  .rush-nav {{
    position: fixed;
    top: 56px;
    bottom: 0;
    left: 0;
    width: 216px;
    transform: translateX(-100%);
    z-index: 20;
  }}
  .rush-nav[data-open="true"] {{
    transform: translateX(0);
  }}
  .rush-inspector {{
    position: fixed;
    top: 56px;
    bottom: 0;
    right: 0;
    width: 85vw;
    max-width: 360px;
    overflow-y: auto;
    transform: translateX(100%);
    z-index: 20;
  }}
  .rush-inspector[data-open="true"] {{
    transform: translateX(0);
  }}
}}

/* Row 15: toggled by application.js's `highContrast` preference --
   stronger borders and no muted text color, never touches authorization
   (purely presentational, this packet never edits server.py). */
.rush-high-contrast {{
  --color-border: #FFFFFF;
  --color-text-muted: var(--color-text);
}}
.rush-high-contrast .rush-topbar,
.rush-high-contrast .rush-nav,
.rush-high-contrast .rush-inspector {{
  border-width: 2px;
}}
"""


_ASSET_PACKAGE = "rush.dashboard"
_ALLOWED_ASSET_NAMES = frozenset({"project_map.js", "application.js"})


def load_dashboard_asset(name: str) -> str:
    """Load an owned dashboard JS module's source by allowlisted name via
    `importlib.resources`, never a checkout-relative filesystem read (works
    identically from a source checkout and an installed wheel)."""
    if name not in _ALLOWED_ASSET_NAMES:
        raise ValueError(f"unknown dashboard asset: {name!r}")
    return importlib.resources.files(_ASSET_PACKAGE).joinpath(name).read_text("utf-8")
