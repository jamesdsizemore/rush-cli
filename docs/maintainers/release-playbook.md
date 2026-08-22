# Maintainers/Release Playbook

## Pre-Release Gate Verification (Phases 41–43)
Before publishing a release:
```bash
rush ship clean
rush ship env
rush ship docs
rush ship migration
rush ship semver
rush ship pack
rush ship gate
```
