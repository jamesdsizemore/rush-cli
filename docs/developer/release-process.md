# Release process

1. Confirm requested scope and authorization. Validation does not authorize tag or publication.
2. Update version, changelog, compatibility/migration notes, and lockfile as required.
3. Run full local quality, dependency audit, docs-link, whitespace, graph, and package gates.
4. Install wheel and sdist independently; test import, `rush --help`, representative CLI JSON, and MCP stdio startup.
5. Validate from a clean clone and require remote CI green for the exact candidate.
6. Review staged diff and release artifacts/checksums.
7. Create a tag only after explicit authorization.
8. Publish only after separate explicit authorization and verify the remote artifact.

The `rush release` command is a dry-run local artifact inventory. It does not publish and must not be represented as a release automation system.
