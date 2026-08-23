"""Unit tests for Phase 45 TelemetryStore, OutputShaper, and Gain TUI."""

from pathlib import Path

from rich.console import Console

from src.rush.token_economy.output_shaper import OutputShaper
from src.rush.token_economy.telemetry import TelemetryStore
from src.rush.token_economy.tui_gain import render_gain_dashboard


def test_telemetry_store(tmp_path: Path):
    store = TelemetryStore(project_root=tmp_path)
    summary_empty = store.get_summary()
    assert summary_empty["events_count"] == 0
    assert summary_empty["net_tokens_saved"] == 0

    # Record events
    store.record_savings(
        "pytest_distiller", raw_tokens=5000, compressed_tokens=500, duration_ms=12.5
    )
    store.record_savings(
        "toon_encoder", raw_tokens=2000, compressed_tokens=800, duration_ms=5.0
    )

    summary = store.get_summary()
    assert summary["events_count"] == 2
    assert summary["total_raw_tokens"] == 7000
    assert summary["total_compressed_tokens"] == 1300
    assert summary["net_tokens_saved"] == 5700
    assert summary["compression_ratio"] > 0.8
    assert summary["dollar_savings_est"] > 0.0


def test_output_shaper():
    shaper = OutputShaper()

    verbose_text = (
        "Sure, I can help with that. Here is the requested output:\n- Step 1\n- Step 2"
    )
    shaped = shaper.shape_response(verbose_text, style="terse")
    assert not shaped.startswith("Sure")
    assert "- Step 1" in shaped

    # Non-terse style
    assert shaper.shape_response(verbose_text, style="default") == verbose_text


def test_render_gain_dashboard(tmp_path: Path):
    console = Console(record=True, width=80)
    render_gain_dashboard(project_root=tmp_path, console=console)
    output = console.export_text()
    assert "Rush Context Intelligence Gain HUD" in output
