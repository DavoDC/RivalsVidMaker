"""The app mark (task 52): one renderer in src/gui/icon.py feeds the favicon, and the tray later.

Nothing here opens a window or touches config; the preview script writes only into tmp_path.
"""
import base64
import re
import subprocess
import sys
from pathlib import Path

from PIL import Image

from gui import icon, tokens

REPO_ROOT = Path(__file__).resolve().parents[2]
ICON_SRC = REPO_ROOT / "src" / "gui" / "icon.py"
PREVIEW = REPO_ROOT / "scripts" / "preview_icon.py"

HEX_LITERAL = re.compile(r"#(?:[0-9a-fA-F]{8}|[0-9a-fA-F]{6}|[0-9a-fA-F]{3})\b(?![-\w])")
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


def _rgb(hex_text):
    return tuple(int(hex_text[i:i + 2], 16) for i in (1, 3, 5))


def _near(pixel, target, tolerance=40):
    return all(abs(pixel[i] - target[i]) <= tolerance for i in range(3))


def test_render_is_a_64_pixel_rgba_image():
    img = icon.render(64)
    assert img.size == (64, 64)
    assert img.mode == "RGBA"


def test_tile_pixel_at_the_left_edge_is_gold():
    img = icon.render(64)
    assert _near(img.getpixel((2, 32)), _rgb(tokens.TIER_QUAD), tolerance=8)


def test_panel_pixel_above_the_centre_is_navy_ground():
    img = icon.render(64)
    assert _near(img.getpixel((32, 16)), _rgb(tokens.GROUND), tolerance=8)


def test_triangle_pixel_below_the_slash_is_gold():
    img = icon.render(64)
    assert _near(img.getpixel((24, 43)), _rgb(tokens.TIER_QUAD), tolerance=8)


def test_no_pixel_is_the_old_hexa_pink():
    img = icon.render(64)
    pink = _rgb(tokens.TIER_HEXA)
    pixels = (img.getpixel((x, y)) for y in range(img.height) for x in range(img.width))
    assert not any(_near(px, pink, tolerance=40) for px in pixels if px[3] > 0)


def test_corner_pixel_is_transparent_outside_the_rounded_tile():
    img = icon.render(64)
    assert img.getpixel((0, 0))[3] == 0


def test_png_bytes_start_with_the_png_signature():
    data = icon.png_bytes(64)
    assert data.startswith(PNG_SIGNATURE)


def test_data_url_is_a_base64_png_that_decodes_to_the_same_bytes():
    url = icon.data_url(64)
    assert url.startswith("data:image/png;base64,")
    assert base64.b64decode(url.split(",", 1)[1]) == icon.png_bytes(64)


def test_icon_source_holds_no_hex_colour_literal():
    text = ICON_SRC.read_text(encoding="utf-8")
    assert HEX_LITERAL.search(text) is None


def test_preview_script_writes_three_pngs_at_16_32_64(tmp_path):
    out = tmp_path / "preview"
    result = subprocess.run(
        [sys.executable, str(PREVIEW), "--out", str(out)],
        capture_output=True, text=True, timeout=120,
    )
    assert result.returncode == 0, result.stderr
    for size in (16, 32, 64):
        path = out / f"icon-{size}.png"
        assert path.exists(), path
        with Image.open(path) as img:
            assert img.size == (size, size)
