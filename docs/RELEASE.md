# Release

Rush release validation and publication are separate decisions. Follow [Release process](developer/release-process.md): update version/docs, run full quality and package gates, install wheel/sdist independently, verify a clean clone and remote CI, then request explicit tag authorization and separate publication authorization.

`rush release` is dry-run only and cannot publish.
