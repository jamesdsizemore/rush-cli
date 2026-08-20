# Incident and security handling

Treat credential disclosure, path escape/overwrite, command injection, unauthorized network/browser execution, MCP stdout corruption, secret leakage, and publication/history mutation as security-sensitive.

1. Move sensitive reports to a private channel supported by repository hosting; do not ask for public reproduction data.
2. Acknowledge, preserve evidence, identify affected versions and trust boundary, and assign an owner.
3. Reproduce with synthetic data and disable affected capability if containment is uncertain.
4. Patch with denial/regression tests, redaction review, and sibling adapter audit.
5. Run full package/clean-clone/MCP gates and prepare a clear advisory.
6. Coordinate version/tag/publication only with explicit authorization.
7. Document remediation without exposing exploit secrets.

A leaked real credential is rotated first; deleting it from source alone is insufficient.
