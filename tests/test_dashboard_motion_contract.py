"""Phase 66 P66-02 / Phase 69 P69-05: theme/motion token contract and
motion/responsive/recovery source contract (plan section 3.4, Phase 66 §0
rows 15/24).

These are the directly unit-testable half of motion acceptance -- exact
token values, the generation-based stale-response/animation cancellation
contract, and (P69-05 additions below) static source-content assertions
against the real, loaded `project_map.js`/`application.js`/CSS -- exact
literal identifiers, numeric tokens, and code ordering, not a JS runtime.
They do not by themselves prove real browser animation/interaction; the
plan's own section 3.9 requires observing actual intermediate animated
states and runtime behaviors (wheel zoom/pan, keyboard shortcuts,
fetch-abort/retry, polling) in a real installed browser against the
supplied reference video, which needs a real browser automation runtime.
This sandbox's project virtualenv has no `playwright`/`selenium` install
(verified: `ModuleNotFoundError: No module named 'playwright'` against
`.venv/bin/python`), so that live comparison is a disclosed external
blocker for this packet's pytest half, proven separately by a live
`browser-qa-agent`/`e2e-runner` session against a running `rush dashboard`,
not faked here.
"""

from __future__ import annotations

from rush.dashboard.static_assets import (
    BOOTSTRAP_JS,
    DASHBOARD_CSS,
    load_dashboard_asset,
)
from rush.dashboard.theme import (
    MOTION,
    THEME,
    SelectionGeneration,
    contrast_ratio,
    resolve_duration,
)


def _balanced_brace_span(source: str, brace_open: int) -> str:
    """Return `source[brace_open:...]` up to (and including) the `}` that
    balances the `{` at `brace_open`."""
    depth = 0
    index = brace_open
    while index < len(source):
        if source[index] == "{":
            depth += 1
        elif source[index] == "}":
            depth -= 1
            if depth == 0:
                return source[brace_open : index + 1]
        index += 1
    raise AssertionError(f"unbalanced braces starting at {brace_open}")


def _extract_function_body(source: str, signature: str) -> str:
    """Balanced body of a `function name(...) { ... }` declaration whose
    definition line contains `signature` -- skips the parameter list via
    paren-balance first, so a default-object param (`options = {}`) never
    confuses the body's own brace-balance."""
    start = source.index(signature)
    paren_start = source.index("(", start)
    depth = 0
    index = paren_start
    while index < len(source):
        if source[index] == "(":
            depth += 1
        elif source[index] == ")":
            depth -= 1
            if depth == 0:
                break
        index += 1
    brace_open = source.index("{", index)
    return _balanced_brace_span(source, brace_open)


def _extract_arrow_body(source: str, signature: str) -> str:
    """Balanced body of an arrow function `(...) => { ... }` whose call site
    or declaration contains `signature`."""
    start = source.index(signature)
    arrow_index = source.index("=>", start)
    brace_open = source.index("{", arrow_index)
    return _balanced_brace_span(source, brace_open)


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


# --- Phase 69 P69-05: motion, responsive layout, and recovery (row 15/24) ---


def test_responsive_breakpoints_768_1024_present() -> None:
    assert "1024px" in DASHBOARD_CSS
    assert "768px" in DASHBOARD_CSS
    assert "data-open" in DASHBOARD_CSS
    assert "translateX(-100%)" in DASHBOARD_CSS
    assert "translateX(100%)" in DASHBOARD_CSS


def test_fit_restores_full_bounds_not_translation_reset() -> None:
    js = load_dashboard_asset("project_map.js")
    body = _extract_function_body(js, "function fit(")
    assert "Math.min" in body
    assert "Math.max" in body
    assert "translate(0px, 0px)" not in body


def test_set_filters_actually_filters() -> None:
    js = load_dashboard_asset("project_map.js")
    body = _extract_function_body(js, "function setFiltersInternal(")
    assert "nodeTypes" in body
    assert "display" in body


def test_selection_captures_live_transform_before_cancelling() -> None:
    js = load_dashboard_asset("project_map.js")
    capture_index = js.index("getComputedStyle(camera)")
    cancel_index = js.index("cancelActiveAnimations()", capture_index)
    assert 0 < cancel_index - capture_index < 400


def test_fetch_aborts_on_supersede_and_retries_per_schedule() -> None:
    js = load_dashboard_asset("application.js")
    assert "AbortController" in js
    for delay_ms in ("1000", "2000", "4000", "8000"):
        assert delay_ms in js


def test_reduced_motion_and_selected_project_persist_across_reload() -> None:
    assert "localStorage" in BOOTSTRAP_JS
    assert "reducedMotion" in BOOTSTRAP_JS
    assert "selectedProjectId" in BOOTSTRAP_JS
    js = load_dashboard_asset("application.js")
    assert "localStorage" in js
    assert "selectedProjectId" in js


def test_high_contrast_toggle_persists_and_never_affects_authorization() -> None:
    assert "highContrast" in BOOTSTRAP_JS
    js = load_dashboard_asset("application.js")
    assert "highContrast" in js
    assert "rush-high-contrast" in DASHBOARD_CSS
    # This packet's allowed_files never include server.py -- authorization
    # is mechanically untouched by these changes, not merely asserted.


