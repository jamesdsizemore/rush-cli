"""Export Rush's outlined wordmark and web/application asset kit.

Uses installed FontTools, Pillow, Node sharp, and macOS iconutil. No Rush deps.
Run: python3 build.py; verify without rewriting: python3 build.py --check
"""

from __future__ import annotations

import base64
import hashlib
import json
import math
import os
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET
import zipfile
from html import escape
from pathlib import Path

from fontTools.pens.boundsPen import BoundsPen
from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.pens.transformPen import TransformPen
from fontTools.ttLib import TTFont
from PIL import Image, ImageChops
from PIL.IcoImagePlugin import IcoImageFile

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[3]
SOURCE = HERE / "source"
BG, INK, CYAN, PINK, PURPLE = "#080b18", "#f5f7ff", "#30e8ff", "#ff45cf", "#a66bff"
SHARP_PATH = os.environ.get("RUSH_SHARP_PATH", "sharp")
PNG_JOBS: list[dict] = []


def svg(name: str, width: float, height: float, content: str, title: str) -> Path:
    path = HERE / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width:g} {height:g}" '
        f'width="{width:g}" height="{height:g}" role="img" aria-labelledby="title">'
        f'<title id="title">{title}</title>{content}</svg>\n'
    )
    return path


def pngs(path: Path, widths: tuple[int, ...]) -> None:
    for width in widths:
        PNG_JOBS.append({"source": str(path), "output": str(path.with_name(f"{path.stem}-{width}.png")), "width": width})


def word_paths(font: TTFont, refined: bool = True) -> tuple[str, float, float]:
    glyphs, cmap = font.getGlyphSet(), font.getBestCmap()
    assert cmap is not None
    # Optical pairs R/U, U/S, S/H, preserving the established condensed italic.
    offsets = (0, 428, 868, 1268) if refined else (0, 419.43, 848.86, 1231.29)
    shear = 0.08 if refined else 0
    paths, boxes = [], []
    for letter, x in zip("RUSH", offsets):
        glyph = glyphs[cmap[ord(letter)]]
        matrix = (1, 0, shear, -1, x, 708)
        pen = SVGPathPen(glyphs)
        glyph.draw(TransformPen(pen, matrix))
        bounds = BoundsPen(glyphs)
        glyph.draw(TransformPen(bounds, matrix))
        boxes.append(bounds.bounds)
        paths.append(f'<path data-letter="{letter}" d="{pen.getCommands()}"/>')
    left, top = min(b[0] for b in boxes), min(b[1] for b in boxes)
    width, height = max(b[2] for b in boxes) - left, max(b[3] for b in boxes) - top
    return f'<g transform="translate({-left:g} {-top:g})">{"".join(paths)}</g>', width, height


def render() -> None:
    node = shutil.which("node")
    if node is None:
        raise RuntimeError("Node.js is required to render brand PNGs")
    subprocess.run([node, "-e", """
const fs = require('fs');
const sharp = require(process.argv[1]);
const jobs = JSON.parse(fs.readFileSync(0, 'utf8'));
(async () => {
  for (const job of jobs) {
    await sharp(job.source, {density: 288}).resize({width: job.width}).png().toFile(job.output);
  }
})().catch(error => {console.error(error); process.exit(1)});
""", str(SHARP_PATH)], input=json.dumps(PNG_JOBS), text=True, check=True)


def outline_text(font: TTFont, text: str, x: float, y: float, size: float,
                 color: str = INK, tracking: float = 0, anchor: str = "start") -> str:
    glyphs, cmap = font.getGlyphSet(), font.getBestCmap()
    assert cmap is not None
    units_per_em = getattr(font["head"], "unitsPerEm", None)
    assert isinstance(units_per_em, int) and units_per_em > 0
    scale = size / units_per_em
    width = sum(font["hmtx"][cmap[ord(c)]][0] * scale for c in text) + tracking * (len(text) - 1)
    x -= width / 2 if anchor == "middle" else 0
    paths = []
    for char in text:
        name = cmap[ord(char)]
        pen = SVGPathPen(glyphs)
        glyphs[name].draw(TransformPen(pen, (scale, 0, 0, -scale, x, y)))
        if pen.getCommands():
            paths.append(f'<path d="{pen.getCommands()}"/>')
        x += font["hmtx"][name][0] * scale + tracking
    return f'<g fill="{color}" data-copy="{escape(text, quote=True)}">{"".join(paths)}</g>'


