"""Design tokens for the local GUI: every colour, type size, spacing step and radius.

Source of truth: docs/DESIGN.md section 6. A test checks the colour table there matches
COLOURS below. Nothing else under src/gui may hold a hex colour literal; CSS strings use
@@NAME@@ placeholders that fill() swaps for these values.
"""
import re

# Colours (DESIGN.md section 6 table)
GROUND = "#131722"       # page background, a blue-black like a night map
PANEL = "#1B2130"        # grouped surfaces
LINE = "#2A3247"         # 1 px dividers and outlines
TEXT = "#E3E7F0"         # primary text, focus ring
TEXT_DIM = "#8E97AD"     # secondary text
WORKING = "#4FA3E0"      # a job is running
ERROR = "#E5484D"        # failed, needs action
TIER_QUAD = "#F2C14E"    # QUAD
TIER_PENTA = "#FF8A3D"   # PENTA
TIER_HEXA = "#FF4D8D"    # HEXA
TIER_LOW_1 = "#3B4359"   # KO outline
TIER_LOW_2 = "#596380"   # DOUBLE outline
TIER_LOW_3 = "#8089A3"   # TRIPLE outline
ON_TIER = "#131722"      # text on a tier fill

# Type: Bahnschrift is a system font on Windows, so nothing is downloaded.
FONT_STACK = 'Bahnschrift, "Segoe UI Variable", "Segoe UI", sans-serif'

# Size scale in px (DESIGN.md section 6)
SIZE_FINE = 12      # fine print
SIZE_UI = 14        # tables and buttons
SIZE_BODY = 16      # body
SIZE_SECTION = 20   # section heading
SIZE_TAB = 26       # tab heading
SIZE_REEL = 40      # the reel's total duration

# Spacing step 4 (DESIGN.md section 6), in px
SPACE_4 = 4
SPACE_8 = 8
SPACE_12 = 12
SPACE_16 = 16
SPACE_24 = 24
SPACE_32 = 32

# Radius in px (DESIGN.md section 6)
RADIUS_CHIP = 2     # chips and reel segments
RADIUS_PANEL = 6    # panels and buttons

_PLACEHOLDER = re.compile(r"@@([A-Z0-9_]+)@@")
_VALUES = {name: value for name, value in list(globals().items())
           if name.isupper() and not name.startswith("_")}


# copied from a sibling local GUI kit (tokens.py), shape only
def fill(css: str) -> str:
    """Swap every @@NAME@@ placeholder for its token value; an unknown name raises KeyError."""
    return _PLACEHOLDER.sub(lambda m: str(_VALUES[m.group(1)]), css)
