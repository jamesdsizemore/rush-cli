# Limitations

- Review currently analyzes Python with deterministic heuristics; no real LLM provider call exists.
- Several catalog commands are guarded placeholders or feasibility-gated.
- Generic CLI command generation exposes only path/JSON for most tools, leaving internal permission/message/output options unavailable.
- Parsed configuration fields are not all consumed by every tool.
- External engine availability, version, configuration, and behavior remain environment-dependent.
- Rush is not a sandbox or complete security assessment.
- `skipped` exits 0 and requires JSON policy handling when a check is mandatory.
- Platform CI is Linux-focused; Windows behavior is covered by local tests/guidance rather than a full matrix.
