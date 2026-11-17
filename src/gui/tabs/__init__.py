"""Tab modules: one per key in gui/tabdefs.py, each with build(source) that paints that tab."""
from __future__ import annotations

from nicegui import ui

from gui import tokens


def heading(text: str):
    """The tab heading (DESIGN.md section 6: tab heading size, display weight and width)."""
    return ui.label(text).style(
        f"font-size:{tokens.SIZE_TAB}px;font-weight:600;font-stretch:87.5%;margin:0;"
    )
