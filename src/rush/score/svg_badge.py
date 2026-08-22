"""Standalone SVG quality badge generator."""

from __future__ import annotations

from typing import ClassVar


class SvgBadgeGenerator:
    """Generates pure SVG badges representing repository quality score."""

    GRADE_COLORS: ClassVar[dict[str, str]] = {
        "A+": "#4c1",
        "A": "#97ca00",
        "A-": "#a4a61d",
        "B+": "#dfb317",
        "B": "#fe7d37",
        "C": "#e05d44",
        "D": "#e05d44",
        "F": "#e05d44",
    }

    @classmethod
    def generate_badge_svg(cls, score: float, grade: str) -> str:
        color = cls.GRADE_COLORS.get(grade, "#9f9f9f")
        text_label = "rush quality"
        text_val = f"{score:.0f}% ({grade})"

        svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="130" height="20" role="img" aria-label="{text_label}: {text_val}">
  <linearGradient id="s" x2="0" y2="100%">
    <stop offset="0" stop-color="#bbb" stop-opacity=".1"/>
    <stop offset="1" stop-opacity=".1"/>
  </linearGradient>
  <clipPath id="r">
    <rect width="130" height="20" rx="3" fill="#fff"/>
  </clipPath>
  <g clip-path="url(#r)">
    <rect width="75" height="20" fill="#555"/>
    <rect x="75" width="55" height="20" fill="{color}"/>
    <rect width="130" height="20" fill="url(#s)"/>
  </g>
  <g fill="#fff" text-anchor="middle" font-family="Verdana,Geneva,DejaVu Sans,sans-serif" text-rendering="geometricPrecision" font-size="110">
    <text x="385" y="140" transform="scale(.1)" fill="#fff">{text_label}</text>
    <text x="1015" y="140" transform="scale(.1)" fill="#fff">{text_val}</text>
  </g>
</svg>"""
        return svg
