"""Media optimization, CLS layout audit, and SVG security sanitizer tool.

Performs SVG script and event handler injection audit, HTML/template CLS image
dimension verification, and raster image optimization guarded by --allow-artifact-write.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from .base import Finding, ToolFn, ToolName, ToolResult
from .common import elapsed_ms, now_ms

# Regex patterns for SVG security auditing
_SCRIPT_TAG_PATTERN = re.compile(
    r"<script[\s\S]*?</script>|<script[^>]*/>", re.IGNORECASE
)
_EVENT_HANDLER_PATTERN = re.compile(
    r"\bon[a-z]+\s*=\s*['\"][^'\"]*['\"]", re.IGNORECASE
)
_JS_URI_PATTERN = re.compile(
    r"""(href|src|xlink:href)\s*=\s*['"]\s*javascript:[^'"]*['"]""", re.IGNORECASE
)

# Regex pattern for HTML <img> without width/height
_IMG_TAG_PATTERN = re.compile(r"<img\b([^>]*)>", re.IGNORECASE)


def _sanitize_svg_content(content: str) -> str:
    """Strip script tags, inline event handlers, and javascript: URIs from SVG."""
    sanitized = _SCRIPT_TAG_PATTERN.sub("", content)
    sanitized = _EVENT_HANDLER_PATTERN.sub("", sanitized)
    sanitized = _JS_URI_PATTERN.sub("", sanitized)
    return sanitized


class MediaOptTool(ToolFn):
    name: ToolName = "media-opt"

    @property
    def mcp_description(self) -> str:
        return (
            "Audit media assets for CLS and SVG security at <path>; writes "
            "optimized assets with --allow-artifact-write. Returns {status, findings[], summary}."
        )

    def __call__(
        self,
        path: Path,
        *,
        allow_network: bool = False,
        allow_download: bool = False,
        allow_cache_write: bool = False,
        allow_build: bool = False,
        allow_slow: bool = False,
        allow_artifact_write: bool = False,
        allow_browser: bool = False,
        **options: object,
    ) -> ToolResult:
        from ..permissions import ExecutionPermissions

        permissions = ExecutionPermissions(
            network=allow_network,
            download=allow_download,
            cache_write=allow_cache_write,
            build=allow_build,
            slow=allow_slow,
            artifact_write=allow_artifact_write,
            browser=allow_browser,
        )
        return self.run(path, permissions=permissions, **options)

    def run(
        self,
        path: Path,
        *,
        config: Any = None,
        permissions: Any = None,
        sanitize: bool = False,
        optimize: bool = False,
        **options: object,
    ) -> ToolResult:
        from ..permissions import ExecutionPermissions, build_execution_metadata

        start = now_ms()
        p = Path(path)
        granted_perms = permissions or ExecutionPermissions()

        svg_files: list[Path] = []
        html_files: list[Path] = []
        image_files: list[Path] = []

        if p.is_file():
            suf = p.suffix.lower()
            if suf == ".svg":
                svg_files.append(p)
            elif suf in (".html", ".htm", ".jsx", ".tsx", ".vue", ".svelte"):
                html_files.append(p)
            elif suf in (".png", ".jpg", ".jpeg", ".webp"):
                image_files.append(p)
        elif p.is_dir():
            svg_files.extend(sorted(p.glob("**/*.svg")))
            for ext in ("*.html", "*.htm", "*.jsx", "*.tsx", "*.vue", "*.svelte"):
                html_files.extend(sorted(p.glob(f"**/{ext}")))
            for ext in ("*.png", "*.jpg", "*.jpeg", "*.webp"):
                image_files.extend(sorted(p.glob(f"**/{ext}")))

        if not svg_files and not html_files and not image_files:
            return ToolResult(
                tool=self.name,
                engine="media-opt",
                engine_version="1.0.0",
                status="skipped",
                duration_ms=elapsed_ms(start),
                summary=f"media-opt: No media or markup files found at {path}.",
                findings=[],
                raw=None,
                metadata={
                    "execution": build_execution_metadata(
                        "executed",
                        granted=permissions,
                        producer="media-opt",
                    )
                },
            )

        findings: list[Finding] = []
        sanitized_svg_count = 0

        # 1. Audit SVGs
        for svg_path in svg_files:
            try:
                content = svg_path.read_text(encoding="utf-8", errors="replace")
                has_script = bool(_SCRIPT_TAG_PATTERN.search(content))
                has_events = bool(_EVENT_HANDLER_PATTERN.search(content))
                has_js_uri = bool(_JS_URI_PATTERN.search(content))

                if has_script or has_events or has_js_uri:
                    if sanitize and getattr(granted_perms, "artifact_write", False):
                        cleaned = _sanitize_svg_content(content)
                        svg_path.write_text(cleaned, encoding="utf-8")
                        sanitized_svg_count += 1
                    else:
                        findings.append(
                            Finding(
                                path=str(svg_path),
                                line=1,
                                rule="media-opt/svg-script-injection",
                                severity="error",
                                message=f"SVG contains executable scripts or event handlers: {svg_path.name}",
                                remediation="Sanitize SVG by stripping active scripts, or run with --allow-artifact-write to sanitize.",
                            )
                        )
            except Exception:  # noqa: BLE001, S112
                continue

        # 2. Audit CLS Image Dimensions in Markup
        for html_path in html_files:
            try:
                content = html_path.read_text(encoding="utf-8", errors="replace")
                for line_idx, line in enumerate(content.splitlines(), 1):
                    for match in _IMG_TAG_PATTERN.finditer(line):
                        attrs = match.group(1).lower()
                        has_width = "width=" in attrs or "width:" in attrs
                        has_height = "height=" in attrs or "height:" in attrs
                        has_aspect_ratio = "aspect-ratio" in attrs
                        if not (has_width and has_height) and not has_aspect_ratio:
                            findings.append(
                                Finding(
                                    path=str(html_path),
                                    line=line_idx,
                                    rule="media-opt/missing-image-dimensions",
                                    severity="warn",
                                    message=f"Image tag missing explicit width/height attributes in {html_path.name}: {match.group(0)[:60]}",
                                    remediation="Specify explicit width and height or aspect-ratio CSS to avoid Cumulative Layout Shift (CLS).",
                                )
                            )
            except Exception:  # noqa: BLE001, S112
                continue

        # 3. Raster Image Optimization
        optimized_images_count = 0
        if optimize and getattr(granted_perms, "artifact_write", False):
            try:
                from PIL import Image

                for img_path in image_files:
                    if img_path.suffix.lower() == ".png":
                        orig_size = img_path.stat().st_size
                        with Image.open(img_path) as im:
                            im.save(img_path, optimize=True)
                        new_size = img_path.stat().st_size
                        if new_size < orig_size:
                            optimized_images_count += 1
            except ImportError:
                pass

        has_errors = any(f.get("severity") in ("error", "fail") for f in findings)
        if has_errors:
            status = "fail"
        elif findings:
            status = "warn"
        else:
            status = "ok"

        total_scanned = len(svg_files) + len(html_files) + len(image_files)
        summary = f"media-opt: Audited {total_scanned} media/markup file(s), {len(findings)} finding(s)"
        if sanitized_svg_count > 0:
            summary += f", sanitized {sanitized_svg_count} SVG(s)"

        return ToolResult(
            tool=self.name,
            engine="media-opt",
            engine_version="1.0.0",
            status=status,
            duration_ms=elapsed_ms(start),
            summary=summary,
            findings=findings,
            metrics={
                "svg_files_count": len(svg_files),
                "markup_files_count": len(html_files),
                "image_files_count": len(image_files),
                "findings_count": len(findings),
                "sanitized_svg_count": sanitized_svg_count,
            },
            raw={"sanitized_count": sanitized_svg_count},
            metadata={
                "execution": build_execution_metadata(
                    "executed",
                    granted=permissions,
                    producer="media-opt",
                )
            },
        )
