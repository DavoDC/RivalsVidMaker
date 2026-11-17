# copied from a sibling local GUI kit (tabdefs.py)
"""Tab keys and labels, in lifecycle order (docs/DESIGN.md section 4).

The key is the deep link (?tab=<key>) and the id suffix of the tab button (tab-<key>).
Each key has a module gui/tabs/<key>.py with build(source) that paints that tab.
"""
from __future__ import annotations

TABS = (
    ("clips", "Clips"),
    ("compile", "Compile"),
    ("videos", "Videos"),
    ("archive", "Archive"),
    ("activity", "Activity"),
)

KEYS = tuple(key for key, _label in TABS)
DEFAULT = "clips"


def label_of(key: str) -> str:
    return dict(TABS)[key]
