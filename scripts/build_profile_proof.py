#!/usr/bin/env python3
"""Rebuild ``profile/assets/proof-e2e.png`` — the org profile's visual proof.

WHY THIS IS A SCRIPT AND NOT A HAND-MADE IMAGE. The profile README claims one
thing visually: that a researcher can go from raw data to a compiled manuscript
with SciTeX, without leaving one project. An image asserting that is worth
nothing unless a reader can check where it came from, so every pixel is a crop
of something that already exists, and every crop rectangle is written down
here:

  panel 1  SciTeX Hub, a project's files      scitex-hub demo pipeline, 2026-09-14
  panel 2  SciTeX Hub, Writer + compiled PDF  scitex-hub demo pipeline, 2026-09-14
  panel 3  SciTeX Hub, Scholar library        scitex-hub docs/images/, 2026-03-08
  panel 4  Figures 1-2 of the compiled        automated-research-demo, committed PDF
           manuscript from a real run

The three UI panels are frames of the Hub's own narrated demo recording — a
REAL development build signed in as a throwaway demo account, not a mockup and
not a production screenshot. The panel sources, their commits, dates and the
identifiers cropped out of each are recorded in
``profile/assets/ASSET-MANIFEST.md``; the Hub scenario files that generated the
frames are ``scripts/demo_videos/scenarios/*.yaml`` (tracked in scitex-hub).

IDENTIFIERS ARE CROPPED, NOT BLURRED, WHEREVER THE CROP COULD BE MOVED: the
browser chrome, the owner/project breadcrumb and the account avatar are outside
the crop rectangles below. What could not be cropped away — the tutorial
overlay boxes burned into the recording — is painted out with the panel's own
background colour, sampled at run time rather than guessed.

The Hub frames are read from a local scitex-hub checkout (``--hub-src``), not
downloaded: ``media/videos/demos/`` is untracked there, so there is no raw URL
to fetch. Panel 4 is fetched, because that repo commits its PDFs.

Usage:  python scripts/build_profile_proof.py [output.png] [--hub-src DIR]
Needs:  Pillow, PyMuPDF (``uv pip install pillow pymupdf``), network.
"""

from __future__ import annotations

import io
import sys
import urllib.request
from pathlib import Path
from typing import cast

from PIL import Image, ImageDraw, ImageFont

_DEMO_RAW = "https://raw.githubusercontent.com/scitex-ai/automated-research-demo/main"
_MANUSCRIPT_PDF = f"{_DEMO_RAW}/scitex/writer/paper/01_manuscript/manuscript.pdf"

_HUB_DEFAULT = Path("/home/ywatanabe/proj/scitex-hub")

#: (kind, path-relative-to-hub-or-url, crop rectangle in source pixels,
#:  rectangles to paint out with the sampled background colour)
#:
#: Rectangles come from the images' own layout, measured with PyMuPDF block
#: boxes for the PDF page and by reading the frames' bounding boxes for the UI
#: shots — an eyeballed box cut the figure axes and half the abstract earlier.
_PANELS: list[dict] = [
    {
        "name": "project files",
        "src": "media/videos/demos/projects-2026-09-14-thumbnail.png",
        "crop": (74, 250, 1197, 620),
        # the recording's tutorial callout, painted out; it covers the
        # "last commit" columns only, so every file name stays visible
        "paint": ((338, 539, 935, 614),),
    },
    {
        "name": "writer + compiled pdf",
        "src": "media/videos/demos/writer-2026-09-14-thumbnail.png",
        "crop": (88, 78, 1240, 650),
        # "The PDF of your section appears. Use the download button to save it."
        "paint": ((410, 548, 870, 624),),
    },
    {
        "name": "scholar library",
        "src": "docs/images/screenshot-scholar.png",
        # from y=200 the recording's tab row (and its library count) is gone;
        # x from 680 drops the file tree and console rail, which carry the
        # account and project names
        "crop": (680, 200, 1580, 640),
        "paint": (),
    },
    {
        "name": "figures from the run",
        "src": _MANUSCRIPT_PDF,
        # page 19 at 140 dpi: Figure 1 embed (253,378)-(933,536), Figure 2 below
        "crop": (200, 360, 990, 790),
        "paint": (),
    },
]