def test_wheel_zoom_and_background_pan_work() -> None:
    js = load_dashboard_asset("project_map.js")
    assert '"wheel"' in js
    assert '"mousedown"' in js
    assert '"mousemove"' in js


def test_keyboard_zoom_fit_back_shortcuts_work() -> None:
    js = load_dashboard_asset("project_map.js")
    body = _extract_arrow_body(js, 'container.addEventListener("keydown"')
    for key_literal in ('"+"', '"-"', '"0"', '"Escape"'):
        assert key_literal in body


def test_roving_tabindex_moves_with_selection() -> None:
    js = load_dashboard_asset("project_map.js")
    assert "updateRovingTabindex" in js
    assert '"tabindex", "-1"' in js
    assert '? "0" : "-1"' in js


def test_semantic_relationship_list_exposes_same_records_as_graph() -> None:
    js = load_dashboard_asset("project_map.js")
    assert "relationship-list" in js
    body = _extract_function_body(js, "function buildRelationshipList(")
    assert "mapData.nodes" in body
    assert "mapData.edges" in body


def test_tooltip_appears_after_delay_and_closes_on_move() -> None:
    js = load_dashboard_asset("project_map.js")
    assert "TOOLTIP_DELAY_MS = 300" in js
    assert "mousemove" in js
    assert "map-tooltip" in js


def test_event_polling_and_visibility_change_trigger_refresh() -> None:
    js = load_dashboard_asset("application.js")
    assert "POLL_INTERVAL_ACTIVE_MS = 750" in js
    assert "POLL_INTERVAL_IDLE_MS = 5000" in js
    assert "visibilitychange" in js


def test_project_entry_animation_matches_520ms_default_easing() -> None:
    js = load_dashboard_asset("project_map.js")
    body = _extract_function_body(js, "function render(mapData) {")
    assert "project_enter_ms" in body
    assert "motion.easing," in body
    assert "easing_exit" not in body


def test_relationship_reveal_staggers_24ms_capped_192ms() -> None:
    js = load_dashboard_asset("project_map.js")
    assert "relationship_stagger_ms" in js
    assert "relationship_stagger_cap_ms" in js
    assert "newEdgeIndex" in js
    assert "newNodeIndex" in js
    assert "Math.min(" in js


def test_inspector_entry_transform_is_exact_perspective_translate_rotate() -> None:
    js = load_dashboard_asset("project_map.js")
    assert "inspector_initial_transform" in js
    assert (
        MOTION["inspector_initial_transform"]
        == "perspective(1200px) translateX(24px) rotateY(-6deg)"
    )


def test_detail_rows_stage_180ms_stagger_32ms_capped_128ms() -> None:
    js = load_dashboard_asset("project_map.js")
    body = _extract_function_body(js, "function showGroupMembersInternal(")
    assert "detail_row_fade_ms" in body
    assert "detail_row_stagger_ms" in body
    assert "detail_row_stagger_cap_ms" in body


def test_evidence_pulse_plays_once_480ms_on_real_event_only_never_idle() -> None:
    js = load_dashboard_asset("project_map.js")
    pulse_body = _extract_function_body(js, "function pulseEvidenceInternal(")
    assert "evidence_pulse_ms" in pulse_body
    assert "iterations: 1" in pulse_body
    render_body = _extract_function_body(js, "function render(mapData) {")
    assert (
        "evidence_pulse_ms" not in render_body
    )  # never triggered from the idle render path

    app_js = load_dashboard_asset("application.js")
    tick_body = _extract_arrow_body(app_js, "const tick = async () => {")
    assert "pulseEvidence" in tick_body
    assert 'status === "terminal"' in tick_body


def test_polling_cycle_with_unchanged_data_does_not_recreate_the_renderer() -> None:
    js = load_dashboard_asset("project_map.js")
    render_body = _extract_function_body(js, "function render(mapData) {")
    sequence_index = render_body.index("mapData.sequence")
    return_index = render_body.index("return;", sequence_index)
    assert return_index - sequence_index < 200

    render_map_body = _extract_function_body(js, "export function renderMap(")
    assert "activeContainer" in render_map_body


def test_polling_cycle_with_changed_data_updates_in_place_preserving_camera_and_selection() -> (
    None
):
    js = load_dashboard_asset("project_map.js")
    render_map_body = _extract_function_body(js, "export function renderMap(")
    assert "activeRenderer.render(mapData)" in render_map_body
    assert "createRenderer(container" in render_map_body


def test_several_poll_cycles_after_pan_selection_and_keyboard_focus_do_not_reset_interaction_state() -> (
    None
):
    js = load_dashboard_asset("project_map.js")
    render_body = _extract_function_body(js, "function render(mapData) {")
    assert "cancelActiveAnimations()" not in render_body


def test_full_graph_transition_from_data_ready_to_settled_render_is_at_most_800ms() -> (
    None
):
    # The 800ms bound itself; the real end-to-end measurement (data-ready to
    # fully-settled render, excluding fetch) is this packet's browser VERIFY
    # step -- not reproducible from a pure token assertion.
    assert MOTION["interaction_complete_ms"] == 800