def build() -> None:
    SOURCE.mkdir(exist_ok=True)
    originals = REPO / "research/dashboard-prototype/assets"
    for source, name in [(originals / "rush-mark.svg", "rush-mark-original.svg"),
                         (originals / "fonts/BarlowCondensed-BoldItalic.woff2", "BarlowCondensed-BoldItalic.woff2"),
                         (originals / "fonts/Barlow-OFL.txt", "Barlow-OFL.txt"),
                         (originals / "fonts/IBMPlexSans-Medium.woff2", "IBMPlexSans-Medium.woff2"),
                         (originals / "fonts/IBMPlexMono-Regular.woff2", "IBMPlexMono-Regular.woff2"),
                         (originals / "fonts/PlexSans-LICENSE.txt", "PlexSans-LICENSE.txt"),
                         (originals / "fonts/PlexMono-LICENSE.txt", "PlexMono-LICENSE.txt")]:
        target = SOURCE / name
        if not target.exists():
            shutil.copyfile(source, target)
    font = TTFont(SOURCE / "BarlowCondensed-BoldItalic.woff2")
    word, w, h = word_paths(font)
    original, ow, _ = word_paths(font, False)
    mark_root = ET.fromstring((SOURCE / "rush-mark-original.svg").read_text())
    mark = "".join(ET.tostring(c, encoding="unicode") for c in mark_root if not c.tag.endswith("title"))

    def bottle(x: float, y: float, height: float, monochrome: str | None = None) -> str:
        if monochrome:
            # Inherit original silhouette and bolt; eliminate gradients for true one-ink use.
            body = (f'<path d="M24 17V23L14 34C12.7 35.5 12 37.4 12 39.4V68C12 73 15.8 77 21 77H43C48.2 77 52 73 52 68V39.4C52 37.4 51.3 35.5 50 34L40 23V17" fill="none" stroke="{monochrome}" stroke-width="3" stroke-linejoin="round"/>'
                    f'<rect x="22" y="7" width="20" height="11" rx="2" fill="{monochrome}"/>'
                    f'<path d="M35 27L18 49H29L23 70L49 40H36L43 27H35Z" fill="{monochrome}"/>')
        else:
            body = mark
        return f'<g transform="translate({x:g} {y:g}) scale({height / 84:g})">{body}</g>'

    body_font = TTFont(SOURCE / "IBMPlexSans-Medium.woff2")
    mono_font = TTFont(SOURCE / "IBMPlexMono-Regular.woff2")
    artwork = base64.b64encode((SOURCE / "rush-campaign-art.png").read_bytes()).decode("ascii")
    layouts = [
        ("website-hero", 2400, 1350, (128,88,150), (128,385,30), (128,603,230,220), (128,970,36,55), (128,1220,700,25)),
        ("github-hero", 1280, 640, (56,38,80), (56,206,16), (56,323,118,112), (56,502,20,32), (56,600,204,16)),
        ("website-hero-mobile", 1080, 1440, (72,64,116), (72,310,26), (72,470,178,170), (72,733,34,49), (72,1350,325,29)),
    ]
    for name, width, height, brand, eyebrow, headline, supporting, footer in layouts:
        bx, by, bh = brand
        mobile = "mobile" in name
        content = '<defs><linearGradient id="hero-bottom" x1="0" y1="0" x2="0" y2="1"><stop stop-color="#080b18" stop-opacity="0"/><stop offset="1" stop-color="#080b18"/></linearGradient><linearGradient id="hero-top" x1="0" y1="0" x2="0" y2="1"><stop stop-color="#080b18"/><stop offset="1" stop-color="#080b18" stop-opacity="0"/></linearGradient></defs>'
        content += f'<rect width="{width}" height="{height}" fill="{BG}"/>'
        if mobile:
            content += f'<svg x="0" y="820" width="1080" height="470" viewBox="740 130 932 610" preserveAspectRatio="xMidYMid slice"><image width="1672" height="941" href="data:image/png;base64,{artwork}"/></svg>'
            content += '<rect y="820" width="1080" height="100" fill="url(#hero-top)"/>'
        else:
            content += f'<image width="{width}" height="{height}" preserveAspectRatio="xMidYMid slice" href="data:image/png;base64,{artwork}"/>'
        content += f'<rect y="{height*.81:g}" width="{width}" height="{height*.19:g}" fill="url(#hero-bottom)"/>'
        brand_mark = bottle(bx, by, bh).replace("rush-glass", "hero-brand-glass").replace("rush-charge", "hero-brand-charge")
        content += brand_mark + f'<g fill="{INK}" data-wordmark="rush-v2" transform="translate({bx+bh*64/84+bh*.16:g} {by+bh*.08:g}) scale({bh*.84/h:g})">{word}</g>'
        content += outline_text(mono_font, "GIVE YOUR AGENTS", *eyebrow, color=CYAN, tracking=2)
        tx, ty, size, leading = headline
        for i, line in enumerate(("MORE THAN", "A PROMPT.")):
            content += outline_text(font, line, tx, ty + i*leading, size)
        sx, sy, small, step = supporting
        for i, line in enumerate(("Project memory. Relevant context.", "Control over what happens next.")):
            content += outline_text(body_font, line, sx, sy+i*step, small, "#c1cbe0")
        fx, fy, gap, small = footer
        for i, (label, detail, color) in enumerate(zip(("MEMORY", "CONTEXT", "CONTROL"), ("Carry decisions forward.", "Find the code that matters.", "Set execution boundaries."), (PURPLE, CYAN, PINK))):
            content += outline_text(mono_font, label, fx+i*gap, fy, small, color, 1)
            if name == "website-hero":
                content += outline_text(body_font, detail, fx+i*gap, fy+47, 30, "#c1cbe0")
        path = svg(f"hero/{name}.svg", width, height, content, "Rush — give your agents more than a prompt. Project memory, relevant context, and execution control.")
        pngs(path, (1200,2400) if name == "website-hero" else (width,))

    colors = {"light": INK, "dark": BG, "cyan": CYAN, "mono-white": "#ffffff", "mono-black": "#000000"}
    pad = 72
    for name, color in colors.items():
        path = svg(f"wordmark/rush-wordmark-{name}.svg", w + 2 * pad, h + 2 * pad,
                   f'<g fill="{color}" transform="translate({pad} {pad})">{word}</g>', "Rush")
        pngs(path, (256, 512, 1024, 2048))
    mark_h, gap = h * 1.16, 100
    mark_w = mark_h * 64 / 84
    for name in ("light", "dark", "mono-white", "mono-black"):
        color = colors[name]
        mono = color if name.startswith("mono") else None
        contents = bottle(pad, pad, mark_h, mono) + f'<g fill="{color}" transform="translate({pad + mark_w + gap:g} {pad + (mark_h-h)/2:g})">{word}</g>'
        path = svg(f"lockup/rush-lockup-{name}.svg", w + mark_w + gap + 2 * pad, mark_h + 2 * pad, contents, "Rush — lightning in a bottle")
        pngs(path, (512, 1024, 2048))
        stack_h = 760
        stack_w = stack_h * 64 / 84
        contents = bottle((w + 2 * pad - stack_w) / 2, pad, stack_h, mono) + f'<g fill="{color}" transform="translate({pad} {pad + stack_h + 80})">{word}</g>'
        path = svg(f"stacked/rush-stacked-{name}.svg", w + 2 * pad, 2 * pad + stack_h + 80 + h, contents, "Rush — lightning in a bottle")
        pngs(path, (256, 512, 1024))

    for name, height in [("rush-app", 800), ("rush-app-maskable", 680)]:
        app_width = height * 64 / 84
        path = svg(f"app/{name}.svg", 1024, 1024, f'<rect width="1024" height="1024" fill="{BG}"/>' + bottle((1024-app_width)/2, (1024-height)/2, height), "Rush application icon")
        pngs(path, (192, 512) if "maskable" in name else (16, 24, 32, 48, 64, 128, 180, 192, 256, 512, 1024))
    path = svg("web/favicon.svg", 84, 84, bottle(10, 0, 84), "Rush")
    pngs(path, (16, 32, 48))

    for name, width, height in [("github-preview", 1280, 640), ("website-social", 1200, 630)]:
        scale = width * .53 / w
        logo_h = h * scale
        bottle_h = logo_h * 1.16
        bottle_w = bottle_h * 64 / 84
        group_w = bottle_w + 40 + w * scale
        x, y = (width - group_w) / 2, height * .25
        content = f'<rect width="{width}" height="{height}" fill="{BG}"/>'
        content += bottle(x, y, bottle_h)
        content += f'<g fill="{INK}" transform="translate({x + bottle_w + 40:g} {y + (bottle_h-logo_h)/2:g}) scale({scale:g})">{word}</g>'
        path = svg(f"social/{name}.svg", width, height, content, "Rush — memory, context, and control for coding agents")
        pngs(path, (width,))

    # Before/after proof uses equal cap height and original CSS tracking as baseline.
    proof = f'<rect width="1440" height="1300" fill="{BG}"/>'
    for glyphs, label, gy in [(original, "CURRENT", 160), (word, "REFINED", 790)]:
        scale = 1080 / max(w, ow)
        proof += f'<text x="180" y="{gy-55}" fill="#b5c0d8" font-family="sans-serif" font-size="24" letter-spacing="5">{label}</text>'
        proof += f'<g fill="{INK}" transform="translate(180 {gy}) scale({scale:g})">{glyphs}</g>'
    path = svg("proof/wordmark-comparison.svg", 1440, 1300, proof, "Rush wordmark comparison: original above, refined below")
    pngs(path, (1440,))
    render()

    with Image.open(HERE / "web/favicon-48.png") as image:
        image.save(HERE / "web/favicon.ico", sizes=[(16,16),(32,32),(48,48)])
    with Image.open(HERE / "app/rush-app-1024.png") as image:
        image.save(HERE / "app/rush.ico", sizes=[(n,n) for n in (16,24,32,48,64,128,256)])
    iconset = HERE / "app/rush.iconset"
    iconset.mkdir(exist_ok=True)
    for size in (16, 32, 128, 256, 512):
        for multiplier in (1, 2):
            name = f"icon_{size}x{size}{'@2x' if multiplier == 2 else ''}.png"
            shutil.copyfile(HERE / f"app/rush-app-{size*multiplier}.png", iconset / name)
    subprocess.run(["iconutil", "-c", "icns", str(iconset), "-o", str(HERE / "app/rush.icns")], check=True)

    files = sorted(p for p in HERE.rglob("*") if p.is_file() and p.name not in ("manifest.json", "rush-wordmark-v2.zip") and "__pycache__" not in p.parts)
    manifest = {"wordmark": "RUSH", "revision": "v2", "palette": {"background": BG, "text": INK, "cyan": CYAN, "pink": PINK, "purple": PURPLE},
                "refinement": {"additional_shear": .08, "glyph_offsets": [0,428,868,1268]},
                "files": {str(p.relative_to(HERE)): hashlib.sha256(p.read_bytes()).hexdigest() for p in files}}
    (HERE / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    with zipfile.ZipFile(HERE / "rush-wordmark-v2.zip", "w", zipfile.ZIP_DEFLATED) as archive:
        for p in files + [HERE / "manifest.json"]:
            archive.write(p, p.relative_to(HERE))
    print(f"Exported {len(files)} files, manifest, and ZIP to {HERE}")


def check() -> None:
    image: Image.Image
    manifest = json.loads((HERE / "manifest.json").read_text())
    for name, digest in manifest["files"].items():
        assert hashlib.sha256((HERE / name).read_bytes()).hexdigest() == digest, name
        path = HERE / name
        if path.suffix == ".png":
            with Image.open(path) as image:
                image.verify()
            if path.stem.rsplit("-", 1)[-1].isdigit():
                assert Image.open(path).width == int(path.stem.rsplit("-", 1)[-1]), name
        elif path.suffix == ".svg":
            ET.parse(path)
    for path in (HERE / "wordmark").glob("*.svg"):
        root = ET.parse(path).getroot()
        assert not any(e.tag.endswith("text") or e.tag.endswith("image") for e in root.iter()), path
        assert [e.attrib.get("data-letter") for e in root.iter() if "data-letter" in e.attrib] == list("RUSH"), path
        image = Image.open(path.with_name(f"{path.stem}-512.png")).convert("RGBA")
        alpha = image.getchannel("A")
        assert alpha.getpixel((0, 0)) == 0 and alpha.getextrema() == (0,255), path
        bbox = alpha.getbbox()
        assert bbox is not None, path
        left, top, right, bottom = bbox
        assert left > 0 and top > 0 and right < image.width and bottom < image.height, path
    mono = Image.open(HERE / "wordmark/rush-wordmark-mono-black-512.png").convert("RGBA")
    assert mono.convert("RGB").getextrema() == ((0,0),(0,0),(0,0)), "monochrome must be one ink"
    for icon_path, sizes in ((HERE / "web/favicon.ico", {(16,16),(32,32),(48,48)}),
                             (HERE / "app/rush.ico", {(n,n) for n in (16,24,32,48,64,128,256)})):
        image = Image.open(icon_path)
        assert isinstance(image, IcoImageFile)
        assert image.ico.sizes() == sizes
    assert Image.open(HERE / "app/rush.icns").size == (1024,1024)
    maskable = Image.open(HERE / "app/rush-app-maskable-512.png").convert("RGB")
    base = Image.new("RGB", maskable.size, BG)
    delta = ImageChops.difference(maskable, base)
    for y in range(512):
        for x in range(512):
            if math.hypot(x-256,y-256) > 204.8:
                pixel = delta.getpixel((x,y))
                assert isinstance(pixel, tuple)
                assert max(pixel) <= 1, "maskable content outside safe circle"
    for name, expected in [("github-preview",(1280,640)),("website-social",(1200,630))]:
        assert Image.open(HERE / f"social/{name}-{expected[0]}.png").size == expected
    wordmark_paths = [e.attrib["d"] for e in ET.parse(HERE / "wordmark/rush-wordmark-light.svg").iter() if "data-letter" in e.attrib]
    for name, dimensions in [("website-hero",(2400,1350)),("website-hero-mobile",(1080,1440)),("github-hero",(1280,640))]:
        root = ET.parse(HERE / f"hero/{name}.svg").getroot()
        assert not any(e.tag.endswith("text") for e in root.iter()), name
        backgrounds = [e for e in root.iter() if e.tag.endswith("image")]
        assert len(backgrounds) == 1, name
        assert base64.b64decode(backgrounds[0].attrib["href"].split(",",1)[1]) == (SOURCE / "rush-campaign-art.png").read_bytes(), name
        assert [e.attrib["d"] for e in root.iter() if "data-letter" in e.attrib] == wordmark_paths, name
        ids = [e.attrib["id"] for e in root.iter() if "id" in e.attrib]
        assert len(ids) == len(set(ids)), name
        copy = [e.attrib["data-copy"] for e in root.iter() if "data-copy" in e.attrib]
        assert all(line in copy for line in ("GIVE YOUR AGENTS","MORE THAN","A PROMPT.","Project memory. Relevant context.","Control over what happens next.","MEMORY","CONTEXT","CONTROL")), name
        image = Image.open(HERE / f"hero/{name}-{dimensions[0]}.png").convert("RGBA")
        assert image.size == dimensions and image.getchannel("A").getextrema() == (255,255), name
    with zipfile.ZipFile(HERE / "rush-wordmark-v2.zip") as archive:
        assert archive.testzip() is None
        assert set(archive.namelist()) == set(manifest["files"]) | {"manifest.json"}
    print("PASS: exact RUSH outlines, transparent unclipped wordmarks, one-ink variant, ICO sizes, ICNS, maskable safe area, social/hero dimensions, outlined hero copy, original wordmark paths, hashes, ZIP contents")


if __name__ == "__main__":
    check() if sys.argv[1:] == ["--check"] else build()