_PDF_PAGE = 19  # 1-indexed
_PDF_DPI = 140
_PDF_PAGE_SIZE = (1190, 1540)

_WIDTH = 900
_GAP = 16
_PAD = 14
_BORDER = (208, 215, 222)  # GitHub --border-default
_BADGE_BG = (11, 114, 133)  # the teal this repo's badges already use
_FONT_DIR = "/usr/share/fonts/truetype/liberation"
#: Wrapped to fit 900 px at _FOOTER_SIZE; the first version ran off the right
#: edge and was silently sliced, which is exactly the kind of half-statement
#: this footer exists to avoid.
_FOOTER_LINES = (
    "SciTeX Hub — development build, demo account, identifiers cropped.",
    "Sources, commits and crop rectangles: profile/assets/ASSET-MANIFEST.md",
)
_FOOTER_SIZE = 22


def _fetch(url: str) -> bytes:
    with urllib.request.urlopen(url, timeout=60) as fh:
        return fh.read()


def _render_pdf_page(pdf_bytes: bytes, page: int, dpi: int) -> Image.Image:
    import pymupdf  # only this panel needs a PDF stack

    doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")
    pix = doc[page - 1].get_pixmap(dpi=dpi)
    return Image.open(io.BytesIO(pix.tobytes("png"))).convert("RGB")


def _rgb(im: Image.Image, xy: tuple[int, int]) -> tuple[int, int, int]:
    """Pillow types ``getpixel`` as a union; narrow it at the one call site."""
    return cast("tuple[int, int, int]", im.convert("RGB").getpixel(xy))


def _background(im: Image.Image, rect: tuple[int, int, int, int]) -> tuple[int, int, int]:
    """Sample the panel's own background just left of ``rect``, same row.

    Sampled rather than hardcoded: the four frames have three different dark
    backgrounds, and a hardcoded fill would leave a visible patch on two of
    them.
    """
    x0, y0, _, y1 = rect
    y = (y0 + y1) // 2
    for x in range(x0 - 4, max(x0 - 80, 0), -4):
        r, g, b = _rgb(im, (x, y))
        if abs(r - g) < 12 and abs(g - b) < 12:  # a neutral, i.e. not a glyph edge
            return (r, g, b)
    return _rgb(im, (max(x0 - 4, 0), y))


def _panel(source: Image.Image, crop, paint) -> Image.Image:
    im = source.crop(crop)
    draw = ImageDraw.Draw(im)
    for rect in paint:
        x0, y0, x1, y1 = rect
        rel = (x0 - crop[0], y0 - crop[1], x1 - crop[0], y1 - crop[1])
        draw.rectangle(rel, fill=_background(source, rect))
    return im


def _fit(im: Image.Image, width: int) -> Image.Image:
    return im.resize((width, round(im.height * width / im.width)), Image.Resampling.LANCZOS)


def _posterise(im: Image.Image, levels: int) -> Image.Image:
    """Snap each channel to ``levels`` values via a 256-entry LUT.

    A lookup table rather than a callable: Pillow types the callable form as
    taking a union, so a round() inside it cannot be checked.
    """
    step = 255 // (levels - 1)
    lut = [min(255, round(value / step) * step) for value in range(256)]
    return im.point(lut)


