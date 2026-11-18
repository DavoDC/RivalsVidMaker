"""The app mark: one renderer for the favicon now and the tray icon later.

The mark is a gold tile with a slanted navy panel, and a gold play triangle cut by a KO slash.
Every coordinate is a fraction of the tile (0..1); the art is drawn at 4x and downsampled, so edges stay clean.
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

    def poly(points, colour):
        draw.polygon([(x * big, y * big) for x, y in points], fill=_opaque(colour))

    img = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Tile: full size, rounded, gold.
    draw.rounded_rectangle([0, 0, big - 1, big - 1], radius=0.18 * big, fill=_opaque(tokens.TIER_QUAD))

    # Slanted navy panel.
    poly(((0.22, 0.12), (0.92, 0.12), (0.78, 0.88), (0.08, 0.88)), tokens.GROUND)

    # Gold play triangle.
    poly(((0.36, 0.30), (0.70, 0.50), (0.36, 0.70)), tokens.TIER_QUAD)

    # KO slash through the triangle, in navy.
    poly(((0.28, 0.63), (0.76, 0.35), (0.78, 0.41), (0.30, 0.69)), tokens.GROUND)

    return img.resize((size, size), RESAMPLE)


def png_bytes(size=64):
    """The mark as PNG file bytes."""
    buf = io.BytesIO()
    render(size).save(buf, format="PNG")
    return buf.getvalue()


def data_url(size=64):
    """The mark as a data: URL the page can use as its favicon."""
    return "data:image/png;base64," + base64.b64encode(png_bytes(size)).decode("ascii")
