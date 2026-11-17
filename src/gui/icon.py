"""The app mark: one renderer for the favicon now and the tray icon later.

The mark reads as versus clips turned into a video: a video frame with film sprocket notches,
a gold play triangle, and two pink slashes crossing behind it like a versus X. Every coordinate
is a fraction of the tile (0..1); the art is drawn at 4x and downsampled, so edges stay clean.
Colours come from tokens.py; this file holds no colour literal of its own.
"""
import base64
import io

from PIL import Image, ImageDraw

from gui import tokens

SUPERSAMPLE = 4
RESAMPLE = Image.Resampling.LANCZOS


def _rgb(hex_text):
    """Turn a token's hex string into an (r, g, b) tuple."""
    return tuple(int(hex_text[i:i + 2], 16) for i in (1, 3, 5))


def _opaque(hex_text):
    return _rgb(hex_text) + (255,)


def render(size=64):
    """Return the mark as an RGBA image of size x size pixels."""
    big = size * SUPERSAMPLE

    def at(x, y):
        return (x * big, y * big)

    def box(x0, y0, x1, y1):
        return [*at(x0, y0), *at(x1, y1)]

    img = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Tile: full size, rounded, page ground colour.
    draw.rounded_rectangle([0, 0, big - 1, big - 1], radius=0.2 * big, fill=_opaque(tokens.GROUND))

    # Versus slashes behind the frame, round caps drawn as end discs.
    width = 0.11 * big
    for (x0, y0), (x1, y1) in (((0.18, 0.82), (0.82, 0.18)), ((0.18, 0.18), (0.82, 0.82))):
        draw.line([at(x0, y0), at(x1, y1)], fill=_opaque(tokens.TIER_HEXA), width=round(width))
        for cx, cy in ((x0, y0), (x1, y1)):
            cx, cy = cx * big, cy * big
            draw.ellipse([cx - width / 2, cy - width / 2, cx + width / 2, cy + width / 2],
                         fill=_opaque(tokens.TIER_HEXA))

    # Video frame: panel fill with a text-coloured outline.
    draw.rounded_rectangle(box(0.14, 0.26, 0.86, 0.74), radius=0.06 * big,
                           fill=_opaque(tokens.PANEL), outline=_opaque(tokens.TEXT),
                           width=round(0.04 * big))

    # Sprocket notches sit on the frame's top and bottom inner edge.
    half = 0.03
    for cx in (0.30, 0.70):
        for cy in (0.31, 0.69):
            draw.rectangle(box(cx - half, cy - half, cx + half, cy + half), fill=_opaque(tokens.GROUND))

    # Gold play triangle.
    draw.polygon([at(0.42, 0.36), at(0.66, 0.50), at(0.42, 0.64)], fill=_opaque(tokens.TIER_QUAD))

    return img.resize((size, size), RESAMPLE)


def png_bytes(size=64):
    """The mark as PNG file bytes."""
    buf = io.BytesIO()
    render(size).save(buf, format="PNG")
    return buf.getvalue()


def data_url(size=64):
    """The mark as a data: URL the page can use as its favicon."""
    return "data:image/png;base64," + base64.b64encode(png_bytes(size)).decode("ascii")
