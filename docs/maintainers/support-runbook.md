# Maintainer Support & Issue Triage Runbook

Operational procedures for triaging issues, diagnosing environment discrepancies, and reproducing bug reports.

---

## 1. Issue Triage Workflow

```text
Incoming Issue Report
       │
       ├── Missing Info? -> Request rush --version, OS, command, target structure, JSON result
       │
       ├── Engine Absent? -> Point user to rush capabilities and install hint in EngineSpec
       │
       ├── Windows Path / Venv Issue? -> Guide user to clear VIRTUAL_ENV/PYTHONPATH
       │
       └── Bug / Parser Discrepancy? -> Reproduce with fixture in tests/fixtures/engine_reports/
```

---

## 2. Windows Environment Contamination Checks

When Windows users report strange tool failures or module import errors:
1. Verify whether active virtual environment leaked foreign packages:
   ```powershell
   Remove-Item Env:\VIRTUAL_ENV -ErrorAction SilentlyContinue
   Remove-Item Env:\PYTHONPATH -ErrorAction SilentlyContinue
   ```
2. Verify interpreter path:
   ```powershell
   .venv\Scripts\python.exe -c "import sys; print(sys.executable)"
   ```

---

## 3. Parser Discrepancy Handling

If an upstream engine update causes parsing errors:
1. Request a sanitized sample output from the user.
2. Add the sample as a test fixture under `tests/fixtures/engine_reports/<engine>/new_version.json`.
3. Update parser in `src/rush/engines/<engine>.py`.
4. Ensure parser returns `status: "error"` if output cannot be parsed safely.

See [Support Guidelines](../SUPPORT.md) and [Troubleshooting Guide](../user-guide/troubleshooting.md).
