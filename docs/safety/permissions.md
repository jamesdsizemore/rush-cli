# Permissions

Rush distinguishes ordinary local inspection from work that can be expensive, mutating, browser-driven, or networked.

| Boundary | Intended explicit value | Default |
|---|---|---|
| browser execution | `allow_browser` | skip/refuse |
| long-running work | `allow_slow` | skip/refuse |
| network/load target | `allow_network` | skip/refuse |
| fuzz execution | `allow_fuzz` | skip/refuse |
| snapshot/visual baseline change | `accept` | do not change |
| release publication | `publish` + `confirm` | dry-run/no publication |
| SBOM overwrite/outside path | safe output + `overwrite` | refuse overwrite/outside target |

Current reality: the generic CLI exposes only `PATH` and `--json` for most catalog commands, so it does **not** expose the advanced consent options above. That is a deliberate reason those capabilities remain skipped or incomplete—not an invitation to guess flags. MCP exposes only parameters present in each callable's generated schema.

Consent should be specific to one invocation and target. Never encode blanket browser/network/publication permission in an assistant prompt or shared config.
