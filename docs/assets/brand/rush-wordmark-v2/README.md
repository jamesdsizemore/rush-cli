# Rush wordmark v2 — web and application kit

Refined **RUSH** retains Barlow Condensed Bold Italic and the existing bottle/bolt identity. Optical spacing is adjusted per pair, and an additional 0.08 shear gives the lettering a stronger, consistent forward lean. The master is crisp, flat vector artwork: no glow, embedded bitmap, font download, or trademark symbol.

Open `preview.html` to compare the refinement and inspect every family. `proof/wordmark-comparison-1440.png` shows current CSS lettering above the refined outlines at the same cap height. `rush-wordmark-v2.zip` contains this entire kit, including source, license, and exporter.

## Choose an asset

| Use | File | Notes |
| --- | --- | --- |
| Website/app wordmark on dark surfaces | `wordmark/rush-wordmark-light.svg` | Off-white, transparent background. |
| Wordmark on light surfaces | `wordmark/rush-wordmark-dark.svg` | Deep navy, transparent background. |
| Accent wordmark | `wordmark/rush-wordmark-cyan.svg` | Cyan; intended for dark surfaces. |
| Single-color wordmark | `wordmark/rush-wordmark-mono-white.svg`, `wordmark/rush-wordmark-mono-black.svg` | White or black paths only. |
| Bottle beside wordmark | `lockup/rush-lockup-*.svg` | Color light/dark and monochrome white/black. |
| Bottle above wordmark | `stacked/rush-stacked-*.svg` | Same four color versions, compact placements. |
| Browser tab | `web/favicon.svg`, `web/favicon.ico` | Bottle mark; ICO contains 16, 32, 48 px. |
| Apple touch icon | `app/rush-app-180.png` | Opaque square; platform supplies mask. |
| Web app/PWA | `app/rush-app-192.png`, `app/rush-app-512.png` | Ordinary icon family. |
| Maskable web app icon | `app/rush-app-maskable-192.png`, `app/rush-app-maskable-512.png` | Bottle fits inside central 80% safe circle. |
| Windows application | `app/rush.ico` | 16, 24, 32, 48, 64, 128, 256 px. |
| macOS application | `app/rush.icns`, `app/rush.iconset/` | 16–1024 px, including Retina sizes. |
| Linux application / other platforms | `app/rush-app-512.png`, `app/rush-app-1024.png` | Opaque square PNG plus scalable `app/rush-app.svg`. |
| GitHub social preview | `social/github-preview-1280.png` | 1280 × 640, opaque; matching SVG included. |
| Website link sharing | `social/website-social-1200.png` | 1200 × 630, opaque; matching SVG included. |
| Website product hero | `hero/website-hero.svg`, `hero/website-hero-2400.png` | 2400 × 1350; 1200 × 675 PNG also included. |
| Mobile website hero | `hero/website-hero-mobile.svg`, `hero/website-hero-mobile-1080.png` | 1080 × 1440; composition rearranged for narrow screens. |
| GitHub product hero / README | `hero/github-hero.svg`, `hero/github-hero-1280.png` | 1280 × 640, opaque, outlined copy and refined wordmark. |

All production SVG lettering is outlined. Wordmark PNGs have transparent backgrounds and widths 256, 512, 1024, 2048 px. Horizontal lockup PNGs are 512, 1024, 2048 px wide; stacked lockups are 256, 512, 1024 px wide. Application PNGs cover 16, 24, 32, 48, 64, 128, 180, 192, 256, 512, 1024 px. File suffix gives pixel width; aspect ratio is preserved.

Use SVG for sharp website/application UI. Choose a raster at least twice its displayed pixel width when PNG is required. Use the bottle-only app icon at small sizes; the four-letter wordmark is not a favicon. Keep artwork proportions and included clear space. Do not add glow, stretch letters, or put white/cyan artwork on white backgrounds.

## Web examples

After copying `wordmark/`, `web/`, `app/`, and `social/` into your site's `/brand/` directory:

```html
<img src="/brand/wordmark/rush-wordmark-light.svg" alt="Rush" width="144">
<link rel="icon" href="/brand/web/favicon.svg" type="image/svg+xml">
<link rel="icon" href="/brand/web/favicon.ico" sizes="16x16 32x32 48x48">
<link rel="apple-touch-icon" href="/brand/app/rush-app-180.png" sizes="180x180">
<meta property="og:image" content="https://YOUR-DOMAIN/brand/social/website-social-1200.png">
```

