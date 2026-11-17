"""Design tokens (docs/DESIGN.md section 6): src/gui/tokens.py is the code source."""
import re
from pathlib import Path

import pytest

from gui import tokens

ROOT = Path(__file__).resolve().parents[2]
GUI_SRC = ROOT / "src" / "gui"
DESIGN_MD = ROOT / "docs" / "DESIGN.md"

HEX_LITERAL = re.compile(r"#(?:[0-9a-fA-F]{8}|[0-9a-fA-F]{6}|[0-9a-fA-F]{3})\b(?![-\w])")
EXTERNAL_URL = re.compile(r"https?://(?!localhost[:/]|127\.0\.0\.1[:/])[^\s'\"]+")


def _design_text():
    return DESIGN_MD.read_text(encoding="utf-8")


def _token_table_rows():
    """(token, hex) pairs from the section 6 table: | `name` | `#hex` | meaning |."""
    section = _design_text().split("## 6. Tokens", 1)[1].split("\n## ", 1)[0]
    return re.findall(r"\|\s*`([a-z0-9_]+)`\s*\|\s*`(#[0-9a-fA-F]{6})`", section)


def _gui_python_files():
    return sorted(p for p in GUI_SRC.rglob("*.py") if "__pycache__" not in p.parts)


def test_token_table_is_parsed():
    rows = _token_table_rows()
    assert len(rows) == 14, rows


@pytest.mark.parametrize("name,value", _token_table_rows())
def test_every_colour_row_in_design_md_exists_in_tokens(name, value):
    const = name.upper()
    assert hasattr(tokens, const), f"tokens.py has no {const} for DESIGN.md `{name}`"
    assert getattr(tokens, const).lower() == value.lower(), name


@pytest.mark.parametrize("const,value", [
    ("SIZE_FINE", 12), ("SIZE_UI", 14), ("SIZE_BODY", 16),
    ("SIZE_NAV", 22), ("SIZE_SECTION", 20), ("SIZE_TAB", 26), ("SIZE_TITLE", 32), ("SIZE_REEL", 40),
])
def test_type_size_scale_matches_design_md(const, value):
    # DESIGN.md section 6, "Size scale (px)": 12, 14, 16, 20, 22, 26, 32, 40
    assert getattr(tokens, const) == value


def test_size_scale_sentence_in_design_md_lists_every_size_token():
    # the size scale is a sentence in section 6, not a table; each token's px value must appear in it
    line = next(ln for ln in _design_text().splitlines() if ln.startswith("Size scale (px):"))
    for const in ("SIZE_FINE", "SIZE_UI", "SIZE_BODY", "SIZE_NAV", "SIZE_SECTION", "SIZE_TAB", "SIZE_TITLE", "SIZE_REEL"):
        assert re.search(rf"\b{getattr(tokens, const)} [a-z]", line), (const, line)


@pytest.mark.parametrize("const,value", [
    ("SPACE_4", 4), ("SPACE_8", 8), ("SPACE_12", 12),
    ("SPACE_16", 16), ("SPACE_24", 24), ("SPACE_32", 32),
])
def test_spacing_steps_match_design_md(const, value):
    # DESIGN.md section 6, "Spacing step 4": 4, 8, 12, 16, 24, 32
    assert getattr(tokens, const) == value


@pytest.mark.parametrize("const,value", [("RADIUS_CHIP", 2), ("RADIUS_PANEL", 6)])
def test_radius_matches_design_md(const, value):
    # DESIGN.md section 6, "Radius": 2 px on chips, 6 px on panels and buttons
    assert getattr(tokens, const) == value


def test_font_stack_matches_design_md():
    assert tokens.FONT_STACK == 'Bahnschrift, "Segoe UI Variable", "Segoe UI", sans-serif'
    assert "Bahnschrift, \"Segoe UI Variable\", \"Segoe UI\", sans-serif" in _design_text()


def test_fill_replaces_colour_and_number_placeholders():
    assert tokens.fill("color:@@GROUND@@;") == "color:#131722;"
    assert tokens.fill("font-size:@@SIZE_BODY@@px") == "font-size:16px"
    assert tokens.fill("gap:@@SPACE_8@@px;border-radius:@@RADIUS_PANEL@@px") == "gap:8px;border-radius:6px"


def test_fill_leaves_text_without_placeholders_alone():
    css = ".x{color:#abc}"
    assert tokens.fill(css) == css


def test_fill_raises_on_unknown_token_name():
    with pytest.raises(KeyError):
        tokens.fill("color:@@NOT_A_TOKEN@@")


def test_fill_refuses_non_token_module_names():
    # only the token table is reachable from fill(), not helpers or private names
    with pytest.raises(KeyError):
        tokens.fill("@@FILL@@")
    with pytest.raises(KeyError):
        tokens.fill("@@_VALUES@@")


def test_no_hex_colour_literal_outside_tokens():
    hits = []
    for p in _gui_python_files():
        if p.name == "tokens.py":
            continue
        for n, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
            for m in HEX_LITERAL.finditer(line):
                hits.append(f"{p.relative_to(ROOT).as_posix()}:{n}: {m.group(0)}")
    assert not hits, "hex colours outside src/gui/tokens.py:\n" + "\n".join(hits)


def test_no_font_face_in_gui_source():
    hits = [p.relative_to(ROOT).as_posix() for p in _gui_python_files()
            if "@font-face" in p.read_text(encoding="utf-8")]
    assert not hits, hits


def test_no_external_http_url_in_gui_source():
    hits = []
    for p in _gui_python_files():
        for n, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
            for m in EXTERNAL_URL.finditer(line):
                hits.append(f"{p.relative_to(ROOT).as_posix()}:{n}: {m.group(0)}")
    assert not hits, "external URLs in src/gui (only localhost allowed):\n" + "\n".join(hits)
