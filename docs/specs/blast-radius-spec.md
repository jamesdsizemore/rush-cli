# Specification: Transitive Blast Radius Analyzer

## 1. Overview
The `BlastRadiusAnalyzer` (`src/rush/tools/blast_radius.py`) statically inspects Abstract Syntax Tree import graphs across the repository to determine the full downstream blast radius, affected API routes, and recommended test suites when modifying files.

## 2. API & Data Model
```python
report = analyzer.analyze(changed_files=[Path("src/auth.py")], max_depth=5)
# Returns: BlastRadiusReport(target_files, max_depth, affected_files, affected_routes, recommended_tests, risk_score)
```
