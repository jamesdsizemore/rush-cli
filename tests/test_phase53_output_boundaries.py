"""Contract tests for Phase 53: Subprocess and Public Output Boundaries (P53.2.1)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from rush.cache import ResultCache
from rush.html_export import export_to_html
from rush.sarif import export_to_sarif
from rush.score.consensus import ConsensusFinding
from rush.score.sarif_export import SarifExporter
from rush.tools import common
from rush.tools.base import ToolResult


def test_subprocess_sanitizes_before_truncation(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Verify that subprocess output sanitization runs strictly before truncation."""
    fresh_secret = "sk-ant-api03-abcdef123456789012345678"
    # Create output where padding + secret would be sliced if truncation ran before sanitization
    padding = "A" * 50
    raw_output = padding + fresh_secret + " " + ("B" * 200)

    monkeypatch.setattr(common, "MAX_SUBPROCESS_OUTPUT_CHARS", 80)

    bounded = common._bounded_redacted_output(raw_output)
    assert "[TRUNCATED]" in bounded
    assert fresh_secret not in bounded
    assert "[REDACTED_ANTHROPIC_KEY]" in bounded


def test_cli_mcp_html_sarif_cache_outputs_remove_fresh_sentinel(tmp_path: Path) -> None:
    """Verify that public serializers (SARIF, HTML, Consensus SARIF, Cache) sanitize secret sentinels."""
    fresh_anthropic = "sk-ant-api03-abcdef123456789012345678"
    fresh_bearer = "Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.abcdef1234567890"

    finding = {
        "path": "src/app.py",
        "line": 42,
        "rule": "security/secret",
        "severity": "error",
        "message": f"Leaked token {fresh_anthropic}",
        "fix": f"auth = '{fresh_bearer}'",
        "raw": {"secret_token": fresh_anthropic},
    }

    result: ToolResult = {
        "tool": "security",
        "engine": "trufflehog",
        "engine_version": "3.0.0",
        "status": "fail",
        "duration_ms": 100,
        "summary": f"Found key {fresh_anthropic}",
        "findings": [finding],
        "raw": {"secret_key": fresh_anthropic},
    }

    # 1. SARIF Export boundary
    sarif_doc = export_to_sarif(result)
    sarif_str = json.dumps(sarif_doc)
    assert fresh_anthropic not in sarif_str
    assert fresh_bearer not in sarif_str

    # 2. HTML Export boundary
    html_doc = export_to_html(result)
    assert fresh_anthropic not in html_doc
    assert fresh_bearer not in html_doc

    # 3. Consensus SARIF Export boundary
    consensus_finding = ConsensusFinding(
        file_path="config.py",
        line_number=10,
        rule_id="SEC001",
        severity="HIGH",
        description=f"Secret found in config: {fresh_anthropic}",
        agreeing_models=["gpt-4", "claude-3"],
        confidence=0.95,
    )
    consensus_sarif = SarifExporter.export_sarif([consensus_finding])
    assert fresh_anthropic not in consensus_sarif

    # 4. ResultCache boundary (set and get)
    cache_db = tmp_path / "cache.db"
    cache = ResultCache(db_path=cache_db)
    test_file = tmp_path / "test.py"
    test_file.write_text("print('test')", encoding="utf-8")

    cache.set("cache_key_123", result, test_file)

    # Inspect raw SQLite database content: must not contain fresh secrets
    with cache._get_connection() as conn:
        row = conn.execute(
            "SELECT result_json FROM cache_entries WHERE key = ?", ("cache_key_123",)
        ).fetchone()
        assert row is not None
        assert fresh_anthropic not in row["result_json"]
        assert fresh_bearer not in row["result_json"]

    # Retrieve from cache: must be clean
    retrieved = cache.get("cache_key_123", test_file)
    assert retrieved is not None
    assert fresh_anthropic not in json.dumps(retrieved)
    assert fresh_bearer not in json.dumps(retrieved)
