# Configuration

Rush discovers `rush.toml` by walking from the requested path to the Git root.
All `[tools.<name>]` sections must name an entry in the canonical tool catalog;
an unknown name is rejected to catch typos.

```toml
[review]
max_file_lines = 400
use_graft = false

[tools.typecheck]
engine_args = ["--strict"]
check = true

[tools.coverage]
engine_args = ["--branch"]
```

`engine_args` and `check` are generic tool settings. Tool behavior remains safe
by default: browser/slow/network operations require their own explicit flags.
Rush never installs an engine while reading configuration.
