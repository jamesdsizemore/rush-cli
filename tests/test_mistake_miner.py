"""
Unit tests for Phase 43 / TDD-43-06: Bi-Temporal Git-Revert Mistake Miner.
Tests extraction of pre-mortem mistake guards from simulated Git revert logs.
"""


def parse_revert_message(commit_subject: str, commit_body: str) -> dict | None:
    """Parses a git commit message to detect revert patterns and extract mistake guards."""
    if not commit_subject.startswith("Revert"):
        return None
    return {
        "reverted_summary": commit_subject.replace("Revert ", "").strip('"'),
        "rationale": commit_body.strip() if commit_body else "No explanation provided",
        "guard_status": "active",
    }


def test_parse_git_revert_commit():
    subject = 'Revert "feat: enable aggressive async socket pooling"'
    body = "Found race condition causing connection timeouts under 50+ concurrent requests."
    guard = parse_revert_message(subject, body)
    assert guard is not None
    assert guard["reverted_summary"] == "feat: enable aggressive async socket pooling"
    assert "race condition" in guard["rationale"]
    assert guard["guard_status"] == "active"
