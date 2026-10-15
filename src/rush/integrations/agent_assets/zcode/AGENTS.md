Use Rush's canonical `rush` skill for explicit task bootstrap, scoped memory,
and portable continuation. Discover `rush_memory` before calling it; use the
`bootstrap` operation only when the connected server advertises that schema.
Provide the actual task ID, kind and query. Never infer task intent from a
conversation ID. A package file does not prove the plugin is enabled: enable
Rush in ZCode Settings -> Plugins, then open a new session. Native ZCode
memory and Rush memory remain separate. Project hook settings are ignored;
use the enabled plugin's hooks. Preview MCP configuration changes and retain
other servers in `.zcode/config.json` or `~/.zcode/cli/config.json`.
