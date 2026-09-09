"""Unit tests for MediaOptTool (PR50.10)."""

from __future__ import annotations

from pathlib import Path
from xml.etree import ElementTree as ET

from rush.permissions import ExecutionPermissions
from rush.tools.media_opt import MediaOptTool


def test_media_opt_skipped_when_no_media(tmp_path: Path) -> None:
    tool = MediaOptTool()
    res = tool.run(tmp_path)

    assert res["tool"] == "media-opt"
    assert res["status"] == "skipped"
    assert "No media or markup files found" in res["summary"]
    assert res["findings"] == []


def test_media_opt_clean_svg(tmp_path: Path) -> None:
    svg_file = tmp_path / "icon.svg"
    svg_file.write_text(
        '<svg viewBox="0 0 100 100"><circle cx="50" cy="50" r="40"/></svg>',
        encoding="utf-8",
    )

    tool = MediaOptTool()
    res = tool.run(svg_file)

    assert res["status"] == "ok"
    assert res["findings"] == []


def test_media_opt_detects_svg_script_injection(tmp_path: Path) -> None:
    svg_file = tmp_path / "malicious.svg"
    svg_file.write_text(
        '<svg><script>alert(1)</script><circle cx="10" cy="10" r="5" onload="evil()"/></svg>',
        encoding="utf-8",
    )

    tool = MediaOptTool()
    res = tool.run(svg_file)

    assert res["status"] == "fail"
    assert len(res["findings"]) >= 1
    rules = [f["rule"] for f in res["findings"]]
    assert "media-opt/svg-script-injection" in rules


def test_media_opt_svg_sanitize_with_permissions(tmp_path: Path) -> None:
    svg_file = tmp_path / "dirty.svg"
    svg_file.write_text(
        '<svg><script>alert("xss")</script><rect width="10" height="10" onclick="hack()"/></svg>',
        encoding="utf-8",
    )

    tool = MediaOptTool()
    res = tool.run(
        svg_file,
        sanitize=True,
        permissions=ExecutionPermissions(artifact_write=True),
    )

    assert res["status"] == "ok"
    cleaned = svg_file.read_text(encoding="utf-8")
    assert "<script" not in cleaned
    assert "onclick=" not in cleaned
    assert "<rect" in cleaned


def test_media_opt_sanitizes_decoded_namespaced_and_mixed_case_svg(
    tmp_path: Path,
) -> None:
    svg_file = tmp_path / "encoded.svg"
    svg_file.write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" '
        'xmlns:xlink="http://www.w3.org/1999/xlink" '
        'xmlns:evil="urn:evil"><ScRiPt>alert(1)</ScRiPt>'
        '<rect id="shape" width="10" height="12" evil:OnLoad="hack()" '
        'xlink:href="JaVa&#x53;CrIpT:alert(2)" fill="blue"/></svg>',
        encoding="utf-8",
    )

    res = MediaOptTool().run(
        svg_file,
        sanitize=True,
        permissions=ExecutionPermissions(artifact_write=True),
    )

    assert res["status"] == "ok"
    root = ET.fromstring(svg_file.read_bytes())
    assert all(
        element.tag.rsplit("}", 1)[-1].casefold() != "script" for element in root.iter()
    )
    rect = next(element for element in root.iter() if element.tag.endswith("}rect"))
    assert rect.attrib["id"] == "shape"
    assert rect.attrib["width"] == "10"
    assert rect.attrib["height"] == "12"
    assert rect.attrib["fill"] == "blue"
    assert all(
        not name.rsplit("}", 1)[-1].casefold().startswith("on")
        and not "".join(value.split()).casefold().startswith("javascript:")
        for name, value in rect.attrib.items()
    )


def test_media_opt_rejects_dtd_and_external_entities_without_writes(
    tmp_path: Path,
) -> None:
    outside = tmp_path / "outside.txt"
    outside.write_bytes(b"synthetic-secret-outside")
    svg_file = tmp_path / "entity.svg"
    original = (
        '<!DoCtYpE svg [<!EnTiTy leak SYSTEM "'
        f"{outside.as_uri()}"
        '">]><svg><text>&leak;</text></svg>'
    ).encode()
    svg_file.write_bytes(original)

    res = MediaOptTool().run(
        svg_file,
        sanitize=True,
        permissions=ExecutionPermissions(artifact_write=True),
    )

    assert res["status"] == "error"
    assert svg_file.read_bytes() == original
    assert outside.read_bytes() == b"synthetic-secret-outside"
    assert "synthetic-secret-outside" not in res["summary"]