def _load_panel(spec: dict, hub: Path) -> Image.Image:
    if spec["src"].endswith(".pdf"):  # checked FIRST: the PDF is also a URL
        page = _render_pdf_page(_fetch(spec["src"]), _PDF_PAGE, _PDF_DPI)
        if page.size != _PDF_PAGE_SIZE:
            raise SystemExit(
                f"manuscript page rendered {page.size}, expected {_PDF_PAGE_SIZE} — "
                "the crop rectangles are pixels of THAT rendering"
            )
        return page
    if spec["src"].startswith("http"):
        return Image.open(io.BytesIO(_fetch(spec["src"]))).convert("RGB")
    path = hub / spec["src"]
    if not path.exists():
        raise SystemExit(
            f"{path} is missing — pass --hub-src pointing at a scitex-hub checkout "
            "(the demo frames live under media/videos/demos/, which is not committed)"
        )
    return Image.open(path).convert("RGB")


def build(out: Path, hub: Path) -> Path:
    panels = [_fit(_panel(_load_panel(spec, hub), spec["crop"], spec["paint"]), _WIDTH - 2 * _PAD)
              for spec in _PANELS]

    footer = (_FOOTER_SIZE + 6) * len(_FOOTER_LINES) + 4
    height = (
        _PAD
        + sum(p.height for p in panels)
        + _GAP * (len(panels) - 1)
        + _PAD
        + footer
    )
    canvas = Image.new("RGB", (_WIDTH, height), (255, 255, 255))
    draw = ImageDraw.Draw(canvas)

    y = _PAD
    for i, panel in enumerate(panels, start=1):
        canvas.paste(panel, (_PAD, y))
        draw.rectangle(
            [_PAD - 1, y - 1, _PAD + panel.width, y + panel.height], outline=_BORDER, width=1
        )
        bx, by, size = _PAD + 8, y + 8, 40
        draw.rounded_rectangle([bx, by, bx + size, by + size], radius=8, fill=_BADGE_BG)
        label = str(i)
        font = ImageFont.truetype(f"{_FONT_DIR}/LiberationSans-Bold.ttf", 30)
        draw.text(
            (bx + (size - draw.textlength(label, font=font)) / 2, by + size / 2 - 20),
            label,
            font=font,
            fill=(255, 255, 255),
        )
        y += panel.height + _GAP

    # The composite travels: it will be copied into slides and chats that carry
    # none of the README's context. So the honest label is IN the image.
    small = ImageFont.truetype(f"{_FONT_DIR}/LiberationSans-Regular.ttf", _FOOTER_SIZE)
    remaining = _WIDTH - 2 * _PAD
    for i, line in enumerate(_FOOTER_LINES):
        if draw.textlength(line, font=small) > remaining:
            raise SystemExit(
                f"footer line {i} is {draw.textlength(line, font=small):.0f} px wide, "
                f"only {remaining} px available — it would be sliced"
            )
        draw.text((_PAD, y + 4 + i * (_FOOTER_SIZE + 6)), line, font=small, fill=(87, 96, 106))

    # One global palette. The UI frames are flat colours and quantise without
    # visible loss; the 4-level posterise of the paper panel is what keeps the
    # file small enough for a phone to load without thinking about it.
    paper_cut = _PAD + sum(p.height for p in panels[:-1]) + _GAP * (len(panels) - 1)
    text = _posterise(canvas.crop((0, paper_cut, _WIDTH, y)).convert("L"), levels=4).convert("RGB")
    canvas.paste(text, (0, paper_cut))
    canvas = canvas.convert("P", palette=Image.Palette.ADAPTIVE, colors=128, dither=Image.Dither.NONE)

    out.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(out, optimize=True)
    return out


def main() -> int:
    args = [a for a in sys.argv[1:]]
    hub = _HUB_DEFAULT
    if "--hub-src" in args:
        i = args.index("--hub-src")
        hub = Path(args[i + 1])
        del args[i : i + 2]
    default_out = Path(__file__).resolve().parents[1] / "profile" / "assets" / "proof-e2e.png"
    out = Path(args[0]) if args else default_out
    written = build(out, hub)
    print(f"{written} {written.stat().st_size} bytes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