`YOUR-DOMAIN` is your deployment domain. For a PWA, add these entries to its **existing** manifest's `icons` array:

```json
[
  {"src":"/brand/app/rush-app-192.png","sizes":"192x192","type":"image/png","purpose":"any"},
  {"src":"/brand/app/rush-app-512.png","sizes":"512x512","type":"image/png","purpose":"any"},
  {"src":"/brand/app/rush-app-maskable-192.png","sizes":"192x192","type":"image/png","purpose":"maskable"},
  {"src":"/brand/app/rush-app-maskable-512.png","sizes":"512x512","type":"image/png","purpose":"maskable"}
]
```

GitHub README example, when committed at this kit's current location:

```markdown
<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/assets/brand/rush-wordmark-v2/lockup/rush-lockup-light.svg">
  <img src="docs/assets/brand/rush-wordmark-v2/lockup/rush-lockup-dark.svg" alt="Rush" width="360">
</picture>
```

The root README uses `hero/github-hero-1280.png` and leads with “Give your agents more than a prompt.” Project memory, relevant context, and execution control substantiate that hook. The website hero assets are supplied for integration; dashboard and packaging configuration retain their existing artwork. This package does not claim a native application or PWA exists.

## Product hero

The campaign pairs “Give your agents more than a prompt” with a sculptural glass lightning bolt and directional cyan/pink light. Supporting copy states the value: project memory, relevant context, and control over what happens next. Three benefit labels connect that promise to memory, context, and control; code quality remains part of the README's supporting workflow. This is conceptual brand artwork, with no simulated telemetry or dashboard claims. The rejected cyan underline is absent. Existing logo-only sharing images remain available.

All hero copy is outlined from the existing local Barlow Condensed Bold Italic, IBM Plex Sans Medium, and IBM Plex Mono fonts. The refined RUSH paths are reused exactly. Each SVG embeds the generated raster artwork from `source/rush-campaign-art.png`; typography remains vector, while the artwork has a fixed native resolution of 1672 × 941. No fonts, external images, or network requests are needed to render. Use PNG for GitHub. The mobile composition gives artwork a separate crop below the headline.

Responsive website example, after copying `hero/` into `/brand/`:

```html
<picture>
  <source media="(max-width: 640px)" srcset="/brand/hero/website-hero-mobile.svg">
  <img src="/brand/hero/website-hero.svg" alt="Rush — give your agents more than a prompt. Project memory, relevant context, and execution control." style="display:block;width:100%;height:auto">
</picture>
```

## Source and reproduction

`source/BarlowCondensed-BoldItalic.woff2` and `source/Barlow-OFL.txt` are unchanged copies from the local prototype. Barlow is Copyright 2017 The Barlow Project Authors, licensed under SIL Open Font License 1.1. `source/rush-mark-original.svg` preserves the original prototype bottle vector; the full-color lockups reuse it unchanged. Monochrome lockups retain its silhouette/bolt and remove color-dependent detail for one-ink reproduction. No modified font is distributed.

Hero reproduction also includes unchanged `source/IBMPlexSans-Medium.woff2`, `source/IBMPlexMono-Regular.woff2`, and their `PlexSans-LICENSE.txt` / `PlexMono-LICENSE.txt` SIL OFL notices. See the original local `SOURCES.md` for pinned upstream font provenance.

`source/rush-campaign-art.png` was generated with the built-in imagegen tool. `source/rush-campaign-prompt.md` records the complete generation prompt. Rebuilding reuses this saved artwork; it does not regenerate it or call an image API.

The brand brief is `research/dashboard-prototype/README.md:95`; original font provenance is `research/dashboard-prototype/assets/fonts/SOURCES.md`. Palette: navy `#080b18`, off-white `#f5f7ff`, cyan `#30e8ff`, pink `#ff45cf`, purple `#a66bff`. The original bottle retains its own gradient stops.

The exporter requires existing Python FontTools with WOFF2/Brotli support, Pillow, Node with sharp, and macOS `iconutil` for ICNS. It changes only files inside this kit. Existing source copies are retained on subsequent builds. If sharp is outside normal Node resolution, set `RUSH_SHARP_PATH` to its installed package path.

```sh
python3 build.py
python3 build.py --check
```

`--check` verifies actual exported outlines, PNG transparency and clipping, one-ink color, ICO contents, ICNS readability, maskable safe area, social dimensions, every recorded SHA-256, and exact ZIP membership. Expected result begins `PASS:`. It does not rewrite files or install dependencies. `manifest.json` records artifact hashes and refinement parameters.
