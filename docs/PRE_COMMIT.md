# Pre-commit integration

Rush never installs Git hooks or adds a pre-commit dependency during package
installation. Integration is deliberately opt-in and local to a repository.

## Validate a message

```bash
rush commit-msg . --message "feat: add parser"
```

This command validates only; it never amends commits, rewrites history, or
installs a hook.

## Optional hook setup

If you choose to use `pre-commit`, install and configure it independently in
your repository. Review the hook configuration before installing it. Rush does
not create `.pre-commit-config.yaml` unless you explicitly request that file.

## CI and release safety

- `rush ci` only inspects local workflow configuration by default.
- `rush release` is a dry-run plan by default. It does not create tags,
  GitHub releases, or package uploads.
- Any future publication integration must require explicit publication and
  confirmation flags in an interactive or CI-safe boundary.
