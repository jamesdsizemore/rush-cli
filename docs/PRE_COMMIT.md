# Pre-commit integration

Rush does not install hooks. Add a repository-owned hook only after choosing fast, deterministic commands such as lint or format check. Avoid test/security/network/browser/slow commands in commit-time hooks.

Example local hook command:

```yaml
- id: rush-lint
  name: rush lint
  entry: rush lint .
  language: system
  pass_filenames: false
```

Pin/install Rush and required engines separately. Review `skipped` policy; system hooks inherit a different `PATH` on some platforms.
