"""Phase 01 truth-audit contracts for claimed live adapters."""

from __future__ import annotations

from rush.catalog import PARSER_FIXTURE_SUITES, TOOL_SPECS


def test_every_engine_backed_real_adapter_has_a_registered_parser_fixture_suite() -> (
    None
):
    claimed_live = {
        name
        for name, spec in TOOL_SPECS.items()
        if spec.maturity == "real_adapter" and spec.engine_names
    }

    assert claimed_live
    assert claimed_live <= set(PARSER_FIXTURE_SUITES)
    assert PARSER_FIXTURE_SUITES["iac"] == (
        "tests/test_tflint_reference.py",
        "tests/test_checkov_reference.py",
    )
