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
    <div class="rush-topbar" data-role="topbar"></div>
    <div class="rush-nav" data-role="nav"></div>
    <div class="rush-map" data-role="map"></div>
    <div class="rush-inspector" data-role="inspector"></div>
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

  function startApp() {
    setState("connected", "Connected.");
    var appEl = document.getElementById("rush-app");
    if (appEl) appEl.hidden = false;
    import("/assets/application.js").then(function (module) {
      module.startApplication(appEl || document.body, {});
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
