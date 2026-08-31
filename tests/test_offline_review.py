"""Unit tests for OfflineReviewTool (PR50.11)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from rush.tools.offline_runner import OfflineReviewTool


def test_offline_review_skipped_when_model_absent(tmp_path: Path) -> None:
    tool = OfflineReviewTool()
    res = tool.run(tmp_path)

    assert res["tool"] == "offline-review"
    assert res["status"] == "skipped"
    assert "onnxruntime or ONNX model absent" in res["summary"]
    assert res["findings"] == []


def test_offline_review_skipped_when_onnxruntime_not_installed(
    tmp_path: Path, monkeypatch
) -> None:
    model_file = tmp_path / "model.onnx"
    model_file.write_bytes(b"dummy onnx content")

    tool = OfflineReviewTool()
    with patch("rush.tools.offline_runner._has_onnxruntime", return_value=False):
        res = tool.run(tmp_path, model_path=model_file)

    assert res["status"] == "skipped"
    assert "onnxruntime" in res["summary"]


def test_offline_review_runs_with_mocked_session(tmp_path: Path) -> None:
    model_file = tmp_path / "model.onnx"
    model_file.write_bytes(b"dummy onnx content")

    code_file = tmp_path / "sample.py"
    code_file.write_text("def insecure_exec(cmd):\n    exec(cmd)\n", encoding="utf-8")

    tool = OfflineReviewTool()

    mock_session = MagicMock()
    # Mock inference output: defect score 0.85
    mock_session.run.return_value = [[[0.85]]]
    mock_session.get_inputs.return_value = [MagicMock(name="input_ids")]

    with (
        patch("rush.tools.offline_runner._has_onnxruntime", return_value=True),
        patch(
            "rush.tools.offline_runner._create_inference_session",
            return_value=mock_session,
        ),
    ):
        res = tool.run(tmp_path, model_path=model_file)

    assert res["status"] == "warn"
    assert len(res["findings"]) == 1
    assert res["findings"][0]["rule"] == "offline-review/model-flagged-defect"


def test_offline_review_clean_with_low_score(tmp_path: Path) -> None:
    model_file = tmp_path / "model.onnx"
    model_file.write_bytes(b"dummy onnx content")

    code_file = tmp_path / "clean.py"
    code_file.write_text("def add(a, b):\n    return a + b\n", encoding="utf-8")

    tool = OfflineReviewTool()

    mock_session = MagicMock()
    mock_session.run.return_value = [[[0.05]]]
    mock_session.get_inputs.return_value = [MagicMock(name="input_ids")]

    with (
        patch("rush.tools.offline_runner._has_onnxruntime", return_value=True),
        patch(
            "rush.tools.offline_runner._create_inference_session",
            return_value=mock_session,
        ),
    ):
        res = tool.run(tmp_path, model_path=model_file)

    assert res["status"] == "ok"
    assert res["findings"] == []
