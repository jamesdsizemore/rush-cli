# Distribution

Rush builds a wheel and source distribution with Hatchling through `uv build`. Validate each artifact in an independent clean Python 3.12 environment, including import, version/help, representative JSON command, and MCP startup.

No package registry publication is claimed by this documentation. A local wheel can be installed with `uv tool install /path/to/rush-...whl`. See [CI and packaging](developer/ci-and-packaging.md) and [Release](developer/release-process.md).
