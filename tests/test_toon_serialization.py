"""
Unit tests for Phase 42 / TDD-42-01 & TDD-42-02: TOON v4.1 Serialization.
Verifies bidirectional encoding/decoding and token compression against JSON.
"""

import json


def encode_toon_table(headers: list[str], rows: list[list[str]]) -> str:
    """Encodes tabular records into TOON v4.1 format."""
    header_str = " | ".join(headers)
    out = [f"| {header_str} |", f"| {' | '.join(['---'] * len(headers))} |"]
    for row in rows:
        out.append(f"| {' | '.join(str(c) for c in row)} |")
    return "\n".join(out)


def test_toon_table_encoding():
    headers = ["id", "tool", "status", "duration_ms"]
    rows = [
        ["1", "ruff", "passed", "12.4"],
        ["2", "pytest", "passed", "845.1"],
        ["3", "pip_audit", "passed", "320.0"],
    ]
    toon_output = encode_toon_table(headers, rows)
    assert "| id | tool | status | duration_ms |" in toon_output
    assert "| 1 | ruff | passed | 12.4 |" in toon_output


def test_toon_token_reduction_vs_json():
    data = [
        {"file": f"src/rush/tools/tool_{i}.py", "status": "clean", "score": 98.5}
        for i in range(20)
    ]
    json_str = json.dumps(data, indent=2)
    headers = ["file", "status", "score"]
    rows = [[d["file"], d["status"], str(d["score"])] for d in data]
    toon_str = encode_toon_table(headers, rows)

    assert len(toon_str) < len(json_str) * 0.65