def test_media_opt_rejects_malformed_svg_without_writes(tmp_path: Path) -> None:
    svg_file = tmp_path / "malformed.svg"
    original = b'<svg><rect id="shape"></svg>'
    svg_file.write_bytes(original)

    res = MediaOptTool().run(
        svg_file,
        sanitize=True,
        permissions=ExecutionPermissions(artifact_write=True),
    )

    assert res["status"] == "error"
    assert svg_file.read_bytes() == original


def test_media_opt_preserves_benign_namespaced_svg_geometry(tmp_path: Path) -> None:
    svg_file = tmp_path / "geometry.svg"
    svg_file.write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20">'
        '<path id="edge" d="M 1 2 L 18 17" stroke="black"/></svg>',
        encoding="utf-8",
    )

    res = MediaOptTool().run(
        svg_file,
        sanitize=True,
        permissions=ExecutionPermissions(artifact_write=True),
    )

    assert res["status"] == "ok"
    root = ET.fromstring(svg_file.read_bytes())
    assert root.tag == "{http://www.w3.org/2000/svg}svg"
    path = next(element for element in root.iter() if element.tag.endswith("}path"))
    assert path.attrib == {
        "id": "edge",
        "d": "M 1 2 L 18 17",
        "stroke": "black",
    }


def test_media_opt_strips_active_uri_animation_and_embedded_content(
    tmp_path: Path,
) -> None:
    svg_file = tmp_path / "active-content.svg"
    svg_file.write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" '
        'xmlns:h="http://www.w3.org/1999/xhtml">'
        '<rect id="safe" aria-label="javascript: is a URI scheme" '
        'data-note="javascript: documentation" width="10" height="12">'
        '<animate attributeName="cx" values="0;10"/></rect>'
        '<a id="link" href="javascript:alert(1)"/>'
        '<animate id="active-animation" attributeName="href" '
        'values="https://safe.example;javascript:alert(2)"/>'
        '<set id="active-set" attributeName="href" to="JaVa&#x53;CrIpT:alert(3)"/>'
        '<foreignObject><h:div id="safe-html">safe</h:div>'
        '<h:iframe srcdoc="&lt;script&gt;alert(4)&lt;/script&gt;"/>'
        "</foreignObject></svg>",
        encoding="utf-8",
    )

    res = MediaOptTool().run(
        svg_file,
        sanitize=True,
        permissions=ExecutionPermissions(artifact_write=True),
    )

    assert res["status"] == "ok"
    root = ET.fromstring(svg_file.read_bytes())
    by_id = {element.attrib.get("id"): element for element in root.iter()}
    assert by_id["safe"].attrib["aria-label"] == "javascript: is a URI scheme"
    assert by_id["safe"].attrib["data-note"] == "javascript: documentation"
    assert by_id["safe-html"].text == "safe"
    assert by_id["safe"].find("{http://www.w3.org/2000/svg}animate") is not None
    assert "link" in by_id
    assert "href" not in by_id["link"].attrib
    assert "active-animation" not in by_id
    assert "active-set" not in by_id
    assert all(
        element.tag.rsplit("}", 1)[-1].casefold()
        not in {"script", "iframe", "object", "embed"}
        for element in root.iter()
    )


def test_media_opt_cls_missing_dimensions(tmp_path: Path) -> None:
    html_file = tmp_path / "page.html"
    html_file.write_text(
        '<html><body><img src="photo.png" alt="photo"></body></html>',
        encoding="utf-8",
    )

    tool = MediaOptTool()
    res = tool.run(html_file)

    assert res["status"] == "warn"
    assert len(res["findings"]) == 1
    assert res["findings"][0]["rule"] == "media-opt/missing-image-dimensions"
