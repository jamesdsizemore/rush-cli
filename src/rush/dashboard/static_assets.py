"""Embedded single-page application HTML/JS/CSS assets."""

from __future__ import annotations

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
