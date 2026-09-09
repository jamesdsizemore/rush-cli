"""Media optimization, CLS layout audit, and SVG security sanitizer tool.

Performs SVG script and event handler injection audit, HTML/template CLS image
dimension verification, and raster image optimization guarded by --allow-artifact-write.
"""

from __future__ import annotations

import re
import stat
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET

from ..io.atomic_file import AtomicFile, SanitizedBytes
from ..io.physical_paths import PhysicalRoot
from .base import Finding, ToolFn, ToolName, ToolResult, ToolStatus
from .common import elapsed_ms, now_ms

_DTD_ENTITY_PATTERN = re.compile(rb"<!\s*(?:DOCTYPE|ENTITY)\b", re.IGNORECASE)
_ACTIVE_ELEMENT_NAMES = frozenset({"script", "iframe", "object", "embed"})
_URI_ATTRIBUTE_NAMES = frozenset(
    {"href", "src", "action", "formaction", "poster", "data", "cite", "background"}
)
_URI_ANIMATION_VALUE_NAMES = frozenset({"values", "from", "to", "by"})

# Regex pattern for HTML <img> without width/height
_IMG_TAG_PATTERN = re.compile(r"<img\b([^>]*)>", re.IGNORECASE)


def _local_name(name: str) -> str:
    return name.rsplit("}", 1)[-1].casefold()


def _is_javascript_uri(value: str) -> bool:
    return "".join(value.split()).casefold().startswith("javascript:")


def _has_javascript_animation_value(element: ET.Element) -> bool:
    target_name = next(
        (
            value.rsplit(":", 1)[-1].casefold()
            for name, value in element.attrib.items()
            if _local_name(name) == "attributename"
        ),
        "",
    )
    if target_name not in _URI_ATTRIBUTE_NAMES:
        return False
    return any(
        _is_javascript_uri(part)
        for name, value in element.attrib.items()
        if _local_name(name) in _URI_ANIMATION_VALUE_NAMES
        for part in value.split(";")
    )


def _parse_svg(content: bytes) -> tuple[bytes, bool]:
    """Parse SVG without declarations and remove decoded executable content."""
    if _DTD_ENTITY_PATTERN.search(content.replace(b"\x00", b"")):
        raise ValueError("DTD and entity declarations are forbidden")
    root = ET.fromstring(content)
    if _local_name(root.tag) in _ACTIVE_ELEMENT_NAMES:
        raise ValueError("active root element is forbidden")
    changed = False
    for parent in root.iter():
        for child in list(parent):
            child_name = _local_name(child.tag)
            if child_name in _ACTIVE_ELEMENT_NAMES or (
                child_name in {"animate", "set"}
                and _has_javascript_animation_value(child)
            ):
                parent.remove(child)
                changed = True
        for name, value in list(parent.attrib.items()):
            local_name = _local_name(name)
            if (local_name.startswith("on") and len(local_name) > 2) or (
                local_name in _URI_ATTRIBUTE_NAMES and _is_javascript_uri(value)
            ):
                del parent.attrib[name]
                changed = True
    sanitized = ET.tostring(root, encoding="utf-8")
    ET.fromstring(sanitized)
    return sanitized, changed


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
        sanitize: bool = False,
        optimize: bool = False,
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
        return self.run(
            path,
            permissions=permissions,
            sanitize=sanitize,
            optimize=optimize,
            **options,
        )

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
        invalid_svg = False
        pending_svg_writes: list[tuple[AtomicFile, Path, bytes]] = []

        # 1. Audit SVGs
        for svg_path in svg_files:
            try:
                root_path = p if p.is_dir() else p.parent
                relative_path = svg_path.relative_to(root_path)
                physical_root = PhysicalRoot(root_path)
                contained_path = physical_root.open_contained(
                    relative_path, purpose="read"
                )
                if not stat.S_ISREG(contained_path.stat(follow_symlinks=False).st_mode):
                    raise ValueError("SVG is not an ordinary file")
                content = contained_path.read_bytes()
                cleaned, has_active_content = _parse_svg(content)

                if has_active_content:
                    if sanitize and getattr(granted_perms, "artifact_write", False):
                        pending_svg_writes.append(
                            (AtomicFile(physical_root), relative_path, cleaned)
                        )
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
            except Exception:  # noqa: BLE001
                invalid_svg = True
                findings.append(
                    Finding(
                        path=str(svg_path),
                        line=1,
                        rule="media-opt/invalid-svg",
                        severity="error",
                        message=f"SVG could not be safely parsed: {svg_path.name}",
                        remediation="Provide well-formed SVG without DTD or entity declarations.",
                    )
                )

        if not invalid_svg:
            for writer, relative_path, cleaned in pending_svg_writes:
                try:
                    writer.write_bytes(relative_path, SanitizedBytes(data=cleaned))
                    sanitized_svg_count += 1
                except Exception:  # noqa: BLE001
                    invalid_svg = True
                    findings.append(
                        Finding(
                            path=str(relative_path),
                            line=1,
                            rule="media-opt/svg-write-error",
                            severity="error",
                            message="Sanitized SVG could not be written safely.",
                            remediation="Check target containment and file permissions.",
                        )
                    )
                    break

        # 2. Audit CLS Image Dimensions in Markup
        for html_path in html_files:
            try:
                markup = html_path.read_text(encoding="utf-8", errors="replace")
                for line_idx, line in enumerate(markup.splitlines(), 1):
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
        if (
            not invalid_svg
            and optimize
            and getattr(granted_perms, "artifact_write", False)
        ):
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
        status: ToolStatus
        if invalid_svg:
            status = "error"
        elif has_errors:
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
