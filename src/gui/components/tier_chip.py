"""Tier chip: the tier word, upper case, on the game's tier colour (spec section 9, DESIGN.md section 7).

Only QUAD, PENTA and HEXA get a coloured chip, because colour means "a highlight worth keeping". KO, DOUBLE
and TRIPLE are not chipped here. Colours come from tokens.py; no hex literal lives in this file.
"""
from __future__ import annotations

from html import escape

from gui import tokens

FILL = {
    "QUAD": tokens.TIER_QUAD,
    "PENTA": tokens.TIER_PENTA,
    "HEXA": tokens.TIER_HEXA,
}
CHIP_TIERS = tuple(FILL)


def chip_html(tier: str, count: int | None = None) -> str:
    """An inline chip for one kept tier, with its count after the word when given.

    Raises ValueError for any tier outside CHIP_TIERS, so a low tier can never be coloured by mistake.
    """
    if tier not in FILL:
        raise ValueError(f"no chip for tier {tier!r}; chips are for {', '.join(CHIP_TIERS)}")
    text = tier if count is None else f"{tier} {int(count)}"
    style = (f"display:inline-block;background:{FILL[tier]};color:{tokens.ON_TIER};"
             f"border-radius:{tokens.RADIUS_CHIP}px;padding:0 {tokens.SPACE_8}px;"
             f"margin-right:{tokens.SPACE_4}px;font-size:{tokens.SIZE_UI}px;font-weight:600;"
             f"font-stretch:87.5%;font-variant-numeric:tabular-nums;")
    return f'<span class="rvm-chip" data-tier="{tier}" style="{style}">{escape(text)}</span>'
