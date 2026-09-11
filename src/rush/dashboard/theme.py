"""Phase 66 P66-02: shared theme/motion tokens (plan section 3.4).

`THEME` and `MOTION` are the sole token values for the neon blue/pink/purple
palette and the coordinated-motion contract. `static_assets.py` serializes
them into CSS custom properties and the `/api/theme` bootstrap JSON;
`tui.py` (P66-03) builds Rich styles from the same mapping. Never duplicate
these literal values anywhere else -- import from here.
"""

from __future__ import annotations

from typing import Any

THEME: dict[str, str] = {
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

# Kind -> accent token (spec 3.4: "Blue identifies files/navigation, pink
# findings/active work, purple memory/agents").
KIND_ACCENTS: dict[str, str] = {
    "project": "blue",
    "directory": "blue",
    "file": "blue",
    "finding": "pink",
    "memory": "purple",
    "agent": "purple",
    "group": "blue",
}

# Motion token table (spec 3.4, "Motion token table is binding").
MOTION: dict[str, Any] = {
    "easing": "cubic-bezier(0.22,1,0.36,1)",
    "easing_exit": "cubic-bezier(0.4,0,1,1)",
    "hover_focus_ms": 120,
    "menu_ms": 180,
    "project_enter_ms": 520,
    "camera_focus_ms": 420,
    "relationship_reveal_ms": 360,
    "relationship_stagger_ms": 24,
    "relationship_stagger_cap_ms": 192,
    "inspector_entry_ms": 300,
    "detail_row_fade_ms": 180,
    "detail_row_translate_px": 8,
    "detail_row_stagger_ms": 32,
    "detail_row_stagger_cap_ms": 128,
    "exit_ms": 140,
    "evidence_pulse_ms": 480,
    "interaction_complete_ms": 800,
    "reduced_motion_opacity_ms": 80,
    "inspector_initial_transform": "perspective(1200px) translateX(24px) rotateY(-6deg)",
}


def resolve_duration(token_name: str, *, reduced_motion: bool) -> int:
    """Reduced-motion mode collapses every spatial animation to an 80ms
    opacity change (spec 3.4); otherwise return the named token's duration."""
    if reduced_motion:
        return int(MOTION["reduced_motion_opacity_ms"])
    value = MOTION[token_name]
    if not isinstance(value, int):
        raise TypeError(f"{token_name} is not a duration token")
    return value


def _srgb_channel_to_linear(channel_255: int) -> float:
    c = channel_255 / 255.0
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def relative_luminance(hex_color: str) -> float:
    """WCAG relative luminance (0..1) for a `#RRGGBB` color."""
    value = hex_color.lstrip("#")
    r, g, b = (int(value[i : i + 2], 16) for i in (0, 2, 4))
    lr, lg, lb = (_srgb_channel_to_linear(c) for c in (r, g, b))
    return 0.2126 * lr + 0.7152 * lg + 0.0722 * lb


def contrast_ratio(foreground_hex: str, background_hex: str) -> float:
    """WCAG contrast ratio (1..21) between two `#RRGGBB` colors."""
    l1 = relative_luminance(foreground_hex) + 0.05
    l2 = relative_luminance(background_hex) + 0.05
    lighter, darker = max(l1, l2), min(l1, l2)
    return lighter / darker


class SelectionGeneration:
    """Monotonic selection-generation counter (spec 3.4): "On a newer
    action ... increment selection generation and ignore responses/
    animation completions from prior generations." This is the directly
    unit-testable half of the cancellation contract that `application.js`
    and `project_map.js` implement client-side with the same semantics
    (see their `_generation`/`isCurrentGeneration` mirrors)."""

    def __init__(self) -> None:
        self._generation = 0

    def advance(self) -> int:
        """Start a new action (project switch, selection, filter change);
        returns the new current generation."""
        self._generation += 1
        return self._generation

    def current(self) -> int:
        return self._generation

    def is_current(self, generation: int) -> bool:
        """True only if `generation` is still the latest -- a response or
        animation tagged with any older generation must be discarded."""
        return generation == self._generation


__all__ = [
    "KIND_ACCENTS",
    "MOTION",
    "THEME",
    "SelectionGeneration",
    "contrast_ratio",
    "relative_luminance",
    "resolve_duration",
]
