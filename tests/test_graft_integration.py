"""Opt-in local Graft review-context contracts."""

from __future__ import annotations

from pathlib import Path

from rush.tools.review import ReviewTool


class FakeGraftProvider:
    def available(self, project_root: Path) -> bool:
        return True

    def context_for(self, path: Path) -> list[dict]:
        return [
            {
                "path": str(path),
                "line": 1,
                "rule": "graft-context",
                "severity": "info",
                "message": "local dependency context",
            }
        ]


def test_review_uses_graft_only_when_explicitly_requested(tmp_path: Path) -> None:
    source = tmp_path / "module.py"
    source.write_text("x = 1\n", encoding="utf-8")

    result = ReviewTool().run(
        source, use_graft=True, graft_provider=FakeGraftProvider()
    )

    assert result["review_kind"] == "heuristic"
    assert any(finding["rule"] == "graft-context" for finding in result["findings"])
    assert result["metadata"]["graft"] == "used"


def test_review_without_opt_in_preserves_heuristic_only_output(tmp_path: Path) -> None:
    source = tmp_path / "module.py"
    source.write_text("x = 1\n", encoding="utf-8")

    result = ReviewTool().run(source, graft_provider=FakeGraftProvider())

    assert not any(finding["rule"] == "graft-context" for finding in result["findings"])
    assert result["review_kind"] == "heuristic"


def test_local_graft_context_provider_fallback(tmp_path: Path) -> None:
    from rush.integrations.graft import LocalGraftContext

    provider = LocalGraftContext()
    # Directory without .hermes/graft
    assert provider.available(tmp_path) is False
    assert provider.context_for(tmp_path / "app.py") == []

