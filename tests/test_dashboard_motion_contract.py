"""Phase 66 P66-02: theme/motion token contract (plan section 3.4).

These are the directly unit-testable half of motion acceptance -- exact
token values and the generation-based stale-response/animation cancellation
contract. They do not by themselves prove real browser animation; the plan's
own section 3.9 requires observing actual intermediate animated states in a
real installed browser against the supplied reference video, which needs a
real browser automation runtime. This sandbox's project virtualenv has no
`playwright`/`selenium` install (verified: `ModuleNotFoundError: No module
named 'playwright'` against `.venv/bin/python`), so that live comparison is
a disclosed external blocker for this packet, not something faked here.
"""

from __future__ import annotations

from rush.dashboard.theme import (
    MOTION,
    THEME,
    SelectionGeneration,
    contrast_ratio,
    resolve_duration,
)


def test_exact_theme_contrast() -> None:
    assert THEME == {
        "background": "#080B18",
        "surface": "#10162A",
        "surface_raised": "#18213A",
        "border": "#7282AA",
        "text": "#F5F7FF",
        "text_muted": "#BAC5DF",
        "blue": "#4DDFFF",
        "pink": "#FF62CC",
        "purple": "#B89CFF",
        "warning": "#FFE080",
        "error": "#FF8FA3",
        "focus": "#FFFFFF",
    }

    # Normal text must meet 4.5:1 against every surface it appears on.
    for surface in ("background", "surface", "surface_raised"):
        assert contrast_ratio(THEME["text"], THEME[surface]) >= 4.5
        assert contrast_ratio(THEME["text_muted"], THEME[surface]) >= 4.5

    # Focus ring and graph-control accents must meet 3:1 against adjacent
    # surfaces (spec 3.4).
    for surface in ("background", "surface"):
        assert contrast_ratio(THEME["focus"], THEME[surface]) >= 3.0
        assert contrast_ratio(THEME["blue"], THEME[surface]) >= 3.0
        assert contrast_ratio(THEME["pink"], THEME[surface]) >= 3.0
        assert contrast_ratio(THEME["purple"], THEME[surface]) >= 3.0


def test_motion_tokens_and_reduced_mode() -> None:
    assert MOTION["easing"] == "cubic-bezier(0.22,1,0.36,1)"
    assert MOTION["easing_exit"] == "cubic-bezier(0.4,0,1,1)"
    assert MOTION["hover_focus_ms"] == 120
    assert MOTION["menu_ms"] == 180
    assert MOTION["project_enter_ms"] == 520
    assert MOTION["camera_focus_ms"] == 420
    assert MOTION["relationship_reveal_ms"] == 360
    assert MOTION["relationship_stagger_ms"] == 24
    assert MOTION["relationship_stagger_cap_ms"] == 192
    assert MOTION["inspector_entry_ms"] == 300
    assert MOTION["detail_row_fade_ms"] == 180
    assert MOTION["detail_row_translate_px"] == 8
    assert MOTION["detail_row_stagger_ms"] == 32
    assert MOTION["detail_row_stagger_cap_ms"] == 128
    assert MOTION["exit_ms"] == 140
    assert MOTION["evidence_pulse_ms"] == 480
    assert MOTION["interaction_complete_ms"] == 800
    assert MOTION["reduced_motion_opacity_ms"] == 80

    # Reduced motion collapses every spatial animation to the same 80ms
    # opacity change, regardless of the token's normal duration.
    assert resolve_duration("camera_focus_ms", reduced_motion=True) == 80
    assert resolve_duration("relationship_reveal_ms", reduced_motion=True) == 80
    assert resolve_duration("camera_focus_ms", reduced_motion=False) == 420
    assert resolve_duration("project_enter_ms", reduced_motion=False) == 520


def test_selection_generation_cancels_prior_response() -> None:
    generation = SelectionGeneration()
    assert generation.current() == 0

    first = generation.advance()  # user selects node A; fetch/animation start
    assert generation.is_current(first)

    # A newer action (project switch, new selection) fires before the first
    # request/animation resolves.
    second = generation.advance()
    assert not generation.is_current(first)
    assert generation.is_current(second)

    # A late-arriving response/animation completion tagged with the stale
    # first generation must be ignored even after further advances.
    generation.advance()
    assert not generation.is_current(first)
    assert not generation.is_current(second)
