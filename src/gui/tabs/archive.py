"""Archive tab: kept QUAD or better clips for a best-of, read only (spec section 3).

One row per character with the kept count and a chip for each of QUAD, PENTA and HEXA that has clips.
Rows are a single table; each row carries its view_model testid. Lists this long are not virtualised:
the row check needs every row on the page.
"""
from __future__ import annotations

from html import escape

from nicegui import ui

from gui import tokens, view_model
from gui.components import tier_chip
from gui.tabs import heading

PAINTS_ROWS = True

EMPTY_COPY = ("Nothing archived yet. Clean up a live video and its QUAD or better clips are kept here "
              "for a best-of.")

_TABLE = (f"width:100%;border-collapse:collapse;font-size:{tokens.SIZE_UI}px;"
          f"font-variant-numeric:tabular-nums;")
_TH = (f"text-align:left;color:{tokens.TEXT_DIM};font-weight:600;padding:{tokens.SPACE_8}px 0;"
       f"border-bottom:1px solid {tokens.LINE};")
_TD = f"padding:{tokens.SPACE_8}px {tokens.SPACE_8}px {tokens.SPACE_8}px 0;border-bottom:1px solid {tokens.LINE};"


def _plural(count: int, word: str) -> str:
    return f"{count} {word}" if count == 1 else f"{count} {word}s"


def _tier_cell(tiers: dict) -> str:
    chips = [tier_chip.chip_html(t, tiers[t]) for t in tier_chip.CHIP_TIERS if tiers.get(t)]
    if not chips:
        return f'<span style="color:{tokens.TEXT_DIM};">-</span>'
    return "".join(chips)


def table_html(rows: list[dict]) -> str:
    """The archive table: a header row, then one row per character with its view_model testid."""
    body = []
    for row in rows:
        body.append(
            f'<tr data-testid="{row["testid"]}">'
            f'<td style="{_TD}">{escape(str(row.get("name") or ""))}</td>'
            f'<td style="{_TD}text-align:right;">{int(row.get("count") or 0)}</td>'
            f'<td style="{_TD}">{_tier_cell(row.get("tiers") or {})}</td>'
            "</tr>")
    return (f'<table style="{_TABLE}"><thead><tr>'
            f'<th style="{_TH}">Character</th>'
            f'<th style="{_TH}text-align:right;">Kept</th>'
            f'<th style="{_TH}">Tiers</th>'
            "</tr></thead><tbody>" + "".join(body) + "</tbody></table>")


def build(source) -> None:
    archive = view_model.snapshot(source)["archive"]
    rows = archive["by_character"]
    heading("Archive")
    if not rows:
        ui.label(EMPTY_COPY).style(f"font-size:{tokens.SIZE_BODY}px;color:{tokens.TEXT_DIM};")
        return
    ui.label(f"{_plural(int(archive['total'] or 0), 'clip')} kept for a best-of. QUAD or better only."
             ).style(f"font-size:{tokens.SIZE_BODY}px;color:{tokens.TEXT_DIM};")
    ui.html(table_html(rows))
