# Maintainer Playbook & Operational Governance

This playbook outlines mandatory policies, release gates, security incident protocols, and scanner promotion standards for maintainers of the Rush CLI repository.

---

## 1. Engine Promotion & Maturity Governance

Before promoting any new engine adapter or updating its maturity:
1. **Deterministic Parser Fixture**: Create clean, finding, and malformed sample reports in `tests/fixtures/engine_reports/<engine>/`.
2. **Reference Test Suite**: Add `tests/test_<engine>_reference.py` with mock subprocess isolation.
3. **Register in Truth Audit**: Add to `PARSER_FIXTURE_SUITES` in `src/rush/catalog.py` and verify with `tests/test_phase01_truth_audit.py`.
4. **Universal Documentation Update**: Update all 13 required doc files as defined in the [Master Build Plan](developer/master-innovation-remediation-build-plan.md).
5. **Phase Ledger**: Record execution details, commit IDs, and error recovery in `.hermes/implementation/phase-XX-ledger.md`.

---

## 2. Quality & Verification Gates

Maintainers must ensure all automated gates pass before cutting a release:

```bash
# 1. Clear foreign virtualenv contamination
unset VIRTUAL_ENV PYTHONPATH

# 2. Run entire test suite (100% pass rate required)
.venv/Scripts/python.exe -m pytest tests/ -q

# 3. Verify documentation parity & internal links
.venv/Scripts/python.exe scripts/sync_docs.py --check

# 4. Enforce strict linting and formatting
.venv/Scripts/ruff.exe check src tests scripts
.venv/Scripts/ruff.exe format --check src tests scripts

# 5. Verify Graft code graph
graft --dir .hermes/graft check .
```

---

## 3. Incident and Security Response

Follow [Incident and Security Runbook](maintainers/incident-and-security.md) for triaging reported vulnerabilities. Never publish unredacted secret values or live exploit payloads.

---

## 4. Related Maintainer Documents

- [Scanner Governance Policy](maintainers/scanner-governance.md)
- [Support Runbook](maintainers/support-runbook.md)
- [Versioning & Compatibility Policy](maintainers/versioning-and-compatibility.md)
- [Documentation Style Guide](maintainers/documentation-style-guide.md)
- [Release Process Guide](developer/release-process.md)
